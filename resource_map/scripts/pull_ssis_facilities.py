# -*- coding: utf-8 -*-
"""한국사회보장정보원 사회복지시설정보 OpenAPI 에서 이주민 관련 시설을 받는다.

`FRAME_COVERAGE.md` 는 오랫동안 이 출처를 "OpenAPI 전용이고 DATA_GO_KR_KEY 가 비어
있다"로 적어 두었다. 키가 생겼으므로 여기서 받는다.

이 API 가 다른 명부보다 나은 점은 두 가지다. 시설마다 정부가 부여한 `fcltCd` 와
소관 시군구 코드가 붙어 있어서 이름 표기가 달라도 같은 시설을 가리킨다는 것이 확인되고,
`getFcltKindCodeInfoInqire` 가 시설종류 259개의 전체 목록을 주므로 **분모가 무엇인지를
추측하지 않아도 된다.**

받는 종류는 이주민을 직접 대상으로 하는 것만이다. 사회복지시설 전체는 수만 곳이고
그 대부분은 이 데이터셋의 범위 밖이다.

  140101  다문화가족지원센터            (가족센터 명부의 대조용 분모)
  140100  다문화가족복지시설            (상위 코드)
  100103  성매매피해지원시설 외국인지원시설

인증키는 `data/data go kr/data go kr key.txt` 에 있고 **URL 인코딩된 형태**다.
`requests` 의 `params` 로 넘기면 한 번 더 인코딩되어 서명이 깨지므로 반드시 디코딩해서
넘긴다. 이것이 이 API 에서 가장 흔한 실패 원인이다.

Run:  python scripts/v2/pull_ssis_facilities.py
"""
from __future__ import annotations
import argparse
import io
import os
import sys
import time
import urllib.parse as up
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW2 = os.path.join(ROOT, "data", "raw", "v2")
INTERIM = os.path.join(ROOT, "data", "interim")
BASE = "https://apis.data.go.kr/B554287/sclWlfrFcltInfoInqirService1"

WANT = [
    ("140101", "다문화가족지원센터"),
    ("140100", "다문화가족복지시설"),
    ("100103", "성매매피해지원시설 외국인지원시설"),
]

COLS = ["name_ko", "name_en", "category", "subcategory", "governing_ministry",
        "operator_type", "operator_name", "road_address", "sido", "sigungu",
        "phone", "website", "target_population", "services_provided",
        "established_year", "closed_year", "operational_status", "source_url",
        "source_date", "notes"]

# 이 데이터셋은 2026-07-01 개편 이후의 행정구역 이름을 쓴다. 인구 분모가 개편 전
# 17개 시도 기준이므로 틀은 개편 전 이름을 유지한다(kird-2026-admin-reorg 결정).
SIDO_BACK = {
    "전남광주통합특별시": "",          # 광주 인지 전남 인지는 시군구가 정한다
    "강원특별자치도": "강원도",
    "전북특별자치도": "전라북도",
    "제주특별자치도": "제주특별자치도",
}
INCHEON_BACK = {"제물포구": "중구", "영종구": "중구", "검단구": "서구",
                "서해구": "서구"}


def load_key():
    p = os.path.join(ROOT, "data", "data go kr", "data go kr key.txt")
    if os.path.exists(p):
        return up.unquote(io.open(p, encoding="utf-8").read().strip())
    k = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if k:
        return up.unquote(k)
    raise SystemExit("no data.go.kr key found")


def call(op, key, params, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}/{op}", params=dict(params, serviceKey=key),
                             timeout=30)
            if r.status_code == 200:
                return ET.fromstring(r.text)
        except Exception:
            pass
        time.sleep(1 + attempt)
    return None


def pull(op, key, extra):
    """Every page of one operation. Returns rows and the server's own total, so
    a short read is visible instead of passing for a complete answer."""
    rows, page, total = [], 1, None
    while True:
        root = call(op, key, dict(extra, numOfRows=100, pageNo=page))
        if root is None:
            print(f"    page {page}: no response")
            break
        rc = root.findtext(".//resultCode")
        if rc != "00":
            print(f"    page {page}: {rc} {root.findtext('.//resultMsg')}")
            break
        items = list(root.iter("item"))
        rows += [{c.tag: (c.text or "").strip() for c in it} for it in items]
        total = int(root.findtext(".//totalCount") or 0)
        if not items or page * 100 >= total:
            break
        page += 1
        time.sleep(0.2)
    return rows, total


def back_convert(sgg_name):
    """'서울특별시 중랑구' -> ('서울특별시', '중랑구'), pre-2026 naming."""
    parts = str(sgg_name or "").split()
    if not parts:
        return "", ""
    sido, sgg = parts[0], " ".join(parts[1:])
    if sido == "전남광주통합특별시":
        sido = "광주광역시" if sgg in ("동구", "서구", "남구", "북구",
                                   "광산구") else "전라남도"
    sido = SIDO_BACK.get(sido, sido) or sido
    if sido == "인천광역시":
        sgg = INCHEON_BACK.get(sgg, sgg)
    return sido, sgg


def main(a):
    key = load_key()
    print("=== 시설종류 코드 (분모의 정의) ===")
    root = call("getFcltKindCodeInfoInqire", key, {"numOfRows": 500, "pageNo": 1})
    kinds = [{c.tag: (c.text or "") for c in it} for it in root.iter("item")] \
        if root is not None else []
    print(f"  종류 {len(kinds)}개")
    if kinds:
        pd.DataFrame(kinds).to_csv(
            os.path.join(INTERIM, "ssis_facility_kinds.csv"),
            index=False, encoding="utf-8-sig")

    out = []
    for code, label in WANT:
        rows, total = pull("getFcltListInfoInqire", key, {"fcltKindCd": code})
        print(f"  {code} {label}: totalCount {total}, 받은 행 {len(rows)}")
        if total is not None and len(rows) != total:
            print(f"    WARNING 서버가 {total}건이라 했는데 {len(rows)}건만 받았다")
        for r in rows:
            sido, sgg = back_convert(r.get("jrsdSggNm", ""))
            out.append({
                "name_ko": r.get("fcltNm", ""),
                "name_en": r.get("fcltEngNm", ""),
                "category": "multicultural_family_center"
                            if code.startswith("1401") else "violence_victim_shelter",
                "subcategory": r.get("fcltKindNm", "") or label,
                "governing_ministry": "보건복지부",
                "operator_type": "", "operator_name": r.get("rprsNm", ""),
                "road_address": r.get("fcltAddr", "") or r.get("rnAddr", ""),
                "sido": sido, "sigungu": sgg,
                "phone": r.get("fcltTelno", ""), "website": "",
                "target_population": "다문화가족" if code.startswith("1401") else "이주여성",
                "services_provided": "", "established_year": "", "closed_year": "",
                "operational_status": "active",
                "source_url": "https://www.data.go.kr/data/15000578/openapi.do",
                "source_date": a.date,
                "notes": f"한국사회보장정보원 사회복지시설정보 OpenAPI, "
                         f"시설종류코드 {code}, 시설코드 {r.get('fcltCd','')}. "
                         f"원문 시군구 표기 {r.get('jrsdSggNm','')}",
            })
    if not out:
        print("아무것도 받지 못했다")
        return 1
    df = pd.DataFrame(out)
    for c in COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLS]
    p = os.path.join(RAW2, "welfare", "ssis_migrant_welfare_facilities.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    df.to_csv(p, index=False, encoding="utf-8-sig")
    print(f"\nwrote {p} ({len(df)} rows)")
    print(df.sido.value_counts().to_string())
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-08-20")
    sys.exit(main(ap.parse_args()))
