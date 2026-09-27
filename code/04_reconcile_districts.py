"""District reconciliation, and every index recomputed on the reconciled set.

Each yearbook uses the district names of its own year, so a district's series
breaks wherever one was merged, split or renamed. Bucheon comes first as the one
case where the district level exists for only part of the series; the remaining
boundary changes and stray rows follow. The published counts are never altered,
only the label a row carries.

The enclaves and the national summary are then rebuilt from the reconciled
counts, every diversity index is put on a top-19-plus-residual basis so the 2013
to 2014 coverage break does not read as a change in the distribution, and the
language block is trimmed to the released top 20 per district.
"""
import json
import math
import os
import re
import warnings

import pandas as pd

from kird import cont
from kird import hhi
from kird import incl
from kird import make_record
from kird import morans_i as _morans_i
from kird import pielou
from kird import shannon
from kird import COUNTRY_LANGUAGE
from kird import COUNTRY_REGION
from kird import LANG_UNIT
from kird import language_estimate
from kird import RESIDUAL_LINES
from kird import ROOT


def consolidate_bucheon():
    """Bucheon (부천시) abolished its general districts (gu) in 2016 and re-created
    them in 2024, so the raw series lists 소사구/오정구/원미구 in 2014-2015 and 2024
    but only 부천시 in 2016-2023 (and 부천시 itself is missing in 2024). That makes
    every Bucheon trend discontinuous. This consolidates Bucheon to a single 부천시
    unit in every year (summing the gu where they exist and recomputing the diversity
    indices), and removes the gu rows, so the district trend is continuous and matches
    the map's on-the-fly aggregation.

    Edits site/data/indices.json (by_sigungu) and site/data/region.json (by_sigungu).
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")

    CR = COUNTRY_REGION

    idx = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))["data"]
    idx_doc = {"data": idx}
    full_idx = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
    region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))

    SIDO = "경기도"
    isB = lambda name: "부천" in name



    def cont_H(counts, pop):
        return cont(counts, pop)[0]





    fixed = []
    for y in full_idx["data"]["by_sigungu"]:
        recs = full_idx["data"]["by_sigungu"][y]
        bc = [r for r in recs if isB(r["sigungu"])]
        gu = [r for r in bc if r["sigungu"] != "부천시"]
        if not gu:
            continue  # 2016-2023: single clean 부천시, leave as is
        # merged nationality dict from region (gu + any stray 부천시)
        blk = region["by_sigungu"].get(y, {}).get(SIDO, {})
        merged = {}
        for k, cc in blk.items():
            if isB(k):
                for nm, v in cc.items():
                    merged[nm] = merged.get(nm, 0) + v
        total_pop = sum((r.get("total_pop") or 0) for r in gu) or None
        foreign_total = sum(merged.values())
        H = shannon(merged); S = len(merged)
        rec = {"sido": SIDO, "sigungu": "부천시", "foreign_total": foreign_total,
               "total_pop": total_pop,
               "foreign_share_pct": round(100 * foreign_total / total_pop, 2) if total_pop else None,
               "shannon_H": H, "shannon_H_inclusive": incl(merged, total_pop),
               "continent_H": cont_H(merged, total_pop), "HHI": hhi(merged),
               "evenness": pielou(H, S), "n_nationalities": S}
        # carry continent_shares if present on a gu record's schema (optional, skip)
        full_idx["data"]["by_sigungu"][y] = [r for r in recs if not isB(r["sigungu"])] + [rec]
        # region: collapse to single 부천시
        if blk:
            for k in [k for k in blk if isB(k)]:
                del blk[k]
            blk["부천시"] = merged
        fixed.append((y, foreign_total, total_pop))

    json.dump(full_idx, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(region, open(os.path.join(SITE, "region.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("consolidated Bucheon for years:", [f[0] for f in fixed])
    for y, f, p in fixed:
        print(f"  {y}: 부천시 foreign={f:,} pop={p:,} share={round(100*f/p,2) if p else None}")
    # verify no gu remain anywhere
    rem = {y: [r["sigungu"] for r in full_idx["data"]["by_sigungu"][y] if isB(r["sigungu"])]
           for y in full_idx["data"]["by_sigungu"]}
    print("remaining 부천 entries per year:", {y: v for y, v in rem.items() if v != ["부천시"]})



def fix_subnational():
    """Clean up subnational (sigungu) administrative-transition artifacts in
    indices.json / region.json so every district series is continuous and matches
    the geojson labels:

      1. 화성시 2014 — parser grabbed the wrong row (1,796 vs the real 화성시 계 = 29,968);
         re-parse the correct row from the 2014 source.
      2. 인천 남구 -> 미추홀구 (renamed 2018); merge into 미추홀구 (geojson uses 미추홀구).
      3. 군위군 경상북도 -> 대구광역시 (transferred 2023); the geojson uses 대구광역시|군위군,
         so relabel all years to 대구 for a continuous series.
      4. Fold the residual lines of abolished or renamed districts (마산시, 진해시,
         연기군, 청원군, 여주군, 당진군, 포천군, 화성시 동부출장소) into their
         successor, then remove the old names. A line printed under a bare city name
         beside that city's gu (수원시, 용인시, 창원시 from 2010, ...) is kept as a
         row of its own (5차 대조).
      (부천시 was consolidated earlier by consolidate_bucheon.py.)

    Then recompute the indices for every changed district and rebuild the per-sigungu
    language demand from the corrected nationality counts (keyed "sido|sigungu").
    """
    warnings.filterwarnings("ignore")

    from kird import cont, hhi, incl, make_record, pielou, shannon
    from kird import COUNTRY_LANGUAGE, COUNTRY_REGION
    from kird import ROOT  # noqa: E402
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")
    RAW = os.path.join(ROOT, "01_raw_data")

    CR, CLG = COUNTRY_REGION, COUNTRY_LANGUAGE

    full = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
    idx = full["data"]
    region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))
    RBS = region["by_sigungu"]
    IBS = idx["by_sigungu"]



    def irec(year, sido, sigungu):
        for r in IBS[year]:
            if r["sido"] == sido and r["sigungu"] == sigungu: return r
        return None

    log = []

    # ---------- 1) 화성시 2014 re-parse ----------
    f14 = os.path.join(RAW, "출입국통계연보", "2014_출입국통계연보", "14_2장_Ⅱ_3.지역 및 국적_지역별 등록외국인 현황.xlsx")
    df = pd.read_excel(f14, header=None)
    header = [str(x).split("\n")[0] for x in df.iloc[0].tolist()]
    from kird import COUNTRY_CANONICAL
    # canonical names, as every other district row has them by now (영국외지민 is
    # 영국, and so on); the raw header alone put a second UK label on 화성시 2014.
    # Every column that holds people is read, the ones that name no nationality
    # (무국적, 미등록국가, 기타) included, as 01's load_region_country reads them
    # (2026-09-26, final audit).
    ccols = {c: COUNTRY_CANONICAL.get(re.sub(r"\s+", "", header[c]), re.sub(r"\s+", "", header[c]))
             for c in range(4, df.shape[1])
             if re.search(r"[가-힣]", str(header[c])) and re.sub(r"\s+", "", header[c]) not in ("계", "총계")}
    # The 2014 table prints 화성시 동부출장소 (1,709) as a row of its own beside
    # 화성시 (29,968), and 경기도's 소계 and the grand total, which equals the national
    # status table to the person, count both: the sub-office is NOT inside the city
    # row that year. Until 2026-09-26 (4차 대조) only the city row was read and the
    # 1,709 were lost. Read both and add them.
    hw_rows = [r for _, r in df.iterrows()
               if str(r.iloc[1]).strip().replace(" ", "") in ("화성시", "화성시동부출장소")
               and str(r.iloc[2]).strip() in ("계", "총계")]
    if hw_rows:
        nat = {}
        for r_ in hw_rows:
            for c, nm in ccols.items():
                v = r_.iloc[c]
                try: v = int(float(str(v).replace(",", "")))
                except: v = 0
                if v > 0: nat[nm] = nat.get(nm, 0) + v
        RBS["2014"]["경기도"]["화성시"] = nat
        rec = irec("2014", "경기도", "화성시")
        pop = rec.get("total_pop") if rec else None
        new = make_record("경기도", "화성시", nat, pop, rec.get("lisa") if rec else None)
        IBS["2014"] = [x for x in IBS["2014"] if not (x["sido"] == "경기도" and x["sigungu"] == "화성시")] + [new]
        log.append(f"화성시 2014: foreign {rec['foreign_total'] if rec else '?'} -> {new['foreign_total']:,} (share {new['foreign_share_pct']}%)")

    # ---------- 2) 인천 남구 -> 미추홀구 (merge per year) ----------
    for y in IBS:
        rblk = RBS.get(y, {}).get("인천광역시", {})
        if "남구" in rblk:
            merged = dict(rblk.get("미추홀구", {}))
            for nm, v in rblk["남구"].items(): merged[nm] = merged.get(nm, 0) + v
            rblk["미추홀구"] = merged
            del rblk["남구"]
            nam = irec(y, "인천광역시", "남구"); mic = irec(y, "인천광역시", "미추홀구")
            pop = (mic or nam or {}).get("total_pop")
            lisa = (mic or nam or {}).get("lisa")
            new = make_record("인천광역시", "미추홀구", merged, pop, lisa)
            IBS[y] = [r for r in IBS[y] if not (r["sido"] == "인천광역시" and r["sigungu"] in ("남구", "미추홀구"))] + [new]
            log.append(f"미추홀구 {y}: merged 남구 -> {new['foreign_total']:,}")

    # ---------- 3) 군위군 경상북도 -> 대구광역시 (relabel) ----------
    for y in IBS:
        rgb = RBS.get(y, {}).get("경상북도", {})
        if "군위군" in rgb:
            RBS[y].setdefault("대구광역시", {})["군위군"] = rgb.pop("군위군")
            for r in IBS[y]:
                if r["sido"] == "경상북도" and r["sigungu"] == "군위군":
                    r["sido"] = "대구광역시"
            log.append(f"군위군 {y}: 경상북도 -> 대구광역시")

    # ---------- 3b) 세종특별자치시: a single self-governing city with no sub-districts.
    # build_dashboard emits it only as a '총계'/'0' artifact, so it was lost from the
    # subnational panels. Relabel it to a real single district (세종시) and compute its
    # record from the nationality counts so the indices/language/region panels resolve.
    def _sido_pop(year, sido):
        for s in idx.get("by_sido", {}).get(year, []):
            if s["sido"] == sido:
                return s.get("total_pop")
        return None

    for y in IBS:
        blk = RBS.get(y, {}).get("세종특별자치시")
        if not blk:
            continue
        nat = next((blk[kk] for kk in ("총계", "총합계", "계", "세종시", "0") if kk in blk), None)
        if not nat:
            continue
        # A year can carry more than one alias of the same Sejong row (2021 has both
        # '총계' and '0', the latter from the 남성/여성 rows whose 시군구 cell is a
        # literal 0). They are duplicates of one district, so keep the first and drop
        # every other alias — popping only the first left the rest in place and
        # double-counted Sejong in the region-derived national total.
        blk["세종시"] = nat
        for kk in ("총계", "총합계", "계", "0"):
            blk.pop(kk, None)
        rec0 = irec(y, "세종특별자치시", "0") or irec(y, "세종특별자치시", "세종시")
        pop = _sido_pop(y, "세종특별자치시") or (rec0.get("total_pop") if rec0 else None)
        new = make_record("세종특별자치시", "세종시", blk["세종시"], pop, "ns")
        IBS[y] = [r for r in IBS[y] if r["sido"] != "세종특별자치시"] + [new]
        log.append(f"세종시 {y}: single-district record (foreign {new['foreign_total']:,}, share {new['foreign_share_pct']}%)")
    region.setdefault("sigungu_en", {}).pop("세종특별자치시|0", None)
    region["sigungu_en"]["세종특별자치시|세종시"] = "Sejong-si"

    # ---------- 4) remove strays / artifacts ----------
    # sub-office lines and pre-promotion 군 / 시 transition rows, each already folded
    # into its successor above (nothing here is a duplicate: every one of these
    # lines is counted once in its province's 소계, on top of the rows beside it). Some are
    # preserved for years before the administrative reorganization so the figure
    # layer can color the post-reorg child polygons with the pre-reorg parent
    # value (e.g., the five Changwon gu's 2009 colors come from 창원시 / 마산시 /
    # 진해시 totals).
    STRAYS = [
        # (sido, sigungu, remove_from_year). Every name here is folded into its
        # successor below before it is removed, so removing it loses nobody.
        ("경상남도", "마산시", 2010),   # merged July 2010 → keep 2008-2009 as parent
        ("경상남도", "진해시", 2010),   # merged July 2010 → keep 2008-2009 as parent
        ("충청남도", "연기군", 2012),   # became Sejong 2012 → keep 2008-2011
        ("충청북도", "청원군", 2014),   # absorbed by Cheongju 2014 → keep 2008-2013
        ("경기도", "여주군", 2008), ("경기도", "포천군", 2008),
        ("경기도", "화성시동부출장소", 2008),
        ("충청남도", "당진군", 2008),
    ]
    # 2026-09-26 (5차 대조): 수원시, 용인시, 고양시, 성남시, 안양시, 천안시, 청주시 and,
    # from 2010, 창원시 are no longer strays. The line the yearbook prints under the
    # bare city name beside that city's own gu rows is never the city's total: in
    # every district table from 2008 to 2024 the province 소계 equals the sum of all
    # its lines with the city line included (2010: 경상남도 57,718 with 창원시 261;
    # 2009: 경기도 266,808 with 용인시 142). Removing it lost 5-294 people a year in
    # 2008-2013 and 3 in 2014-2015. It stays a district row under the city's name,
    # with no resident population.
    # Residual lines of abolished districts in the 2014+ tables. Several editions
    # still print a line under a district that no longer exists, and those people
    # are real registrations on ground that now belongs to one successor: 연기군 in
    # 2014 (11, now 세종시) and 청원군 in 2014, 2015, 2016 and 2019 (1,798 / 74 /
    # 665 / 118, absorbed into 청주 in July 2014). The STRAYS list below dropped
    # them, so the district file fell short of the yearbook's own table total by
    # that much, while visa_by_sigungu (08's _RENAMES) and the 2008-2013 block
    # (03's REMAP) already carried the same lines on the successor. Fold them the
    # same way here, before the strays go. (당진군 and 여주군, whose names the parser
    # maps to 당진시 and 여주시, are added there since the same date; they stay in
    # the list in case a line arrives under the old name.) 2026-09-26 (4차 대조).
    FOLD = {("충청남도", "연기군"): ("세종특별자치시", "세종시"),
            ("충청북도", "청원군"): ("충청북도", "청주시 청원구"),
            ("충청남도", "당진군"): ("충청남도", "당진시"),
            ("경기도", "여주군"): ("경기도", "여주시")}
    # 화성시동부출장소 is the same kind of line in every edition that prints it
    # (2008-2013 here; 2014 is read in step 1): 경기도's 소계 counts it on top of
    # the 화성시 row (2012: 1,992; 2013: 1,775), so it is not inside the city row.
    SUBOFFICE = {("경기도", "화성시동부출장소"): ("경기도", "화성시")}
    # Residual lines whose successor applies in every year from the change on, the
    # 2008-2013 block included (03's REMAP does not carry these). 포천군 became 포천시
    # in 2003 and the 2009 table still prints a 포천군 line (1); 마산시 and 진해시 were
    # merged into 창원시 in July 2010, and a 마산시 line survives in 2013 (2) and 2014
    # (1). 마산시 has two successor gu, so its line goes to the 창원시 line, which
    # holds the people the yearbook places in 창원시 and in none of its gu. These
    # were dropped as strays until 2026-09-26 (5차 대조).
    FOLD_FROM = {("경기도", "포천군"): (("경기도", "포천시"), 2004),
                 ("경상남도", "마산시"): (("경상남도", "창원시"), 2010),
                 ("경상남도", "진해시"): (("경상남도", "창원시 진해구"), 2010)}
    for y in IBS:
        fold = dict(SUBOFFICE)
        if int(y) >= 2014:
            fold.update(FOLD)
        fold.update({k: tgt for k, (tgt, y0) in FOLD_FROM.items() if int(y) >= y0})
        for (sido, sg), (sido2, sg2) in fold.items():
            old = RBS.get(y, {}).get(sido, {}).get(sg)
            if not old:
                continue
            tgt = RBS[y].setdefault(sido2, {}).setdefault(sg2, {})
            for c, v in old.items():
                tgt[c] = tgt.get(c, 0) + v
            del RBS[y][sido][sg]
            rec = irec(y, sido2, sg2)
            new = make_record(sido2, sg2, tgt, rec.get("total_pop") if rec else None,
                              rec.get("lisa") if rec else None)
            IBS[y] = [r for r in IBS[y] if not (r["sido"] == sido2 and r["sigungu"] == sg2)] + [new]
            log.append(f"folded residual {sido} {sg} {y} ({sum(old.values()):,}) into {sido2} {sg2}")
            if sido != sido2:
                # The province rows read the yearbook's own 소계, which still counts
                # the line in the old province (연기군 2014 in 충청남도). Move it there
                # too, as 03 does for 2012-2013, so 세종특별자치시 equals 세종시.
                RBSD_ = region.get("by_sido", {}).get(y, {})
                if sido in RBSD_ and sido2 in RBSD_:
                    for c, v in old.items():
                        RBSD_[sido][c] = RBSD_[sido].get(c, 0) - v
                        if RBSD_[sido][c] <= 0:
                            del RBSD_[sido][c]
                        RBSD_[sido2][c] = RBSD_[sido2].get(c, 0) + v
                    moved = sum(old.values())
                    for rec_ in idx.get("by_sido", {}).get(y, []):
                        if rec_["sido"] in (sido, sido2):
                            # the count moves by exactly the line; the province
                            # total keeps whatever else its 소계 holds
                            ft = (rec_.get("foreign_total") or 0) + (moved if rec_["sido"] == sido2 else -moved)
                            nr = make_record(rec_["sido"], "", RBSD_[rec_["sido"]],
                                             rec_.get("total_pop"), "ns")
                            for k_ in ("sigungu", "lisa", "foreign_total", "foreign_share_pct"):
                                nr.pop(k_, None)
                            rec_.update(nr)
                            rec_["foreign_total"] = ft
                            tp_ = rec_.get("total_pop")
                            rec_["foreign_share_pct"] = round(100 * ft / tp_, 2) if tp_ else None
                    log.append(f"  and at province level: {sido} -> {sido2} {y}")

    for y in IBS:
        yi = int(y)
        for sido, sg, from_y in STRAYS:
            if yi < from_y:
                continue
            if sido in RBS.get(y, {}) and sg in RBS[y][sido]:
                del RBS[y][sido][sg]
            before = len(IBS[y])
            IBS[y] = [r for r in IBS[y] if not (r["sido"] == sido and r["sigungu"] == sg)]
            if len(IBS[y]) != before: log.append(f"removed stray {sido} {sg} {y}")

    # ---------- 5) rebuild per-sigungu language demand from corrected counts ----------
    # Use the CLDR-derived weighted country-language shares (one country contributes
    # fractional speakers to multiple languages) when available; fall back to the
    # single-language map for any country missing from the shares table.
    shares_path = os.path.join(ROOT, "03_cleaned_data", "country_language_shares.json")
    COUNTRY_SHARES = json.load(open(shares_path, encoding="utf-8")) if os.path.exists(shares_path) else {}
    AGG = {"총계", "총합계", "소계", "계"}
    lang_n = 0
    for y, blk in RBS.items():
        if y not in idx.get("language", {}): continue
        out = {}
        for sido, sigs in blk.items():
            for sg, nat in sigs.items():
                if sg in AGG: continue
                bl = {}
                for nm, v in nat.items():
                    if not v: continue
                    shares = COUNTRY_SHARES.get(nm)
                    if shares:
                        for sh in shares:
                            bl[sh["language"]] = bl.get(sh["language"], 0) + v * sh["share"]
                    else:
                        lg = CLG.get(nm)
                        if lg: bl[lg] = bl.get(lg, 0) + v
                if bl:
                    out[f"{sido}|{sg}"] = sorted(
                        ({"language": k, "count": round(v, 1)} for k, v in bl.items() if v >= 0.5),
                        key=lambda d: -d["count"])
        idx["language"][y]["by_sigungu"] = out
        lang_n += 1

    # National-level language series: use the official-yearbook-based aggregate
    # from national_language.json (covers 2006-2024, computed in build_national_
    # language.py from the national stay totals). Rolling up sigungu counts would
    # undercount because some foreigners are not assigned to a district in the
    # published tables.
    nl_path = os.path.join(SITE, "national_language.json")
    if os.path.exists(nl_path):
        NL = json.load(open(nl_path, encoding="utf-8"))
        # the file is keyed by scope ({"stay": {year: [...]}, "reg": {...}}); the
        # released/indices national language scope is staying-based, same as
        # regen_language.py. Without this the year loop below would write "stay" and
        # "reg" as if they were years and leave every real year's national list empty.
        NL = NL.get("stay", NL)
        for y, arr in NL.items():
            idx.setdefault("language", {}).setdefault(y, {"national": [], "by_sigungu": {}})
            idx["language"][y]["national"] = list(arr)

    json.dump(full, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(region, open(os.path.join(SITE, "region.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("\n".join(log[:40]))
    print(f"... language by_sigungu rebuilt for {lang_n} years")


def recompute_from_reconciled():
    """Enclaves and the national summary, recomputed from the reconciled districts.

    Both have to run after the district reconciliation, and both read the same two
    files, so they are one step. The enclave set is rebuilt at the published
    threshold from the consolidated region and index data, and the national summary
    fields that are exact functions of the district counts are recomputed from those
    same counts.
    """
    def recompute_enclaves():
        """Recompute ethnic enclaves at the LQ >= 2 & share >= 30% threshold (was LQ >= 5),
        from the CONSOLIDATED region.json + indices.json so the enclave set is consistent
        with the subnational fixes (Bucheon -> single 부천시, 미추홀구, 군위->대구, strays
        removed). Replicates build_dashboard's enclave logic exactly (absolute floor x>=200,
        LQ on the resident-registry base, share within the district's foreign population)
        and overwrites indices.json's data.enclaves and summary[year].n_enclaves.

        The LQ is (x_d / pop_d) / (X / sum_d pop_d), where pop_d is the district's
        `total_pop`, the resident-registration count of Korean nationals (the release's
        `resident_pop`; foreigners were never in that register), and the national base
        is the sum of the same counts over the districts, as README 'Index definitions'
        states. 4라운드 대조 (2026-09-27): this line read "LQ on total-population
        basis", which reads as resident_pop + registered_foreigners; an audit following
        it recomputed lower LQs (2014 안산시 단원구 한국계중국인: 9.9 against the
        published 11.0) and a different enclave set.

        Criterion (Wilson & Portes 1980; Logan, Zhang & Alba 2002, concept): a district x
        nationality pair is an enclave when the nationality's location quotient is at least
        2 (twice the share expected from the national distribution) AND the nationality is
        at least 30% of the district's foreign population. The 30% floor prevents rare-
        nationality LQ artifacts (a nationally scarce group gives a huge LQ from a tiny
        local cluster); together the two criteria capture overrepresentation AND local
        dominance.
        """
        HERE = os.path.dirname(os.path.abspath(__file__))
        SITE = os.path.join(ROOT, "05_dashboard", "data")
        AGG = {"총계", "계", "소계", "총합계"}
        LQ_MIN, SHARE_MIN, ABS_FLOOR = 2.0, 0.30, 200

        full = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
        idx = full["data"]
        region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))["by_sigungu"]

        log = []
        for y in idx["by_sigungu"]:
            if y not in region:
                continue
            recs = {(r["sido"], r["sigungu"]): r for r in idx["by_sigungu"][y]}
            # 전국 인구는 요약 칸을 읽지 않고 시군구를 직접 더한다. 요약의
            # national_total_pop 은 한 단계 뒤의 recompute_summary 가 같은 합으로
            # 바로잡는 값이라, 여기서 읽으면 고치기 전 수(다른 시군구 집합에서 온
            # 것)로 LQ 를 계산하게 된다. 2013년 아산 한국계중국인(lq 2.0021)이
            # 그 낡은 분모에서는 2 아래로 밀려 집거 목록에서 빠졌다(2026-08-26).
            natpop = (sum(r["total_pop"] for r in idx["by_sigungu"][y]
                          if r.get("total_pop"))
                      or idx["summary"][y]["national_total_pop"])
            # national total per nationality (consolidated)
            X = {}
            for sido, sigs in region[y].items():
                for sg, cs in sigs.items():
                    if sg in AGG:
                        continue
                    for c, n in cs.items():
                        X[c] = X.get(c, 0) + n
            rows = []
            for sido, sigs in region[y].items():
                for sg, cs in sigs.items():
                    if sg in AGG:
                        continue
                    rec = recs.get((sido, sg))
                    if not rec:
                        continue
                    tot_pop = rec.get("total_pop")
                    sg_for = sum(cs.values())
                    if not tot_pop or sg_for <= 0:
                        continue
                    for c, x in cs.items():
                        # 기타 is the residual bin, never an enclave (the release
                        # drops it; the dashboard now does too). 2026-09-25. Nor is
                        # any other line that names no nationality (2026-09-26).
                        if c in RESIDUAL_LINES or x < ABS_FLOOR or X.get(c, 0) <= 0 or not natpop:
                            continue
                        lq = (x / tot_pop) / (X[c] / natpop)
                        share = x / sg_for
                        if lq >= LQ_MIN and share >= SHARE_MIN:
                            rows.append({
                                "sido": sido, "sigungu": sg, "country": c,
                                "count": int(x), "lq": round(lq, 1),
                                "share_of_foreign_pct": round(share * 100, 1),
                                "sigungu_foreign_total": int(sg_for),
                                "foreign_share_of_pop_pct": round(sg_for / tot_pop * 100, 2),
                            })
            rows.sort(key=lambda r: -r["lq"])
            idx["enclaves"][y] = rows
            idx["summary"][y]["n_enclaves"] = len(rows)
            log.append((int(y), len(rows)))

        json.dump(full, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print("Recomputed enclaves (LQ>=2 & share>=30%, floor 200):")
        for y, n in sorted(log):
            print(f"  {y}: {n}")
        print("total rows:", sum(n for _, n in log))



    def recompute_summary():
        """Recompute ONLY the definitionally-exact national summary fields from the
        corrected by_sigungu/region data, after the 화성 2014 re-parse + stray removal
        left the annual aggregates stale (summary national_foreign 2014 was 1,057,423
        while the corrected district file sums to 1,083,782).

        Updates only fields that are exact functions of the district nationality counts
        and population (no Korean-estimate-in-entropy or adjacency assumptions, which
        would risk diverging from build_dashboard's method):
          national_foreign_total, national_share_pct, national_shannon_H,
          mean_sigungu_H, n_nationalities, national_evenness, continent_H, continent_shares.
        The diversity fields among them are on the full district detail here;
        normalize_top19 replaces them, with national_HHI and the inclusive H, on the
        top-19-plus-residual basis every other level uses.

        Also fills morans_I_share, which the earlier steps cannot reach: build_dashboard
        runs before the 2008-2013 district block is merged in, so those years had no key
        at all, and its Moran's I uses its pre-consolidation district set, which still
        holds the Bucheon gu rows, 인천 남구, and the duplicated 수원시 / 창원시 city
        totals. It is recomputed here for EVERY year from the reconciled district panel.
        (Until 2026-09-27 this step also set national_HHI from the national
        registered-by-nationality table, every nationality a group of its own, and
        normalize_top19 left it there, so the country's HHI alone sat off the index
        basis: 2024 0.0940 against 0.1004 on the basis of its other indices. 4라운드 대조.)

        LEAVES theil_segregation_H (build_segregation_release.py owns it), by_nationality
        (D/isolation/interaction) and national_shannon_H_inclusive at their upstream
        values. by_sido is untouched (built from sido 총계 rows, not district sums).
        """
        HERE = os.path.dirname(os.path.abspath(__file__))
        SITE = os.path.join(ROOT, "05_dashboard", "data")
        AGG = {"총계", "계", "소계", "총합계"}

        def classify(c):
            return COUNTRY_REGION.get(c, "기타")

        full = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
        idx = full["data"]
        region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))["by_sigungu"]

        # queen-contiguity weights and build_dashboard's own Moran's I, reused verbatim
        _adj_path = os.path.join(ROOT, "03_cleaned_data", "adjacency.json")
        _ADJ = json.load(open(_adj_path, encoding="utf-8")) if os.path.exists(_adj_path) else {}


        def morans_i(value_by_key):
            return _morans_i(value_by_key, _ADJ)



        def entropy(counts):
            t = sum(counts)
            return -sum((v / t) * math.log(v / t) for v in counts if v > 0) if t else 0.0


        rep = []
        for y in idx["by_sigungu"]:
            sig = idx["by_sigungu"][y]
            s = idx["summary"][y]
            # Derive the national denominator from the district panel so the identity
            # Sigma sigungu.total_pop == national_total_pop holds exactly. Taking it from
            # build_dashboard's own running total left Sejong out of 2012 and 2013, the
            # two years the city existed but had not yet entered that pop set.
            sig_pop = sum(r["total_pop"] for r in sig if r.get("total_pop"))
            natpop = sig_pop or s.get("national_total_pop")
            s["national_total_pop"] = natpop
            nat = {}
            for sido, sigs in region.get(y, {}).items():
                for sg, cs in sigs.items():
                    if sg in AGG:
                        continue
                    for c, v in cs.items():
                        nat[c] = nat.get(c, 0) + v
            nf = sum(nat.values())
            nat_H = entropy(list(nat.values()))
            n_nat = sum(1 for v in nat.values() if v > 0)
            cont = {}
            for c, v in nat.items():
                cont[classify(c)] = cont.get(classify(c), 0) + v
            cont_full = dict(cont)
            cont_full["동아시아"] = cont_full.get("동아시아", 0) + max(natpop or 0, 0)
            old = s["national_foreign_total"]
            s["national_foreign_total"] = nf
            s["national_share_pct"] = (nf / natpop * 100) if natpop else None
            s["national_shannon_H"] = round(nat_H, 3)
            s["mean_sigungu_H"] = round(sum((r.get("shannon_H") or 0) for r in sig) / len(sig), 3) if sig else None
            s["n_nationalities"] = n_nat
            s["national_evenness"] = round(nat_H / math.log(n_nat), 3) if n_nat > 1 else None
            s["continent_H"] = round(entropy(list(cont_full.values())), 4)
            s["continent_shares"] = {k: round(100 * v / nf, 3) for k, v in sorted(cont.items(), key=lambda x: -x[1])} if nf else {}
            # Moran's I of the district foreign share on the reconciled district set
            # (see the docstring); national_HHI is set by normalize_top19
            share_by_key = {r["sido"] + "|" + r["sigungu"].replace(" ", ""): r["foreign_share_pct"]
                            for r in sig if r.get("foreign_share_pct") is not None}
            mi = morans_i(share_by_key)
            s["morans_I_share"] = round(mi, 4) if mi is not None else None
            rep.append((int(y), old, nf, round(sum(r["foreign_total"] for r in sig))))

        json.dump(full, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print("year   old_foreign   new_foreign   by_sigungu_sum (must == new)")
        for y, o, nf, ss in sorted(rep):
            flag = "" if nf == ss else "  <-- MISMATCH"
            print(f"{y}  {o:>11,}  {nf:>12,}  {ss:>12,}{flag}")

    recompute_enclaves()
    recompute_summary()



def normalize_top19():
    """Make the diversity indices comparable across the full 2008-2024 series by
    re-computing them on a consistent top-19-nationality + 기타 basis.

    Why: the source publishes only the top 19 nationalities (+ Others) at the
    district level for 2008-2013, but the full ~200 nationality detail for
    2014-2024. Indices that are sensitive to the long tail of small nationalities
    (Shannon H, Pielou evenness, HHI, n_nationalities, continent H, inclusive H)
    therefore have a coverage-driven discontinuity at 2013->2014 that does not
    reflect a real distribution change. This script reduces 2014+ district counts
    to the top 19 + 기타 (identified per year from the national sums) before
    re-computing those indices, while leaving raw counts in foreign_residents_by_
    sigungu.csv untouched (full detail preserved for users who want it).

    What it does NOT touch:
      - raw counts in region.json and foreign_residents_by_sigungu.csv
      - segregation indices (already operate on a per-nationality basis with the
        top-19 groups; the long tail does not move D or isolation meaningfully)
      - ethnic enclaves (LQ + share criterion selects large groups; long tail
        cannot satisfy the threshold)

    Run order: fix_subnational -> recompute_enclaves -> recompute_summary ->
    normalize_indices_top19 -> export_dataset.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")


    OTHER = "기타"
    TOP_K = 19  # source-published top-N at sigungu level for 2008-2013

    full = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
    idx = full["data"]
    region = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))
    RBS = region["by_sigungu"]
    RBSD = region.get("by_sido", {})
    IBS = idx["by_sigungu"]
    IBSD = idx.get("by_sido", {})


    def observed(nat_dict):
        """How many nationalities the source actually lists, before the top-19
        reduction. The residual 기타 is a bin, not a nationality, so it does not
        count, and neither does any other line that names no nationality (무국적,
        미등록국가; kird.RESIDUAL_LINES), which the district files carry since
        2026-09-26. Through 2013 the yearbook publishes only the top 19 plus that
        bin at the district level, so these counts are capped at 19 for those years."""
        return len([c for c, v in nat_dict.items()
                    if v and v > 0 and c not in RESIDUAL_LINES])


    def reduce_to_top19(nat_dict, top19_set):
        """Keep top 19 nationalities, lump the rest into 기타."""
        out = {}
        other = 0
        for c, v in nat_dict.items():
            if c in top19_set:
                out[c] = out.get(c, 0) + v
            else:
                other += v
        if other:
            out[OTHER] = out.get(OTHER, 0) + other
        return out


    def national_top19(year):
        """Identify the top-19 nationalities nationally for the year, by summing
        across all districts. Excludes 기타 itself so it stays as the residual bin,
        and every other line that names no nationality, which goes into that bin."""
        nat = {}
        for sido, sigs in RBS.get(year, {}).items():
            for sg, cs in sigs.items():
                if sg in ("총계", "총합계", "소계", "계"):
                    continue
                for c, v in cs.items():
                    if c in RESIDUAL_LINES:
                        continue
                    nat[c] = nat.get(c, 0) + v
        return set(c for c, _ in sorted(nat.items(), key=lambda x: -x[1])[:TOP_K])


    changed = 0
    years_done = []
    for ystr in sorted(IBS):
        top19 = national_top19(ystr)
        if not top19:
            continue
        years_done.append(ystr)
        for rec in IBS[ystr]:
            sido, sg = rec["sido"], rec["sigungu"]
            nat = RBS.get(ystr, {}).get(sido, {}).get(sg)
            if not nat:
                continue
            reduced = reduce_to_top19(nat, top19)
            # The observed count, taken before the reduction. n_nationalities is
            # about to become the size of the index base (top-19 + residual), which
            # is 20 for most districts and every province. Keeping the real count
            # separately is the only way a reader can tell the two apart.
            rec["n_nationalities_observed"] = observed(nat)
            new = make_record(sido, sg, reduced, rec.get("total_pop"), rec.get("lisa"))
            # only overwrite the coverage-sensitive index fields; preserve
            # foreign_total, total_pop, foreign_share_pct (those use raw counts and
            # do not depend on nationality coverage)
            for f in ("shannon_H", "shannon_H_inclusive", "continent_H",
                      "continent_shares", "HHI", "n_nationalities", "evenness"):
                rec[f] = new[f]
            changed += 1

    # Province (sido) rows, same basis. summary_by_sido.csv reads these straight out
    # of by_sido, so leaving them on full nationality detail put the province series on
    # a different footing from the district and national ones (n_nationalities ~150 vs 20
    # from 2014 on).
    sido_changed = 0
    for ystr in years_done:
        top19 = national_top19(ystr)
        for rec in IBSD.get(ystr, []):
            nat = RBSD.get(ystr, {}).get(rec["sido"])
            if not nat:
                continue
            reduced = reduce_to_top19(nat, top19)
            # The observed count for a province is the union over its districts in
            # the district-by-nationality table, NOT the count in the separately
            # published province table (RBSD). The two disagree in 4 of 306
            # province-years by 1-4 nationalities, and the district table is the
            # one every level of the release counts from, so the levels stay
            # consistent (README "Levels and how they aggregate").
            uni = set()
            for _sg, _cs in RBS.get(ystr, {}).get(rec["sido"], {}).items():
                if _sg in ("총계", "총합계", "소계", "계"):
                    continue
                uni |= {c for c, v in _cs.items() if v and c not in RESIDUAL_LINES
                        and c not in ("총계", "총합계", "소계", "계")}
            rec["n_nationalities_observed"] = len(uni)
            new = make_record(rec["sido"], "", reduced, rec.get("total_pop"), "ns")
            # Every diversity index on the one basis, HHI and the inclusive H included.
            # Until 2026-09-27 (4라운드 대조) these two kept the full nationality detail
            # ("dominated by the largest groups"), so the province series read 19 named
            # groups plus Other through 2013 and every nationality from 2014: HHI fell by
            # up to 0.017 at the 2014 coverage break for that reason alone (울산 2014:
            # 0.1348 on the detail, 0.1521 on the basis), and index_base_k, which the
            # README gives as the basis of every index, did not describe them.
            for f in ("shannon_H", "shannon_H_inclusive", "continent_H", "continent_shares",
                      "HHI", "n_nationalities", "evenness"):
                if f in new:
                    rec[f] = new[f]
            sido_changed += 1

    # Re-derive national-level diversity fields in summary on the same basis
    for ystr in years_done:
        top19 = national_top19(ystr)
        nat = {}
        for sido, sigs in RBS.get(ystr, {}).items():
            for sg, cs in sigs.items():
                if sg in ("총계", "총합계", "소계", "계"):
                    continue
                for c, v in cs.items():
                    nat[c] = nat.get(c, 0) + v
        reduced = reduce_to_top19(nat, top19)
        s = idx.setdefault("summary", {}).setdefault(ystr, {})
        nf = sum(reduced.values())
        natpop = s.get("national_total_pop")
        H = shannon(reduced)
        n = len([v for v in reduced.values() if v > 0])
        cont = {}
        for c, v in reduced.items():
            cont[COUNTRY_REGION.get(c, "기타")] = cont.get(COUNTRY_REGION.get(c, "기타"), 0) + v
        cont_full = dict(cont)
        cont_full["동아시아"] = cont_full.get("동아시아", 0) + max(natpop or 0, 0)
        s["national_shannon_H"] = round(H, 3)
        # national inclusive: same top-19 reduced basis + Korean group as national_shannon_H /
        # continent_H (was left on the off-basis full-detail value from add_sido_national_diversity).
        s["national_shannon_H_inclusive"] = round(shannon({**reduced, "_korean_residual": max(natpop or 0, 0)}), 3) if natpop else None
        # national HHI on the same basis. It had been left on the national
        # registered-by-nationality table with every nationality a group (2024: 0.0940
        # against 0.1004 here), the one national index off the basis index_base_k
        # describes (4라운드 대조, 2026-09-27). 2008 follows the 2008 district table, which
        # prints 중국 with 한국계중국인 inside it, as the other 2008 indices do.
        s["national_HHI"] = hhi(reduced)
        s["n_nationalities"] = n
        s["n_nationalities_observed"] = observed(nat)
        s["national_evenness"] = round(H / math.log(n), 3) if n > 1 else None
        s["continent_H"] = round(shannon(cont_full), 4)
        s["continent_shares"] = {k: round(100 * v / nf, 3) for k, v in sorted(cont.items(), key=lambda x: -x[1])} if nf else {}
        s["mean_sigungu_H"] = round(sum((r.get("shannon_H") or 0) for r in IBS[ystr]) / len(IBS[ystr]), 3) if IBS[ystr] else None

    json.dump(full, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"normalized indices to top-{TOP_K}+기타 basis: {changed} district rows, "
          f"{sido_changed} province rows across years {years_done[0]}-{years_done[-1]}")
    print("Run export_dataset next to refresh the CSVs.")


def trim_language_top20():
    """Language demand trimmed to the released basis, top 20 languages per district.

    Step 13 writes the untrimmed language block, with every language a district's
    nationality mix implies. This step regenerates the national series from the
    Ethnologue shares and replaces the `language` key in indices.json with the top 20
    per district, which is what the release and the dashboard both carry. Only that
    key is touched, so the other indices are left as the earlier steps computed them.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")

    # the single-language fallback, for countries Ethnologue does not cover
    CLG = COUNTRY_LANGUAGE
    SHARES = json.load(open(os.path.join(ROOT, "03_cleaned_data", "country_language_shares.json"), encoding="utf-8"))

    idxfull = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))
    idx = idxfull["data"]
    RBS = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))["by_sigungu"]
    AGG = {"총계", "총합계", "소계", "계"}

    n = 0
    for y, blk in RBS.items():
        if y not in idx.get("language", {}):
            continue
        out = {}
        for sido, sigs in blk.items():
            for sg, nat in sigs.items():
                if sg in AGG:
                    continue
                # empty share list = deliberately zero (wholly Korean-L1 origin); never
                # fall back to the single map for those. kird.language_estimate is the
                # exact computation 08_export_dataset uses for the release, so the
                # dashboard and language_demand.csv pick the same 20 languages
                # (2026-09-27; they had ranked on values rounded to one decimal).
                bl = language_estimate({nm: v for nm, v in nat.items() if v}, SHARES, CLG)
                if bl:
                    # top 20 per district. The name is the tiebreak: languages tie
                    # often in small districts, and without it the cut depends on
                    # whatever order the counts were accumulated in.
                    top = sorted(bl.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
                    out[f"{sido}|{sg}"] = [{"language": k, "count": round(u / LANG_UNIT, 1)}
                                           for k, u in top if u >= LANG_UNIT // 2]
        idx["language"][y]["by_sigungu"] = out
        n += 1

    # national은 national_language.json에서
    NL = json.load(open(os.path.join(SITE, "national_language.json"), encoding="utf-8"))
    NL = NL.get("stay", NL)   # the released/indices national language scope is staying-based
    for y, arr in NL.items():
        idx.setdefault("language", {}).setdefault(y, {"national": [], "by_sigungu": {}})
        idx["language"][y]["national"] = list(arr)

    json.dump(idxfull, open(os.path.join(SITE, "indices.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"indices.language by_sigungu rebuilt: {n} years")
    y = sorted(idx["language"])[-1]
    print(f"{y} national top:", [(d["language"], d["count"]) for d in idx["language"][y]["national"][:8]])



def relisa():
    """더 이상 여기서 계산하지 않는다. 09 의 build_lisa 가 유일한 자리다.

    이 함수는 지표 파일(2014년부터)을 읽어 계산했기 때문에 2008-2013년을 채울 수
    없었다. 국지 Moran 에 필요한 것은 외국인 비율뿐이고 배포본 CSV 가 2008년부터
    담으므로, 09 에서 그 파일을 읽어 모든 해를 계산한다.
    """
    print("relisa: 09_finish_release.build_lisa 가 계산한다 (한 곳에서만)")


if __name__ == "__main__":
    consolidate_bucheon()
    fix_subnational()
    recompute_from_reconciled()
    normalize_top19()
    trim_language_top20()
    relisa()
