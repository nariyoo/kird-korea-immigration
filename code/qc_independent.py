# -*- coding: utf-8 -*-
"""인구 데이터셋을 **관문과 무관하게** 다시 검산한다.

`validate_release.py` 는 릴리스가 스스로 앞뒤가 맞는지 본다. 이 파일은 그것을
다시 부르지 않는다 — 같은 논리를 두 번 돌리면 같은 사각지대를 두 번 지나간다.
여기서는 파일들 사이의 **합이 맞는지**, 열쇠가 유일한지, 값이 있을 수 있는
범위인지, 연도가 끊기지 않는지를 처음부터 센다.

    python qc_demo.py
"""
import collections
import csv
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
# 2026-09-19: 여기에 G: 드라이브 절대 경로가 박혀 있었다. 프로젝트가
# 드롭박스로 옮겨간 뒤로 이 검사는 한 번도 돌지 못했다(폴더 없음).
# 제 자리에서 찾고, 인자로 다른 폴더를 줄 수도 있게 둔다.
HERE = os.path.dirname(os.path.abspath(__file__))
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
D = (os.path.abspath(_ARGS[0]) if _ARGS
     else os.path.join(os.path.dirname(HERE), "data"))
if not os.path.isdir(D):
    raise SystemExit("자료 폴더가 없다: %s" % D)
findings = []


def note(sev, key, msg):
    findings.append((sev, key, msg))


def _path(name):
    # 기탁본은 요약 넷을 data/ 에, 나머지를 data/detailed_data/ 에 둔다. 둘 다 본다.
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
print("파일 %d개" % len(files))

# ------------------------------------------------------------ 1. 열쇠 유일성
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
    # 2026-09-25: 이름 열쇠로는 유일했는데 코드로는 겹쳤다(2024 부천시 세 구가 모두
    # 41190). 코드 열쇠로 다시 센다.
    "children_by_age.csv": ["year", "sigungu_code", "age"],
}
for f, keys in KEYS.items():
    rows = load(f)
    seen = collections.Counter(tuple(r.get(k, "") for k in keys) for r in rows)
    dup = [k for k, n in seen.items() if n > 1]
    if dup:
        note("고쳐야 함", "열쇠 중복",
             "%s: %d개 열쇠가 두 번 이상 (%s …)" % (f, len(dup), dup[0]))

# 1b. 읍면동 코드: 한 해 안에서 한 코드가 두 곳을 가리키면 안 된다 (2023 하남시
#     풍산동이 고양 일산동구 풍산동의 코드를, 2024 창원 성산구 중앙동이 진주 중앙동의
#     코드를 달고 있었다). 빈 코드는 세지 않는다.
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

# ------------------------------------------------------------ 2. 층 사이의 합
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


# 시군구 합 == 시도 값 (자격별)
vg, vs = load("visa_by_sigungu.csv"), load("visa_by_sido.csv")
col = "n" if "n" in (vg[0] if vg else {}) else None
if col is None:
    for cand in ("count", "value", "population", "n_persons"):
        if vg and cand in vg[0]:
            col = cand
            break
if col:
    a = total_by(vg, ["year", "sido", "visa_code"], col)
    b = total_by(vs, ["year", "sido", "visa_code"], col)
    both = set(a) & set(b)
    bad = [(k, a[k], b[k]) for k in both if abs(a[k] - b[k]) > 0.5]
    print("자격별 시군구합 대 시도값: 견준 짝 %d · 어긋난 것 %d"
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

# ------------------------------------------------------------ 3. 값의 범위
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

# ------------------------------------------------------------ 4. 연도 연속성
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

# ------------------------------------------------------------ 5. 조화표 완전성
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

# ------------------------------------------------------------ 보고
print()
by = collections.Counter(k for _, k, _ in findings)
print("찾은 것 %d건" % len(findings))
for k, n in by.most_common():
    print("  %-12s %d" % (k, n))
print()
for sev, k, m in findings:
    print("  [%s] %-10s %s" % (sev, k, m[:150]))
if not findings:
    print("  독립 검산에서 걸린 것 없음")

# 고쳐야 할 것이 하나라도 있으면 1 로 끝난다 (관문으로 쓸 수 있게). 2026-09-25.
sys.exit(1 if any(s == "고쳐야 함" for s, _, _ in findings) else 0)
