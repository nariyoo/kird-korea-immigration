# -*- coding: utf-8 -*-
"""Adversarial second read of a chosen website.

The deterministic fingerprint answers "does this page print something only this
organization prints". It cannot answer "is this page ABOUT this organization or
about the body that hosts it", which is the failure that put a parish directory
on eleven Catholic migrant centres and a city portal on a district office.

So every pick that is not settled by a phone number or a street address gets a
second, sceptical read. The prompt asks the model to REFUTE, and uncertainty
resolves to rejection, because attaching the wrong site is worse than attaching
none (census standing rule: a join that cannot find an identity must fail
loudly).

Run:
  python scripts/v2/llm_verify.py --picks website_found.csv --out website_verified.csv
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
from webcache import PageStore  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
MODEL = os.environ.get("VERIFY_MODEL", "claude-sonnet-5")
CACHE = os.path.join(OUT, "llm_verify_cache.jsonl")

SYSTEM = """당신은 한국의 이주민 지원기관 데이터셋을 검수한다. 어떤 웹페이지가 특정 기관의
공식 웹사이트로 기록되어 있다. 당신의 일은 그 기록을 **반박하는** 것이다.

판정값 하나를 고른다.

- `own`: 이 페이지는 그 기관 자신의 웹사이트다. 페이지가 그 기관의 이름으로 스스로를 소개하고,
  그 기관의 소개·사업·연락처를 담고 있다.
- `parent_or_host`: 그 기관이 속한 상위 조직(지자체, 교구, 본부, 모법인, 위탁기관)의
  사이트이거나 상위 조직 사이트 안의 한 페이지다. 그 기관 이야기가 나오더라도 사이트의
  주인이 다르면 이 값이다.
- `different_org`: 이름이 비슷하거나 같은 지역에 있을 뿐 다른 기관의 사이트다.
- `aggregator`: 지도 서비스, 업체정보 조회, 채용정보, 뉴스 기사, 블로그, 위키, 명부·디렉터리
  등 기관 자신이 만들지 않은 페이지다.
- `cannot_tell`: 페이지 내용이 판정에 모자란다. 차단 화면, 빈 페이지, 로그인 요구 등.

**확신이 없으면 `own` 을 고르지 마라.** 애매하면 `cannot_tell` 이다.
같은 이름의 단어가 몇 개 겹친다는 것은 근거가 아니다. 페이지가 그 기관의 주소나 전화번호를
적고 있는지, 그 기관의 이름으로 스스로를 부르는지를 보라.

JSON 하나만 출력한다. 다른 말은 쓰지 않는다.
{"verdict": "...", "owner": "페이지 주인의 이름(모르면 빈 문자열)", "why": "한 문장"}"""


def make_prompt(row, page):
    txt = (page.get("text") or "")[:3500]
    return f"""## 기록된 기관
이름: {row.get('name_ko','')}
유형: {row.get('category','')}
소재: {row.get('sido','')} {row.get('sigungu','')}
주소: {row.get('road_address','') or row.get('addr','')}
전화: {row.get('phone','')}

## 기록된 웹사이트
URL: {row.get('url','')}
<title>: {page.get('title','')}
og:site_name: {page.get('og_site_name','')}
meta description: {page.get('description','')}

## 페이지 본문 (앞부분)
{txt}
"""


_lock = threading.Lock()
_cache = {}
if os.path.exists(CACHE):
    with open(CACHE, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
                _cache[r["k"]] = r["v"]
            except Exception:
                pass


def _client():
    import anthropic
    key = (os.environ.get("ANTHROPIC_API_KEY")
           or os.environ.get("ANTHROPIC_API_KEY_BATCH"))
    return anthropic.Anthropic(api_key=key)


CLI = None


def judge(row, page):
    global CLI
    k = f"{row.get('facility_id','')}|{row.get('url','')}|{MODEL}"
    if k in _cache:
        return _cache[k]
    if CLI is None:
        CLI = _client()
    v = {"verdict": "cannot_tell", "owner": "", "why": "api error"}
    for attempt in range(3):
        try:
            m = CLI.messages.create(
                model=MODEL, max_tokens=400, system=SYSTEM,
                messages=[{"role": "user", "content": make_prompt(row, page)}])
            t = "".join(b.text for b in m.content if b.type == "text").strip()
            t = t[t.find("{"): t.rfind("}") + 1]
            v = json.loads(t)
            break
        except Exception as e:
            v = {"verdict": "cannot_tell", "owner": "",
                 "why": f"{type(e).__name__}"}
    with _lock:
        _cache[k] = v
        with open(CACHE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")
    return v


def run(picks_csv, pages_jsonl, out_csv, workers=6, only_uncertain=True):
    df = pd.read_csv(picks_csv, dtype=str).fillna("")
    df = df[df["url"].str.strip() != ""].copy()
    store = PageStore(pages_jsonl)
    if only_uncertain:
        # A phone number or a street address printed on the page settles
        # identity WHEN the page is the organization's own domain. It settles
        # nothing on a host shared by dozens of organizations, where the portal
        # prints everybody's phone number, so those always go to the model
        # regardless of what the fingerprint found.
        settled = ((df["evidence"].str.contains("phone|address", na=False)
                    & (df.get("verdict", "") != "found_shared_host")
                    & (df.get("how", "") != "shared_host"))
                   # a facility's own subdomain on its network's official web
                   # system needs no second opinion, and asking for one on a
                   # page that returns HTTP 400 to this country only produces
                   # cannot_tell
                   | df["evidence"].str.contains("official_platform", na=False)
                   # a person opened this one; there is nothing to adjudicate
                   | df["evidence"].str.contains("manual_verified", na=False))
        todo = df[~settled].copy()
    else:
        todo = df.copy()
    print(f"picks {len(df)} | sent to adversarial read {len(todo)} "
          f"(settled by phone/address: {len(df)-len(todo)})")

    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(judge, r, store.get(r["url"]) or {}): i
                for i, r in todo.iterrows()}
        done = 0
        for fu in as_completed(futs):
            i = futs[fu]
            res[i] = fu.result()
            done += 1
            if done % 25 == 0:
                print(f"  verified {done}/{len(todo)}", flush=True)

    df["llm_verdict"] = ""
    df["llm_owner"] = ""
    df["llm_why"] = ""
    for i, v in res.items():
        df.at[i, "llm_verdict"] = v.get("verdict", "")
        df.at[i, "llm_owner"] = v.get("owner", "")
        df.at[i, "llm_why"] = v.get("why", "")
    df.loc[df["llm_verdict"] == "", "llm_verdict"] = "settled_by_key"

    keep = df["llm_verdict"].isin(["own", "settled_by_key"])
    df["final_website"] = df["url"].where(keep, "")
    df["demote_reason"] = df["llm_verdict"].where(~keep, "")

    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("\n=== adversarial verdicts ===")
    print(df.llm_verdict.value_counts().to_string())
    print(f"\nkept {int(keep.sum())} of {len(df)}")
    print(f"wrote {out_csv}")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", default=os.path.join(OUT, "website_found.csv"))
    ap.add_argument("--pages", default=os.path.join(OUT, "pages_candidates.jsonl"))
    ap.add_argument("--out", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    run(a.picks, a.pages, a.out, a.workers, only_uncertain=not a.all)
