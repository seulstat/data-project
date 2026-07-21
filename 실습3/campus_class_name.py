"""
==============================================================================
작 성 자: 이슬
프로그램명 : 실습 3 - Pandas EDA / Polars Lazy / DuckDB SQL 비교
설  명     : 같은 폴더의 sales_100k.csv(매출 데이터)를 대상으로
             1) Pandas 기초 EDA + IQR 이상치 제거
             2) Pandas named aggregation 집계 (region·category별 총매출/평균/건수)
             3) 동일 집계를 Polars Lazy API로 재작성
             4) DuckDB SQL 집계 + timeit 성능 비교
             를 수행한다.


변경내역   : 2026-07-21  v1.0  이슬   최초 작성
==============================================================================
"""

from __future__ import annotations

import sys
import timeit
from pathlib import Path

try:
    import pandas as pd
    import polars as pl
    import duckdb
except ImportError as e:
    print(f"[오류] 필수 라이브러리 임포트 실패: {e}")
    print("아래 명령으로 의존성을 설치하세요:\n    pip3 install -r requirements.txt")
    sys.exit(1)

# ------------------------------------------------------------------
# 공통 상수
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "sales_100k.csv"
CLEAN_CSV_PATH = BASE_DIR / "sales_100k_clean.csv"
AGG_CSV_PATH = BASE_DIR / "agg_region_category.csv"

REQUIRED_COLS = ["region", "category", "amount"]
GROUP_COLS = ["region", "category"]
TIMEIT_NUMBER = 5  # 세 도구 공통 timeit 반복 횟수 (공정 비교)


def load_data(path: Path) -> pd.DataFrame:
    """CSV를 로딩하고 필수 컬럼 존재 여부를 검증한다."""
    if not path.exists():
        print(f"[오류] '{path.name}' 파일을 찾을 수 없습니다.")
        print(f"'{path.parent}' 폴더에 sales_100k.csv를 넣어주세요.")
        sys.exit(1)

    try:
        df = pd.read_csv(path, encoding="utf-8")
    except pd.errors.EmptyDataError:
        print(f"[오류] '{path.name}' 파일이 비어 있습니다.")
        sys.exit(1)
    except (pd.errors.ParserError, UnicodeDecodeError) as e:
        print(f"[오류] '{path.name}' 파싱/인코딩 실패: {e}")
        sys.exit(1)

    if df.empty:
        print("[오류] 로딩된 데이터가 0행입니다.")
        sys.exit(1)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        print(f"[오류] 필수 컬럼 누락: {missing}")
        sys.exit(1)

    return df


def run_eda_and_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """기초 EDA를 출력하고 IQR 방법으로 amount 이상치를 제거한다.

    반환하는 lower/upper는 Polars·DuckDB 집계에도 동일하게 적용되어
    세 도구의 집계 결과를 일치시키는 데 쓰인다.
    """
    print("\n===== [실습 1] df.info() =====")
    df.info()

    print("\n===== [실습 1] 컬럼별 결측치 개수 =====")
    print(df.isnull().sum())

    # 집계·후속 실습(실습 4)에 필요한 핵심 컬럼 결측 제거
    before = len(df)
    df = df.dropna(subset=REQUIRED_COLS)

    q1 = df["amount"].quantile(0.25)
    q3 = df["amount"].quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr

    clean = df[df["amount"].between(lower, upper)].reset_index(drop=True)

    print(f"\n===== [실습 1] IQR 이상치 제거 (lower={lower:.2f}, upper={upper:.2f}) =====")
    print(f"결측 제거 전: {before:,}행 -> 결측 제거 후: {len(df):,}행 -> 이상치 제거 후: {len(clean):,}행")

    if clean.empty:
        print("[오류] 이상치 제거 후 데이터가 0행입니다. IQR 기준을 확인하세요.")
        sys.exit(1)

    return clean, lower, upper


def agg_pandas(df: pd.DataFrame) -> pd.DataFrame:
    """region·category별 총매출/평균/건수를 named aggregation으로 집계한다."""
    return (
        df.groupby(GROUP_COLS)
        .agg(total=("amount", "sum"), mean=("amount", "mean"), count=("amount", "count"))
        .reset_index()
        .sort_values("total", ascending=False)
        .reset_index(drop=True)
    )


def agg_polars(csv_path: Path, lower: float, upper: float) -> pl.DataFrame:
    """Pandas와 동일한 필터·집계를 Polars Lazy API로 재작성한다."""
    return (
        pl.scan_csv(csv_path)
        .filter(
            pl.col("amount").is_not_null()
            & pl.col("region").is_not_null()
            & pl.col("category").is_not_null()
            & pl.col("amount").is_between(lower, upper)
        )
        .group_by(GROUP_COLS)
        .agg(
            pl.col("amount").sum().alias("total"),
            pl.col("amount").mean().alias("mean"),
            pl.col("amount").count().alias("count"),
        )
        .sort("total", descending=True)
        .collect()
    )


def agg_duckdb(csv_path: Path, lower: float, upper: float) -> pd.DataFrame:
    """Pandas와 동일한 필터·집계를 DuckDB SQL로 재작성한다."""
    query = """
        SELECT region, category,
               SUM(amount) AS total,
               AVG(amount) AS mean,
               COUNT(amount) AS count
        FROM read_csv_auto(?)
        WHERE amount IS NOT NULL
          AND region IS NOT NULL
          AND category IS NOT NULL
          AND amount BETWEEN ? AND ?
        GROUP BY region, category
        ORDER BY total DESC
    """
    return duckdb.sql(query, params=[str(csv_path), lower, upper]).df()


def benchmark(clean_df: pd.DataFrame, csv_path: Path, lower: float, upper: float) -> pd.DataFrame:
    """세 도구의 동일 집계 로직을 동일 반복 횟수(timeit)로 성능 비교한다."""
    col = f"total_sec(number={TIMEIT_NUMBER})"
    elapsed = {
        "pandas": timeit.timeit(lambda: agg_pandas(clean_df), number=TIMEIT_NUMBER),
        "polars": timeit.timeit(lambda: agg_polars(csv_path, lower, upper), number=TIMEIT_NUMBER),
        "duckdb": timeit.timeit(lambda: agg_duckdb(csv_path, lower, upper), number=TIMEIT_NUMBER),
    }
    return (
        pd.DataFrame(elapsed.items(), columns=["tool", col])
        .sort_values(col)
        .reset_index(drop=True)
    )


def main() -> None:
    """전체 실습 1~4를 순서대로 실행하고 실습 4 연계 산출물을 저장한다."""
    try:
        raw_df = load_data(CSV_PATH)
        clean_df, lower, upper = run_eda_and_clean(raw_df)

        print("\n===== [실습 2] Pandas named aggregation (region·category, total 내림차순) =====")
        pandas_agg = agg_pandas(clean_df)
        print(pandas_agg)

        print("\n===== [실습 3] Polars Lazy 집계 =====")
        polars_agg = agg_polars(CSV_PATH, lower, upper)
        print(polars_agg)

        print("\n===== [실습 4] DuckDB SQL 집계 =====")
        duckdb_agg = agg_duckdb(CSV_PATH, lower, upper)
        print(duckdb_agg)

        print(f"\n===== [실습 4] 세 도구 timeit 성능 비교 (number={TIMEIT_NUMBER}) =====")
        print(benchmark(clean_df, CSV_PATH, lower, upper))

        # 실습 4(시각화·통계 검정) 연계용 산출물 저장
        clean_df.to_csv(CLEAN_CSV_PATH, index=False, encoding="utf-8")
        pandas_agg.to_csv(AGG_CSV_PATH, index=False, encoding="utf-8")
        print(f"\n[완료] 정제 데이터 저장: {CLEAN_CSV_PATH.name} ({len(clean_df):,}행)")
        print(f"[완료] 집계 결과 저장: {AGG_CSV_PATH.name} ({len(pandas_agg):,}행)")

    except Exception as e:
        print(f"[오류] 처리 중 예외가 발생했습니다: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
