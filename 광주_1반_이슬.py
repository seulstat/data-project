"""
--------------------------------
작성자: 이슬
작성목적: SKALA 데이터분석 및 AIOps 과목 [실습 1] 데이터 집계 및 [실습 2] Pydantic 검증 파이프라인 통합
작성일: 2026-07-20

변경사항 내역
- 2026-07-20 / 최초 버전 작성 / 실습 1 JSON 데이터 집계 기능 구현
- 2026-07-20 / 실습 2 반영 통합 / Pydantic v2 기반 SalesRecord 스키마 정의 및 타입 데이터 모델링 반영
- 2026-07-20 / 가독성 및 효율성 개선 / Single-Pass(단일 순회) 구조로 파싱과 동시에 유효성 검증 분리
- 2026-07-20 / 데이터 안전성 확보 / try-except 예외 처리를 통한 파일 입출력 및 JSONDecodeError 방어
- 2026-07-20 / 파일 입출력 다각화 / 검증 완료 데이터(CSV) 및 에러 로그(JSON) 내보내기 구현 (ensure_ascii 처리)
- 2026-07-20 / 파이프라인 무결성 검증 / safe_load_csv() 구현 및 finally 블록, assert문을 이용한 2차 건수 교차 검증 반영
- 2026-07-20 / 결함 수정 / CSV 재로드에 따른 딕셔너리 구조 변경에 맞춰 실습 1 연동부 문법 및 int() 형변환 전면 수정
--------------------------------
"""

from pathlib import Path
import json
import sys
from collections import Counter, defaultdict

# from dataclasses import dataclass
from typing import List, Optional  # TypedDict

# 라이브러리 추가
import csv
import logging
from pydantic import BaseModel, Field, ValidationError

# 로거 설정 기본화 (콘솔 출력용)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ==============
# 데이터 타입 정의 (TypedDict & dataclass)
# ==============

# class SaleDict(TypedDict):
#     # 오리지널 JSON 데이터 구조를 명시하기 위한 TypedDict
#     region: str
#     category: str
#     amount: int
#     month: str

# @dataclass
# class SaleRecord:
#     # 객체 지향적 접근 & 타입 안전성을 위한 dataclass
#     region: str
#     category: str
#     amount: int
#     month: str

#     @classmethod
#     def from_dict(cls, d: SaleDict) -> 'SaleRecord':
#         # dict 데이터를 dataclass 객체로 변환
#         return cls(
#             region=d['region'],
#             category=d['category'],
#             amount=int(d['amount']),
#             month=d['month']
#         )


# ==============
# [실습 2-2] Pydantic 스키마 정의 (기존 dataclass 대체)
# ==============
class SalesRecord(BaseModel):
    month: str = Field(min_length=1)
    region: str = Field(min_length=1)
    amount: int = Field(gt=0)
    category: Optional[str] = None


# ==============
# [실습 2-3] 검증 파이프라인 (valid / errors 분리)
# ==============
# 데이터 경로 지정
data_dir = Path("data")
raw_path = data_dir / "Python_Practice2_Data.json"

valid_records: List[SalesRecord] = []
error_records: List[dict] = []

try:
    # 원본 파일은 json.load로 딕셔너리 리스트로 가져오기
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data: List[dict] = json.load(f)

    # raw_data 한 번만 순회하여 즉시 분류
    for row in raw_data:
        try:
            # 딕셔너리를 Pydantic 모델에 언패킹하여 즉시 검증
            model = SalesRecord(**row)
            valid_records.append(model.model_dump())

        except ValidationError as e:
            # {"row": 오리지널_데이터, "error": 에러_내용} 구조로 할당
            error_records.append({"row": row, "error": str(e)})

            # ValidationError 내용을 확인하기 위한 출력
            print(f"[검증 실패 로그]: {e}\n")

    print(
        f"[성공] 파이프라인 검증 완료. Valid: {len(valid_records)}건 / Errors: {len(error_records)}건"
    )

except FileNotFoundError:
    print(f"[오류] 파일이 없습니다: {raw_path}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"[오류] JSON 파싱 에러: {e}")
    sys.exit(1)


# =================
# [실습 2-4] 1. valid record를 csv로, errors를 json으로 저장
# - model_dump() 사용 필수
# - json.dump ensure_ascii=False 설정 필수
# =================
valid_path = data_dir / "valid_records.csv"
error_path = data_dir / "error_records.json"

# valid_record.csv 저장
fieldnames = list(SalesRecord.model_fields.keys())  # 열 이름 뽑기
with open(valid_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(valid_records)

# error_record.json 저장
Path(error_path).write_text(
    json.dumps(error_records, ensure_ascii=False), encoding="utf-8"
)

# 1차 분류 건수 자체 검증 assert문
assert len(valid_records) == 100, "Valid 건수 검증 실패"
assert len(error_records) == 0, "Error 건수 검증 실패"
print(
    f"[검증 완료] 1차 분기 assert 통과! (Valid: {len(valid_records)} / Errors: {len(error_records)})"
)


# =================
# [실습 2-1] 예외 처리 + 파일 읽기
# =================
def safe_load_csv(file_path: Path) -> list | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            data = list(reader)  ##### 왜 list로 만드는거지?

        # 성공 로그 기록 및 데이터 변환
        logger.info(f"파일 로딩 성공: {file_path}")
        return data

    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {file_path}")
        return None

    finally:
        logger.info("로딩 종료")


# =================
# [실습 2-4] 2. valid csv 다시 읽어 건수 검증
# =================
reloaded = safe_load_csv(valid_path)

if reloaded is not None:
    assert len(reloaded) == len(valid_records), (
        "재로딩된 데이터 건수가 원본과 일치하지 않습니다."
    )
    print(f"[검증 완료] 2차 재로딩 assert 통과! len(reloaded)=={len(valid_records)}")
else:
    print("[오류] 데이터 재로딩에 실패하여 검증을 진행할 수 없습니다.")


sales = reloaded

# ==============
# raw_data 불러오기
# ==============

# 데이터 경로 지정
# data_dir = Path('data')
# raw_path = data_dir / 'Python_Practice2_Data.json'

# raw_data: List[SaleRecord] = []

# try:
#     # 파일 전체 내용을 문자열로 읽어오기
#     with open(raw_path, 'r', encoding='utf-8') as f:
#         raw_data: List[SaleDict] = json.load(f)

#     # 가공 편의성 및 타입 안전성을 위해 dataclass list로 변환
#     sales = [SaleRecord.from_dict(item) for item in raw_data]
#     print(f"[성공] 데이터 로딩 완료. 총 건수: {len(sales)}개\n")

# except FileNotFoundError:
#     print(f"[오류] 지정한 경로에 파일이 존재하지 않습니다: {raw_path}")
#     sys.exit(1)
# except json.JSONDecodeError as e:
#     print(f"[오류] JSON 형식이 올바르지 않습니다. 파일 내부 구조를 확인하세요. \n 에러 내용: {e}")
#     sys.exit(1)
# except Exception as e:
#     print(f"[시스템 오류] 예상치 못한 오류 발생: {e}")
#     sys.exit(1)


# ==============
# [실습 1-1] 리스트/딕셔너리 컴프리헨션
# ==============

# amount >= 1000인 거래만 필터링
filtered_sales = [r for r in sales if int(r["amount"]) >= 1000]  # 47개 데이터

# 지역별 총매출 dict를 컴프리헨션으로 계산
# - 중복 없는 region 명단을 set 컴프리헨션으로 추출
regions = {r["region"] for r in filtered_sales}

# - 추출한 지역을 순회하며 각 지역별 amount의 sum 구하는 dict 컴프리헨션
region_total = {
    r: sum(int(row["amount"]) for row in filtered_sales if row["region"] == r)
    for r in regions
}

### 체크포인트 확인용 print
print(f"1-1) filtered_sales 개수: {len(filtered_sales)}")
print(f"1-2) region_total 결과: {region_total}")


# ==============
# [실습 1-2] Counter + defaultdict
# ==============

# Counter: 빈도 집계
region_cnts = Counter(r["region"] for r in sales)

# 체크포인트: Counter.most_common() 순서 및 상위 3개 추출
top3_regions = region_cnts.most_common(3)
print(f"\n2) 지역별 거래 건수 Top 3: {top3_regions}")

# defaultdic(list)를 활용하여 카테고리별 amount 리스트 그룹화
category_amounts = defaultdict(list)
for r in sales:
    category_amounts[r["category"]].append(int(r["amount"]))


# ==============
# [실습 1-3] 제너레이터 - 메모리 비교
# ==============


# generator 함수 정의
def get_high_sales_gen(data):
    for r in data:
        if int(r["amount"]) > 1000:
            yield r


# 비교 대상 object 생성
high_sales_list = [r for r in sales if int(r["amount"]) > 1000]
high_sales_gen = get_high_sales_gen(sales)  # generator 객체 자체 유지

list_mem = sys.getsizeof(high_sales_list)
gen_mem = sys.getsizeof(high_sales_gen)

print("\n3) 메모리 비교 (sys.getsizeof):")
print(f"    - list memory: {list_mem} bytes")
print(f"    - generator memory: {gen_mem} bytes")
print(f"    - generator가 더 효율적인가? {gen_mem < list_mem}")


# ==============
# [실습 1-4] 종합 - 월별 카테고리 매출 집계
# ==============

# 월별 카테고리별 매출 합산을 위한 defaultdict(float)
monthly_cat_sales = defaultdict(float)

for r in sales:
    key = (r["month"], r["category"])
    monthly_cat_sales[key] += int(r["amount"])

# 금액 기준 내림차순 정렬 및 Top 3 추출 구체화
# 정렬 기준 dict.items()를 받아서 x[1](금액)을 기준으로 내림차순 정렬(reverse=True)
sorted_monthly_sales = sorted(
    monthly_cat_sales.items(), key=lambda x: x[1], reverse=True
)
top3_monthly_sales = sorted_monthly_sales[:3]

print("\n4) 월별 카테고리 매출 집계 Top 3 (금액 내림차순):")
for (month, category), total_amount in top3_monthly_sales:
    print(f"    - [{month}] {category}: {total_amount}원")
