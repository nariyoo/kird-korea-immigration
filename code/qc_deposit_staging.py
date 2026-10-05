# -*- coding: utf-8 -*-
"""Fully check the staging tree to be uploaded to openICPSR, using only the files in it.

`validate_release.py` already checks the indicators, identities and dictionary
(61 checks). This tool checks what that one does not.

    1. File list          CSV 27 + DTA 27 + docs 3 = 57, nothing else
    2. CSV-DTA values     Compare every pair cell by cell. Step 10 parity only
                          checks shape (rows x columns), so fixing a CSV without
                          rebuilding the .dta passes there. This catches it by value.
    3. Data-dependent claims in the README
                          observed nationality count (190/193), adm_code match rate,
                          naturalization reconciliation, broad/registered ratio
                          (1.05/1.74), blank list, Sejong wide exception.
    4. Against published v1.1.0
                          Count per file what is new and what changed.
                          The result must match the measured section of
                          OPENICPSR_METADATA.md.
    5. Refugee languages  Is Haitian Creole under '인도적체류' (humanitarian stay)?
                          (the marker case of the 2026-08-26 extension).

    python qc_deposit_staging.py [<deposit folder> [<previous version zip>]]

With no folder, it checks the staging in the working tree. Someone who downloaded
the deposit can pass the unpacked deposit folder and run the same checks there.
The previous version zip is optional; without it only that section is skipped.
Only pandas and numpy are needed.

Exits 0 if everything passes, 1 if anything fails.
"""
import glob
import io
import os
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 04_dataset_release
# 2026-09-19: the default path below added the folder name under ROOT a
# second time. Run without arguments, it died for lack of README.md. Run with
# an argument, inventory's `rel` pointed to a missing folder and **the release
# vs staging comparison was silently skipped.** That comparison is the very
# check added to catch the missing diaspora table on 2026-08-31. The check
# that catches missing tables was itself missing.

# A recipient must be able to run this as is. Use the folder given as an
# argument; otherwise use the staging in the working tree. Passing a
# downloaded deposit folder validates it in place.
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
STG = (os.path.abspath(_ARGS[0]) if _ARGS
       else os.path.join(ROOT, "data deposit",
                         "kird_openicpsr_deposit_staging"))
# The deposit's docs (README, DATA_NOTES) live in the public repository
# (2026-09-29, from V2).
GH_DOCS = os.path.join(ROOT, "data deposit", "kird_dataset_github")
# Comparison with the previous version runs only if that zip exists (optional).
PUBZIP = (os.path.abspath(_ARGS[1]) if len(_ARGS) > 1
          else os.path.join(ROOT, "data deposit",
                            "KIRD_openicpsr_deposit_v1.1.0.zip"))

FAILS = []


def check(ok, label, detail=""):
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", label,
                           ("  |  " + str(detail)) if (detail and not ok) else ""))
    if not ok:
        FAILS.append(label)


def all_csvs():
    return (sorted(glob.glob(os.path.join(STG, "data", "*.csv")))
            + sorted(glob.glob(os.path.join(STG, "data", "detailed_data", "*.csv"))))


# ------------------------------------------------------------- 1. File list
def inventory():
    print("== 1. File list")
    files = []
    for dp, _, fns in os.walk(STG):
        for fn in fns:
            files.append(os.path.relpath(os.path.join(dp, fn), STG))
    csvs = [f for f in files if f.endswith(".csv") and f != "data_dictionary.csv"]
    dtas = [f for f in files if f.endswith(".dta")]
    docs = sorted(f for f in files if not f.endswith((".csv", ".dta")))
    check(len(csvs) == 28, "CSV 28개", len(csvs))
    check(len(dtas) == 28, "DTA 28개", len(dtas))
    # **Counting alone does not tell which table is missing.** On 2026-08-31
    # diaspora_residence_by_sido was missing from staging and still passed.
    # The release added that table on 8-29 but staging was not rerun, and the
    # expected count was hard-coded as 27, so 27 files looked correct. When run
    # in the working tree, match names against the release folder. When a
    # recipient runs it with only the deposit, that folder is absent and this
    # check is skipped.
    rel = os.path.join(ROOT, "data")
    if not os.path.isdir(rel):
        print("  --   No release folder, skipping comparison: %s" % rel)
    if os.path.isdir(rel):
        want = {f for f in os.listdir(rel) if f.endswith(".csv")}
        have = {os.path.basename(f) for f in csvs}
        missing = sorted(want - have)
        extra = sorted(have - want)
        check(not missing, "릴리스의 표가 모두 스테이징에 있다", missing)
        # Deposit-only tables (the two refugee tables) are not in the release
        # data/. They are listed by name.
        check(set(extra) <= {"refugee_by_nationality.csv",
                             "refugee_language_demand.csv"},
              "스테이징에만 있는 표는 난민 표 둘뿐", extra)
        bad = release_vs_deposit(rel, STG)
        check(not bad, "릴리스의 표와 기탁본의 같은 칸이 값까지 같다(기탁본은 wide 열만 더한다)",
              bad[:4])
        bad = dictionary_vs_deposit(os.path.join(ROOT, "data_dictionary.csv"),
                                    os.path.join(STG, "data_dictionary.csv"))
        check(not bad, "릴리스 사전과 기탁본 사전이 같은 (파일, 변수) 행에서 같다", bad[:4])
    # 2026-09-29: the deposit carries no README (Nari, V2). The docs are
    # README.md and DATA_NOTES.md in the public repository, and the doc checks
    # below read those two
    check(docs == ["LICENSE.txt"], "문서는 LICENSE 뿐 (README 와 노트는 GitHub)", docs)
    check(os.path.exists(os.path.join(STG, "data_dictionary.csv")),
          "data_dictionary.csv 있음")
    # **No undocumented file may enter the deposit.** On 2026-08-31 five files
    # (three crosswalks, language_weights, diaspora) were in staging without
    # ever appearing in the README table. Neither the count check nor the
    # CSV-DTA pair check sees that.
    import re as _re
    _md = io.open(os.path.join(GH_DOCS, "README.md"), encoding="utf-8").read()
    _in_readme = set(_re.findall(r"\|\s*`?([a-z0-9_]+)\.csv`?\s*\|", _md))
    _undocumented = sorted({os.path.basename(f)[:-4] for f in csvs}
                           - _in_readme)
    check(not _undocumented, "모든 표가 README 의 표에 있다", _undocumented)

    pairs = {f[:-4] for f in csvs} ^ {f[:-4] for f in dtas}
    check(not pairs, "모든 CSV 에 .dta 짝", sorted(pairs))


# --------------------------------------------------- 2. CSV-DTA value match
def parity():
    print("== 2. CSV-DTA value match (cell by cell)")
    for cp in all_csvs():
        stem = os.path.basename(cp)[:-4]
        dp = cp[:-4] + ".dta"
        c = pd.read_csv(cp, encoding="utf-8-sig", low_memory=False)
        d = pd.read_stata(dp)
        ok = c.shape == d.shape and list(c.columns) == list(d.columns)
        detail = "shape %s vs %s" % (c.shape, d.shape)
        if ok:
            bad = 0
            for col in c.columns:
                a, b = c[col], d[col]
                # broad_apportioned reads as bool (True/False) from the CSV and as
                # text "True"/"False" from the .dta. Same meaning, so compare as text.
                if (pd.api.types.is_bool_dtype(a)
                        or set(map(str, b.dropna().unique())) <= {"True", "False"}):
                    m = (a.fillna("").astype(str).str.lower()
                         != b.fillna("").astype(str).str.lower()).to_numpy()
                elif pd.api.types.is_numeric_dtype(a) or pd.api.types.is_numeric_dtype(b):
                    an = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
                    bn = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
                    m = ~np.isclose(an, bn, rtol=0, atol=1e-9, equal_nan=True)
                else:
                    m = (a.fillna("").astype(str).str.strip()
                         != b.fillna("").astype(str).str.strip()).to_numpy()
                bad += int(m.sum())
            ok = bad == 0
            detail = "%d개 셀이 다름" % bad
        check(ok, "parity %s" % stem, detail)


# ---------------------------------------- 3. Data-dependent claims in README
WIDE_PREFIX = ("nat_", "visa_", "lang_", "mc_")
WIDE_EXTRA = {"n_enclaves", "settlement_type"}


def release_vs_deposit(rel, stg):
    """Do the tables in release data/ and the same tables in the deposit agree,
    value by value, in the same columns?

    2026-09-26 (3rd comparison): four summary files differed between the two
    folders in the same columns (release broad_apportioned TRUE/FALSE vs deposit
    True/False; national_annual broad count 891341.0 vs 891341; summary_by_sido
    n_nationalities_observed 19.0 vs 19). Detail tables must match byte for byte.
    Summary files must match in every release column, and the only columns the
    deposit adds may be the wide columns, n_enclaves and settlement_type.
    """
    import filecmp
    out = []
    for f in sorted(x for x in os.listdir(rel) if x.endswith(".csv")):
        cands = [os.path.join(stg, "data", "detailed_data", f), os.path.join(stg, "data", f)]
        q = next((c for c in cands if os.path.exists(c)), None)
        if q is None:
            continue
        if "detailed_data" in q:
            if not filecmp.cmp(os.path.join(rel, f), q, shallow=False):
                out.append("%s: detail table differs" % f)
            continue
        a = pd.read_csv(os.path.join(rel, f), encoding="utf-8-sig", dtype=str,
                        keep_default_na=False)
        b = pd.read_csv(q, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        miss = [c for c in a.columns if c not in b.columns]
        more = [c for c in b.columns if c not in a.columns
                and not c.startswith(WIDE_PREFIX) and c not in WIDE_EXTRA]
        diff = [c for c in a.columns if c in b.columns and len(a) == len(b)
                and not (a[c].values == b[c].values).all()]
        if len(a) != len(b) or miss or more or diff:
            out.append("%s: rows %d/%d, missing %s, unexpected %s, differ %s"
                       % (f, len(a), len(b), miss, more, diff))
    return out


def dictionary_vs_deposit(p_rel, p_stg):
    if not (os.path.exists(p_rel) and os.path.exists(p_stg)):
        return []
    a = pd.read_csv(p_rel, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    b = pd.read_csv(p_stg, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    m = a.merge(b, on=["file", "variable"], how="left", suffixes=("", "_d"))
    out = ["%s.%s: not in the deposit dictionary" % (r.file, r.variable)
           for r in m[m["type_d"].isna()].itertuples()]
    for c in ("type", "description_en", "description_ko"):
        d = m[m["type_d"].notna() & (m[c] != m[c + "_d"])]
        out += ["%s.%s: %s differs" % (r.file, r.variable, c) for r in d.itertuples()]
    return out


def readme_numbers():
    """Do the numbers quoted in the READMEs equal the values recomputed from the
    deposit files (readme_facts)?

    2026-09-26 (3rd comparison): the F-6, F-2 and F-4 counts, the 2006-2014
    national totals, and the public repository's file table (naturalization panel
    2009-2024, 15,636 rows) still held values from the build before the 2nd fix.
    """
    print("== 3a. Numbers quoted in README (readme_facts --check)")
    import readme_facts
    buf = io.StringIO()
    from contextlib import redirect_stdout
    with redirect_stdout(buf):
        rc = readme_facts.main(["--check"])
    out = buf.getvalue()
    for line in out.strip().splitlines():
        print("   " + line)
    check(rc == 0, "README 의 인용 수가 기탁 파일과 같다", out[-400:] if rc else "")


def deposit_docs():
    """The public repository's README and DATA_NOTES joined into one text. Claim
    checks read a claim from either (the deposit has no README from 2026-09-29)."""
    out = []
    for nm in ("README.md", "DATA_NOTES.md"):
        p = os.path.join(GH_DOCS, nm)
        if os.path.exists(p):
            out.append(io.open(p, encoding="utf-8").read())
    return "\n\n".join(out)


def readme_claims():
    print("== 3. Data-dependent claims in README")
    txt = deposit_docs()
    D = os.path.join(STG, "data") + os.sep
    DD = os.path.join(STG, "data", "detailed_data") + os.sep
    na = pd.read_csv(D + "national_annual.csv", encoding="utf-8-sig")
    s = pd.read_csv(D + "summary_by_sigungu.csv", encoding="utf-8-sig",
                    low_memory=False)
    emd = pd.read_csv(D + "summary_by_eupmyeondong.csv", encoding="utf-8-sig",
                      low_memory=False)

    # Observed nationality count: national 2013=19, 2014=188 (the docs' "193" is
    # the value before names were merged). From the 2026-09-26 final audit,
    # non-nationality columns ('무국적', '미등록국가', '기타') are not counted. The
    # earlier 190 counted one stateless person in '화성시' in 2014 as a nationality.
    # From that evening, rows with no country name ('국적불명', '국제연합',
    # '국제연합전문기구') are also not counted, so 189 becomes 188
    # ('국제연합' in 2014).
    obs = dict(zip(na["year"], na["n_nationalities_observed"]))
    check(obs.get(2013) == 19 and obs.get(2014) == 188,
          "national n_nationalities_observed 2013=19, 2014=188",
          {y: obs.get(y) for y in (2013, 2014)})
    check("193 in 2014" not in txt and ", 193" not in txt,
          "README 에 옛 값 193 이 남아 있지 않다")

    # Broad/registered ratio
    r08 = na.loc[na.year == 2008, "broad_total"].iloc[0] / \
        na.loc[na.year == 2008, "foreign_total"].iloc[0]
    r24 = na.loc[na.year == 2024, "broad_total"].iloc[0] / \
        na.loc[na.year == 2024, "foreign_total"].iloc[0]
    # 2026-09-26 (4th comparison): 1.05 -> 1.04 in 2008, once the district files stopped
    # losing the '화성시' sub-office line and the columns that fold onto one country.
    check(abs(r08 - 1.04) < 0.005 and abs(r24 - 1.74) < 0.005,
          "broad/registered 1.04 (2008), 1.74 (2024)",
          (round(r08, 3), round(r24, 3)))

    # adm_code match rate: does the README's stated range match the measurement?
    emd_pct = {}
    for y, g in emd.groupby("year"):
        emd_pct[int(y)] = 100.0 * g["adm_code"].notna().sum() / len(g)
    lo, hi = min(emd_pct.values()), max(emd_pct.values())
    # Do the README's lower and upper bounds contain the measurement? Find the two
    # percentages and compare, so it still reads if the sentence shape changes.
    # 2026-09-26: the README now gives 2014 and 2015 each, and only a lower bound
    # after that ("96.3% in 2014, 97.9% in 2015, and 99.7% or more in every later year").
    rx = __import__("re")
    m = rx.search(r"([\d.]+)% in 2014, ([\d.]+)% in 2015, and ([\d.]+)% or more in "
                  r"every later year", txt)
    if m:
        later = min(v for y, v in emd_pct.items() if y >= 2016)
        ok = (abs(float(m.group(1)) - emd_pct[2014]) < 0.06
              and abs(float(m.group(2)) - emd_pct[2015]) < 0.06
              and float(m.group(3)) <= later + 1e-9 and later - float(m.group(3)) < 0.1)
        check(ok, "adm_code 붙임율 서술이 실측(2014 %.1f, 2015 %.1f, 이후 최저 %.2f%%)과 같다"
              % (emd_pct[2014], emd_pct[2015], later), m.group(0))
    else:
        check(False, "adm_code 서술을 README 에서 못 찾았다 (실측 %.1f-%.1f%%)"
              % (lo, hi))

    # 2008 blanks: only theil and ethnic_koreans
    r = na[na.year == 2008].iloc[0]
    # Blanks in wide columns (nat_/visa_/lang_) follow the documented rule "not
    # printed separately that year", so they are not counted here.
    blanks = [c for c in na.columns
              if pd.isna(r[c]) and not c.startswith(("nat_", "visa_", "lang_"))]
    # foreign_resident_households: MOIS prints the '세대수' (households) column 2009-2015 only
    # (2026-09-27).
    check(set(blanks) == {"theil_segregation_H", "ethnic_koreans",
                          "foreign_resident_households"},
          "national_annual 2008 빈칸은 theil, ethnic_koreans, 세대수 뿐", blanks)

    # Naturalization reconciliation: summing the by-country table per type
    # matches the annual table within five
    ann = pd.read_csv(DD + "naturalization_annual.csv", encoding="utf-8-sig")
    byc = pd.read_csv(DD + "naturalization_by_country.csv", encoding="utf-8-sig")
    norm = lambda t: str(t).replace(" ", "")
    ann["t"] = ann["type"].map(norm)
    byc["t"] = byc["type"].map(norm)
    a = ann.groupby(["year", "t"])["n"].sum()
    b = byc.groupby(["year", "t"])["n"].sum()
    both = a.index.intersection(b.index)
    gap = (b[both] - a[both])
    over = gap[gap.abs() > 5]
    # 2026-09-25: earlier, seven cells exceeded five and the README said "the
    # source data are like that". In fact the parser ignored '한국계 포함' on the
    # 2017 China row, did not read the '취득인지' and '재취득' columns for
    # 2014-2018, and counted '기타' twice in 2019 and 2024. After the fix no cell
    # exceeds five (1-5 across four types in 2018).
    WANT = {}
    check({(int(y), t): int(v) for (y, t), v in over.items()} == WANT,
          "연간표 대비 유형별 차이가 모두 다섯 이하다", dict(over))

    # Wide layer sums. Until 2026-09-26 (3rd comparison) the sido wide columns
    # were summed by sido name, so Sejong's share for 2008-2011 was lost (no sido
    # row) and '군위군' went into Daegu up to 2022. Now each sigungu goes to the
    # sido it belonged to that year (first two digits of sigungu_code). Every
    # year and every sido must match to the person.
    sd = pd.read_csv(D + "summary_by_sido.csv", encoding="utf-8-sig",
                     low_memory=False)
    wide = [c for c in s.columns if c.startswith(("nat_", "visa_", "lang_"))
            and c in sd.columns]
    cc = lambda v: "" if v != v else str(v).split(".")[0]
    lo_ = (s.assign(_p=s["sigungu_code"].map(lambda v: cc(v)[:2]))
            .groupby(["year", "_p"])[wide].sum())
    hi_ = (sd.assign(_p=sd["sido_code"].map(lambda v: cc(v).zfill(2)))
             .groupby(["year", "_p"])[wide].sum())
    j_ = lo_.join(hi_, lsuffix="_lo", rsuffix="_hi", how="outer").fillna(0)
    gap_ = max(float((j_[c + "_lo"] - j_[c + "_hi"]).abs().max()) for c in wide)
    check(gap_ < 0.5, "wide 층 합: 해마다 시도마다 시군구 합(그 해의 시도) = 시도",
          "최대 차이 %s" % gap_)
    check(not rx.search(r"short by exactly the 세종", txt),
          "README 에 옛 세종 wide 예외 문장이 남아 있지 않다")

    # 2026-09-25: the README put the eupmyeondong whose multicultural leaf cells
    # fall short of the subtotal at "about 1,400", but in 2024 it was 2,143.
    # Count the sentence's 2024 value from the data.
    mc = pd.read_csv(DD + "multicultural_households.csv", encoding="utf-8-sig",
                     low_memory=False)
    fam = {"결혼이민자귀화자_소계": ["결혼이민자", "귀화자등"],
           "자녀_소계": ["자녀_귀화인지외국국적", "자녀_국내출생"],
           "기타동거인_소계": ["기타동거인_내국인", "기타동거인_외국인"]}
    g = mc[mc["year"] == 2024].pivot_table(
        index=["sido", "sigungu", "eupmyeondong"], columns="category",
        values="n", aggfunc="sum")
    short = np.zeros(len(g), bool)
    for sub, leaves in fam.items():
        L = g.reindex(columns=leaves).fillna(0).sum(axis=1)
        S = g.reindex(columns=[sub]).iloc[:, 0]
        short |= (S.notna() & (L < S)).values
    m = rx.search(r"\(([\d,]+) of ([\d,]+)\s+in 2024\)", txt)
    said = tuple(int(v.replace(",", "")) for v in m.groups()) if m else None
    check(said == (int(short.sum()), len(g)),
          "README 의 다문화 소계 부족 읍면동 수(2024)가 자료와 같다",
          (said, (int(short.sum()), len(g))))


# ---------------------------------------------- 4. Against published v1.1.0
def against_published():
    print("== 4. Against published v1.1.0 (zip)")
    import zipfile
    if not os.path.exists(PUBZIP):
        print("     (No previous version zip, skipping: %s)" % PUBZIP)
        return
    zf = zipfile.ZipFile(PUBZIP)
    pub = {}
    for nm in zf.namelist():
        if nm.endswith(".csv") and "data_dictionary" not in nm:
            pub[os.path.basename(nm)] = nm
    new, changed, unchanged = [], [], []
    for cp in all_csvs():
        fn = os.path.basename(cp)
        if fn not in pub:
            new.append(fn)
            continue
        a = io.open(cp, "rb").read()
        b = zf.read(pub[fn])
        (unchanged if a == b else changed).append(fn)
    removed = sorted(set(pub) - {os.path.basename(c) for c in all_csvs()})
    print("     new %d  changed %d  unchanged %d  removed %d"
          % (len(new), len(changed), len(unchanged), len(removed)))
    for lab, lst in (("새로", new), ("그대로", unchanged), ("없어짐", removed)):
        print("     %s: %s" % (lab, ", ".join(sorted(lst)) or "없음"))
    check(removed == ["summary_national.csv"],
          "없어진 것은 이름이 바뀐 summary_national 뿐", removed)


# ------------------------------------------------------ 5. Refugee languages
def refugee_language():
    print("== 5. Refugee languages")
    rl = pd.read_csv(os.path.join(STG, "data", "detailed_data",
                                  "refugee_language_demand.csv"),
                     encoding="utf-8-sig")
    hai = rl[(rl["status"] == "인도적체류") & (rl["language"].str.contains("크레올"))]
    check(len(hai) == 1, "인도적체류에 아이티크레올어가 있다",
          rl[rl["status"] == "인도적체류"]["language"].tolist()[:8])
    en_gap = rl[rl["language_en"].astype(str).str.contains("[가-힣]", regex=True)]
    check(len(en_gap) == 0, "영문 칸에 한글이 없다", en_gap["language_en"].tolist())
    # 2026-09-25: only the refugee nationality table wrote Russia as '러시아', so it
    # did not join to the standard name in crosswalk_country ('러시아(연방)').
    # Check that it uses only standard names, like the other nationality tables.
    rn = pd.read_csv(os.path.join(STG, "data", "detailed_data",
                                  "refugee_by_nationality.csv"), encoding="utf-8-sig")
    cw = pd.read_csv(os.path.join(STG, "data", "detailed_data",
                                  "crosswalk_country.csv"), encoding="utf-8-sig")
    off = sorted(set(rn["country"]) - set(cw["country"]))
    check(not off, "난민 국적표의 국적이 모두 crosswalk_country 의 표준 이름이다", off)
    # Round 3 comparison (2026-09-27): refugee language demand must be
    # reproducible from the deposit alone, as the data dictionary describes. For
    # each status, sum the 10 named nationalities x language_weights shares in
    # units of 1/10,000 person, round once, and keep only languages among the top
    # 20 whose unrounded sum reaches 1 person ('보호' = '난민인정' + '인도적체류').
    # Earlier, values already rounded to one decimal were rounded again and four
    # rows were 1 person too high ('난민인정' Amharic 50, '인도적체류' Assyrian 14, etc.).
    lw = pd.read_csv(os.path.join(STG, "data", "detailed_data", "language_weights.csv"),
                     encoding="utf-8-sig")
    U = 10000
    sh = {}
    for c, lang, s_ in zip(lw["country"], lw["language"], lw["share"]):
        if isinstance(lang, str) and lang:
            sh.setdefault(c, []).append((lang, int(round(float(s_) * U))))
    named = rn[rn["country"] != "기타"]
    cnt = {st: dict(zip(g["country"], g["count"])) for st, g in named.groupby("status")}
    cnt["보호"] = {c: cnt.get("난민인정", {}).get(c, 0) + cnt.get("인도적체류", {}).get(c, 0)
                 for c in set(cnt.get("난민인정", {})) | set(cnt.get("인도적체류", {}))}
    want = {}
    for st in ("난민인정", "인도적체류", "보호"):
        est = {}
        for c, n in cnt.get(st, {}).items():
            for lang, u in sh.get(c, ()):
                est[lang] = est.get(lang, 0) + int(n) * u
        for lang, u in sorted(est.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
            if u >= U:
                want[(st, lang)] = (u + U // 2) // U
    got = {(st, lang): int(n) for st, lang, n in
           zip(rl["status"], rl["language"], rl["count"])}
    diff = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
    check(not diff, "난민 언어 수요가 refugee_by_nationality x language_weights 에서 한 번 "
          "반올림으로 다시 나온다 (%d행)" % len(want),
          ["%s %s: 실린 %s, 다시 낸 %s" % (k[0], k[1], got.get(k), want.get(k))
           for k in diff[:6]])


# -------------------------------------------------- 6. In the user's seat
def as_a_user():
    """Do exactly what a recipient actually does.

    On 2026-08-26 this found three problems. The deposit's `adm_code` was stored
    as `3203062.0`, so the GIS key carried a decimal point (the release files were
    fine; pandas had promoted an integer column with missing values to float and it
    was written as is). In 2014 the same dong appeared twice under two spellings,
    so 391 codes overlapped. And '창원 성산구 중앙동' carried a '진주시' code. All
    three show up at once if you "open it and join", but a schema check misses them.
    """
    print("== 6. In the user's seat")
    D = os.path.join(STG, "data") + os.sep
    DD = os.path.join(STG, "data", "detailed_data") + os.sep

    # (a) Values that should be integers do not carry .0
    import re
    P = re.compile(r"^-?[0-9]+[.]0$")
    bad = []
    for cp in all_csvs():
        d = pd.read_csv(cp, encoding="utf-8-sig", dtype=str, low_memory=False)
        for c in d.columns:
            if c.endswith("_pct") or c in ("share", "share_pct", "lq",
                                           "dissimilarity_D", "isolation",
                                           "interaction_korean"):
                continue
            v = d[c].dropna()
            if len(v) and v.str.match(P).mean() > 0.5 and v.str.match(P).any():
                bad.append("%s.%s" % (os.path.basename(cp), c))
    check(not bad, "정수 칸에 소수 꼬리(.0)가 없다", bad[:6])

    # (b) Is the eupmyeondong code a unique GIS key within each year?
    e = pd.read_csv(D + "summary_by_eupmyeondong.csv", encoding="utf-8-sig",
                    dtype={"adm_code": str}, low_memory=False)
    v = e.dropna(subset=["adm_code"]).copy()
    v["adm_code"] = v["adm_code"].str.strip()
    v = v[v["adm_code"] != ""]
    dup = int(v.duplicated(["year", "adm_code"]).sum())
    check(dup == 0, "adm_code 가 연도 안에서 유일하다 (경계 join 이 행을 불리지 않는다)",
          "%d행" % dup)
    v["p4"] = v["adm_code"].str[:4]
    mode = v.groupby(["year", "sido", "sigungu"])["p4"].transform(
        lambda x: x.mode().iloc[0])
    check(int((v["p4"] != mode).sum()) == 0,
          "모든 동 코드가 제 시군구의 코드 대역 안에 있다",
          "%d행" % int((v["p4"] != mode).sum()))

    # (c) Joining summary and detail on the Korean keys leaves nothing unmatched?
    s = pd.read_csv(D + "summary_by_sigungu.csv", encoding="utf-8-sig",
                    low_memory=False)
    for name, key in (("nationality_by_sigungu.csv",
                       ["year", "sido", "sigungu"]),
                      ("visa_by_sigungu.csv", ["year", "sido", "sigungu"])):
        n = pd.read_csv(DD + name, encoding="utf-8-sig", low_memory=False)
        j = n.merge(s[key + ["resident_pop"]], on=key, how="left", indicator=True)
        miss = int((j["_merge"] != "both").sum())
        check(miss == 0, "%s 가 요약에 전부 붙는다" % name, "%d행" % miss)
        # (c2) The reverse too: does every summary row with registered foreigners
        # have detail rows? The 2026-09-26 final audit found this checked only one
        # direction. The 2015 '창원시' (1 person) summary row has no visa rows,
        # because the sigungu x visa table of that year has no '창원시' line and puts
        # that person in the '마산합포구' line (2,160) (the nationality table has
        # '창원시' 1 + '마산합포구' 2,159). Only that one place is empty as in the
        # source; any other gap is a defect.
        EMPTY_OK = {"visa_by_sigungu.csv": {(2015, "경상남도", "창원시")}}
        have = set(map(tuple, n[n["n"] > 0][key].drop_duplicates().values.tolist()))
        want = set(map(tuple, s[s["registered_foreigners"] > 0][key].values.tolist()))
        lack = sorted(want - have)
        ok_ = EMPTY_OK.get(name, set())
        check([k for k in lack if k not in ok_] == [] and ok_ <= set(lack),
              "등록외국인이 있는 요약 행마다 %s 행이 있다 (원자료대로 빈 곳 %d)"
              % (name, len(ok_)), "없는 곳 %s" % lack[:5])

    # (d) Do the docs say not to join on the English name alone?
    d24 = s[s["year"] == s["year"].max()]
    n_dup = int(d24["sigungu_en"].duplicated().sum())
    txt = deposit_docs()
    warned = ("sigungu_en" in txt and
              ("not unique" in txt or "on its own" in txt or "동구" in txt))
    check(n_dup == 0 or warned,
          "sigungu_en 이 유일하지 않다는 것을 README 가 알린다 (중복 %d개)" % n_dup)


# ---------------------------------------------- 7. README reading recipe
def readme_recipe():
    """Run the reading code the README recommends, as is, on every table.

    2026-09-26 (4th comparison): to read code columns as text, the README
    recommended `dtype=codes, keep_default_na=False` for "every file you join".
    keep_default_na=False turns blanks into empty strings across the whole file,
    not only the code columns, so wide columns such as nat_japan in
    summary_by_sigungu became mixed text and numbers and `.sum()` died with a
    TypeError (summary_by_sido concatenated the numbers with no warning). Pull out
    the README's code block, run it, and compare with a plain read.
    """
    print("== 7. README reading recipe")
    import re as _re
    import warnings as _w
    docs = [os.path.join(GH_DOCS, "DATA_NOTES.md")]
    rel_readme = os.path.join(ROOT, "README.md")
    if os.path.exists(rel_readme):
        docs.append(rel_readme)
    for doc in docs:
        md = io.open(doc, encoding="utf-8").read()
        m = _re.search(r"\*\*Read the code columns as text\.\*\*.*?```python\s*\n(.*?)```",
                       md, _re.S)
        label = os.path.relpath(doc, ROOT)
        check(m is not None, "%s: 코드 칸 읽기 요리법이 있다" % label)
        if m is None:
            continue
        code = m.group(1)
        bad = []
        for cp in all_csvs():
            ns = {"pd": pd, "path": cp}
            with _w.catch_warnings():
                _w.simplefilter("error")
                try:
                    exec(code, ns)
                except Exception as e:          # a warning counts as a failure
                    bad.append("%s: %s" % (os.path.basename(cp), type(e).__name__))
                    continue
            got = ns.get("df")
            plain = pd.read_csv(cp, encoding="utf-8-sig", low_memory=False)
            codes = [c for c in ("sido_code", "sigungu_code", "adm_code") if c in got.columns]
            for c in plain.columns:
                if c in codes:
                    v = got[c]
                    if not (v.map(type) == str).all() or v.str.endswith(".0").any():
                        bad.append("%s.%s: code column not plain text"
                                   % (os.path.basename(cp), c))
                elif (pd.api.types.is_numeric_dtype(plain[c])
                      and not pd.api.types.is_numeric_dtype(got[c])):
                    bad.append("%s.%s: numeric column read as %s"
                               % (os.path.basename(cp), c, got[c].dtype))
        check(not bad, "%s: 그 요리법으로 %d개 표를 모두 읽으면 코드 칸은 글자, 수 칸은 수"
              % (label, len(all_csvs())), bad[:5])


def main():
    inventory()
    parity()
    readme_claims()
    readme_numbers()
    against_published()
    refugee_language()
    as_a_user()
    readme_recipe()
    print()
    if FAILS:
        print("%d failed:" % len(FAILS))
        for f in FAILS:
            print("   " + f)
        return 1
    print("All passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
