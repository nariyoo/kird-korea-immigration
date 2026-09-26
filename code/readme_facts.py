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
]

# Claims every README that describes the data must carry (the GitHub README is a
# shorter code-first document and carries only the file table).
REQUIRED = {"f6_first", "f2_first", "f2_next", "f4_stay_last", "residual_min",
            "residual_max", "respop", "district_residuals", "broad_gap"}

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


def refresh(path, F, check):
    s = io.open(path, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in s else "\n"
    notes, problems = [], []
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
    if os.path.basename(os.path.dirname(path)) != os.path.basename(GITHUB):
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
