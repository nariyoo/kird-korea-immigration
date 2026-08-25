# -*- coding: utf-8 -*-
"""v1.1.0 -> v1.2.0: n_nationalities 를 두 칸으로 가른다.

v1.1.0 의 `n_nationalities` 는 이름이 말하는 것과 다른 값이었다. 다양성 지수를
모든 해에 같은 밑변에서 계산하려고 상위 19개국과 잔여 한 칸으로 줄인 뒤, 그
줄인 칸의 개수를 이 이름으로 실었다. 그래서

    안산시 단원구 2025   실제 99개국   실린 값 20
    구로구      2025   실제 88개국   실린 값 20
    시도 열일곱 곳       실제 112~186  실린 값 20 (열여덟 해 내내)
    전국               실제 192      실린 값 20 (열여덟 해 내내)

2025년 시군구 250곳 가운데 195곳이 정확히 20이다. data_dictionary 는 이 칸을
"Distinct nationalities present" 라고 적고 있었다. 내려받은 사람이 그대로
인용하면 틀린 수를 싣게 된다.

v1.2.0 에서 가른다.

    index_base_k              지수를 계산한 칸 수(상위 19 + 잔여). v1.1.0 의
                              n_nationalities 와 값이 같다.
    n_nationalities_observed  그 단위·그 해에 연감이 실제로 싣는 국적 수.
                              잔여 칸(기타)은 국적이 아니므로 세지 않는다.
    n_nationalities           없앤다. 이름을 그대로 두고 값만 바꾸면 v1.1.0 을
                              인용한 사람이 조용히 다른 수를 받는다. 지우면
                              읽던 코드가 소리 내어 멈춘다.

**2008-2013 은 잘려 있다.** 연감이 시군구 단위에서 전체 국적을 싣기 시작한
해가 2014년이고 그 앞은 상위 19개와 잔여뿐이다. 그래서 관측 국적 수는 그
해들에 19로 막힌다(전국 2013년 19 -> 2014년 193). 막힌 것 자체가 자료의
사실이므로 값을 비우지 않고 싣고, 코드북과 README 에 적는다.

세는 자리는 기탁본 안의 `nationality_by_sigungu.csv` 하나다. 시도 값은 그 도
시군구가 가진 국적의 합집합, 전국 값은 250곳의 합집합이며, **인원은 더하지만
지수는 각 층에서 다시 계산한다**는 규칙과 어긋나지 않는다(국적 수는 지수가
아니라 세는 값이라 합집합이 맞다).

    python 02_code/migrate_v1_2_0_nationality_columns.py [--apply]

붙이지 않고 돌리면 무엇이 바뀌는지만 적는다. 여러 번 돌려도 결과가 같다.
`04_reconcile_districts.py`·`06_build_summaries.py`·`08_export_dataset.py` 도
같은 두 칸을 내도록 고쳤으므로, 다음 전체 빌드는 여기서 만든 것과 같은 표를
만든다. 두 길이 같은 수를 내는지 이 파일이 확인한다(--verify).
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
    """기탁본의 국적 표에서 층마다 국적 수를 센다."""
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
    """원자료에서 다시 세어 같은 수가 나오는지 본다. 기탁본의 국적 표가
    원자료를 그대로 옮긴 것이라면 두 수가 같아야 한다."""
    if not os.path.exists(RAW):
        print("  (원자료 대조 건너뜀: region.json 이 없다)")
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
                        print("  어긋남 %s %s %s: 기탁본 %s, 원자료 %d"
                              % (y, s1, s2, sg.get((y, s1, s2)), len(got)))
        for s1, v in seen_sd.items():
            if sd.get((y, s1), len(v)) != len(v):
                bad += 1
        if na.get(y, len(seen_na)) != len(seen_na):
            bad += 1
            print("  어긋남 전국 %s: 기탁본 %s, 원자료 %d"
                  % (y, na.get(y), len(seen_na)))
    print("  원자료 대조: %s" % ("어긋난 것 %d" % bad if bad else "모두 같음"))
    return bad == 0


def migrate(name, level, sg, sd, na, apply_):
    head, rows = read(name)
    if BASE in head:
        print("  %-26s 이미 갈라져 있다" % name)
        return 0
    if OLD not in head:
        raise SystemExit("멈춤: %s 에 %s 칸이 없다" % (name, OLD))
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
    print("  %-26s %5d행, 관측 국적 수 채운 행 %d" % (name, len(rows), filled))
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
    print("기탁본 국적 표에서 센 값: 시군구 %d칸, 시도 %d칸, 해 %d개"
          % (len(sg), len(sd), len(na)))
    print("  전국:", ", ".join("%s년 %d" % (y, na[y])
                              for y in sorted(na, key=int)[:3]), "…",
          ", ".join("%s년 %d" % (y, na[y]) for y in sorted(na, key=int)[-2:]))
    verify(sg, sd, na)
    blank = 0
    for name, level in FILES.items():
        blank += migrate(name, level, sg, sd, na, apply_)
    if blank:
        print("빈 칸 %d개 (국적 표가 닿지 않는 해. summary_by_sido 의 2006-2007)" % blank)
    print("고쳤다" if apply_ else "(--apply 를 붙이면 파일을 고친다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
