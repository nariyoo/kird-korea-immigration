# -*- coding: utf-8 -*-
"""Find each organization's own website, with the evidence that says it is.

Difference from the v1 enrichment, which is what produced the wrong links:

  v1: one query, take the first organic result whose TITLE looked like a name
      match, normalize it to the host root, write it in. Nothing was ever
      fetched, so a Kakao Map place page, a business-number lookup site and a
      city hall all passed.

  v2: five queries of different KINDS per organization, every surviving
      candidate FETCHED, and the pick made on what the page itself prints:
      the organization's phone number, its street address, its whole name.
      A candidate that only shares a token with the name is a lead, never a
      pick (census failure #10).

Ranking is by key exactness first and only then by anything else, because an
ordering that puts "more results agree" above "the right key" eventually
prefers the biggest wrong site (census failure #16).

Run:
  python scripts/v2/find_websites.py --frame data/processed/v2/frame_v2.csv
  python scripts/v2/find_websites.py --limit 40          # smoke test
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import collections
import urllib.parse as up
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import idmatch  # noqa: E402
import hosts  # noqa: E402
import serper  # noqa: E402
from webcache import PageStore, crawl  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
os.makedirs(OUT, exist_ok=True)

MAX_CANDIDATES = 5          # fetched per organization
QUERY_NUM = 10              # organic results asked per query


# ---------------------------------------------------------------- queries

def build_queries(org):
    """Five slots, always in this order. A slot is skipped only when the input
    field is empty, never to save money: the method has to be the same across
    units or the results are not comparable (Nari's standing rule)."""
    name = str(org.get("name_ko") or "").strip()
    sg = str(org.get("sigungu") or "").strip()
    sd = re.sub(r"(특별자치도|특별자치시|특별시|광역시|자치도|자치시)$", "",
                str(org.get("sido") or "").strip())
    ph = str(org.get("phone") or "").strip()
    addr = str(org.get("road_address") or org.get("addr") or "").strip()
    qs = []
    if name:
        qs.append(("name_region", f'"{name}" {sg or sd}'.strip()))
        qs.append(("name_exact", f'"{name}"'))
        qs.append(("name_home", f'{name} 홈페이지'))
    if ph and idmatch.phone_digits(ph):
        qs.append(("phone", f'"{ph}"'))
    ak = idmatch.address_keys(addr)
    if ak:
        # the road name and building number as printed, plus the region, is the
        # single most discriminating string an organization publishes
        m = re.search(r"([가-힣A-Za-z0-9]+(?:로|길)\s*\d+(?:-\d+)?)", addr)
        if m:
            qs.append(("address", f'"{m.group(1)}" {sg or sd}'.strip()))
    return qs


# URLs a person opened and confirmed. This is the one input that outranks the
# search, because the identity test it would otherwise have to pass is a test on
# what the page says, and a page that cannot be read from here says nothing:
# mapcast.org answers with almost no text, so 아시아평화를향한이주 was published
# pointing at a linkareer volunteer advert that reprinted its phone and address.
# A person having opened the site is better evidence than an unreadable page,
# and the pick carries web_src=ledger so the provenance is never lost.
_LEDGER = None


def manual_websites():
    global _LEDGER
    if _LEDGER is not None:
        return _LEDGER
    _LEDGER = {}
    p = os.path.join(ROOT, "data", "raw", "v2", "fixup", "manual_website.csv")
    if os.path.exists(p):
        d = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
        for _, r in d.iterrows():
            u = str(r.get("website", "")).strip()
            k = str(r.get("name_key", "")).strip()
            if u and k:
                _LEDGER[k] = u
        print(f"person-verified websites in the ledger: {len(_LEDGER)}")
    return _LEDGER


def collect_candidates(org):
    """Every organic result across the query slots, de-duplicated on the
    normalized URL. Nothing is chosen here."""
    seen = {}
    # Whatever URL the row already carries enters as one candidate among the
    # rest and has to earn its place on the same evidence. That way an existing
    # value is neither trusted because it is there nor discarded because it is
    # old, and every row goes through the identical method.
    cur = str(org.get("website") or "").strip()
    if cur:
        nu = hosts.norm_url(cur)
        if nu:
            seen[nu] = {"url": cur, "norm": nu, "title": "", "snippet": "",
                        "slots": ["existing"], "best_pos": 0}
    import build_frame as _bf
    lg = manual_websites().get(_bf.namekey(org.get("name_ko", "")), "")
    if lg:
        nu = hosts.norm_url(lg) or lg
        seen[nu] = {"url": lg, "norm": nu, "title": "", "snippet": "",
                    "slots": ["ledger"], "best_pos": 0, "from_ledger": True}
    for slot, q in build_queries(org):
        for pos, o in enumerate(serper.organic(q, QUERY_NUM)):
            link = (o.get("link") or "").strip()
            if not link:
                continue
            nu = hosts.norm_url(link)
            if not nu:
                continue
            c = seen.get(nu)
            if c is None:
                c = {"url": link, "norm": nu, "title": o.get("title", ""),
                     "snippet": o.get("snippet", ""), "slots": [], "best_pos": 99}
                seen[nu] = c
            if slot not in c["slots"]:
                c["slots"].append(slot)
            c["best_pos"] = min(c["best_pos"], pos)
    return list(seen.values())


# ---------------------------------------------------------------- ranking

def _domain_carries_name(url, org):
    """A domain that spells a distinctive part of the name is strong evidence
    on its own: nobody else registers it."""
    h = hosts.host_of(url)
    hc = re.sub(r"[^a-z0-9가-힣]", "", h.lower())
    for t in idmatch.distinctive_tokens(org.get("name_ko") or ""):
        tc = idmatch.compact(t)
        if len(tc) >= 2 and tc in hc:
            return True
    # romanized initials, e.g. 김포이주민센터 -> gimpo / kimpo
    return False


RANK = {
    "A_key": 0,     # the page prints this organization's phone or street address
    "A_name": 1,    # whole name plus region on the page
    "B": 2,         # whole name, or two distinctive tokens plus region
    "B_snip": 3,    # the same, but read out of the search index, not the page
    "C": 4,         # a token only
}


def score_candidate(org, cand, page):
    """Evidence, rank and the reason. Returns None when the candidate is
    disqualified outright, with the reason recorded by the caller."""
    labels = hosts.classify(cand["url"], page.get("title", ""),
                            page.get("og_site_name", ""))
    bad = set(labels) & hosts.DEMOTE
    if bad:
        return {"rank": 99, "tier": None, "evidence": [], "labels": labels,
                "reject": "not_a_homepage:" + ",".join(sorted(bad))}
    state = page.get("state", "unfetched")
    if state in ("parked", "notfound"):
        return {"rank": 99, "tier": None, "evidence": [], "labels": labels,
                "reject": "dead:" + state}
    # Checked BEFORE anything that depends on reading the page. A subdomain of a
    # facility type's official web system is that facility's own site by
    # construction, and those systems are exactly the ones that refuse
    # non-Korean IPs, so a rule placed after the blocked-page branch never runs.
    if cand.get("from_ledger"):
        return {"rank": RANK["A_key"], "tier": "A",
                "evidence": ["manual_verified"], "labels": labels,
                "reject": None, "domain_name": True}
    if hosts.is_official_subdomain(cand["url"]):
        sfp = idmatch.fingerprint(org, cand.get("snippet", ""),
                                  cand.get("title", ""))
        pfp = idmatch.fingerprint(org, page.get("text", ""),
                                  page.get("title", ""))
        if sfp["tier"] or pfp["tier"]:
            return {"rank": RANK["A_key"], "tier": "A",
                    "evidence": (pfp["evidence"] or sfp["evidence"])
                                + ["official_platform"]
                                + ([state] if state != "ok" else []),
                    "labels": labels, "reject": None, "domain_name": True}

    fp = idmatch.fingerprint(org, page.get("text", ""),
                             (page.get("title", "") + " " +
                              page.get("og_site_name", "")))
    ev = fp["evidence"]
    if state in ("blocked", "error", "thin", "spa") and not fp["tier"]:
        # The page could not be read from here. That is not evidence the site is
        # wrong, and for the 216 가족센터 on *.familynet.or.kr it is a refusal
        # aimed at non-Korean IPs, nothing more.
        #
        # Google indexed those pages from inside Korea, so the result title and
        # snippet are that page's own text, read by someone who could reach it.
        # Use them, and say so: the pick is capped below anything confirmed on
        # the page itself, and `via_snippet` travels with the row.
        sfp = idmatch.fingerprint(
            org, cand.get("snippet", ""), cand.get("title", ""))
        if sfp["tier"] in ("A", "B"):
            return {"rank": RANK["B_snip"], "tier": "B",
                    "evidence": sfp["evidence"] + ["via_snippet", state],
                    "labels": labels, "reject": None,
                    "domain_name": _domain_carries_name(cand["url"], org)}
        return {"rank": 99, "tier": None, "evidence": ev, "labels": labels,
                "reject": "unread:" + state}
    named = ("name_full" in ev) or ("tokens2" in ev)
    if ("phone" in ev or "address" in ev) and named:
        # An identifier the organization publishes, ON a page that also names
        # it. Either half alone is not identity: a phone-lookup site, a road-
        # address page and a property listing all print the number and the
        # street, and a directory of care homes prints them for the OTHER
        # tenant of the same building. This is US-census failure #9 in a new
        # costume, and it cost 322 wrong picks before the AND went in.
        rank = RANK["A_key"]
    elif "name_full" in ev and "region" in ev:
        rank = RANK["A_name"]
    elif ("phone" in ev or "address" in ev) and not named:
        return {"rank": 99, "tier": None, "evidence": ev, "labels": labels,
                "reject": "identifier_without_name"}
    elif fp["tier"] == "B":
        rank = RANK["B"]
    elif fp["tier"] == "C":
        rank = RANK["C"]
    else:
        return {"rank": 99, "tier": None, "evidence": ev, "labels": labels,
                "reject": "name_absent"}
    return {"rank": rank, "tier": fp["tier"], "evidence": ev, "labels": labels,
            "reject": None, "domain_name": _domain_carries_name(cand["url"], org)}


def pick(org, scored):
    """Key exactness first. Everything else is a tie-break INSIDE one rank."""
    live = [s for s in scored if s["score"]["reject"] is None]
    if not live:
        return None
    live.sort(key=lambda s: (
        s["score"]["rank"],
        0 if s["score"]["domain_name"] else 1,
        0 if len(s["cand"]["slots"]) > 1 else 1,   # found by two kinds of query
        s["cand"]["best_pos"],
    ))
    return live[0]


# ---------------------------------------------------------------- host root

def host_root(url):
    p = up.urlparse(url)
    return f"{p.scheme or 'https'}://{p.netloc}/"


def resolve_root(org, chosen, store):
    """If the pick sits at a path, decide whether the site as a whole is this
    organization's or somebody else's. A programme page on a host institution
    keeps its path and is labelled; it is not promoted to the host root, which
    is how a local branch ends up pointing at a city hall."""
    u = chosen["cand"]["url"]
    p = up.urlparse(u)
    if not (p.path or "").strip("/"):
        return u, "root"
    root = host_root(u)
    rp = store.get(root)
    if rp is None:
        return u, "path_unchecked"
    fp = idmatch.fingerprint(org, rp.get("text", ""),
                             rp.get("title", "") + " " + rp.get("og_site_name", ""))
    if fp["tier"] in ("A", "B"):
        return root, "root_confirmed"
    return u, "hosted_page"


# ---------------------------------------------------------------- driver

def run(frame, out_prefix, limit=None, workers=8, only_missing=True):
    df = pd.read_csv(frame, dtype=str).fillna("")
    if only_missing and "website" in df.columns:
        need = df[df["website"].str.strip() == ""].copy()
        have = len(df) - len(need)
        print(f"frame {len(df)} | already have a website {have} | searching {len(need)}")
    else:
        need = df.copy()
        print(f"frame {len(df)} | searching all {len(need)}")
    if limit:
        need = need.head(int(limit))

    orgs = need.to_dict("records")

    # 1. candidates (Serper, cached on disk)
    print("collecting candidates ...", flush=True)
    cands = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(collect_candidates, o): i for i, o in enumerate(orgs)}
        done = 0
        for fu in as_completed(futs):
            i = futs[fu]
            try:
                cands[i] = fu.result()
            except Exception as e:
                cands[i] = []
                print(f"  cand err {i}: {type(e).__name__}", flush=True)
            done += 1
            if done % 50 == 0:
                print(f"  candidates {done}/{len(orgs)}", flush=True)

    # 2. shortlist and fetch. Shortlisting happens BEFORE fetching only on the
    #    signals a URL carries by itself (host class, position), never on a
    #    name guess, so nothing plausible is dropped unread.
    store = PageStore(os.path.join(OUT, "pages_candidates.jsonl"))
    want = []
    short = {}
    for i, o in enumerate(orgs):
        cs = []
        for c in cands.get(i, []):
            lab = hosts.classify(c["url"], c["title"], "")
            if set(lab) & hosts.DEMOTE:
                continue
            cs.append(c)
        cs.sort(key=lambda c: (0 if len(c["slots"]) > 1 else 1, c["best_pos"]))
        cs = cs[:MAX_CANDIDATES]
        short[i] = cs
        # Only the candidates themselves. Host roots used to be crawled here
        # too, which doubled the fetch set to serve a question (is the root this
        # organization's, or its host's) that only matters for the ONE candidate
        # that ends up picked. They are fetched after the pick instead.
        for c in cs:
            want.append(c["url"])
    print(f"pages to fetch: {len(set(want))}", flush=True)
    # Plain clients only on the first sweep. Most candidates are discarded, and
    # rendering every one of them costs hours for pages nobody will keep.
    crawl(want, store, workers=workers, use_browser=False, label="candidates")

    def score_org(i, o):
        out = []
        for c in short[i]:
            page = store.get(c["url"]) or {}
            out.append({"cand": c, "score": score_candidate(o, c, page),
                        "state": page.get("state", "unfetched"),
                        "page_title": page.get("title", "")[:120]})
        return out

    # 3. browser recovery, but only where a plain client failed to settle the
    #    organization. A candidate rejected as an aggregator or a dead page does
    #    not become right when rendered; a blocked one might.
    hard = []
    for i, o in enumerate(orgs):
        if pick(o, score_org(i, o)) is not None:
            continue
        for c in short[i]:
            st = (store.get(c["url"]) or {}).get("state")
            if st in ("blocked", "thin", "spa", "error", None):
                hard.append(c["url"])
    if hard:
        from browser_batch import recover
        print(f"browser recovery for unsettled organizations: {len(set(hard))}",
              flush=True)
        recover(store, urls=list(dict.fromkeys(hard)), conc=6)

    # 4. host roots, for the picks only
    picked = {}
    roots = []
    for i, o in enumerate(orgs):
        b = pick(o, score_org(i, o))
        picked[i] = b
        if b is not None:
            r = host_root(b["cand"]["url"])
            if r != b["cand"]["url"]:
                roots.append(r)
    if roots:
        print(f"host roots to check for the picks: {len(set(roots))}", flush=True)
        crawl(roots, store, workers=workers, use_browser=False, label="roots")

    # 5. score, pick, resolve root
    rows, detail = [], []
    for i, o in enumerate(orgs):
        scored = score_org(i, o)
        best = pick(o, scored)
        rec = {"facility_id": o.get("facility_id", ""), "name_ko": o["name_ko"],
               "category": o.get("category", ""), "sido": o.get("sido", ""),
               "sigungu": o.get("sigungu", ""), "phone": o.get("phone", ""),
               "n_candidates": len(short[i])}
        if best is None:
            rec.update(url="", tier="", rank="", evidence="", how="",
                       page_title="", verdict="not_found")
        else:
            url, how = resolve_root(o, best, store)
            sc = best["score"]
            rec.update(url=url, tier=sc["tier"], rank=sc["rank"],
                       evidence=",".join(sc["evidence"]), how=how,
                       page_title=best["page_title"],
                       verdict=("found_A" if sc["rank"] <= 1 else
                                "found_B_snippet" if sc["rank"] == RANK["B_snip"]
                                else "found_" + str(sc["tier"])))
        rows.append(rec)
        detail.append({"facility_id": o.get("facility_id", ""),
                       "name_ko": o["name_ko"],
                       "queries": [q for _, q in build_queries(o)],
                       "candidates": [{
                           "url": s["cand"]["url"], "slots": s["cand"]["slots"],
                           "pos": s["cand"]["best_pos"], "state": s["state"],
                           "title": s["page_title"],
                           "rank": s["score"]["rank"], "tier": s["score"]["tier"],
                           "evidence": s["score"]["evidence"],
                           "reject": s["score"]["reject"]} for s in scored]})

    res = pd.DataFrame(rows)

    # One more directory test, learned from the data instead of enumerated:
    # a host that ends up as the pick for several DIFFERENT organizations, and
    # whose name none of them carries, is a directory this run had never seen.
    # The enumerated list caught moyaweb and dorojuso; this catches the next one.
    picked_host = collections.Counter(
        hosts.host_of(u) for u in res.url if u)
    shared = {h for h, n in picked_host.items() if h and n >= 4}
    demoted = 0
    for i, r in res.iterrows():
        h = hosts.host_of(r["url"])
        if h not in shared:
            continue
        hc = re.sub(r"[^a-z0-9가-힣]", "", h.lower())
        own = any(idmatch.compact(t) in hc
                  for t in idmatch.distinctive_tokens(r["name_ko"])
                  if len(idmatch.compact(t)) >= 2)
        if own:
            continue
        # This is where a deterministic rule stops being able to help. The 45
        # 출입국·외국인관서 sit at immigration.go.kr/immigration/<id>/subview.do
        # and that page IS each office's own; 46 rows sat on welfarehello.com,
        # a welfare portal running news items about them. BOTH spell the
        # organization's whole name, so no string test separates them.
        #
        # So the row is not decided here. It keeps its URL, is marked, and is
        # sent to the adversarial read, which is asked exactly this question
        # (own / parent_or_host / aggregator). Deciding it here by guessing
        # would be the census's "attaching something is not better than
        # attaching nothing" failure.
        res.at[i, "verdict"] = "found_shared_host"
        res.at[i, "tier"] = "B"
        res.at[i, "how"] = "shared_host"
        demoted += 1
    if demoted:
        print(f"sent to adversarial read, host shared by 4+ organizations: "
              f"{demoted} ({len(shared)} hosts)", flush=True)

    res.to_csv(os.path.join(OUT, f"{out_prefix}.csv"), index=False,
               encoding="utf-8-sig")
    with open(os.path.join(OUT, f"{out_prefix}_detail.jsonl"), "w",
              encoding="utf-8") as f:
        for d in detail:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print("\n=== website search result ===")
    print(res.verdict.value_counts().to_string())
    print(f"\nwrote {out_prefix}.csv and {out_prefix}_detail.jsonl to data/processed/v2/")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(ROOT, "data", "processed",
                                                    "v2", "frame_v2_geo.csv"))
    ap.add_argument("--out", default="website_found")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--all", action="store_true",
                    help="search every row, not only rows without a website")
    a = ap.parse_args()
    run(a.frame, a.out, a.limit, a.workers, only_missing=not a.all)
