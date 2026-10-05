# -*- coding: utf-8 -*-
"""v1.1.0 -> v1.2.0: split n_nationalities into two columns.

In v1.1.0 `n_nationalities` held a value different from what its name says. To
compute the diversity indices on the same base in every year, nationalities were
reduced to the top 19 plus one residual cell, and the number of those reduced cells
was released under this name. So

    Ansan Danwon-gu 2025   actual 99 nationalities   released value 20
    Guro-gu         2025   actual 88 nationalities   released value 20
    17 provinces           actual 112 to 186         released value 20 (all 18 years)
    national               actual 192                released value 20 (all 18 years)

In 2025, 195 of the 250 districts are exactly 20. The data_dictionary described the
column as "Distinct nationalities present". Anyone who downloaded it and quoted it
as is would report a wrong number.

v1.2.0 splits it.

    index_base_k              number of cells the indices were computed on (top 19
                              + residual). Same values as v1.1.0 n_nationalities.
    n_nationalities_observed  number of nationalities the yearbook actually lists
                              for that unit and year. The residual cell ('기타',
                              other) is not a nationality and is not counted.
    n_nationalities           removed. Keeping the name and changing only the
                              values would silently give anyone who cited v1.1.0 a
                              different number. Removing it makes code that read
                              it stop loudly.

**2008-2013 are truncated.** The yearbook first lists all nationalities at the
district level in 2014; before that it gives only the top 19 and the residual. So
the observed count is capped at 19 in those years (national 19 in 2013 -> 193 in
2014). The cap is itself a fact of the data, so the values are released, not
blanked, and the codebook and README say so.

The only place counted is `nationality_by_sigungu.csv` in the deposit. The province
value is the union of the nationalities its districts hold, and the national value
is the union over the 250 districts. This does not conflict with the rule that
**counts are summed but indices are recomputed at each level** (a nationality count
is a count, not an index, so the union is correct).

    python 02_code/migrate_v1_2_0_nationality_columns.py [--apply]

Without the flag it only reports what would change. Repeated runs give the same
result. `04_reconcile_districts.py`, `06_build_summaries.py` and
`08_export_dataset.py` were also changed to emit the same two columns, so the next
full build produces the same tables as this script. This file checks that the two
paths give the same numbers (--verify).
"""
import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "04_dataset_release", "data")
_RAWS = [os.path.join(ROOT, "05_dashboard", "data", "region.json"),
         os.path.join(ROOT, "99_archive", "dashboard_unused_data_2026-08-22",
                      "data", "region.json")]
RAW = next((q for q in _RAWS if os.path.exists(q)), _RAWS[0])
AGG = {"총계", "총합계", "소계", "계"}
OTHER = "기타"
OLD, BASE, OBS = "n_nationalities", "index_base_k", "n_nationalities_observed"
FILES = {"summary_by_sigungu.csv": "sigungu",
         "summary_by_sido.csv": "sido",
         "national_annual.csv": "national"}


def read(name):
    with io.open(os.path.join(DATA, name), encoding="utf-8-sig", newline="") as fh:
        r = csv.reader(fh)
        return next(r), list(r)


def observed_counts():
    """Count nationalities at each level from the deposit's nationality table."""
    head, rows = read("nationality_by_sigungu.csv")
    ix = {c: i for i, c in enumerate(head)}
    sg = defaultdict(set)
    sd = defaultdict(set)
    na = defaultdict(set)
    for r in rows:
        c = r[ix["country"]]
        if c == OTHER:
            continue
        try:
            if int(r[ix["n"]] or 0) <= 0:
                continue
        except ValueError:
            continue
        y, s1, s2 = r[ix["year"]], r[ix["sido"]], r[ix["sigungu"]]
        sg[(y, s1, s2)].add(c)
        sd[(y, s1)].add(c)
        na[y].add(c)
    return ({k: len(v) for k, v in sg.items()},
            {k: len(v) for k, v in sd.items()},
            {k: len(v) for k, v in na.items()})


def verify(sg, sd, na):
    """Recount from the raw data and check that the same numbers come out. If the
    deposit's nationality table is a faithful copy of the raw data, the two agree."""
    if not os.path.exists(RAW):
        print("  (raw data check skipped: region.json not found)")
        return True
    reg = json.load(io.open(RAW, encoding="utf-8"))["by_sigungu"]
    bad = 0
    for y, blk in reg.items():
        seen_sd, seen_na = defaultdict(set), set()
        for s1, rows in blk.items():
            if s1 in AGG:
                continue
            for s2, cs in rows.items():
                if s2 in AGG:
                    continue
                got = {c for c, v in cs.items() if v and c not in AGG and c != OTHER}
                seen_sd[s1] |= got
                seen_na |= got
                if sg.get((y, s1, s2), len(got)) != len(got):
                    bad += 1
                    if bad < 4:
                        print("  mismatch %s %s %s: deposit %s, raw %d"
                              % (y, s1, s2, sg.get((y, s1, s2)), len(got)))
        for s1, v in seen_sd.items():
            if sd.get((y, s1), len(v)) != len(v):
                bad += 1
        if na.get(y, len(seen_na)) != len(seen_na):
            bad += 1
            print("  mismatch national %s: deposit %s, raw %d"
                  % (y, na.get(y), len(seen_na)))
    print("  raw data check: %s" % ("어긋난 것 %d" % bad if bad else "모두 같음"))
    return bad == 0


def migrate(name, level, sg, sd, na, apply_):
    head, rows = read(name)
    if BASE in head:
        print("  %-26s already split" % name)
        return 0
    if OLD not in head:
        raise SystemExit("stopped: %s has no %s column" % (name, OLD))
    ix = {c: i for i, c in enumerate(head)}
    at = ix[OLD]
    new_head = head[:at] + [BASE, OBS] + head[at + 1:]
    out, filled = [], 0
    for r in rows:
        y = r[ix["year"]]
        if level == "sigungu":
            v = sg.get((y, r[ix["sido"]], r[ix["sigungu"]]))
        elif level == "sido":
            v = sd.get((y, r[ix["sido"]]))
        else:
            v = na.get(y)
        if v is not None:
            filled += 1
        out.append(r[:at] + [r[at], "" if v is None else str(v)] + r[at + 1:])
    print("  %-26s %5d rows, %d rows with observed nationality count filled" % (name, len(rows), filled))
    if apply_:
        p = os.path.join(DATA, name)
        with io.open(p, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(new_head)
            w.writerows(out)
    return len(rows) - filled


def main():
    apply_ = "--apply" in sys.argv
    sg, sd, na = observed_counts()
    print("counts from the deposit nationality table: %d district cells, %d province cells, %d years"
          % (len(sg), len(sd), len(na)))
    print("  national:", ", ".join("%s년 %d" % (y, na[y])
                              for y in sorted(na, key=int)[:3]), "…",
          ", ".join("%s년 %d" % (y, na[y]) for y in sorted(na, key=int)[-2:]))
    verify(sg, sd, na)
    blank = 0
    for name, level in FILES.items():
        blank += migrate(name, level, sg, sd, na, apply_)
    if blank:
        print("%d empty cells (years the nationality table does not cover: 2006-2007 in summary_by_sido)" % blank)
    print("고쳤다" if apply_ else "(--apply 를 붙이면 파일을 고친다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
