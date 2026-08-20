# -*- coding: utf-8 -*-
"""연도별 행정구역 코드 층 — 이름 대신 그 해 정부 코드로 붙이기 위한 모듈.

공개 테이블은 지금까지 한글 지명으로만 이어져 있었다. 지명은 안 변한다는 보장이
없다. 인천 남구는 2018년 미추홀구가 됐고, 군위군은 2023년 경북에서 대구로 옮겼고,
창원·마산·진해는 2010년에 합쳤고, 청원군은 2014년 청주시로 들어갔고, 큰 시의
일반구는 판마다 '고양시 덕양구' / '고양시' + '덕양구고양동' / '마산합포구'처럼 다르게
적힌다. 그때마다 join이 조용히 어긋난다. 그래서 이름을 고치는 규칙을 하나 더 만드는
대신, 그 해 정부가 쓰던 코드로 옮겨 붙인다.

권위 자료는 행정안전부 행정표준코드관리시스템의 법정동코드 전체자료다
(01_raw_data/행정표준코드/, 그 폴더 README에 URL과 받은 날짜). 10자리 법정동코드는
SS-GGG-EEE-RR 구조라 앞 2자리가 시도, 앞 5자리가 시군구(일반구 포함)다. 이 두
자리수는 행정동코드 체계와 같은 값을 쓰므로 시도·시군구 층에서는 두 체계가 갈리지
않는다. 읍면동 층은 05_dashboard/data/emd_years/ 의 연도별 경계 스냅샷이 그 해
코드를 이미 갖고 있어 그쪽을 그대로 쓴다.

기준 시점은 각 연도의 12월 31일이다. 자료가 그 해 말 기준으로 발행되고, 한 해
안에 일어난 개편(2014-07-01 청주·청원 통합, 2023-07-01 군위군 대구 편입)을 그 해
자료가 이미 반영하기 때문이다.

  sido_code(year, sido)                       2자리 코드, 못 풀면 None
  sigungu_code(year, sido, sigungu)           5자리 코드, 못 풀면 None
  eupmyeondong_sigungu_code(y, sd, sg, dong)  읍면동 행의 5자리 코드
  emd_boundary(year, sido, sigungu, dong)     그 해 경계의 (시도, 시군구명, 읍면동코드)
  year_table()                                연도별 코드표, JSON으로도 저장

이름 정규화는 mois_geocode.py 규칙(norm, canon_sido)을 가져다 쓴다. 두 벌을 만들지
않는다. 못 푼 이름은 코드를 지어내지 않고 빈칸으로 두고 unresolved()에 쌓는다.
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import zipfile
from collections import defaultdict

import pandas as pd

from kird import CLEAN, RAW, SITE_DATA
from mois_geocode import canon_sido, norm

REG_DIR = os.path.join(RAW, "행정표준코드")
CACHE = os.path.join(CLEAN, "admin_code_register.csv")
YEAR_TABLE = os.path.join(SITE_DATA, "admin_codes_by_year.json")

FIRST_YEAR, LAST_YEAR = 2006, 2025

# ---- 시도 계보 -------------------------------------------------------------
# 같은 시도가 코드를 갈아탄 경우만 묶는다. 이름이 달라도 한 줄에 있으면 한 시도다.
# 2026-07-01 전남광주통합특별시(12)는 광주(29)와 전남(46)을 흡수하지만, 이 자료는
# 2025년에서 끝나므로 계보에 넣지 않았다. 2026년 이후로 늘릴 때 넣어야 한다.
SIDO_LINEAGE = [
    ("21", "26"),   # 부산직할시 -> 부산광역시 (1995-01-01)
    ("22", "27"),   # 대구직할시 -> 대구광역시 (1995-01-01)
    ("23", "28"),   # 인천직할시 -> 인천광역시 (1995-01-01)
    ("24", "29"),   # 광주직할시 -> 광주광역시 (1995-01-01)
    ("25", "30"),   # 대전직할시 -> 대전광역시 (1995-01-01)
    ("42", "51"),   # 강원도 -> 강원특별자치도 (2023-06-11)
    ("45", "52"),   # 전라북도 -> 전북특별자치도 (2024-01-18)
    ("49", "50"),   # 제주도 -> 제주특별자치도 (2006-07-01)
]

# ---- 시군구 계보 -----------------------------------------------------------
# 이름이나 상위 시도가 바뀌어 코드가 갈린 승계 관계. 파이프라인이 이미 선언해 둔 것과
# 같은 목록이다(08_export_dataset.py _RENAMES, 06_build_summaries.py RECOVER,
# mois_geocode.py SGG_RENAME / SGG_SIDO_MOVE). 여기서는 양방향으로 쓴다. 옛 이름이
# 뒤 연도에 남아 있으면 후계 코드로, 현행 이름이 앞 연도에 쓰이면 그 해 전신 코드로
# 풀린다. 공개본이 전 기간 현행 이름으로 라벨을 통일해 두었기 때문에 뒤쪽이 특히
# 필요하다(2014년 행이 '미추홀구'라고 적혀 있어도 그 해 코드는 남구 28170이다).
SGG_LINEAGE = [
    (("인천광역시", "남구"), ("인천광역시", "미추홀구")),          # 2018-07-01 개명
    (("경상북도", "군위군"), ("대구광역시", "군위군")),            # 2023-07-01 대구 편입
    (("충청북도", "청원군"), ("충청북도", "청주시 청원구")),        # 2014-07-01 청주 통합
    (("경상남도", "진해시"), ("경상남도", "창원시 진해구")),        # 2010-07-01 창원 통합
    (("충청남도", "당진군"), ("충청남도", "당진시")),              # 2012-01-01 시 승격
    (("경기도", "여주군"), ("경기도", "여주시")),                  # 2013-09-23 시 승격
    (("경기도", "포천군"), ("경기도", "포천시")),                  # 2003-10-19 시 승격
    (("충청남도", "연기군"), ("세종특별자치시", "세종특별자치시")),   # 2012-07-01 세종 출범
]

# 자료가 시군구 자리에 쓰는 별칭. 어느 칸을 가리키는 말인가만 옮긴다.
# 세종은 단층제라 법정동코드에 시군구 행 하나(3611000000)뿐이고 그 이름이 곧 시도명이다.
SGG_NAME_ALIAS = {
    ("세종특별자치시", "세종시"): "세종특별자치시",
    ("세종특별자치시", "총계"): "세종특별자치시",
    ("세종특별자치시", "0"): "세종특별자치시",
}

# 공개본이 하나의 시군구로 유지하는 일반구. 부천시 일반구는 2016-07-01 폐지되고
# 2024-01-01 다시 생겼는데, 공개본은 패널을 끊지 않으려고 전 기간 '부천시' 한 칸으로
# 낸다(08_export_dataset.py _BUCHEON_GU). 그래서 그 밑 읍면동도 부천시 코드를 단다.
# 부천시 코드는 그 해에도 실재하는 코드이므로 지어낸 값이 아니라 한 단계 위 코드다.
_RELEASE_PARENT_RAW = {
    ("경기도", "부천시 원미구"): "부천시",
    ("경기도", "부천시 소사구"): "부천시",
    ("경기도", "부천시 오정구"): "부천시",
    ("경기도", "원미구"): "부천시",
    ("경기도", "소사구"): "부천시",
    ("경기도", "오정구"): "부천시",
}
# 띄어쓰기가 판마다 다르고 경계 파일은 '부천시소사구'처럼 붙여 쓰므로 정규화해 둔다
RELEASE_PARENT = dict(((norm(a), norm(b)), c) for (a, b), c in _RELEASE_PARENT_RAW.items())

_UNRESOLVED = defaultdict(int)


def unresolved():
    """못 푼 (층, 연도, 시도, 이름) 별 건수."""
    return dict(_UNRESOLVED)


def reset_unresolved():
    _UNRESOLVED.clear()


def _ref(year):
    return int(year) * 10000 + 1231


# ---- 원자료 읽기 -----------------------------------------------------------
def _latest_zip():
    zs = sorted(glob.glob(os.path.join(REG_DIR, "법정동코드_조회자료_*.zip")))
    if not zs:
        raise SystemExit("법정동코드 조회자료가 없다. python 02_code/fetch_admin_codes.py 로 "
                         "받아라 (기대 위치 %s)" % REG_DIR)
    return zs[-1]


def _parse_register():
    """법정동코드 조회자료 xlsx -> 시도·시군구 행만 남긴 납작한 표."""
    src = _latest_zip()
    with zipfile.ZipFile(src) as z:
        member = [n for n in z.namelist() if n.endswith(".xlsx")][0]
        raw = pd.read_excel(io.BytesIO(z.read(member)), dtype=str)
    raw = raw.rename(columns=lambda c: str(c).strip())

    def d(x):
        s = "" if pd.isna(x) else str(x).strip()
        return int(s[:8]) if re.fullmatch(r"\d{8}", s[:8]) else None

    rows = []
    cols = ["법정동코드", "법정동명", "폐지구분", "생성일", "폐지일"]
    for code, name, flag, crt, cls in raw[cols].itertuples(index=False):
        code = str(code).strip()
        if len(code) != 10 or not code.isdigit():
            continue
        if code.endswith("00000000"):
            level = "sido"
        elif code.endswith("00000"):
            level = "sgg"
        else:
            continue
        start, end = d(crt), d(cls)
        # 등록기가 코드를 닫은 날을 생성일 칸에도 적어 둔 레코드(생성일 == 폐지일)가
        # 157건 있다. 그 생성일은 실제 설치일이 아니므로 모름으로 둔다.
        if start is not None and start == end:
            start = None
        rows.append((code, str(name).strip(), level,
                     str(flag).strip() == "현존", start, end))
    df = pd.DataFrame(rows, columns=["code", "name", "level", "alive", "start", "end"])
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_csv(CACHE, index=False, encoding="utf-8-sig")
    print("  법정동코드 %s -> 시도 %d, 시군구 %d (캐시 %s)"
          % (os.path.basename(src), int((df.level == "sido").sum()),
             int((df.level == "sgg").sum()), os.path.basename(CACHE)))
    return df


def _register():
    src = _latest_zip()
    if os.path.exists(CACHE) and os.path.getmtime(CACHE) >= os.path.getmtime(src):
        return pd.read_csv(CACHE, encoding="utf-8-sig",
                           dtype={"code": str, "name": str, "level": str})
    return _parse_register()


# ---- 인덱스 ---------------------------------------------------------------
class _Rec(object):
    __slots__ = ("code", "name", "start", "end", "alive")

    def __init__(self, code, name, start, end, alive):
        self.code, self.name, self.alive = code, name, bool(alive)
        self.start = None if pd.isna(start) else int(start)
        self.end = None if pd.isna(end) else int(end)

    def live_at(self, ref, ignore_start=False):
        if not ignore_start and self.start is not None and self.start > ref:
            return False
        if self.end is not None and self.end <= ref:
            return False
        return True

    def __repr__(self):
        return "<%s %s %s~%s>" % (self.code, self.name, self.start, self.end)


def _pick(cands, ref):
    """ref 시점에 있던 레코드 하나. 없으면 생성일을 풀어 한 번 더 본다.

    등록기가 옛 구역 다섯 건(부천시 세 일반구, 청원군, 전주시 덕진구)의 생성일을
    2013-04-02(일괄 적재일)로 적어 두어 실제 설치일보다 늦다. 엄격 판정이 비면
    생성일을 무시하고 폐지일만 보며, 그중 ref 직후에 닫힌 레코드를 고른다.

    두 번째 판정은 이미 폐지됐고 폐지일이 있는 레코드에만 적용한다. 현존 레코드의
    생성일은 뒤에서 덮어쓴 기록이 없어 믿을 수 있고, 풀어 주면 아직 생기지도 않은
    구역이 과거 연도에 되살아난다(2026-07-01 전남광주통합특별시, 인천 제물포구).
    """
    for ignore in (False, True):
        pool = cands if not ignore else [r for r in cands if not r.alive and r.end is not None]
        live = [r for r in pool if r.live_at(ref, ignore)]
        if len(live) == 1:
            return live[0]
        if live:
            return sorted(live, key=lambda r: (r.end if r.end is not None else 99999999,
                                               -(r.start or 0)))[0]
    return None


def _build():
    df = _register()
    grp_of = {}
    for grp in SIDO_LINEAGE:
        for c in grp:
            grp_of[c] = grp[0]

    def gid(c2):
        return grp_of.get(c2, c2)

    sido_recs = defaultdict(list)
    sido_name = {}
    for r in df[df.level == "sido"].itertuples(index=False):
        c2 = r.code[:2]
        sido_recs[c2].append(_Rec(c2, r.name, r.start, r.end, r.alive))
        if r.alive or c2 not in sido_name:
            sido_name[c2] = r.name

    sgg_raw = list(df[df.level == "sgg"].itertuples(index=False))
    # 8자리 0으로 끝나는 시도 행이 없는 시도(세종특별자치시)는 시군구 행에서 세운다.
    for r in sgg_raw:
        c2 = r.code[:2]
        if c2 not in sido_recs:
            head = r.name.split(" ")[0]
            sido_recs[c2].append(_Rec(c2, head, r.start, r.end, r.alive))
            sido_name[c2] = head

    sido_by_name = defaultdict(set)
    for c2, recs in sido_recs.items():
        for rc in recs:
            sido_by_name[norm(rc.name)].add(c2)

    lineage, recs_by_key, path_of = {}, defaultdict(list), {}

    def find(k):
        while lineage.get(k, k) != k:
            k = lineage[k]
        return k

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            lineage[rb] = ra

    for r in sgg_raw:
        c2 = r.code[:2]
        sname = sido_name.get(c2, "")
        full = r.name
        path = full[len(sname) + 1:] if sname and full.startswith(sname + " ") else full
        key = (gid(c2), norm(path))
        recs_by_key[key].append(_Rec(r.code[:5], full, r.start, r.end, r.alive))
        path_of.setdefault(key, path)
        lineage.setdefault(key, key)

    def key_of(sd, sg):
        c2s = sido_by_name.get(norm(sd)) or sido_by_name.get(norm(canon_sido(sd)))
        return (gid(sorted(c2s)[0]), norm(sg)) if c2s else None

    for a, b in SGG_LINEAGE:
        ka, kb = key_of(*a), key_of(*b)
        if ka in lineage and kb in lineage:
            union(ka, kb)

    fam = defaultdict(list)
    for k, rs in recs_by_key.items():
        fam[find(k)].extend(rs)
    # 폐지 표시인데 폐지일이 빈 레코드(경기도 여주군)는 같은 계보의 다음 생성일로 닫는다.
    for rs in fam.values():
        for rc in rs:
            if rc.end is None and not rc.alive:
                later = [s.start for s in rs if s.start is not None
                         and (rc.start is None or s.start > rc.start)]
                rc.end = min(later) if later else None

    key_fam = {k: fam[find(k)] for k in recs_by_key}

    # 부모 시 없이 적힌 일반구('마산합포구') -> 그 시도 안에서 유일한 전체 경로.
    # 시도 안에서만 찾으므로 광주 남구가 포항시 남구로 끌려가지 않는다.
    bare = defaultdict(set)
    for k, path in path_of.items():
        if " " in path:
            bare[(k[0], norm(path.split(" ")[-1]))].add(k)
    bare = dict((b, next(iter(v))) for b, v in bare.items()
                if len(v) == 1 and b not in recs_by_key)

    return {"sido_recs": sido_recs, "sido_name": sido_name, "sido_by_name": sido_by_name,
            "gid": gid, "key_fam": key_fam, "bare": bare, "path_of": path_of,
            "keys": set(recs_by_key)}


_IX = {}


def _ix():
    if not _IX:
        _IX.update(_build())
    return _IX


# ---- 공개 API --------------------------------------------------------------
def sido_code(year, sido):
    """그 해 12/31 기준 시도 2자리 코드. 못 풀면 None."""
    ix = _ix()
    c2s = ix["sido_by_name"].get(norm(sido)) or ix["sido_by_name"].get(norm(canon_sido(sido)))
    if not c2s:
        _UNRESOLVED[("sido", int(year), "", str(sido))] += 1
        return None
    g = ix["gid"](sorted(c2s)[0])
    cands = [rc for c2, recs in ix["sido_recs"].items() if ix["gid"](c2) == g for rc in recs]
    r = _pick(cands, _ref(year))
    if r is None:
        _UNRESOLVED[("sido", int(year), "", str(sido))] += 1
        return None
    return r.code


def _sgg_key(sido, sgg):
    ix = _ix()
    name = SGG_NAME_ALIAS.get((str(sido).strip(), str(sgg).strip())) or str(sgg).strip()
    c2s = ix["sido_by_name"].get(norm(sido)) or ix["sido_by_name"].get(norm(canon_sido(sido)))
    if not c2s:
        return None
    g = ix["gid"](sorted(c2s)[0])
    k = (g, norm(name))
    if k in ix["keys"]:
        return k
    return ix["bare"].get((g, norm(name)))


def sigungu_code(year, sido, sigungu, release_grain=True):
    """그 해 12/31 기준 시군구 5자리 코드. 못 풀면 None.

    release_grain=True면 공개본이 하나로 유지하는 일반구(부천시 원미·소사·오정구)를
    모시(부천시) 코드로 올린다. 공개본 시군구 표가 그 칸을 부천시로 내기 때문이다.
    """
    sd, sg = str(sido).strip(), str(sigungu).strip()
    if release_grain:
        sg = RELEASE_PARENT.get((norm(sd), norm(sg)), sg)
    k = _sgg_key(sd, sg)
    if k is None:
        _UNRESOLVED[("sigungu", int(year), sd, str(sigungu))] += 1
        return None
    r = _pick(_ix()["key_fam"][k], _ref(year))
    if r is None:
        _UNRESOLVED[("sigungu", int(year), sd, str(sigungu))] += 1
        return None
    return r.code


# ---- 읍면동: 그 해 경계 스냅샷 ---------------------------------------------
_EMD_CACHE = {}
_SEP2 = re.compile(r"[\s·.,・ㆍᆞ‧･]")


def _emdnorm(s):
    return re.sub(r"제(\d)", r"\1", _SEP2.sub("", s or ""))


def _emd_label(y):
    y = int(y)
    return "2014" if y <= 2014 else ("2024" if y >= 2024 else str(y))


_CITY_GU = re.compile(r"^(.+?시)(.+구)$")
_NUM_DONG = re.compile(r"\d+동$")
_BRANCH = re.compile(r"^(.*?[읍면동])")
EMD_YEARS = tuple(range(2014, 2025))


def _collapse(ndong):
    """분동 표기를 하나로: 광교1동/광교2동 -> 광교동. 원자료와 경계가 서로 다른 해의
    분동 상태를 적을 때, 그 동이 어느 일반구인지만 알면 되는 자리에서 쓴다."""
    return _NUM_DONG.sub("동", ndong)


def _emd_index(year):
    lab = _emd_label(year)
    if lab in _EMD_CACHE:
        return _EMD_CACHE[lab]
    path = (os.path.join(SITE_DATA, "korea_emd.json") if lab == "2024"
            else os.path.join(SITE_DATA, "emd_years", "korea_emd_%s.json" % lab))
    ix = {"strict": {}, "part": {}, "loose": {},
          "strict_c": {}, "part_c": {}, "loose_c": {}}
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    for ft in g["features"]:
        p = ft["properties"]
        v = (p["sido"], p["sg"], p.get("code", ""))
        sg, dong = _emdnorm(p["sg"]), _emdnorm(p["dong"])
        c = _collapse(dong)
        ix["strict"][(p["sido"], sg, dong)] = v
        ix["strict_c"].setdefault((p["sido"], sg, c), v)
        # '고양시덕양구'는 모시('고양시')로도, 구('덕양구')로도 찾을 수 있게 둔다.
        # 자료가 판마다 둘 중 하나만 적기 때문이다(2014년은 시만, 2024년은 구만).
        m = _CITY_GU.match(p["sg"])
        halves = [_emdnorm(m.group(1)), _emdnorm(m.group(2))] if m else []
        for h in halves:
            ix["part"].setdefault((p["sido"], h, dong), v)
            ix["part_c"].setdefault((p["sido"], h, c), v)
        ix["loose"].setdefault((p["sido"], dong), v)
        ix["loose_c"].setdefault((p["sido"], c), v)
    _EMD_CACHE[lab] = ix
    return ix


def _look(ix, sido, sg, dongs):
    """한 해 인덱스 안에서 정확 -> 반쪽 -> 시도 순으로, 이름 후보를 차례로 맞춰 본다."""
    for keyset in ("strict", "part", "loose", "strict_c", "part_c", "loose_c"):
        collapsed = keyset.endswith("_c")
        for d in dongs:
            d2 = _collapse(d) if collapsed else d
            k = (sido, d2) if keyset.startswith("loose") else (sido, sg, d2)
            hit = ix[keyset].get(k)
            if hit:
                return hit
    return None


def _dong_candidates(dong):
    d = _emdnorm(dong)
    out = [d]
    if "출장소" in d:                       # 죽장면상옥출장소 -> 죽장면
        m = _BRANCH.match(d)
        if m and m.group(1) != d:
            out.append(m.group(1))
    return out


def emd_boundary(year, sido, sigungu, dong):
    """그 해 경계 스냅샷의 (시도, 그 해 시군구명, 그 해 읍면동 코드). 못 찾으면 None.

    시군구명이 그 해 경계와 그대로 맞으면 거기서 끝이고, 아니면 모시나 구 한쪽만
    적힌 경우로 보고 반쪽 이름으로 맞춰 보고, 그래도 없으면 시도 안에서 동 이름만으로
    찾는다. 반쪽 단계가 있어서 원자료가 '고양시'라고만 적은 2014년과 '마산합포구'라고만
    적은 2024년이 같은 동을 서로 다른 시군구로 끌고 가지 않는다.
    """
    return _look(_emd_index(year), sido, _emdnorm(sigungu), _dong_candidates(dong))


def boundary_sigungu_name(year, sido, sigungu, dong):
    """그 동이 그 해 어느 시군구에 있었는지, 이름으로. 못 찾으면 None.

    그 해 스냅샷에 없는 동이 있다. 2014년 수원 광교동은 2015년부터 광교1·2동으로
    나뉜 뒤에야 경계에 나타나고, 천안 부성1·2동과 불당동도 마찬가지다. 그런 동은
    가까운 해 스냅샷에서 찾는다. 일반구 소속은 그 사이에 바뀌지 않으므로 이름만
    가져오고 코드는 쓰지 않는다(코드는 늘 그 행의 연도로 다시 푼다).
    """
    b = emd_boundary(year, sido, sigungu, dong)
    if b:
        return b[0], b[1]
    y = int(year)
    for other in sorted(EMD_YEARS, key=lambda o: (abs(o - y), o)):
        if other == y:
            continue
        b = _look(_emd_index(other), sido, _emdnorm(sigungu), _dong_candidates(dong))
        if b:
            return b[0], b[1]
    return None


def eupmyeondong_sigungu_code(year, sido, sigungu, dong):
    """읍면동 행의 시군구 코드. 그 해 경계가 말하는 일반구를 먼저 쓴다."""
    b = boundary_sigungu_name(year, sido, sigungu, dong)
    if b:
        c = sigungu_code(year, b[0], b[1])
        if c:
            return c
    return sigungu_code(year, sido, sigungu)


# ---- 공개 테이블에 코드 열 붙이기 ------------------------------------------
def add_code_columns(df, verbose_name=""):
    """sido_code / sigungu_code 를 sido_en / sigungu_en 옆에 끼운 새 DataFrame.

    이미 있으면 지우고 다시 계산한다(같은 입력이면 같은 결과라 몇 번 돌려도 같다).
    eupmyeondong 열이 있는 표는 그 해 경계가 말하는 일반구를 먼저 써서 시군구 코드를
    정한다. 원자료가 '고양시'처럼 모시로만 적은 해에도 동이 속한 구를 되찾기 위해서다.
    값은 문자열이고, 못 푼 자리는 빈칸으로 둔다(코드를 지어내지 않는다).
    """
    if "year" not in df.columns:
        return df
    df = df.drop(columns=[c for c in ("sido_code", "sigungu_code") if c in df.columns])
    if "sido" not in df.columns:
        return df

    years = df["year"].astype(str).str.slice(0, 4)
    sido = df["sido"].fillna("").astype(str)

    if "sigungu" in df.columns:
        sgg = df["sigungu"].fillna("").astype(str)
        if "eupmyeondong" in df.columns:
            dong = df["eupmyeondong"].fillna("").astype(str)
            keys = list(zip(years, sido, sgg, dong))
            cache = {}
            for k in set(keys):
                cache[k] = ("" if not k[1] or not k[2]
                            else (eupmyeondong_sigungu_code(*k) or ""))
        else:
            keys = list(zip(years, sido, sgg))
            cache = {}
            for k in set(keys):
                cache[k] = "" if not k[1] or not k[2] else (sigungu_code(*k) or "")
        sgg_vals = [cache[k] for k in keys]
    else:
        sgg_vals = None

    sd_keys = list(zip(years, sido))
    sd_cache = {}
    for k in set(sd_keys):
        sd_cache[k] = "" if not k[1] else (sido_code(*k) or "")
    sd_vals = [sd_cache[k] for k in sd_keys]
    if sgg_vals is not None:
        # 그 해 없던 시도 이름(2011년 세종특별자치시)은 시군구 코드 앞 2자리로 잇는다
        sd_vals = [a or (b[:2] if b else "") for a, b in zip(sd_vals, sgg_vals)]

    cols = list(df.columns)
    df = df.assign(sido_code=sd_vals)
    cols.insert(cols.index("sido_en") + 1 if "sido_en" in cols else cols.index("sido") + 1,
                "sido_code")
    if sgg_vals is not None:
        df = df.assign(sigungu_code=sgg_vals)
        cols.insert(cols.index("sigungu_en") + 1 if "sigungu_en" in cols
                    else cols.index("sigungu") + 1, "sigungu_code")
    if verbose_name:
        n = sum(1 for v in (sgg_vals or []) if not v)
        print("  %-38s sido_code + sigungu_code (빈 시군구코드 %d)" % (verbose_name, n))
    return df[cols]


# ---- 연도별 코드표 ---------------------------------------------------------
def year_table(first=FIRST_YEAR, last=LAST_YEAR, save=True):
    """{연도: {'sido': {코드: 이름}, 'sigungu': {코드: [시도코드, 전체이름]}}}"""
    ix = _ix()
    out = {}
    for y in range(int(first), int(last) + 1):
        ref = _ref(y)
        sd = {}
        for c2, recs in ix["sido_recs"].items():
            r = _pick(recs, ref)
            if r is not None and r.code == c2:
                sd[c2] = r.name
        sg, seen = {}, set()
        for k, famrecs in ix["key_fam"].items():
            if id(famrecs) in seen:
                continue
            seen.add(id(famrecs))
            r = _pick(famrecs, ref)
            if r is not None:
                sg[r.code] = [r.code[:2], r.name]
        out[str(y)] = {"sido": dict(sorted(sd.items())),
                       "sigungu": dict(sorted(sg.items()))}
    if save:
        os.makedirs(os.path.dirname(YEAR_TABLE), exist_ok=True)
        with open(YEAR_TABLE, "w", encoding="utf-8") as f:
            json.dump({"source": "행정안전부 행정표준코드관리시스템 법정동코드 전체자료",
                       "source_url": "https://www.code.go.kr/stdcode/regCodeL.do",
                       "reference_instant": "12-31 of each year",
                       "years": out}, f, ensure_ascii=False, separators=(",", ":"))
        print("  wrote %s" % YEAR_TABLE)
    return out


SPOT_CHECKS = [
    (2017, "인천광역시", "미추홀구"), (2017, "인천광역시", "남구"),
    (2019, "인천광역시", "미추홀구"),
    (2022, "대구광역시", "군위군"), (2022, "경상북도", "군위군"),
    (2023, "대구광역시", "군위군"),
    (2015, "경상남도", "창원시 마산합포구"), (2015, "경상남도", "마산합포구"),
]


if __name__ == "__main__":
    t = year_table()
    for y in ("2006", "2015", "2023", "2025"):
        print("  %s: 시도 %d, 시군구 %d" % (y, len(t[y]["sido"]), len(t[y]["sigungu"])))
    print("\n손검증:")
    for y, sd, sg in SPOT_CHECKS:
        print("  %d %s %-16s sido=%s sigungu=%s"
              % (y, sd, sg, sido_code(y, sd), sigungu_code(y, sd, sg)))
    if unresolved():
        print("\n못 푼 이름:", unresolved())
