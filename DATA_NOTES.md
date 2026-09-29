# Data notes

Notes for the tables deposited at ICPSR (https://doi.org/10.3886/E249944): how to read them, how each table is built, how the levels add up, how the indices are defined, and where and why cells are blank. `data_dictionary.csv` in the deposit defines every column; `README.md` describes the pipeline.

## Reading the files

| Level | Start here | What it is | Count |
|---|---|---|---|
| **sido** (시도) | `summary_by_sido.csv` | provinces and metropolitan cities | 16 (2006-2011) / 17 (2012-) |
| **sigungu** (시군구) | `summary_by_sigungu.csv` | districts: autonomous gu, cities (si), counties (gun), and the general gu of large cities | ~250 |
| **eup/myeon/dong** (읍·면·동) | `summary_by_eupmyeondong.csv` | sub-districts (towns and neighborhoods) | ~3,500 |

Begin from the summary file at your level. One row is one place in one year, with
the headline measures already on it: foreign share, the broad-definition
composition, settlement type and, at the national, sido and sigungu levels, the
diversity indices. Use a breakdown file only when you need detail within a place
(by nationality, visa status, age and sex, language, and so on).

**Join keys.** Join on codes, not names. Each row has `sido_code` (2 digits) and
`sigungu_code` (5 digits), the 행정안전부 법정동코드 in force on 31 December of the
row's year, and sub-district rows also have `adm_code`, that year's
administrative-dong code for joining to GIS boundaries. Names move (인천 남구 became
미추홀구 in 2018; 군위군 moved from 경상북도 to 대구광역시 in 2023), and the English
district name `sigungu_en` is not unique on its own: several provinces have a 동구 or
a 중구, all `Dong-gu` or `Jung-gu`. Join the levels on `(year, sigungu_code)`.

**Read the code columns as text.** The codes are identifiers, and they are blank on
some rows of some files, so pandas would read them as float in one file and integer
in another and a join would silently match nothing. Read them as strings:
```python
import pandas as pd
codes = {c: str for c in ("sido_code", "sigungu_code", "adm_code")}
df = pd.read_csv(path, encoding="utf-8-sig", converters=codes)
```
The files are UTF-8 with a byte-order mark, hence `utf-8-sig`. A converter touches
only its own column, so the counts remain numeric; do not use `keep_default_na=False`
for the same purpose, since it turns every blank in the file into text. In R,
`readr::read_csv(path, col_types = cols(sido_code = "c", sigungu_code = "c",
adm_code = "c"))`. The `.dta` files store the three codes as strings already.

## Usage notes

**Two population definitions.** MOJ registered foreigners (residence over 90 days, with
a foreign-resident registration) and MOIS broad-definition foreign residents
(non-naturalized residents, naturalized citizens and their children) are different
populations. Both appear side by side so a user can pick the base; the MOIS count
was about 1.7 times the MOJ count nationally in 2024. `resident_pop` counts Korean
nationals only, and `foreign_share_pct` is `registered_foreigners / resident_pop`.

**Counts aggregate across levels; indices are recomputed.** Counts at one level are
the sums of the level below. Diversity and segregation indices are computed at each level
with the unit treated as a whole, so a province's index is not the mean of its
districts'. When summing a district file up to provinces, group on `year` and the
first two digits of `sigungu_code`, not on `sido`: the district files label 세종시
and 군위군 with their 2024 province in every year, while the province files count a
district in the province it belonged to that year.

**Coverage changes.** District-level MOJ counts start in 2008 and sub-district
(MOIS) rows in 2014. For 2008-2013 the district tables list only the year's 19
largest nationalities nationwide by name and fold the rest into an Other line, so counts of
nationalities and enclave flags should not be compared across 2014. The MOIS
broad-definition counts exist at the general-gu level only from 2016; for 2008-2015
they are apportioned from the city total and flagged `broad_apportioned = True`.
From 2016 MOIS masks every count under 5; a masked cell is filled only where the
printed totals determine it exactly, and is otherwise blank.

**Status codes.** E-8 meant trainee employment (연수취업) in 2006-2009 and seasonal
work (계절근로) from 2021; the files code the first as `E8T` and the second as `E8`.
Marriage migrants hold F-2 until F-6 appears in 2011, so compare F-2 + F-6 across
that year. F-4 overseas Koreans file a residence report instead of a registration,
so they are absent from the district and province visa tables by construction; their
residence reports are in `diaspora_residence_by_sido`.

**Files with more than one population or level.** Filter before summing:
`population` in `age_sex_national`, `nationality_national`, `visa_national` and
`visa_by_nationality` (`registered` or `stay`); `category_level` in
`multicultural_households` (`total`, `subtotal`, `leaf`); `type` in the
naturalization panels, which mix subtotals with their routes; and `scope` in
`language_demand`.

## Files (data/)

The file tables are in `README.md` (section 2).

The dataset is organized into **per-level summary files** (one row per place ×
year, combining every single-value indicator from both MOJ and MOIS) and
**breakdown files** (kept separate because they have many rows per place × year,
e.g. one per nationality / visa / age / household type).

**Folder layout.** The four summary files (national, sido, sigungu, eup/myeon/dong)
sit at the top of `data/`; the breakdown files are under `data/detailed_data/`.

**Formats.** Every dataset is provided twice, with identical content: a
UTF-8 CSV (`*.csv`) and a labeled Stata file (`*.dta`, Stata 14 / version 118).
Each `.dta` carries a variable label on every column and a dataset label, with
Korean text preserved; column names match the CSV (all are within Stata's 32-char
limit). Categorical fields are kept as readable bilingual text rather than numeric
codes, so no value-label lookup is needed. Both formats are regenerated by the
build code on GitHub (https://github.com/nariyoo/kird-korea-immigration).

Each summary row carries MOJ `registered_foreigners` + diversity/segregation
indices **and** the MOIS broad-definition composition (`broad_total`,
`non_naturalized`, `workers`, `marriage_migrants`, `students`, `naturalized`,
`children`, …) plus derived settlement measures (`settlement_rate_pct`,
`*_dependence_pct`, `settlement_type`), and `foreign_resident_households`, the
MOIS count of foreign-resident households (외국인주민 세대수) that the 2009-2015
editions print after the children block (blank in the other years, which do not
print it; from 2014 also at the sub-district level). Eup/myeon/dong rows are
MOIS-only (MOJ publishes no sub-district detail) and carry that year's `adm_code`.

Each summary row **also carries the breakdown detail as wide columns**, so the most
common categories are available inline without joining to the long files. To keep
the width bounded, only the **top 50** categories of each dimension (by total count
over the whole panel) are attached; the full tail stays in the long breakdown files.
For nationality that is the **49 largest nationalities by name plus `nat_other`**,
everyone else: the other nationalities and the lines that name no nationality
(무국적, 미등록국가, 기타, 국제연합, ...), which are never ranked as if they were a
country. So the `nat_*` columns of a row always add up to its
`registered_foreigners` (at the national row, to the registered national total).

| Prefix | Dimension | Source | Levels |
|---|---|---|---|
| `nat_*` | nationality count | nationality_by_sigungu (sido, sigungu); nationality_national, registered (national) | national, sido, sigungu |
| `visa_*` | visa-status count | visa_by_sigungu (sido, sigungu); visa_national, registered (national) | national, sido, sigungu |
| `lang_*` | language-demand count | language_demand, sigungu scope | national, sido, sigungu |
| `mc_*` | multicultural leaf category | multicultural_households | eup/myeon/dong |
| `n_enclaves` | number of ethnic-enclave nationalities | ethnic_enclaves | national, sido, sigungu |

Column names use the romanized/English label (`nat_china`, `lang_vietnamese`, …);
`data_dictionary.csv` gives the Korean + English definition of every one. A
nationality or visa column is **0** where that year's table reports the category and
the place has none, and **blank where the category was not separately reported**
that year (for 2008-2013 the district tables list only the national top 19
nationalities and fold the rest into "Other", so the other named columns are blank
and their people are in `nat_other`). A `lang_*` cell is blank where the language is
not among the district's 20 largest.
Sido columns are sums of the district values, a district counting in the province
it belonged to that year (the first two digits of its `sigungu_code`), which is the
boundary every other column of `summary_by_sido` uses: 세종시 in 충청남도 for
2008-2011 and 군위군 in 경상북도 through 2022 (see The province of a district). They
equal the district sums to the person in every year and every wide column.

The national row is built differently for nationality and visa. Its `nat_*` and
`visa_*` columns are the published national counts on the registered basis, read
from `nationality_national` and `visa_national` (population = registered), so they
carry every nationality in every year and include the people the yearbook places in
no district. They are therefore not the sum of the district columns: from 2014 the
two differ by those unplaced people only, while for 2008-2013 the district tables
list only the top 19 nationalities of each district, so a national column there can
hold a nationality the district columns leave blank (or fold into 중국, as 2008 does
with 한국계중국인). The national `lang_*` columns remain the sum of the district rows
of `language_demand` (registered, district-allocated basis, each district carrying
its top ~20 languages); the file's `national` scope, which covers every language, is
on the staying basis and so is not used on this row.

Single-age children are **not** attached as wide columns: `children_by_age` covers
2011 onward only and is reported at a city/gu grain that does not line up with the
summary spine, so inline `childage_*` columns would not be additive across levels.
The children **total** is kept (the `children` broad-definition column), and the full
single-age detail (0-18) remains in the long `children_by_age.csv`.

`age_sex_national.csv` carries two populations in its `population` column, the
way `nationality_national.csv` does. `registered` counts registered foreigners
(등록외국인) from the yearbook table 국적(지역) 및 연령별 등록외국인 현황, 2006-2024.
`stay` counts staying foreigners (체류외국인), the registered population plus
short-term sojourners and F-4 residence reports, from 국적(지역) 및 연령별 체류외국인
현황, 2011-2024; the yearbook first prints that table in its 2011 edition. **Filter
to one population before summing or comparing years.** The two differ in level for
every nationality (United States 2013: 23,990 registered, 134,717 staying), so a
series that changes base between years shows a break with nothing behind it.
Summed over ages, each series equals `nationality_national.csv` for the same
population, line and year, the lines that name no nationality included (무국적, 기타,
미등록국가, 미상, 한국; see Levels and how they aggregate), with two exceptions that
come from the yearbook. In 2022 the age table names 17 staying residents under
홍콩거주난민, folded here into 홍콩, whom the status table counts in its 기타 line
without saying which statuses they hold, so they cannot be placed in the status
tables. And the staying age tables of 2014, 2015, 2016 and 2018 print a grand total
4, 3, 2 and 1 persons above the sum of their own rows, persons no row or sex holds,
whom the status table of the same edition counts in its 기타 line. `gender` is M, F,
T and, on the staying basis, X: the 제3의성 (third sex) row the staying table prints
(1 person in 2019, 3 in 2022, 7 in 2023, 9 in 2024), with T = M + F + X in every
cell. (The 2014 status table's 자격없음 (0-0)
column, 434 people across 46 nationalities, is read as status `X00`, so 2014
matches.) The 2006-2008 editions print the registered table on other bands, 0-5,
6-10, ... 56-60 and an open band printed 60세이상 in 2006-2007 and 61세 이상 in 2008.
`age_group` carries them under those labels (0-5 ... 56-60, then 60+ or 61+), 13
bands a year as in every other year, and does not fold them into 0-4 ... 60+,
because the yearbook does not settle which ages they hold: in 2006-2007 the printed
56-60 and 60+ both claim age 60, and the 2008 edition's region-by-age table, which
counts the same 854,007 people on bands printed 0-4, 5-9, ..., differs from this
table in every band (0-4 7,496 there, 0-5 9,377 here), while these counts run on
into 2009's bands as if they were the same ones (0-4 9,971 in 2009). Compare
2006-2008 with later years band by band only with that in mind; totals over all
bands are unaffected.

**Status codes whose meaning changed.** E-8 names two statuses. The 2006-2009
editions print it as 연수취업 (trainee employment; 69,595 registered in 2006); that
status was abolished and no edition prints an E-8 column from 2010 to 2020. From
the 2021 edition E-8 is 계절근로 (seasonal worker). The release carries the old
status as `E8T` and the seasonal-worker status as `E8`, so neither series runs into
the other; `crosswalk_visa` records the split. F-6 (결혼이민, marriage migrant)
first appears in 2011 (4,356 registered); before that, marriage migrants hold F-2
(거주), which falls from 138,345 in 2011 to 63,299 in 2012 as they move to F-6.
Compare F-2 + F-6 across 2011. `X00` is the 2014 stay table's 자격없음 (0-0).

**The crew status is one code, `E10`, from 2006.** The 2007-2009 editions print no
E-10 column. They print the crew status as three columns of their own, E0A 내항선원
(coastal-route crew), E0B 어선원 (fishing-vessel crew) and, in 2009, E0C 순항선원
(cruise-ship crew), E-0-A to E-0-C in the district tables: the three subdivisions the
yearbook prints under E-10 선원취업 from 2010 (E-10-1 to E-10-3), and the status the
2006 edition prints as E-10 내항선원. The release carries them as `E10` (2,900
registered in 2007, 4,314 in 2008, 5,207 in 2009), and `crosswalk_visa` has a row for
each column with the editions that print it (rule `crew column printed as ...`).

**Status labels an edition prints differently.** Ten labels differ from the one the
release carries for the same code, and `crosswalk_visa` lists each with the editions
that print it (rule `same code, label printed as ...`). D-3 is 산업연수 through the
2012 edition and 기술연수 from 2013, and the release carries 기술연수 in every
year with the English the Korea Immigration Service gives D-3, Industrial Trainee;
C-3 is 단기종합 through 2010 (단기방문 after), D-7 상사주재 through 2009 (주재), E-7
특정직업 in 2006-2009 (특정활동), E-9 비취업 in 2006-2009 (비전문취업), E-2 회화 or
회화강사 in some tables from 2010 (회화지도), E-10 내항선원 in 2006 (선원취업), and
G-1 기타 in every edition that prints the code whole, all but 2009 (기타비자; the
code-less 기타 column is `ETC`). The 2022 and 2024 registered tables print E-8 as
연수취업, the old trainee-employment name, over a column that holds the seasonal
workers (the staying and district tables of the same editions print 계절근로 or
E8), so those rows are `E8`.

**`children_by_age` does not sum to the `children` column.** It counts every
foreign-resident child MOIS lists by age, Korea-born and naturalized or foreign
nationality alike, while `summary_by_sigungu.children` counts Korea-born children
only from 2016, so the age file is larger (2024: 315,383 against 295,304).

`multicultural_households.csv` flattens a 3-level MOIS hierarchy into one file, so
grand totals (합계), the three subtotals (`*_소계`), and the leaf categories
coexist. Use the `category_level` column (`total` / `subtotal` / `leaf`) to filter
to a single level before summing, or you will double count. **The three levels need
not sum to each other.** MOIS masks every count under 5 (`*`) and prints no zero. A
masked cell is carried wherever the printed cells fix it, and may be 0: through the
sub-district's own identities (a part masked alone beside its subtotal and sibling,
one of the four groups masked alone under 합계, a subtotal whose parts are printed)
and through the district row printed above the sub-districts (see **Masked cells**
under Harmonization & validation). 45,051 rows of 2016-2024 are such cells, 15,433
of them 0; a cell nothing fixes has no row. So in 43 to 77 of the roughly 3,500
sub-district units each year (59 of 3,554 in 2024) the leaves still fall short of their
own subtotal in at least one of the three families (결혼이민자귀화자_소계, 자녀_소계,
기타동거인_소계), and nationally the leaf sum is 0.04-0.05% below 합계 every year (2024:
1,239,004 against 1,239,448; it was 0.6-0.8% before any masked cell was carried and
0.07-0.09% while only the sub-district's own row counted). The subtotals plus
한국인배우자 come closer (2024: 1,239,327). Use `total` for a headline count and treat the leaf level as a
composition, not an exhaustive partition.

**MOJ vs MOIS.** MOJ registered foreigners (long-term, >90 days) and MOIS
broad-definition foreign residents (non-naturalized + naturalized + children) use
**different population definitions** and are not directly comparable. Both are
included side by side in the summary files so users can pick the right base. The
two definitions diverge and increasingly so: nationally the MOIS broad count
reaches about 1.7x the MOJ registered count by 2024, and the ratio varies widely
across districts. Sejong (est. 2012-07) appears as its own district 세종시 from 2008; there is no
연기군 row anywhere in the panel. The 2012-2014 editions still print a residual 연기군 line under 충청남도 after that ground became 세종; the district and province files both count it in 세종, so the province row 세종특별자치시 equals the district 세종시 in every year from 2012. The files carry no broad-definition share: `resident_pop` counts Korean nationals only, so a share built from `broad_total` should state its denominator.

All categorical fields are **bilingual**: every Korean label column is paired
with an English column for international reuse: `country_en`, `sido_en`,
`sigungu_en` (Revised Romanization), `language_en`, `category_en`, `type_en`,
`visa_label_en`, `continent_en`. The one exception is the
eup/myeon/dong sub-district name, which is kept in Korean; for those rows the
official `adm_code` is the language-neutral identifier. See `data_dictionary.csv`
for bilingual variable definitions.

## Levels and how they aggregate
The panel carries the same indicator set at three levels: `summary_by_sigungu.csv`
(district), `summary_by_sido.csv` (province) and `national_annual.csv` (country).
Two rules govern the relationship between them.

- **Counts sum.** Resident population, the MOIS broad-definition composition, and
  the nationality and visa breakdowns at one level are the sum of the level below,
  a district counting in the province it belonged to that year (see The province of
  a district), and `national_annual.foreign_total` is the sum of the districts. For
  the general districts of 2008-2015 the district file's broad-definition columns are
  apportioned from the city total, each column split over the city's gu by the
  largest-remainder rule, so the district sums equal the province row exactly; the
  province rows add up to `national_annual` exactly. One column is the
  exception: `summary_by_sido.registered_foreigners` is the yearbook's own province
  row, which is the only source for 2006-2007. From 2008 it equals the sum of that
  province's districts in every province and year except 2015, when the yearbook's own
  경기도 소계 holds one person more than its district lines, so the province rows
  differ from the district sum by at most 1 person a year nationally. Use the district
  sum where the levels must add up.
- **Indices do not.** Shannon H, HHI, evenness, continent H and the segregation
  indices are recomputed at each level with that unit treated as one whole. A
  province's H is not the mean of its districts' H, and averaging the level below
  gives a different and wrong number.

`n_nationalities_observed` follows the first rule as a set union, not a sum: a
province's count is the number of distinct nationalities across its districts.

**The national tables carry the yearbook's non-nationality lines.** The
nationality x status table the national tables come from prints, besides the
nationalities, lines that hold people but name no nationality: 무국적 (Stateless)
in 2006-2013 and 2019, 미등록국가 and 미상 in 2019, a single 기타 (Other) line in
2014-2018 and 2020-2024 when it prints no stateless line, and 한국 (3 staying
persons in 2012). `visa_by_nationality`, `nationality_national` and `visa_national`
carry them as rows of their own (106 to 337 registered foreigners a year), so each
year equals the grand total the yearbook prints, on the registered and the staying
basis alike. The staying
population of every year is read from the edition's own nationality x status table.

**No-nationality columns in the district table.** The district and province
tables come from the yearbook's district table, which
prints the same kind of population as columns of its own, by edition: 무국적 in 2014-2016, 2019, 2021-2022 and 2024, 미등록국가 in 2014-2016, 2019 and 2021-2022, and a single 기타 column in 2017-2018, 2020 and 2023.
`nationality_by_sigungu` carries them district by district as printed (126 to 183 people a year over up to 85 districts),
so every district, province and national sum equals the table's printed total. They
are not nationalities: `n_nationalities_observed` does not count them, the diversity
indices put them in the residual bin, and they never form an enclave or a row of
`segregation_by_nationality`. In `region_segregation` they fall into the 기타
continent. The district table's labels that name no country (국적불명, 국제연합,
국제연합전문기구) are treated the same way: 기타 continent, not a nationality. In
the 2008-2013 district tables `기타` is a different thing, the yearbook's residual of
the nationalities it does not list by name (see Ethnic enclave below).
The national age table prints lines of the same kind, which `age_sex_national` carries as the status tables do (see Files).

The breakdowns come in level-parallel sets (v1.2.0): nationality at
`nationality_by_sigungu` / `nationality_by_sido` / `nationality_national`, visa
status at `visa_by_sigungu` / `visa_by_sido` / `visa_national`, and language
demand as the `scope` column of `language_demand`. From 2008 the sido
tables are sums of the district tables (allocated basis); the national tables are
projections of `visa_by_nationality` (published national basis). For 2006 and 2007,
which have no district table, `nationality_by_sido` carries the province table those
yearbooks print: five named nationalities (타이완, 미국, 일본, 필리핀 and 중국, without
한국계중국인) and an Other column, carried as 기타, which holds everyone else,
한국계중국인 included. `summary_by_sido`'s 2006-2007 `registered_foreigners` and
diversity indices come from the same table. `visa_by_sido` starts in 2008.

**The subnational visa tables are registered-foreigner only, and F-4 is absent
from them by construction.** `visa_national` carries a `population` column with
`registered` and `stay` rows; `visa_by_sido` and `visa_by_sigungu` correspond to
the `registered` rows alone. Holders of the F-4 overseas-Korean status file a
place-of-residence report (거소신고) under the Overseas Koreans Act rather than
a foreign-resident registration, so they never enter the registered basis and
`visa_by_sigungu` records zero F-4 in every district in every year from 2008 to
2024. Nationally they are the largest single status on the staying basis, at
555,968 in 2024. Anyone computing an overseas-Korean population by district from
the visa tables will get zero. Two files carry them instead:
`diaspora_residence_by_sido` holds the residence reports themselves, by
province and nationality, 2008 to 2024 (553,664 in 2024, of whom 389,544 are
Korean Chinese; each year sums to the table's printed total, the 2012 table's line
기타 of 8 people who have no province carried as sido 기타), and the `ethnic_koreans` column of `summary_by_sigungu` holds
the MOIS survey count at district level (415,695 in 2024). The two differ
because they are different registers with different definitions: the first
counts F-4 residence reports, the second counts ethnic Koreans among all
foreign residents in the MOIS survey.

**The district visa table adds up to the national registered total.**
`visa_by_sigungu` and `visa_by_sido` sum to the registered rows of `visa_national`
in every year from 2008 to 2024 (F-4 is zero on the registered basis at every
level, as above). Their `ETC` code is the district table's 기타 column, the
statuses the table does not list by code (분류외: SOFA, treaty and others): none
through 2012, 363 people in 2013, 39,210 at the 2020 peak and 31,626 in 2024, the
same as `visa_national`'s `ETC` in every year.
`nationality_by_sigungu` adds up to the same national registered total in every year except 2015 (1 person, whom the
yearbook's 경기도 소계 holds and none of its district lines does), because it carries
the district table's columns that name no nationality (see Levels and how they
aggregate). District by district the two files
hold the same people, with two differences that come from the 2015 tables themselves.
The district-by-nationality table prints a line under the bare name 창원시 (1 person)
above 창원시 마산합포구 (2,159), while the district-by-visa table prints no 창원시
line and 2,160 for 마산합포구, so `visa_by_sigungu` has no 2015 창원시 row and its
마산합포구 holds one person more than `nationality_by_sigungu`'s. And the
district-by-visa table prints a 화성시 동부출장소 line (1 person, added to 화성시) that
the district-by-nationality table does not print: that table holds the person only in
its 경기도 소계, which is the one person `nationality_by_sigungu` falls short of the
national total in 2015.
`summary_by_sigungu.registered_foreigners` agrees with `nationality_by_sigungu`. The
gap against the `stay` rows is a different quantity again.

## What the yearbook publishes and this deposit does not carry

Stated so a user knows what to go to the source for. The yearbook has 34 tables
in its 2024 edition and this deposit builds on eleven of them.

- **Undocumented residents.** The yearbook counts them by the status the
  person entered on, 2014 onward, and by duration of overstay, sex and
  continent. This deposit does not carry any of it. The dashboard does, at
  <https://immigrantsinkorea.today/h-undocumented.html>, built from the same
  yearbook sheets. There is no district detail in any year.
- **Marriage migrants at district level with a status breakdown** (3장 Ⅰ_2),
  published for 2017, 2018 and 2020 to 2025, with 2019 missing from the source.
  The `marriage_migrants` column of `summary_by_sigungu` is the MOIS survey
  measure of the same population and covers every year, so this deposit carries
  that and not the Ministry of Justice split.
- **Student detail** (2장 Ⅳ), which breaks D-2 into its sub-statuses by
  nationality. The `students` column of `summary_by_sigungu` carries the count.
- **Entries and exits, landing permits, vessels and crew, visa issuance**
  (chapter 1), and **short-stay foreigners** (2장 Ⅲ), which are movement and
  short-visit statistics rather than the resident population this deposit is
  about.
- **Residence reports by Korean citizens abroad** (재외국민 거소신고), which sits
  beside the overseas-Korean table in every year. They are Korean nationals and
  outside the scope of a foreign-resident dataset.

## Index definitions
Let $p_i$ be nationality $i$'s share of a district's foreign population, $x_i$ its
local count, $X_i$ its national count, $t_i$ the district population, and $k_i$ the
Korean count.

- **Foreign share** $= \dfrac{\text{registered foreigners}}{\text{resident population}}\times 100$.
- **Shannon H** $= -\sum_i p_i \ln p_i$ over nationalities (within foreigners).
- **Shannon H (inclusive)** = same entropy with Koreans added as one group.
- **Continent H (visible diversity)** = Shannon H over world regions, Koreans counted as East Asian; higher when groups from other continents are present.
- **HHI** $= \sum_i p_i^2$.
- **index_base_k** = the number of categories the diversity indices above are
  computed over, all five of them (Shannon H, the inclusive H, continent H, HHI and
  evenness) at every level: those of the year's national top 19 nationalities that are present
  in the unit, plus one residual bin. Every unit is scored against the same national
  top 19, so the series stay comparable across years; the value is at most 20 and
  describes the index basis, not the unit. It is 20 for the country in every year and
  for every province from 2009; in 2008 two provinces lack one of the national top 19
  (전라북도 and 제주특별자치도, 19). The province rows of 2006-2007, which have no
  district table, are computed over the five nationalities the province table names
  plus its Other column, so 6. It is below 20 for the districts that lack some of the
  national top 19 (58 of the 250 in 2024).
- **n_nationalities_observed** = how many distinct nationalities the source lists
  for that unit and year, with the residual bin and every line that names no
  country (무국적, 미등록국가, 기타, 국적불명, 국제연합, 국제연합전문기구) excluded; a province's count is
  the union over its districts. Capped at 19 through 2013, when the yearbook
  publishes only the top 19 plus a residual at the district level (national: 19 in 2013, 188 in 2014). Comparisons that cross 2014 should stay within one era.
- **Location Quotient (LQ)** = (n_d / resident_pop_d) / (sum_d n_d / sum_d resident_pop_d), on the resident-registry base, NOT the within-foreigner share (the two differ by the ratio of national to local foreign share).
- **Index of Dissimilarity (D)** $= \tfrac{1}{2}\sum_i \left| \dfrac{x_i}{X} - \dfrac{k_i}{K} \right|$ vs Koreans (evenness).
- **Isolation / Korean interaction** $= \sum_i \dfrac{x_i}{X}\cdot\dfrac{x_i}{t_i}$ and $\sum_i \dfrac{x_i}{X}\cdot\dfrac{k_i}{t_i}$ (exposure).
- **Theil multigroup segregation H** $= \sum_i \dfrac{t_i (E - E_i)}{T\,E}$ over Koreans plus each nationality on a uniform top-19+residual basis every year (Korean count = resident_pop, $t_i$ = resident_pop + registered; Reardon & Firebaugh 2002). The dissimilarity / isolation / interaction files use the same Korean count and totals, over every district with a resident population, Sejong included. The rows under a bare city name beside that city's gu (see District (sigungu) units) have none, so Theil H leaves out 3 to 294 people a year in 2009-2015, and the segregation files, which start in 2014, leave out 2014 창원시 (4), 2015 수원시 (2) and 2015 창원시 (1). `region_segregation.total` still counts them; `segregation_by_nationality.national_total` is the sum over the districts the indices use.
- **Ethnic enclave** = $\text{LQ} \ge 2$ **and** a single nationality $\ge 30\%$ of the sigungu's foreign population **and** at least 200 registered foreigners of that nationality in the district (Wilson & Portes 1980; Logan, Zhang & Alba 2002). The floor keeps a nationally rare nationality from being flagged on a handful of local residents. Each row of `ethnic_enclaves.csv` is one district × nationality pair, so a district can hold more than one enclave and `n_enclaves` counts pairs, not districts. Flags are computed on the nationality detail the source publishes each year (top-19-plus-residual for 2008-2013, full detail from 2014); the residual 기타 (Other) category and the other columns that name no nationality (무국적, 미등록국가) are never flagged, and `national_annual.n_enclaves` equals the per-year row count of `ethnic_enclaves.csv`. Year-over-year enclave comparisons should stay within one era or track a single nationality.

## Language demand (how it is built)
No Korean source records the first-language distribution of the foreign-resident
population, so `language_demand` is derived. Each nationality's count is split
across languages by that country's first-language (L1, mother-tongue) speaker
shares from the Ethnologue 24th edition (SIL Global, 2021), so a nationality
contributes fractionally to every language spoken in its country of origin (e.g.
India splits across Hindi, Bengali, Telugu, Tamil, Marathi and others; Pakistan
across Punjabi, Pashto, Sindhi and Urdu). Three rules shape the result:
- **Korean is excluded.** The file estimates foreign-language interpretation and
  translation demand, so nationalities whose L1 is wholly Korean (e.g.
  Korean-Chinese) contribute nothing. The two other Korean-diaspora labels, which
  Ethnologue does not list, take the language of the country of residence:
  한국계러시아인 Russian and 한국계미국인 English.
- **Major dialect variants are merged into a parent language** (e.g. the Karen
  varieties to Karen, the Chin varieties to Chin), while distinct minority languages
  are kept individually so smaller languages surface on their own.
- **One rounding.** A language's estimate is the sum over nationalities of count x
  share, rounded once, half up, to whole persons. A language is kept only when that
  sum, before rounding, reaches one person: a sum of 0.5 to 0.999 is dropped, although
  rounding alone would show 1. The refugee language file follows the same rule. Every row of every scope re-derives exactly from the released nationality
  counts and `language_weights.csv` (`validate_release.py` on GitHub does it).

`scope` is `national`, `sido` (added in v1.2.0) or `sigungu`: national and sido
rows keep every language, sigungu rows keep the 20 languages with the largest
estimate in each district (ties broken by the Korean label). The three
scopes share the recipe but not the population basis: national rows are computed
from the published national staying-foreigners composition
(`nationality_national`, `population='stay'`), while sido and sigungu rows are
computed from the registered district-assigned tables (`nationality_by_sido`,
`nationality_by_sigungu`). The scopes are therefore not nested sums: the
national rows cover a broader population than the subnational rows, and sido
rows are not sums of the truncated sigungu rows. The build is reproducible from the country to
language share table produced by the build code on GitHub
(`02_language_reference.py`; see https://github.com/nariyoo/kird-korea-immigration).

`language` is the Korean label and `language_en` the English one. Every language of
the district scope, and every language that reaches 500 estimated speakers at the
national or province scope in some year, has a Korean label (a transliteration of the
Ethnologue name under 외래어 표기법 where Korean has no settled name). The long tail
of small languages keeps the Ethnologue English name in both columns; the data
dictionary gives how many and what share of the estimated speakers they hold.

## Harmonization & validation
KIS yearbook Excel layouts change ~6 times across 2006-2024; country names,
visa sub-codes, and province/district names are harmonized across years. Nationality
labels that early yearbooks render with fixed-width spacing (e.g. `중      국`) are
collapsed to their standard form (`중국`). Three MOIS source errors are corrected:
`청순군` → `청송군` and `충청북도 충주시` → `충주시` in the 2024 sub-district sheets
(verified against the same units in MOIS's own district-level sheets), and the 2014
평창동 (서울 종로구) `broad_total`, printed as 505 where the row's own sex split
(265 + 357), its component identity, and its printed population share all give 622.

Validation against published official MOJ totals: the national registered-foreigner
count equals the grand total the yearbook prints, to the person, in every year
2006-2024, and so does the staying-foreigner (체류) count, each year read from the
edition's own nationality x status table (for 2006-2010 the table 2장 Ⅱ, which the
build also checks against the registered, short-term and residence-report tables,
status by status). `code/check_published_totals.py` holds the build to this.
Two source quirks are handled: (1) 2007-2008 yearbooks list a category total
alongside its full sub-code breakdown for some statuses (e.g. D-3); exact
duplicates are removed by anchoring to each file's grand-total row; (2) the
2006-2010 editions print the staying population twice, whole (2장 Ⅱ) and in three
parts (등록, 단기, and 외국적동포 거소신고 in a later chapter); the release reads the
whole table, because the residence-report part books the F-4 holders under a coarser
nationality. Resident population totals match MOIS (49.0M in 2006, peaking at 51.8M in 2019 and 51.2M in 2024).

The denominator (`resident_pop`) is the MOIS resident-registration population
(내국인 주민등록인구), the **same value** used for `foreign_share_pct`
and every derived index, so a user reproduces the foreign share exactly as
`registered_foreigners / resident_pop`. It is present for every district and year
and was verified against the published MOIS figure (e.g. Yeongam-gun 51,391 in
2024), with no district exceeding a 100% foreign share. `foreign_share_pct` is
blank only where the MOJ source carries no district-level registered count:
2006-2007 (the yearbook publishes no sigungu breakdown those years) and a few
dissolved-unit rows whose MOJ counts were folded into their successor (below).

### District (sigungu) units
The district level follows the units the MOJ yearbook publishes, about 247-250 per
year: the autonomous gu (자치구) of the metropolitan cities, the counties (군), the
cities without general districts, **and** the general districts (일반구) of large
cities, which the source reports separately (e.g. 안산시 단원구, 고양시 일산동구,
창원시 마산합포구). A high-foreign-share general district such as 안산 단원구 (13%
foreign in 2024) is therefore kept distinct from its city, preserving the spatial
detail residential-diversity and segregation research needs. `summary_by_sigungu`
carries one row per such unit per year, and its registered counts sum exactly to
the national MOJ total (no double-counting; the one exception is a person in 2015,
see Levels and how they aggregate). Pure renames and same-boundary
promotions are carried under **one continuous label**: 인천 남구 as 미추홀구, 당진군 as
당진시, 여주군 as 여주시. Genuine boundary changes are **not** collapsed: 마산시 and pre-merger 창원시 appear
as separate units through 2009 (진해시 is carried as 창원시 진해구, the gu on its ground,
from 2008), and the
four post-merger Changwon gu appear from 2010; 세종특별자치시 runs as a province from 2012 while the
district 세종시 runs from 2008 on the pre-2012 territory (no 연기군 row exists);
청주시 청원구 likewise runs from 2008: through 2013 it is the county 청원군, under
청원군's own code of those years (43710), and from 2014 the merged city's gu of that
name (43114), which is not the same ground (the 2014 merger spread the old county
over all four gu), so no 청원군 row exists either; the residual lines some later editions still print under 청원군,
당진군, 연기군 or 여주군 are carried on the successor, as are a 포천군 line in 2009
(1 person), 진해시 lines in 2011 and 2012 (1 each, carried on 창원시 진해구) and
마산시 lines in 2013 and 2014 (2 and 1, carried on the 창원시 line described next);
`crosswalk_region` has a rule row for every such name. Sub-office (출장소) lines
are added to their city: the yearbook counts 화성시 동부출장소 apart from the 화성시
line (1,709 people in 2014). Some editions also print a line under the bare name of
a city beside that city's own general districts: 용인시 in 2008-2011 (14, 142, 33
and 3 people), 창원시 in 2010-2015 (261 in 2010, 1-5 later), and 1-15 people under
고양시, 성남시, 안양시, 천안시, 청주시 or 수원시 in 2009-2015. This line is not the
city's total: the province 소계 and the grand total count it on top of the gu rows.
It holds people the yearbook places in the city and in none of its gu, and it is a
district row of its own under the city's name and code (21 district-years), with
no resident population, share, broad-definition columns or LISA class. The
2015 district-by-visa table prints no 창원시 line (its 마산합포구 line holds that
person), so `visa_by_sigungu` carries 20 of the 21. The MOIS broad-definition layer is
published at the general-district (gu) level from 2016; for 2008-2015 it is reported
at the city level for general-district cities and is apportioned to the gu by each
gu's share of the city's MOJ registered foreigners, so the panel stays at a single
grain. Apportioned rows carry `broad_apportioned = True` so they can be excluded or
down-weighted; directly published rows carry `False`, and so do the city lines above,
which have no MOIS columns and nothing apportioned, so the column is never blank. In the years MOIS (counting as
of 1 January) and MOJ (31 December) fall on either side of a merger, each MOIS row
goes to the units on its own ground: in 2010 the old 마산시 to 창원시 마산합포구 and
마산회원구 and the old 창원시 to 성산구 and 의창구, each apportioned between its two,
and 진해시 to 진해구 whole; in 2008-2013 청주시 to 청주시 상당구 and 흥덕구, and 청원군
whole to the row that carries it, 청주시 청원구; in 2014 청주시 and 청원군 together to
the merged city's four gu. The CSV holds the literal words
`True` / `False`, which pandas reads as a boolean column; filter with
`df[df.broad_apportioned == True]`, not on the string `'TRUE'`.

**The province of a district.** Two rules place a district in a province, one for
each kind of file. The district files (`summary_by_sigungu`, `nationality_by_sigungu`,
`visa_by_sigungu`, the `sigungu` scope of `language_demand`, `ethnic_enclaves`,
`children_by_age`, `multicultural_households`, `summary_by_eupmyeondong`) put every
district under the province it belongs to in 2024, in every year, so that a district
keeps one `sido` and `sigungu` label across the panel. Two districts are affected.
군위군 moved from 경상북도 to 대구광역시 on 1 July 2023; the district files carry it as
대구광역시 군위군 with `sido_code` 27 in every year, while its `sigungu_code` is the
code of that year (47720 through 2022, 27720 from 2023). 세종시 is carried as
세종특별자치시 세종시 from 2008; for 2008-2011, before the province existed, its
`sido_code` is blank and its `sigungu_code` is 44730. The province files
(`summary_by_sido`, `nationality_by_sido`, `visa_by_sido`, the `sido` scope of
`language_demand`, `diaspora_residence_by_sido`) count a district in the province it
belonged to that year, which is the province named by the first two digits of its
`sigungu_code`: 군위군 in 경상북도 through 2022 and 세종시 in 충청남도 through 2011, so
there is no 세종특별자치시 province row before 2012. To add a district file up to a
province file, group on `year` and the first two digits of `sigungu_code`, not on
`sido`; grouping on `sido` moves 군위군's people from 경상북도 to 대구광역시 for
2008-2022 (576 registered foreigners in 2015) and creates a 세종특별자치시 total for
2008-2011. Province names are one fixed set: 강원도 and 전라북도 keep those names after
the register renamed them 강원특별자치도 (2023) and 전북특별자치도 (2024), and
`sido_code` follows the register (42 to 51, 45 to 52). `crosswalk_region` lists each
rule.

The broad-definition layer is **additive across levels**: each old-name or merged
district that the panel canonicalizes (인천 남구 → 미추홀구, 당진군 → 당진시, 여주군 →
여주시, 경북 군위군 → 대구 군위군, 청원군 → 청주 청원구, 마산시/진해시 → 창원 gu) has its
MOIS broad counts folded onto the successor district at the same grain, so the
district values sum to the province and national totals exactly when each district
is counted in the province it belonged to that year (see The province of a district;
the apportioned general districts split each city column by the largest-remainder
rule, so they add up to it). The **sido** level follows the official province boundaries of
each year, which the sido diversity indices also use: 세종특별자치시 became a province
only in 2012, so its 2008-2011 residents are carried under 충청남도, and 군위군 is
carried under 경상북도 through 2022. The **sigungu** panel keeps 세종시 and 군위군 as
continuous units under their 2024 province; the national total counts these
residents exactly once.

### Sub-district (eup/myeon/dong)
Dong boundaries are redrawn almost every year (dongs split, merge, and rename),
so each year's `summary_by_eupmyeondong` rows sit on that year's own boundaries
and carry that year's official administrative-dong code (`adm_code`: 7-digit for
2014/2015/2017, 10-digit standard codes for 2016 and 2018+, from the
vuski/admdongkor yearly snapshots). To attach the code, MOIS dong names are
matched to that year's boundary set after light normalization: separators
stripped, the 제N동 → N동 form unified, a city-or-gu prefix removed only when it is
a real gu of that city (so 압구정동 and 반구1동 are not mis-split), 면/읍 class
swaps, and known renames mapped (e.g. 원남면 → 매화면, 서면 → 금강송면, 중부면 →
남한산성면). The share of each year's dong rows that match a boundary code is 96.5% in 2014, 97.9% in 2015, and 99.7% or more in every later year (100% in 2016-2019 and 2022-2024). Within a year no two rows share an `adm_code`, and every dong code falls inside its district's code block, so the code is safe as a one-to-one GIS join key. A code is never guessed: where a dong name is not unique within its province and the district did not match, the cell is left blank rather than filled from a same-named dong in another city.

The 2014 edition prints the sub-districts of the cities with general districts under
the city alone, and each is placed in its gu by that year's boundaries. Three of 창원시's
share the name 중앙동; the sheet lists them in the gu order (성산구 1,104, 마산합포구 94,
진해구 55), and the same edition's household and naturalized-resident sheets print
them with their gu, so each is carried in its own gu. The same edition prints two branch-office
lines under 인천 중구 (영종출장소중산지소 59, 용유출장소무의지소 11); they are carried as
sub-district rows with a blank `adm_code`. Eight rows that
existed only in the edition's separate household table (sheet 6: 영종출장소,
장봉출장소, …) and carried no value in any column are gone; that table is not the one
this file carries.

Known limitations:
- `resident_pop` is present for every district and year and equals the denominator
  used for `foreign_share_pct`, and the district-summed registered total matches the
  national MOJ total exactly in every year but 2015 (one person). District-level MOJ
  counts begin in 2008 (the yearbook publishes no sigungu breakdown for 2006-2007).
  MOIS does publish its broad-definition count by district for 2006 and 2007;
  `summary_by_sigungu` does not carry those two years, because its unit list is MOJ's,
  which starts in 2008, and MOIS prints the cities with general districts whole, with
  no district count to divide them by. The two years are in `summary_by_sido`, summed.
- The MOIS broad-definition layer is at the general-district (gu) level only from
  2016; for 2008-2015 it is reported at the city level for cities with general
  districts and is apportioned to the gu by MOJ registered-foreigner share, so those
  early-year gu values for the broad-definition composition are estimates (flagged
  `broad_apportioned = True`). Backcasting the rule on 2016-2019, where the true gu
  values are published, gives a median absolute error of 4.9% (90th percentile
  13.1%); allocation by resident population, the obvious alternative, errs by a
  median of 20.4% because foreign residents sort within cities far more unevenly
  than the total population.
- The MOIS broad-definition composition before 2009 uses an earlier category
  scheme. `naturalized` for 2007-2008 is the sum of the published 혼인귀화자 +
  기타귀화자, and `non_naturalized` (no published subtotal before 2009) is recovered
  through the source identity broad_total = non_naturalized + naturalized + children.
  Categories the source did not publish those years are blank: `students`
  (2006-2007), `ethnic_koreans` (2006-2008; until 2008 ethnic-Korean foreign
  nationals are counted inside `other_foreigners`, so pre-2009 `other_foreigners`
  is broader than the 2009+ category), and `other_foreigners` (2006). Where
  `students` is unavailable, `study_dependence_pct` and `settlement_type` are
  blank as well. In 2006 (`summary_by_sido` only) `marriage_migrants` is the
  source's 국제결혼이주자 group total, which includes that group's children, the
  same children `children` counts (Seoul: 19,848 = 2,719 men + 12,255 women + 4,874
  children), so the two columns overlap that year and should not be added; from
  2007 they are disjoint, and 2006's `marriage_dependence_pct` counts the children
  too.
- **Masked cells.** From 2016 MOIS masks every count under 5 (`***` in 2016, `*`
  after). A masked cell is carried wherever the cells the sheet prints fix it exactly,
  through the identities the sheet itself publishes. Within a row, a total is the sum
  of its parts: `broad_total` = `non_naturalized` + `naturalized` + `children` and
  `non_naturalized` = its five types; in `multicultural_households` 합계 = the four
  member groups and each two-part group = its parts; in the age sheet behind
  `children_by_age` a district's total = its nineteen single ages. Across rows, a row
  with rows printed under it is their sum, column by column: the nation over its
  provinces, a province over its districts, a city over its general districts, a
  district over its sub-districts. Every identity left with one masked cell settles
  it, and the passes repeat until none does, so a cell one identity settles can settle
  the next. The rule is the same for every unit, level and file. No settled value
  falls below 0 or above 4, and every identity whose cells are all printed holds, in
  every edition 2016-2024. A cell nothing fixes is blank (a row absent, in the long
  files), and so are the dependence rates and `settlement_type` that need it.
  `summary_by_sigungu` and `summary_by_sido` gain none: the district rows' own
  identities already fix every masked cell they have (524 in 2016-2024), and the
  province rows print none. `code/check_published_totals.py` settles the four sheets
  again with code of its own and holds every released cell of 2016-2024 to the
  result.
- At the eup/myeon/dong level the MOIS source suppresses or omits some
  sub-composition cells, so the component columns (`workers`, `marriage_migrants`,
  `students`, …) can be blank and need not sum to `non_naturalized` or `broad_total`.
  A blank is an unreported value, not a zero. Every sub-district MOIS prints has a
  row: where it masks the row's own total (합계) and with it every cell, the district
  row fixes that total (31 sub-district-years in 2016-2024, none in 2014-2015).
- `children_by_age` carries a masked age wherever the printed cells fix it (see
  Masked cells): 633 cells of 2016-2024, 177 fixed by the district's own total and 456 more by its city's or its province's row. An age nothing fixes (595 cells of 2016-2024, none in
  2023), or one the sheet does not print (it leaves out some ages with no children,
  e.g. 2014), has no row. 울릉군 (Ulleung-gun, 47940), whose every printed age is masked, has the 9 to 19 ages a year its
  province's row and its own total fix, and its children total (19 to 29 a year) is in
  the `children` column of `summary_by_sigungu`. 부천시 is one district in every year of that file, as in every
  other district file: its three general districts, re-created in 2024, are summed.
- 2005 excluded (irregular source format with prior-year reference columns).

### Where blank cells appear, and why
Every blank in the data is an explained, intentional gap:
- `language_demand` `sido`/`sigungu` (+`_en`) are blank on the `national`-scope rows, and `sigungu` is blank on the `sido`-scope rows
  by design (those rows are not tied to a district).
- `national_annual` carries every index for 2008 except `theil_segregation_H`,
  which begins in 2009 because the 2008 nationality basis folds Korean-Chinese into
  China and the multigroup index is not back-computed onto it. `ethnic_koreans` is
  also blank in 2008, the year MOIS did not publish that component.
- The three naturalization files have no blank cells. `naturalization_by_country`
  and `naturalization_by_age` carry each edition's table as a full grid, one row per
  printed row and processing type, so a zero is a row with `n` = 0 in every year: the
  2019, 2020 and 2024 by-country tables and the 2019, 2020, 2023 and 2024 by-age
  tables leave those cells empty where the other editions print 0, and each such
  row's printed total equals the sum of its printed cells. They do mix totals with
  their own components: `귀화소계` equals `간이귀화 + 일반귀화 + 특별귀화 + 수반취득`
  to the person in every year the four routes are published (from 2014 in
  `naturalization_by_country`, from 2015 in `naturalization_by_age`, whose 2014
  edition prints the subtotal alone). Summed over countries or ages, `귀화소계`
  (`귀화` before 2014) equals `naturalization_annual`'s `귀화` in every year 2011-2024;
  the one exception is `naturalization_by_age` 2012, whose edition prints 10,539
  against the annual series' 10,540. 국적회복, 국적판정 and 국적이탈 equal the annual
  series in every year in both panels. The other types differ in 11 cells, each
  traced to the raw editions, because the annual series is the newest edition's
  trend table, which MOJ revises, while each panel year is that year's edition:
  2018 in both panels (국적보유 86 against 89, 국적상실 26,608 against 26,607,
  국적선택 1,714 against 1,719, 국적취득(인지) 504 against 506), 2012 in
  `naturalization_by_age` (국적상실 17,642 against 17,641), and 2013 in both panels,
  whose `국적취득` column holds re-acquisition only (419) without the 343
  acquisitions by recognition the annual series adds. The panels start in 2011
  because no earlier edition gives a single year: the 2006, 2007, 2009 and 2010
  editions print their by-country and by-age tables cumulatively, from 1991 to the
  edition year (242,374, 278,713, 363,131 and 405,170 cases against 31,069, 36,339,
  49,820 and 42,039 in the year itself), and the raw inputs hold no such table of
  the 2008 edition. Age bands are read from each row's
  own label; the editions that print bare numerals (10, 20, ... 99) give each band's
  upper bound, as the editions with explicit labels (0세~9세 ...) confirm. In `naturalization_by_country`, `중국` never includes
  `한국계중국인`: the 2017 edition prints China "한국계 포함" and the Korean-Chinese
  row beside it, and the subgroup is taken back out (China 3,260, Korean-Chinese
  1,521 naturalizations; the 2017 split is out of line with other years, as MOJ
  printed it). The 2018 edition prints China and Russia with their Korean-descent
  subgroups folded in and no split, so 2018 carries the combined units
  `중국+한국계중국인` and `러시아(연방)+한국계러시아인`. `한국` appears only under the
  nationality-status types (people resolving a Korean nationality they already held).
  The by-country and by-age panels carry the all-routes type from 2014, when the
  editions first split 귀화 into routes; before that the type is `귀화`. `국적취득` sits beside
  `국적취득(인지)` and `국적취득(재취득)`. Select one type level before summing, as
  with `category_level` in `multicultural_households`.
- In `summary_by_sigungu`, `ethnic_koreans` is blank for every district in 2008,
  the year MOIS did not publish that component. The renamed and reassigned units
  (인천 미추홀구, 충남 당진시, 경기 여주시, 대구 군위군) carry a full 2008-2024 MOIS
  composition on the successor name, with no other blank.
- In `summary_by_sido` / `summary_by_sigungu`, the pre-2009 MOIS categories the
  source did not publish are blank (see Known limitations), and
  `study_dependence_pct` / `settlement_type` are blank wherever `students` is
  unavailable.
- See above for the pre-2009 MOIS composition and the eup/myeon/dong
  sub-composition suppression.
