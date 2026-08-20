# MOIS 외국인주민통계 파서 — KIRD supplement (2006-2024)

행정안전부 「지방자치단체 외국인주민 현황」 2006-2024 (19년) 전수 처리.
KIRD 본체(MOJ 출입국통계)와 별개 레이어로 통합 가능.

## 산출물 (`통계연보/data_processed/`)

| 파일 | 차원 | 연도 | 행 수 |
|---|---|---|---|
| `mois_sido.csv` | 시도 × 외국인주민 카테고리 × 성별 | 2006-2024 | 10,004 |
| `mois_sigungu.csv` | 시군구 × 카테고리 × 성별 | 2006-2024 | 143,785 |
| `mois_eupmyeondong.csv` | 읍면동 × 카테고리 | 2014-2024 | 549,355 |
| `mois_multicultural_eupmyeondong.csv` | 다문화가구원 × 읍면동 × 가구원유형 | 2016-2024 | 298,049 |
| `mois_nationality_sigungu.csv` | 시군구 × **국적별** × 성별 | 2009-2024 | 257,709 |
| `mois_nationality_eupmyeondong.csv` | **읍면동 × 국적별** × 성별 | 2014-2015 | 380,322 |
| `mois_nationality_by_visa_sigungu.csv` | 시군구 × 비자유형 × 국적별 × 성별 | 2009-2024 | 825,948 |
| `mois_nationality_by_visa_eupmyeondong.csv` | **읍면동 × 비자유형 × 국적별** | 2014-2015 | 1,779,084 |
| `mois_nationality_naturalized_sigungu.csv` | 시군구 × 귀화자 국적 × 성별 | 2014-2015 | 24,678 |
| `mois_nationality_naturalized_eupmyeondong.csv` | **읍면동 × 귀화자 국적** | 2014-2015 | 379,404 |
| `mois_nationality_children_sigungu.csv` | 시군구 × 자녀 국적 × 성별 | 2014-2015 | 24,678 |
| `mois_nationality_children_eupmyeondong.csv` | **읍면동 × 자녀 국적** | 2014-2015 | 380,052 |
| `mois_children_age_sido.csv` | 시도 × 자녀 연령(0-18세) × 성별 | 2014-2024 | 10,651 |
| `mois_children_age_sigungu.csv` | 시군구 × 자녀 연령 × 성별 | 2011-2024 | 189,664 |
| `mois_children_parent_type_eupmyeondong.csv` | **읍면동 × 부모유형 × 국적** | 2014-2015 | 986,256 |
| `mois_children_parent_type_sigungu.csv` | 시군구 × 자녀유형(귀화·인지/국내출생) | 2016-2024 | 14,306 |
| `mois_residence_period_sigungu.csv` | 시군구 × 체류기간 × 성별 | 2016-2024 | 31,626 |
| `mois_naturalized_prev_nationality_sigungu.csv` | 시군구 × 귀화자 이전국적 × 성별 | 2016-2024 | 44,617 |
| `mois_naturalization_period_sigungu.csv` | 시군구 × 국적취득경과기간 | 2016-2024 | 15,710 |
| `mois_household_eupmyeondong.csv` | 읍면동 × 외국인주민 세대수 | 2014-2015 | 7,048 |
| `mois_coverage.csv` | (메타) 연도/레벨/카테고리 매트릭스 | — | 49 |
| | | **합계** | **~6.4M** |

읽기 좋은 long 포맷: `year, sido, sigungu, [eupmyeondong,] [category|country|age|visa_type|parent_type,] sex, n`.

## KIRD 본체에 새로 들어오는 자산

### 🔥 KIRD/MOJ 둘 다 없는 데이터
- **읍면동 × 국적별** (2014-2015): 380K 행. 동단위 다양성 분석 가능 — KIRD enclave/diversity 지표를 한 해상도 아래로
- **읍면동 × 비자유형 × 국적별** (2014-2015): 1.78M 행. 외국인근로자/결혼이민자/유학생 별 동단위 분포
- **읍면동 × 부모유형 × 국적별** (2014-2015): 986K 행. 동단위 2세대 immigrant 분포
- **읍면동 × 귀화자/자녀 국적별** (2014-2015): 759K 행
- **읍면동 × 세대수** (2014-2015): 7K 행

### 💡 시군구 단위로 KIRD 확장
- **귀화자 (한국국적취득자)** × 시군구 × 국적/연도: MOJ엔 부재
- **외국인주민 자녀** × 시군구 × 연령(0-18세) × 성별: 2011-2024 (14년) — K-12/보육 정책 분석
- **자녀 부모유형** (외국인부모/외-한국인부모/한국인부모): 2009-2015 메인 시트 / 2016+ 귀화·인지/국내출생
- **체류기간별**: 정착 vs 단기 비율 (2016-2024)
- **귀화자 이전국적**: 출신국별 귀화 인구 (2016-2024)
- **다문화가구원**: 한국인배우자/결혼이민자/귀화자/자녀/동거인 (2016-2024)

### KIRD/MOJ와 비교
| 카테고리 | KIRD (MOJ) | MOIS (이번) |
|---|---|---|
| 등록외국인 | ✓ 2006-2024 | ✓ 2006-2024 |
| 한국국적취득자 | ✗ | ✓ 2006-2024 |
| 외국인주민 자녀 | ✗ | ✓ 2006-2024 |
| 외국인 × 국적 × 시군구 | 2017+ | 2009-2024 |
| 외국인 × 국적 × **읍면동** | ✗ | **2014-2015** |
| 자녀 × 연령 × 시군구 | ✗ | 2011-2024 |
| 다문화가구원 | ✗ | 2016-2024 |

## 처리 순서

```bash
python scripts_mois/run_all.py
```

또는 개별:
```
parse_2006.py → parse_2007_2010.py → parse_2011_2013.py → parse_2014_2015.py
→ parse_2016plus.py → parse_nationality.py → parse_children_age.py
→ parse_extras.py → consolidate.py
```

각 단계 idempotent. consolidate.py는 합계 시트의 시기별 결과를 단일 CSV로 합침.

## 알려진 한계

1. **2015→2016 스키마 단절**:
   - 2016+ 메인 1-1/1-2/1-3 시트는 합계 수준만 제공 (한국국적취득 sub, 자녀 부모유형 sub 빠짐).
   - 세부 정보는 별도 시트(6, 7, 8, 9, 10)에 분산 — 본 파서로 다 추출했음.
2. **2014-2015 읍면동 vs 시도시군구 분리**: 별도 파일로 제공되어 파서도 두 파일을 읽음.
3. **2015 인구주택총조사 기준** (`2015_외국인주민통계_인구주택총조사기준.xlsx`): 동일 연도 다른 방법론 — 현재 파서 미사용 (이중계상 방지). 별도 robustness check 시 활용 가능.
4. **2024 1-3 시트 오타** (`천찬시동남구` → `천안시동남구`): 자동 보정.
5. **결혼이민자 및 국적취득자 연령별** (2014-2015 sheet 5): 시트 구조 특수해서 미처리. 시도×연령×혼인이민/귀화 cross-table — 필요시 별도 파서.
6. **읍면동 행정동 코드**: 현재 한글 이름만. KIRD geometry와 매칭하려면 행안부 표준 행정동코드(BCNT 5자리) 매핑 필요.

## 권장 KIRD 통합 단계

1. `scripts/build_mois_layer.py` 신설: `data_processed/mois_*.csv`를 site/data/ JSON 형태로 변환
2. 읍면동 행정동 코드 매핑 (행안부 표준코드 또는 통계청 KOSTAT 코드)
3. MOJ vs MOIS 시군구 단위 합계 비교 → manuscript robustness check
4. **읍면동 enclave/LQ 지표** (2014-2015): KIRD 현 시군구 지표를 동 단위 확장 — 시기는 2년이지만 unique geographical scale
