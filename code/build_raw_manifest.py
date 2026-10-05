# -*- coding: utf-8 -*-
"""Build the list of raw inputs (reviewer comment C8).

The raw sources are all public but are not redistributed. Without a list, someone
reproducing the build cannot tell which files to download, from where, or how many.
This script walks `01_raw_data`, records each file's relative path, size and SHA-256,
and puts a list in the release that gives each folder's source and download page.
A downloaded file can be checked against the one we used by its hash.

    python 02_code/build_raw_manifest.py

Output: `04_dataset_release/raw_input_manifest.csv`
        `04_dataset_release/raw_input_manifest.md` (sources and how to get them)
"""
import csv
import hashlib
import io
import os
import re
import sys

# LAST_YEAR, not RELEASE_LAST_YEAR: the build reads the newest yearbook (the 2025
# edition supplies the naturalization trend table and the 2025 dashboard year), so
# the manifest has to list it. Until 2026-09-26 this imported RELEASE_LAST_YEAR
# under the name LAST_YEAR and left the 35 files of the 2025 edition out.
from kird import RAW, RELEASE, LAST_YEAR, ROOT, SITE_DATA

# Inputs the build reads from outside 01_raw_data: the district and sub-district
# boundary files, kept with the dashboard. Found on 2026-09-26 by logging every file
# the pipeline opens; a build from the manifest alone stopped without them.
AUX = {
    "05_dashboard/data": (
        SITE_DATA,
        lambda rel: rel == "korea_sigungu.json" or rel == "korea_emd.json"
        or (rel.startswith("emd_years/") and rel.endswith(".json")),
        ("District (sigungu) and sub-district (eup/myeon/dong) boundaries, GeoJSON; "
         "sub-district vintages 2014-2024 from the vuski/admdongkor snapshots of "
         "Statistics Korea SGIS boundaries",
         "Statistics Korea (SGIS); Ministry of the Interior and Safety",
         "https://github.com/vuski/admdongkor")),
}

YEARBOOK = "출입국통계연보"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# folder -> (source name, publisher, download page)
SOURCES = {
    "출입국통계연보": (
        "Korea Immigration Service Statistical Yearbook",
        "Ministry of Justice, Korea Immigration Service",
        "https://www.immigration.go.kr/immigration/1570/subview.do"),
    "주민등록인구 현황": (
        "Resident registration population statistics",
        "Ministry of the Interior and Safety",
        "https://jumin.mois.go.kr/"),
    "행정안전부 외국인주민통계": (
        "Broad-definition foreign resident statistics (외국인주민현황)",
        "Ministry of the Interior and Safety",
        "https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardList.do?bbsId=BBSMSTR_000000000014"),
    "행정표준코드": (
        "Statutory administrative code register (법정동코드)",
        "Ministry of the Interior and Safety, Korean Administrative Standard Code",
        "https://www.code.go.kr/stdcode/regCodeL.do"),
    "한국교육개발원_유학생": (
        "International student statistics",
        "Korean Educational Development Institute (KEDI/KESS)",
        "https://kess.kedi.re.kr/"),
    "ethnologue global dataset": (
        "Ethnologue Global Dataset, 24th edition (licensed; not redistributed)",
        "SIL International",
        "https://www.ethnologue.com/product/global-dataset/"),
    "refugee_statistics": (
        "Refugee status determination statistics",
        "Ministry of Justice, Korea Immigration Service",
        "https://www.immigration.go.kr/immigration/1570/subview.do"),
    "공공데이터포털": (
        "MOJ undocumented foreign residents by year (법무부_불법체류 외국인 현황, dataset 15112636)",
        "Ministry of Justice, via the Public Data Portal",
        "https://www.data.go.kr/data/15112636/fileData.do"),
    "kosis": (
        "KOSIS regional statistics tables (dashboard context layers only; no released file uses them)",
        "Statistics Korea",
        "https://kosis.kr/"),
    "서울_등록외국인_동별": (
        "Registered foreigners by sub-district, Seoul",
        "Seoul Open Data Plaza",
        "https://data.seoul.go.kr/"),
}

SKIP_EXT = {".tmp", ".lnk"}


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    if not os.path.isdir(RAW):
        raise SystemExit("raw data folder not found: %s" % RAW)
    rows = []
    skipped = []
    for root, dirs, files in os.walk(RAW):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in SKIP_EXT or f.startswith("~$"):
                continue
            if root == RAW:          # notes directly under the raw folder are not data
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, RAW).replace(os.sep, "/")
            top = rel.split("/", 1)[0]
            # Leave out yearbooks for years this release does not use. Even if they
            # were downloaded, the list should answer "what is needed to rebuild
            # this release".
            sub = rel.split("/")[1] if "/" in rel else ""
            m = re.match(r"(" + "[0-9]" * 4 + ")_", sub)
            if top == YEARBOOK and m and int(m.group(1)) > LAST_YEAR:
                skipped.append(rel)
                continue
            name, pub, url = SOURCES.get(top, ("", "", ""))
            rows.append(["01_raw_data", rel, name, pub, url, os.path.getsize(p), sha256(p)])
    for loc, (base, keep, (name, pub, url)) in AUX.items():
        for root, dirs, files in os.walk(base):
            for f in sorted(files):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, base).replace(os.sep, "/")
                if keep(rel):
                    rows.append([loc, rel, name, pub, url, os.path.getsize(p), sha256(p)])
    out = os.path.join(RELEASE, "raw_input_manifest.csv")
    with io.open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        # location: the folder under the project root; path: relative to it
        w.writerow(["location", "path", "source", "publisher", "download_page", "bytes",
                    "sha256"])
        w.writerows(rows)
    print("raw_input_manifest.csv: %d files" % len(rows))
    if skipped:
        print("  LAST_YEAR(%d): %d yearbook files after it left out" % (LAST_YEAR, len(skipped)))

    by_top = {}
    for r in rows:
        key = r[1].split("/", 1)[0] if r[0] == "01_raw_data" else r[0]
        by_top.setdefault(key, []).append(r)
    md = [
        "# Raw input manifest",
        "",
        "The raw sources are public and are not redistributed with this deposit. This",
        "manifest lists every file the pipeline reads, with its size and SHA-256, so a",
        "reproducer can confirm they have the same files. Download pages are the",
        "publisher's own; the yearbook editions are the per-year archives on the KIS",
        "statistics page. Each row gives the folder under the project root",
        "(`location`: `01_raw_data`, or `05_dashboard/data` for the boundary files) and",
        "the path inside it; `run_pipeline.py` expects them there.",
        "",
        "| folder | source | publisher | files | download |",
        "|---|---|---|---|---|",
    ]
    for top in sorted(by_top):
        name, pub, url = SOURCES.get(top) or (AUX[top][2] if top in AUX else ("", "", ""))
        md.append("| `%s` | %s | %s | %d | %s |"
                  % (top, name or "(undocumented)", pub, len(by_top[top]),
                     ("<%s>" % url) if url else ""))
    md += ["",
           "Total: %d files, %.0f MB. Per-file checksums are in"
           % (len(rows), sum(r[5] for r in rows) / 1e6),
           "`raw_input_manifest.csv`.", ""]
    io.open(os.path.join(RELEASE, "raw_input_manifest.md"), "w",
            encoding="utf-8").write("\n".join(md))
    missing = sorted({r[1].split("/", 1)[0] for r in rows if not r[2]})
    if missing:
        print("  folders with no source recorded: %s" % ", ".join(missing))
    print("raw_input_manifest.md written too")


if __name__ == "__main__":
    main()
