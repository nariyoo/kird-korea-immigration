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
                  LANG_EN_KO, RELEASE_DATA, RELEASE_PARENT, RELEASE_SGG_NAME,
                  RELEASE_SIDO_NAME, RELEASE_SIDO_NAMES, SGG_LINE_FOLD, SGG_LINEAGE,
                  SGG_NAME_ALIAS, SGG_RENAME, SGG_SIDO_MOVE, SGG_SPLIT_LINEAGE, SIDO_ALIAS,
                  SIDO_LINEAGE)

# Labels an edition prints in parentheses, which every parser reads as the name
# inside them (01_parse_yearbooks.clean_country, build_diaspora_residence.canon_country):
# the 2017 edition's nationality tables print these five so. 2026-09-27 (2라운드
# 대조): the crosswalk listed none, so the merge could not be read off the table;
# check_published_totals.crosswalk_labels_gate now holds every label the raw tables
# print to this file.
PAREN_LABELS = ("(마카오)", "(영국속국민)", "(영국외지민)", "(타이완)", "(홍콩)")

# The labels COUNTRY_CANONICAL folds that are not a spelling of their target but a
# line of their own in the yearbook: a territory, a nationality class, a legacy code
# the register still keeps, or refugees resident in Hong Kong. Editions print them
# beside the country they are folded into (2024: 영국 8,697 with 영국외지민 183,
# 영국외지시민 4 and 영국해외영토시민 3; 콩고민주공화국 378 with 자이르 7; 홍콩 12,786
# with 홍콩거주난민 14). The crosswalk names that rule so a reader can tell the two
# kinds of merge apart (2026-09-27).
FOLDED_LINES = frozenset({"자이르", "미국인근섬", "미령버진아일랜드", "미령사모아",
                          "영령인도양섬", "불령가이아나", "홍콩거주난민", "영국속국민",
                          "영국보호민", "영국외지민", "영국외지시민", "영국속령지시민",
                          "영국해외영토시민"})
FOLDED_RULE = "separate yearbook line folded into this country"

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
    for src, canon in sorted(COUNTRY_CANONICAL.items()):
        rows.append(row(src, canon, FOLDED_RULE if src in FOLDED_LINES
                        else "source label variant"))
    for src in PAREN_LABELS:
        inner = src[1:-1]
        rows.append(row(src, COUNTRY_CANONICAL.get(inner, inner),
                        "source label variant (printed in parentheses)"))
    for canon in sorted(set(COUNTRY_REGION) | set(en) | set(COUNTRY_CANONICAL.values())):
        # Every standard name has a row of its own, as the label the editions print.
        # Until 2026-09-26 (1라운드 수정) a name was skipped when some retired spelling
        # pointed to it, so 미국, 영국, 타이, 타이완, 러시아(연방) and 13 more had no row
        # under the spelling most editions print. A name that is itself a retired
        # spelling (자이르, 대만) is not listed twice: the source_label uniqueness gate
        # caught that on 2026-08-26.
        if canon not in COUNTRY_CANONICAL:
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
    # district-table lines the release carries on another district (1라운드 수정,
    # 2026-09-26: the 화성시 동부출장소 and 마산시 lines were applied but not listed)
    for (sd, sg), (tsd, tg), rule in SGG_LINE_FOLD:
        rows.append(["sigungu", sd, sg, tsd, tg, rule])
    for (sd, emd), new in sorted(EMD_RENAME.items()):
        rows.append(["eupmyeondong", sd, emd, sd, new, "sub-district renamed"])
    # 대상 칸(sido, name)은 배포본이 실제로 싣는 이름으로 적는다. SIDO_ALIAS 와
    # SGG_NAME_ALIAS 는 경계 파일과 등록부 조회에 맞춘 새 이름(강원특별자치도,
    # 전북특별자치도, 세종특별자치시)으로 모으는데, 자료는 강원도·전라북도·세종시를
    # 쓴다. 원천 칸(source_sido, source_name)은 원자료 표기 그대로 둔다.
    for r in rows:
        r[3] = RELEASE_SIDO_NAME.get(r[3], r[3])
        if r[0] in ("sigungu",):
            r[4] = RELEASE_SGG_NAME.get((r[3], r[4]), r[4])
    # Every province under the name the release carries has a row of its own, as the
    # label most editions print (2008-2009 and 2014 on print the full names). Until
    # 2026-09-27 (2라운드 대조) only 강원도, 전라북도 and 제주특별자치도 had one, the
    # three SIDO_ALIAS happens to list, so the full name of the other fourteen was the
    # one label the table did not map.
    have = {r[1] for r in rows if r[0] == "sido"}
    for name in RELEASE_SIDO_NAMES:
        if name not in have:
            rows.append(["sido", name, "", name, "", "unchanged"])
    for r in rows:
        if r[0] == "sido" and r[1] == r[3]:
            r[5] = "unchanged"
    rows = sorted([r for r in rows if r[0] == "sido"], key=lambda r: r[1]) +         [r for r in rows if r[0] != "sido"]
    for item in list(SIDO_LINEAGE) + list(SGG_LINEAGE) + list(SGG_SPLIT_LINEAGE):
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
        if code == "E8T":
            # 연보는 이 자격을 E-8 로 싣는다(2006-2009년판). 같은 코드를 2021년판부터
            # 계절근로가 다시 쓰므로 이 자료는 옛 자격을 E8T 로 따로 싣는다.
            rows.append(["E8 (2006-2009 editions)", "E8T", ko, en,
                         "same source code, different status: 연수취업 to 2009"])
            continue
        rows.append([code, parent, ko, en,
                     "sub-code collapsed to parent" if parent != code else "unchanged"])
    # The status tables print their unclassified statuses in a column with no code,
    # headed 기타, 기타(other), 기타(others) or 기타(Others) by edition (2017 on); 01
    # reads every one as ETC. check_published_totals.crosswalk_labels_gate lists the
    # headings the raw tables print.
    # Until 2026-09-27 (2라운드 대조) the only ETC row read 'ETC, unchanged', as if a
    # table printed that code (10,171 people in 2018, 39,210 in 2020).
    if "ETC" in labels:
        ko, en = labels["ETC"]
        for src in ("기타", "기타(other)", "기타(others)", "기타(Others)"):
            rows.append([src, "ETC", ko, en,
                         "source label variant (the code-less column of unclassified "
                         "statuses)"])
    _write(os.path.join(data, "crosswalk_visa.csv"),
           ["source_code", "visa_code", "visa_label", "visa_label_en", "rule"], rows)
    return rows


def language_weights(data=None, countries=None):
    """국적 -> 제1언어 비중. `language_demand` 를 검산할 수 있게 한다.

    `countries` is the standard-name vocabulary of crosswalk_country. The shares
    table also holds a few other spellings of the same countries (마셜제도 beside the
    data's 마샬군도, 솔로몬제도 beside 솔로몬군도, ...) that no data file uses; they are
    left out, so every country here has its crosswalk row (1라운드 수정, 2026-09-26)."""
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
    skipped = sorted(c for c in shares if countries is not None and c not in countries)
    if skipped:
        print("     크로스워크에 없는 표기 %d개는 싣지 않는다: %s" % (len(skipped), ", ".join(skipped)))
    for country in sorted(shares):
        if countries is not None and country not in countries:
            continue
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
    cc = country_crosswalk(data)
    region_crosswalk(data)
    visa_crosswalk(data)
    language_weights(data, countries={r[1] for r in cc})


if __name__ == "__main__":
    build_all()
