# Code

The build and analysis code behind KIRD, for the "Code availability" section. It
documents the harmonization, the index computation, and the export. The raw
government source files and the intermediate products are not redistributed here,
so the scripts do not run end to end from a bare checkout; the authoritative
outputs are the CSVs deposited on openICPSR.

## Layout

Ten steps, numbered in run order, in three phases. Phase 1 (`01`-`05`) turns the
raw yearbooks into the harmonized panel; phase 2 (`06`-`09` plus the two figure
steps) turns that into the released tables and the repository figures; phase 3 (`10`) stages the openICPSR deposit and runs on demand.
The steps read and write the intermediate JSON and CSV in place, so the order is
the number in the filename. The unnumbered files are the shared module, the runner, the checkers and helpers the sections
below describe, and `requirements.txt`.

```
python run_pipeline.py              # phases 1 and 2
python run_pipeline.py --phase 1    # raw yearbooks -> dashboard JSON
python run_pipeline.py --phase 2    # dashboard JSON -> released CSVs
python run_pipeline.py --phase 3    # released CSVs -> deposit, on demand
python run_pipeline.py --from 08_export_dataset.py   # resume at a step
```

`run_pipeline.py` holds the step list and is the contract: a script that is not in
it is not part of the build. Paths come from `kird.py`, which finds the
project root from its own location and accepts a `KIRD_ROOT` override:

```
KIRD_ROOT=/path/to/KIRD python run_pipeline.py
```

Install with `pip install -r requirements.txt` (Python 3.10+).

## Shared module

`kird.py` holds everything the steps import: the paths, resolved from the project
root; the reference tables (`COUNTRY_CANONICAL`, `COUNTRY_REGION`,
`COUNTRY_LANGUAGE`, `LANG_EN_KO`, `SIDO_EN`, `SIDO_EN_SHORT`); the index
formulas (`shannon`, `incl`, `cont`, `hhi`, `pielou`, `make_record`, `morans_i`);
and the per-year administrative-code layer. Every step imports the same tables
and the same formulas, so a district in 2009 and the same district in 2019 are
measured identically. `SIDO_EN` and `SIDO_EN_SHORT` differ on purpose: the
released files romanize the provinces with the -do suffix (Gyeonggi-do) and the
dashboard uses the short English form (Gyeonggi).

The administrative-code layer is what puts `sido_code` and `sigungu_code` on the
released tables. It reads the 행정안전부 법정동코드 register kept in
`01_raw_data/행정표준코드/` and gives a province or district name the code the
government used on 31 December of the row's year, following the register's own
생성일 / 폐지일 plus a declared lineage for the successions that changed a code
(인천 남구 to 미추홀구 in 2018, 군위군 from 경상북도 to 대구광역시 in 2023,
청원군 into 청주시 in 2014, 진해시 into 창원시 in 2010). A name the register
cannot resolve leaves the cell blank and is reported; no code is ever invented.
The module also runs from the command line:

```
python kird.py                 # the resolved paths
python kird.py --fetch-codes   # download the 법정동코드 register from code.go.kr
python kird.py --code-table    # rebuild the year-by-year code table as JSON
python kird.py --admin2024     # rebuild the 2024 boundary anchor table
```

## Steps

Each step is one stage of the build and holds every section of it; the section
functions inside a step run in the order the `__main__` block lists them.

| Step | What it does |
|---|---|
| `01_parse_yearbooks.py` | The core parser. Reads every MOJ yearbook, harmonizes 2006-2024 across nationality names, visa sub-codes and province and district names, composes the 2006-2010 staying totals as 등록 + 단기 + 거소신고, removes the 2007-2008 category-total duplicates, and checks the national aggregates against the published totals. |
| `02_language_reference.py` | The language reference tables: the Korean/English label map, and the Ethnologue 24 first-language shares by country. Everything that touches language reads these, so they come first. |
| `03_extend_panel.py` | The panel, extended: local Moran clusters onto every district-year, the province series back to 2006 with its diversity columns, the national series (undocumented residents, national language demand), one label per country with the language series recomputed on the merged names, the district-by-visa panel, refugee language demand, and the 2008-2013 district and age backfills. |
| `04_reconcile_districts.py` | Boundary changes reconciled onto one label per district, every index recomputed on the reconciled set, all of it put on a top-19-plus-residual basis so the 2013/2014 coverage break does not read as a change in the distribution, and the language block trimmed to the released top 20 per district. |
| `05_mois_layer.py` | The MOIS tables (행정안전부 외국인주민통계, a broader population definition than MOJ): join keys, the administrative codes on them, the cross-check against the MOJ counts, assembly, the Sejong patches, and packaging as CSV and Parquet. The parsers for the nineteen raw 행정안전부 editions are in the same file, under `python 05_mois_layer.py --reparse`; the pipeline does not call them, because their output changes only when a new edition is published. |
| `06_build_summaries.py` | The per-level summaries on the MOJ district grain of roughly 250 districts a year, the MOIS-only sub-district summary with that year's official code, and the four MOIS CSVs. |
| `07_build_naturalization.py` | Chapter 4 of every edition into the three nationality-processing panels, each checked against the separately published annual totals. |
| `08_export_dataset.py` | The tidy release CSVs, then `language_demand.csv` on the released basis over the draft the export writes. It also audits the English district names in the boundary file before writing anything, since `sigungu_en` is copied out of that file verbatim; `python 08_export_dataset.py --check-names` runs that audit on its own. |
| `09_finish_release.py` | The single authority for the released schema, the segregation files recomputed over all districts, the bilingual dictionary asserted against the files present, one labeled Stata `.dta` per table, and the integrity audit, which must end `AUDIT CLEAN`. |
| `10_stage_deposit.py` | The openICPSR deposit: the two refugee files (a cumulative 1994-2024 snapshot, since MOJ publishes refugee outcomes by nationality only cumulatively), the wide summary variants with every place-keyed breakdown pivoted to one column per category, and the deposit gate over the result. |

Between 08 and 09, `run_pipeline.py` renames the five working-name exports to
their released names and deletes every working-name intermediate, because the
dictionary in step 09 asserts that it documents exactly the files it finds.

## Where the panel ends

Two cut-offs, both in `kird.py`.

| constant | what it bounds |
|---|---|
| `LAST_YEAR` | How far the raw yearbooks are read. The public dashboard shows this much. It is the last year the Ministry of Justice has published. |
| `RELEASE_LAST_YEAR` | Where this dataset and the deposit end. It is the last year the Ministry of the Interior and Safety has also published. |

The two ministries publish on different schedules. The dashboard can show a year
that has MOJ counts alone; a released row for that year would carry the
broad-definition columns empty, so the dataset stops one year earlier. Steps 01
through 08 build everything to `LAST_YEAR`; `run_pipeline.cut_release_years()`
then drops every row past `RELEASE_LAST_YEAR` from the release folder in one
pass, before step 09 recomputes the indices and audits them. Every index is
computed within a single year, so cutting afterwards leaves the remaining years
unchanged. When MOIS catches up, raise `RELEASE_LAST_YEAR` and rebuild.

## Checks you can run on the released data

| script | what it does |
|---|---|
| `validate_release.py` | Re-derives every published index from the published counts, using the deposited CSVs alone. It reads either layout: the flat release folder, or the deposit's `data/` plus `data/detailed_data/`. Point it at the folder you downloaded. |
| `check_published_totals.py` | Reads the grand-total cell printed in each yearbook and compares it with the national totals in `visa_national.csv`, year by year, for registered and for staying foreigners. This is the check behind the reconciliation figures quoted in the descriptor. It needs the raw yearbooks. |
| `build_raw_manifest.py` | Writes the list of raw input files with size and SHA-256, so a file you download can be checked against the one used here. |
| `crosswalks.py` | Writes the harmonization rules out as tables: which source spelling became which standard label, and why. |

## Released filenames

| working name | released name |
|---|---|
| `foreign_residents_by_visa.csv` | `visa_by_nationality.csv` |
| `foreign_residents_by_sigungu.csv` | `nationality_by_sigungu.csv` |
| `foreign_residents_by_sigungu_visa.csv` | `visa_by_sigungu.csv` |
| `foreign_residents_by_age_sex.csv` | `age_sex_national.csv` |
| `national_summary_annual.csv` | `national_annual.csv` |

The standalone denominator and index tables (`resident_population_by_sigungu`,
`indices_by_sigungu`, `indices_by_sido`) are no longer released separately; their
columns are folded into the `summary_by_*` files, one row per place and year.

## Scope of this bundle

This bundle holds the code that produces the deposited data. The working copy
also carries scripts that write only into the dashboard, among them the KEDI
international-student series, the refugee dashboard panel, the sub-district
boundary joins with their geocoder, and the script that writes this bundle. None of those produces a deposited file, so none is published
here.

## Inputs

Public government source files. They are not redistributed here.

- Ministry of Justice, Korea Immigration Service Statistical Yearbooks (2006-2024)
- Ministry of the Interior and Safety, Local Government Foreign Resident Status (2006-2024)
- Ministry of the Interior and Safety, Resident Registration Population (the denominator)
