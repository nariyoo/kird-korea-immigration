"""Everything that extends the parsed base before reconciliation.

The parser writes one year per yearbook on that yearbook's own terms. This step
turns that into the panel: local Moran clusters onto every district-year, the
province series back to 2006 with its diversity columns, the national series
(undocumented residents, national language demand), one label per country with
the language series recomputed on the merged names, the district-by-visa panel,
refugee language demand, the 2008-2013 district backfill out of the pre-2014
table family, and the nationality x age x sex table on both population bases
(registered 2009-, staying 2011-).

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

    The 2006 and 2007 tables (국적 및 지역별) name five nationalities and an Other
    column per province, with no district rows. They are also written out whole,
    Other included, to 03_cleaned_data/sido_nationality_2006_2007.csv, which 08
    releases as the 2006-2007 rows of nationality_by_sido (1라운드 수정, 2026-09-26:
    the province split the yearbook prints was carried nowhere, though summary_by_sido
    builds its 2006-2007 indices on it). The 2006 province rows print each cell as
    (거주)/(기타), two lines with no 계 line; the parser read the first line only, so
    the 2006 province indices were computed on the 거주 residents alone (Seoul's
    Americans counted 36 of 11,890). A cell whose row prints no 계 line is now the
    sum of its lines.
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

    def num_sum(x):
        tot = 0
        for part in str(x).split("\n"):
            s = part.replace(",", "").strip()
            try: tot += int(float(s))
            except: pass
        return tot

    def unreadable(x):
        """A cell that prints something other than a number, a dash or nothing (2012:
        강원도's 미얀마 cell is a backquote)."""
        s = str(x).split("\n")[0].replace(",", "").strip()
        if s in ("", "nan", "-"):
            return False
        try:
            float(s)
            return False
        except ValueError:
            return True

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
        """Find (header_row, region_col, total_col, {nat_col: name}); the Other
        column, and the 구분 column that says what a stacked cell holds, are kept
        on the function as .other / .marker for the caller."""
        header_info.other = header_info.marker = None
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
                        if nm in ("기타", "Others", "기타(Others)") and header_info.other is None:
                            header_info.other = c
                        if nm == "구분":
                            header_info.marker = c
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
        oc, mc = header_info.other, header_info.marker
        out = {}
        if not summode:
            for rr in range(hr + 1, df.shape[0]):
                sd = norm_sido(df.iloc[rr, rc])
                if not sd or sd in out: continue
                tval = num(df.iloc[rr, tc])
                if tval > 0:
                    # A row whose 구분 cell lists no 계 line (2006: "(거주)\n(기타)")
                    # stacks the parts of the count, so the count is their sum; with
                    # a 계 line (the national row) or no stacking, the first line.
                    mk = str(df.iloc[rr, mc]) if mc is not None else ""
                    parts = (mc is not None and "\n" in mk
                             and not mk.split("\n")[0].strip().startswith("계"))
                    cell = num_sum if parts else num
                    rec = {"_total": tval}
                    bad = []
                    for c, nm in nats.items():
                        v = cell(df.iloc[rr, c])
                        if v > 0: rec[nm] = rec.get(nm, 0) + v
                        elif unreadable(df.iloc[rr, c]): bad.append(nm)
                    if oc is not None:
                        rec["_other"] = cell(df.iloc[rr, oc])
                        # One cell of the row the parser cannot read is the printed
                        # total less the other nationalities and Other: 2012 강원도
                        # prints a backquote for 미얀마, whose district lines add up to
                        # the 21 that recovers (3라운드 대조, 2026-09-27).
                        if len(bad) == 1:
                            rest = (tval - rec["_other"]
                                    - sum(v for k, v in rec.items() if not k.startswith("_")))
                            if rest > 0:
                                rec[bad[0]] = rest
                                print(f"    {os.path.basename(path)[:4]}: {sd} {bad[0]} "
                                      f"cell unreadable, recovered as {rest:,} from the total")
                    out[sd] = rec
            # 연기군 was abolished on 2012-07-01 and its whole territory became
            # 세종특별자치시, but the 2012 and 2013 editions still print a residual
            # 연기군 line inside 충청남도's block (89 and 13 people) and count it in
            # 충청남도's 소계. It is the same ground as 세종, and the district files
            # already carry it in 세종시 (03 merge_sigungu_nationality maps 연기군 to
            # 세종시), as do the province files built from them. Move it here too, so
            # summary_by_sido's 세종 equals its one district in every year (it was
            # 2,271 against 2,360 in 2012 and 2,462 against 2,475 in 2013). The
            # national total does not move. 2026-09-26 (4차 대조).
            if "세종특별자치시" in out and "충청남도" in out:
                cur = None
                for rr in range(hr + 1, df.shape[0]):
                    sd = norm_sido(df.iloc[rr, rc])
                    if sd:
                        cur = sd
                    if cur != "충청남도":
                        continue
                    sg = str(df.iloc[rr, rc + 1]).split("\n")[0].strip()
                    if sg != "연기군":
                        continue
                    tval = num(df.iloc[rr, tc])
                    if tval <= 0:
                        continue
                    src, dst = out["충청남도"], out["세종특별자치시"]
                    src["_total"] -= tval
                    dst["_total"] += tval
                    for c, nm in nats.items():
                        v = num(df.iloc[rr, c])
                        if v > 0:
                            src[nm] = src.get(nm, 0) - v
                            if src[nm] <= 0:
                                del src[nm]
                            dst[nm] = dst.get(nm, 0) + v
                    if oc is not None:
                        # the line's Other cell moves with it (the province indices
                        # count Other as their residual bin since 2026-09-27)
                        ov = num(df.iloc[rr, oc])
                        src["_other"] = src.get("_other", 0) - ov
                        dst["_other"] = dst.get("_other", 0) + ov
                    print(f"    {os.path.basename(path)[:4]}: residual 연기군 line "
                          f"({tval:,}) moved from 충청남도 to 세종특별자치시")
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
            if oc is not None:
                rec["_other"] = rec.get("_other", 0) + num(df.iloc[rr, oc])
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
    early_rows = []         # the 2006-2007 province table as printed, Other included
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
            other = rec0.pop("_other", None)
            named = rec0  # the nationalities the table names
            # Every year's table is named nationalities plus an Other column that
            # together make the printed total (2008-2013 as well: checked 2026-09-27).
            if other is None or sum(named.values()) + other != ftot:
                raise SystemExit(f"{year} {sd}: the named nationalities and Other "
                                 f"({sum(named.values())} + {other}) do not add up "
                                 f"to the printed total {ftot}")
            if year <= 2007:
                # the province table is the only nationality detail these years have
                early_rows += [(year, sd, c, n) for c, n in sorted(named.items())]
                early_rows.append((year, sd, "기타", other))
            # The indices count Other as one more group, the residual bin the district
            # and national indices keep (index_base_k: the top 19 present plus one
            # residual bin). Until 2026-09-27 (3라운드 대조) the province indices of
            # 2006-2013 dropped it, so they were computed on the named nationalities
            # alone (2010 강원도: shannon_H 2.220 over 19 groups, 2.303 with the 605 in
            # Other), unlike every other level and year.
            counts = dict(named)
            if other:
                counts["기타"] = other
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
    ep = pd.DataFrame(early_rows, columns=["year", "sido", "country", "n"])
    if sorted(ep["year"].unique().tolist()) != [2006, 2007]:
        raise SystemExit("the 2006-2007 province table was not read for both years")
    ep.to_csv(os.path.join(ROOT, "03_cleaned_data", "sido_nationality_2006_2007.csv"),
              index=False, encoding="utf-8-sig")
    print("wrote sido_nationality_2006_2007.csv:",
          ", ".join("%d %s" % (y, format(int(n), ",")) for y, n in ep.groupby("year")["n"].sum().items()))



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

    # 2014-2018년판은 「남미주계」와 「오세아니아주계」와 「기타계」를 쓰는데 이
    # 표에 그 셋이 없어서 **다섯 해 내내 두세 줄이 조용히 버려지고 있었다**
    # (2014년 대륙 합이 총계보다 1,645 적었다). 화면이 최신 해만 싣고 있어서
    # 눈에 띌 자리가 없었다. 아래 `by_continent` 합 관문이 이제 그것을 막는다.
    CONTI = {"아시아주": "아시아", "아시아주계": "아시아", "북아메리카주": "북아메리카", "북미주계": "북아메리카",
             "남아메리카주": "남아메리카", "중남미주계": "남아메리카", "남미주계": "남아메리카",
             "유럽주": "유럽", "구주계": "유럽",
             "유럽주계": "유럽", "아프리카주": "아프리카", "아프리카주계": "아프리카",
             "오세아니아주": "오세아니아", "대양주계": "오세아니아", "오세아니아주계": "오세아니아",
             "기타": "기타", "기타계": "기타", "신원미상": "기타",
             # 2016년판은 「무  국  적」(사이에 공백)을 한 줄로 싣는다.
             # 79명이라 대륙 합이 총계보다 그만큼 적었다.
             "무국적": "기타", "국적불명": "기타"}

    def _sq(x):
        """줄 이름의 공백을 지운다. 「무  국  적」처럼 글자 사이를 벌려
        놓은 해가 있다."""
        return re.sub(r"\s+", "", str(x))

    CONTI_EN = {"아시아": "Asia", "북아메리카": "N. America", "남아메리카": "S. America",
                "유럽": "Europe", "아프리카": "Africa", "오세아니아": "Oceania", "기타": "Other"}

    def vcode(col):
        """Extract a normalized visa code like B1, C3, E9 from a column header.

        The residual column (기타 / Others) carries no code and was dropped, so
        by_visa summed 6,466 short of its own total in 2024 and similarly in
        every year from 2020. It is returned as ETC, the code the rest of the
        project already uses for a residual status.
        """
        s = str(col)
        # 글자를 A-H 로 잡고 있었다. 연보에 **관광상륙(T-1)** 칸이 있어서
        # 2015년과 2016년에 한 명씩이 조용히 버려졌다. 자격 합이 총계보다
        # 1 적었고, 화면이 상위 열 개만 실어서 드러날 자리가 없었다.
        m = re.search(r"([A-Z])\s*-?\s*(\d{1,2})", s)
        if m:
            return m.group(1) + m.group(2)
        if "소계" in s or "합계" in s or "총" in s:
            return None
        if re.match(r"\s*(기타|others?)", s, re.I):
            return "ETC"
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
        # 2019-2024년판은 대륙 이름을 「총계」 줄에만 적고 남성·여성 줄은 비워 둔다
        # (병합 셀). 채우지 않으면 아래의 「총합계 + 남성」이 한 번도 맞지 않아 전국
        # 남녀가 2019-2024년 내내 0으로 남았다(화면 첫 쪽 표가 0을 실었다). 2026-09-25.
        df[c_cont] = df[c_cont].ffill()
        vmap = {c: vcode(c) for c in cols[3:] if vcode(c)}
        rec = {"total": 0, "male": 0, "female": 0, "by_visa": {}, "by_continent": {}}
        cm = cf = 0
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
            elif sex == "남성" and cont in CONTI:
                cm += num(r[c_tot])
            elif sex == "여성" and cont in CONTI:
                cf += num(r[c_tot])
        # 2019년판에는 전국 남녀 줄이 없다. 대륙 줄을 더한다.
        if not rec["male"] and not rec["female"]:
            rec["male"], rec["female"] = cm, cf
        if rec["male"] + rec["female"] != rec["total"]:
            raise SystemExit("남녀 합 %d 이 총계 %d 과 다르다 (%s)"
                             % (rec["male"] + rec["female"], rec["total"], f))
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
            if _sq(nat_raw) in CONTI:
                rec["by_continent"][CONTI[_sq(nat_raw)]] = num(r[c_tot])
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
                vs = sum(rec["by_visa"].values())
                if vs != rec["total"]:
                    raise SystemExit(
                        "%d: 자격 합 %d 이 총계 %d 과 %+d 다르다. 연보의 칸 "
                        "이름에서 코드를 못 얻었을 수 있다" % (y, vs, rec["total"],
                                                    vs - rec["total"]))
                cs = sum(rec["by_continent"].values())
                gap = cs - rec["total"]
                # 2014년판은 연보 제 대륙 줄의 합이 제 총계보다 1 많다
                # (198,568+3,727+1,059+1,872+587+2,851+115 = 208,779 대
                # 208,778). 원본의 어긋남이므로 그대로 싣고 소리만 낸다.
                # 몇 줄이 통째로 빠지면 차이가 천 단위가 되므로 거기서 멈춘다.
                if abs(gap) > 2:
                    raise SystemExit(
                        "%d: 대륙 합 %d 이 총계 %d 과 %+d 다르다. 연보가 쓰는 "
                        "대륙 이름이 CONTI 에 없을 수 있다 (%s)"
                        % (y, cs, rec["total"], gap, sorted(rec["by_continent"])))
                if gap:
                    print("  %d: 대륙 합이 총계와 %+d (연보 원본의 어긋남)" % (y, gap))
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




def build_undocumented_duration():
    """Parse the duration-of-overstay table (연보 6장 Ⅰ_2) into undocumented.json.

    The status-on-entry table (Ⅰ_1) was the only one read. This one says **how
    long** each person has been out of status, and from 2014 on, when the
    yearbook dropped the nationality rows, it is the most informative axis the
    source still publishes. It also reaches back to 2010, four years earlier
    than the status table.

    The buckets are disjoint despite the "이하" wording: 「2개월이하」 means more
    than one month and at most two. They sum to the year's grand total exactly,
    in every year from 2010 to 2025, which is the check below.

    Three layouts:
    - 2019-2025  [대륙, 성별, 총합계, <bucket cols>], one row per sex
    - 2014-2018  the same but every cell holds the three sexes joined by newlines
    - 2010-2013  as 2014-2018

    Only the national grand-total row is kept; the page does not use the
    continent split of this table.
    """
    import glob as _glob
    RAW = os.path.join(ROOT, "01_raw_data")
    OUT = os.path.join(ROOT, "05_dashboard", "data", "undocumented.json")
    if not os.path.exists(OUT):
        raise SystemExit("run build_undocumented() first: %s" % OUT)

    def num(x):
        s = str(x).replace(",", "").strip()
        if not s or s == "nan":
            return 0
        try:
            return int(float(s))
        except Exception:
            return 0

    YB = os.path.join(RAW, "출입국통계연보", "*")
    files = {}
    for f in (_glob.glob(os.path.join(YB, "*체류기간별 불법체류*외국인 현황.xls*"))
              + _glob.glob(os.path.join(YB, "*체류기간별_불법체류*"))):
        m = re.search(r"(20\d\d)", os.path.basename(f)) or re.search(r"(20\d\d)", f)
        if m:
            files[int(m.group(1))] = f

    BUCKET = re.compile(r"^\d+(개월|년)(이하|초과)$")
    out = {}
    for y in sorted(files):
        df = pd.read_excel(files[y], header=None)
        hdr = next((i for i in range(min(8, len(df)))
                    if any("개월이하" in str(x) for x in df.iloc[i].tolist())), None)
        if hdr is None:
            print("  %d: no header row in the duration table" % y)
            continue
        cols = [str(x).strip() for x in df.iloc[hdr].tolist()]
        cells = [(j, c) for j, c in enumerate(cols) if BUCKET.match(c)]
        row = next((r for _, r in df.iloc[hdr + 1:].iterrows()
                    if str(r[0]).strip() in ("계", "총합계", "총계")), None)
        if row is None:
            print("  %d: no grand-total row in the duration table" % y)
            continue
        # 2014-2018 join the three sexes into one cell with newlines; the first
        # line is the total. Reading the cell whole gives a number ten times too
        # big and no check would notice, so split first.
        vals = {}
        for j, c in cells:
            raw = str(row[j])
            vals[c] = num(raw.split("\n")[0] if "\n" in raw else raw)
        out[str(y)] = vals

    d = json.load(open(OUT, encoding="utf-8"))
    kept, skipped = 0, []
    for ys, rec in d["national"].items():
        v = out.get(ys)
        if not v:
            skipped.append(ys)
            continue
        s = sum(v.values())
        if s != rec["total"]:
            raise SystemExit(
                "%s: duration buckets sum to %d, the year's total is %d"
                % (ys, s, rec["total"]))
        rec["by_duration"] = v
        kept += 1
    d["duration_note_ko"] = ("칸은 서로 겹치지 않습니다. 「2개월이하」는 1개월을 "
                             "넘고 2개월까지입니다.")
    d["duration_note_en"] = ("The buckets are disjoint: 2 months or less means "
                             "over one month and up to two.")
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("duration added for %d years%s" % (
        kept, (", no table for " + ", ".join(skipped)) if skipped else ""))



def build_undocumented_country():
    """Parse 표 6-4 국가별 불법체류 외국인 현황 out of the yearbook PDF.

    **This table is not in the Excel bundle.** The yearbook ships its statistical
    tables as an Excel zip, and chapter 6 of that zip has exactly two files, by
    status on entry and by length of overstay. The narrative PDF carries four
    more, and one of them is the nationality split, every year, top ten plus a
    residual. Reading only the Excel bundle is why this project believed for a
    while that the yearbook stopped publishing nationality after 2013.

    The 2025 edition prints five years at once (2021-2025), so one PDF gives the
    whole recent panel. The extracted lines are regular:

        태국 142,677 147,481 152,265 137,035 115,851 32.4%

    The sum of the countries equals the year's grand total, which is the check.

    공공데이터포털 15112636 (법무부_불법체류 외국인 현황) carries the same table for
    2010-2022 as a CSV, and the overlapping years agree exactly; that file is the
    way to extend this back before 2021 if the longer panel is ever wanted.
    """
    import csv
    import io
    import pypdf
    RAW = os.path.join(ROOT, "01_raw_data")
    OUT = os.path.join(ROOT, "05_dashboard", "data", "undocumented.json")
    pdfs = sorted(glob.glob(os.path.join(
        RAW, "출입국통계연보", "*", "*통계연보(전체).pdf")))
    if not pdfs:
        print("no yearbook PDF; skipping the nationality table")
        return
    src = pdfs[-1]

    def num(s):
        return int(str(s).replace(",", ""))

    # 뽑아낸 글에 제어문자가 섞여 있다. 2025년판은 나라마다 둘째 수 뒤에
    # BEL()이 붙어 있어 공백으로 안 읽히고 줄이 통째로 안 걸린다.
    ctrl = re.compile("[" + "".join(chr(c) for c in list(range(0, 9)) + [11, 12] + list(range(14, 32))) + "]")

    rdr = pypdf.PdfReader(src)
    page = None
    for pg in rdr.pages:
        t = ctrl.sub(" ", pg.extract_text() or "")
        if "국가별 불법체류" in t and "합계" in t:
            page = t
            break
    if page is None:
        raise SystemExit("표 6-4 를 %s 에서 못 찾았다" % os.path.basename(src))

    # 연도는 「구분 2021년 … 2025년」 머리줄에서만 읽는다. 쪽 전체에서 긁으면
    # 바로 위 문장의 「2025년 말 기준 …」이 먼저 잡혀 차례가 뒤집힌다.
    head = next((l for l in page.split(chr(10))
                 if l.strip().startswith("구분") and "년" in l), "")
    years = re.findall(r"(20\d\d)년", head)
    if len(years) < 2:
        raise SystemExit("표 6-4 의 연도 머리줄을 못 읽었다: %r" % head)

    # 나라 줄: 이름 + 연도 수만큼의 수 + 구성비. 합계 줄도 같은 모양이다.
    row = re.compile(r"^(합계|[가-힣A-Za-z·\s]+?)\s+((?:[\d,]+\s+){%d})"
                     r"([\d.]+%%)?\s*$" % len(years))
    tot, by = {}, {}
    for line in page.split("\n"):
        m = row.match(line.strip())
        if not m:
            continue
        name = m.group(1).strip()
        vals = [num(x) for x in m.group(2).split()]
        if name == "합계":
            tot = dict(zip(years, vals))
        else:
            by[name] = dict(zip(years, vals))
    if not tot or not by:
        raise SystemExit("표 6-4 를 읽었으나 합계 %d, 나라 %d" % (len(tot), len(by)))

    # 연보 PDF 는 다섯 해만 싣는다. 그 앞 해는 공공데이터포털 15112636 이
    # 같은 표를 2010-2022년 CSV 로 싣는다(01_raw_data/공공데이터포털/… 의
    # 출처.md). 겹치는 해는 나라마다 같아야 하고, 다르면 멈춘다.
    portal = {}
    pc = os.path.join(RAW, "공공데이터포털", "법무부_불법체류 외국인 현황_20221231",
                      "법무부_국적별 불법체류 외국인 현황(2010~2022).csv")
    if os.path.exists(pc):
        rowsp = list(csv.reader(io.open(pc, encoding="utf-8")))
        names = [c.strip() for c in rowsp[0][1:]]
        for r in rowsp[1:]:
            portal[r[0].strip()] = {k: num(v) for k, v in zip(names, r[1:])
                                    if str(v).strip()}
        for y in sorted(set(portal) & set(by and years or [])):
            a = {k: v[y] for k, v in by.items() if v.get(y)}
            if a and a != portal[y]:
                raise SystemExit("%s: 포털 CSV 와 연보 PDF 가 다르다 %s"
                                 % (y, {k: (portal[y].get(k), a.get(k))
                                        for k in set(a) | set(portal[y])
                                        if portal[y].get(k) != a.get(k)}))
        print("  포털 CSV %d해와 맞대어 봤다 (겹치는 해 어긋남 0)" % len(portal))

    d = json.load(open(OUT, encoding="utf-8"))
    added = []
    for y in sorted(set(years) | set(portal)):
        pairs = [[k, v[y]] for k, v in by.items() if v.get(y)]
        src_name = "연보 PDF"
        if not pairs and y in portal:
            pairs = [[k, v] for k, v in portal[y].items() if v]
            src_name = "포털 CSV"
        s = sum(v for _, v in pairs)
        if y in tot and int(tot[y]) != s:
            raise SystemExit("%s: 나라 합 %d 이 표의 합계 %d 과 다르다"
                             % (y, s, tot[y]))
        rec = d["national"].get(y)
        if rec is None:
            continue
        if rec["total"] != s:
            raise SystemExit("%s: 나라 합 %d 이 연보 총계 %d 과 다르다"
                             % (y, s, rec["total"]))
        # 「기타」는 상위 열 나라를 뺀 나머지다. 나라가 아니므로 끝에 둔다.
        pairs.sort(key=lambda kv: (kv[0] == "기타", -kv[1]))
        rec["by_country"] = pairs
        added.append(y + ("*" if src_name == "포털 CSV" else ""))
    d["country_note_ko"] = ("연보 6장 표 6-4. 상위 열 나라와 나머지를 「기타」로 "
                            "묶은 것입니다. 엑셀 통계표에는 없고 연보 본문에만 "
                            "있습니다.")
    d["country_note_en"] = ("Yearbook ch.6 table 6-4: the ten largest "
                            "nationalities and a residual. It is in the "
                            "narrative PDF, not the Excel tables.")
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("nationality added for %s (* = 포털 CSV, 나머지는 %s)"
          % (", ".join(added), os.path.basename(src)))


def build_undocumented_age():
    """Parse 표 6-3 연령별 불법체류 외국인 현황 out of the yearbook PDF.

    Age is the one axis the yearbook publishes for this population that says
    something the visa and duration tables cannot: the people out of status are
    overwhelmingly of working age, and a third of them are in their thirties.

    **It is a single-year snapshot.** The table is printed 기준 the edition's own
    31 December, with no back years, so each edition carries exactly one column
    set. Only the 2025 PDF is in this repository, so only 2025 gets the split.
    That is a property of the source, not a gap to fill by interpolation.

    The buckets sum to the year's grand total, which is the check.
    """
    import pypdf
    RAW = os.path.join(ROOT, "01_raw_data")
    OUT = os.path.join(ROOT, "05_dashboard", "data", "undocumented.json")
    pdfs = sorted(glob.glob(os.path.join(
        RAW, "출입국통계연보", "*", "*통계연보(전체).pdf")))
    if not pdfs:
        print("no yearbook PDF; skipping the age table")
        return
    src = pdfs[-1]
    ctrl = re.compile("[" + "".join(chr(c) for c in list(range(0, 9)) + [11, 12]
                                    + list(range(14, 32))) + "]")
    rdr = pypdf.PdfReader(src)
    page = None
    for pg in rdr.pages:
        t = ctrl.sub(" ", pg.extract_text() or "")
        if "연령별 불법체류" in t and "세 이상" in t:
            page = t
            break
    if page is None:
        raise SystemExit("표 6-3 를 %s 에서 못 찾았다" % os.path.basename(src))

    # 기준 해는 제목의 「2025.12.31. 기준」에서 읽는다. 쪽 어디서나 긁으면 쪽
    # 번호나 본문의 다른 해가 먼저 잡힌다.
    ttl = next((l for l in page.split(chr(10)) if "연령별 불법체류" in l), "")
    my = re.search(r"(20\d\d)\.\s*12", ttl)
    if not my:
        raise SystemExit("표 6-3 의 기준 해를 못 읽었다: %r" % ttl)
    year = my.group(1)

    # 머리줄과 값줄이 따로 뽑혀 나온다. 「계 19세 이하 …」 다음 줄이 값이다.
    lines = [l.strip() for l in page.split(chr(10))]
    hi = next((i for i, l in enumerate(lines)
               if l.startswith("계") and "세 이상" in l), None)
    if hi is None:
        raise SystemExit("표 6-3 의 머리줄을 못 찾았다")
    labels = re.findall(r"19세 이하|\d+-\d+세|\d+세 이상", lines[hi])
    vals = []
    for l in lines[hi + 1:hi + 4]:
        vals = [int(x.replace(",", "")) for x in re.findall(r"[\d,]+", l)]
        if len(vals) == len(labels) + 1:
            break
    if len(vals) != len(labels) + 1:
        raise SystemExit("표 6-3 의 값줄을 못 읽었다: 칸 %d, 수 %d"
                         % (len(labels), len(vals)))
    tot, nums = vals[0], vals[1:]
    if sum(nums) != tot:
        raise SystemExit("표 6-3: 연령 칸 합 %d 이 계 %d 과 다르다"
                         % (sum(nums), tot))

    d = json.load(open(OUT, encoding="utf-8"))
    rec = d["national"].get(year)
    if rec is None:
        raise SystemExit("%s년이 undocumented.json 에 없다" % year)
    if rec["total"] != tot:
        raise SystemExit("%s: 연령표의 계 %d 이 연보 총계 %d 과 다르다"
                         % (year, tot, rec["total"]))
    rec["by_age"] = list(zip(labels, nums))
    d["age_note_ko"] = ("연보 6장 표 6-3. 연보가 그해 12월 31일 기준 한 해만 "
                        "싣습니다.")
    d["age_note_en"] = ("Yearbook ch.6 table 6-3. The yearbook prints one year "
                        "only, as of 31 December.")
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("age added for %s (%d buckets, %s)"
          % (year, len(nums), os.path.basename(src)))


def build_undocumented_registered():
    """Parse 표 6-5 연도별 등록외국인 중 불법체류 외국인 현황 out of the PDF.

    This is a different population from the headline count, and the difference
    matters. The headline 357,598 counts everyone out of status, most of whom
    entered visa-free or on a short-term permit and never registered. Table 6-5
    counts only people who **did** register and later fell out of status:
    128,813 of 1,604,920 registered foreigners in 2025, which is the 8.0% the
    yearbook calls 불법체류율 for this subgroup.

    Dividing the headline count by the registered total, as the ratio chart on
    the page does for the 등록 대비 line, answers a different question and gives
    22.3%. Both are defensible; they are not the same number and the page should
    carry the published one too.

    The edition prints five years at once. Two checks: 합법체류 + 불법체류 equals
    등록외국인 in every year, and 등록외국인 matches the registered series this
    repository already carries.
    """
    import pypdf
    RAW = os.path.join(ROOT, "01_raw_data")
    OUT = os.path.join(ROOT, "05_dashboard", "data", "undocumented.json")
    pdfs = sorted(glob.glob(os.path.join(
        RAW, "출입국통계연보", "*", "*통계연보(전체).pdf")))
    if not pdfs:
        print("no yearbook PDF; skipping the registered-overstay table")
        return
    src = pdfs[-1]
    ctrl = re.compile("[" + "".join(chr(c) for c in list(range(0, 9)) + [11, 12]
                                    + list(range(14, 32))) + "]")
    rdr = pypdf.PdfReader(src)
    page = None
    for pg in rdr.pages:
        t = ctrl.sub(" ", pg.extract_text() or "")
        if "등록외국인 중 불법체류" in t and "불법체류율" in t:
            page = t
            break
    if page is None:
        raise SystemExit("표 6-5 를 %s 에서 못 찾았다" % os.path.basename(src))

    head = next((l for l in page.split(chr(10))
                 if l.strip().startswith("구분") and "년" in l), "")
    years = re.findall(r"(20\d\d)년", head)
    if len(years) < 2:
        raise SystemExit("표 6-5 의 연도 머리줄을 못 읽었다: %r" % head)

    want = {"등록외국인": "reg", "합법체류": "legal", "불법체류": "undoc"}
    got = {}
    for line in page.split(chr(10)):
        line = line.strip()
        for ko, key in want.items():
            if not line.startswith(ko) or key in got:
                continue
            nums = [int(x.replace(",", ""))
                    for x in re.findall(r"\b[\d,]{4,}\b", line)]
            if len(nums) >= len(years):
                got[key] = dict(zip(years, nums[:len(years)]))
    missing = sorted(set(want.values()) - set(got))
    if missing:
        raise SystemExit("표 6-5 에서 %s 줄을 못 읽었다" % missing)

    for y in years:
        a, b, c = got["legal"][y], got["undoc"][y], got["reg"][y]
        if a + b != c:
            raise SystemExit("%s: 합법 %d + 불법 %d 이 등록외국인 %d 과 다르다"
                             % (y, a, b, c))

    # 이 저장소가 이미 싣고 있는 등록외국인 수와 맞대어 본다. 해가 어긋나면
    # 수만 단위로 벌어지므로 그것을 잡는 것이 이 검사의 목적이다.
    #
    # **똑같기를 바라면 안 된다.** 이 저장소의 등록외국인은 국적별 표를 더한
    # 것이고 그 표에는 나라 192개만 있다. 연보의 총계에는 국적불명·무국적
    # 나머지가 들어 있어서 해마다 170~200명쯤 더 크다(2025년 195명, 0.012%).
    # 그 차이는 자료 구조에서 오는 것이라 없앨 수 없다. 그래서 0.1%를 넘을
    # 때만 멈춘다 — 해를 잘못 읽으면 그 한계를 한참 넘는다.
    dat = os.path.join(ROOT, "05_dashboard", "data", "data.json")
    if os.path.exists(dat):
        reg = json.load(open(dat, encoding="utf-8"))["populations"]["reg"]["data"]["ALL"]
        gaps = []
        for y in years:
            mine = sum((reg.get(y) or {}).values())
            if not mine:
                continue
            gap = got["reg"][y] - mine
            if abs(gap) > 0.001 * got["reg"][y]:
                raise SystemExit(
                    "%s: 연보의 등록외국인 %d 과 이 저장소의 %d 이 %d 만큼 다르다"
                    % (y, got["reg"][y], mine, gap))
            gaps.append(gap)
        if gaps:
            print("  등록외국인 수를 이 저장소 값과 맞대어 봤다 "
                  "(국적불명 나머지만큼 %d~%d명 차이)" % (min(gaps), max(gaps)))

    d = json.load(open(OUT, encoding="utf-8"))
    for y in years:
        rec = d["national"].get(y)
        if rec is None:
            continue
        rec["registered"] = {"reg": got["reg"][y], "legal": got["legal"][y],
                             "undoc": got["undoc"][y],
                             "rate": round(100.0 * got["undoc"][y]
                                           / got["reg"][y], 1)}
    d["registered_note_ko"] = ("연보 6장 표 6-5. 외국인등록을 한 뒤 기간을 넘긴 "
                               "사람만 셉니다. 등록한 적 없이 초과 체류하는 "
                               "사람은 여기 들지 않습니다.")
    d["registered_note_en"] = ("Yearbook ch.6 table 6-5. It counts only people "
                               "who registered and later fell out of status, "
                               "not those who never registered.")
    json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("registered-overstay added for %s" % ", ".join(years))

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
            # The 기타 column (Others; 2013 on) holds the statuses the table does not
            # list by code, and the district rows add up to the row total only with
            # it. It carries no code, so vcode() skipped it and visa_by_sigungu fell
            # short of the table's own grand total by exactly that column: 363 in
            # 2013, 39,210 in 2020, 31,626 in 2024 (5차 대조, 2026-09-26). Its grand
            # total equals visa_national's ETC (분류외) in every year, so it takes
            # that code.
            if c not in vcols and c > 3:
                heads = [re.sub(r"\s+", "", str(x).split("\n")[0]) for x in (h_codes[c], h_alt[c])
                         if x is not None and not (isinstance(x, float) and pd.isna(x))]
                if any(h.startswith("기타") or h.lower().startswith("other") for h in heads):
                    vcols[c] = "ETC"
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
        # E-8 in the 2008-2009 editions is 연수취업, not the 계절근로 of 2021 on;
        # 01_parse_yearbooks.split_e8 carries it as E8T, and so does this panel.
        if year <= 2009:
            for rec in parsed.values():
                if "E8" in rec:
                    rec["E8T"] = rec.get("E8T", 0) + rec.pop("E8")
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
    # City lines printed beside that city's own general districts (용인시 14 in 2008,
    # 142 in 2009, 33 in 2010; 창원시 261 in 2010; 성남시, 안양시, 고양시, 천안시,
    # 청주시 1-15 in 2009-2013). They are not the city's total: the province 소계
    # and the grand total count them on top of the gu rows, to the person, in every
    # edition. They are people the yearbook places in the city and in none of its
    # gu, and they stay a row of their own under the city's name. There is no
    # resident population for such a row (the MOIS table has gu rows only), so its
    # denominator is left empty rather than given the whole city's. Until
    # 2026-09-26 (5차 대조) 04 dropped them as "city totals that duplicate the gu
    # rows", 5-294 people a year.
    residual_city = {}
    for ystr, blk in preview.items():
        for key in blk:
            sido, sg = key.split("|")
            if re.fullmatch(r".+시", sg) and any(
                    k2 != key and k2.startswith(sido + "|" + sg) and k2.endswith("구")
                    for k2 in blk):
                residual_city.setdefault(ystr, set()).add(key)
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
            if key in residual_city.get(ystr, ()):
                pop_v = None
            elif pop_v is None:
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
    """Nationality x age x sex, on the two population bases the yearbook uses.

    The yearbook publishes this cross-tabulation twice, for two populations, and
    the release carries both with a `population` column, the way
    nationality_national.csv already does:

      registered  국적(지역) 및 연령별 등록외국인 현황   2009-LAST_YEAR
                  (2장 Ⅲ-2 through the 2013 edition, 2장 Ⅱ-2 from 2014)
      stay        국적(지역) 및 연령별 체류외국인 현황   2011-LAST_YEAR
                  (2장 Ⅱ-2 in 2011-2013, 2장 Ⅰ-2 from 2014). Stay adds the
                  short-term sojourners and the F-4 residence reports to the
                  registered population, so the two bases are never mixed.

    Until 2026-09-25 the released file mixed them: 2009-2013 came from the
    registered table (this function) and 2014 on from the stay table (01's
    load_age), so the United States went from 23,990 in 2013 to 136,663 in 2014
    with no change in the population behind it.

    2008 stays out. Its edition prints the bands 0~5, 6~10, ... 56~60, 61+
    (checked again on 2026-09-25 against 2장_Ⅲ_2 of the 2008 edition), which
    cannot be folded into the 13 bands 0-4 ... 55-59, 60+. The stay table starts
    with the 2011 edition; the 2009 and 2010 editions carry only the registered
    and short-term tables.

    Three layouts:
      2009-2013  one row per nationality, T/M/F stacked in each cell with
                 newlines; country rows carry M/F only.
      2014-2018  one row per sex, the nationality on its (M) row, markers
                 (T)/(M)/(F); country rows carry M/F only.
      2019-      대륙 | 국적 | 성별 (총계/남성/여성), a 총계 row per nationality
                 from 2020. The stay table (not the registered one) also prints
                 a 제3의성 (third sex) row: one person under 오스트레일리아 in
                 2019, 3-9 a year from the 2022 edition. It is carried as gender
                 X, and T counts it.
    Where the source has no T row, T = M + F + X. Bands from 60 up fold into 60+
    if an edition ever prints them. Aggregates (continent subtotals, 계/총계) are
    dropped. The lines that hold people but name no nationality (무국적, the
    single 기타 line, 미등록국가, 미상, 국적불명, 한국) are carried as rows of their
    own, as the status tables carry them in nationality_national; until 2026-09-26
    (1라운드 수정) they were only counted for the gate below and dropped, so the
    age table fell short of nationality_national by 106-324 people a year. Zero
    cells are not written.

    Gates, all against the raw tables:
      - every row's age bands sum to the row total the table prints;
      - the parsed persons, the non-nationality lines included, equal the
        table's printed grand total, per edition and population;
      - the stay series for 2014-LAST_YEAR equals 01's age_long.csv cell by cell
        on the nationalities 01 carries, so the release and the dashboard read
        one parse.

    Writes (in place):
      03_cleaned_data/age_sex_long.csv  population, year, country, gender,
                                        age_group, n; 08 exports it
      03_cleaned_data/age_long.csv      back to what 01 wrote (stay, 2014-)
      05_dashboard/data/age.json        rebuilt from the stay series alone,
                                        2011-LAST_YEAR
    """
    warnings.filterwarnings("ignore")
    from kird import COUNTRY_CANONICAL

    SITE = os.path.join(ROOT, "05_dashboard", "data")
    PROC = os.path.join(ROOT, "03_cleaned_data")
    YB = os.path.join(ROOT, "01_raw_data", "출입국통계연보")

    BANDS = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34',
             '35-39', '40-44', '45-49', '50-54', '55-59', '60+']
    GRAND = {"계", "총계", "총합계"}
    # Rows that hold persons but are not a nationality. They are carried under the
    # label the status tables give the same line (nationality_national), so the two
    # tables can be compared line by line: every spelling of the single residual
    # line becomes 기타.
    RESID = {"기타", "기타국", "기타국가", "기타지역", "무국적", "국적불명", "미상",
             "미등록국가", "한국"}
    RESID_LABEL = {"기타국": "기타", "기타국가": "기타", "기타지역": "기타",
                   "기타계": "기타"}
    resid_label = lambda c: RESID_LABEL.get(c, c)
    RESID_OUT = {resid_label(c) for c in RESID}
    # Not nationalities. Matched after whitespace is removed.
    DROP = GRAND | RESID | {
        "소계", "합계", "Grand-Total", "Sub-Total", "무국적계",
        "아시아주계", "아시아주", "북아메리카주계", "북아메리카주", "북아메리카",
        "남아메리카주계", "남아메리카주", "남아메리카", "아메리카주계",
        "유럽주계", "유럽주", "유럽", "오세아니아주계", "오세아니아주", "오세아니아",
        "아프리카주계", "아프리카주", "아프리카", "기타주계", "기타계",
        "북아메리카계", "남아메리카계", "북미주계", "북미주", "남미주계", "남미주",
        "중남미", "중남미주계", "구소련계", "구소련", "한국계외국인주계"}
    SEX = {"계(T)": "T", "(T)": "T", "T": "T", "계": "T", "총계": "T", "총합계": "T",
           "남(M)": "M", "(M)": "M", "M": "M", "남": "M", "남성": "M",
           "여(F)": "F", "(F)": "F", "F": "F", "여": "F", "여성": "F",
           "제3의성": "X"}

    def canon(name):
        if not isinstance(name, str):
            return None
        c = re.sub(r"\s+", "", name.split("\n")[0])
        if not c or c == "nan":
            return None
        if c.startswith("(") and c.endswith(")"):
            c = c[1:-1]
        return COUNTRY_CANONICAL.get(c, c)

    def is_agg(c):
        return c in DROP or c.endswith("총계") or c.endswith("총합계")

    def band(h):
        """'0~4세', '5 - 9세', '0세~4세', '60세이상' -> canonical band. Anything
        from 60 up folds into 60+; a band that cannot be folded is marked '!'."""
        s = str(h).split("\n")[0].replace(" ", "").replace("세", "")
        m = re.match(r"^(\d+)[~∼\-](\d+)$", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
        else:
            m = re.match(r"^(\d+)(?:이상|\+)$", s)
            if not m:
                return None
            a, b = int(m.group(1)), None
        if a >= 60:
            return "60+"
        lab = "%d-%d" % (a, b) if b is not None else "%d+" % a
        return lab if lab in BANDS else "!" + lab

    def ints(cell):
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            return []
        out = []
        for line in str(cell).split("\n"):
            s = line.replace(",", "").strip()
            if s == "-":
                out.append(0)
            elif s:
                out.append(int(float(s)))
        return out

    def age_cols(header, first=0):
        cols = {i: band(v) for i, v in enumerate(header)
                if i >= first and band(v)}
        bad = sorted({b for b in cols.values() if b.startswith("!")})
        if bad:
            raise SystemExit("age bands %s do not fold into the 13 bands" % bad)
        return cols

    def parse_stacked(path, year):
        """2009-2013. Returns (rows, residual persons, printed grand total)."""
        df = pd.read_excel(path, header=None)
        hr = next(r for r in range(8)
                  if any("국적" in str(c) for c in df.iloc[r])
                  and any("성별" in str(c) for c in df.iloc[r]))
        hdr = df.iloc[hr].tolist()
        c_ko = next(i for i, v in enumerate(hdr) if "국적" in str(v))
        c_sx = next(i for i, v in enumerate(hdr) if "성별" in str(v))
        c_tot = next(i for i, v in enumerate(hdr)
                     if str(v).strip().startswith("합계"))
        ages = age_cols(hdr)
        rows, resid, grand = [], 0, None
        for r in range(hr + 1, df.shape[0]):
            c = canon(df.iat[r, c_ko])
            if not c:
                continue
            sl = [SEX[s.strip()] for s in str(df.iat[r, c_sx]).split("\n")
                  if s.strip() in SEX]
            if not sl:
                continue
            tv = dict(zip(sl, ints(df.iat[r, c_tot])))
            t_row = tv.get("T", tv.get("M", 0) + tv.get("F", 0))
            if c in GRAND:
                grand = t_row
            if is_agg(c) and c not in RESID:
                continue
            c = resid_label(c)
            acc = {}
            for i, b in ages.items():
                v = ints(df.iat[r, i])
                if len(v) != len(sl):
                    raise SystemExit("%d %s %s: %d values for %d sexes"
                                     % (year, c, b, len(v), len(sl)))
                d = dict(zip(sl, v))
                d.setdefault("T", d.get("M", 0) + d.get("F", 0) + d.get("X", 0))
                for g in ("T", "M", "F", "X"):
                    if g in d:
                        acc[(g, b)] = acc.get((g, b), 0) + d[g]
            got = sum(acc.get(("T", b), 0) for b in BANDS)
            if got != t_row:
                raise SystemExit("%d %s: bands sum to %d, the row prints %d"
                                 % (year, c, got, t_row))
            rows += [(year, c, g, b, n) for (g, b), n in acc.items()]
        return rows, resid, grand

    def parse_rows(path, year):
        """2014-. One row per sex. Returns (rows, residual persons, grand total)."""
        df = pd.read_excel(path, sheet_name=0, header=None)
        hdr = df.iloc[0].tolist()
        ages = age_cols(hdr, first=4)
        modern = str(hdr[0]).replace(" ", "") == "대륙"
        cc = 1 if modern else 0
        cur = None
        per = {}        # (country, sex) -> [row total, {band: n}]
        grand, resid, subs = {}, {}, {}
        # The trailing 기타 block (기타계, 기타, 기타 총계, 기타 | 총계) is a leaf
        # from 2020 on: 169-282 persons with nothing listed under it. In 2019 it
        # heads 무국적 / 미등록국가 / 국제연합 instead. Its own total counts as
        # residual only when nothing is listed under it.
        ETC = ("기타계", "기타", "기타총계")
        etc, etc_kids, in_etc, etc_row = {}, False, False, False
        etc_bands = {}      # the 기타 block's own rows by sex, band by band
        for r in range(1, df.shape[0]):
            c0, c1 = df.iat[r, 0], df.iat[r, cc]
            if modern:
                k0 = canon(c0) if pd.notna(c0) else None
                k1 = canon(c1) if pd.notna(c1) else None
                if k0 is not None:
                    in_etc = k0 in ETC
                # etc_row: this row is the 기타 block's own total (its 총계 row
                # or the 남성/여성 rows that continue it, whose name cells are
                # blank); a nationality listed under it ends that.
                if k1 is not None and k1 != "총계":
                    etc_row = False
                    etc_kids = etc_kids or in_etc
                elif k0 is not None or k1 == "총계":
                    etc_row = in_etc
                if k0 == "총합계" and k1 in (None, "총계"):
                    # the grand total: 총합계 | (blank) or 총합계 | 총계 (2025)
                    cur = "총합계"
                elif k1 is not None:
                    # a nationality, or a continent subtotal printed as
                    # 아시아주 | 총계 (2019, 2022-); 총계 is dropped below
                    cur = "__sub__" if k1 == "총계" else k1
                elif k0 is not None:
                    # A continent block starts with the nationality cell blank.
                    # Its 남성/여성 rows leave both name cells empty and must not
                    # inherit the previous nationality (the 2020 기타계 fault
                    # fixed in 01's load_age).
                    cur = k0
            elif pd.notna(c0):
                cur = canon(c0)
            g = SEX.get(str(df.iat[r, 2]).strip())
            if cur is None or g is None:
                continue
            v = ints(df.iat[r, 3])
            t_row = v[0] if v else 0
            if modern and etc_row:
                etc[g] = etc.get(g, 0) + t_row
                eb = etc_bands.setdefault(g, {})
                for i, b in ages.items():
                    v = ints(df.iat[r, i])
                    eb[b] = eb.get(b, 0) + (v[0] if v else 0)
                if cur == "__sub__":
                    subs[g] = subs.get(g, 0) + t_row
                continue
            if cur == "총합계" or (not modern and cur in GRAND):
                grand[g] = t_row
                continue
            if cur == "__sub__":
                subs[g] = subs.get(g, 0) + t_row
                continue
            name = cur
            if is_agg(cur):
                # In 2014-2018 기타계 is a leaf row holding the residual persons
                # (183 in 2018); from 2019 it heads a block that lists 무국적 and
                # the rest separately. A leaf that holds people is carried as a
                # row of its own (see RESID); the rest are aggregates.
                if not (cur in RESID or (not modern and cur == "기타계")):
                    continue
                name = resid_label(cur)
            slot = per.setdefault((name, g), [0, {}])
            slot[0] += t_row
            for i, b in ages.items():
                v = ints(df.iat[r, i])
                slot[1][b] = slot[1].get(b, 0) + (v[0] if v else 0)
        # The 2019 registered sheet prints no grand-total row, only the
        # continent subtotals (아시아주 | 총계 ...); their sum is its total.
        # 2014-2018 print a (T) row only for the grand total and aggregates.
        grand = grand or subs
        if etc and not etc_kids:
            # the 기타 block is a leaf (2020 on): its own rows are the residual line
            for g, t in etc.items():
                slot = per.setdefault(("기타", g), [0, {}])
                slot[0] += t
                for b, n in etc_bands.get(g, {}).items():
                    slot[1][b] = slot[1].get(b, 0) + n
        g_tot = grand.get("T", grand.get("M", 0) + grand.get("F", 0) + grand.get("X", 0)) \
            if grand else None
        # per residual row: its 총계 if printed, else M + F + X (2019's 미상 prints
        # a 여성 row alone). Nothing lands here any more; kept for the gate.
        r_tot = sum(d.get("T", d.get("M", 0) + d.get("F", 0) + d.get("X", 0))
                    for d in resid.values())
        rows = []
        for c in sorted({k[0] for k in per}):
            for g in ("T", "M", "F", "X"):
                if (c, g) in per:
                    tot, bands = per[(c, g)]
                elif g == "T":
                    tot = sum(per.get((c, s), [0])[0] for s in ("M", "F", "X"))
                    bands = {b: sum(per.get((c, s), [0, {}])[1].get(b, 0)
                                    for s in ("M", "F", "X")) for b in BANDS}
                else:
                    continue
                if sum(bands.values()) != tot:
                    raise SystemExit("%d %s %s: bands sum to %d, the row prints %d"
                                     % (year, c, g, sum(bands.values()), tot))
                rows += [(year, c, g, b, n) for b, n in bands.items()]
        return rows, r_tot, g_tot

    def find(year, pop):
        pat = {"registered": "*국적*연령별*등록외국인*",
               "stay": "*국적*연령별*체류외국인*"}[pop]
        g = [p for p in glob.glob(os.path.join(YB, "%d_*" % year, pat))
             if "단기" not in os.path.basename(p)]
        if len(g) != 1:
            raise SystemExit("%d %s: expected one age table, found %s"
                             % (year, pop, [os.path.basename(p) for p in g]))
        return g[0]

    FIRST = {"registered": 2009, "stay": 2011}
    # Where the table's printed grand total exceeds the sum of its own rows.
    # Four stay tables do this by one to four persons: 2014 prints 계 1,797,618
    # while its (M) and (F) rows add up to 1,797,614 (checked against the raw
    # sheets on 2026-09-25; the 2014-2018 editions print no sex other than (M)
    # and (F)). The rows are carried as printed; any other gap stops. 2019 was
    # listed here with one person until 2026-09-26 (1라운드 수정): that person is
    # the 제3의성 row under 오스트레일리아, which is now carried.
    KNOWN_GAP = {("stay", 2014): 4, ("stay", 2015): 3, ("stay", 2016): 2,
                 ("stay", 2018): 1}
    out = []
    print("\nnationality x age x sex, two bases:")
    for pop in ("registered", "stay"):
        for y in range(FIRST[pop], LAST_YEAR + 1):
            p = find(y, pop)
            rows, resid, grand = (parse_stacked if y <= 2013 else parse_rows)(p, y)
            tot = sum(n for (_, _, g, _, n) in rows if g == "T")
            gap = None if grand is None else grand - tot - resid
            want = KNOWN_GAP.get((pop, y), 0)
            print("  %-10s %d  %3d nationalities  T %10s + residual %5s = "
                  "printed %10s  %s  [%s]"
                  % (pop, y, len({r[1] for r in rows}), format(tot, ","),
                     format(resid, ","), format(grand or 0, ","),
                     "ok" if gap == 0 else ("known %+d" % gap if gap == want
                                            else "GAP %s" % gap),
                     os.path.basename(p)[:36]))
            if gap != want:
                raise SystemExit("%s %d: parsed %d + residual %d != printed %s"
                                 % (pop, y, tot, resid, grand))
            out += [(pop,) + r for r in rows]

    K = ["population", "year", "country", "gender", "age_group"]
    long = pd.DataFrame(out, columns=K + ["n"])
    long = long.groupby(K, as_index=False)["n"].sum()
    long = long[long["n"] != 0]
    order = {b: i for i, b in enumerate(BANDS)}
    long = (long.assign(_b=long["age_group"].map(order))
                .sort_values(["population", "year", "country", "_b", "gender"])
                .drop(columns="_b").reset_index(drop=True))

    # The stay series from 2014 must be the one 01 parsed for the dashboard, on
    # the nationalities 01 carries (01 drops the non-nationality lines; the
    # dashboard lists nationalities only).
    csv = os.path.join(PROC, "age_long.csv")
    base = pd.read_csv(csv, encoding="utf-8-sig")
    base = base[base["year"] >= 2014][["year", "country", "gender", "age_group", "n"]]
    b = (base[~base["country"].isin(RESID_OUT)]
         .groupby(["year", "country", "gender", "age_group"])["n"].sum())
    b = b[b != 0]
    s = (long[(long["population"] == "stay") & (long["year"] >= 2014)
              & ~long["country"].isin(RESID_OUT)]
         .set_index(["year", "country", "gender", "age_group"])["n"])
    j = pd.concat([b.rename("p01"), s.rename("here")], axis=1).fillna(0)
    diff = j[j["p01"] != j["here"]]
    if len(diff):
        raise SystemExit("stay 2014-: %d cells differ from 01's age_long.csv, "
                         "e.g.\n%s" % (len(diff), diff.head().to_string()))
    print("  stay 2014-%d equals 01's age_long.csv (%s nonzero cells)"
          % (LAST_YEAR, format(len(j), ",")))

    long.to_csv(os.path.join(PROC, "age_sex_long.csv"), index=False,
                encoding="utf-8-sig")
    print("  wrote age_sex_long.csv: %s rows" % format(len(long), ","))
    print(long.groupby(["year", "population"]).size().unstack(1).to_string())
    # age_long.csv is 01's stay parse. The registered 2009-2013 rows this
    # function used to append are what mixed the two bases; take them out.
    base.to_csv(csv, index=False, encoding="utf-8-sig")

    # The dashboard's age.json is labelled 체류외국인. It is rewritten here from
    # the stay series, 2011-LAST_YEAR, and nothing else. It used to carry the
    # registered 2009-2013 rows next to 01's stay rows, and 01's rows kept only
    # the last of several source classes that fold into one nationality
    # (미국 + 미국인근섬, 영국 + 영국외지민, 홍콩 + 홍콩거주난민, ...), so 38
    # country-years in 2014-2025 were wrong; 미국 2025 read T = 1. The series
    # here sums the classes. Every band is written, zeros included, so each
    # nationality's table lists all 13 bands; within a nationality the bands
    # keep the lexical order 01 wrote, which is what breaks ties when a summary
    # names the largest band.
    age_json = os.path.join(SITE, "age.json")
    aj = json.load(open(age_json, encoding="utf-8"))
    # nationalities only, as before 2026-09-26: the non-nationality lines stay out
    # of the dashboard's country lists, and T already counts the X persons
    st = long[(long["population"] == "stay") & ~long["country"].isin(RESID_OUT)]
    data = {}
    for (y, c), grp in st.groupby(["year", "country"]):
        v = {(r.age_group, r.gender): int(r.n) for r in grp.itertuples()}
        data.setdefault(str(y), {})[c] = {
            b: {g: v.get((b, g), 0) for g in ("M", "F", "T")} for b in sorted(BANDS)}
    aj["data"] = data
    aj["years"] = [int(y) for y in data]
    aj["age_groups"] = BANDS
    first, last = aj["years"][0], aj["years"][-1]
    aj["population"] = "stay"
    aj["source_ko"] = ("법무부 출입국·외국인정책 통계연보 · 국적 및 연령별 체류외국인 "
                       "(%d~%d)" % (first, last))
    aj["source_en"] = ("KIS Yearbook · Staying foreign residents by nationality "
                       "and age (%d–%d)" % (first, last))
    json.dump(aj, open(age_json, "w", encoding="utf-8"), ensure_ascii=False)
    print("  age.json: stay basis, %d-%d" % (first, last))


if __name__ == "__main__":
    add_lisa(build_adjacency())
    parse_sido_2006_2013()
    add_sido_diversity()
    build_undocumented()
    build_undocumented_duration()
    build_undocumented_country()
    build_undocumented_age()
    build_undocumented_registered()
    build_national_language()
    merge_country_names()
    build_visa_sigungu()
    add_refugee_language()
    extend_sigungu_nationality()
    merge_sigungu_nationality()
    extend_age_sex()
