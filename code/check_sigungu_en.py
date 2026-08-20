# -*- coding: utf-8 -*-
"""Validate the English district names the dataset publishes.

`sigungu_en` in the released CSVs is copied verbatim from `name_eng` in
`05_dashboard/data/korea_sigungu.json` (see `01_parse_yearbooks.build_sigungu_en`
and `08_export_dataset._load_en_lookups`). Nothing in the pipeline checks that
value, so a wrong romanization in the boundary file reaches the deposit
unnoticed. In August 2026 eight of them were wrong, including 철원군 published
as "Gongju-si" across 1,877 rows.

Two rules catch that class of error without a full romanizer:

  suffix  a name ending in 시 / 군 / 구 must romanize as -si / -gun / -gu,
          which catches "Gongju-si" for 철원군 and "Hwaseongsi" for 화성시.
  onset   the first Latin letter must be a possible romanization of the first
          Korean consonant, which catches 미추홀구 published under its
          pre-2018 name "Nam-gu".

Run standalone (`python check_sigungu_en.py`) or call `check_geojson()` from
the export step. Exit code is 1 when anything fails.
"""
import io, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, "05_dashboard", "data", "korea_sigungu.json")

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
# Revised Romanization initials. ㅇ is silent, so the syllable's vowel decides,
# and 와/워/외 give W.
ONSET = {"ㄱ": "GK", "ㄲ": "GK", "ㄴ": "N", "ㄷ": "DT", "ㄸ": "DT", "ㄹ": "RL",
         "ㅁ": "M", "ㅂ": "BP", "ㅃ": "BP", "ㅅ": "S", "ㅆ": "S",
         "ㅇ": "AEIOUYW", "ㅈ": "J", "ㅉ": "J", "ㅊ": "C", "ㅋ": "K",
         "ㅌ": "T", "ㅍ": "P", "ㅎ": "H"}
SUFFIX = {"시": "-si", "군": "-gun", "구": "-gu"}


def _onset(ko):
    c = ord(ko[0]) - 0xAC00
    return CHO[c // 588] if 0 <= c < 11172 else None


def problems(name, en):
    """Every rule this pair breaks. Empty list means it looks right."""
    if not name:
        return []
    if not en:
        return ["no English name"]
    out = []
    tail = name[-1]
    if tail in SUFFIX and not en.lower().endswith(SUFFIX[tail]):
        out.append("ends in %s so the English should end in %s" % (tail, SUFFIX[tail]))
    ch = _onset(name)
    if ch and en[0].upper() not in ONSET.get(ch, ""):
        out.append("starts with %s so %s is not a possible first letter" % (ch, en[0]))
    return out


def check_geojson(path=GEO, verbose=True):
    """Returns the list of (name, sido, name_eng, message). Empty when clean."""
    geo = json.load(io.open(path, encoding="utf-8"))
    bad = []
    for f in geo["features"]:
        p = f["properties"]
        nm, en = p.get("name", ""), p.get("name_eng", "")
        # a general gu is written 수원시장안구 in this file and
        # "Suwon-si Jangan-gu" in English, so check the two parts pairwise.
        # 양구군 is one name, not 양구 + 군, so split only on 시 + 구
        m = re.match(r"^(.+시)(.+구)$", nm)
        pairs = list(zip(m.groups(), en.split())) if (m and len(en.split()) == 2)             else [(nm, en)]
        for a, b in pairs:
            for msg in problems(a, b):
                bad.append((nm, p.get("sido", ""), en, msg))
    if verbose:
        for nm, sd, en, msg in bad:
            print("  %-16s %-14s %-24s %s" % (nm, sd, en, msg))
        print("%d districts checked, %d problems" % (len(geo["features"]), len(bad)))
    return bad


if __name__ == "__main__":
    sys.exit(1 if check_geojson() else 0)
