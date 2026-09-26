# -*- coding: utf-8 -*-
"""The numbers the READMEs quote, read from the released files and written back.

2026-09-26 (3차 대조): the READMEs quoted F-6, F-2 and F-4 counts, national totals
and a file table that were right when written and went stale when a later fix moved
the data (F-6 2011 4,355 against 4,356 in the files; the public repository's table
gave the naturalization panels 2009-2024 and 15,636 rows against 2011-2024 and
13,556). Hand-kept numbers go stale again at the next rebuild, so each quoted number
now has an anchor here: a pattern that finds the sentence and the value the files
give. `refresh` rewrites the value in place; `--check` writes nothing and exits 1
when any README disagrees with the data or has lost an anchor.

    python code/readme_facts.py            # rewrite the READMEs
    python code/readme_facts.py --check    # the gate (qc_deposit_staging calls it)

The file tables (rows of the form "| `name.csv` | ... | 2008-2024 | 4,240 |") are
refreshed the same way: the year range and the row count come from the file itself.
10_stage_deposit.py runs this after staging, so the numbers are read from the files
being deposited.
"""
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd  # noqa: E402

from kird import RELEASE, RELEASE_DATA  # noqa: E402

DEPOSIT = os.path.join(RELEASE, "data deposit", "kird_openicpsr_deposit_staging")
GITHUB = os.path.join(RELEASE, "data deposit", "kird_dataset_github")
TARGETS = [
    os.path.join(RELEASE, "README.md"),
    os.path.join(DEPOSIT, "README.md"),
    os.path.join(GITHUB, "README.md"),
    # the upload notes: file and variable counts against ICPSR's stated limits
    # (2026-09-26, 4차 대조: it said "more than 1,000 columns" against 695)
    os.path.join(RELEASE, "OPENICPSR_METADATA.md"),
]

# The yearbook's lines that hold people but name no nationality (as 01 keeps them).
RESIDUAL_LINES = ["무국적", "기타", "미등록국가", "미상", "한국"]


def data_dirs():
    """Where to read the tables: the staged deposit first, then the release."""
    out = []
    for d in (os.path.join(DEPOSIT, "data"), os.path.join(DEPOSIT, "data", "detailed_data"),
              RELEASE_DATA):
        if os.path.isdir(d):
            out.append(d)
    return out


def find(name):
    for d in data_dirs():
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def rd(name):
    p = find(name)
    if p is None:
        raise SystemExit("readme_facts: %s not found in %s" % (name, data_dirs()))
    return pd.read_csv(p, encoding="utf-8-sig", dtype={"sido_code": str,
                                                        "sigungu_code": str},
                       low_memory=False)


def fmt(n):
    return format(int(n), ",")


def facts():
    F = {}
    vn = rd("visa_national.csv")
    reg = vn[vn["population"] == "registered"]
    stay = vn[vn["population"] == "stay"]

    def cell(df, code, year):
        return int(df[(df["visa_code"] == code) & (df["year"] == year)]["n"].sum())

    f6 = reg[(reg["visa_code"] == "F6") & (reg["n"] > 0)]
    F["f6_first_year"] = str(int(f6["year"].min()))
    y6 = int(f6["year"].min())
    F["f6_first"] = fmt(cell(reg, "F6", y6))
    F["f2_first"] = fmt(cell(reg, "F2", y6))
    F["f2_next"] = fmt(cell(reg, "F2", y6 + 1))
    last = int(stay["year"].max())
    F["last"] = str(last)
    F["f4_stay_last"] = fmt(cell(stay, "F4", last))

    nn = rd("nationality_national.csv")
    tot = nn.groupby(["population", "year"])["n"].sum()
    F["reg_2006"] = fmt(tot[("registered", 2006)])
    for y in (2006, 2008, 2009, 2014):
        F["stay_%d" % y] = fmt(tot[("stay", y)])
    r = nn[(nn["population"] == "registered") & nn["country"].isin(RESIDUAL_LINES)]
    per = r.groupby("year")["n"].sum()
    F["residual_min"], F["residual_max"] = fmt(per.min()), fmt(per.max())

    # resident population, summed over provinces
    sd = rd("summary_by_sido.csv")
    rp = sd.groupby("year")["resident_pop"].sum()
    y0, yp, yl = int(rp.index.min()), int(rp.idxmax()), int(rp.index.max())
    F["respop"] = ("%.1fM in %d, peaking at %.1fM in %d and %.1fM in %d"
                   % (rp[y0] / 1e6, y0, rp[yp] / 1e6, yp, rp[yl] / 1e6, yl))

    # broad-definition columns: district sums (by the province of that year, the
    # first two digits of sigungu_code) against the province rows
    sg = rd("summary_by_sigungu.csv")
    BROAD = [c for c in ("broad_total", "non_naturalized", "workers", "marriage_migrants",
                         "students", "ethnic_koreans", "other_foreigners", "naturalized",
                         "children") if c in sg.columns and c in sd.columns]
    sg = sg.assign(_p=sg["sigungu_code"].map(lambda v: "" if v != v else str(v)[:2]))
    a = sg.groupby(["year", "_p"])[BROAD].sum(min_count=1)
    b = sd.assign(_p=sd["sido_code"].astype(str)).groupby(["year", "_p"])[BROAD].sum(min_count=1)
    gap = (a - b).abs().max(axis=1).dropna()
    gap = gap[gap > 0]
    if gap.empty:
        F["broad_gap"] = "nothing"
    else:
        names = dict(zip(sd["sido_code"].astype(str), sd["sido"]))
        provs = sorted({p_ for _, p_ in gap.index})
        ys = sorted({int(y) for y, _ in gap.index})
        pl = [names.get(p_, p_) for p_ in provs]
        F["broad_gap"] = ("at most %d people, in %s in %d-%d"
                          % (int(gap.max()), (", ".join(pl[:-1]) + " and " + pl[-1])
                             if len(pl) > 1 else pl[0], ys[0], ys[-1]))

    # the yearbook's non-nationality lines below the national level
    nb = rd("nationality_by_sigungu.csv")
    # 기타 is left out: in the 2008-2013 district tables it is the yearbook's residual
    # of the nationalities it does not list, not the status table's 기타 line.
    hit = nb[nb["country"].isin([c for c in RESIDUAL_LINES if c != "기타"]) & (nb["n"] > 0)]
    if hit.empty:
        F["district_residuals"] = "none"
    elif len(hit) > 3:
        F["district_residuals"] = ("%d district-years, %s people"
                                   % (len(hit), fmt(hit["n"].sum())))
    else:
        F["district_residuals"] = "; ".join(
            "%s in %d, %s %s, %s %s" % (r.country, r.year, r.sido, r.sigungu, fmt(r.n),
                                        "person" if r.n == 1 else "people")
            for r in hit.sort_values(["year", "sido", "sigungu"]).itertuples())
    # 2026-09-26 (4차 대조): province rows against the district sums, and the district
    # tables against the national ones. These sentences were hand-kept and described
    # the parser's losses (UK columns overwritten, sub-office and residual lines
    # dropped) as the yearbook's own figures.
    sgc = sg.assign(_p=sg["sigungu_code"].map(lambda v: "" if v != v else str(v)[:2]))
    dp = sgc.groupby(["year", "_p"])["registered_foreigners"].sum()
    sp = sd.assign(_p=sd["sido_code"].astype(str)).groupby(["year", "_p"])["registered_foreigners"].sum()
    j = pd.concat([dp.rename("d"), sp.rename("s")], axis=1).dropna()
    bad_years = sorted({int(y) for (y, _), r in j.iterrows() if r["d"] != r["s"]})
    nat_gap = (sd.groupby("year")["registered_foreigners"].sum()
               - sg.groupby("year")["registered_foreigners"].sum()).dropna()
    nat_gap = nat_gap[nat_gap.index.isin(bad_years)]
    F["sido_eq_from"] = str(max(bad_years) + 1) if bad_years else str(int(j.index.get_level_values(0).min()))
    F["sido_gap_years"] = "%d-%d" % (min(bad_years), max(bad_years)) if bad_years else "none"
    # 2026-09-26 (5차 대조): the gap can run either way (2014: the district file holds
    # one stateless 화성시 resident the province row leaves out), so its size is stated.
    _mx = int(nat_gap.abs().max()) if len(nat_gap) else 0
    F["sido_gap_range"] = "at most %s %s" % (fmt(_mx), "person" if _mx == 1 else "people")
    # visa_by_sigungu carries the district table's 기타 column as ETC since 5차 대조;
    # the README quotes it and says it equals visa_national's ETC, so check that here.
    vb_ = rd("visa_by_sigungu.csv")
    etc_d = vb_[vb_["visa_code"] == "ETC"].groupby("year")["n"].sum()
    etc_n = reg[reg["visa_code"] == "ETC"].groupby("year")["n"].sum()
    etc_n = etc_n[etc_n > 0]
    if not etc_d.reindex(etc_n.index).fillna(-1).astype(int).equals(etc_n.astype(int)):
        raise SystemExit("readme_facts: visa_by_sigungu ETC differs from visa_national ETC")
    ns_ = nb.groupby("year")["n"].sum()
    F["etc_2020"] = fmt(etc_d[2020])
    F["etc_last"] = fmt(etc_d[last])
    F["dist_gap_last"] = fmt(tot[("registered", last)] - ns_[last])
    na_ = rd("national_annual.csv").set_index("year")
    F["broad_ratio_2008"] = "%.2f" % (na_.loc[2008, "broad_total"] / na_.loc[2008, "foreign_total"])
    F["broad_ratio_last"] = "%.2f" % (na_.loc[last, "broad_total"] / na_.loc[last, "foreign_total"])

    # Against the published v1.1.0 (2026-09-26, 4차 대조: these were hand-kept and
    # moved when the district counts did). Only when the v1.1.0 zip is present.
    zp = os.path.join(RELEASE, "data deposit", "KIRD_openicpsr_deposit_v1.1.0.zip")
    if os.path.exists(zp):
        import zipfile
        z = zipfile.ZipFile(zp)
        pick = lambda k: next(n for n in z.namelist() if n.endswith(k))
        o = pd.read_csv(z.open(pick("summary_national.csv")), encoding="utf-8-sig")
        j = o.merge(rd("national_annual.csv"), on="year").dropna(
            subset=["morans_I_share_x", "morans_I_share_y"])
        d = (j["morans_I_share_x"] - j["morans_I_share_y"]).abs()
        d = d[d > 0]
        F["moran_min"], F["moran_max"] = "%.4f" % d.min(), "%.4f" % d.max()
        F["moran_years"] = str(len(d))
        os_ = pd.read_csv(z.open(pick("summary_by_sigungu.csv")), encoding="utf-8-sig")
        m = os_.merge(sg, on=["year", "sido", "sigungu"])
        dd = m["lisa_x"] != m["lisa_y"]
        F["lisa_diff"], F["lisa_joined"] = fmt(dd.sum()), fmt(len(m))
        F["lisa_diff_pre"] = fmt((dd & (m["year"] <= 2013)).sum())
        F["lisa_diff_post"] = fmt((dd & (m["year"] >= 2014)).sum())

    # the deposit's shape: tables, data files, and columns (= variables)
    csvs = [os.path.join(d, f) for d in data_dirs()[:2] for f in os.listdir(d)
            if f.endswith(".csv")]
    top = {"national_annual.csv", "summary_by_sido.csv", "summary_by_sigungu.csv",
           "summary_by_eupmyeondong.csv"}
    ncol = {}
    for p in csvs:
        with io.open(p, encoding="utf-8-sig", newline="") as fh:
            ncol[os.path.basename(p)] = len(next(csv.reader(fh)))
    F["n_tables"] = str(len(csvs))
    F["n_datafiles"] = str(sum(1 for d in data_dirs()[:2] for f in os.listdir(d)
                               if f.endswith((".csv", ".dta"))))
    F["vars_all"] = fmt(sum(ncol.values()))
    F["vars_summary"] = fmt(sum(v for k, v in ncol.items() if k in top))
    return F


# (fact, pattern). The pattern must match exactly once in each README that carries
# the sentence; group "v" is the value. Whitespace in the prose may wrap, so the
# patterns use \s+ between words.
def _p(s):
    return re.compile(s, re.S)


CLAIMS = [
    ("f6_first_year", _p(r"F-6\s+\(결혼이민, marriage migrant\)\s+first appears in (?P<v>\d{4})\s+\(")),
    ("f6_first", _p(r"first appears in \d{4}\s+\((?P<v>[\d,]+) registered\)")),
    ("f2_first", _p(r"which falls from (?P<v>[\d,]+) in \d{4} to")),
    ("f2_next", _p(r"which falls from [\d,]+ in \d{4} to (?P<v>[\d,]+) in \d{4}")),
    ("f4_stay_last", _p(r"largest single status on the staying basis, at\s+(?P<v>[\d,]+) in \d{4}")),
    ("residual_min", _p(r"carry them as rows of their own\s+\((?P<v>[\d,]+) to [\d,]+ registered")),
    ("residual_max", _p(r"carry them as rows of their own\s+\([\d,]+ to (?P<v>[\d,]+) registered")),
    ("respop", _p(r"Resident population totals match MOIS\s+\((?P<v>[^)]*)\)")),
    ("district_residuals", _p(r"Below the national level the only such rows are:\s+(?P<v>[^.]*)\.")),
    ("broad_gap", _p(r"differ from the\s+province row by\s+(?P<v>[^;]*);")),
    ("reg_2006", _p(r"Registered 2006 is (?P<v>[\d,]+) in the deposited files")),
    ("stay_2006", _p(r"staying 2006\s+(?P<v>[\d,]+)\s+\(")),
    ("stay_2008", _p(r"staying 2006\s+[\d,]+\s+\([\d,]+\), 2008\s+(?P<v>[\d,]+)")),
    ("stay_2009", _p(r", 2009\s+(?P<v>[\d,]+)\s+\([\d,]+\) and 2014")),
    ("stay_2014", _p(r"\)\s+and 2014\s+(?P<v>[\d,]+)\s+\(")),
    ("sido_eq_from", _p(r"and from (?P<v>\d{4}) it equals the sum of that")),
    ("sido_gap_years", _p(r"province's districts in every province and year\. In (?P<v>\d{4}-\d{4}) the")),
    ("sido_gap_range", _p(r"differ from the district sum by (?P<v>at most [\d,]+ (?:person|people)) a year")),
    ("etc_2020", _p(r"363 people in 2013, (?P<v>[\d,]+) at the 2020 peak")),
    ("etc_last", _p(r"at the 2020 peak and (?P<v>[\d,]+) in \d{4}, the\s+same as")),
    ("dist_gap_last", _p(r"itself sits (?P<v>[\d,]+) below the national total")),
    ("broad_ratio_2008", _p(r"ran (?P<v>[\d.]+) times `registered_foreigners` in 2008")),
    ("broad_ratio_last", _p(r"in 2008 and (?P<v>[\d.]+) times in \d{4}")),
    ("moran_years", _p(r"`morans_I_share` differs in all (?P<v>\d+) years")),
    ("moran_min", _p(r"\(by (?P<v>0\.\d{4}) to\s+0\.\d{4}")),
    ("moran_max", _p(r"\(by 0\.\d{4} to\s+(?P<v>0\.\d{4})")),
    ("lisa_diff", _p(r"`lisa`(?: differs)? in (?P<v>[\d,]+) of\s+(?:the )?[\d,]+\s+(?:matched )?district-years")),
    ("lisa_joined", _p(r"`lisa`(?: differs)? in [\d,]+ of\s+(?:the )?(?P<v>[\d,]+)\s+(?:matched )?district-years")),
    ("lisa_diff_pre", _p(r"(?:district-years,\s+|\. )(?P<v>[\d,]+) of (?:them|the [\d,]+ are)\s+2008-2013")),
    ("lisa_diff", _p(r"[\d,]+ of the (?P<v>[\d,]+) are\s+2008-2013")),
    ("lisa_diff_post", _p(r"the other (?P<v>[\d,]+) are spread over 2014-2024")),
    ("n_tables", _p(r"and its (?P<v>\d+) tables carry")),
    ("vars_all", _p(r"tables carry (?P<v>[\d,]+) variables between them")),
    ("vars_summary", _p(r"variables between them \((?P<v>[\d,]+) in the four summary")),
    ("n_datafiles", _p(r"it is the (?P<v>\d+) data files that exceed")),
]
# Claims the upload notes must carry.
REQUIRED_META = {"n_tables", "vars_all", "vars_summary", "n_datafiles"}

# Claims every README that describes the data must carry (the GitHub README is a
# shorter code-first document and carries only the file table).
REQUIRED = {"f6_first", "f2_first", "f2_next", "f4_stay_last", "residual_min",
            "residual_max", "respop", "district_residuals", "broad_gap",
            "sido_eq_from", "sido_gap_years", "sido_gap_range", "etc_2020",
            "etc_last", "dist_gap_last"}

ROW = re.compile(r"^\|\s*`?([A-Za-z0-9_]+\.csv)`?\s*\|")
YEARS = re.compile(r"^\s*((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2})\s*$")
COUNT = re.compile(r"^\s*[\d,]+\s*$")


def table_facts(name):
    p = find(name)
    if p is None:
        return None
    years, rows = set(), 0
    with io.open(p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            rows += 1
            y = r.get("year")
            if y:
                try:
                    years.add(int(float(y)))
                except ValueError:
                    pass
    return (min(years) if years else None, max(years) if years else None, rows)


def fix_table_line(line, name):
    got = table_facts(name)
    if not got:
        return line, ["%s: not in the deposit" % name]
    y0, y1, n = got
    cells = line.split("|")
    notes = []
    for i, c in enumerate(cells):
        m = YEARS.match(c)
        if m and y0 is not None:
            want = "%d-%d" % (y0, y1)
            if "%s-%s" % (m.group(1), m.group(2)) != want:
                notes.append("%s years %s-%s -> %s" % (name, m.group(1), m.group(2), want))
                cells[i] = " %s " % want
            continue
        if COUNT.match(c):
            want = fmt(n)
            if c.strip() != want:
                notes.append("%s rows %s -> %s" % (name, c.strip(), want))
                cells[i] = " %s " % want
    return "|".join(cells), notes


# ---------------------------------------------------------------- file tables
# 2026-09-26 (4차 대조): the release README's two file tables were kept by hand and
# had fallen out of step with the deposit README: national_annual sat under
# "Breakdowns", and the four crosswalk/weights tables had no row at all. Both READMEs
# now take their tables from this one list, between marker comments, and --check
# fails when a README's tables miss a file its folder holds or list one it does not.
# (file, section, grain, source); "summary" rows carry no source column.
FILE_TABLE = [
    ("national_annual.csv", "summary", "year (whole country)", None),
    ("summary_by_sido.csv", "summary", "sido × year", None),
    ("summary_by_sigungu.csv", "summary", "sido × sigungu × year", None),
    ("summary_by_eupmyeondong.csv", "summary",
     "sido × sigungu × eup·myeon·dong × year (+ official dong code)", None),
    ("nationality_by_sigungu.csv", "breakdown", "sido × sigungu × nationality × year", "MOJ"),
    ("nationality_by_sido.csv", "breakdown", "sido × nationality × year (district sums)", "MOJ"),
    ("nationality_national.csv", "breakdown", "population × nationality × year", "MOJ"),
    ("visa_by_sigungu.csv", "breakdown", "sido × sigungu × visa status × year", "MOJ"),
    ("visa_by_sido.csv", "breakdown", "sido × visa status × year (district sums)", "MOJ"),
    ("visa_national.csv", "breakdown", "population × visa status × year", "MOJ"),
    ("visa_by_nationality.csv", "breakdown", "population × nationality × visa × year", "MOJ"),
    ("age_sex_national.csv", "breakdown",
     "population × nationality × age × sex × year", "MOJ"),
    ("children_by_age.csv", "breakdown", "sido × sigungu × age (0-18) × year", "MOIS"),
    ("multicultural_households.csv", "breakdown",
     "… × eup·myeon·dong × household-member type × year", "MOIS"),
    ("naturalization_annual.csv", "breakdown", "year × processing type", "MOJ"),
    ("naturalization_by_country.csv", "breakdown",
     "former nationality × processing type × year", "MOJ"),
    ("naturalization_by_age.csv", "breakdown", "age band × processing type × year", "MOJ"),
    ("ethnic_enclaves.csv", "breakdown", "year × sigungu × nationality", "derived"),
    ("language_demand.csv", "breakdown",
     "year × scope (national, sido, sigungu) × language", "derived"),
    ("segregation_by_nationality.csv", "breakdown", "nationality × year", "derived"),
    ("region_segregation.csv", "breakdown",
     "continent of origin (`continent` column) × year", "derived"),
    ("refugee_by_nationality.csv", "breakdown",
     "status × nationality, cumulative 1994-2024 (deposit only)", "MOJ"),
    ("refugee_language_demand.csv", "breakdown",
     "status × language, cumulative 1994-2024 (deposit only)", "derived"),
    ("diaspora_residence_by_sido.csv", "breakdown",
     "sido × nationality × year (residence reports, not the registered-foreigner "
     "register)", "MOJ"),
    ("crosswalk_country.csv", "breakdown",
     "nationality label × edition, with the harmonized name, English label and "
     "continent (`continent` / `continent_en`: the nationality-to-continent map behind "
     "`continent_H` and `region_segregation`)", "derived"),
    ("crosswalk_region.csv", "breakdown",
     "place names: province, district and sub-district renames, moves and boundary "
     "lineage (the chains behind the continuous district labels)", "derived"),
    ("crosswalk_visa.csv", "breakdown", "visa code × label, Korean and English", "derived"),
    ("language_weights.csv", "breakdown",
     "nationality × language × share, the first-language shares behind "
     "`language_demand`", "derived"),
]
# Tables with no year column: what the Years cell says instead.
YEARS_FIXED = {"crosswalk_country.csv": "2006-2024 editions",
               "crosswalk_visa.csv": "2006-2024 editions",
               "crosswalk_region.csv": "fixed", "language_weights.csv": "fixed",
               "refugee_by_nationality.csv": "snapshot",
               "refugee_language_demand.csv": "snapshot"}
MARK = re.compile(r"(<!-- file-table:(summary|breakdown) -->)(.*?)(<!-- /file-table -->)", re.S)


def years_cell(name):
    if name in YEARS_FIXED:
        return YEARS_FIXED[name]
    d = pd.read_csv(find(name), encoding="utf-8-sig", low_memory=False,
                    usecols=lambda c: c in ("year", "population"))
    if name == "age_sex_national.csv":
        g = d.groupby("population")["year"].agg(["min", "max"]).sort_values("min")
        return "; ".join("%s %d-%d" % (k, r["min"], r["max"]) for k, r in g.iterrows())
    return "%d-%d" % (d["year"].min(), d["year"].max())


def render_table(section, present, nl):
    rows = [r for r in FILE_TABLE if r[1] == section and r[0] in present]
    if section == "summary":
        out = ["| File | Grain | Years |", "|---|---|---|"]
        out += ["| %s | %s | %s |" % (f, g, years_cell(f)) for f, _, g, _ in rows]
    else:
        out = ["| File | Grain | Years | Source |", "|---|---|---|---|"]
        out += ["| %s | %s | %s | %s |" % (f, g, years_cell(f), src)
                for f, _, g, src in rows]
    return nl + nl.join(out) + nl


def present_files(path):
    """The tables in the folder a README describes."""
    if os.path.normcase(os.path.dirname(path)) == os.path.normcase(RELEASE):
        return {f for f in os.listdir(RELEASE_DATA) if f.endswith(".csv")}
    have = set()
    for d in (os.path.join(DEPOSIT, "data"), os.path.join(DEPOSIT, "data", "detailed_data")):
        if os.path.isdir(d):
            have |= {f for f in os.listdir(d) if f.endswith(".csv")}
    return have


def refresh_tables(path, s, nl):
    """Rewrite the marked file tables; report files the tables miss or add."""
    notes, problems = [], []
    present = present_files(path)
    unknown = sorted(present - {r[0] for r in FILE_TABLE})
    if unknown:
        problems.append("tables with no FILE_TABLE entry: %s" % unknown)
    marks = list(MARK.finditer(s))
    if marks:
        out, last = [], 0
        for m in marks:
            want = render_table(m.group(2), present, nl)
            if m.group(3) != want:
                notes.append("file table (%s) regenerated" % m.group(2))
            out += [s[last:m.start(3)], want]
            last = m.end(3)
        out.append(s[last:])
        s = "".join(out)
    listed = [m.group(1) for m in (ROW.match(l) for l in s.split(nl)) if m]
    dup = sorted({f for f in listed if listed.count(f) > 1})
    miss = sorted(present - set(listed))
    extra = sorted(set(listed) - present)
    if dup:
        problems.append("files listed twice in the tables: %s" % dup)
    if miss:
        problems.append("files the folder holds but no table lists: %s" % miss)
    if extra:
        problems.append("files a table lists but the folder lacks: %s" % extra)
    return s, notes, problems


def refresh(path, F, check):
    s = io.open(path, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in s else "\n"
    notes, problems = [], []
    if os.path.basename(path) == "README.md":
        s, n0, p0 = refresh_tables(path, s, nl)
        notes += n0
        problems += p0
    # 1) the file table
    out = []
    for line in s.split(nl):
        m = ROW.match(line)
        if m:
            line, n = fix_table_line(line, m.group(1))
            notes += n
        out.append(line)
    s = nl.join(out)
    # 2) the quoted numbers
    seen = set()
    for key, pat in CLAIMS:
        hits = list(pat.finditer(s))
        if not hits:
            continue
        if len(hits) > 1:
            problems.append("%s: anchor matches %d times" % (key, len(hits)))
            continue
        seen.add(key)
        m = hits[0]
        want = F[key]
        if m.group("v") != want:
            notes.append("%s %r -> %r" % (key, m.group("v"), want))
            s = s[:m.start("v")] + want + s[m.end("v"):]
    if os.path.basename(path) == "OPENICPSR_METADATA.md":
        lost = sorted(REQUIRED_META - seen)
        if lost:
            problems.append("anchors not found (sentence reworded?): %s" % lost)
    elif os.path.basename(os.path.dirname(path)) != os.path.basename(GITHUB):
        lost = sorted(REQUIRED - seen)
        if lost:
            problems.append("anchors not found (sentence reworded?): %s" % lost)
    if notes and not check:
        io.open(path, "w", encoding="utf-8", newline="").write(s)
    return notes, problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    F = facts()
    rc = 0
    for path in TARGETS:
        if not os.path.exists(path):
            print("readme_facts: %s absent, skipped" % path)
            continue
        notes, problems = refresh(path, F, check)
        label = os.path.relpath(path, RELEASE)
        if notes:
            print("%s: %d value(s) %s" % (label, len(notes),
                                        "differ from the data" if check else "rewritten"))
            for n in notes:
                print("   " + n)
            if check:
                rc = 1
        else:
            print("%s: every quoted number matches the data" % label)
        for p in problems:
            print("   PROBLEM " + p)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
