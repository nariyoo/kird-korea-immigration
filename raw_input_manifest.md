# Raw input manifest

The raw sources are public and are not redistributed with this deposit. This
manifest lists every file the pipeline reads, with its size and SHA-256, so a
reproducer can confirm they have the same files. Download pages are the
publisher's own; the yearbook editions are the per-year archives on the KIS
statistics page. Each row gives the folder under the project root
(`location`: `01_raw_data`, or `05_dashboard/data` for the boundary files) and
the path inside it; `run_pipeline.py` expects them there.

| folder | source | publisher | files | download |
|---|---|---|---|---|
| `05_dashboard/data` | District (sigungu) and sub-district (eup/myeon/dong) boundaries, GeoJSON; sub-district vintages 2014-2024 from the vuski/admdongkor snapshots of Statistics Korea SGIS boundaries | Statistics Korea (SGIS); Ministry of the Interior and Safety | 12 | <https://github.com/vuski/admdongkor> |
| `ethnologue global dataset` | Ethnologue Global Dataset, 24th edition (licensed; not redistributed) | SIL International | 10 | <https://www.ethnologue.com/product/global-dataset/> |
| `kosis` | KOSIS regional statistics tables (dashboard context layers only; no released file uses them) | Statistics Korea | 7 | <https://kosis.kr/> |
| `refugee_statistics` | Refugee status determination statistics | Ministry of Justice, Korea Immigration Service | 25 | <https://www.immigration.go.kr/immigration/1570/subview.do> |
| `공공데이터포털` | MOJ undocumented foreign residents by year (법무부_불법체류 외국인 현황, dataset 15112636) | Ministry of Justice, via the Public Data Portal | 3 | <https://www.data.go.kr/data/15112636/fileData.do> |
| `주민등록인구 현황` | Resident registration population statistics | Ministry of the Interior and Safety | 7 | <https://jumin.mois.go.kr/> |
| `출입국통계연보` | Korea Immigration Service Statistical Yearbook | Ministry of Justice, Korea Immigration Service | 950 | <https://www.immigration.go.kr/immigration/1570/subview.do> |
| `한국교육개발원_유학생` | International student statistics | Korean Educational Development Institute (KEDI/KESS) | 35 | <https://kess.kedi.re.kr/> |
| `행정안전부 외국인주민통계` | Broad-definition foreign resident statistics (외국인주민현황) | Ministry of the Interior and Safety | 25 | <https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardList.do?bbsId=BBSMSTR_000000000014> |
| `행정표준코드` | Statutory administrative code register (법정동코드) | Ministry of the Interior and Safety, Korean Administrative Standard Code | 3 | <https://www.code.go.kr/stdcode/regCodeL.do> |

Total: 1077 files, 373 MB. Per-file checksums are in
`raw_input_manifest.csv`.
