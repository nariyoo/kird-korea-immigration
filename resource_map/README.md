# Resource map

이 디렉터리는 openICPSR 예치 자료와 **다른 산출물**이다. 예치된 것은
2006–2025년 등록외국인 통계 패널이고, 여기 있는 것은 이주민 지원기관 표집틀과
그것을 만든 코드다. 예치 자료를 재현하려면 `code/` 를 보면 된다.

## 무엇인가

한국의 이주민 지원기관을 명부 단위로 모아 하나의 표집틀로 만들고, 각 기관의
홈페이지와 SNS 계정이 실제로 그 기관의 것인지 검증하고, 무엇을 하는 곳인지와
누가 돈을 대고 누가 운영하는지를 코딩한 것이다. 결과는 대시보드의 자원지도
화면으로 공개된다.

## 문서

| 파일 | 내용 |
|---|---|
| `docs/PIPELINE_V2.md` | 실행 순서와 각 단계가 보장하는 것 |
| `docs/INCLUSION_CRITERIA.md` | 무엇이 목록에 들어오고 무엇이 빠지는가 |
| `docs/FRAME_COVERAGE.md` | 명부별 분모와 수집 현황, 막힌 것 |
| `docs/GOVERNANCE_CODING.md` | 재원과 운영주체 두 변수의 정의와 분포 |
| `docs/WEB_ATTRIBUTION_AUDIT.md` | 홈페이지 오귀속을 어떻게 측정하고 고쳤는가 |
| `docs/V2_RESULT.md` | 위음성·위양성·오귀속 세 질문에 대한 답 |

## 재현에 필요한 것

`scripts/` 는 그대로 옮겨 놓은 것이고 경로는 프로젝트 작업 트리를 전제한다.
원자료(`data/raw/v2/`)와 캐시는 용량과 이용약관 때문에 여기 포함하지 않았다.
Serper 검색 키와 카카오 로컬 API 키가 필요하다.

## 인용

Yoo, N. (2026). *Spatiotemporal administrative dataset of nationality,
residential diversity, and language demand among immigrants in South Korea,
2006–2024* [Data set]. Ann Arbor, MI: openICPSR.
https://doi.org/10.3886/E249944V1
