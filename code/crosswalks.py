# -*- coding: utf-8 -*-
"""Export the harmonization rules as data (reviewer comments C1, C7).

Until now the rules that merge nationality names, administrative area names and
visa status codes lived only in prose and in code. A user then had no way to check
or dispute "why were these two merged". The rules are exported as tables as they
are, so that someone who has only the deposit can check every merge.

What is exported

* `crosswalk_country.csv`: nationality labels as printed in the yearbook -> this
  dataset's standard name, with its English name and continent. Both the places
  where spelling variants were merged and where they were not are visible.
* `crosswalk_region.csv`: old spellings of province and district names, renames,
  upgrades and annexations, and the places where general districts were folded
  into one city.
* `crosswalk_visa.csv`: sub-codes of the pre-2010 editions -> parent code, and each
  code's Korean and English name.
* `language_weights.csv`: nationality -> the shares of that country's first
  languages. `language_demand` is computed from this table. The Ethnologue source
  cannot be redistributed, but the shares derived from it are our own output, and
  without this table `language_demand` cannot be rechecked.

Called by `09_finish_release.py` when it finishes the release.
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
# the 2017 edition's nationality tables print these five so. 2026-09-27 (second-round
# cross-check): the crosswalk listed none, so the merge could not be read off the table;
# check_published_totals.crosswalk_labels_gate now holds every label the raw tables
# print to this file.
PAREN_LABELS = ("(마카오)", "(영국속국민)", "(영국외지민)", "(타이완)", "(홍콩)")

# Labels an edition prints with a space between words that the standard name does
# not have, which every parser reads with the spaces removed ("한국계 중국인" in the
# 2006 and 2014-2018 tables, "국제연합 전문기구" in the 2023 and 2024 district tables,
# ...). 2026-09-27 (third-round cross-check): the crosswalk had only the unspaced
# names, and check_published_totals compared labels with every space removed, so the
# gap passed; it now holds a label printed with a word space to a row of its own. A
# name padded one character at a time (2006: "가 이 아 나") or to a fixed width (2009:
# "중      국") is layout, not spelling, and has no row.
SPACED_LABELS = ("(영국 속국민)", "(영국 외지민)", "국제연합 전문기구", "남아프리카 공화국",
                 "미령 버진아일랜드", "불령 가이아나", "상투메 프린시페", "세르비아 몬테네그로",
                 "세인트빈센트 그레나딘", "세인트크리스토퍼 네비스", "앤티가 바부다",
                 "앤티카 바부다", "영국 속령지 시민", "영국 외지민", "영국 외지시민",
                 "중앙 아프리카 공화국", "티모르 민주공화국", "한국계 러시아인", "한국계 중국인")

# The labels COUNTRY_CANONICAL folds that are not a spelling of their target but a
# line of their own in the yearbook: a territory, a nationality class, a legacy code
# the register still keeps, or refugees resident in Hong Kong. Editions print them
# beside the country they are folded into (2024: "영국" 8,697 with "영국외지민" 183,
# "영국외지시민" 4 and "영국해외영토시민" 3; "콩고민주공화국" 378 with "자이르" 7;
# "홍콩" 12,786 with "홍콩거주난민" 14). The crosswalk names that rule so a reader can tell the two
# kinds of merge apart (2026-09-27).
FOLDED_LINES = frozenset({"자이르", "미국인근섬", "미령버진아일랜드", "미령사모아",
                          "영령인도양섬", "불령가이아나", "홍콩거주난민", "영국속국민",
                          "영국보호민", "영국외지민", "영국외지시민", "영국속령지시민",
                          "영국해외영토시민"})
FOLDED_RULE = "separate yearbook line folded into this country"

# Labels an edition prints for a status in place of the one the release carries, under
# the same code: (code, label as printed, the editions that print it in any of the
# national registered, national staying or district status tables). A status renamed
# (D-3 "산업연수" became "기술연수" in the 2013 edition, C-3 "단기종합" "단기방문" in
# 2011, D-7 "상사주재" "주재" in 2010, E-7 "특정직업" "특정활동"), a short or long form
# of the name (E-2 "회화" and "회화강사", E-9 "비취업", G-1 "기타"), E-10 printed as
# "내항선원" in 2006, and the label of the retired trainee-employment E-8 that the 2022
# and 2024 registered tables print over the seasonal-worker column. The 2009 edition
# prints D-3 only as its sub-codes, so it has no D-3 label. Fourth-round cross-check
# (2026-09-27): only the E-8 split had a row, so a reader of crosswalk_visa could not
# tell that the "산업연수" of the 2006-2012 tables is the D3 the release calls
# "기술연수". check_published_totals.
# status_variant_gate holds this list to the raw tables in both directions.
STATUS_LABEL_VARIANTS = [
    ("C3", "단기종합", "2006-2010"),
    ("D3", "산업연수", "2006-2008, 2010-2012"),
    ("D7", "상사주재", "2006-2009"),
    ("E10", "내항선원", "2006"),
    ("E2", "회화", "2010-2022, 2024"),
    ("E2", "회화강사", "2019-2022, 2024"),
    ("E7", "특정직업", "2006-2009"),
    ("E8", "연수취업", "2022, 2024"),
    ("E9", "비취업", "2006-2009"),
    ("G1", "기타", "2006-2008, 2010-2024"),
]
VARIANT_RULE = "same code, label printed as "
VARIANT_NOTE = {
    # the English the Korea Immigration Service gives D-3 (Visa Navigator, 2023):
    # the release keeps it with the current Korean name
    "D3": "; Industrial Trainee is the Korea Immigration Service's English name for D-3",
    "E8": " in the registered table, over the seasonal workers (the staying and district "
          "tables of the same editions print 계절근로 or E8)",
    "G1": " beside the code G-1 (the code-less 기타 column is ETC)",
}


# The crew columns of the 2007-2009 editions: (source code, the label the editions
# print over it, the editions that print it, the subdivision of E-10 it is). The
# national registered and staying tables print them as E0A to E0C and the 2008 and
# 2009 district tables as E-0-A to E-0-C; none of those editions prints an E-0 or an
# E-10 column. The 2006 edition prints the status as E-10 ("내항선원") and the 2010
# edition on as E-10 "선원취업", whose subdivisions are E-10-1 "내항선원", E-10-2
# "어선원" and E-10-3 "순항여객선원". Since the owner's decision of 2026-09-27 the three columns are
# E10 (01_parse_yearbooks.CREW_SUBCODES); they had been a code of their own, E0.
# check_published_totals.crew_gate holds these rows to the raw tables, edition by
# edition.
CREW_ROWS = [
    ("E0A", "내항선원", "2007-2009", "E-10-1", "E-0-A in the 2008-2009 district tables"),
    ("E0B", "어선원", "2007-2009", "E-10-2", "E-0-B in the 2008-2009 district tables"),
    ("E0C", "순항선원", "2009", "E-10-3", "E-0-C in the 2009 district table"),
]
CREW_RULE = "crew column printed as %s (%s; %s), subdivision %s of E-10 선원취업: carried as E10"


def variant_source_code(code, editions):
    """The source_code of a label-variant row: the code and the editions that print it."""
    many = "," in editions or "-" in editions
    return "%s (%s edition%s)" % (code, editions, "s" if many else "")


def variant_years(editions):
    """'2006-2008, 2010-2012' -> {2006, 2007, 2008, 2010, 2011, 2012}."""
    out = set()
    for part in editions.split(","):
        a, _, b = part.strip().partition("-")
        out |= set(range(int(a), int(b or a) + 1))
    return out


# English continent names. Same spelling as the deposit's other tables.
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
    print("  %s: %d rows" % (os.path.basename(path), len(rows)))


def country_crosswalk(data=None):
    data = data or RELEASE_DATA
    # Some countries are missing from the segregation table (small countries are
    # left out of it), so English country names are also read from the national
    # nationality table. If neither has one, leave it blank and report it.
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
    # Names that never appear in the data, so no English name exists anywhere. Kept
    # so they are caught if the yearbook uses them
    EXTRA_EN = {"한국계미국인": "Korean-American",
                "북한": "North Korea", "케이맨제도": "Cayman Islands",
                "동독": "East Germany", "유고슬라비아": "Yugoslavia",
                "자이르": "Zaire", "스발바르": "Svalbard",
                "크리스마스": "Christmas Island"}

    def row(src, canon, rule):
        # Countries not in the region table are grouped by the pipeline as "기타"
        # (other; the default of COUNTRY_REGION.get). A blank in the crosswalk would
        # leave that rule visible only in the code, so write the value actually applied.
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
    for src in SPACED_LABELS:
        bare = "".join(src.split()).strip("()")
        rows.append(row(src, COUNTRY_CANONICAL.get(bare, bare),
                        FOLDED_RULE + " (printed with a space)" if bare in FOLDED_LINES
                        else "source label variant (printed with a space)"))
    for canon in sorted(set(COUNTRY_REGION) | set(en) | set(COUNTRY_CANONICAL.values())):
        # Every standard name has a row of its own, as the label the editions print.
        # Until 2026-09-26 (first-round fix) a name was skipped when some retired
        # spelling pointed to it, so "미국", "영국", "타이", "타이완", "러시아(연방)" and 13
        # more had no row under the spelling most editions print. A name that is itself
        # a retired spelling ("자이르") is not listed twice: the source_label uniqueness gate
        # caught that on 2026-08-26.
        if canon not in COUNTRY_CANONICAL:
            rows.append(row(canon, canon, "unchanged"))
    blank = [r[1] for r in rows if not r[2]]
    if blank:
        print("     %d names with no English country name: %s" % (len(blank), ", ".join(blank[:6])))
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
    # district-table lines the release carries on another district (first-round fix,
    # 2026-09-26: the "화성시 동부출장소" and "마산시" lines were applied but not listed)
    for (sd, sg), (tsd, tg), rule in SGG_LINE_FOLD:
        rows.append(["sigungu", sd, sg, tsd, tg, rule])
    for (sd, emd), new in sorted(EMD_RENAME.items()):
        rows.append(["eupmyeondong", sd, emd, sd, new, "sub-district renamed"])
    # The target columns (sido, name) give the names the release actually carries.
    # SIDO_ALIAS and SGG_NAME_ALIAS map to the new names used for the boundary files
    # and register lookups ("강원특별자치도", "전북특별자치도", "세종특별자치시"), but the
    # data use "강원도", "전라북도" and "세종시". The source columns (source_sido,
    # source_name) keep the raw spelling.
    for r in rows:
        r[3] = RELEASE_SIDO_NAME.get(r[3], r[3])
        if r[0] in ("sigungu",):
            r[4] = RELEASE_SGG_NAME.get((r[3], r[4]), r[4])
    # Every province under the name the release carries has a row of its own, as the
    # label most editions print (2008-2009 and 2014 on print the full names). Until
    # 2026-09-27 (second-round cross-check) only "강원도", "전라북도" and "제주특별자치도"
    # had one, the
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
    """Sub-codes folded into a parent code. The folds actually made are read from the raw data."""
    data = data or RELEASE_DATA
    labels = {}
    p = os.path.join(data, "visa_national.csv")
    if os.path.exists(p):
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig")):
            labels.setdefault(r["visa_code"], (r.get("visa_label") or "",
                                               r.get("visa_label_en") or ""))
    # The sub-codes 01 actually folded. Writing only the rule would not show which
    # code went where
    folded = {}
    q = os.path.join(CLEAN, "visa_code_collapse.csv")
    if os.path.exists(q):
        for r in csv.DictReader(io.open(q, encoding="utf-8-sig")):
            folded[r["source_code"]] = r["visa_code"]
    else:
        print("  visa_code_collapse.csv not found. Run 01 once so the sub-codes are included")
    crew = {r[0] for r in CREW_ROWS}
    off = {c: folded.get(c) for c in crew if folded.get(c) not in (None, "E10")}
    if off or "E0" in labels:
        raise SystemExit("crosswalk_visa: the crew columns must be carried as E10 "
                         "(01_parse_yearbooks.CREW_SUBCODES): %s%s"
                         % (off, "; visa_national still has E0" if "E0" in labels else ""))
    rows = []
    for code in sorted(set(labels) | set(folded)):
        if code in crew:
            continue                          # CREW_ROWS, below
        parent = folded.get(code, code)
        ko, en = labels.get(parent, labels.get(code, ("", "")))
        if code == "E8T":
            # The yearbook prints this status as E-8 (2006-2009 editions). From the 2021
            # edition the same code is reused for seasonal work, so this dataset
            # carries the old status separately as E8T.
            rows.append(["E8 (2006-2009 editions)", "E8T", ko, en,
                         "same source code, different status: 연수취업 to 2009"])
            continue
        rows.append([code, parent, ko, en,
                     "sub-code collapsed to parent" if parent != code else "unchanged"])
    # the crew columns of 2007-2009, linked to E-10
    ko, en = labels.get("E10", ("", ""))
    for code, printed, editions, sub, district in CREW_ROWS:
        rows.append([variant_source_code(code, editions), "E10", ko, en,
                     CREW_RULE % (printed, code, district, sub)])
    # the labels an edition prints for a code in place of the released one
    for code, printed, editions in STATUS_LABEL_VARIANTS:
        if code not in labels:
            raise SystemExit("crosswalk_visa: %s has a label variant but no row in "
                             "visa_national" % code)
        ko, en = labels[code]
        rows.append([variant_source_code(code, editions), code, ko, en,
                     VARIANT_RULE + printed + VARIANT_NOTE.get(code, "")])
    # The status tables print their unclassified statuses in a column with no code,
    # headed "기타", "기타(other)", "기타(others)" or "기타(Others)" by edition (2017 on); 01
    # reads every one as ETC. check_published_totals.crosswalk_labels_gate lists the
    # headings the raw tables print.
    # Until 2026-09-27 (second-round cross-check) the only ETC row read 'ETC, unchanged', as if a
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
    """Nationality -> first-language shares, so that `language_demand` can be rechecked.

    `countries` is the standard-name vocabulary of crosswalk_country. The shares
    table also holds a few other spellings of the same countries ("마셜제도" beside the
    data's "마샬군도", "솔로몬제도" beside "솔로몬군도", ...) that no data file uses; they
    are left out, so every country here has its crosswalk row (first-round fix,
    2026-09-26). The other direction holds too: every standard name gets a row, with
    the note 'no first-language shares available' where the shares table has no entry.
    Until 2026-09-27 (fifth-round cross-check) the loop ran over the shares table
    alone, so "북한", "케이맨제도" and "한국계미국인", standard names with no people in
    the nationality files,
    had no row although the dictionary promises one for every standard name."""
    data = data or RELEASE_DATA
    src = os.path.join(CLEAN, "country_language_shares.json")
    if not os.path.exists(src):
        print("  country_language_shares.json not found. Skipping language_weights")
        return []
    shares = json.load(io.open(src, encoding="utf-8"))
    # English language names. language_demand holds only the top languages, so the
    # dictionary is read as well
    en = {v: k for k, v in LANG_EN_KO.items()}
    p = os.path.join(data, "language_demand.csv")
    if os.path.exists(p):
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig")):
            if r.get("language") and r.get("language_en"):
                en[r["language"]] = r["language_en"]
    rows = []
    skipped = sorted(c for c in shares if countries is not None and c not in countries)
    if skipped:
        print("     %d spellings not in the crosswalk are left out: %s" % (len(skipped), ", ".join(skipped)))
    for country in (sorted(countries) if countries is not None else sorted(shares)):
        items = shares.get(country) or []
        if not items:
            rows.append([country, "", "", "", "no first-language shares available"])
            continue
        for it in sorted(items, key=lambda x: -x.get("share", 0)):
            lang = it.get("language", "")
            # Names not in the dictionary are already in English (like Uyghur). Use as is
            rows.append([country, lang, en.get(lang, lang),
                         "%.4f" % float(it.get("share", 0)), ""])
    _write(os.path.join(data, "language_weights.csv"),
           ["country", "language", "language_en", "share", "note"], rows)
    return rows


def build_all(data=None):
    print("crosswalks: exporting the harmonization rules as tables")
    cc = country_crosswalk(data)
    region_crosswalk(data)
    visa_crosswalk(data)
    language_weights(data, countries={r[1] for r in cc})


if __name__ == "__main__":
    build_all()
