# Licensing

This repository carries three sets of terms, because it holds three kinds of thing.

| What | Terms | Text |
|---|---|---|
| Code in `code/` | MIT | [`../LICENSE`](../LICENSE) |
| `README.md`, `code/README.md`, `data_dictionary.csv`, `figures/` | CC BY 4.0 | [`CC-BY-4.0.txt`](CC-BY-4.0.txt) |
| The Pretendard typeface in `code/fonts/`, which the figure scripts draw in | SIL Open Font License 1.1 | [`../code/fonts/OFL.txt`](../code/fonts/OFL.txt) |

CC BY 4.0 matches the terms the released tables carry on openICPSR, so the
documentation travels with the deposit under one license. Creative Commons
licenses are not written for software, which is why the pipeline itself is MIT.
The typeface is bundled unmodified so the figures build the same on any machine;
the OFL lets it be redistributed with software but not sold on its own.

## The released tables are not here

The released tables are deposited on openICPSR under CC BY 4.0. Version 1.2.0
holds 28 tables: the 26 that phases 1 and 2 of this pipeline build, and the two
cumulative refugee tables that phase 3 adds when it stages the deposit. The
earlier version 1.1.0, at <https://doi.org/10.3886/E249944V1>, holds 17. This
repository holds the code that builds them and the documentation that
describes them.

## Source material

The panel is built from the annual statistical yearbooks of the Republic of
Korea Ministry of Justice, Statistics Korea, and the Ministry of the Interior
and Safety, and on first-language shares from SIL Global's Ethnologue 24 Global
Dataset, which is licensed under SIL's own terms and is not redistributed. Redistribution of figures derived from those yearbooks follows the
terms each ministry attaches to its own publications; neither the yearbooks nor
any raw extract from them is included in this repository.
