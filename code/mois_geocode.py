"""행정구역 코드 기반 join 시스템 (2024 기준 앵커, FIPS식).

admdong2024 소스 geojson의 공식 행정코드(시도 2자리 / 시군구 5자리 / 행정동 8자리)를
정규 테이블로 만들고, MOIS·KIS의 '이름'을 alias 규칙으로 정규화해 코드로 매핑한다.
이름 매칭의 깨지기 쉬움을 코드 join으로 대체하고, 매핑 불가 항목을 체계적으로 missing 리포트.

핵심:
  build_tables()        -> ADMIN(시도/시군구/읍면동 코드 테이블) 반환 + admin2024.json 저장
  geocode_sido/sgg/emd  -> 이름 → 코드 (alias 규칙 적용). 실패 시 None.
2024년에 사라진(병합·개명) 과거 동은 2024 코드가 없으므로 None → '진짜 missing'으로 분류.
"""
from __future__ import annotations
import os, re, json

from kird import ROOT  # noqa: E402
SRC_GEO = os.path.join(ROOT, "_emd_geo", "admdong2024.geojson")
OUT = os.path.join(ROOT, "05_dashboard", "data", "admin2024.json")

SEP = re.compile(r"[\s·.,・ㆍᆞ‧･()]")
def norm(s: str) -> str:
    return SEP.sub("", s or "").strip()

# ---- 시도 alias: MOIS/KIS 표기 → 2024 geojson 표기(신명칭) ----
SIDO_ALIAS = {
    "강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도",
    "강원특별자치도": "강원특별자치도", "전북특별자치도": "전북특별자치도", "제주특별자치도": "제주특별자치도",
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "강원": "강원특별자치도", "전북": "전북특별자치도", "제주": "제주특별자치도",
    "경기": "경기도", "충북": "충청북도", "충남": "충청남도",
    "경북": "경상북도", "경남": "경상남도", "전남": "전라남도",
}
def canon_sido(name: str) -> str:
    n = (name or "").strip()
    return SIDO_ALIAS.get(n, n)

# ---- 동명 변형 후보 (제N동 ↔ N동, 면↔읍) ----
def dong_variants(dong: str):
    out = {dong}
    m = re.match(r"^(.*?)제(\d+동)$", dong)      # 고덕제1동 -> 고덕1동
    if m: out.add(m.group(1) + m.group(2))
    m = re.match(r"^(.*?)(\d+동)$", dong)         # 고덕1동 -> 고덕제1동
    if m and "제" not in m.group(1)[-1:]: out.add(m.group(1) + "제" + m.group(2))
    # 숫자접미 N동 → 통합동(2024년 합쳐진 경우): 고잔1동·고잔2동 → 고잔동, 가능3동 → 가능동.
    # (2024에 실제 통합동이 있을 때만 매칭되므로 분동 유지 지역은 영향 없음)
    base = re.sub(r"제?\d+동$", "동", dong)
    if base != dong: out.add(base)
    # '본동' 통합형: 원곡본동·소사본동 → 원곡동·소사동
    if dong.endswith("본동"): out.add(dong[:-2] + "동")
    if dong.endswith("면"): out.add(dong[:-1] + "읍")
    elif dong.endswith("읍"): out.add(dong[:-1] + "면")
    return out

# ---- 시군구(구) alias: 과거 경북 군위군 → 2023 대구 편입 ----
SGG_SIDO_MOVE = {("경상북도", "군위군"): "대구광역시"}

# ---- 시군구 개명/승격 alias: (정규화 sido, 정규화 sgg) → 2024 sggnm(정규화) ----
SGG_RENAME = {
    ("인천광역시", "남구"): "미추홀구",      # 2018 미추홀구 개명
    ("경기도", "여주군"): "여주시",          # 2013 시 승격
}


def build_tables():
    src = json.load(open(SRC_GEO, encoding="utf-8"))
    sido_t, sgg_t, emd_t = {}, {}, {}
    # 이름 인덱스 (정규화 키 → 코드)
    idx_sido, idx_sgg, idx_emd, idx_emd_loose, si_children = {}, {}, {}, {}, {}
    for f in src["features"]:
        p = f["properties"]
        sido_c, sgg_c, adm_c = p["sido"], p["sgg"], p["adm_cd"]
        sidonm, sggnm = p["sidonm"], p["sggnm"]
        pre = sidonm + " " + sggnm + " "
        dong = p["adm_nm"][len(pre):] if p["adm_nm"].startswith(pre) else p["adm_nm"].split(" ")[-1]
        sido_t[sido_c] = sidonm
        sgg_t[sgg_c] = {"sido_code": sido_c, "sidonm": sidonm, "sggnm": sggnm}
        emd_t[adm_c] = {"sgg": sgg_c, "sido_code": sido_c, "sidonm": sidonm, "sggnm": sggnm, "dong": dong}
        idx_sido[norm(sidonm)] = sido_c
        idx_sgg[(norm(sidonm), norm(sggnm))] = sgg_c
        idx_emd[(norm(sidonm), norm(sggnm), norm(dong))] = adm_c
        idx_emd_loose.setdefault((norm(sidonm), norm(dong)), adm_c)
        # 'OO시OO구' → 부모 시(OO시)의 자식 구 코드 목록 (초기연도 시-단위 보고 확장용)
        m = re.match(r"^(.+?시)(.+구)$", sggnm)
        if m:
            si_children.setdefault((sido_c, norm(m.group(1))), set()).add(sgg_c)
    tables = {"sido": sido_t, "sigungu": sgg_t, "emd": emd_t}
    json.dump(tables, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return tables, (idx_sido, idx_sgg, idx_emd, idx_emd_loose, {k: sorted(v) for k, v in si_children.items()})


# 인덱스는 첫 호출 때 만든다. 소스 geojson이 34MB라, alias 규칙만 가져다 쓰는
# 모듈(admin_codes.py)이 import 한 번에 그걸 다 읽는 일이 없도록 지연 구축한다.
_BUILT = {}
_LAZY = ("TABLES", "IDX_SIDO", "IDX_SGG", "IDX_EMD", "IDX_EMD_LOOSE", "SI_CHILDREN")


def _tables():
    if not _BUILT:
        t, (a, b, c, d, e) = build_tables()
        _BUILT.update(TABLES=t, IDX_SIDO=a, IDX_SGG=b, IDX_EMD=c,
                      IDX_EMD_LOOSE=d, SI_CHILDREN=e)
    return _BUILT


def __getattr__(name):
    if name in _LAZY:
        return _tables()[name]
    raise AttributeError(name)


def geocode_sido(sido: str):
    return _tables()["IDX_SIDO"].get(norm(canon_sido(sido)))


def geocode_sgg(sido: str, sgg: str):
    """단일 시군구 코드. 'OO시'(구 보유)처럼 단일 코드가 없으면 None → geocode_sgg_codes 사용."""
    s = canon_sido(sido)
    s = SGG_SIDO_MOVE.get((sido, (sgg or "").strip()), s)        # 군위군 등 이동
    sg2 = SGG_RENAME.get((norm(s), norm(sgg)), sgg)              # 남구→미추홀구 등
    key = (norm(s), norm(sg2))
    return _tables()["IDX_SGG"].get(key)


def geocode_sgg_codes(sido: str, sgg: str):
    """시군구 → 1개 이상 코드 목록. 'OO시'(구 보유) 초기연도 보고는 자식 구 전체로 확장."""
    c = geocode_sgg(sido, sgg)
    if c:
        return [c]
    s = canon_sido(sido)
    kids = _tables()["SI_CHILDREN"].get((geocode_sido(sido), norm(sgg)))
    return list(kids) if kids else []


# ---- 읍면동 단순 개명(1:1, 경계 동일) — 데이터엔 코드가 없어 이름으로 매칭. 행안부 행정구역 개편 근거 ----
# (시도, 옛 동명) → 2024 동명. 전 연도 1:1 미매칭 후보에서 실제 개명만 검증 채택(오탐 제외).
_EMD_RENAME_RAW = [
    ("경상북도", "금수면", "금수강산면"),    # 성주 2016
    ("경상북도", "양북면", "문무대왕면"),    # 경주 2021
    ("경상북도", "부동면", "주왕산면"),      # 청송 2016
    ("경상북도", "사벌면", "사벌국면"),      # 상주 2018
    ("경상북도", "고령읍", "대가야읍"),      # 고령 2015
    ("경기도", "능서면", "세종대왕면"),      # 여주 2021
    ("경기도", "석수3동", "충훈동"),         # 안양 만안 2018
    ("경기도", "하면", "조종면"),            # 가평 2015
    ("강원도", "중동면", "산솔면"),          # 영월 2021
    ("강원도", "수주면", "무릉도원면"),      # 영월 2016
    ("서울특별시", "일원2동", "개포3동"),    # 강남 2016(일원2동→개포3동)
    ("서울특별시", "면목제3.8동", "면목3·8동"),  # 중랑(표기차)
    ("서울특별시", "금호2-3가동", "금호2·3가동"),  # 성동(표기차)
]
EMD_RENAME = {(norm(canon_sido(sd)), norm(old)): new for sd, old, new in _EMD_RENAME_RAW}


def geocode_emd(sido: str, sgg: str, dong: str):
    T = _tables()
    IDX_EMD, IDX_EMD_LOOSE = T["IDX_EMD"], T["IDX_EMD_LOOSE"]
    s = canon_sido(sido)
    s = SGG_SIDO_MOVE.get((sido, (sgg or "").strip()), s)
    ns = norm(s); nsgg = norm(sgg)
    # 1순위: 원본 동명 그대로(정확 일치) — 변형보다 항상 우선(분동 유지 지역 오매칭 방지)
    norig = norm(dong)
    if (ns, nsgg, norig) in IDX_EMD:
        return IDX_EMD[(ns, nsgg, norig)]
    if (ns, norig) in IDX_EMD_LOOSE:
        return IDX_EMD_LOOSE[(ns, norig)]
    # 1.5순위: 검증된 단순 개명(1:1). 옛 이름 → 2024 이름으로 정확 매칭.
    ren = EMD_RENAME.get((ns, norig))
    if ren:
        rn = norm(ren)
        if (ns, nsgg, rn) in IDX_EMD:
            return IDX_EMD[(ns, nsgg, rn)]
        if (ns, rn) in IDX_EMD_LOOSE:
            return IDX_EMD_LOOSE[(ns, rn)]
    # 2순위: 구조적 변형(구-접두 제거/출장소 부모/숫자접미 통합 등). 2024에 실제 있을 때만 매칭.
    bases = [dong]
    toks = (sgg or "").split()
    gu = toks[-1] if len(toks) > 1 and toks[-1].endswith("구") else None
    if gu and dong.startswith(gu) and dong != gu:        # (a) sgg 구토큰 글루 '장안구송죽동'
        bases.append(dong[len(gu):])
    m = re.match(r"^(.+?구)(.+(?:동|읍|면))$", dong)        # (b) 임의 '구' 접두(부모시 보고 '덕양구고양동')
    if m:
        bases.append(m.group(2))
    if "출장소" in dong:                                   # (c) 출장소→부모 읍/면/동 합산
        pm = re.match(r"^(.*?[읍면동])", dong)
        if pm and pm.group(1) != dong:
            bases.append(pm.group(1))
    cands = []
    for b in bases:
        for d in dong_variants(b):
            if d not in cands:
                cands.append(d)
    for d in cands:                                       # 변형: strict 먼저
        if (ns, nsgg, norm(d)) in IDX_EMD:
            return IDX_EMD[(ns, nsgg, norm(d))]
    for d in cands:                                       # 변형: loose(시군구 무시)
        if (ns, norm(d)) in IDX_EMD_LOOSE:
            return IDX_EMD_LOOSE[(ns, norm(d))]
    return None


if __name__ == "__main__":
    T = _tables()["TABLES"]
    print(f"시도 {len(T['sido'])}, 시군구 {len(T['sigungu'])}, 읍면동 {len(T['emd'])}")
    print("저장:", OUT)
