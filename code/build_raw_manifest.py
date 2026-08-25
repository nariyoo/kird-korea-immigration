# -*- coding: utf-8 -*-
"""원자료 목록을 만든다 (심사 지적 C8).

원자료는 모두 공개 자료지만 재배포하지 않는다. 그러면 재현하려는 사람은 어떤
파일을 어디서 몇 개 받아야 하는지 알 수 없다. 이 스크립트가 `01_raw_data` 를
훑어 파일마다 상대경로·크기·SHA-256 을 적고, 폴더마다 출처와 내려받은 곳을
적은 목록을 릴리스에 싣는다. 받은 파일이 우리가 쓴 것과 같은지 해시로 대조할
수 있다.

    python 02_code/build_raw_manifest.py

산출: `04_dataset_release/raw_input_manifest.csv`
      `04_dataset_release/raw_input_manifest.md` (출처와 받는 법)
"""
import csv
import hashlib
import io
import os
import re
import sys

from kird import RAW, RELEASE, RELEASE_LAST_YEAR as LAST_YEAR

YEARBOOK = "출입국통계연보"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 폴더 -> (자료 이름, 발행처, 내려받는 곳)
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
        raise SystemExit("원자료 폴더가 없다: %s" % RAW)
    rows = []
    skipped = []
    for root, dirs, files in os.walk(RAW):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in SKIP_EXT or f.startswith("~$"):
                continue
            if root == RAW:          # 원자료 폴더 바로 밑의 안내문은 자료가 아니다
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, RAW).replace(os.sep, "/")
            top = rel.split("/", 1)[0]
            # 이 판이 쓰지 않는 해의 연감은 목록에서 뺀다. 받아 두었더라도
            # 목록은 「이 배포본을 다시 지으려면 무엇이 필요한가」여야 한다.
            sub = rel.split("/")[1] if "/" in rel else ""
            m = re.match(r"(" + "[0-9]" * 4 + ")_", sub)
            if top == YEARBOOK and m and int(m.group(1)) > LAST_YEAR:
                skipped.append(rel)
                continue
            name, pub, url = SOURCES.get(top, ("", "", ""))
            rows.append([rel, name, pub, url, os.path.getsize(p), sha256(p)])
    out = os.path.join(RELEASE, "raw_input_manifest.csv")
    with io.open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "source", "publisher", "download_page", "bytes", "sha256"])
        w.writerows(rows)
    print("raw_input_manifest.csv: %d개 파일" % len(rows))
    if skipped:
        print("  LAST_YEAR(%d) 뒤라 뺀 연감 파일 %d개" % (LAST_YEAR, len(skipped)))

    by_top = {}
    for r in rows:
        by_top.setdefault(r[0].split("/", 1)[0], []).append(r)
    md = [
        "# Raw input manifest",
        "",
        "The raw sources are public and are not redistributed with this deposit. This",
        "manifest lists every file the pipeline reads, with its size and SHA-256, so a",
        "reproducer can confirm they have the same files. Download pages are the",
        "publisher's own; the yearbook editions are the per-year archives on the KIS",
        "statistics page.",
        "",
        "| folder | source | publisher | files | download |",
        "|---|---|---|---|---|",
    ]
    for top in sorted(by_top):
        name, pub, url = SOURCES.get(top, ("", "", ""))
        md.append("| `%s` | %s | %s | %d | %s |"
                  % (top, name or "(undocumented)", pub, len(by_top[top]),
                     ("<%s>" % url) if url else ""))
    md += ["",
           "Total: %d files, %.0f MB. Per-file checksums are in"
           % (len(rows), sum(r[4] for r in rows) / 1e6),
           "`raw_input_manifest.csv`.", ""]
    io.open(os.path.join(RELEASE, "raw_input_manifest.md"), "w",
            encoding="utf-8").write("\n".join(md))
    missing = sorted({r[0].split("/", 1)[0] for r in rows if not r[1]})
    if missing:
        print("  출처를 안 적은 폴더: %s" % ", ".join(missing))
    print("raw_input_manifest.md 도 썼다")


if __name__ == "__main__":
    main()
