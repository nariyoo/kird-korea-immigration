# -*- coding: utf-8 -*-
"""Recheck the population dataset **independently of the gate**.

`validate_release.py` checks that the release is internally consistent. This file
does not call it again: running the same logic twice passes the same blind spots
twice. Here we count from scratch whether **sums agree** across files, whether keys
are unique, whether values lie in a possible range, and whether years are unbroken.

    python qc_demo.py
"""
import collections
import csv
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
# 2026-09-19: an absolute G: drive path was hardcoded here. After the project
# moved to Dropbox this check never ran once (folder not found).
# Look relative to this file, and allow another folder as an argument.
HERE = os.path.dirname(os.path.abspath(__file__))
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
D = (os.path.abspath(_ARGS[0]) if _ARGS
     else os.path.join(os.path.dirname(HERE), "data"))
if not os.path.isdir(D):
    raise SystemExit("data folder not found: %s" % D)
findings = []


def note(sev, key, msg):
    findings.append((sev, key, msg))


def _path(name):
    # The deposit puts the four summaries in data/ and the rest in
    # data/detailed_data/. Look in both.
    for base in (D, os.path.join(D, "detailed_data")):
        if os.path.exists(os.path.join(base, name)):
            return os.path.join(base, name)
    return os.path.join(D, name)


def load(name):
    with io.open(_path(name), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(v):
    v = str(v or "").strip().replace(",", "")
    if v in ("", "NA", "nan", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


files = sorted(f for base in (D, os.path.join(D, "detailed_data")) if os.path.isdir(base)
               for f in os.listdir(base) if f.endswith(".csv"))
print("%d files" % len(files))

# ------------------------------------------------------------ 1. key uniqueness
KEYS = {
    "summary_by_sido.csv": ["year", "sido"],
    "summary_by_sigungu.csv": ["year", "sido", "sigungu"],
    "summary_by_eupmyeondong.csv": ["year", "sido", "sigungu", "eupmyeondong"],
    "visa_national.csv": ["year", "population", "visa_code"],
    "visa_by_sido.csv": ["year", "sido", "visa_code"],
    "visa_by_sigungu.csv": ["year", "sido", "sigungu", "visa_code"],
    "nationality_national.csv": ["year", "population", "country"],
    "age_sex_national.csv": ["year", "population", "country", "gender", "age_group"],
    "nationality_by_sido.csv": ["year", "sido", "country"],
    "nationality_by_sigungu.csv": ["year", "sido", "sigungu", "country"],
    "diaspora_residence_by_sido.csv": ["year", "sido", "country"],
    "national_annual.csv": ["year"],
    "region_segregation.csv": ["year", "continent"],
    "segregation_by_nationality.csv": ["year", "country"],
    # 2026-09-25: unique on the name key but duplicated on the code (in 2024 all three
    # gu of Bucheon had 41190). Count again on the code key.
    "children_by_age.csv": ["year", "sigungu_code", "age"],
}
for f, keys in KEYS.items():
    rows = load(f)
    seen = collections.Counter(tuple(r.get(k, "") for k in keys) for r in rows)
    dup = [k for k, n in seen.items() if n > 1]
    if dup:
        note("고쳐야 함", "열쇠 중복",
             "%s: %d개 열쇠가 두 번 이상 (%s …)" % (f, len(dup), dup[0]))

# 1b. Sub-district (eup/myeon/dong) codes: within a year one code must not point to
#     two places (in 2023 Pungsan-dong, Hanam carried the code of Pungsan-dong,
#     Goyang Ilsandong-gu, and in 2024 Jungang-dong, Changwon Seongsan-gu carried the
#     code of Jungang-dong, Jinju). Empty codes are not counted.
for f in ("multicultural_households.csv", "summary_by_eupmyeondong.csv"):
    if f not in files:
        continue
    place = collections.defaultdict(set)
    for r in load(f):
        c = (r.get("adm_code") or "").strip()
        if c:
            place[(r["year"], c)].add((r["sido"], r["sigungu"], r["eupmyeondong"]))
    dup = {k: v for k, v in place.items() if len(v) > 1}
    if dup:
        k = sorted(dup)[0]
        note("고쳐야 함", "코드 중복",
             "%s: adm_code %d개가 한 해에 두 곳 이상 (%s %s -> %s)"
             % (f, len(dup), k[0], k[1], sorted(dup[k])))

# ------------------------------------------------------------ 2. sums across levels
def total_by(rows, level, valcol, extra=None):
    out = collections.defaultdict(float)
    for r in rows:
        v = num(r.get(valcol))
        if v is None:
            continue
        if extra and not extra(r):
            continue
        out[tuple(r.get(k, "") for k in level)] += v
    return out


# district sum == province value (by visa status)
vg, vs = load("visa_by_sigungu.csv"), load("visa_by_sido.csv")
col = "n" if "n" in (vg[0] if vg else {}) else None
if col is None:
    for cand in ("count", "value", "population", "n_persons"):
        if vg and cand in vg[0]:
            col = cand
            break
if col:
    # The province is the one the district belonged to in that year, i.e. the first
    # two digits of sigungu_code. The district file uses the 2024 province names in
    # every year (Gunwi-gun is always Daegu, Sejong is Sejong Special Self-Governing
    # City from 2008). 2026-09-26 (third cross-check).
    for r in vg:
        r["_p"] = (r.get("sigungu_code") or "").split(".")[0][:2]
    for r in vs:
        r["_p"] = (r.get("sido_code") or "").split(".")[0].zfill(2)
    a = total_by(vg, ["year", "_p", "visa_code"], col)
    b = total_by(vs, ["year", "_p", "visa_code"], col)
    both = set(a) & set(b)
    bad = [(k, a[k], b[k]) for k in both if abs(a[k] - b[k]) > 0.5]
    print("district sum vs province value by visa status: %d pairs compared, %d differ"
          % (len(both), len(bad)))
    if bad:
        note("봐야 함", "층 합",
             "visa 시군구합≠시도 %d짝 (보기 %s: %s 대 %s)"
             % (len(bad), bad[0][0], bad[0][1], bad[0][2]))
    only_g = set(a) - set(b)
    if only_g:
        note("봐야 함", "층 짝",
             "시군구에만 있는 (해,시도,자격) %d개 (보기 %s)"
             % (len(only_g), sorted(only_g)[0]))

# ------------------------------------------------------------ 3. value ranges
for f in files:
    rows = load(f)
    if not rows:
        note("고쳐야 함", "빈 파일", f)
        continue
    for cname in rows[0]:
        vals = [num(r.get(cname)) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals or len(vals) < len(rows) * 0.5:
            continue
        neg = [v for v in vals if v < 0]
        if neg and not any(t in cname for t in
                           ("moran", "change", "diff", "growth", "delta")):
            note("봐야 함", "음수",
                 "%s.%s: 음수 %d개 (가장 작은 값 %s)"
                 % (f, cname, len(neg), min(neg)))
        if cname.endswith(("_share", "_pct", "_rate")) or "share" in cname:
            out = [v for v in vals if v < 0 or v > 100]
            if out:
                note("봐야 함", "비율 범위",
                     "%s.%s: 0~100 밖 %d개" % (f, cname, len(out)))

# ------------------------------------------------------------ 4. year continuity
for f in files:
    rows = load(f)
    if not rows or "year" not in rows[0]:
        continue
    ys = sorted({int(r["year"]) for r in rows
                 if str(r.get("year", "")).strip().isdigit()})
    if not ys:
        continue
    gaps = [y for y in range(ys[0], ys[-1] + 1) if y not in ys]
    if gaps:
        note("봐야 함", "연도 구멍", "%s: %s~%s 사이에 %s 없음"
             % (f, ys[0], ys[-1], gaps))

# ------------------------------------------------------------ 5. crosswalk completeness
try:
    cw = {r["source_code"]: r for r in load("crosswalk_visa.csv")}
    used = {r.get("visa_code", "") for r in load("visa_national.csv")}
    miss = sorted(u for u in used if u and u not in cw
                  and u not in {r.get("visa_code") for r in cw.values()})
    if miss:
        note("봐야 함", "조화표",
             "visa_code %d개가 crosswalk_visa 에 없다 (%s)" % (len(miss), miss[:6]))
except Exception as e:                                        # noqa: BLE001
    note("봐야 함", "조화표", "visa 조화표를 못 읽었다: %s" % e)

# ------------------------------------------------------------ report
print()
by = collections.Counter(k for _, k, _ in findings)
print("%d findings" % len(findings))
for k, n in by.most_common():
    print("  %-12s %d" % (k, n))
print()
for sev, k, m in findings:
    print("  [%s] %-10s %s" % (sev, k, m[:150]))
if not findings:
    print("  nothing flagged by the independent check")

# Exit with 1 if anything must be fixed (so this can serve as a gate). 2026-09-25.
sys.exit(1 if any(s == "고쳐야 함" for s, _, _ in findings) else 0)
