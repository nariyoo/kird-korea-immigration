# v2 파이프라인 — 실행 순서와 각 단계가 지키는 규칙

`scripts/v2/` 아래에 있다. **순서가 곧 방법이다.** 뒤 단계가 앞 단계의 산출을 증거로
쓰기 때문에 순서를 바꾸면 조용히 다른 결과가 나온다. 미국 조직 센서스에서 순서를
어겨 3,022개 기관의 재코딩이 통째로 지워진 적이 있다 (실패 #2).

## 고정 실행 순서

```
0. normalize_addresses.py 명부의 모든 주소       → addr_canon.json       (카카오 → 법정동+본번-부번)
0b. pull_ssis_facilities.py 사회복지시설 OpenAPI   → welfare/ssis_*.csv     (다문화가족지원센터 분모)
0c. enrich_from_ssis.py   등록부 대 틀            → fixup/addr_ssis_done.csv (주소 보강과 충돌 분리)
1. build_frame.py        명부 전부 + v1 master → frame_v2.csv          (중복 병합, 신원 해시 id)
2. geocode_frame.py      frame_v2.csv          → frame_v2_geo.csv      (좌표 + 출처)
3. find_websites.py --all frame_v2_geo.csv    → website_found.csv     (질의 5종, 후보 fetch, tier)
4. llm_verify.py         website_found.csv     → website_verified.csv  (A 아닌 것만 반박 검증)
5. find_socials.py       + website_verified    → socials_v2.csv        (자기 사이트에서 읽은 것 우선)
5b. verify_socials.py    socials_v2.csv        → socials_v2.csv        (이름 없는 계정 제거)
5c. find_news_evidence.py frame_v2_geo.csv     → existence_evidence.csv (실재 흔적)
6. code_inclusion.py     + website_verified    → inclusion_coded.csv   (serves / unit_type / 근거)
6b. code_services.py     inclusion_coded.csv   → inclusion_coded.csv   (services_tag / pop_tag)
6c. code_governance.py   inclusion_coded.csv   → inclusion_coded.csv   (gov_funder / gov_operator)
7. build_orgs.py         위 전부              → 05_dashboard/orgs.json
8. export_dashboard.py   orgs.json            → facilities.json, facility_counts.json
9. inject_resource_page.py orgs.json          → h-resource.html, h-notes.html
```

3번의 `--all` 은 빼면 안 된다. 이 플래그가 없으면 `website` 칸이 비어 있는 행만
검색하고, 명부가 URL을 이미 적어 둔 나머지는 `website_found.csv` 에 아예 들어가지
않는다. `build_orgs.py` 는 그 파일에서 주소를 읽으므로, 명부가 준 링크를 전부 잃은 채로
빌드가 끝난다. 실제로 한 번 그렇게 돌아서 census 가 `0/1835 web (0%)` 을 찍었다. 지금은
`build_orgs.py` 가 웹사이트 보유율 20% 미만이면 쓰기를 거부한다. `--all` 은 명부가 준
URL도 다른 후보와 똑같이 신원 검사를 거치게 한다는 점에서도 맞는 기본값이다.

0번은 `build_frame.py` 의 주소 비교가 성립하기 위한 전제다. 병합은 주소로 묶는데, 명부들은
같은 주소를 같은 방식으로 적지 않는다. `동진로263번길 14` 와 `동진로 263번길 14` 는
정규식이 각각 `동진로263번길14` 와 `동진로263` 으로 읽어서 영영 안 만나고, 한 명부가 지번
주소를 적고 다른 명부가 도로명 주소를 적으면 문자열로는 절대 같아지지 않는다. 주소 체계가
다르기 때문이다.

카카오 주소검색은 두 체계를 같은 레코드로 해석하고, 그 레코드에 법정동 코드와 본번·부번이
들어 있다. 이 세 값은 필지 하나만 가리키므로 두 표기와 두 체계가 모두 동의하는 키가 된다.

```
경상남도 진주시 동진로263번길 14   -> 4817011400-330-4
경상남도 진주시 동진로 263번길 14  -> 4817011400-330-4
경남 진주시 상대동 330-4          -> 4817011400-330-4
```

명부에 있는 주소 3,995개 중 3,853개(96%)가 필지 키를 받았고, **822개 필지가 명부마다 다르게
적혀 있었다**. 이 단계를 넣기 전 공개 지도에는 이름·지역이 같은 중복이 58쌍 있었다.

캐시는 원본 주소 문자열을 키로 쓰므로 재빌드는 새 주소만 조회한다. 캐시가 없으면
`build_frame.py` 가 문자열 키로 떨어지면서 그 사실을 출력한다.

6c 는 누가 돈을 대고 누가 운영하는지를 두 칸으로 코딩한다. 명부 하나하나가 곧 지정이거나
재원 프로그램이므로 명부를 1순위 근거로 쓰고, 운영주체 자유기술 칸은 명부가 비워 둔 값을
채우는 데만 쓴다. 정의와 분포는 [GOVERNANCE_CODING.md](GOVERNANCE_CODING.md) 에 있다.

`audit_current_web.py` 는 이 흐름 밖이다. v1 공개본이 얼마나 틀렸는지 재는 용도이고,
결과는 `docs/WEB_ATTRIBUTION_AUDIT.md` 에 있다.

## 왜 이 순서인가

- **웹사이트가 포함 판정보다 먼저다.** 기관이 이주민을 지원하는지 판정하려면 그 기관이
  자기 사이트에 뭐라고 써 놨는지를 봐야 한다. 이름과 주소만으로 판정하면 그것이 곧
  규칙 11이 금지하는 `name_only` 판정이다.
- **SNS가 웹사이트보다 뒤다.** 계정은 기관 자기 사이트에서 읽은 것만 무조건 채택한다.
  사이트가 확정되기 전에는 어디서 읽어야 하는지 알 수 없다.
- **export 가 build_orgs 보다 뒤다.** `facilities.json` 과 `facility_counts.json` 은
  orgs.json의 투영이다. 따로 만들면 세 파일이 서로 다른 숫자를 말하게 된다
  (센서스 실패 #5: orgs.json은 바뀌었는데 summary.json이 안 바뀌어 화면의 대표 숫자가
  깜빡이며 두 값을 오갔다).

## 캐시

전부 재실행 가능하고, 네트워크 작업은 디스크에 캐시된다.

| 파일 | 무엇 | 지우면 |
|---|---|---|
| `data/interim/serper_v2_cache.jsonl` | 질의별 검색결과 | 검색을 다시 산다 |
| `data/processed/v2/pages_candidates.jsonl` | 후보 페이지 본문 | 다시 크롤한다 |
| `data/processed/v2/pages_current.jsonl` | v1 공개 URL 페이지 본문 | 〃 |
| `data/interim/geocode_v2_cache.json` | 카카오 지오코딩 | 다시 호출한다 |
| `data/processed/v2/llm_verify_cache.jsonl` | 웹사이트 반박 검증 | 다시 호출한다 |
| `data/processed/v2/inclusion_cache.jsonl` | 포함 판정 | 〃 |

## 사람이 봐야 하는 산출물

기계가 판정을 미룬 것은 지우지 않고 별도 파일로 뺀다. 이 네 개가 다음 사람의 작업 목록이다.

| 파일 | 무엇 |
|---|---|
| `review_dedup.csv` | 이름이 비슷한데 같은 기관인지 다른 기관인지 기계가 못 정한 쌍 |
| `review_inclusion.csv` | 포함 근거가 이름뿐이거나 판정이 `no` 로 나온 행 |
| `review_web_current.csv` | v1 웹사이트 중 확인되지 않은 것 |
| `website_found_detail.jsonl` | 기관마다 어떤 질의로 어떤 후보가 나왔고 왜 떨어졌는지 |

## 각 모듈이 지키는 것

**`idmatch.py`** — 신원은 증거집합으로 돌려주고 절대 불리언으로 돌려주지 않는다.
토큰 겹침, 포함관계, 같은 건물, 괄호 약칭은 후보를 정렬하는 데만 쓴다.
전화번호·도로명주소·전체이름만이 신원을 확정한다.

**`fetchpage.py`** — requests → curl_cffi(Chrome TLS) → Playwright 로 올라간다.
`blocked`(차단) / `parked`(주차) / `thin`(빈 페이지) / `spa`(JS 셸) / `notfound` /
`error` 를 각각 다르게 기록한다. 차단은 판정이 아니다. Cloudflare·Akamai 인터스티셜은
길이가 아니라 문구로 잡는다. 한국어 페이지의 EUC-KR/CP949 인코딩을 직접 판별한다
(틀리면 페이지 전체가 깨져 모든 이름 검사가 실패한다).

**`hosts.py`** — URL이 틀리는 방식을 종류별로 나눈다. aggregator / social / news /
portal / filejunk 는 강등하고, platform(사이트빌더·블로그호스트)은 강등하지 않는다.
그 위의 내용은 기관 자신의 것이기 때문이다. 충돌 검사는 호스트가 아니라 **경로까지
포함한 정규화 URL**로 한다. 한 사이트빌더에 세 든 두 기관을 한 페이지로 착각하면 안 된다.

**`find_websites.py`** — 질의 5종은 모든 기관에 똑같이 적용한다. 비용을 아끼려고 일부
기관만 줄이지 않는다. 후보는 **키 정확도 순으로만** 정렬하고, 결과 수나 검색 순위는
같은 등급 안에서만 동점을 가른다. 페이지를 못 읽은 후보는 구글 검색결과의 제목·스니펫으로
대신 판정하되(구글은 한국에서 읽었다) 등급을 한 칸 낮추고 `via_snippet` 을 붙인다.

**`llm_verify.py`** — 전화번호나 주소로 이미 확정된 건은 다시 묻지 않는다. 나머지는
모델에게 **반박**을 시키고, 확신이 없으면 `own` 을 못 고르게 한다.

**`find_socials.py`** — 기관 자기 사이트에 링크된 계정은 무조건 채택. 사이트가 없는
기관만 검색으로 찾고, 그때도 프로필이 **전체 이름**을 담아야 한다. 검색으로 찾은
LinkedIn·X·YouTube 는 연락 경로를 늘리지 않으면서 위험만 같으므로 아예 찾지 않는다.

**`code_inclusion.py`** — 권위 있는 명부가 그 자격으로 실은 행은 모델에게 묻지 않는다.
명부가 더 나은 증거다. 나머지만 기관 자기 사이트 본문을 증거로 코딩하고, 증거가
기관명과 주소뿐이면 판정하지 않고 사람에게 넘긴다.

**`build_orgs.py`** — 쓰기 전에 필드별 census를 찍고, 좌표가 80% 아래로 떨어지면
쓰기를 거부한다. 웹사이트가 바뀐 기관의 옛 사이트에서 읽은 SNS는 버린다.

## 실행

```bash
PY="C:/Users/Nari/anaconda3/python.exe"
cd "G:/My Drive/03 Research/03 Immigration NLP/KIRD Dashboard/08_migrant_facilities_map"
for s in build_frame geocode_frame find_websites llm_verify find_socials \
         code_inclusion build_orgs export_dashboard; do
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 "$PY" -u "scripts/v2/$s.py" || break
done
```

전부 캐시를 쓰므로 두 번째 실행부터는 네트워크 작업이 거의 없다.

## 아직 안 한 것

- 차단된 306행(대부분 `*.familynet.or.kr`)의 페이지 본문 확인. 한국 IP에서 3단계를
  한 번 돌리면 끝난다.
- `DATA_GO_KR_KEY` 발급. 이게 있으면 경기도 31개 시군이 한 번에 나올 가능성이 있다.
- 경기도 26개 시군, 인천 7개 군구의 지자체 시설.
- 폭력피해 이주여성 쉼터 33개소는 소재지 비공개라 영구히 못 넣는다. 갭 분석 화면에
  그 사실을 적어야 한다.
