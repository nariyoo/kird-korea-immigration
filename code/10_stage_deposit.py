"""The openICPSR deposit, staged from the release and checked.

The deposit is not the same object as the release. It adds the two refugee files,
a cumulative 1994-2024 snapshot since MOJ publishes refugee outcomes by
nationality only cumulatively, and it carries wide summary variants where every
place-keyed breakdown is pivoted to one column per category. The last pass is the
gate: file integrity, CSV and DTA parity, cross-level sums, within-row
identities, and comparison against the published MOJ figures.
"""
import csv
import importlib.util
import json
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

from kird import CLEAN
from kird import DEPOSIT
from kird import DEPOSIT_DATA
from kird import DEPOSIT_DATA as DEP
from kird import DEPOSIT_PUBLISHED
from kird import RELEASE
from kird import RELEASE_DATA
from kird import ROOT

_FR = None


def _finish_release():
    """09_finish_release.py as a module, cached. Its file name starts with a digit,
    so it cannot be imported normally; this is the pattern build_unhcr_refugees.py
    already uses. Imported for the labeled-Stata helpers, so a deposit .dta is
    written exactly the way a release .dta is instead of through a bare to_stata."""
    global _FR
    if _FR is None:
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location(
            "finish_release", os.path.join(here, "09_finish_release.py"))
        _FR = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_FR)
    return _FR


# The four files the deposit keeps at the top of data/ rather than in
# detailed_data/. attach_breakdowns() writes them itself, with the wide breakdown
# columns attached, so stage_release() must not copy the plain release versions
# over them. All four keep the names the release uses; v1.1.0 shipped the
# national one as summary_national.csv and v1.2.0 renames it back to
# national_annual.csv so that one table has one name in every channel.
TOP_LEVEL = {"summary_by_sido.csv", "summary_by_sigungu.csv",
             "summary_by_eupmyeondong.csv", "national_annual.csv"}
# Written into the deposit by add_refugee_files() / export_deposit_stata(); they
# have no release counterpart, so they are never stale leftovers.
DEPOSIT_ONLY = ("refugee_",)


def stage_release():
    """Lay the finished release out in the deposit's folder shape.

    Nothing else in phase 3 moves a table. attach_breakdowns() rewrites the four
    summary files and final_qc() only reads, so without this step a rebuilt deposit
    keeps whatever the last upload left behind: fresh summary CSVs sitting next to
    year-old detail tables, and .dta files that never move at all. That mismatch is
    what final_qc() reports as CSV/DTA parity failures.

        04_dataset_release/data/*.csv        -> <deposit>/data/detailed_data/
        04_dataset_release/data/stata/*.dta  -> <deposit>/data/detailed_data/

    minus the four TOP_LEVEL files, which attach_breakdowns() writes into
    <deposit>/data/ instead.

    README.md and LICENSE.txt are the deposit's own curated documents and are NOT
    the release's copies: the deposit README describes the detailed_data/ split, the
    wide columns and the data-only scope of the deposit, and LICENSE.txt is the full
    CC BY text where 04_dataset_release/LICENSE is a two-line pointer. They are
    seeded once (from the published deposit, falling back to the release) and then
    left alone, the same rule 08_export_dataset.py applies to the README and
    CITATION.cff it would otherwise regenerate, so an edit written for the next
    version survives a rebuild.
    """
    SRC = RELEASE_DATA
    SRC_DTA = os.path.join(RELEASE_DATA, "stata")
    DETAIL = os.path.join(DEPOSIT_DATA, "detailed_data")
    os.makedirs(DETAIL, exist_ok=True)

    csvs = sorted(f for f in os.listdir(SRC) if f.endswith(".csv"))
    absent = sorted(TOP_LEVEL - set(csvs))
    if absent:
        raise SystemExit(f"release incomplete: {SRC} has no {absent}; run phase 2 first")
    detail = [f for f in csvs if f not in TOP_LEVEL]
    if not detail:
        raise SystemExit(f"no detail tables in {SRC}: nothing to stage")

    print(f"staging {len(detail)} detail tables -> {DETAIL}")
    staged, no_dta = [], []
    for f in detail:
        stem = f[:-4]
        src_dta = os.path.join(SRC_DTA, stem + ".dta")
        if not os.path.exists(src_dta):
            no_dta.append(stem)
            continue
        shutil.copy2(os.path.join(SRC, f), os.path.join(DETAIL, f))
        shutil.copy2(src_dta, os.path.join(DETAIL, stem + ".dta"))
        staged.append(stem)
        c_sz = os.path.getsize(os.path.join(DETAIL, f))
        d_sz = os.path.getsize(os.path.join(DETAIL, stem + ".dta"))
        print(f"  {stem:34s} {c_sz:>12,} B csv  {d_sz:>12,} B dta")
    if no_dta:
        raise SystemExit(f"no Stata file in {SRC_DTA} for {no_dta}; run phase 2 first")

    # Drop anything left from an earlier release that this one no longer produces,
    # so the deposit cannot ship a table the dictionary does not document.
    keep = {stem + ext for stem in staged for ext in (".csv", ".dta")}
    stale = sorted(f for f in os.listdir(DETAIL)
                   if f not in keep and not f.startswith(DEPOSIT_ONLY))
    for f in stale:
        os.remove(os.path.join(DETAIL, f))
        print(f"  removed stale {f}")

    # 맨 위 넷도 같은 이유로 청소한다. 이름을 바꾸면 옛 이름의 파일이 남아
    # 같은 표가 두 이름으로 실린다.
    top_keep = {f for f in TOP_LEVEL}
    top_keep |= {f[:-4] + ".dta" for f in TOP_LEVEL}
    top_stale = sorted(f for f in os.listdir(DEPOSIT_DATA)
                       if f.endswith((".csv", ".dta")) and f not in top_keep)
    for f in top_stale:
        os.remove(os.path.join(DEPOSIT_DATA, f))
        print(f"  removed stale {f} (data/ top level)")

    for name, sources in (
            ("README.md", [os.path.join(DEPOSIT_PUBLISHED, "README.md"),
                           os.path.join(RELEASE, "README.md")]),
            ("LICENSE.txt", [os.path.join(DEPOSIT_PUBLISHED, "LICENSE.txt"),
                             os.path.join(RELEASE, "LICENSE")])):
        dst = os.path.join(DEPOSIT, name)
        if os.path.exists(dst):
            print(f"  {name} kept (curated for the deposit; not regenerated)")
            continue
        src = next((q for q in sources if os.path.exists(q)), None)
        if src is None:
            raise SystemExit(f"no source for the deposit's {name}: tried {sources}")
        shutil.copy2(src, dst)
        print(f"  {name} seeded from {os.path.relpath(src, ROOT)}")

    # Say out loud how the staged bundle differs from the one already published, so a
    # table that quietly appeared or vanished cannot ride along unnoticed.
    pub = os.path.join(DEPOSIT_PUBLISHED, "data", "detailed_data")
    if os.path.isdir(pub):
        here = {f for f in os.listdir(DETAIL) if f.endswith((".csv", ".dta"))}
        there = {f for f in os.listdir(pub) if f.endswith((".csv", ".dta"))}
        print(f"  vs published deposit: only here {sorted(here - there) or 'none'}; "
              f"only there {sorted(there - here) or 'none'}")
    return staged



def add_refugee_files():
    """Build refugee nationality + refugee language-demand release files and add them
    to the openICPSR deposit (detailed_data/), matching the deposit's conventions
    (UTF-8-BOM CSV, bilingual ko/en columns, dictionary rows -> labeled .dta via
    export_deposit_stata()).

    Runs AFTER attach_breakdowns(), which rewrites data_dictionary.csv from the
    release dictionary: run before it and these seven refugee rows are silently
    dropped, which is why the published v1.1.0 dictionary documents neither file.

    Grain: cumulative SNAPSHOT (not annual). MOJ publishes refugee outcomes (1994-2024
    cumulative) with a nationality breakdown only as cumulative top-10 lists; annual
    nationality detail exists for 2016-2023 only and only as top-10 + an unmappable
    'Other', so a complete, language-mappable file has to be the cumulative snapshot.
    This is the same population the dashboard's refugee-language panel already shows.

    Two files:
      refugee_by_nationality.csv   status x nationality (applicant / recognized / humanitarian)
      refugee_language_demand.csv  status x language    (recognized / humanitarian / protected)

    Language demand is derived exactly like the general language_demand.csv: each
    nationality's count is split across its country's first-language (L1) speaker
    shares from Ethnologue 24 (SIL Global 2021), Korean excluded. The counts are read
    from refugee_data.language_demand in data.json (built by 08_add_refugee_language.py
    off country_language_shares.json); English language labels are taken from the same
    lang_ko_en.json the deposit uses.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    DJ = os.path.join(ROOT, "05_dashboard", "data", "data.json")
    LANG_KO_EN = os.path.join(ROOT, "03_cleaned_data", "lang_ko_en.json")
    DETAIL = os.path.join(DEPOSIT_DATA, "detailed_data")
    DICT = os.path.join(DEPOSIT, "data_dictionary.csv")
    if not os.path.exists(DICT):
        raise SystemExit(f"{DICT} missing; attach_breakdowns() writes it and runs first")

    STATUS_EN = {"신청": "applicant", "난민인정": "recognized",
                 "인도적체류": "humanitarian", "보호": "protected"}

    # Bilingual label fixes for the few refugee languages the source keys by a Latin
    # name (so the Korean column would be Latin) or leaves untranslated (so the
    # English column would be Korean). Keyed by the language string exactly as it
    # appears in data.json -> refugee_data.language_demand. Keeps the released file
    # fully bilingual. (lang_ko_en.json, the general ko->en map, cannot fix a
    # Latin-keyed language because it has no Korean entry to look up.)
    LANG_LABEL = {
        "친어": ("친어", "Chin"),
        "Chittagonian": ("치타공어", "Chittagonian"),
    }


    def write_csv(path, header, rows):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f)
            wr.writerow(header)
            wr.writerows(rows)
        print(f"  {os.path.basename(path)}: {len(rows):,} rows")


    def main():
        data = json.load(open(DJ, encoding="utf-8"))
        rd = data["refugee_data"]
        lang_en = json.load(open(LANG_KO_EN, encoding="utf-8"))

        # ---- 1) refugee_by_nationality.csv (cumulative top-10 per status) ----
        nat_rows = []
        nat_src = [
            ("신청", rd.get("top_applicant_nationalities", [])),
            ("난민인정", rd.get("top_recognized_nationalities", [])),
            ("인도적체류", rd.get("top_humanitarian_nationalities", [])),
        ]
        for status, lst in nat_src:
            for ko, en, count, pct in lst:
                nat_rows.append([status, STATUS_EN[status], ko, en, count, pct])
        write_csv(os.path.join(DETAIL, "refugee_by_nationality.csv"),
                  ["status", "status_en", "country", "country_en", "count", "share_pct"],
                  nat_rows)

        # ---- 2) refugee_language_demand.csv (estimated, Ethnologue L1 split) ----
        # Counts are person counts: round to whole persons (round half up) and keep
        # the top 20 languages per status, matching the deposit's integer convention
        # and the sigungu-scope top-~20 cap in the general language_demand. (The 20th
        # language is well above 1 person in every status, so rounding never erases a
        # kept language; the fractional long tail is dropped as spurious precision on
        # this small, approximate population.)
        lang_rows = []
        ld = rd["language_demand"]
        TOP_N = 20
        for status in ("난민인정", "인도적체류", "보호"):
            skey = STATUS_EN[status]
            top = sorted(ld[skey], key=lambda d: -d["count"])[:TOP_N]
            for d in top:
                count = int(float(d["count"]) + 0.5)  # round half up to whole persons
                if count < 1:
                    continue
                src = d["language"]
                if src in LANG_LABEL:
                    ko, en = LANG_LABEL[src]
                else:
                    ko = src
                    en = lang_en.get(src) or d.get("language_en") or src
                lang_rows.append([status, skey, ko, en, count])

        # Verify every label is bilingual: Korean column in Hangul, English column not.
        # Surfaces any new gap (a Latin-keyed or untranslated language) as a loud error
        # rather than shipping a half-translated row; add it to LANG_LABEL above.
        def has_hangul(s):
            return any("가" <= c <= "힣" for c in str(s))
        gaps = [(ko, en) for _, _, ko, en, _ in lang_rows
                if not has_hangul(ko) or has_hangul(en)]
        if gaps:
            raise SystemExit(f"Untranslated language label(s); add to LANG_LABEL: {gaps}")
        write_csv(os.path.join(DETAIL, "refugee_language_demand.csv"),
                  ["status", "status_en", "language", "language_en", "count"],
                  lang_rows)

        # ---- 3) append data dictionary rows (file, variable, type, en, ko) ----
        new_dict = [
            ["refugee_by_nationality.csv", "status / status_en", "string",
             "Refugee-process outcome: 신청 applicant, 난민인정 recognized, 인도적체류 humanitarian (Korean + English).",
             "난민 절차 구분: 신청/난민인정/인도적체류(한글+영문)."],
            ["refugee_by_nationality.csv", "country / country_en", "string",
             "Nationality (Korean + English).", "국적(한글+영문)."],
            ["refugee_by_nationality.csv", "count", "integer",
             "Cumulative cases 1994-2024 for that status and nationality (MOJ top-10 per status; full national totals: 122,095 applied / 1,544 recognized / 2,696 humanitarian).",
             "1994-2024 누적 건수(MOJ 구분별 top-10; 전체: 신청 122,095·인정 1,544·인도적 2,696)."],
            ["refugee_by_nationality.csv", "share_pct", "float",
             "Nationality's percent of that status's cumulative total.",
             "해당 구분 누적 총계 대비 국적 비중(%)."],
            ["refugee_language_demand.csv", "status / status_en", "string",
             "Protected population: 난민인정 recognized, 인도적체류 humanitarian, 보호 protected (recognized + humanitarian).",
             "보호 인구 구분: 난민인정/인도적체류/보호(난민인정+인도적체류)."],
            ["refugee_language_demand.csv", "language / language_en", "string",
             "Estimated first language (Korean + English).", "추정 모어(한글+영문)."],
            ["refugee_language_demand.csv", "count", "integer",
             "Estimated speakers = cumulative nationality count x that country's L1 (mother-tongue) share (Ethnologue 24, SIL Global 2021), rounded to whole persons; Korean excluded. Top 20 languages per status. Built from the published top-10 nationalities only (approximation of the full population's interpretation demand).",
             "추정 화자수 = 누적 국적 인원 x 해당국 L1 모어 share(Ethnologue 24), 사람 수로 반올림; 한국어 제외. 구분별 상위 20개 언어. 공개 top-10 국적만 반영(근사치)."],
        ]
        # Idempotent: drop any existing refugee_* dictionary rows, then re-append, so
        # this script can be re-run without duplicating rows. Rewrite with one BOM and
        # CRLF to match the deposit dictionary's existing format.
        import pandas as pd
        dd = pd.read_csv(DICT, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        dd = dd[~dd["file"].str.startswith("refugee_")]
        add = pd.DataFrame(new_dict, columns=list(dd.columns))
        dd = pd.concat([dd, add], ignore_index=True)
        dd.to_csv(DICT, index=False, encoding="utf-8-sig", lineterminator="\r\n")
        print(f"  data_dictionary.csv: {len(add)} refugee rows (idempotent rewrite, {len(dd)} total)")

    main()



def attach_breakdowns():
    """Attach every place-keyed breakdown to the summary files as wide columns.

    For each summary level, the long breakdown files are pivoted to one column per
    category (counts) and merged on the place/year keys, so the summary becomes a
    single wide row per place x year. The long breakdown files are kept as-is.

    Column naming: <prefix><english-slug>, Stata-safe (<=32 chars, unique). A blank
    cell means the category was not separately reported for that place-year (NOT a
    zero); e.g. for 2008-2013 the source folds non-top nationalities into "Other".

      nat_*       nationality counts        (nationality_by_sigungu)
      visa_*      visa-status counts        (visa_by_sigungu)
      lang_*      language-demand counts    (language_demand, scope=sigungu)
      childage_*  children by single age    (children_by_age)
      mc_*        multicultural leaf cats   (multicultural_households)  [eupmyeondong]
      n_enclaves  count of enclave groups   (ethnic_enclaves)

    Run on the deposit data folder. Writes wide summaries in place + a mapping CSV
    (_wide_columns.csv) used to extend data_dictionary.csv.
    """
    SRC = RELEASE_DATA
    DATA = DEPOSIT_DATA


    def slug(prefix, label, used):
        s = re.sub(r"[^A-Za-z0-9]+", "_", str(label).strip().lower()).strip("_")
        name = (prefix + s)[:32].rstrip("_")
        base, i = name, 1
        while name in used or not name:
            suf = f"_{i}"
            name = (base[:32 - len(suf)] + suf).strip("_")
            i += 1
        used.add(name)
        return name


    def top_keep(long_df, cat_col, val_col, n=50):
        """Set of the top-n category values (as str) by total val across the breakdown."""
        tot = long_df.groupby(long_df[cat_col].astype(str))[val_col].sum().sort_values(ascending=False)
        return set(tot.head(n).index)


    def tidy_types(df, orig_cols):
        """Clean numeric types on the newly added wide columns: all counts as nullable
        integers (so CSV shows 1234 and blank, not 1234.0). Language-demand values are
        estimates and are rounded to whole persons like the other counts."""
        for c in df.columns:
            if c in orig_cols:
                continue
            if c.startswith(("nat_", "visa_", "childage_", "mc_", "lang_")):
                df[c] = pd.to_numeric(df[c], errors="coerce").round(0).astype("Int64")
        return df


    def build_namemap(cats_ko, cats_en, prefix, used):
        """cats_ko/en: parallel lists. Returns {ko_value: final_name}, {final_name:(ko,en)}."""
        pairs = sorted(set(zip(map(str, cats_ko), map(str, cats_en))), key=lambda t: t[1])
        nm, lab = {}, {}
        for ko, en in pairs:
            n = slug(prefix, en, used)
            nm[ko] = n
            lab[n] = (ko, en)
        return nm, lab


    def pivot_merge(summary, keys, long_df, cat_col, val_col, prefix, label_rows,
                    src, cat_en_col=None, code_labels=None, keep=None):
        if keep is not None:
            long_df = long_df[long_df[cat_col].astype(str).isin(keep)]
        used = set(summary.columns)
        cats_ko = long_df[cat_col].astype(str)
        cats_en = long_df[cat_en_col].astype(str) if cat_en_col else cats_ko
        nm, lab = build_namemap(cats_ko, cats_en, prefix, used)
        piv = long_df.pivot_table(index=keys, columns=cat_col, values=val_col, aggfunc="sum")
        piv.columns = [nm[str(c)] for c in piv.columns]
        out = summary.merge(piv.reset_index(), on=keys, how="left")
        for fn, (ko, en) in lab.items():
            if code_labels and ko in code_labels:        # visa: ko is the code; look up label
                lk, le = code_labels[ko]
                label_rows.append((fn, en_desc(prefix, le, lk, src)))
            else:
                label_rows.append((fn, en_desc(prefix, en, ko, src)))
        return out


    def en_desc(prefix, en, ko, src):
        kind = {"nat_": "nationality", "visa_": "visa status", "lang_": "language",
                "childage_": "children aged", "mc_": "multicultural category"}[prefix]
        en_d = f"Count for {kind}: {en} ({ko}). From {src}; blank = not separately reported."
        ko_d = f"{kind} {ko}({en}) 인원수. 출처 {src}; 공백=별도 미보고."
        return (en_d, ko_d)


    def main():
        rows = []  # (file, varname, (en_desc, ko_desc))

        # ---- shared breakdown loads ----
        nat = pd.read_csv(f"{SRC}/nationality_by_sigungu.csv", encoding="utf-8-sig")
        visa = pd.read_csv(f"{SRC}/visa_by_sigungu.csv", encoding="utf-8-sig")
        lang = pd.read_csv(f"{SRC}/language_demand.csv", encoding="utf-8-sig")
        lang_sg = lang[lang["scope"] == "sigungu"].copy()
        enc = pd.read_csv(f"{SRC}/ethnic_enclaves.csv", encoding="utf-8-sig")
        # visa code -> label map (labels live in visa_by_nationality)
        vbn = pd.read_csv(f"{SRC}/visa_by_nationality.csv", encoding="utf-8-sig")
        code_labels = {str(r.visa_code): (str(r.visa_label), str(r.visa_label_en))
                       for r in vbn[["visa_code", "visa_label", "visa_label_en"]].drop_duplicates().itertuples()}

        # Cap the wide columns to the TOP_N categories overall (by total count); the
        # full tail stays in the long breakdown files. Small dimensions (visa ~35,
        # ages 0-18) fall under the cap so all are kept. Same keep-sets are reused at
        # sido so the columns line up across levels.
        TOP_N = 50
        keep_nat = top_keep(nat, "country", "n", TOP_N)
        keep_visa = top_keep(visa, "visa_code", "n", TOP_N)
        keep_lang = top_keep(lang_sg, "language", "count", TOP_N)

        # ===== summary_by_sigungu =====
        K = ["year", "sido", "sigungu"]
        s = pd.read_csv(f"{SRC}/summary_by_sigungu.csv", encoding="utf-8-sig")
        base_n = len(s)
        orig = list(s.columns)
        lr = []
        s = pivot_merge(s, K, nat, "country", "n", "nat_", lr, "nationality_by_sigungu", "country_en", keep=keep_nat)
        s = pivot_merge(s, K, visa, "visa_code", "n", "visa_", lr, "visa_by_sigungu", code_labels=code_labels, keep=keep_visa)
        s = pivot_merge(s, K, lang_sg, "language", "count", "lang_", lr, "language_demand", "language_en", keep=keep_lang)
        # childage_* intentionally NOT attached: children_by_age covers 2011+ only and is
        # reported at a city/gu grain inconsistent with the summary spine, so the wide
        # columns would not be additive across levels. The children TOTAL stays (broad),
        # and the full single-age detail remains in the long children_by_age.csv.
        nenc = enc.groupby(K).size().rename("n_enclaves").reset_index()
        s = s.merge(nenc, on=K, how="left")
        s["n_enclaves"] = s["n_enclaves"].fillna(0).astype(int)
        lr.append(("n_enclaves", ("Number of ethnic-enclave nationalities in the district that year (0 if none).",
                                  "그 해 그 시군구의 ethnic enclave 국적 수(없으면 0).")))
        assert len(s) == base_n, "row count changed!"
        s = tidy_types(s, orig)
        s.to_csv(f"{DATA}/summary_by_sigungu.csv", index=False, encoding="utf-8-sig")
        for v, d in lr:
            rows.append(("summary_by_sigungu.csv", v, d))
        print(f"summary_by_sigungu: {base_n} rows, {len(s.columns)} cols (+{len(lr)})")

        # ===== summary_by_sido (aggregate sigungu-level breakdowns up to sido) =====
        K2 = ["year", "sido"]
        s2 = pd.read_csv(f"{SRC}/summary_by_sido.csv", encoding="utf-8-sig")
        base_n2 = len(s2)
        orig2 = list(s2.columns)
        nat2 = nat.groupby(K2 + ["country", "country_en"], as_index=False)["n"].sum()
        visa2 = visa.groupby(K2 + ["visa_code"], as_index=False)["n"].sum()
        lang2 = lang_sg.groupby(K2 + ["language", "language_en"], as_index=False)["count"].sum()
        lr2 = []
        s2 = pivot_merge(s2, K2, nat2, "country", "n", "nat_", lr2, "nationality (summed to sido)", "country_en", keep=keep_nat)
        s2 = pivot_merge(s2, K2, visa2, "visa_code", "n", "visa_", lr2, "visa (summed to sido)", code_labels=code_labels, keep=keep_visa)
        s2 = pivot_merge(s2, K2, lang2, "language", "count", "lang_", lr2, "language demand (summed to sido)", "language_en", keep=keep_lang)
        nenc2 = enc.groupby(K2).size().rename("n_enclaves").reset_index()
        s2 = s2.merge(nenc2, on=K2, how="left"); s2["n_enclaves"] = s2["n_enclaves"].fillna(0).astype(int)
        lr2.append(("n_enclaves", ("Number of enclave (district x nationality) cases in the province that year.",
                                   "그 해 그 시도의 enclave(시군구x국적) 건수.")))
        assert len(s2) == base_n2
        s2 = tidy_types(s2, orig2)
        s2.to_csv(f"{DATA}/summary_by_sido.csv", index=False, encoding="utf-8-sig")
        for v, d in lr2:
            rows.append(("summary_by_sido.csv", v, d))
        print(f"summary_by_sido: {base_n2} rows, {len(s2.columns)} cols (+{len(lr2)})")

        # ===== summary_by_eupmyeondong (multicultural leaf categories) =====
        K3 = ["year", "sido", "sigungu", "eupmyeondong"]
        s3 = pd.read_csv(f"{SRC}/summary_by_eupmyeondong.csv", encoding="utf-8-sig")
        base_n3 = len(s3)
        orig3 = list(s3.columns)
        mc = pd.read_csv(f"{SRC}/multicultural_households.csv", encoding="utf-8-sig")
        mc_leaf = mc[mc["category_level"] == "leaf"].copy()
        keep_mc = top_keep(mc_leaf, "category", "n", TOP_N)
        lr3 = []
        s3 = pivot_merge(s3, K3, mc_leaf, "category", "n", "mc_", lr3, "multicultural_households (leaf)", "category_en", keep=keep_mc)
        assert len(s3) == base_n3
        s3 = tidy_types(s3, orig3)
        s3.to_csv(f"{DATA}/summary_by_eupmyeondong.csv", index=False, encoding="utf-8-sig")
        for v, d in lr3:
            rows.append(("summary_by_eupmyeondong.csv", v, d))
        print(f"summary_by_eupmyeondong: {base_n3} rows, {len(s3.columns)} cols (+{len(lr3)})")

        # ===== national_annual — full national summary at data/ top =====
        na_src = os.path.join(SRC, "national_annual.csv")
        if os.path.exists(na_src):
            na = pd.read_csv(na_src, encoding="utf-8-sig")  # pristine base (indices + counts)
            orig_na = list(na.columns)
            lrn = []
            COMP = ["broad_total", "non_naturalized", "workers", "marriage_migrants", "students",
                    "ethnic_koreans", "other_foreigners", "naturalized", "children"]
            COMP_KO = {"broad_total": "광의 합계", "non_naturalized": "한국국적 미취득", "workers": "외국인근로자",
                       "marriage_migrants": "결혼이민자", "students": "유학생", "ethnic_koreans": "외국국적동포",
                       "other_foreigners": "기타외국인", "naturalized": "한국국적취득자", "children": "외국인주민자녀"}
            # v1.2.0: the release national_annual already carries this block
            # (08_export sums it from summary_by_sido) and the base dictionary
            # documents it, so merging again would duplicate the columns and the
            # dictionary rows. Build it here only from an older release that
            # lacks it.
            if not all(c in na.columns for c in COMP):
                sdo = pd.read_csv(f"{SRC}/summary_by_sido.csv", encoding="utf-8-sig")
                comp = sdo.groupby("year")[COMP].sum(min_count=1).reset_index()
                na = na.merge(comp, on="year", how="left")
                for c in COMP:
                    lrn.append((c, (f"National MOIS broad-definition {c} (sum across districts).",
                                    f"전국 MOIS 광의 {COMP_KO[c]} (시군구 합).")))

            def _g(r, k):
                v = r.get(k)
                return 0 if pd.isna(v) else v

            def _pct(n, d):
                return round(100 * n / d, 2) if d else pd.NA

            def _settle(r):
                tot, w, s, m = _g(r, "broad_total"), _g(r, "workers"), _g(r, "students"), _g(r, "marriage_migrants")
                nat_, ch = _g(r, "naturalized"), _g(r, "children")
                und = _g(r, "non_naturalized") or max(tot - nat_ - ch, 0)
                if not und or not tot:
                    st = ""
                else:
                    w_, s_, m_ = (w / und) / 0.38, (s / und) / 0.16, (m / und) / 0.15
                    mx = max(w_, s_, m_)
                    st = "다목적형(Multi-purpose)" if mx < 1 else ("산업형(Industrial)" if mx == w_ else (
                        "대학·유학형(University)" if mx == s_ else "결혼정주형(Marriage-settled)"))
                return pd.Series({"settlement_rate_pct": _pct(nat_ + ch, tot), "labor_dependence_pct": _pct(w, und),
                                  "marriage_dependence_pct": _pct(m, und), "study_dependence_pct": _pct(s, und),
                                  "settlement_type": st})
            _sett = na.apply(_settle, axis=1)
            _new_sett = [c for c in _sett.columns if c not in na.columns]
            na = pd.concat([na, _sett[_new_sett]], axis=1)
            SETT = {"settlement_rate_pct": ("National settlement rate = (naturalized + children) / broad_total x100.", "전국 정착률 = (귀화+자녀)/광의합 x100."),
                    "labor_dependence_pct": ("National labor dependence = workers / non_naturalized x100.", "전국 노동의존도 = 근로자/미취득 x100."),
                    "marriage_dependence_pct": ("National marriage dependence = marriage_migrants / non_naturalized x100.", "전국 결혼의존도 = 결혼이민/미취득 x100."),
                    "study_dependence_pct": ("National study dependence = students / non_naturalized x100.", "전국 유학의존도 = 유학생/미취득 x100."),
                    "settlement_type": ("National settlement typology from the dependence ratios.", "전국 정착유형(의존비율 기반).")}
            for c, dd_ in SETT.items():
                if c in _new_sett:
                    lrn.append((c, dd_))
            for c in COMP:
                na[c] = pd.to_numeric(na[c], errors="coerce").round(0).astype("Int64")
            # wide national totals (same keep-sets as the summaries, aggregated to the year)
            natN = nat.groupby(["year", "country", "country_en"], as_index=False)["n"].sum()
            visN = visa.groupby(["year", "visa_code"], as_index=False)["n"].sum()
            lanN = lang_sg.groupby(["year", "language", "language_en"], as_index=False)["count"].sum()
            na = pivot_merge(na, ["year"], natN, "country", "n", "nat_", lrn, "nationality (national total)", "country_en", keep=keep_nat)
            na = pivot_merge(na, ["year"], visN, "visa_code", "n", "visa_", lrn, "visa (national total)", code_labels=code_labels, keep=keep_visa)
            na = pivot_merge(na, ["year"], lanN, "language", "count", "lang_", lrn, "language demand (national total)", "language_en", keep=keep_lang)
            na = tidy_types(na, orig_na)
            out_na = os.path.join(DATA, "national_annual.csv")
            na.to_csv(out_na, index=False, encoding="utf-8-sig")
            for v, dd_ in lrn:
                rows.append(("national_annual.csv", v, dd_))
            print(f"national_annual: {len(na)} rows, {len(na.columns)} cols (+{len(lrn)})")

        # ---- extend the data dictionary (idempotent: pristine long dict + wide defs) ----
        typ = lambda v: "integer"  # all attached wide columns are integer counts
        add = pd.DataFrame([(f, v, typ(v), d[0], d[1]) for f, v, d in rows],
                           columns=["file", "variable", "type", "description_en", "description_ko"])
        bad = [v for v in add["variable"] if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v) or len(v) > 32]
        print(f"\nnew column defs: {len(add)} | invalid/over-32 Stata names:", bad if bad else "none")
        base_dict = pd.read_csv(os.path.join(ROOT, "04_dataset_release", "data_dictionary.csv"), encoding="utf-8-sig")
        # v1.2.0: the deposit keeps the release name. v1.1.0 shipped this
        # table as summary_national.csv; the changelog records the rename.
        full = pd.concat([base_dict, add], ignore_index=True)
        full.to_csv(os.path.join(os.path.dirname(DATA), "data_dictionary.csv"), index=False, encoding="utf-8-sig")
        print(f"data_dictionary.csv: {len(base_dict)} base + {len(add)} wide = {len(full)} rows")

    main()



def export_deposit_stata():
    """Write the .dta files that exist only in the deposit.

    The detail tables' Stata versions come straight from the release, but six files
    have no release counterpart: the four summaries carry the wide breakdown columns
    attach_breakdowns() attaches, and the two refugee tables are built here. Their
    .dta files therefore have to be written here, from the deposit's own CSVs and its
    own extended data_dictionary.csv. Skipping this is what leaves fresh summary CSVs
    beside year-old summary DTAs and fails final_qc()'s parity check.

    Labelling goes through 09_finish_release.write_labeled_dta, the same helper the
    release export uses, so a deposit .dta carries a variable label on every column,
    the KIRD dataset label, and dictionary-driven numeric typing. The wide columns are
    labeled from the (file, variable, en/ko) rows attach_breakdowns() already wrote
    into the deposit dictionary. Over-long variable names raise instead of being
    truncated; the wide-column slugs are already capped at Stata's 32 characters.
    """
    fr = _finish_release()
    DICT = os.path.join(DEPOSIT, "data_dictionary.csv")
    if not os.path.exists(DICT):
        raise SystemExit(f"{DICT} missing; attach_breakdowns() must run first")
    meta = fr.load_stata_dict(DICT)

    targets = [(os.path.join(DEPOSIT_DATA, f + ".csv"), f) for f in
               ("national_annual", "summary_by_sido", "summary_by_sigungu",
                "summary_by_eupmyeondong")]
    targets += [(os.path.join(DEPOSIT_DATA, "detailed_data", f + ".csv"), f) for f in
                ("refugee_by_nationality", "refugee_language_demand")]

    absent = [f for path, f in targets if not os.path.exists(path)]
    if absent:
        raise SystemExit(f"deposit CSV(s) missing, cannot write their .dta: {absent}")

    unlabeled = []
    for path, stem in targets:
        df, labels = fr.write_labeled_dta(path, path[:-4] + ".dta", meta)
        unlabeled += [f"{stem}.{c}" for c in df.columns if c not in labels]
        print(f"  {stem}.dta: {len(df):>7,} rows x {len(df.columns)} cols "
              f"({len(labels)} labeled)")
    if unlabeled:
        raise SystemExit("no data_dictionary.csv entry for: " + ", ".join(unlabeled))


def final_qc():
    """Final pre-publish QC for the KIRD openICPSR deposit.
    Checks: (1) file integrity + CSV/DTA parity, (2) cross-level sum consistency,
    (3) within-row identities, (4) official MOJ-figure comparison, (5) wide attach consistency.
    Reports FAILURES and magnitudes; does not modify any file.
    """
    def load(name):
        p = os.path.join(DEP, name)
        return pd.read_csv(p, encoding="utf-8-sig")

    nat   = load("national_annual.csv")
    sido  = load("summary_by_sido.csv")
    sgg   = load("summary_by_sigungu.csv")
    emd   = load("summary_by_eupmyeondong.csv")
    det   = lambda f: pd.read_csv(os.path.join(DEP, "detailed_data", f), encoding="utf-8-sig")

    fams = {
        "nat":      [c for c in nat.columns if c.startswith("nat_")],
        "visa":     [c for c in nat.columns if c.startswith("visa_")],
        "lang":     [c for c in nat.columns if c.startswith("lang_")],
        "childage": [c for c in nat.columns if c.startswith("childage_")],
    }
    broad = ["broad_total","non_naturalized","workers","marriage_migrants","students",
             "ethnic_koreans","other_foreigners","naturalized","children"]

    FAILS = []
    def check(label, ok, detail=""):
        tag = "PASS" if ok else "FAIL"
        if not ok: FAILS.append(label)
        print(f"[{tag}] {label}" + (f"  -- {detail}" if detail else ""))

    print("="*70); print("(1) FILE INTEGRITY + CSV/DTA PARITY"); print("="*70)
    files = ["national_annual","summary_by_sido","summary_by_sigungu","summary_by_eupmyeondong"]
    det_files = ["age_sex_national","children_by_age","ethnic_enclaves","language_demand",
                 "multicultural_households","nationality_by_sigungu","naturalization_annual",
                 "naturalization_by_age","naturalization_by_country","region_segregation",
                 "segregation_by_nationality","visa_by_nationality","visa_by_sigungu"]
    for f in files + det_files:
        sub = "" if f in files else "detailed_data"
        csv_p = os.path.join(DEP, sub, f+".csv")
        dta_p = os.path.join(DEP, sub, f+".dta")
        c = pd.read_csv(csv_p, encoding="utf-8-sig")
        has_dta = os.path.exists(dta_p)
        if has_dta:
            d = pd.read_stata(dta_p)
            ok = (len(c)==len(d)) and (c.shape[1]==d.shape[1])
            check(f"{f}: CSV/DTA parity", ok, f"csv{c.shape} dta{d.shape}")
        else:
            check(f"{f}: DTA exists", False, "no .dta")

    print("\n" + "="*70); print("(2) CROSS-LEVEL SUM CONSISTENCY (wide families)"); print("="*70)
    def cmp_levels(low, high, cols, lname, hname, by=None):
        """sum `cols` over low grouped by year (and `by`), compare to high."""
        cols = [c for c in cols if c in low.columns and c in high.columns]
        if not cols: return
        keys = ["year"] + ([by] if by else [])
        lo = low.groupby(keys)[cols].sum().sum(axis=1)
        if by:
            hi = high.groupby(keys)[cols].sum().sum(axis=1)
        else:
            hi = high.groupby("year")[cols].sum().sum(axis=1)
        j = pd.concat([lo.rename("low"), hi.rename("high")], axis=1).dropna()
        j["gap"] = j["low"] - j["high"]
        j["pct"] = 100*j["gap"]/j["high"].replace(0,np.nan)
        worst = j["pct"].abs().max()
        yr_worst = j["pct"].abs().idxmax()
        ok = worst < 0.5  # tolerance 0.5%
        check(f"Sum {lname} == {hname} [{ '+'.join(c.split('_')[0] for c in [cols[0]]) }* fam]",
              ok, f"max |gap|={worst:.2f}% at {yr_worst} (n={len(cols)} cols)")
        if not ok:
            bad = j[j["pct"].abs()>=0.5].sort_values("pct", key=abs, ascending=False).head(6)
            print("       worst rows:\n" + bad[["low","high","gap","pct"]].to_string())

    for fam, cols in fams.items():
        print(f"-- family: {fam} ({len(cols)} cols) --")
        cmp_levels(sgg,  nat,  cols, "sigungu", "national")
        cmp_levels(sido, nat,  cols, "sido",    "national")
        cmp_levels(sgg,  sido, cols, "sigungu-in-sido", "sido", by="sido")

    print("\n-- broad categories --")
    for col in broad:
        cmp_levels(sgg, nat, [col], f"sigungu.{col}", "national")
    # emd -> sigungu for broad (emd has broad cols)
    print("-- emd -> sigungu (broad_total) --")
    cmp_levels(emd, sgg, ["broad_total"], "emd", "sigungu",
               by=None)

    print("\n" + "="*70); print("(3) WITHIN-ROW IDENTITIES (national)"); print("="*70)
    n = nat.copy()
    n["share_chk"] = 100*n["foreign_total"]/n["total_pop"]
    d = (n["share_chk"]-n["foreign_share_pct"]).abs().max()
    check("national foreign_share_pct == foreign_total/total_pop", d<0.001, f"max abs diff={d:.5f}")

    # broad identities (only on rows where the components are published that year)
    comp5 = ["workers","marriage_migrants","students","ethnic_koreans","other_foreigners"]
    if all(c in n for c in comp5+["non_naturalized","naturalized","children","broad_total"]):
        m5 = n[comp5].notna().all(axis=1)
        nn = n.loc[m5, comp5].sum(axis=1)
        rel1 = (nn - n.loc[m5,"non_naturalized"]).abs()/n.loc[m5,"non_naturalized"].replace(0,np.nan)
        check("national non_naturalized == Σ(work+marr+stud+ethk+other)", rel1.max()<0.001, f"max rel diff={rel1.max():.6f}")
        bt = n["non_naturalized"].fillna(0)+n["naturalized"].fillna(0)+n["children"].fillna(0)
        rel2 = (bt - n["broad_total"]).abs()/n["broad_total"].replace(0,np.nan)
        check("national broad_total == non_naturalized + naturalized + children", rel2.max()<0.001, f"max rel diff={rel2.max():.6f}")

    # Σchildage == children?
    ca = fams["childage"]
    if ca and "children" in n:
        s = n[ca].sum(axis=1)
        rel = (s - n["children"]).abs()/n["children"].replace(0,np.nan)
        check("national Σchildage_* == children", rel.max()<0.02, f"max rel diff={rel.max():.4f}")

    print("\n" + "="*70); print("(4) OFFICIAL MOJ FIGURE COMPARISON"); print("="*70)
    # mois_moj_validation.csv: year,sido,sigungu,moj_n,mois_n
    try:
        v = pd.read_csv(os.path.join(CLEAN,"mois_moj_validation.csv"), encoding="utf-8-sig")
        # The authoritative validation: our national foreign_total must equal the official
        # MOJ national control to the person, every year.
        mj = v.dropna(subset=["moj_n"]).groupby("year")["moj_n"].sum()
        cmpn = pd.concat([nat.set_index("year")["foreign_total"], mj.rename("moj")], axis=1).dropna()
        cmpn["pct"] = 100*(cmpn["foreign_total"]-cmpn["moj"])/cmpn["moj"]
        check("national foreign_total == official MOJ national total (every year)",
              cmpn["pct"].abs().max()<0.01, f"max |diff|={cmpn['pct'].abs().max():.4f}% over {len(cmpn)} yrs")
        # Sigungu-level MOIS vs MOJ divergence is expected and documented: MOIS counts by
        # residence registration (행정구역), MOJ by 체류지; they reconcile only at the
        # national total. Reported for transparency, NOT a pass/fail criterion.
        v2 = v.dropna(subset=["moj_n","mois_n"]).copy()
        if len(v2):
            v2["apct"] = 100*(v2["mois_n"]-v2["moj_n"]).abs()/v2["moj_n"].replace(0,np.nan)
            print(f"   [info] sigungu MOIS vs MOJ: median |diff|={v2['apct'].median():.1f}%, "
                  f"{100*(v2['apct']<5).mean():.0f}% within 5% (expected; different geographic basis)")
    except Exception as e:
        print("   (validation file issue):", e)

    print("\n" + "="*70); print("(5) WIDE ATTACH SANITY (per-level Σfam vs national totals)"); print("="*70)
    for fam, cols in fams.items():
        if not cols:
            print(f"   {fam:9s}: (not attached as wide columns)")
            continue
        cN = nat[cols].sum(axis=1).sum()
        cS = sido[cols].sum(axis=1).sum()
        cG = sgg[cols].sum(axis=1).sum()
        pS = 100*cS/cN if cN else float('nan')
        pG = 100*cG/cN if cN else float('nan')
        print(f"   {fam:9s}: national={cN:,.0f}  Σsido={cS:,.0f} ({pS:.1f}%)  Σsigungu={cG:,.0f} ({pG:.1f}%)")

    print("\n" + "="*70)
    print(f"SUMMARY: {len(FAILS)} FAIL(s)")
    for f in FAILS: print("   FAIL:", f)
    print("="*70)


if __name__ == "__main__":
    # Order matters. stage_release lays the release out in the deposit's shape;
    # attach_breakdowns then overwrites the four summaries with their wide variants
    # and rewrites data_dictionary.csv from scratch, so add_refugee_files has to come
    # after it or its dictionary rows are thrown away; export_deposit_stata needs both
    # the finished dictionary and the finished CSVs; final_qc reads the result.
    stage_release()
    attach_breakdowns()
    add_refugee_files()
    export_deposit_stata()
    final_qc()
