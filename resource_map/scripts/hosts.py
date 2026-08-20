# -*- coding: utf-8 -*-
"""What a host IS, independent of which organization it was attached to.

A URL can be wrong in several different ways and they need different remedies,
so they are named separately rather than collapsed into one "bad" flag:

  aggregator  a business/phone/map/review directory. Never anybody's homepage.
  social      a social profile. Belongs in the fb/ig slot, not the website slot.
  news        an article about the organization. Not its website.
  portal      a government or umbrella portal that lists many organizations.
  platform    a site builder or blog host. The content there IS the org's own,
              so this is explicitly NOT a demotion, only a note.
  filejunk    a file-download or board-view URL captured instead of a page.
"""
from __future__ import annotations
import re
import urllib.parse as up

AGGREGATOR = re.compile(
    r"(place\.map\.kakao|map\.kakao|map\.naver|place\.naver|maps\.google|"
    r"google\.[a-z.]+/maps|kko\.to|naver\.me|place\.udanax\.org|"
    r"marketbz|moneypin|bizno\.net|nett\.kr|114\.co\.kr|cretop|nicebizinfo|"
    r"jangterm|opencorp|bigvalue\.ai|allthatcompany|theteams\.kr|"
    r"jobplanet|jobkorea|saramin|albamon|wanted\.co\.kr|incruit|catch\.co\.kr|"
    # Postings boards. A recruitment or volunteering listing reprints the
    # organization's phone number and street address inside the posting, so it
    # satisfies a phone+address+name identity test while being somebody else's
    # site. 아시아평화를향한이주 was published pointing at a linkareer volunteer
    # advert because of exactly this.
    r"linkareer|campuspick|allforyoung|thinkyou\.co\.kr|"
    r"volunteer\.seoul\.kr|1365\.go\.kr|vms\.or\.kr|dovol\.youth\.go\.kr|"
    r"daangn\.com|karrotmarket|yelp\.|tripadvisor|"
    r"welfare24\.net|smalllibrary\.org|koreancoop\.com|grandculture\.net|"
    r"together\.kakao|happybean|sedoparking|hugedomains|afternic|"
    r"reportworld|happycampus|dbpia|riss\.kr|earticle|kiss\.kstudy|kstudy\.com|"
    r"wikitree|netongs|marketbiz|namu\.wiki|wikipedia\.org|wikiwand|"
    # Reverse lookup by phone number or by street address. These print the
    # organization's own phone and address, which is precisely why they slipped
    # past an identity test built on those two fields: 322 picks landed here
    # before the tier rule was corrected to require a name as well.
    r"moyaweb|whocall|nomorecall|hoxy\.kr|dooricall|"
    r"dorojuso|juso\.app|jusoen|zipcode|address\.kr|"
    # property listings and building pages
    r"ziptoss|zippoom|zaritalk|dabangapp|hogangnono|kbland|rtech\.or\.kr|"
    r"budongsanplanet|richgo|asil\.kr|"
    # sector directories that carry a business at an address
    r"caredoc|hidoc|goodoc|mediexpo|kmle|"
    r"diningcode|mangoplate|siksin|foodsafetykorea|"
    r"alltheway\.kr|findall|localsearch|"
    # Found by the shared-host test on this data: each carries dozens of
    # different organizations at per-organization paths and is nobody's site.
    r"welfarehello|yugacrew|zighang|medieus|youbianku|"
    r"easylaw\.go\.kr|mcst\.go\.kr/slibrary|maria\.catholic\.or\.kr|"
    r"v\.daum\.net|news\.naver|n\.news|"
    r"dawoolim|mcfamily\.or\.kr|livingindaejeon|cbngo\.org|gmhc\.kr)",
    re.I,
)

SOCIAL = re.compile(
    r"(facebook\.com|instagram\.com|threads\.(net|com)|youtube\.com|youtu\.be|"
    r"twitter\.com|x\.com|linkedin\.|tiktok\.|pf\.kakao|open\.kakao|"
    r"band\.us|cafe\.naver|cafe\.daum|blog\.naver|m\.blog\.naver|post\.naver|"
    r"blog\.daum|tistory\.com|brunch\.co\.kr|velog\.io|blogspot\.)",
    re.I,
)

NEWS = re.compile(
    r"(yna\.co\.kr|newsis\.com|newspim|news1\.kr|nocutnews|ohmynews|edaily|"
    r"mk\.co\.kr|hankyung|chosun\.com|donga\.com|hani\.co\.kr|khan\.co\.kr|"
    r"joongang|joins\.com|seoul\.co\.kr|kmib\.co\.kr|kookje|ajunews|asiae\.co\.kr|"
    r"sedaily|labortoday|hankookilbo|segye\.com|munhwa\.com|imaeil|kwangju\.co\.kr|"
    r"jjan\.kr|jnilbo|yeongnam|busan\.com|kado\.net|inews24|pressian|"
    r"mediatoday|newscj|christiantoday|kidok|cpbc\.co\.kr|catholictimes|"
    r"\bnews\.|/news/|newsroom)",
    re.I,
)

# National directories and government portals that LIST organizations. A row
# pointing here has no site of its own recorded; the portal is not it.
PORTAL = re.compile(
    r"(liveinkorea\.kr|danuri\.go\.kr|hikorea\.go\.kr|work\.go\.kr|work24\.go\.kr|"
    r"socinet\.go\.kr|npas\.mois\.go\.kr|mogef\.go\.kr/inc/fs_fsc|"
    r"directory\.cbck\.or\.kr|m\.catholic\.or\.kr|jejubokji\.net|"
    r"bokjiro\.go\.kr|w4c\.go\.kr|1365\.go\.kr|nanumkorea)",
    re.I,
)

# Site builders and blog-style hosts. The content IS the organization's own, so
# these are NOT demoted; they are only recorded so a host-collision test does
# not mistake two tenants of one builder for one shared page.
PLATFORM = re.compile(
    r"(wixsite\.com|weebly\.com|sites\.google\.com|modoo\.at|cafe24\.com|"
    r"imweb\.me|creatorlink\.net|linktr\.ee|mailchi\.mp|notion\.site|"
    r"github\.io|netlify\.app|vercel\.app|blogspot\.com|tistory\.com|"
    r"myshopify|square\.site|clubexpress)",
    re.I,
)

FILEJUNK = re.compile(
    r"(fileDownload|ND_file|q_fileSn|download\.do|FileDown|/bbs/|/board|"
    r"articleview|/article|view\.php|mode=view|/notice|\.pdf$|\.hwp$|\.xlsx?$)",
    re.I,
)

# Titles that name the platform rather than an organization. Read off the page
# itself, so it catches aggregators the host list has never seen.
PLATFORM_TITLE = re.compile(
    r"(카카오맵|네이버\s*지도|카카오맵에서|사업자번호\s*조회|기업정보|"
    r"채용정보|구인구직|기업\s*리뷰|중고거래|당근마켓|"
    r"위키백과|나무위키|블로그|밴드|카페|"
    r"google maps|business directory|company profile|yellow ?pages)",
    re.I,
)


# Web systems where a facility type's official homepage lives, one subdomain
# per facility. 한국건강가정진흥원 runs familynet for the 가족센터 network and
# assigns sdmfc.familynet.or.kr to 서대문구 가족센터 and nobody else, so the
# subdomain IS the identity. That is stronger evidence than anything on a page,
# and it matters because familynet refuses non-Korean IPs: without this rule the
# blocked-but-correct site loses to a readable-but-wrong one, which is how 149
# of 257 family centres ended up pointing at a district office, a university
# CMS, or the contractor that operates them.
OFFICIAL_PLATFORM = re.compile(r"\.familynet\.or\.kr$", re.I)

# The same construction one level down. 법무부 출입국·외국인정책본부 does not give
# each 출입국·외국인사무소 a domain; it publishes each one as a numbered page on
# its own site, so 안산출입국·외국인사무소 is immigration.go.kr/immigration/3352.
# Read literally the site belongs to the ministry, and an adversarial reader is
# right to say so: all 44 offices came back parent_or_host and every 출입국관서
# on the map lost its link. For a person looking for that office, the numbered
# page IS the office's page, and no other page exists. So a per-office subpage
# on one of these domains counts the same as a familynet subdomain, on the same
# condition -- the page has to carry the organization's own name.
OFFICIAL_PAGE_HOST = re.compile(
    r"^(www\.)?(immigration|moj|hikorea)\.go\.kr$", re.I)
_OFFICE_PATH = re.compile(r"/\d{3,}/(subview|view)\.do|/\d{3,}/?$", re.I)


def is_official_subdomain(url):
    h = host_of(url)
    if h and OFFICIAL_PLATFORM.search(h):
        return True
    if h and OFFICIAL_PAGE_HOST.match(h):
        try:
            path = up.urlparse(str(url or "")).path
        except Exception:
            return False
        # the domain root is the ministry and nobody else; only a per-office
        # subpage qualifies
        return bool(_OFFICE_PATH.search(path))
    return False


def host_of(url):
    try:
        h = up.urlparse(str(url or "")).netloc.lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def registrable(url):
    """Rough eTLD+1 for Korean and generic domains, enough to tell a subdomain
    tenant (daegudonggu.familynet.or.kr) from the parent (familynet.or.kr)."""
    h = host_of(url)
    if not h:
        return ""
    parts = h.split(".")
    if len(parts) >= 3 and parts[-1] == "kr" and parts[-2] in (
            "or", "go", "co", "ne", "re", "pe", "ac", "hs", "ms", "es", "sc"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else h


def norm_url(url):
    """Normalize for collision testing: scheme and www dropped, trailing slash
    dropped, but the PATH kept. Two organizations on one site builder must not
    collide just because they share a host (census wrong-org method note)."""
    u = str(url or "").strip()
    if not u:
        return ""
    try:
        p = up.urlparse(u if "//" in u else "http://" + u)
    except Exception:
        return u.lower()
    h = p.netloc.lower()
    if h.startswith("www."):
        h = h[4:]
    path = (p.path or "").rstrip("/")
    q = ("?" + p.query) if p.query else ""
    return f"{h}{path}{q}".lower()


def classify(url, title="", og=""):
    """Every label that applies. Order in the returned list is not meaningful."""
    u = str(url or "")
    lab = []
    if AGGREGATOR.search(u):
        lab.append("aggregator")
    if SOCIAL.search(u):
        lab.append("social")
    if NEWS.search(u):
        lab.append("news")
    if PORTAL.search(u):
        lab.append("portal")
    if PLATFORM.search(u):
        lab.append("platform")
    if FILEJUNK.search(u):
        lab.append("filejunk")
    if "aggregator" not in lab and PLATFORM_TITLE.search(" ".join([title or "", og or ""])):
        lab.append("aggregator")
    return lab


# Labels that mean the URL is not this organization's own website.
DEMOTE = {"aggregator", "social", "news", "portal", "filejunk"}
