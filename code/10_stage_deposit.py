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
import unicodedata
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

    LICENSE.txt is the deposit's one document: the full CC BY text, where
    04_dataset_release/LICENSE is a two-line pointer. It is seeded once (from the
    published deposit, falling back to the release) and then left alone. From V2
    (2026-09-29) the deposit carries no README; its documentation is the public
    repository's README.md and DATA_NOTES.md.
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
    staged, no_dta, stale = [], [], []
    for f in detail:
        stem = f[:-4]
        src_dta = os.path.join(SRC_DTA, stem + ".dta")
        if not os.path.exists(src_dta):
            no_dta.append(stem)
            continue
        # The .dta is not built here; it is copied from the release. So if the CSV
        # is fixed later, the pair goes into the deposit silently mismatched. Sizes
        # are printed, so it does not catch the eye either (on 2026-08-26
        # nationality_by_sido passed with a .dta one day old). Compare the
        # timestamps and stop loudly.
        if os.path.getmtime(src_dta) < os.path.getmtime(os.path.join(SRC, f)):
            stale.append(stem)
            continue
        shutil.copy2(os.path.join(SRC, f), os.path.join(DETAIL, f))
        shutil.copy2(src_dta, os.path.join(DETAIL, stem + ".dta"))
        staged.append(stem)
        c_sz = os.path.getsize(os.path.join(DETAIL, f))
        d_sz = os.path.getsize(os.path.join(DETAIL, stem + ".dta"))
        print(f"  {stem:34s} {c_sz:>12,} B csv  {d_sz:>12,} B dta")
    if no_dta:
        raise SystemExit(f"no Stata file in {SRC_DTA} for {no_dta}; run phase 2 first")
    if stale:
        raise SystemExit(
            f"Stata file older than its CSV for {stale}; rerun export_stata "
            f"(09_finish_release.export_stata) before staging")

    # Drop anything left from an earlier release that this one no longer produces,
    # so the deposit cannot ship a table the dictionary does not document.
    keep = {stem + ext for stem in staged for ext in (".csv", ".dta")}
    stale = sorted(f for f in os.listdir(DETAIL)
                   if f not in keep and not f.startswith(DEPOSIT_ONLY))
    for f in stale:
        os.remove(os.path.join(DETAIL, f))
        print(f"  removed stale {f}")

    # The top four are cleaned for the same reason. After a rename, the file under
    # the old name would remain and the same table would ship under two names.
    # Any file, not only .csv/.dta: final_qc now holds the whole tree to the
    # dictionary (2026-09-27).
    top_keep = {f for f in TOP_LEVEL}
    top_keep |= {f[:-4] + ".dta" for f in TOP_LEVEL}
    top_stale = sorted(f for f in os.listdir(DEPOSIT_DATA)
                       if os.path.isfile(os.path.join(DEPOSIT_DATA, f)) and f not in top_keep)
    for f in top_stale:
        os.remove(os.path.join(DEPOSIT_DATA, f))
        print(f"  removed stale {f} (data/ top level)")

    # 2026-09-29: no README in the deposit from V2 on (Nari); the documentation is the
    # public repository's README.md and DATA_NOTES.md
    for name, sources in (
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
    shares from Ethnologue 24 (SIL Global 2021), Korean excluded, in kird's exact
    integer units and rounded once. The nationality counts are the refugee_data lists
    in data.json and the shares country_language_shares.json (the table
    language_weights.csv publishes); English language labels are taken from the same
    lang_ko_en.json the deposit uses, then from the dashboard's refugee block.
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
        # One label per country, the one crosswalk_country.csv and every other
        # nationality table use. The refugee list printed Russia as "러시아", so this
        # was the one file whose country column did not join to the crosswalk.
        from kird import COUNTRY_CANONICAL
        # Each list is the bulletin's ten named nationalities; the bulletin prints an
        # eleventh line, "기타", for everyone else (tables 11, 14 and 15 of
        # "94_24년 난민 신청 및 심사 통계" (refugee application and review statistics
        # 1994-2024): 40,560 of 122,095 applicants, 263 of 1,544 recognized, 251 of
        # 2,696 humanitarian). Until 2026-09-27 (second-round cross-check) the file
        # stopped at ten, so its rows summed 9-33% short of the totals the dictionary
        # quotes. "기타" is the cumulative total less the ten, and the rows of a status must
        # add up to that total.
        TOTAL = {"신청": rd["cumulative"]["applications_total"],
                 "난민인정": rd["cumulative"]["recognized_total"],
                 "인도적체류": rd["cumulative"]["humanitarian_total"]}
        for status, lst in nat_src:
            for ko, en, count, pct in lst:
                nat_rows.append([status, STATUS_EN[status],
                                 COUNTRY_CANONICAL.get(ko, ko), en, count, pct])
            rest = int(TOTAL[status]) - sum(int(c) for _, _, c, _ in lst)
            if rest < 0 or len(lst) != 10:
                raise SystemExit(f"refugee {status}: {len(lst)} named lines summing above "
                                 f"the cumulative total {TOTAL[status]}")
            nat_rows.append([status, STATUS_EN[status], "기타", "Other", rest,
                             round(100 * rest / int(TOTAL[status]), 1)])
        for status in TOTAL:
            got = sum(r[4] for r in nat_rows if r[0] == status)
            if got != int(TOTAL[status]):
                raise SystemExit(f"refugee_by_nationality {status}: rows sum to {got}, "
                                 f"not {TOTAL[status]}")
        write_csv(os.path.join(DETAIL, "refugee_by_nationality.csv"),
                  ["status", "status_en", "country", "country_en", "count", "share_pct"],
                  nat_rows)

        # ---- 2) refugee_language_demand.csv (estimated, Ethnologue L1 split) ----
        # Each status's ten named nationalities x their first-language shares, summed
        # in kird.language_estimate's exact integer units and rounded once, half up, to
        # whole persons; the 20 largest languages per status, a language kept only
        # when its sum before rounding reaches one person, as in language_demand. "보호"
        # (protected) is recognized + humanitarian, ranked on its own sum. Third-round
        # cross-check (2026-09-27): the counts were read from data.json's refugee block,
        # already rounded to one decimal, and rounded again, so recognized Amharic
        # (49.49) read 50, humanitarian Armenian (4.50) 5, and Assyrian (13.48) 14 in
        # two statuses.
        from kird import LANG_UNIT, language_estimate, lang_persons
        shares = json.load(open(os.path.join(ROOT, "03_cleaned_data",
                                             "country_language_shares.json"),
                                encoding="utf-8"))
        ld = rd["language_demand"]
        ld_en = {d["language"]: d.get("language_en") for lst in ld.values() for d in lst}
        counts = {}
        for status, key in (("난민인정", "top_recognized_nationalities"),
                            ("인도적체류", "top_humanitarian_nationalities")):
            c_ = {}
            for ko, _en, n, _pct in rd.get(key, []):
                c = COUNTRY_CANONICAL.get(ko, ko)
                c = c if c in shares else ko
                if c not in shares:
                    raise SystemExit(f"refugee {status}: {ko} has no first-language shares")
                c_[c] = c_.get(c, 0) + int(n)
            counts[status] = c_
        counts["보호"] = {c: counts["난민인정"].get(c, 0) + counts["인도적체류"].get(c, 0)
                        for c in set(counts["난민인정"]) | set(counts["인도적체류"])}
        lang_rows = []
        TOP_N = 20
        for status in ("난민인정", "인도적체류", "보호"):
            skey = STATUS_EN[status]
            est = language_estimate(counts[status], shares)
            for src, u in sorted(est.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]:
                if u < LANG_UNIT:
                    continue
                count = lang_persons(u)
                if src in LANG_LABEL:
                    ko, en = LANG_LABEL[src]
                else:
                    ko = src
                    en = lang_en.get(src) or ld_en.get(src) or src
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

        # "보호" is ranked on its own combined population, so its top 20 need not be the
        # union of the other two statuses' lists (first-round fix, 2026-09-26: the
        # dictionary said "top 20 per status" and "recognized + humanitarian" without
        # saying the two interact). The sums are read from the rows just written.
        tot = {}
        for st, _, _, _, n_ in lang_rows:
            tot[st] = tot.get(st, 0) + n_
        rec_, hum_, pro_ = tot.get("난민인정", 0), tot.get("인도적체류", 0), tot.get("보호", 0)
        # ---- 3) append data dictionary rows (file, variable, type, en, ko) ----
        new_dict = [
            ["refugee_by_nationality.csv", "status / status_en", "string",
             "Refugee-process outcome: 신청 applicant, 난민인정 recognized, 인도적체류 humanitarian (Korean + English).",
             "난민 절차 구분: 신청/난민인정/인도적체류(한글+영문)."],
            ["refugee_by_nationality.csv", "country / country_en", "string",
             "Nationality (Korean + English): the ten nationalities MOJ names per status, and the bulletin's own eleventh line 기타 / Other for every other nationality, so each status sums to its cumulative total.",
             "국적(한글+영문). 구분마다 법무부가 이름을 적은 10개 국적과, 나머지 국적 모두를 담은 자료 자체의 열한 번째 줄 「기타 / Other」. 그래서 구분마다 합이 누적 총계와 같다."],
            ["refugee_by_nationality.csv", "count", "integer",
             "Cumulative cases 1994-2024 for that status and nationality (MOJ top-10 per status plus the 기타 line; each status sums to its national total: 122,095 applied / 1,544 recognized / 2,696 humanitarian), as MOJ's bulletin of February 2025 (1994-2024 난민 신청 및 심사 통계) prints them. MOJ's next bulletin (난민 종합 통계), which runs a year further, revises the 2023 and 2024 humanitarian permits from 125 and 101 to 119 and 97, so its cumulative count through 2024 is 2,686 (by nationality, e.g. 아이티 116 and 아프가니스탄 31 against 117 and 34 here), and the 2024 applications from 18,336 to 18,335; recognized refugees are the same in both.",
             "1994-2024 누적 건수(MOJ 구분별 top-10 과 기타 줄; 구분마다 합이 전체와 같다: 신청 122,095·인정 1,544·인도적 2,696). 법무부 2025년 2월 자료(1994-2024 난민 신청 및 심사 통계) 그대로다. 한 해를 더 싣는 법무부의 다음 자료(난민 종합 통계)는 2023·2024년 인도적체류 허가를 125·101 에서 119·97 로 고쳐 2024년까지 누적이 2,686 이고(국적별로는 예컨대 아이티 116, 아프가니스탄 31; 여기서는 117, 34), 2024년 신청을 18,336 에서 18,335 로 고쳤다. 난민인정은 두 자료가 같다."],
            ["refugee_by_nationality.csv", "share_pct", "float",
             "Nationality's percent of that status's cumulative total.",
             "해당 구분 누적 총계 대비 국적 비중(%)."],
            ["refugee_language_demand.csv", "status / status_en", "string",
             "Protected population: 난민인정 recognized, 인도적체류 humanitarian, 보호 protected (recognized + humanitarian). 보호 is computed on the combined population and then cut to its own top 20 languages, so its rows are not the sum of the other two statuses' rows: a language in one status's top 20 can fall outside 보호's (치타공어, 10 recognized, has no 보호 row), and 보호 summed over its rows is %s against %s + %s = %s for the other two." % (format(pro_, ","), format(rec_, ","), format(hum_, ","), format(rec_ + hum_, ",")),
             "보호 인구 구분: 난민인정/인도적체류/보호(난민인정+인도적체류). 보호는 합친 인구로 계산한 뒤 제 상위 20개 언어로 자르므로, 그 행은 다른 두 구분의 행을 더한 것이 아니다. 한 구분의 상위 20에 든 언어가 보호의 상위 20 밖에 있을 수 있고(치타공어: 난민인정 10명, 보호 행 없음), 보호 행의 합은 %s 으로 다른 두 구분의 %s + %s = %s 와 다르다." % (format(pro_, ","), format(rec_, ","), format(hum_, ","), format(rec_ + hum_, ","))],
            ["refugee_language_demand.csv", "language / language_en", "string",
             "Estimated first language (Korean + English).", "추정 모어(한글+영문)."],
            ["refugee_language_demand.csv", "count", "integer",
             "Estimated speakers = cumulative nationality count x that country's L1 (mother-tongue) share (Ethnologue 24, SIL Global 2021; the shares are language_weights.csv), summed over nationalities and rounded once, half up, to whole persons; Korean excluded. Top 20 languages per status, a language kept only when its sum before rounding reaches one person. Every row re-derives from refugee_by_nationality.csv and language_weights.csv (qc_deposit_staging.py checks it; until 2026-09-27 the counts were rounded twice and four rows were one person high). Built from the published top-10 nationalities only: the 기타 line of refugee_by_nationality names no nationality and is not allocated to a language (approximation of the full population's interpretation demand).",
             "추정 화자수 = 누적 국적 인원 x 해당국 L1 모어 share(Ethnologue 24; 비중은 language_weights.csv) 를 국적마다 더한 뒤 한 번만, 반올림(0.5 올림)으로 사람 수; 한국어 제외. 구분별 상위 20개 언어이고, 반올림 전 합이 1명에 이르는 언어만 싣는다. 모든 행이 refugee_by_nationality.csv 와 language_weights.csv 에서 다시 나온다(qc_deposit_staging.py 가 본다; 2026-09-27 까지는 두 번 반올림해 네 행이 1명 많았다). 공개 top-10 국적만 반영하며, refugee_by_nationality 의 기타 줄은 국적이 없어 언어로 나누지 않는다(근사치)."],
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
    A category the year's table does report is 0, not blank, where the place has
    none of it.

    Nationality is cut to the 49 largest nationalities by name plus nat_other,
    everyone else. The lines that name no nationality (kird.RESIDUAL_LINES) are never
    ranked as if they were a country: until 2026-09-27 (second-round cross-check) the
    raw "기타" column won a top-50 slot on its 2008-2013 volume and became nat_other, so
    the column held that one raw column and nothing else (blank in every row of
    2014-2016, 2019 and 2021; in 2017 Gyeonggi-do 41 against 2,582 people outside the named columns)
    and the nat_* columns of a row did not add up to registered_foreigners.

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
        # Strip accents first. Otherwise [^A-Za-z0-9] turns them into underscores and
        # `Türkiye` becomes `nat_t_rkiye` (found in the deposit on 2026-08-26).
        # More names fall into the same trap, such as Côte d'Ivoire.
        lab = unicodedata.normalize("NFKD", str(label).strip())
        lab = "".join(ch for ch in lab if not unicodedata.combining(ch))
        s = re.sub(r"[^A-Za-z0-9]+", "_", lab.lower()).strip("_")
        name = (prefix + s)[:32].rstrip("_")
        base, i = name, 1
        while name in used or not name:
            suf = f"_{i}"
            name = (base[:32 - len(suf)] + suf).strip("_")
            i += 1
        used.add(name)
        return name


    def top_keep(long_df, cat_col, val_col, n=50, exclude=()):
        """Set of the top-n category values (as str) by total val across the breakdown,
        leaving out the values in `exclude`."""
        tot = long_df.groupby(long_df[cat_col].astype(str))[val_col].sum().sort_values(ascending=False)
        tot = tot[~tot.index.isin(set(exclude))]
        return set(tot.head(n).index)

    # The computed residual of the nationality columns: everyone outside the named
    # ones, the lines that name no nationality included. Its English label slugs to
    # nat_other, the name the column has always had.
    OTHER_KO, OTHER_EN = "그 밖의 국적", "Other"

    def fold_other(long_df, keep, cat_col="country", en_col="country_en", val_col="n"):
        """The long nationality table with every category outside `keep` summed into
        one OTHER_KO / OTHER_EN line, so the pivot carries a real residual."""
        d = long_df.copy()
        out = ~d[cat_col].astype(str).isin(keep)
        d.loc[out, cat_col] = OTHER_KO
        if en_col in d.columns:
            d.loc[out, en_col] = OTHER_EN
        keys = [c for c in d.columns if c != val_col]
        return d.groupby(keys, as_index=False, dropna=False)[val_col].sum()

    def zero_fill(wide, long_df, cat_col, prefix, namemap_rows, year_col="year"):
        """0, not blank, in a wide column for the years whose long table reports that
        category somewhere: the district tables print a full grid of the categories
        they list, and the long files omit zeros. A category a year's table does not
        list (2008-2013: every nationality outside the national top 19) stays blank."""
        listed = long_df.groupby(year_col)[cat_col].apply(lambda s: set(map(str, s)))
        for fn, ko in namemap_rows:
            if fn not in wide.columns:
                continue
            yrs = {y for y, cats in listed.items() if ko in cats}
            if ko == OTHER_KO:        # the residual is computed, so it always exists
                yrs = set(listed.index)
            m = wide[year_col].isin(yrs) & wide[fn].isna()
            wide.loc[m, fn] = 0
        return wide


    def tidy_types(df, orig_cols):
        """Clean numeric types so the CSV shows 1234 and blank, not 1234.0.

        Two groups. The wide columns this script attaches are all integer counts.
        The columns that came in from the release also need it: `pd.read_csv`
        promotes any integer column that has a blank to float64, and writing that
        back puts a `.0` on every value. The release file has `adm_code` 3203062
        and the deposit copy had 3203062.0 — a GIS join key with a decimal point,
        plus every MOIS count in the sub-district file (2026-08-26). Integer-valued
        release columns are restored to nullable Int64; anything with a real
        fraction (the *_pct rates) is left alone.
        """
        WIDE = ("nat_", "visa_", "childage_", "mc_", "lang_")
        for c in df.columns:
            if c not in orig_cols:
                if c.startswith(WIDE):
                    df[c] = pd.to_numeric(df[c], errors="coerce").round(0).astype("Int64")
                continue
            if not pd.api.types.is_float_dtype(df[c]):
                continue
            v = df[c].dropna()
            if len(v) and (v == v.round(0)).all():
                df[c] = df[c].astype("Int64")
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
                    src, cat_en_col=None, code_labels=None, keep=None, names_out=None):
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
            if names_out is not None:
                names_out.append((fn, ko))
            if code_labels and ko in code_labels:        # visa: ko is the code; look up label
                lk, le = code_labels[ko]
                # the code goes in too: final_qc reads it back to compare the column
                # with visa_national, and a label alone does not name one code
                label_rows.append((fn, en_desc(prefix, le, "%s, %s" % (lk, ko), src)))
            else:
                label_rows.append((fn, en_desc(prefix, en, ko, src)))
        return out


    def en_desc(prefix, en, ko, src):
        kind = {"nat_": "nationality", "visa_": "visa status", "lang_": "language",
                "childage_": "children aged", "mc_": "multicultural category"}[prefix]
        src_en, src_ko = src if isinstance(src, tuple) else (src, src)
        if prefix == "nat_" and ko == OTHER_KO:
            # final_qc reads the last (...) before ". From" as the category; this one
            # is the residual, and says so in the same slot.
            en_d = (f"Count for nationality: everyone outside the 49 nationalities that "
                    f"have a nat_* column of their own, the lines that name no "
                    f"nationality (무국적, 미등록국가, 기타, 국제연합, ...) included, so the "
                    f"nat_* columns of a row add up to its registered foreigners "
                    f"({OTHER_KO}). From {src_en}; blank only where the row carries no "
                    f"nationality column at all (the province rows of 2006-2007, which "
                    f"precede the district tables).")
            ko_d = (f"nat_* 열을 따로 가진 49개 국적 밖의 모든 사람({OTHER_KO}). 국적 "
                    f"없는 줄(무국적, 미등록국가, 기타, 국제연합 등)을 포함하므로 한 행의 "
                    f"nat_* 열을 더하면 등록외국인과 같다. 출처 {src_ko}. 국적 열이 하나도 "
                    f"없는 행(시군구 표보다 앞선 2006-2007년 시도 행)에서만 빈칸.")
            return (en_d, ko_d)
        en_d = (f"Count for {kind}: {en} ({ko}). From {src_en}; 0 where that year's "
                f"table reports the category and the place has none; blank = not "
                f"separately reported that year.")
        ko_d = (f"{kind} {ko}({en}) 인원수. 출처 {src_ko}; 그 해 표가 싣는 범주인데 "
                f"없으면 0, 공백=그 해 별도 미보고.")
        if prefix in ("lang_", "mc_", "childage_"):
            en_d = f"Count for {kind}: {en} ({ko}). From {src_en}; blank = not separately reported."
            ko_d = f"{kind} {ko}({en}) 인원수. 출처 {src_ko}; 공백=별도 미보고."
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
        # 49 nationalities by name, ranked without the lines that name no nationality,
        # and nat_other for everyone else (see the docstring).
        from kird import RESIDUAL_LINES
        keep_nat = top_keep(nat, "country", "n", TOP_N - 1, exclude=RESIDUAL_LINES)
        keep_nat_all = keep_nat | {OTHER_KO}
        keep_visa = top_keep(visa, "visa_code", "n", TOP_N)
        keep_lang = top_keep(lang_sg, "language", "count", TOP_N)
        nat_f = fold_other(nat, keep_nat)

        # ===== summary_by_sigungu =====
        K = ["year", "sido", "sigungu"]
        s = pd.read_csv(f"{SRC}/summary_by_sigungu.csv", encoding="utf-8-sig")
        base_n = len(s)
        orig = list(s.columns)
        lr = []
        nm_nat, nm_visa = [], []
        s = pivot_merge(s, K, nat_f, "country", "n", "nat_", lr, "nationality_by_sigungu", "country_en",
                        keep=keep_nat_all, names_out=nm_nat)
        s = pivot_merge(s, K, visa, "visa_code", "n", "visa_", lr, "visa_by_sigungu", code_labels=code_labels,
                        keep=keep_visa, names_out=nm_visa)
        s = zero_fill(s, nat_f, "country", "nat_", nm_nat)
        s = zero_fill(s, visa, "visa_code", "visa_", nm_visa)
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
        s2 = pd.read_csv(f"{SRC}/summary_by_sido.csv", encoding="utf-8-sig",
                         dtype={"sido_code": str})
        base_n2 = len(s2)
        orig2 = list(s2.columns)

        # 2026-09-26 (third cross-check): a district's values go to the province it
        # belonged to that year, the first two digits of its sigungu_code, which is the
        # boundary summary_by_sido's own counts use. Summing on the district files'
        # continuous label put Gunwi-gun into Daegu for 2008-2022, so the row's nat_*
        # columns held 576 people (2015) its registered_foreigners did not, and left
        # Sejong-si 2008-2011 with no row to land on.
        code2name = {(int(y), str(c)): n for y, c, n in s2[["year", "sido_code", "sido"]].values
                     if isinstance(c, str) and c}

        def to_prov(df):
            pre = df["sigungu_code"].map(lambda v: "" if v != v else str(v).split(".")[0][:2])
            return df.assign(sido=[code2name.get((int(y), p_), sd)
                                   for y, p_, sd in zip(df["year"], pre, df["sido"])])

        nat2 = to_prov(nat_f).groupby(K2 + ["country", "country_en"], as_index=False)["n"].sum()
        visa2 = to_prov(visa).groupby(K2 + ["visa_code"], as_index=False)["n"].sum()
        lang2 = to_prov(lang_sg).groupby(K2 + ["language", "language_en"], as_index=False)["count"].sum()
        lr2 = []
        nm_nat2, nm_visa2 = [], []
        s2 = pivot_merge(s2, K2, nat2, "country", "n", "nat_", lr2, "nationality (summed to sido)", "country_en",
                         keep=keep_nat_all, names_out=nm_nat2)
        s2 = pivot_merge(s2, K2, visa2, "visa_code", "n", "visa_", lr2, "visa (summed to sido)", code_labels=code_labels,
                         keep=keep_visa, names_out=nm_visa2)
        # the same years as the district rows: a category listed anywhere that year
        s2 = zero_fill(s2, nat_f, "country", "nat_", nm_nat2)
        s2 = zero_fill(s2, visa, "visa_code", "visa_", nm_visa2)
        s2 = pivot_merge(s2, K2, lang2, "language", "count", "lang_", lr2, "language demand (summed to sido)", "language_en", keep=keep_lang)
        nenc2 = to_prov(enc).groupby(K2).size().rename("n_enclaves").reset_index()
        s2 = s2.merge(nenc2, on=K2, how="left"); s2["n_enclaves"] = s2["n_enclaves"].fillna(0).astype(int)
        lr2.append(("n_enclaves", ("Number of enclave (district x nationality) cases in the province that year.",
                                   "그 해 그 시도의 enclave(시군구x국적) 건수.")))
        assert len(s2) == base_n2

        # Gate on sums across levels. The README says the wide columns are "the
        # district values summed". The district panel carries Sejong continuously from
        # 2008, while the province panel carries it from 2012, when Sejong was created.
        # So in 2008-2011 Sejong has no province row to land on and that amount
        # silently disappears (found 2026-08-26; 52-56 columns differed in those years,
        # and the difference equalled the Sejong values, to the person, every year).
        #
        # Sejong is not inserted as a province in years it did not exist. Sejong
        # Special Self-Governing City was created in July 2012, and making a province
        # for earlier years would put the data at odds with administrative fact.
        # Instead, only **the share of districts with no province row to land on** is
        # taken out before comparing. Any other leak stops the build. Sejong is not
        # hardcoded, so this works unchanged for other reorganizations.
        wide2 = [c for c in s2.columns
                 if c not in orig2 and c != "n_enclaves" and c in s.columns]
        have = set(map(tuple, s2[K2].values.tolist()))
        sp = to_prov(s)
        orphan = sp[[not (r in have) for r in map(tuple, sp[K2].values.tolist())]]
        lo = s.groupby("year")[wide2].sum()
        hi = s2.groupby("year")[wide2].sum()
        off = (orphan.groupby("year")[wide2].sum()
               .reindex(lo.index).fillna(0) if len(orphan) else 0)
        leak = (lo - hi - off).abs()
        if float(leak.max().max() if len(leak) else 0) > 0:
            bad = leak.stack()
            bad = bad[bad > 0].sort_values(ascending=False)
            raise SystemExit(
                "summary_by_sido wide columns: %d differences not explained by "
                "districts with no province row, largest %s"
                % (len(bad), bad.head(3).to_dict()))
        if len(orphan):
            miss = sorted({(int(r["year"]), r["sido"]) for _, r in orphan.iterrows()})
            print("summary_by_sido: wide columns exclude %s "
                  "(no province row that year; the district rows do carry them)"
                  % ", ".join("%d %s" % m for m in miss))

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
            na = pd.read_csv(na_src, encoding="utf-8-sig",   # pristine base (indices + counts)
                             float_precision="round_trip")  # keeps the release's digits
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
            # Wide national columns, same keep-sets as the summaries.
            # nat_* and visa_* come from the national tables (population =
            # registered): the published national count, full nationality detail in
            # every year. Until 2026-09-26 (fourth cross-check) they were the district tables
            # summed to the year, which left 184 year x nationality cells blank in
            # 2008-2013, when the district tables list only the top 19 per district
            # (nat_korean_chinese 2008: blank against 362,920), put Korean-Chinese into
            # nat_china in 2008 (483,577 against 121,754), and dropped the people
            # the yearbook places in no district. lang_* stays the sum of the
            # district rows of language_demand: the national scope of that file is
            # on the staying basis, a different population from every other column
            # of this row, and no registered-basis national language table exists.
            nn_ = pd.read_csv(f"{SRC}/nationality_national.csv", encoding="utf-8-sig")
            vn_ = pd.read_csv(f"{SRC}/visa_national.csv", encoding="utf-8-sig")
            natN = fold_other(nn_[nn_["population"] == "registered"]
                              .groupby(["year", "country", "country_en"], as_index=False)["n"].sum(),
                              keep_nat)
            visN = (vn_[vn_["population"] == "registered"]
                    .groupby(["year", "visa_code"], as_index=False)["n"].sum())
            lanN = lang_sg.groupby(["year", "language", "language_en"], as_index=False)["count"].sum()
            nm_natN, nm_visN = [], []
            na = pivot_merge(na, ["year"], natN, "country", "n", "nat_", lrn,
                             ("nationality_national (population = registered; the published "
                              "national count, including people placed in no district)",
                              "nationality_national (population = registered; 공표 전국 수, "
                              "시군구가 적히지 않은 사람 포함)"),
                             "country_en", keep=keep_nat_all, names_out=nm_natN)
            na = pivot_merge(na, ["year"], visN, "visa_code", "n", "visa_", lrn,
                             ("visa_national (population = registered; the published "
                              "national count)",
                              "visa_national (population = registered; 공표 전국 수)"),
                             code_labels=code_labels, keep=keep_visa, names_out=nm_visN)
            na = zero_fill(na, natN, "country", "nat_", nm_natN)
            na = zero_fill(na, visN, "visa_code", "visa_", nm_visN)
            na = pivot_merge(na, ["year"], lanN, "language", "count", "lang_", lrn,
                             ("language_demand scope = sigungu summed over districts "
                              "(registered, district-allocated basis; each district "
                              "carries its top ~20 languages, so this is a lower bound; "
                              "the national scope rows are on the staying basis)",
                              "language_demand 의 sigungu 범위를 전국으로 더한 것(등록·시군구 "
                              "배정 기준; 시군구마다 상위 ~20개 언어만 실으므로 하한; national "
                              "범위 행은 체류 기준)"),
                             "language_en", keep=keep_lang)
            na = tidy_types(na, orig_na)
            out_na = os.path.join(DATA, "national_annual.csv")
            na.to_csv(out_na, index=False, encoding="utf-8-sig")
            for v, dd_ in lrn:
                rows.append(("national_annual.csv", v, dd_))
            print(f"national_annual: {len(na)} rows, {len(na.columns)} cols (+{len(lrn)})")

        # ---- extend the data dictionary (idempotent: pristine long dict + wide defs) ----
        # Not every added column is a wide integer count. national_annual also gets
        # the settlement block here: settlement_type is a string and *_pct are floats.
        # Typing them all as integer makes the Stata writer force that type and the
        # string values become missing wholesale (17 rows of settlement_type in
        # national_annual.dta, 2026-08-26).
        def typ(v):
            if v == "settlement_type":
                return "string"
            if v.endswith("_pct"):
                return "float"
            return "integer"
        add = pd.DataFrame([(f, v, typ(v), d[0], d[1]) for f, v, d in rows],
                           columns=["file", "variable", "type", "description_en", "description_ko"])
        # Two wide columns were renamed between v1.1.0 and v1.2.0: the old slug()
        # dropped the accented letter, so v1.1.0 shipped nat_t_rkiye and lang_t_y.
        # Say so on the rows, as index_base_k's row does for n_nationalities.
        # 2026-09-26.
        RENAMED = {"nat_turkiye": "nat_t_rkiye", "lang_tay": "lang_t_y"}
        for v_new, v_old in RENAMED.items():
            m = add["variable"] == v_new
            add.loc[m, "description_en"] += (" This column carried the name %s through "
                                             "v1.1.0." % v_old)
            add.loc[m, "description_ko"] += " v1.1.0 까지 이름은 %s 였다." % v_old
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
    """Final pre-publish QC for the KIRD openICPSR deposit: the gate.

    Every check below is a pass/fail check; the function exits 1 when any fails, so
    `run_pipeline.py --phase 3` stops there. It modifies no file.

      (1) File integrity and CSV/DTA parity: the staging tree holds exactly the
          files the dictionary documents plus the three documents; every CSV under
          data/ and data/detailed_data/ has a .dta twin and no .dta lacks a CSV; each
          pair has the same columns in the same order and the same values, cell by
          cell.
      (2) Cross-level sums of the wide columns: sigungu sums to sido for every
          nat_*, visa_* and lang_* column, province by province (a district counts
          in the province of its sigungu_code that year); sido sums to national for
          lang_*; sigungu against national for nat_* and visa_* from 2014, within
          0.5% a year (the national columns are the published counts, which include
          the people the yearbook places in no district); the MOIS broad columns,
          sigungu against national and eup/myeon/dong against sigungu, within 0.5%.
      (3) Within-row identities at every level: foreign_share_pct =
          100 x foreign count / Korean population; broad_total = non_naturalized +
          naturalized + children and non_naturalized = its five components, to one
          person, wherever the parts are published.
      (4) Comparison against the published MOJ figures: national_annual's nat_* and
          visa_* equal nationality_national / visa_national (population =
          registered) cell by cell (nat_other: the total less the 49 named), and
          national foreign_total equals the district total of the MOJ validation
          file every year; and the nat_* columns of every row add up to its
          registered foreigners (a province's, to its districts'), with nat_other
          never blank.
      (5) Wide-attach consistency: every wide column on a sido or sigungu file also
          sits on national_annual with the same name, and no wide column is blank in
          every row.

    Until 2026-09-26 this printed "SUMMARY: N FAIL(s)" and returned None whatever N
    was, (1) compared shapes only and for 17 of the 28 tables, (3) looked at the
    national row only, (4) swallowed a missing validation file, and (5) printed
    totals without judging them.
    """
    def load(name):
        p = os.path.join(DEP, name)
        return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)

    nat   = load("national_annual.csv")
    sido  = load("summary_by_sido.csv")
    sgg   = load("summary_by_sigungu.csv")
    emd   = load("summary_by_eupmyeondong.csv")
    det   = lambda f: pd.read_csv(os.path.join(DEP, "detailed_data", f),
                                  encoding="utf-8-sig", low_memory=False)

    def fam(df, p):
        return [c for c in df.columns if c.startswith(p)]
    fams = {"nat": "nat_", "visa": "visa_", "lang": "lang_"}
    broad = ["broad_total","non_naturalized","workers","marriage_migrants","students",
             "ethnic_koreans","other_foreigners","naturalized","children"]

    FAILS = []
    def check(label, ok, detail=""):
        tag = "PASS" if ok else "FAIL"
        if not ok: FAILS.append(label)
        print(f"[{tag}] {label}" + (f"  -- {detail}" if detail else ""))

    print("="*70); print("(1) FILE INTEGRITY + CSV/DTA PARITY"); print("="*70)
    # 2026-09-27 (second-round cross-check): the staging tree holds exactly the documented files.
    # Four scratch files (cw_dump.csv, x_gender_2019.csv, types_dump.csv,
    # ages_dump.txt) sat in detailed_data/ after an investigation, and no check
    # looked at anything but the .csv/.dta pairs the dictionary names.
    dd_ = pd.read_csv(os.path.join(DEPOSIT, "data_dictionary.csv"), encoding="utf-8-sig",
                      dtype=str, keep_default_na=False)
    tables = {p_.strip()[:-4] for f_ in dd_["file"] for p_ in f_.split("/")
              if p_.strip().endswith(".csv")}
    expected = {"LICENSE.txt", "data_dictionary.csv"}
    for t in tables:
        sub = "data" if t + ".csv" in TOP_LEVEL else os.path.join("data", "detailed_data")
        expected |= {os.path.normpath(os.path.join(sub, t + e)) for e in (".csv", ".dta")}
    found, odd = set(), []
    for dirpath, dirnames, filenames in os.walk(DEPOSIT):
        for fn in filenames:
            found.add(os.path.normpath(os.path.relpath(os.path.join(dirpath, fn), DEPOSIT)))
        for dn in dirnames:
            rel = os.path.normpath(os.path.relpath(os.path.join(dirpath, dn), DEPOSIT))
            if rel not in ("data", os.path.join("data", "detailed_data")):
                odd.append(rel)
    check("staging tree holds exactly the documented files",
          found == expected and not odd,
          f"would ship {sorted(found - expected)[:6]}, missing {sorted(expected - found)[:6]}, "
          f"folders {odd[:3]}")
    pairs = []
    for sub in ("", "detailed_data"):
        folder = os.path.join(DEP, sub)
        names = os.listdir(folder)
        csvs = {f[:-4] for f in names if f.endswith(".csv")}
        dtas = {f[:-4] for f in names if f.endswith(".dta")}
        check(f"data/{sub + '/' if sub else ''}: every CSV has a .dta and every .dta a CSV",
              csvs == dtas, f"csv only {sorted(csvs - dtas)}, dta only {sorted(dtas - csvs)}")
        pairs += [(sub, f) for f in sorted(csvs & dtas)]
    check("28 tables staged", len(pairs) == 28, f"{len(pairs)}")
    for sub, f in pairs:
        c = pd.read_csv(os.path.join(DEP, sub, f + ".csv"), encoding="utf-8-sig",
                        low_memory=False)
        d = pd.read_stata(os.path.join(DEP, sub, f + ".dta"))
        if list(c.columns) != list(d.columns) or len(c) != len(d):
            check(f"{f}: CSV/DTA parity", False, f"csv{c.shape} dta{d.shape}")
            continue
        bad = 0
        for col in c.columns:
            a, b = c[col], d[col]
            if (pd.api.types.is_bool_dtype(a)
                    or set(map(str, b.dropna().unique())) <= {"True", "False"}):
                m = (a.fillna("").astype(str).str.lower()
                     != b.fillna("").astype(str).str.lower())
            elif pd.api.types.is_numeric_dtype(a) or pd.api.types.is_numeric_dtype(b):
                an = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
                bn = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
                m = ~np.isclose(an, bn, rtol=0, atol=1e-9, equal_nan=True)
            else:
                m = (a.fillna("").astype(str).str.strip()
                     != b.fillna("").astype(str).str.strip())
            bad += int(np.asarray(m).sum())
        check(f"{f}: CSV/DTA parity (shape, columns, values)", bad == 0,
              f"{c.shape}, {bad} cells differ" if bad else f"{c.shape}")

    print("\n" + "="*70); print("(2) CROSS-LEVEL SUMS"); print("="*70)
    _c = lambda v: "" if v != v else str(v).split(".")[0]
    sgg_p = sgg.assign(_prov=sgg["sigungu_code"].map(lambda v: _c(v)[:2]))
    sido_p = sido.assign(_prov=sido["sido_code"].map(lambda v: _c(v).zfill(2)))
    # districts with no province row that year (Sejong-si 2008-2011) have nowhere to land
    have = set(zip(sido_p["year"], sido_p["_prov"]))
    sgg_in = sgg_p[[k in have for k in zip(sgg_p["year"], sgg_p["_prov"])]]
    for name, p in fams.items():
        cols = [c for c in fam(sido, p) if c in sgg.columns]
        lo = sgg_in.groupby(["year", "_prov"])[cols].sum()
        hi = sido_p.groupby(["year", "_prov"])[cols].sum()
        gap = (lo.reindex(hi.index).fillna(0) - hi).abs()
        n_bad = int((gap > 0).sum().sum())
        check(f"{p}*: sigungu sums to sido, per province, year and column ({len(cols)} cols)",
              n_bad == 0, f"{n_bad} cells differ, worst {gap.max().max():.0f}")
    cols = [c for c in fam(nat, "lang_") if c in sido.columns]
    lo = sido.groupby("year")[cols].sum()
    hi = nat.set_index("year")[cols].fillna(0)
    gap = (lo.reindex(hi.index).fillna(0) - hi).abs()
    check(f"lang_*: sido sums to national, per year and column ({len(cols)} cols)",
          int((gap > 0).sum().sum()) == 0, f"worst {gap.max().max():.0f}")

    def within(low, high, cols, label, years=None):
        cols = [c for c in cols if c in low.columns and c in high.columns]
        lo = low.groupby("year")[cols].sum().sum(axis=1)
        hi = high.groupby("year")[cols].sum().sum(axis=1)
        j = pd.concat([lo.rename("low"), hi.rename("high")], axis=1).dropna()
        if years is not None:
            j = j[j.index >= years]
        pct = (100 * (j["low"] - j["high"]) / j["high"].replace(0, np.nan)).abs()
        w = pct.max()
        check(label, bool(w < 0.5), f"max |gap| {w:.3f}% in {pct.idxmax()}")
    for p in ("nat_", "visa_"):
        within(sgg, nat, fam(nat, p), f"{p}*: sigungu sum within 0.5% of the published "
               f"national count, 2014 on", years=2014)
    for col in broad:
        within(sgg, nat, [col], f"broad {col}: sigungu sum within 0.5% of national")
    within(emd, sgg, ["broad_total"], "broad_total: eupmyeondong sum within 0.5% of sigungu")

    print("\n" + "="*70); print("(3) WITHIN-ROW IDENTITIES (every level)"); print("="*70)
    for label, df, num, den in (("national", nat, "foreign_total", "total_pop"),
                                ("sido", sido, "registered_foreigners", "resident_pop"),
                                ("sigungu", sgg, "registered_foreigners", "resident_pop")):
        x = df.dropna(subset=[num, den, "foreign_share_pct"])
        x = x[x[den] > 0]
        g = (100 * x[num] / x[den] - x["foreign_share_pct"]).abs()
        check(f"{label}: foreign_share_pct = 100 x {num} / {den}", bool((g <= 0.006).all()),
              f"max {g.max():.4f}")
    comp5 = ["workers","marriage_migrants","students","ethnic_koreans","other_foreigners"]
    for label, df in (("national", nat), ("sido", sido), ("sigungu", sgg),
                      ("eupmyeondong", emd)):
        x = df.dropna(subset=["broad_total", "non_naturalized", "naturalized", "children"])
        g = (x["broad_total"] - x[["non_naturalized", "naturalized", "children"]].sum(axis=1)).abs()
        check(f"{label}: broad_total = non_naturalized + naturalized + children",
              bool((g <= 1).all()), f"max {g.max() if len(g) else 0}")
        x = df.dropna(subset=["non_naturalized"] + comp5)
        g = (x["non_naturalized"] - x[comp5].sum(axis=1)).abs()
        check(f"{label}: non_naturalized = its five components",
              bool((g <= 1).all()), f"max {g.max() if len(g) else 0}")

    print("\n" + "="*70); print("(4) PUBLISHED MOJ FIGURES"); print("="*70)
    dd = pd.read_csv(os.path.join(DEPOSIT, "data_dictionary.csv"), encoding="utf-8-sig")
    for p, src, key in (("nat_", det("nationality_national.csv"), "country"),
                        ("visa_", det("visa_national.csv"), "visa_code")):
        src = src[src["population"] == "registered"]
        # the category behind each wide column, as the dictionary records it:
        # 'Count for nationality: China ("중국"). From ...' / '... (E9). From ...'
        rows = dd[(dd["file"] == "national_annual.csv") & dd["variable"].str.startswith(p)]
        n_bad, n_cells = 0, 0
        def last_paren(t):
            """The last balanced (...) group before ". From": labels such as
            "러시아(연방)" nest their own parentheses."""
            head = t.split(". From")[0]
            if not head.endswith(")"):
                return None
            depth = 0
            for i in range(len(head) - 1, -1, -1):
                depth += {")": 1, "(": -1}.get(head[i], 0)
                if depth == 0:
                    return head[i + 1:-1]
            return None
        named = [last_paren(d_) for v_, d_ in zip(rows["variable"], rows["description_en"])]
        for v, desc in zip(rows["variable"], rows["description_en"]):
            got_ = last_paren(desc)
            if got_ is None:
                n_bad += 1
                continue
            cat = got_.split(", ")[-1] if p == "visa_" else got_
            if p == "nat_" and cat == "그 밖의 국적":
                # the residual: the national total less the 49 named nationalities
                want = (src.groupby("year")["n"].sum()
                        - src[src[key].astype(str).isin([c for c in named if c and c != cat])]
                        .groupby("year")["n"].sum().reindex(src["year"].unique()).fillna(0))
            else:
                want = src[src[key].astype(str) == cat].groupby("year")["n"].sum()
            got = nat.set_index("year")[v]
            j = pd.concat([got.rename("got"), want.rename("want")], axis=1)
            j = j[j.index.isin(nat["year"])].fillna(0)
            n_cells += len(j)
            n_bad += int((j["got"] != j["want"]).sum())
        check(f"national_annual {p}* = {'nationality' if p == 'nat_' else 'visa'}_national "
              f"(registered), cell by cell", n_bad == 0 and len(rows) > 0,
              f"{n_bad} of {n_cells} cells differ over {len(rows)} columns")
    p_ = os.path.join(CLEAN, "mois_moj_validation.csv")
    if not os.path.exists(p_):
        check("MOJ validation file present", False, p_)
    else:
        v = pd.read_csv(p_, encoding="utf-8-sig")
        mj = v.dropna(subset=["moj_n"]).groupby("year")["moj_n"].sum()
        j = pd.concat([nat.set_index("year")["foreign_total"], mj.rename("moj")], axis=1).dropna()
        check("national foreign_total = the MOJ validation file's district total, every year",
              len(j) == len(nat) and bool((j["foreign_total"] == j["moj"]).all()),
              f"{len(j)} years, max |diff| {(j['foreign_total'] - j['moj']).abs().max():.0f}")

    # 2026-09-27 (second-round cross-check). The nat_* columns of a row must add up to
    # the row's registered foreigners. The cross-level sums above could not see nat_other
    # holding only the raw "기타" column, because the district and province columns
    # were built by the same call and shared the gap (13,171-14,285 people a year in
    # 2014-2017, nat_other blank in every row of 2014-2016, 2019 and 2021).
    # A province's wide columns are its districts summed (see (2)), so they add up to
    # the registered foreigners of its districts; that equals the province row's own
    # count in every province-year but 2015 Gyeonggi-do, whose "소계" the yearbook prints one
    # person above its district lines.
    dist_reg = sgg_p.groupby(["year", "_prov"])["registered_foreigners"].sum()
    sido_reg = pd.Series([dist_reg.get((y, p_), np.nan) for y, p_ in
                          zip(sido_p["year"], sido_p["_prov"])], index=sido.index)
    for label, df, tot, what in (("sigungu", sgg, sgg["registered_foreigners"],
                                  "registered_foreigners"),
                                 ("sido", sido, sido_reg,
                                  "the registered foreigners of its districts")):
        cols = fam(df, "nat_")
        x = df[tot.notna() & df[cols].notna().any(axis=1)]
        g = (x[cols].fillna(0).sum(axis=1) - tot[x.index]).abs()
        check(f"{label}: the nat_* columns of a row add up to {what} "
              f"({len(x)} rows)", len(x) > 0 and bool((g == 0).all()),
              f"{int((g != 0).sum())} rows differ, worst {g.max():.0f}")
        blank = x["nat_other"].isna().sum() if "nat_other" in x.columns else len(x)
        check(f"{label}: nat_other is never blank where the row has nationality columns",
              blank == 0, f"{blank} blank")
    nreg = det("nationality_national.csv")
    nreg = nreg[nreg["population"] == "registered"].groupby("year")["n"].sum()
    cols = fam(nat, "nat_")
    g = (nat.set_index("year")[cols].fillna(0).sum(axis=1) - nreg).dropna().abs()
    check("national: the nat_* columns add up to the registered national total, every year",
          len(g) == len(nat) and bool((g == 0).all()), f"worst {g.max():.0f}")

    print("\n" + "="*70); print("(5) WIDE-ATTACH CONSISTENCY"); print("="*70)
    for label, df in (("sido", sido), ("sigungu", sgg)):
        w = [c for p in fams.values() for c in fam(df, p)]
        off = sorted(set(w) - set(nat.columns))
        check(f"{label}: every wide column also sits on national_annual", not off, off[:5])
    for label, df in (("national", nat), ("sido", sido), ("sigungu", sgg), ("eupmyeondong", emd)):
        w = [c for p in list(fams.values()) + ["mc_"] for c in fam(df, p)]
        empty = [c for c in w if df[c].isna().all()]
        check(f"{label}: no wide column blank in every row ({len(w)} cols)", not empty, empty[:5])

    print("\n" + "="*70)
    print(f"SUMMARY: {len(FAILS)} FAIL(s)")
    for f in FAILS: print("   FAIL:", f)
    print("="*70)
    if FAILS:
        sys.exit(1)


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
    # 2026-09-26 (third cross-check): the numbers the three READMEs quote, and the public
    # repository's file table, are rewritten from the staged files. They had been kept
    # by hand and were a build behind. qc_deposit_staging checks the same with --check.
    import readme_facts
    readme_facts.main([])
    final_qc()
