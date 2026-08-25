"""Everything that extends the parsed base before reconciliation.

The parser writes one year per yearbook on that yearbook's own terms. This step
turns that into the panel: local Moran clusters onto every district-year, the
province series back to 2006 with its diversity columns, the national series
(undocumented residents, national language demand), one label per country with
the language series recomputed on the merged names, the district-by-visa panel,
refugee language demand, and the 2008-2013 district and age backfills out of the
pre-2014 table family.

Section order is execution order and it matters: the spatial clusters must come
before the backfills, whose new records carry no cluster of their own, and the
name merge must follow the first national-language build, which is why the series
is computed twice.
"""
from collections import Counter
import glob
import json
import math
import os
import re
import subprocess
import sys
import warnings

import pandas as pd

from kird import COUNTRY_LANGUAGE
from kird import COUNTRY_REGION
from kird import LAST_YEAR
from kird import ROOT


warnings.filterwarnings("ignore")
import geopandas as gpd
import numpy as np

from kird import ROOT

GEO = os.path.join(ROOT, "05_dashboard", "data", "korea_sigungu.json")
ADJ = os.path.join(ROOT, "03_cleaned_data", "adjacency.json")
IDX = os.path.join(ROOT, "05_dashboard", "data", "indices.json")

LAB = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}


def build_adjacency():
    """Queen contiguity: districts that touch, keyed by match_key.

    Keys are written WITHOUT spaces, because both consumers look them up that
    way: add_lisa's key() and 04_reconcile's share_by_key strip spaces from the
    sigungu. The 2026-08-24 rebuild wrote match_key verbatim, which silently
    dropped the 32 space-bearing districts (every city with 일반구 -- 안산시
    단원구, 수원시 장안구, ...) from LISA and from Moran's I: their lisa went
    blank and the I series moved, and nothing failed. The v1.1.0 adjacency had
    stripped keys, which is why the published values were right."""
    g = gpd.read_file(GEO)
    keys = [str(k).replace(" ", "") for k in g["match_key"].tolist()]
    geoms = g.geometry.tolist()
    sindex = g.sindex

    adj = {k: [] for k in keys}
    for i, geom in enumerate(geoms):
        # bounding-box candidates from the spatial index, then a boundary test
        for j in sindex.query(geom):
            if j == i:
                continue
            if geom.touches(geoms[j]) or (geom.intersects(geoms[j]) and not geom.equals(geoms[j])):
                adj[keys[i]].append(keys[j])
    for k in adj:
        adj[k] = sorted(set(adj[k]))

    json.dump(adj, open(ADJ, "w", encoding="utf-8"), ensure_ascii=False)
    n_edges = sum(len(v) for v in adj.values()) // 2
    print(f"adjacency.json: {len(adj)} districts, ~{n_edges} edges, "
          f"mean degree {sum(len(v) for v in adj.values()) / len(adj):.1f}")
    return adj


def key(r):
    return r["sido"] + "|" + r["sigungu"].replace(" ", "")


def add_lisa(adj):
    """더 이상 분류하지 않는다. 04 의 relisa 가 유일한 계산 자리다.

    국지 Moran 은 시군구를 확정한 뒤에 계산해야 한다(부천 일반구, 세종). 04 가
    그 자리에서 다시 계산해 이 파일을 덮어쓰므로, 여기서 한 번 더 계산하면 같은
    지표가 두 곳에서 나오고 둘이 갈린다. 실제로 FDR 열을 여기에만 넣었을 때
    `lisa` 와 `lisa_fdr` 이 서로 다른 단위 집합을 가리켰다.

    인접 정보(adjacency.json)는 build_adjacency 가 이미 남겼고 04 가 그것을
    읽는다. 이 함수는 그 사실을 적어 두려고 남긴다."""
    print("lisa: 분류는 04_reconcile_districts.relisa 가 한다 (한 곳에서만)")



def parse_sido_2006_2013():
    """Extend by_sido to 2006-2013 from the pre-2014 province-by-nationality yearbook
    tables, so the province-level views (Overview year-snapshot region; map sido mode)
    reach back to 2006. Subnational sigungu data does not exist before 2014, so this
    adds province (시도) granularity only.

    Merges into site/data/indices.json (by_sido) and site/data/region.json (by_sido).
    """
    warnings.filterwarnings("ignore")

    from kird import COUNTRY_CANONICAL, COUNTRY_REGION
    from kird import ROOT  # noqa: E402
    HERE = os.path.dirname(os.path.abspath(__file__))
    RAW = os.path.join(ROOT, "01_raw_data")                      # source yearbook + population folders
    POP = os.path.join(RAW, "주민등록인구 현황")


    # canonical sido names (17, from 2014 indices)
    idx_doc = json.load(open(os.path.join(ROOT, "05_dashboard", "data", "indices.json"), encoding="utf-8"))
    CANON = sorted({r["sido"] for r in idx_doc["data"]["by_sido"]["2014"]})

    SHORT = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
             "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
             "경기": "경기도", "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
             "전북": "전라북도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도"}
    def norm_sido(name):
        n = str(name).split("\n")[0].strip()
        if len(n) < 2:
            # single characters cause false substring hits (e.g., 남 would match 경상남도)
            return None
        n = n.replace("강원특별자치도", "강원도").replace("전북특별자치도", "전라북도")
        if n in CANON: return n
        if n in SHORT: return SHORT[n]
        for s in CANON:
            if n in s or s.startswith(n): return s
        return None

    def num(x):
        s = str(x).split("\n")[0].replace(",", "").strip()
        try: return int(float(s))
        except: return 0

    # ---------- population per sido, 2006-2013 ----------
    def pop_sido():
        out = {}  # {year: {sido: pop}}
        # KOSIS 2006-2007
        k = pd.read_excel(os.path.join(POP, "2006-2007 시도 인구수 KOSIS.xlsx"), header=None)
        for _, r in k.iterrows():
            sd = norm_sido(r.iloc[0])
            if sd and sd != norm_sido("전국"):
                out.setdefault("2006", {})[sd] = num(r.iloc[1])
                out.setdefault("2007", {})[sd] = num(r.iloc[4])
        # MOIS 2008-2015 file → 2008-2013
        m = pd.read_excel(os.path.join(POP, "200812_201512.xlsx"), header=None)
        yr_cols = {}
        for c in range(2, m.shape[1]):
            v = str(m.iloc[1, c])
            if "년" in v: yr_cols[int(v.replace("년", ""))] = c
        for _, r in m.iterrows():
            code = str(r.iloc[0]).strip()
            if code.isdigit() and len(code) == 10 and code.endswith("00000000"):
                sd = norm_sido(r.iloc[1])
                if not sd: continue
                for y, c in yr_cols.items():
                    if 2008 <= y <= 2013:
                        out.setdefault(str(y), {})[sd] = num(r.iloc[c])
        return out

    # ---------- foreign by sido × nationality ----------
    FILES = {
        2006: "2006년_통계연보/1장/Ⅴ/../../../2006년_통계연보",  # placeholder; resolved below
    }

    def find_file(year):
        import glob
        pats = {
            2006: ["2006*/**/*국적및지역별*.xls*"], 2007: ["2007*/**/*국적및지역별*.xls*", "2007*/*국적및지역별*.xls*"],
            2008: ["*2008*/**/*지역및국적별*.xls*", "통계연보2008/**/*지역및국적별*.xls*"],
            2009: ["2009*/**/*지역및국적별*.xls*"], 2010: ["2010*/**/*지역및국적별*.xls*"],
            2011: ["2011*/**/*지역및국적별*.xls*"], 2012: ["2012*/**/*지역및국적별*.xls*"], 2013: ["2013*/**/*지역및국적별*.xls*"],
        }
        for p in pats.get(year, []):
            g = glob.glob(os.path.join(RAW, "출입국통계연보", p), recursive=True)
            if g: return g[0]
        return None

    def header_info(df):
        """Find (header_row, region_col, total_col, {nat_col: name})."""
        for hr in range(min(8, df.shape[0])):
            rowvals = [str(x).split("\n")[0].strip().replace(" ", "") for x in df.iloc[hr].tolist()]
            for tc, v in enumerate(rowvals):
                if v in ("총계", "합계"):
                    nats = {}
                    for c in range(tc + 1, df.shape[1]):
                        nm = str(df.iloc[hr, c]).split("\n")[0].strip()
                        # the 2009 sheet pads Korean headers to a fixed width
                        # ("중      국"); strip the internal spaces so the labels join
                        # with the neighbouring years and hit the country maps
                        nm = re.sub(r"\s+", "", nm)
                        if nm and nm not in ("nan", "총계", "합계", "기타", "Others", "기타(Others)", "구분") and re.search(r"[가-힣]", nm):
                            nats[c] = COUNTRY_CANONICAL.get(nm, nm)
                    # region col: the col (<tc) with the MOST distinct sido matches below
                    best_c, best_n = 0, 0
                    for c in range(0, max(tc, 1)):
                        sample = {norm_sido(df.iloc[rr, c]) for rr in range(hr + 1, min(hr + 40, df.shape[0]))}
                        n = len(sample - {None})
                        if n > best_n: best_n, best_c = n, c
                    return hr, best_c, tc, nats
        return None

    def parse_year(path, summode=False):
        """Return {sido: {'_total': grand_total, nationality: count}} (sido-level).

        Default: the sido name sits on its own total row (소계/계). summode: no sido
        total row — sum the per-sigungu 계(T) rows within each sido block (2010-2011).
        """
        df = pd.read_excel(path, header=None)
        info = header_info(df)
        if not info: return {}
        hr, rc, tc, nats = info
        out = {}
        if not summode:
            for rr in range(hr + 1, df.shape[0]):
                sd = norm_sido(df.iloc[rr, rc])
                if not sd or sd in out: continue
                tval = num(df.iloc[rr, tc])
                if tval > 0:
                    rec = {"_total": tval}
                    for c, nm in nats.items():
                        v = num(df.iloc[rr, c])
                        if v > 0: rec[nm] = rec.get(nm, 0) + v
                    out[sd] = rec
            return out
        # sum mode
        cur = None
        for rr in range(hr + 1, df.shape[0]):
            sd = norm_sido(df.iloc[rr, rc])
            if sd: cur = sd
            if not cur: continue
            # Decide on whole-cell sex markers only. Substring matching over the joined
            # row used to drop every sigungu whose NAME contains 남/여 (성남시, 남동구,
            # 강남구, 여수시, ...), undercounting the 2010-2011 sido sums by ~7%.
            marks = [str(df.iloc[rr, c]).split("\n")[0].strip() for c in range(rc + 1, tc)]
            has_T = any(v == "계" or "(T)" in v for v in marks)
            has_MF = any(v in ("남", "여") or "(M)" in v or "(F)" in v for v in marks)
            if not has_T or has_MF: continue
            tval = num(df.iloc[rr, tc])
            if tval <= 0: continue
            rec = out.setdefault(cur, {"_total": 0})
            rec["_total"] += tval
            for c, nm in nats.items():
                v = num(df.iloc[rr, c])
                if v > 0: rec[nm] = rec.get(nm, 0) + v
        return out

    # ---------- compute by_sido record + merge ----------
    def shannon(counts):
        tot = sum(counts.values())
        if tot <= 0: return 0.0
        h = 0.0
        for v in counts.values():
            if v > 0:
                p = v / tot; h -= p * math.log(p)
        return round(h, 3)

    def continent(counts, pop):
        # continent_H over t_i with Korean in East Asia; shares foreign-only
        reg = {}
        for nm, v in counts.items():
            reg[COUNTRY_REGION.get(nm, "기타")] = reg.get(COUNTRY_REGION.get(nm, "기타"), 0) + v
        ftot = sum(counts.values())
        shares = {k: round(100 * v / ftot, 3) for k, v in sorted(reg.items(), key=lambda x: -x[1])} if ftot else {}
        # continent_H including Korean in East Asia
        full = dict(reg); kor = max(pop, 0)
        full["동아시아"] = full.get("동아시아", 0) + kor
        denom = sum(full.values()); cH = 0.0
        for v in full.values():
            if v > 0:
                p = v / denom; cH -= p * math.log(p)
        return round(cH, 4), shares

    POPS = pop_sido()
    data = idx_doc["data"]
    region_doc = json.load(open(os.path.join(ROOT, "05_dashboard", "data", "region.json"), encoding="utf-8"))
    reg_all = json.load(open(os.path.join(ROOT, "05_dashboard", "data", "data.json"), encoding="utf-8"))["populations"]["reg"]["data"]["ALL"]

    added = []
    for year in range(2006, 2014):
        f = find_file(year)
        if not f: print(year, "FILE NOT FOUND"); continue
        parsed = parse_year(f)
        knowntot0 = sum((reg_all.get(str(year)) or {}).values())
        nat0 = sum(v["_total"] for v in parsed.values()) if parsed else 0
        if knowntot0 and nat0 < 0.5 * knowntot0:  # no sido-total rows → sum sigungu
            alt = parse_year(f, summode=True)
            if sum(v["_total"] for v in alt.values()) > nat0:
                parsed = alt
        if not parsed: print(year, "PARSE EMPTY", os.path.basename(f)); continue
        recs = []
        sido_nat = {}
        for sd, rec0 in parsed.items():
            ftot = rec0.pop("_total")
            counts = rec0  # listed nationalities (subset; for diversity approximation)
            pop = (POPS.get(str(year), {}) or {}).get(sd)
            cH, shares = continent(counts, pop or ftot)
            rec = {"sido": sd, "foreign_total": ftot,
                   "total_pop": pop, "foreign_share_pct": round(100 * ftot / pop, 2) if pop else None,
                   "shannon_H": shannon(counts), "continent_H": cH, "continent_shares": shares,
                   "n_nationalities": len(counts)}
            recs.append(rec)
            sido_nat[sd] = counts
        natsum = sum(r["foreign_total"] for r in recs)
        knowntot = sum((reg_all.get(str(year)) or {}).values())
        ratio = natsum / knowntot if knowntot else 0
        print(f"{year}: {len(recs)} sido, sum_foreign={natsum:,}, reg_national={knowntot:,}, ratio={ratio:.3f}  [{os.path.basename(f)[:24]}]")
        if 0.9 <= ratio <= 1.1:  # validate before merging
            data["by_sido"][str(year)] = recs
            region_doc.setdefault("by_sido", {})[str(year)] = {sd: counts for sd, counts in sido_nat.items()}
            added.append(year)

    json.dump(idx_doc, open(os.path.join(ROOT, "05_dashboard", "data", "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(region_doc, open(os.path.join(ROOT, "05_dashboard", "data", "region.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("merged years:", added)



def add_sido_diversity():
    """Backfill HHI (nationality concentration) and shannon_H_inclusive
    (whole-population diversity, Korean included) onto the sido and national
    records in indices.json, so every diversity metric in the dashboard has
    area / province / national comparison lines (these two were previously
    stored only on by_sigungu records).

    Province values come from region.json by_sido nationality dicts + the sido
    total_pop already in indices. National values come from the registered-
    foreigner national nationality totals (data.json reg ALL) + national_total_pop.
    All registered-foreigner based, matching the subnational (sigungu) panel.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")


    idx_doc = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
    data = idx_doc["data"]
    region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))
    reg_all = json.load(open(os.path.join(SITE, "data.json"), encoding="utf-8"))["populations"]["reg"]["data"]["ALL"]


    def hhi(nat):
        t = sum(nat.values())
        if not t:
            return None
        return round(sum((v / t) ** 2 for v in nat.values()), 4)


    def incl(nat, pop):
        f = sum(nat.values())
        if not f or not pop:
            return None
        kor = max(pop, 0)          # 주민등록은 내국인 명부다. 빼지 않는다
        T = f + kor
        h = 0.0
        for v in list(nat.values()) + [kor]:
            if v > 0:
                p = v / T
                h -= p * math.log(p)
        return round(h, 3)


    # ---- province (by_sido) ----
    sido_n = 0
    for year, recs in data["by_sido"].items():
        sido_nat = region.get("by_sido", {}).get(year, {})
        for rec in recs:
            nat = sido_nat.get(rec["sido"])
            if not nat:
                continue
            rec["HHI"] = hhi(nat)
            rec["shannon_H_inclusive"] = incl(nat, rec.get("total_pop"))
            sido_n += 1

    # ---- national (summary) ----
    nat_n = 0
    for year, s in data["summary"].items():
        nat = reg_all.get(year)
        if not nat:
            continue
        s["national_HHI"] = hhi(nat)
        s["national_shannon_H_inclusive"] = incl(nat, s.get("national_total_pop"))
        nat_n += 1


    # ---- Pielou evenness E = Shannon H / ln(richness) on every record + national ----
    def pielou(H, S):
        if H is None or not S or S < 2:
            return None
        return round(H / math.log(S), 3)


    ev = 0
    for level in ("by_sigungu", "by_sido"):
        for year, recs in data[level].items():
            for rec in recs:
                rec["evenness"] = pielou(rec.get("shannon_H"), rec.get("n_nationalities"))
                ev += 1
    for year, s in data["summary"].items():
        s["national_evenness"] = pielou(s.get("national_shannon_H"), s.get("n_nationalities"))

    # ---- continent tag on by_nationality records (for continent-average lines) ----
    cont_n = 0
    for year, recs in data.get("by_nationality", {}).items():
        for rec in recs:
            rec["continent"] = COUNTRY_REGION.get(rec["country"], "기타")
            cont_n += 1

    json.dump(idx_doc, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"sido records updated: {sido_n}; national-year summaries updated: {nat_n}; evenness records: {ev}; by_nationality continent tags: {cont_n}")
    b24 = data["by_sigungu"]["2024"][0]
    print("evenness ex (sigungu):", b24.get("evenness"), "from H=", b24.get("shannon_H"), "S=", b24.get("n_nationalities"))
    print("national_evenness 2024:", data["summary"]["2024"].get("national_evenness"))
    s24 = data["summary"]["2024"]
    print("national 2024: HHI=", s24["national_HHI"], "incl=", s24["national_shannon_H_inclusive"], "shannon_H=", s24["national_shannon_H"])
    b = [r for r in data["by_sido"]["2024"] if r["sido"] == "경기도"]
    if b:
        print("경기도 2024: HHI=", b[0].get("HHI"), "incl=", b[0].get("shannon_H_inclusive"))


def build_undocumented():
    """Parse unauthorized-stay (미등록/불법체류) yearbook tables into undocumented.json.

    Two layouts:
    - 2019-2024: columns [대륙, 성별, 총합계, <visa code cols>]
    - 2014-2018: columns [국적명, 총계, 성별, 소계, <visa code cols>]
    Outputs national total, by sex, by visa status, and by continent per year.
    """
    RAW = os.path.join(ROOT, "01_raw_data")
    OUT = os.path.join(ROOT, "05_dashboard", "data", "undocumented.json")

    CONTI = {"아시아주": "아시아", "아시아주계": "아시아", "북아메리카주": "북아메리카", "북미주계": "북아메리카",
             "남아메리카주": "남아메리카", "중남미주계": "남아메리카", "유럽주": "유럽", "구주계": "유럽",
             "유럽주계": "유럽", "아프리카주": "아프리카", "아프리카주계": "아프리카",
             "오세아니아주": "오세아니아", "대양주계": "오세아니아", "기타": "기타", "신원미상": "기타"}
    CONTI_EN = {"아시아": "Asia", "북아메리카": "N. America", "남아메리카": "S. America",
                "유럽": "Europe", "아프리카": "Africa", "오세아니아": "Oceania", "기타": "Other"}

    def vcode(col):
        """Extract a normalized visa code like B1, C3, E9 from a column header."""
        s = str(col)
        m = re.search(r"([A-H])\s*-?\s*(\d{1,2})", s)
        if m:
            return m.group(1) + m.group(2)
        if "소계" in s or "합계" in s or "총" in s:
            return None
        return None

    def find_files():
        # yearbooks sit at 01_raw_data/출입국통계연보/<year>_출입국통계연보/; the 2025
        # edition spells the title "불법체류 외국인" with a space, hence the wildcard.
        YB = os.path.join(RAW, "출입국통계연보", "*")
        fs = glob.glob(os.path.join(YB, "*체류자격별 불법체류*외국인 현황.xls*"))
        fs += glob.glob(os.path.join(YB, "*체류자격별_불법체류*외국인_현황.xls*"))
        fs = [f for f in fs if "체류기간별" not in os.path.basename(f)]
        out = {}
        for f in fs:
            m = re.search(r"(20\d\d)", os.path.basename(f)) or re.search(r"(20\d\d)", f)
            if m and int(m.group(1)) <= LAST_YEAR:
                out.setdefault(int(m.group(1)), f)
        return out

    def num(x):
        try: return int(float(str(x).replace(",", "").split("\n")[0]))
        except: return 0

    def parse_recent(f):
        """2019-2024 layout: [대륙, 성별, 총합계, <visa code cols>]."""
        df = pd.read_excel(f, header=0)
        cols = list(df.columns)
        c_cont, c_sex, c_tot = cols[0], cols[1], cols[2]
        vmap = {c: vcode(c) for c in cols[3:] if vcode(c)}
        rec = {"total": 0, "male": 0, "female": 0, "by_visa": {}, "by_continent": {}}
        for _, r in df.iterrows():
            cont, sex = str(r[c_cont]).strip(), str(r[c_sex]).strip()
            if cont == "총합계" and rec["total"] == 0:
                rec["total"] = num(r[c_tot])
                for c, code in vmap.items():
                    rec["by_visa"][code] = rec["by_visa"].get(code, 0) + num(r[c])
            elif cont == "총합계" and sex == "남성":
                rec["male"] = num(r[c_tot])
            elif cont == "총합계" and sex == "여성":
                rec["female"] = num(r[c_tot])
            elif sex == "총계" and cont in CONTI:
                rec["by_continent"][CONTI[cont]] = rec["by_continent"].get(CONTI[cont], 0) + num(r[c_tot])
        return rec

    def parse_mid(f):
        """2014-2018 layout: [국적명, 총계/계, 성별, 소계/계.1, <visa>]; sex markers (T)/(M)/(F)."""
        df = pd.read_excel(f, header=0)
        cols = list(df.columns)
        c_nat, c_tot, c_sex, c_sub = cols[0], cols[1], cols[2], cols[3]
        vmap = {c: vcode(c) for c in cols[4:] if vcode(c)}
        rec = {"total": 0, "male": 0, "female": 0, "by_visa": {}, "by_continent": {}}
        cur_nat = None
        for _, r in df.iterrows():
            nat_raw = str(r[c_nat]).strip()
            if nat_raw and nat_raw != "nan":
                cur_nat = nat_raw
            sex = str(r[c_sex])
            is_total = cur_nat in ("총계", "계")
            if is_total and "T" in sex:
                rec["total"] = num(r[c_tot])
                for c, code in vmap.items():
                    rec["by_visa"][code] = rec["by_visa"].get(code, 0) + num(r[c])
            elif is_total and "M" in sex:
                rec["male"] = num(r[c_sub])
            elif is_total and "F" in sex:
                rec["female"] = num(r[c_sub])
            if nat_raw in CONTI:
                rec["by_continent"][CONTI[nat_raw]] = num(r[c_tot])
        return rec

    files = find_files()
    data = {}
    for y in sorted(files):
        f = files[y]
        try:
            if y >= 2019:
                rec = parse_recent(f)
            elif y >= 2014:
                rec = parse_mid(f)
            else:
                continue  # 2011-2013 multi-header handled separately if needed
            if rec["total"] > 0:
                data[y] = rec
                print(f"{y}: total={rec['total']:>7} visa_codes={len(rec['by_visa'])} cont={len(rec['by_continent'])}")
        except Exception as e:
            print(y, "ERR", repr(e))

    VISA_LABEL = {
        "B1": ("사증면제 (B-1)", "Visa waiver (B-1)"), "B2": ("관광통과 (B-2)", "Tourist/transit (B-2)"),
        "C3": ("단기방문 (C-3)", "Short-term visit (C-3)"), "C4": ("단기취업 (C-4)", "Short-term work (C-4)"),
        "E9": ("비전문취업 (E-9)", "Non-prof. work (E-9)"), "E7": ("전문인력 (E-7)", "Skilled work (E-7)"),
        "D2": ("유학 (D-2)", "Study (D-2)"), "D4": ("일반연수 (D-4)", "Training (D-4)"),
        "F6": ("결혼이민 (F-6)", "Marriage (F-6)"), "E6": ("예술흥행 (E-6)", "Arts/perf. (E-6)"),
        "H2": ("방문취업 (H-2)", "Working visit (H-2)"),
    }
    out = {"years": sorted(data.keys()),
           "national": {str(y): data[y] for y in sorted(data)},
           "visa_labels": {k: {"ko": v[0], "en": v[1]} for k, v in VISA_LABEL.items()},
           "continent_en": CONTI_EN,
           "note_ko": "법무부 출입국·외국인정책 통계연보 6장(불법체류외국인 현황). 미등록(초과체류 등) 외국인.",
           "note_en": "KIS Yearbook ch.6 (unauthorized residents)."}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("wrote", OUT)



def build_national_language():
    """National estimated-language series for the Overview tab, 2006-2024.

    The per-sigungu language data in indices.json only starts in 2014 (subnational
    panel). The Overview language trend should span the full 2006-2024 like the
    other national trends, so compute national language counts from the national
    by-nationality totals (staying foreigners) using the same COUNTRY_LANGUAGE map
    as build_dashboard.py. Writes site/data/national_language.json = {year: [{language, count}]}.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))

    print("map entries:", len(COUNTRY_LANGUAGE))

    data = json.load(open(os.path.join(ROOT, "05_dashboard", "data", "data.json"), encoding="utf-8"))
    years = data["years"]
    BASES = {b: data["populations"][b]["data"]["ALL"] for b in ("stay", "reg")}  # {year: {country: n}}

    # Weighted country->language shares (CLDR-derived, 2 letter Korean labels).
    shares_path = os.path.join(ROOT, "03_cleaned_data", "country_language_shares.json")
    COUNTRY_SHARES = json.load(open(shares_path, encoding="utf-8")) if os.path.exists(shares_path) else {}

    out = {b: {} for b in BASES}
    for b, base_all in BASES.items():
      for y in years:
        yd = base_all.get(str(y)) or base_all.get(y) or {}
        by_lang = {}
        for country, n in yd.items():
            if not n: continue
            if country in COUNTRY_SHARES:
                # an EMPTY share list is deliberate (wholly Korean-L1 origins such as
                # 한국계중국인 contribute zero) — do not fall back to the single map,
                # which would count them as Chinese-language demand
                for sh in COUNTRY_SHARES[country]:
                    by_lang[sh["language"]] = by_lang.get(sh["language"], 0) + n * sh["share"]
            else:
                lg = COUNTRY_LANGUAGE.get(country)
                if lg: by_lang[lg] = by_lang.get(lg, 0) + n
        out[b][str(y)] = sorted(({"language": k, "count": round(v, 1)} for k, v in by_lang.items() if v >= 0.5),
                                key=lambda d: -d["count"])

    path = os.path.join(ROOT, "05_dashboard", "data", "national_language.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print("years:", years[0], "-", years[-1])
    latest = max(out["stay"], key=int)
    print(f"stay {latest} top:", [(d["language"], d["count"]) for d in out["stay"][latest][:5]])
    print(f"reg  {latest} top:", [(d["language"], d["count"]) for d in out["reg"][latest][:5]])
    print("wrote", path)


def merge_country_names():
    """Clean/merge variant or dependent-territory nationality names across the
    dashboard data files (data.json populations, region.json by_sigungu/by_sido),
    then regenerate the derived national-language series.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")

    MERGE = {
        "미국인근섬": "미국",
        "미령버진아일랜드": "미국",
        "불령가이아나": "가이아나",
        "영령인도양섬": "영국",
        "앤티카바부다": "앤티가바부다",
    }

    def merge_counts(d):
        """d = {country: count}; merge in place, return d."""
        for bad, good in MERGE.items():
            if bad in d:
                d[good] = d.get(good, 0) + d.pop(bad)
        return d

    # ---- data.json ----
    dj = os.path.join(SITE, "data.json")
    data = json.load(open(dj, encoding="utf-8"))
    n = 0
    for popkey in ("stay", "reg"):
        pop = data["populations"].get(popkey)
        if not pop: continue
        for code, yd in pop["data"].items():
            for y, cc in yd.items():
                if isinstance(cc, dict):
                    before = len(cc); merge_counts(cc); n += before - len(cc)
    # country_en map: drop merged-away keys
    ce = data.get("country_en", {})
    for bad in MERGE:
        ce.pop(bad, None)
    json.dump(data, open(dj, "w", encoding="utf-8"), ensure_ascii=False)
    print("data.json: merged", n, "country-key occurrences")

    # ---- region.json ----
    rj = os.path.join(SITE, "region.json")
    region = json.load(open(rj, encoding="utf-8"))
    m = 0
    for y, sidos in region.get("by_sigungu", {}).items():
        for sido, sigs in sidos.items():
            for sg, cc in sigs.items():
                if isinstance(cc, dict): before = len(cc); merge_counts(cc); m += before - len(cc)
    for y, sidos in region.get("by_sido", {}).items():
        for sido, cc in sidos.items():
            if isinstance(cc, dict): before = len(cc); merge_counts(cc); m += before - len(cc)
    json.dump(region, open(rj, "w", encoding="utf-8"), ensure_ascii=False)
    print("region.json: merged", m, "country-key occurrences")

    # ---- regenerate national_language.json from cleaned data ----
    build_national_language()   # same module; recompute on the merged names

    # verify
    data2 = json.load(open(dj, encoding="utf-8"))
    cs = set()
    for y, cc in data2["populations"]["stay"]["data"]["ALL"].items():
        if isinstance(cc, dict): cs.update(cc.keys())
    print("remaining merged names in data:", [b for b in MERGE if b in cs])
    print("미국 in ALL 2024:", data2["populations"]["stay"]["data"]["ALL"]["2024"].get("미국"))



def build_visa_sigungu():
    """Parse the district x visa-code 'registered foreigner' yearbook tables for
    2008-2024 into a single panel for the dashboard and the dataset release.

    The source layout changed over the years, so a single unified parser handles
    three variants:
      * 2008-2009  : sido in col1 (block header), sigungu in col2; one row per
                     district (no sex split). Header labels mis-named "국적/체류자격".
      * 2010-2011, 2014-2024: sido in col0 (block header), sigungu in col1,
                     sex marker in col2 (계/남/여), three rows per district.
      * 2012-2013  : same column layout as above, but each cell is newline-stacked
                     (계/남/여 concatenated by 
    ) so each district occupies one row.

    Writes site/data/visa_region.json:
      { "years": [2008..2024],
        "data": { "2024": { "경기도|가평군": {"D2": 30, "E9": 12, ...}, ... }, ... } }
    keyed by "sido|sigungu(no spaces)" to match korea_sigungu.json match_key.
    """
    warnings.filterwarnings("ignore")

    from kird import ROOT  # noqa: E402
    HERE = os.path.dirname(os.path.abspath(__file__))
    RAW = os.path.join(ROOT, "01_raw_data")
    OUT = os.path.join(ROOT, "05_dashboard", "data", "visa_region.json")

    idx = json.load(open(os.path.join(ROOT, "05_dashboard", "data", "indices.json"), encoding="utf-8"))["data"]
    LATEST = max(idx["by_sido"], key=int)
    CANON = sorted({r["sido"] for r in idx["by_sido"][LATEST]})
    SHORT = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
             "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
             "경기": "경기도", "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
             "전북": "전라북도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도"}

    def norm_sido(name):
        n = str(name).split("\n")[0].strip()
        if not n or len(n) < 2:
            # single characters cause false hits via substring (e.g., sex markers
            # '남'/'여' would otherwise match 경상남도/전라남도)
            return None
        n = n.replace("강원특별자치도", "강원도").replace("전북특별자치도", "전라북도")
        if n in CANON: return n
        if n in SHORT: return SHORT[n]
        for s in CANON:
            if n in s or s.startswith(n): return s
        return None

    def vcode(h):
        m = re.search(r"([A-H])\s*-?\s*(\d{1,2})", str(h))
        return (m.group(1) + m.group(2)) if m else None

    AGG = {"총계", "총합계", "소계", "계", "합계", "Grand-Total", "Sub-Total", "Total",
           "nan", "", "시군구", "시도", "지역", "성별", "국적", "체류자격",
           "Nationality", "Region", "Sex", "sex"}
    SEX_TOTAL = {"계", "계(T)", "T", "Total", "총계", "Grand-Total"}
    SEX_M     = {"남", "남(M)", "M", "Male", "남성"}
    SEX_F     = {"여", "여(F)", "F", "Female", "여성"}

    def find_file(year):
        # the yearbooks live at 01_raw_data/출입국통계연보/<year>_출입국통계연보/
        pats = [
            f"출입국통계연보/{year}*/**/*시군구*체류자격*등록외국인*.xls*",
            f"출입국통계연보/{year}*/**/*시군구*및*체류자격*.xls*",
            f"출입국통계연보/{year}*/**/*지역*체류자격*등록외국인*.xls*",
            f"출입국통계연보/{year}*/**/*지역및체류자격*.xls*",
        ]
        for p in pats:
            g = glob.glob(os.path.join(RAW, p), recursive=True)
            # exclude the country x visa file ("국적_지역 및 체류자격별...") which
            # would otherwise be picked over the sigungu x visa file in some years
            g = [f for f in g if "국적" not in os.path.basename(f)]
            if g: return g[0]
        return None

    def parse_year(path):
        df = pd.read_excel(path, header=None)
        # locate header row by density of visa codes
        hr = None
        for r in range(min(8, df.shape[0])):
            row = [str(x) if pd.notna(x) else "" for x in df.iloc[r].tolist()]
            if sum(1 for c in row if vcode(c)) >= 3:
                hr = r; break
        if hr is None:
            return {}
        h_codes = df.iloc[hr].tolist()
        h_alt = df.iloc[hr - 1].tolist() if hr > 0 else [None] * df.shape[1]
        vcols = {}
        for c in range(df.shape[1]):
            for cell in (h_codes[c], h_alt[c]):
                v = vcode(cell)
                if v:
                    vcols[c] = v
                    break
        if not vcols:
            return {}
        first_vcol = min(vcols.keys())

        blocks = {}
        cur_sido = None
        cur_sg = None
        for r in range(hr + 1, df.shape[0]):
            labels = [str(df.iat[r, c]) if pd.notna(df.iat[r, c]) else "" for c in range(first_vcol)]
            labels_first = [l.split("\n")[0].strip() for l in labels]

            # Detect a new sido on this row, from any label cell (Korean first-line,
            # then fall back to subsequent lines of multi-line cells for English).
            sd_new = None
            for lab in labels_first:
                if not lab or lab in AGG: continue
                sd = norm_sido(lab)
                if sd: sd_new = sd; break
            if not sd_new:
                for lab in labels:
                    for ln in lab.split("\n")[1:]:
                        sd = norm_sido(ln.strip())
                        if sd: sd_new = sd; break
                    if sd_new: break
            if sd_new:
                if sd_new != cur_sido:
                    cur_sg = None     # block boundary; do not carry previous district forward
                cur_sido = sd_new
                # 세종특별자치시 has no sub-districts; treat the sido row as the
                # single-district row so its visa totals are captured under 세종시.
                if sd_new == "세종특별자치시":
                    cur_sg = "세종시"

            # Detect sigungu (non-aggregate Korean name with 시/군/구), not a sido.
            sg_new = None
            for lab in labels_first:
                if not lab or lab in AGG: continue
                if norm_sido(lab): continue
                if re.match(r"^[A-Za-z]", lab): continue
                if any(t in lab for t in ("시", "군", "구")):
                    sg_new = lab.replace(" ", "")
                    break
            if sg_new:
                cur_sg = sg_new

            if not (cur_sido and cur_sg):
                continue

            # Detect sex marker; collect each row under its sex so we can later
            # prefer the 계 row when present, else sum 남+여 (the 2019 layout has
            # no per-district 계 row), or treat as 'N' (single row per district).
            sex = None
            for lab in labels_first:
                if lab in SEX_TOTAL: sex = "T"; break
                if lab in SEX_M: sex = "M"; break
                if lab in SEX_F: sex = "F"; break

            # Read visa values; take first line of each cell (handles stacked T/M/F).
            rec = {}
            for c, code in vcols.items():
                cell = str(df.iat[r, c]) if pd.notna(df.iat[r, c]) else ""
                val_str = cell.split("\n")[0].replace(",", "").strip()
                try:
                    v = int(float(val_str))
                except Exception:
                    v = 0
                if v:
                    rec[code] = rec.get(code, 0) + v
            if rec:
                key = cur_sido + "|" + cur_sg
                blocks.setdefault(key, {})[sex or "N"] = rec

        # Resolve per district: prefer 계 row, then no-sex-split, else sum M+F.
        out = {}
        for key, bysex in blocks.items():
            if "T" in bysex:
                out[key] = bysex["T"]
            elif "N" in bysex:
                out[key] = bysex["N"]
            else:
                agg = {}
                for sx in ("M", "F"):
                    for code, v in bysex.get(sx, {}).items():
                        agg[code] = agg.get(code, 0) + v
                if agg:
                    out[key] = agg
        return out


    def harmonize_boundaries(blk):
        """Apply the same district-boundary fixes used in fix_subnational.py so the
        visa panel uses the same district keys as the other subnational files."""
        # 1. 인천 남구 -> 미추홀구 (renamed 2018). Merge if both present (transition).
        nam, mic = blk.get("인천광역시|남구"), blk.get("인천광역시|미추홀구")
        if nam:
            merged = dict(mic) if mic else {}
            for c, v in nam.items():
                merged[c] = merged.get(c, 0) + v
            blk["인천광역시|미추홀구"] = merged
            del blk["인천광역시|남구"]
        # 2. 군위군 경상북도 -> 대구광역시 (transferred 2023; relabel all years for
        #    a continuous series).
        if "경상북도|군위군" in blk:
            blk["대구광역시|군위군"] = blk.pop("경상북도|군위군")
        # 3. 부천시 gu consolidation (gu abolished 2016, re-created 2024, broke the
        #    series). Sum gu rows into a single 부천시 unit.
        bu_keys = [k for k in list(blk) if k.startswith("경기도|부천시") and k != "경기도|부천시"]
        if bu_keys:
            merged = dict(blk.get("경기도|부천시", {}))
            for bk in bu_keys:
                for c, v in blk[bk].items():
                    merged[c] = merged.get(c, 0) + v
                del blk[bk]
            if merged:
                blk["경기도|부천시"] = merged
        return blk


    data = {}
    for year in range(2008, LAST_YEAR + 1):
        f = find_file(year)
        if not f:
            print(year, "FILE NOT FOUND"); continue
        parsed = harmonize_boundaries(parse_year(f))
        tot = sum(sum(r.values()) for r in parsed.values())
        print(f"{year}: {len(parsed)} districts, sum={tot:,}  [{os.path.basename(f)[:40]}]")
        if parsed:
            data[str(year)] = parsed

    out = {"years": sorted(int(y) for y in data), "data": data}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("wrote", OUT)

    # Validation: district-sum vs national registered total per year (data.json)
    dd = json.load(open(os.path.join(ROOT, "05_dashboard", "data", "data.json"), encoding="utf-8"))
    reg_all = dd["populations"]["reg"]["data"]["ALL"]
    print("\nValidation (district-sum vs national registered):")
    for y in sorted(data.keys()):
        nat = sum(reg_all.get(y, {}).values())
        dist = sum(sum(r.values()) for r in data[y].values())
        pct = 100 * (dist - nat) / nat if nat else 0
        flag = "" if abs(pct) < 1 else "  <-- check"
        print(f"  {y}: national={nat:,}  district-sum={dist:,}  ({pct:+.2f}%){flag}")



def add_refugee_language():
    """Estimate the public-service language demand of protected refugees, from the
    cumulative top-nationality lists in refugee_data (recognized refugees and
    humanitarian-stay holders), using the same nationality->language map as the
    general language_demand. Injects refugee_data.language_demand into data.json:

      {"recognized":[{language, language_en, count}], "humanitarian":[...], "protected":[...]}

    These cover the published top nationalities only (not every nationality), so the
    panel is labeled as an approximation.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    DJ = os.path.join(ROOT, "05_dashboard", "data", "data.json")

    CL = dict(COUNTRY_LANGUAGE)
    CL.setdefault("아이티", "프랑스어")  # Haiti -> French (public-service language)

    LANG_EN = {
        "아랍어": "Arabic", "미얀마어": "Burmese", "암하라어": "Amharic", "벵골어": "Bengali",
        "우르두어": "Urdu", "프랑스어": "French", "페르시아어": "Persian", "다리어": "Dari",
        "중국어": "Chinese", "러시아어": "Russian", "영어": "English", "스와힐리어": "Swahili",
        "터키어": "Turkish", "스페인어": "Spanish", "벵갈어": "Bengali",
    }

    data = json.load(open(DJ, encoding="utf-8"))
    rd = data["refugee_data"]

    # Weighted country->language shares (CLDR-derived) — same source the dashboard
    # uses for the general language_demand panels.
    shares_path = os.path.join(ROOT, "03_cleaned_data", "country_language_shares.json")
    COUNTRY_SHARES = json.load(open(shares_path, encoding="utf-8")) if os.path.exists(shares_path) else {}


    def by_lang(rows):
        agg = {}
        for r in rows:
            ko = r[0]; cnt = r[2]
            shares = COUNTRY_SHARES.get(ko)
            if shares:
                for sh in shares:
                    agg[sh["language"]] = agg.get(sh["language"], 0) + cnt * sh["share"]
            else:
                lang = CL.get(ko) or ko  # 기타로 묶지 않음
                agg[lang] = agg.get(lang, 0) + cnt
        out = [{"language": k, "language_en": LANG_EN.get(k, k), "count": round(v, 1)}
               for k, v in sorted(agg.items(), key=lambda x: -x[1]) if v >= 0.5]
        return out


    rec = by_lang(rd.get("top_recognized_nationalities", []))
    hum = by_lang(rd.get("top_humanitarian_nationalities", []))
    # combined protected = recognized + humanitarian
    combo = {}
    for lst in (rec, hum):
        for d in lst:
            combo[d["language"]] = combo.get(d["language"], 0) + d["count"]
    prot = [{"language": k, "language_en": LANG_EN.get(k, k), "count": v}
            for k, v in sorted(combo.items(), key=lambda x: -x[1])]

    rd["language_demand"] = {"recognized": rec, "humanitarian": hum, "protected": prot}
    json.dump(data, open(DJ, "w", encoding="utf-8"), ensure_ascii=False)
    print("recognized langs:", [(d["language"], d["count"]) for d in rec])
    print("humanitarian langs:", [(d["language"], d["count"]) for d in hum])
    print("protected (combined):", [(d["language"], d["count"]) for d in prot])


def extend_sigungu_nationality():
    """Extend the district x nationality panel (foreign_residents_by_sigungu) back
    to 2008-2013 by parsing the '지역 및 국적별 등록외국인 현황' yearbook tables.
    The build_dashboard pipeline already handles 2014-2024 from a different file
    family; this script just adds the 2008-2013 years onto region.json's by_sigungu
    block (and computes matching indices_by_sigungu records via the same helpers
    that fix_subnational uses), so the downstream recompute steps can pick them up.

    Three pre-2014 layouts are handled, mirroring build_visa_sigungu:
      * 2008-2009  : single row per district (no sex split), 시도 in col1, 시군구
                     in col2, 총계 in col3, nationalities in col4+.
      * 2010-2011  : 시도 in col0, 시군구 in col1, sex in col2; three rows per
                     district (계/남/여).
      * 2012-2013  : same column layout as above, but each cell newline-stacks
                     the T/M/F values; one row per district.
    """
    warnings.filterwarnings("ignore")

    from kird import (COUNTRY_CANONICAL, COUNTRY_LANGUAGE,
                              COUNTRY_REGION)
    from kird import ROOT  # noqa: E402
    HERE = os.path.dirname(os.path.abspath(__file__))
    RAW = os.path.join(ROOT, "01_raw_data")
    SITE = os.path.join(ROOT, "05_dashboard", "data")

    idx = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))["data"]
    region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))
    CANON = sorted({r["sido"] for r in idx["by_sido"][max(idx["by_sido"], key=int)]})
    SHORT = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
             "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
             "경기": "경기도", "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
             "전북": "전라북도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도"}

    CR, CLG, CANON_NAME = COUNTRY_REGION, COUNTRY_LANGUAGE, COUNTRY_CANONICAL


    def norm_sido(name):
        n = str(name).split("\n")[0].strip()
        if len(n) < 2: return None
        n = n.replace("강원특별자치도", "강원도").replace("전북특별자치도", "전라북도")
        if n in CANON: return n
        if n in SHORT: return SHORT[n]
        for s in CANON:
            if n in s or s.startswith(n): return s
        return None


    AGG = {"총계", "총합계", "소계", "계", "합계", "Grand-Total", "Sub-Total", "Total",
           "nan", "", "시군구", "시도", "지역", "성별", "국적", "Nationality", "Region", "Sex", "sex"}
    SEX_TOTAL = {"계", "계(T)", "T", "Total", "총계", "Grand-Total"}
    SEX_M = {"남", "남(M)", "M", "Male", "남성"}
    SEX_F = {"여", "여(F)", "F", "Female", "여성"}


    def find_file(year):
        # the yearbooks live at 01_raw_data/출입국통계연보/<year>_출입국통계연보/
        pats = [f"출입국통계연보/{year}*/**/*지역*국적*등록외국인*.xls*",
                f"출입국통계연보/{year}*/**/*지역및국적*.xls*"]
        for p in pats:
            g = glob.glob(os.path.join(RAW, p), recursive=True)
            if g: return g[0]
        return None


    def is_country_header(cell):
        """Heuristic: a non-aggregate Korean string of >=2 chars (or English country),
        not a sido name. Header rows have country names in cols >= total-col."""
        s = str(cell).split("\n")[0].strip()
        if not s or s in AGG or s in SEX_TOTAL or s in SEX_M or s in SEX_F:
            return False
        if norm_sido(s): return False
        # English label row entries like 'China', 'Vietnam' or Korean names like '중국'
        return len(s) >= 2 and not re.match(r"^[\d,.\-+%()\s]+$", s)


    def parse_year(path):
        df = pd.read_excel(path, header=None)
        # Header row = one that contains 총계 / Grand-Total in some column followed
        # by country names. Look for a row with '총계' or 'Grand-Total'.
        hr = None
        total_col = None
        for r in range(min(8, df.shape[0])):
            for c in range(min(8, df.shape[1])):
                cv = str(df.iat[r, c]) if pd.notna(df.iat[r, c]) else ""
                if cv.strip() in ("총계", "Grand-Total"):
                    # Make sure there are non-numeric labels to the right
                    right_labels = [str(df.iat[r, cc]) for cc in range(c + 1, min(c + 6, df.shape[1])) if pd.notna(df.iat[r, cc])]
                    if any(is_country_header(rl) for rl in right_labels):
                        hr = r; total_col = c; break
            if hr is not None:
                break
        if hr is None:
            return {}
        # Country columns: scan a 2-row band (header + below) for country labels.
        h1 = df.iloc[hr].tolist()
        h2 = df.iloc[hr + 1].tolist() if hr + 1 < df.shape[0] else [None] * df.shape[1]
        countries = {}
        for c in range(total_col + 1, df.shape[1]):
            for cell in (h1[c], h2[c]):
                cn = str(cell).split("\n")[0].strip() if cell is not None else ""
                if is_country_header(cn) and re.search(r"[가-힣]", cn):
                    # Prefer Korean name; fall back to whatever non-empty Korean cell we find.
                    # The 2009 sheet pads its Korean headers to a fixed width ("중      국",
                    # "한국계 중국인"), so strip the internal spaces here — otherwise those
                    # labels miss every COUNTRY_REGION / COUNTRY_LANGUAGE lookup and 2009
                    # lands ~94% in 기타 at the continent level.
                    cn = re.sub(r"\s+", "", cn)
                    countries[c] = CANON_NAME.get(cn, cn)
                    break
        if not countries:
            return {}
        first_country_col = min(countries.keys())
        # Walk data rows
        blocks = {}
        cur_sido = None
        cur_sg = None
        for r in range(hr + 2, df.shape[0]):
            labels = [str(df.iat[r, c]) if pd.notna(df.iat[r, c]) else "" for c in range(first_country_col)]
            labels_first = [l.split("\n")[0].strip() for l in labels]
            # New sido?
            sd_new = None
            for lab in labels_first:
                if not lab or lab in AGG: continue
                sd = norm_sido(lab)
                if sd: sd_new = sd; break
            if not sd_new:
                for lab in labels:
                    for ln in lab.split("\n")[1:]:
                        sd = norm_sido(ln.strip())
                        if sd: sd_new = sd; break
                    if sd_new: break
            if sd_new:
                if sd_new != cur_sido:
                    cur_sg = None
                cur_sido = sd_new
                if sd_new == "세종특별자치시":
                    cur_sg = "세종시"
            # Detect sigungu (Korean, not sido, contains 시/군/구)
            sg_new = None
            for lab in labels_first:
                if not lab or lab in AGG: continue
                if norm_sido(lab): continue
                if re.match(r"^[A-Za-z]", lab): continue
                if any(t in lab for t in ("시", "군", "구")):
                    sg_new = lab.replace(" ", ""); break
            if sg_new:
                cur_sg = sg_new
            if not (cur_sido and cur_sg):
                continue
            # Sex marker
            sex = None
            for lab in labels_first:
                if lab in SEX_TOTAL: sex = "T"; break
                if lab in SEX_M: sex = "M"; break
                if lab in SEX_F: sex = "F"; break
            # Read country values (first line of cell handles stacked)
            rec = {}
            for c, cn in countries.items():
                cell = str(df.iat[r, c]) if pd.notna(df.iat[r, c]) else ""
                val_str = cell.split("\n")[0].replace(",", "").strip()
                try: v = int(float(val_str))
                except Exception: v = 0
                if v:
                    rec[cn] = rec.get(cn, 0) + v
            if rec:
                key = cur_sido + "|" + cur_sg
                blocks.setdefault(key, {})[sex or "N"] = rec
        # Resolve sex
        out = {}
        for key, bysex in blocks.items():
            if "T" in bysex:
                out[key] = bysex["T"]
            elif "N" in bysex:
                out[key] = bysex["N"]
            else:
                agg = {}
                for sx in ("M", "F"):
                    for cn, v in bysex.get(sx, {}).items():
                        agg[cn] = agg.get(cn, 0) + v
                if agg: out[key] = agg
        return out


    def harmonize(blk):
        # Same district-boundary fixes as elsewhere in the pipeline.
        nam = blk.get("인천광역시|남구"); mic = blk.get("인천광역시|미추홀구")
        if nam:
            merged = dict(mic) if mic else {}
            for c, v in nam.items(): merged[c] = merged.get(c, 0) + v
            blk["인천광역시|미추홀구"] = merged
            del blk["인천광역시|남구"]
        if "경상북도|군위군" in blk:
            blk["대구광역시|군위군"] = blk.pop("경상북도|군위군")
        bu_keys = [k for k in list(blk) if k.startswith("경기도|부천시") and k != "경기도|부천시"]
        if bu_keys:
            merged = dict(blk.get("경기도|부천시", {}))
            for bk in bu_keys:
                for c, v in blk[bk].items(): merged[c] = merged.get(c, 0) + v
                del blk[bk]
            if merged: blk["경기도|부천시"] = merged
        return blk


    # ---------------- run ----------------
    parsed = {}
    for year in range(2008, 2014):
        f = find_file(year)
        if not f:
            print(year, "FILE NOT FOUND"); continue
        blk = harmonize(parse_year(f))
        sg_count = len(blk)
        nat_set = {c for r in blk.values() for c in r}
        tot = sum(sum(r.values()) for r in blk.values())
        print(f"{year}: {sg_count} districts, {len(nat_set)} unique nationalities, sum={tot:,}  [{os.path.basename(f)[:38]}]")
        parsed[str(year)] = blk

    # Validation: district-sum vs national registered total
    print("\nValidation (district-sum vs national registered):")
    dd = json.load(open(os.path.join(SITE, "data.json"), encoding="utf-8"))
    reg_all = dd["populations"]["reg"]["data"]["ALL"]
    for y in sorted(parsed):
        nat = sum(reg_all.get(y, {}).values())
        dist = sum(sum(r.values()) for r in parsed[y].values())
        pct = 100 * (dist - nat) / nat if nat else 0
        print(f"  {y}: national={nat:,}  district-sum={dist:,}  ({pct:+.2f}%)")

    # Save raw parsed for inspection (before merging into region.json)
    out = os.path.join(SITE, "_sigungu_nat_2008_2013_preview.json")
    json.dump(parsed, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\npreview written -> {out}")
    print("(Not yet merged into region.json — review first, then run merge.)")



def merge_sigungu_nationality():
    """The 2008-2013 district panel merged into region.json and indices.json.

    Step 09 parses those years out of the pre-2014 province-by-nationality tables and
    writes a preview; this step reviews it against the canonical district names and
    merges it in, computing each new district-year's indices the same way every other
    year is computed.
    """
    """Merge the 2008-2013 district x nationality data (produced by
    extend_sigungu_nat_2008_2013.py preview) into region.json (by_sigungu) and
    indices.json (by_sigungu), computing diversity indices via the same helpers
    fix_subnational uses. After running, re-run fix_subnational ->
    recompute_enclaves -> recompute_summary -> export_dataset to extend every
    derived series back to 2008.

    Note: the 2008-2013 yearbook publishes only the top 19 nationalities + 기타
    at the district level, so diversity indices for those years are computed on
    20 nationality bins (top_20 coverage) rather than the ~200 of 2014+. The
    indices are still informative (cross-district comparison is unaffected), but
    year-on-year jumps at 2013->2014 reflect coverage change as well as real
    distribution shifts.
    """
    import os, re, json, math
    import pandas as pd, warnings
    warnings.filterwarnings("ignore")

    from kird import make_record
    from kird import COUNTRY_LANGUAGE, COUNTRY_REGION
    from kird import ROOT  # noqa: E402
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")
    DR_DATA = os.path.join(ROOT, "04_dataset_release", "data")

    PREVIEW = os.path.join(SITE, "_sigungu_nat_2008_2013_preview.json")
    preview = json.load(open(PREVIEW, encoding="utf-8"))

    # Load fix_subnational helpers in-process so we use the exact same formulae.
    CR = COUNTRY_REGION
    CLG = COUNTRY_LANGUAGE

    # Population denominator (sigungu) for 2008-2013. Read from the pipeline's own
    # panel: the release stopped shipping resident_population_by_sigungu.csv (its
    # columns were folded into summary_by_sigungu.csv), and population_long.csv is
    # the same table one step earlier — verified identical on every shared key.
    pop = pd.read_csv(os.path.join(ROOT, "03_cleaned_data", "population_long.csv"))
    pop_lookup = {}                # (year, sido, sigungu_nospace) -> total_pop
    canonical_sg = {}              # (sido, sigungu_nospace) -> canonical sigungu (with spaces)
    for _, r in pop.iterrows():
        sg_full = str(r["sigungu"])
        sg_ns = sg_full.replace(" ", "")
        canonical_sg.setdefault((r["sido"], sg_ns), sg_full)
        if r["year"] not in (2008, 2009, 2010, 2011, 2012, 2013):
            continue
        pop_lookup[(int(r["year"]), r["sido"], sg_ns)] = int(r["total_pop"]) if pd.notna(r["total_pop"]) else None

    # Also seed canonical mapping from the existing 2014+ district indices so any
    # compound names (고양시 덕양구, 안산시 단원구, etc) get the spaced form. Read
    # straight from indices.json — the release no longer ships indices_by_sigungu.csv.
    _idx_json = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))["data"]
    for ystr, rows in _idx_json.get("by_sigungu", {}).items():
        if int(ystr) < 2014:
            continue
        for r in rows:
            canonical_sg.setdefault((r["sido"], str(r["sigungu"]).replace(" ", "")), str(r["sigungu"]))

    # Apply administrative-reorganization name remap so the 2008-2013 records
    # land under the post-reorganization sigungu name used by 2014+ (and by the
    # geo polygon file). Pre-merger names that don't map 1:1 (창원시 / 마산시,
    # 청주시 흥덕구→흥덕구+서원구) are left under their original name; the figure
    # layer renders those parents onto the post-merger polygons via lookup.
    REMAP = {
        "경기도|여주군":       "경기도|여주시",          # gun → si promotion (2013)
        "충청남도|당진군":     "충청남도|당진시",        # gun → si promotion (2012)
        "충청남도|연기군":     "세종특별자치시|세종시",  # absorbed into Sejong (2012)
        "경상남도|진해시":     "경상남도|창원시진해구",  # merged into Changwon (2010)
        "충청북도|청원군":     "충청북도|청주시청원구",  # absorbed into Cheongju (2014)
    }
    # Denominator-only aliases. The parsed 2008-2013 nationality block already uses
    # the harmonized district names, but the MOIS population table still carries the
    # pre-rename ones, so these two districts came out with a null denominator (and
    # dropped ~450k persons a year from the national total).
    POP_ALIASES = {
        "인천광역시|남구":   "인천광역시|미추홀구",  # renamed 2018
        "경상북도|군위군":   "대구광역시|군위군",    # transferred to Daegu 2023
    }
    for old, new in POP_ALIASES.items():
        old_sido, old_sg = old.split("|"); new_sido, new_sg = new.split("|")
        for y in range(2008, 2014):
            v = pop_lookup.get((y, old_sido, old_sg))
            if v is not None and (y, new_sido, new_sg) not in pop_lookup:
                pop_lookup[(y, new_sido, new_sg)] = v

    # Mirror REMAP into pop_lookup so the renamed districts inherit the parent's
    # pop denominator (MOIS file uses the old names for those years).
    for old, new in REMAP.items():
        old_sido, old_sg = old.split("|"); new_sido, new_sg = new.split("|")
        for y in range(2008, 2014):
            v = pop_lookup.get((y, old_sido, old_sg))
            if v is not None and (y, new_sido, new_sg) not in pop_lookup:
                pop_lookup[(y, new_sido, new_sg)] = v

    # Aggregate Bucheon's three abolished gu (소사/오정/원미) into 부천시 for
    # 2008-2009. The extend script already merges the gu nationality counts into
    # 부천시; the pop denominator side just needs the sum of the three gu's
    # resident populations so foreign_share_pct can be computed.
    for y in range(2008, 2014):
        bu_sum = 0
        for gu in ("부천시원미구", "부천시소사구", "부천시오정구"):
            v = pop_lookup.get((y, "경기도", gu))
            if v is not None:
                bu_sum += v
        if bu_sum and (y, "경기도", "부천시") not in pop_lookup:
            pop_lookup[(y, "경기도", "부천시")] = bu_sum

    # Load region.json + indices.json
    region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))
    full = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
    idx = full["data"]
    RBS = region["by_sigungu"]
    IBS = idx["by_sigungu"]

    added_rbs = added_ibs = 0
    missing_pop = []
    for ystr, blk in preview.items():
        # Apply REMAP to this year's parsed block before indexing
        for old, new in REMAP.items():
            if old in blk:
                agg = dict(blk.get(new, {}))
                for c, v in blk[old].items():
                    agg[c] = agg.get(c, 0) + v
                blk[new] = agg
                del blk[old]
        y = int(ystr)
        RBS.setdefault(ystr, {})
        IBS.setdefault(ystr, [])
        # Drop any pre-existing entries for these years to avoid duplicates
        RBS[ystr] = {}
        IBS[ystr] = []
        for key, nat in blk.items():
            sido, sg_ns = key.split("|")
            pop_v = pop_lookup.get((y, sido, sg_ns))
            if pop_v is None:
                missing_pop.append((y, key))
            # Use the canonical sigungu name (with spaces, e.g. "안산시 단원구")
            # so 2008-2013 joins cleanly with 2014+ in indices, region, language.
            # Fall back to the parsed no-space form for dissolved districts that
            # don't exist in 2014+.
            sg_canonical = canonical_sg.get((sido, sg_ns), sg_ns)
            RBS[ystr].setdefault(sido, {})[sg_canonical] = nat
            rec = make_record(sido, sg_canonical, nat, pop_v, "ns")
            IBS[ystr].append(rec)
            added_rbs += 1
            added_ibs += 1

    # Seed idx['language'] and idx['summary'] so fix_subnational and recompute_*
    # pick up the new years instead of skipping or KeyError-ing.
    for ystr in preview:
        idx.setdefault("language", {}).setdefault(ystr, {"national": [], "by_sigungu": {}})
        # national_total_pop = sum of district total_pop for the year (matches the
        # existing convention; recompute_summary will fill the rest of the fields).
        natpop = sum((r.get("total_pop") or 0) for r in IBS[ystr])
        idx.setdefault("summary", {}).setdefault(ystr, {})
        idx["summary"][ystr]["national_total_pop"] = natpop
        # placeholders that recompute_summary will overwrite; required so its
        # report line ("old vs new") can read them
        idx["summary"][ystr].setdefault("national_foreign_total", 0)
        idx["summary"][ystr].setdefault("n_enclaves", 0)

    # Extend region.json years field
    all_years = sorted({int(y) for y in RBS} | set(region["years"]))
    region["years"] = all_years

    json.dump(region, open(os.path.join(SITE, "region.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(full, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)

    print(f"Merged 2008-2013 district nationality data:")
    print(f"  RBS rows added: {added_rbs} (across years {sorted(preview)})")
    print(f"  IBS rows added: {added_ibs}")
    print(f"  Districts missing population denominator: {len(missing_pop)}")
    if missing_pop[:5]:
        print(f"    sample: {missing_pop[:5]}")
    print(f"  region years now: {region['years'][0]}-{region['years'][-1]}")
    print(f"  IBS years now: {sorted(IBS.keys())[0]}-{sorted(IBS.keys())[-1]}")
    print("\nNext: run fix_subnational -> recompute_enclaves -> recompute_summary -> export_dataset")



def extend_age_sex():
    """Extend foreign_residents_by_age_sex back to 2009-2013 by parsing the
    '국적 및 연령별 등록외국인 현황' yearbook tables. 2008 is skipped because its
    5-year buckets start at 0-5 (not 0-4), incompatible with the 13-band convention.

    Source layout 2009-2013:
      col with header '국적'   -> Korean country name
      col with header '연령'   -> English country name (header label is misleading)
      col with header '총계'   -> Grand-Total (single integer)
      col with header '성별'   -> sex marker, newline-stacked (e.g. '남(M)
    여(F)')
      col with header '합계'   -> total, newline-stacked T/M/F values
      cols with '~세' / '세'   -> age band columns, newline-stacked values

    The newline stacking varies: total/aggregate rows have T/M/F, country rows
    typically have just M/F. T is computed as M+F.

    Writes (in place):
      03_cleaned_data/age_long.csv (append 2009-2013 rows)
      site/data/age.json (add 2009-2013 to data and extend years list)
    """
    warnings.filterwarnings("ignore")

    from kird import ROOT  # noqa: E402
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")
    PROC = os.path.join(ROOT, "03_cleaned_data")
    RAW = os.path.join(ROOT, "01_raw_data")

    AGE_BANDS = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34',
                 '35-39', '40-44', '45-49', '50-54', '55-59', '60+']

    # Aggregate-row markers (region groupings, totals) to skip
    SKIP_NAMES = {"총계", "총합계", "아시아주계", "아시아 주계", "북아메리카주계",
                  "남아메리카주계", "아메리카주계", "유럽주계", "오세아니아주계",
                  "아프리카주계", "기타주계", "중남미", "남아메리카주", "북아메리카주",
                  "북미주계", "남미주계", "중남미주계", "오세아니아 주계",
                  "유럽 주계", "아프리카 주계", "북미 주계", "남미 주계",
                  "Asia", "Europe", "Oceania", "Africa", "Americas", "Others",
                  "Grand-Total", "Sub-Total", "Total", "Korean Diaspora",
                  "한국계 외국인주계", "기타 주계"}


    def norm_band(h):
        """Convert source band labels ('0~4세', '5 - 9세', '60세 이상') to canonical."""
        s = str(h).split("\n")[0].strip()
        if not s: return None
        s2 = s.replace(" ", "").replace("세", "")
        m = re.match(r"(\d+)[~\-](\d+)", s2)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        if "이상" in s or "+" in s2:
            m2 = re.match(r"(\d+)", s2)
            if m2:
                return f"{m2.group(1)}+"
        return None


    def split_lines(cell):
        """Parse newline-stacked numeric cell. Returns list of ints."""
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            return []
        out = []
        for line in str(cell).split("\n"):
            s = line.replace(",", "").strip()
            if not s:
                continue
            try:
                out.append(int(float(s)))
            except Exception:
                pass
        return out


    def parse_year(path, year):
        df = pd.read_excel(path, header=None)
        # find header row by presence of '국적' and '성별'
        hr = None
        for r in range(min(8, df.shape[0])):
            row = [str(c) for c in df.iloc[r].tolist()]
            if any("국적" in c for c in row) and any("성별" in c for c in row):
                hr = r; break
        if hr is None:
            return []
        header = df.iloc[hr].tolist()
        # Locate columns by header keyword
        cols = {"country_ko": None, "country_en": None, "total": None,
                "sex": None, "sum": None}
        age_cols = {}  # col_idx -> canonical band
        for c, v in enumerate(header):
            s = str(v) if pd.notna(v) else ""
            if "국적" in s and cols["country_ko"] is None: cols["country_ko"] = c
            elif "연령" in s and cols["country_en"] is None: cols["country_en"] = c
            elif "총계" in s or "Grand-Total" in s: cols["total"] = c
            elif "성별" in s: cols["sex"] = c
            elif "합계" in s or "Total" in s and cols["sum"] is None: cols["sum"] = c
            else:
                band = norm_band(s)
                if band: age_cols[c] = band
        if not age_cols or cols["sex"] is None or cols["country_ko"] is None:
            return []

        rows = []
        for r in range(hr + 1, df.shape[0]):
            ck = str(df.iat[r, cols["country_ko"]]).split("\n")[0].strip() if pd.notna(df.iat[r, cols["country_ko"]]) else ""
            if not ck or ck in SKIP_NAMES:
                continue
            # English country name (or fallback)
            ce = ""
            if cols["country_en"] is not None and pd.notna(df.iat[r, cols["country_en"]]):
                ce = str(df.iat[r, cols["country_en"]]).split("\n")[0].strip()
            # Determine sex order by reading sex column
            sex_cell = df.iat[r, cols["sex"]] if pd.notna(df.iat[r, cols["sex"]]) else ""
            sex_lines = [s.strip() for s in str(sex_cell).split("\n") if s.strip()]
            # Map sex marker to gender code
            sex_order = []
            for sl in sex_lines:
                if sl in ("계(T)", "T", "(T)", "총계", "Total", "Grand-Total", "계"):
                    sex_order.append("T")
                elif sl in ("남(M)", "(M)", "M", "남", "남성", "Male"):
                    sex_order.append("M")
                elif sl in ("여(F)", "(F)", "F", "여", "여성", "Female"):
                    sex_order.append("F")
            if not sex_order:
                # default: assume M, F if exactly 2 values per cell, or T,M,F if 3
                continue
            # Read each age column
            for c, band in age_cols.items():
                vals = split_lines(df.iat[r, c])
                if len(vals) != len(sex_order):
                    continue
                mf = dict(zip(sex_order, vals))
                m = mf.get("M", 0); f = mf.get("F", 0); t = mf.get("T", m + f)
                if t == 0 and m == 0 and f == 0:
                    continue
                rows.append((year, ck, ce, "T", band, t))
                if m: rows.append((year, ck, ce, "M", band, m))
                if f: rows.append((year, ck, ce, "F", band, f))
        return rows


    # Run for 2009-2013
    all_rows = []
    for y in range(2009, 2014):
        # the yearbooks live at 01_raw_data/출입국통계연보/<year>_출입국통계연보/
        YB = os.path.join(RAW, "출입국통계연보")
        g = glob.glob(os.path.join(YB, f"{y}_*/2장_Ⅲ_2.국적및연령별*등록*"))
        if not g:
            g = glob.glob(os.path.join(YB, f"{y}_*/*_2장_Ⅲ_2.국적및연령별*등록*"))
        if not g:
            print(y, "FILE NOT FOUND"); continue
        rows = parse_year(g[0], y)
        n_countries = len({r[1] for r in rows})
        total_T = sum(r[5] for r in rows if r[3] == "T")
        print(f"{y}: {len(rows)} rows, {n_countries} countries, sum T={total_T:,}  [{os.path.basename(g[0])[:38]}]")
        all_rows.extend(rows)

    # Validation: sum of country T vs by_visa registered national for the year
    print("\nValidation (sum_T vs national registered):")
    dd = json.load(open(os.path.join(SITE, "data.json"), encoding="utf-8"))
    reg_all = dd["populations"]["reg"]["data"]["ALL"]
    for y in range(2009, 2014):
        nat = sum(reg_all.get(str(y), {}).values())
        tot = sum(r[5] for r in all_rows if r[0] == y and r[3] == "T")
        pct = 100 * (tot - nat) / nat if nat else 0
        print(f"  {y}: national={nat:,}  sum_T={tot:,}  ({pct:+.2f}%)")

    # Append to age_long.csv (dedup just in case)
    csv = os.path.join(PROC, "age_long.csv")
    existing = pd.read_csv(csv)
    new = pd.DataFrame(all_rows, columns=["year", "country", "country_en", "gender", "age_group", "n"])
    combined = pd.concat([existing[~existing.year.isin(range(2009, 2014))], new], ignore_index=True)
    combined = combined.sort_values(["year", "country", "gender", "age_group"])
    combined.to_csv(csv, index=False)
    print(f"\nappended to {csv} (now {len(combined):,} rows, was {len(existing):,})")

    # Update site/data/age.json
    age_json = os.path.join(SITE, "age.json")
    aj = json.load(open(age_json, encoding="utf-8"))
    for y in range(2009, 2014):
        aj["data"].setdefault(str(y), {})
        yr_rows = [r for r in all_rows if r[0] == y]
        for (_, ck, _, g, band, n) in yr_rows:
            if g not in ("M", "F"):
                continue  # T written below from M+F to match the 2014+ schema
            aj["data"][str(y)].setdefault(ck, {})
            aj["data"][str(y)][ck].setdefault(band, {})
            aj["data"][str(y)][ck][band][g] = n
        # Fill T = M + F per band so the JSON schema is uniform with 2014-2024
        # (dashboard JS reads .T directly).
        for ck, bands in aj["data"][str(y)].items():
            for band, cell in bands.items():
                cell["T"] = (cell.get("M") or 0) + (cell.get("F") or 0)
    aj["years"] = sorted(set(aj.get("years", []) + list(range(2009, 2014))))
    json.dump(aj, open(age_json, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"updated {age_json}: years now {aj['years'][0]}-{aj['years'][-1]}")


if __name__ == "__main__":
    add_lisa(build_adjacency())
    parse_sido_2006_2013()
    add_sido_diversity()
    build_undocumented()
    build_national_language()
    merge_country_names()
    build_visa_sigungu()
    add_refugee_language()
    extend_sigungu_nationality()
    merge_sigungu_nationality()
    extend_age_sex()
