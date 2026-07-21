'''
--------------------------------
작성자: 이슬
작성목적: SKALA 데이터분석 및 AIOps 과목 [종합 실습] 과제 수행: pytest, ruff 검사 코드
작성일: 2026-07-20

변경사항 내역
- 2026-07-20 / 최초 버전 작성 / pytest로 스키마 검증 테스트 코드, ruff 코드로 코드 스타일 검사 코드 작성
-----------------------
'''

from 종합실습.data_pipeline import validate_ip, validate_country


# ==========================================
# 1. 정상 데이터 통과 테스트 (Happy Path)
# ==========================================
def test_validate_ip_success():
    """정상적인 IP 데이터가 들어왔을 때 통과하는지 테스트"""
    good_ip = {
        "country": "South Korea",
        "city": "Seoul",
        "lat": 37.566,
        "lon": 126.978,
        "isp": "KT",
    }
    result = validate_ip(good_ip)
    assert result is not None
    assert result.city == "Seoul"


def test_validate_country_success():
    """정상적인 국가 데이터가 들어왔을 때 통과하는지 테스트"""
    good_country = {
        "name": "Korea",
        "population": 51780000,
        "area": 100210.0,
        "region": "Asia",
        "capital": "Seoul",
    }
    result = validate_country(good_country)
    assert result is not None
    assert result.population == 51780000


# ==========================================
# 2. 비정상 데이터 차단 테스트 (Edge Case / 범위 검증)
# ==========================================
def test_validate_ip_invalid_latitude():
    """위도 범위를 벗어난 잘못된 데이터(-90 ~ 90 범위를 초과)가 오면 None을 반환하는지 테스트"""
    bad_ip = {
        "country": "South Korea",
        "city": "Seoul",
        "lat": 120.5,  # ❌ 위도는 90도를 넘을 수 없음
        "lon": 126.978,
        "isp": "KT",
    }
    result = validate_ip(bad_ip)
    assert (
        result is None
    )  # Pydantic이 ValidationError를 던져 함수 내부에서 None을 반환해야 함


def test_validate_country_invalid_population():
    """인구수가 음수(-500)인 말이 안 되는 데이터가 들어왔을 때 차단되는지 테스트"""
    bad_country = {
        "name": "Ghost Country",
        "population": -500,  # ❌ 인구수는 0 이상이어야 함 (ge=0)
        "area": 5000.0,
        "region": "Unknown",
        "capital": "None",
    }
    result = validate_country(bad_country)
    assert result is None
