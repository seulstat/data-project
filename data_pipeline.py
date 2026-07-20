'''
--------------------------------
작성자: 이슬
작성목적: SKALA 데이터분석 및 AIOps 과목 [종합 실습] 과제 수행
작성일: 2026-07-20

변경사항 내역
- 2026-07-20 / 최초 버전 작성 / 비동기 수집, 스키마 검증, 저장 및 성능 비교 코드 작성
-----------------------
'''

import asyncio
import httpx
from pydantic import BaseModel, Field, ValidationError
import time
import pandas as pd

# 수집할 3개의 Public API 엔드포인트 정의
API_URLS = {
    "weather": "https://api.open-meteo.com/v1/forecast?latitude=37.5665&longitude=126.9780&hourly=temperature_2m,precipitation_probability&forecast_days=3&timezone=Asia/Seoul",
    "country": "https://countries.dev/alpha/KOR",
    "ip": "http://ip-api.com/json/8.8.8.8",
}


async def fetch_data(client, name, url):
    """단일 API 비동기 호출 및 상태 검증"""
    try:
        response = await client.get(url)
        response.raise_for_status()  # 상태 코드가 200번대가 아니면 예외 발생
        print(f"✅ [{name}] API 응답 성공 (Status: {response.status_code})")
        return name, response.json()
    except httpx.HTTPStatusError as e:
        print(f"❌ [{name}] API 응답 에러: {e}")
        return name, None
    except Exception as e:
        print(f"❌ [{name}] 네트워크 또는 예상치 못한 에러: {e}")
        return name, None


async def extract_data():
    """asyncio.gather를 활용한 동시 수집"""
    print("데이터 수집을 시작합니다.")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 각 API 호출을 위한 코루틴(작업) 리스트 생성
        tasks = [fetch_data(client, name, url) for name, url in API_URLS.items()]

        # 3개의 API를 병렬로 동시 실행
        results = await asyncio.gather(*tasks)

        # 수집된 데이터를 딕셔너리 형태로 반환
        collected_data = {name: data for name, data in results if data is not None}
        return collected_data


# API 수집
extracted = asyncio.run(extract_data())
print(f"\n총 {len(extracted)}개의 API 데이터 수집 완료!")


### 스키마 검증
# ==========================================
# 1. Pydantic v2 모델 정의 (실제 데이터 규격 반영)
# ==========================================
class HourlyWeather(BaseModel):
    time: list[str]
    temperature_2m: list[float]
    precipitation_probability: list[int]


class WeatherData(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    hourly: HourlyWeather


class CountryData(BaseModel):
    # 💡 제공해주신 규격에 맞춰 name과 capital을 단순 문자열(str)로 수정했습니다.
    name: str
    population: int = Field(ge=0)
    area: float = Field(ge=0)
    region: str
    capital: str


class IpData(BaseModel):
    country: str
    city: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    isp: str


# ==========================================
# 2. 데이터 검증 함수
# ==========================================
def validate_weather(data: dict) -> WeatherData | None:
    try:
        return WeatherData(**data)
    except ValidationError as e:
        print(f"❌ 날씨 데이터 검증 실패:\n{e}")
        return None


def validate_country(data: dict | list) -> CountryData | None:
    try:
        target_data = data[0] if isinstance(data, list) else data
        return CountryData(**target_data)
    except ValidationError as e:
        print(f"❌ 국가 데이터 검증 실패:\n{e}")
        return None


def validate_ip(data: dict) -> IpData | None:
    try:
        return IpData(**data)
    except ValidationError as e:
        print(f"❌ IP 데이터 검증 실패:\n{e}")
        return None


# ==========================================
# 3. CSV vs Parquet 저장 및 성능 비교 함수
# ==========================================
def save_and_compare_performance(validated_data: BaseModel, file_prefix: str):
    """검증된 데이터를 DataFrame으로 변환 후 I/O 성능을 비교합니다."""

    # 💡 Weather 데이터처럼 구조가 중첩(Nested)된 경우를 위해 분기 처리합니다.
    if hasattr(validated_data, "hourly"):
        # hourly 내부의 리스트들을 행(Row) 형태로 풀어서 데이터프레임으로 만듭니다.
        df = pd.DataFrame(validated_data.hourly.model_dump())
        # 공통 정보인 위도, 경도, 타임존을 열로 추가해줍니다.
        df["latitude"] = validated_data.latitude
        df["longitude"] = validated_data.longitude
        df["timezone"] = validated_data.timezone
    else:
        # 일반적인 1차원 데이터(Country, IP) 처리
        df = pd.DataFrame([validated_data.model_dump()])

    csv_file = f"{file_prefix}.csv"
    parquet_file = f"{file_prefix}.parquet"

    print(f"\n[{file_prefix.upper()} 데이터 저장 및 읽기 성능 비교]")

    # 1. CSV 처리
    start = time.time()
    df.to_csv(csv_file, index=False)
    csv_write = time.time() - start

    start = time.time()
    pd.read_csv(csv_file)
    csv_read = time.time() - start

    # 2. Parquet 처리
    start = time.time()
    df.to_parquet(parquet_file, index=False)
    parquet_write = time.time() - start

    start = time.time()
    pd.read_parquet(parquet_file)
    parquet_read = time.time() - start

    print(f" - CSV     | 쓰기: {csv_write:.5f}초 | 읽기: {csv_read:.5f}초")
    print(f" - Parquet | 쓰기: {parquet_write:.5f}초 | 읽기: {parquet_read:.5f}초")


# ==========================================
# 4. 메인 실행부 (3개 데이터 동시 처리 및 검증 테스트)
# ==========================================
if __name__ == "__main__":
    # 3개 API의 가상 수집 결과 데이터 (완전체 샘플)
    sample_collected_data = {
        "weather": {
            "latitude": 37.56,
            "longitude": 126.97,
            "timezone": "GMT",
            "hourly": {
                "time": ["2026-07-20T11:00", "2026-07-20T12:00"],
                "temperature_2m": [24.2, 25.0],
                "precipitation_probability": [51, 40],
            },
        },
        "country": {
            "area": 100210,
            "name": "Korea (Republic of)",
            "population": 51780579,
            "region": "Asia",
            "capital": "Seoul",
        },
        "ip": {
            "country": "South Korea",
            "city": "Seoul",
            "lat": 37.511,
            "lon": 126.974,
            "isp": "KT",
        },
    }

    print("\n--- [1단계] 데이터 검증 시작 ---")
    valid_weather = validate_weather(sample_collected_data.get("weather", {}))
    valid_country = validate_country(sample_collected_data.get("country", {}))
    valid_ip = validate_ip(sample_collected_data.get("ip", {}))

    print("\n--- [2단계] 포맷별 성능 비교 및 저장 시작 ---")
    if valid_weather:
        save_and_compare_performance(valid_weather, "weather_data")
    if valid_country:
        save_and_compare_performance(valid_country, "country_data")
    if valid_ip:
        save_and_compare_performance(valid_ip, "ip_data")

    print(
        "\n✅ 3개 데이터 모두 검증 완료 및 파일 저장 성능 비교 출력이 종료되었습니다."
    )
