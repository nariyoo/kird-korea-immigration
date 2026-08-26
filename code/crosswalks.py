# -*- coding: utf-8 -*-
"""조화 규칙을 자료로 내보낸다 (심사 지적 C1, C7).

지금까지 국적 이름·행정구역 이름·체류자격 코드를 하나로 모으는 규칙은 산문과
코드 안에만 있었다. 그러면 이용자가 "이 둘을 왜 합쳤나"를 짚어 보거나 반박할
길이 없다. 규칙을 그대로 표로 내보내, 기탁본만 받은 사람도 병합 하나하나를
확인할 수 있게 한다.

내보내는 것

* `crosswalk_country.csv` — 연감에 나오는 국적 표기 → 이 자료의 표준 이름,
  그 이름의 영문과 대륙. 표기 변형을 합친 자리와 합치지 않은 자리가 다 보인다.
* `crosswalk_region.csv` — 시도·시군구 이름의 옛 표기와 개명·승격·편입,
  그리고 일반구를 시 하나로 합친 자리.
* `crosswalk_visa.csv` — 2010년 이전 판의 하위 코드 → 부모 코드, 그리고 코드의
  한글·영문 이름.
* `language_weights.csv` — 국적 → 그 나라의 제1언어별 비중. `language_demand`
  가 이 표로 계산된다. Ethnologue 원본은 재배포할 수 없지만 여기서 파생된
  비중은 우리 산출물이라, 이 표가 없으면 `language_demand` 를 검산할 수 없다.

`09_finish_release.py` 가 릴리스를 마무리할 때 부른다.
"""
import csv
import io
import json
import os

from kird import (CLEAN, COUNTRY_CANONICAL, COUNTRY_REGION, EMD_RENAME, OTHER_REGION,
                  LANG_EN_KO, RELEASE_DATA, RELEASE_PARENT, SGG_LINEAGE,
                  SGG_NAME_ALIAS, SGG_RENAME, SGG_SIDO_MOVE, SIDO_ALIAS,
                  SIDO_LINEAGE)

# 대륙 이름의 영문. 기탁본의 다른 표와 같은 표기를 쓴다.
CONTINENT_EN = {
    "동아시아": "East Asia", "동남아시아": "Southeast Asia", "남아시아": "South Asia",
    "중앙아시아": "Central Asia", "서아시아": "West Asia", "유럽": "Europe",
    "북아메리카": "North America", "중남미": "Latin America", "아프리카": "Africa",
    "오세아니아": "Oceania", "기타": "Other",
}


def _write(path, header, rows):
    with io.open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print("  %s: %d행" % (os.path.basename(path), len(rows)))


def country_crosswalk(data=None):
    data = data or RELEASE_DATA
    # 영문 국명은 분리지수 표에 없는 나라가 있어(작은 나라는 그 표에서 빠진다)
    # 국적별 전국 표까지 함께 본다. 두 곳에 다 없으면 빈칸으로 두고 알린다.
    en = {}
    for name in ("segregation_by_nationality.csv", "nationality_national.csv",
                 "nationality_by_sigungu.csv"):
        p = os.path.join(data, name)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig")):
            c = r.get("country")
            if not c:
                continue
            cur = en.get(c, ("", "", ""))
            en[c] = (cur[0] or (r.get("country_en") or ""),
                     cur[1] or (r.get("continent") or COUNTRY_REGION.get(c, "")),
                     cur[2] or (r.get("continent_en") or ""))
    # 자료에 한 번도 나오지 않아 영문이 어디에도 없는 이름. 연감이 쓰면 잡히도록 남긴다
    EXTRA_EN = {"대만": "Taiwan", "한국계미국인": "Korean-American",
                "북한": "North Korea", "케이맨제도": "Cayman Islands",
                "동독": "East Germany", "유고슬라비아": "Yugoslavia",
                "자이르": "Zaire", "스발바르": "Svalbard",
                "크리스마스": "Christmas Island"}

    def row(src, canon, rule):
        # 지역 표에 없는 나라는 파이프라인이 「기타」로 묶는다(COUNTRY_REGION.get 의
        # 기본값). 크로스워크를 빈칸으로 두면 그 규칙을 코드에서만 알 수 있으므로,
        # 실제로 적용되는 값을 그대로 적는다.
        e = en.get(canon, ("", "", ""))
        if not e[0] and canon in EXTRA_EN:
            e = (EXTRA_EN[canon], e[1], e[2])
        cont = e[1] or COUNTRY_REGION.get(canon, OTHER_REGION)
        return [src, canon, e[0], cont, e[2] or CONTINENT_EN.get(cont, ""), rule]

    rows = []
    seen = set()
    for src, canon in sorted(COUNTRY_CANONICAL.items()):
        rows.append(row(src, canon, "source label variant"))
        seen.add(canon)
    for canon in sorted(set(COUNTRY_REGION) | set(en)):
        # 원천 라벨로 이미 실린 이름은 「unchanged」로 다시 싣지 않는다. 자이르가
        # COUNTRY_REGION 의 보호용 항목에 남아 있어 두 줄이 되었고, source_label
        # 유일성 관문이 그것을 잡았다(2026-08-26).
        if canon not in seen and canon not in COUNTRY_CANONICAL:
            rows.append(row(canon, canon, "unchanged"))
    blank = [r[1] for r in rows if not r[2]]
    if blank:
        print("     영문 국명이 없는 %d곳: %s" % (len(blank), ", ".join(blank[:6])))
    _write(os.path.join(data, "crosswalk_country.csv"),
           ["source_label", "country", "country_en", "continent", "continent_en", "rule"],
           rows)
    return rows


def region_crosswalk(data=None):
    data = data or RELEASE_DATA
    rows = []
    for src, canon in sorted(SIDO_ALIAS.items()):
        rows.append(["sido", src, "", canon, "", "province renamed or relabelled"])
    for (sd, sg), new in sorted(SGG_RENAME.items()):
        rows.append(["sigungu", sd, sg, sd, new, "district renamed"])
    for (sd, sg), new_sd in sorted(SGG_SIDO_MOVE.items()):
        rows.append(["sigungu", sd, sg, new_sd, sg, "district moved to another province"])
    for (sd, sg), new in sorted(SGG_NAME_ALIAS.items()):
        rows.append(["sigungu", sd, sg, sd, new, "source label variant"])
    for (sd, sg), parent in sorted(RELEASE_PARENT.items()):
        rows.append(["sigungu", sd, sg, sd, parent,
                     "general district folded into its city total in the release"])
    for (sd, emd), new in sorted(EMD_RENAME.items()):
        rows.append(["eupmyeondong", sd, emd, sd, new, "sub-district renamed"])
    for item in list(SIDO_LINEAGE) + list(SGG_LINEAGE):
        rows.append(["lineage", "", "", "", "", json.dumps(item, ensure_ascii=False)])
    _write(os.path.join(data, "crosswalk_region.csv"),
           ["level", "source_sido", "source_name", "sido", "name", "rule"], rows)
    return rows


def visa_crosswalk(data=None):
    """부모 코드로 접힌 하위 코드. 실제로 접힌 자리를 원자료에서 찾아 적는다."""
    data = data or RELEASE_DATA
    labels = {}
    p = os.path.join(data, "visa_national.csv")
    if os.path.exists(p):
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig")):
            labels.setdefault(r["visa_code"], (r.get("visa_label") or "",
                                               r.get("visa_label_en") or ""))
    # 01 이 실제로 접은 하위 코드. 규칙만 적으면 어떤 코드가 어디로 갔는지 모른다
    folded = {}
    q = os.path.join(CLEAN, "visa_code_collapse.csv")
    if os.path.exists(q):
        for r in csv.DictReader(io.open(q, encoding="utf-8-sig")):
            folded[r["source_code"]] = r["visa_code"]
    else:
        print("  visa_code_collapse.csv 가 없다. 01 을 한 번 돌려야 하위 코드가 실린다")
    rows = []
    for code in sorted(set(labels) | set(folded)):
        parent = folded.get(code, code)
        ko, en = labels.get(parent, labels.get(code, ("", "")))
        rows.append([code, parent, ko, en,
                     "sub-code collapsed to parent" if parent != code else "unchanged"])
    _write(os.path.join(data, "crosswalk_visa.csv"),
           ["source_code", "visa_code", "visa_label", "visa_label_en", "rule"], rows)
    return rows


def language_weights(data=None):
    """국적 -> 제1언어 비중. `language_demand` 를 검산할 수 있게 한다."""
    data = data or RELEASE_DATA
    src = os.path.join(CLEAN, "country_language_shares.json")
    if not os.path.exists(src):
        print("  country_language_shares.json 이 없다. language_weights 를 건너뛴다")
        return []
    shares = json.load(io.open(src, encoding="utf-8"))
    # 언어의 영문 이름. language_demand 에는 상위 언어만 나오므로 사전도 함께 본다
    en = {v: k for k, v in LANG_EN_KO.items()}
    p = os.path.join(data, "language_demand.csv")
    if os.path.exists(p):
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig")):
            if r.get("language") and r.get("language_en"):
                en[r["language"]] = r["language_en"]
    rows = []
    for country in sorted(shares):
        items = shares[country] or []
        if not items:
            rows.append([country, "", "", "", "no first-language shares available"])
            continue
        for it in sorted(items, key=lambda x: -x.get("share", 0)):
            lang = it.get("language", "")
            # 사전에 없는 이름은 이미 영문으로 실려 있다(Uyghur 처럼). 그대로 쓴다
            rows.append([country, lang, en.get(lang, lang),
                         "%.4f" % float(it.get("share", 0)), ""])
    _write(os.path.join(data, "language_weights.csv"),
           ["country", "language", "language_en", "share", "note"], rows)
    return rows


def build_all(data=None):
    print("crosswalks: 조화 규칙을 표로 내보낸다")
    country_crosswalk(data)
    region_crosswalk(data)
    visa_crosswalk(data)
    language_weights(data)


if __name__ == "__main__":
    build_all()
