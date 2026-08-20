# -*- coding: utf-8 -*-
"""Korean organization identity matching.

The lesson this module exists to enforce (US organization census,
docs/PIPELINE_FAILURE_MODES.md #10): a token overlap, a containment, a shared
building and a bracketed acronym are LEADS. They never settle identity on their
own. Identity is settled by something the organization publishes about itself
that no neighbour shares: its phone number, its street address, or its whole
name.

So every match here returns an EVIDENCE SET, not a boolean, and the caller
tiers on the evidence.
"""
from __future__ import annotations
import re
import unicodedata

# ---------------------------------------------------------------- normalize

_LEGAL = re.compile(
    r"(사단법인|재단법인|사회복지법인|학교법인|의료법인|종교법인|특수법인|"
    r"주식회사|유한회사|비영리민간단체|공익법인|법인)"
)
_LEGAL_PAREN = re.compile(r"[（(]\s*(사|재|복|학|의|종|주|유|비)\s*[)）]")
_BRACKET = re.compile(r"[（(\[【][^)）\]】]*[)）\]】]")
# Latin, Hangul, Han, kana and Cyrillic. Restricting this to Hangul and ASCII
# silently emptied the identity key for every organization named in another
# script, and a row whose key is empty is dropped without a word: 華人世界報 and
#韓中商報 vanished between the roster and the frame that way.
_NONWORD = re.compile(
    r"[^0-9A-Za-z가-힣぀-ヿ㐀-䶿一-鿿Ѐ-ӿ]+")


def nfkc(s):
    return unicodedata.normalize("NFKC", str(s or ""))


def strip_legal(name):
    s = nfkc(name)
    s = _LEGAL_PAREN.sub(" ", s)
    s = _LEGAL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def compact(s):
    """Lowercased, punctuation- and space-free. Korean org names are written
    with and without spaces interchangeably, so containment has to be tested on
    the compacted string."""
    return _NONWORD.sub("", nfkc(s)).lower()


# Words that describe what a facility IS. Shared by hundreds of organizations,
# so they can never be the thing that identifies one.
GENERIC = {
    # facility type
    "센터", "센타", "지원센터", "상담센터", "복지센터", "종합복지센터", "가족센터",
    "복지관", "종합사회복지관", "사회복지관", "회관", "쉼터", "보호시설", "상담소",
    "지원시설", "사업단", "지원단", "본부", "지부", "지회", "분소", "출장소", "사무소",
    "재단", "협회", "협의회", "연합회", "연대", "네트워크", "위원회", "공동체", "모임",
    "학교", "대학교", "대학", "산학협력단", "연구소", "연구원", "연구센터", "부설",
    "병원", "의원", "클리닉", "진료소", "교회", "성당", "사찰", "선교회",
    # population words
    "이주민", "이주여성", "이주노동자", "이주배경", "외국인", "외국인주민", "외국인근로자",
    "다문화", "다문화가족", "다문화가정", "결혼이민자", "난민", "이민자", "이민",
    "노동자", "근로자", "청소년", "아동", "여성", "가족", "주민", "시민",
    # generic modifiers
    "한국", "코리아", "대한", "글로벌", "국제", "월드", "아시아", "사회", "지역",
    "지원", "상담", "교육", "복지", "인권", "문화", "통합", "사회통합", "정착",
    "서비스", "프로그램", "사업", "운영", "관리", "행복", "희망", "사랑", "나눔",
    "함께", "우리", "미래", "새로운", "열린",
}

# 17 시도 and their short forms. A region word identifies WHERE, not WHO, so it
# is scored separately from the name.
SIDO_FULL = {
    "서울특별시": ["서울"], "부산광역시": ["부산"], "대구광역시": ["대구"],
    "인천광역시": ["인천"], "광주광역시": ["광주"], "대전광역시": ["대전"],
    "울산광역시": ["울산"], "세종특별자치시": ["세종"],
    "경기도": ["경기"], "강원특별자치도": ["강원"], "충청북도": ["충북", "충청북"],
    "충청남도": ["충남", "충청남"], "전북특별자치도": ["전북", "전라북"],
    "전라남도": ["전남", "전라남"], "경상북도": ["경북", "경상북"],
    "경상남도": ["경남", "경상남"], "제주특별자치도": ["제주"],
}
_SIDO_SUFFIX = re.compile(r"(특별자치도|특별자치시|특별시|광역시|자치도|자치시|도|시)$")


def sido_forms(sido):
    sido = str(sido or "").strip()
    if not sido:
        return []
    out = {sido}
    out.update(SIDO_FULL.get(sido, []))
    short = _SIDO_SUFFIX.sub("", sido)
    if len(short) >= 2:
        out.add(short)
    return [x for x in out if len(x) >= 2]


def sigungu_forms(sigungu):
    sg = str(sigungu or "").strip()
    if not sg:
        return []
    out = {sg}
    # 시흥시 -> 시흥, 남동구 -> 남동, 청양군 -> 청양
    base = re.sub(r"(특별자치시|시|군|구)$", "", sg)
    if len(base) >= 2:
        out.add(base)
    # 성남시 분당구 -> both parts
    for part in sg.split():
        p = re.sub(r"(시|군|구)$", "", part)
        if len(p) >= 2:
            out.add(p)
    return [x for x in out if len(x) >= 2]


def distinctive_tokens(name):
    """Tokens that could plausibly single this organization out.

    Splits on whitespace AND strips generic suffixes off a glued token, because
    Korean names are frequently written without spaces: 김포이주민센터 has to
    yield 김포, not nothing.
    """
    s = strip_legal(_BRACKET.sub(" ", name))
    toks = []
    for raw in re.split(r"[\s·,/&]+", s):
        t = _NONWORD.sub("", raw)
        if not t:
            continue
        if t in GENERIC:
            continue
        # peel generic words off the ends of a glued token
        changed = True
        while changed and len(t) > 2:
            changed = False
            for g in sorted(GENERIC, key=len, reverse=True):
                if len(g) < 2 or len(t) - len(g) < 2:
                    continue
                if t.endswith(g):
                    t = t[: -len(g)]
                    changed = True
                    break
                if t.startswith(g):
                    t = t[len(g):]
                    changed = True
                    break
        if t and t not in GENERIC and len(t) >= 2:
            toks.append(t)
    # de-dup, longest first: a longer token is a stronger discriminator
    seen, out = set(), []
    for t in sorted(toks, key=len, reverse=True):
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(t)
    return out


# ---------------------------------------------------------------- phone / addr

_PHONE_ANY = re.compile(r"(0\d{1,2})[-.\s)]{0,3}(\d{3,4})[-.\s]{0,3}(\d{4})")


def phone_digits(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d if 9 <= len(d) <= 11 else ""


def phones_in(text):
    out = set()
    for m in _PHONE_ANY.finditer(nfkc(text)):
        d = "".join(m.groups())
        if 9 <= len(d) <= 11:
            out.add(d)
    return out


_ADDR_CORE = re.compile(r"([가-힣A-Za-z0-9]+(?:로|길))\s*(\d+(?:-\d+)?)")


def address_keys(addr):
    """('증가로', '244') -> '증가로244'. The road name alone repeats across a
    city; the road name WITH the building number is close to unique."""
    out = []
    for m in _ADDR_CORE.finditer(nfkc(addr)):
        out.append(_NONWORD.sub("", m.group(1) + m.group(2)).lower())
    return out


# ---------------------------------------------------------------- fingerprint

def fingerprint(org, page_text, page_title=""):
    """Evidence that `page_text` is about `org`. Returns the evidence set and a
    tier. Never returns a bare boolean, on purpose."""
    hay_raw = nfkc(str(page_text or "") + " " + str(page_title or ""))
    hay = compact(hay_raw)
    ev = []

    name = str(org.get("name_ko") or "")
    ncomp = compact(strip_legal(_BRACKET.sub("", name)))
    toks = distinctive_tokens(name)
    tok_hits = [t for t in toks if len(compact(t)) >= 2 and compact(t) in hay]

    # 1. phone printed on the page
    ph = phone_digits(org.get("phone"))
    if ph and ph in phones_in(hay_raw):
        ev.append("phone")

    # 2. street address printed on the page
    akeys = address_keys(org.get("road_address") or org.get("addr") or "")
    if akeys and any(k in hay for k in akeys):
        ev.append("address")

    # 3. whole name present
    if len(ncomp) >= 5 and ncomp in hay:
        ev.append("name_full")

    # 4. region
    regs = sigungu_forms(org.get("sigungu")) or sido_forms(org.get("sido"))
    if any(compact(r) in hay for r in regs):
        ev.append("region")

    if len(tok_hits) >= 2:
        ev.append("tokens2")
    elif len(tok_hits) == 1:
        ev.append("token1")

    if "phone" in ev or "address" in ev:
        tier = "A"
    elif "name_full" in ev and "region" in ev:
        tier = "A"
    elif "name_full" in ev or ("tokens2" in ev and "region" in ev):
        tier = "B"
    elif "tokens2" in ev or "token1" in ev:
        tier = "C"
    else:
        tier = None
    return {"tier": tier, "evidence": ev, "token_hits": tok_hits,
            "n_tokens": len(toks)}


def _selftest():
    assert "김포" in distinctive_tokens("김포이주민센터")
    # a purely generic name yields no discriminating token
    assert distinctive_tokens("다문화가족지원센터") == [], distinctive_tokens("다문화가족지원센터")
    # glued generic suffix is peeled
    assert "안산" in distinctive_tokens("안산외국인주민지원본부"), distinctive_tokens("안산외국인주민지원본부")
    # phone settles it even when the name is generic
    a = {"name_ko": "김포이주민센터", "sigungu": "김포시", "phone": "031-982-7580"}
    r = fingerprint(a, "김포시 이주민을 위한 상담. 031-982-7580 으로 연락주세요.")
    assert r["tier"] == "A" and "phone" in r["evidence"], r
    # region alone is not identity
    r2 = fingerprint({"name_ko": "김포이주민센터", "sigungu": "김포시"},
                     "김포시청 홈페이지입니다")
    assert r2["tier"] in (None, "C"), r2
    assert address_keys("서울특별시 서대문구 증가로 244") == ["증가로244"]
    print("idmatch selftest OK")


if __name__ == "__main__":
    _selftest()
