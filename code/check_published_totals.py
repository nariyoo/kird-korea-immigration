# -*- coding: utf-8 -*-
"""배포본의 전국 합계를 연감이 인쇄한 총계와 맞춰 본다.

원고가 대는 「공표치와 0.x% 안에서 일치한다」는 문장의 근거다. 파이프라인 안의
검사가 아니라, 연감 파일에서 **인쇄된 총계 한 칸만** 따로 읽어 배포본
`visa_national.csv` 의 그 해 합계와 비교한다. 조화 과정을 거치지 않은 값과 맞대는
것이라, 조화가 무엇을 흘렸는지 아니면 더했는지 그대로 드러난다.

    python 02_code/check_published_totals.py

체류외국인은 2011년부터 연감이 국적×체류자격 한 표로 싣는다. 2006-2010년은
그런 표가 없어 등록 + 단기 + 거소신고를 합쳐 만들었지만, 그 다섯 해도 연감 2장의
「체류외국인 현황」이 머리 총계를 찍어 두었으므로 그 값과 맞대 본다. 합성치가
공표치보다 큰 만큼이 세 표의 겹침이다.

출력: 03_cleaned_data/published_total_check.csv
"""
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kird import CLEAN, RELEASE_DATA          # noqa: E402

# 2006-2010년판에는 국적×체류자격으로 짠 체류외국인 표가 없다. 대신 2장 첫머리의
# 「체류외국인 현황」이 그 해 총계를 찍어 두었으므로, 합성한 값을 이것과 맞댄다.
RAWYB = os.path.join(os.path.dirname(HERE), "01_raw_data", "출입국통계연보")
HEADLINE_STAY = {
    2006: os.path.join(RAWYB, "2006_출입국통계연보", "2장", "2-체류외국인현황.xls"),
    2007: os.path.join(RAWYB, "2007_출입국통계연보", "2-Ⅱ.체류외국인현황.xls"),
    2008: os.path.join(RAWYB, "2008_출입국통계연보", "2장_Ⅱ_체류외국인현황.xls"),
    2009: os.path.join(RAWYB, "2009_출입국통계연보", "2장_Ⅱ_체류외국인현황.xls"),
    2010: os.path.join(RAWYB, "2010_출입국통계연보", "2장_Ⅱ_체류외국인현황.xls"),
}

TOTAL_LABELS = ("총계", "총 계", "합계", "합 계", "grand-total", "grandtotal", "total")


def norm(v):
    return str(v).replace(" ", "").replace("\n", "").strip().lower()


def cell_number(v):
    """연감은 한 칸에 줄바꿈으로 여러 수를 넣기도 한다. 첫 수만 쓴다."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).split("\n")[0].replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def printed_total(path):
    """그 파일이 인쇄한 총계.

    판마다 표 머리가 달라서 「총계 열」을 이름으로 찾으면 자꾸 빗나간다(2019년
    이후는 열 이름이 총합계이고, 2014년판은 열 이름이 그냥 계다). 대신 총계
    **행**을 찾은 뒤 그 행에서 가장 큰 수를 쓴다. 총계 열은 나머지 열의 합이므로
    그 행에서 언제나 가장 크다.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    for i in range(min(12, len(df))):
        row = df.iloc[i].tolist()
        head = norm(" ".join(str(x) for x in row[:2] if isinstance(x, str)))
        if not head:
            continue
        if not any(t in head for t in ("총계", "총합계", "합계", "grand-total")):
            continue
        # 2006-2007년판은 비교용으로 앞선 해의 총계 행을 위에 얹어 둔다.
        # 「2004년 총계」 같은 행을 그 해의 총계로 읽으면 안 된다.
        if re.search(r"(19|20)[0-9]{2}년", head):
            continue
        nums = [cell_number(v) for v in row]
        nums = [n for n in nums if n and n > 0]
        if nums:
            return max(nums), ""
    # 2006-2007년판처럼 첫 칸이 「계」 한 글자인 판
    for i in range(min(12, len(df))):
        row = df.iloc[i].tolist()
        if isinstance(row[0], str) and norm(row[0]) in ("계", "총계", "총합계"):
            nums = [cell_number(v) for v in row]
            nums = [n for n in nums if n and n > 0]
            if nums:
                return max(nums), ""
    return None, "총계 행을 못 찾았다"


def released_totals():
    df = pd.read_csv(os.path.join(RELEASE_DATA, "visa_national.csv"),
                     encoding="utf-8-sig")
    out = {}
    for pop, g in df.groupby("population"):
        out[pop] = g.groupby("year")["n"].sum().to_dict()
    return out


def main():
    # 파일 목록은 01 과 같은 것을 쓰되, 그 스크립트를 실행하지 않고 다시 적는다.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_p1", os.path.join(HERE, "01_parse_yearbooks.py"))
    src = open(spec.origin, encoding="utf-8").read()
    ns = {"__name__": "_p1_defs"}
    head = src[:src.index("# Continent aggregate")]
    exec(compile(head, spec.origin, "exec"), ns)      # 사전만 얻는다

    rel = released_totals()
    rows = []
    stay_files = dict(ns["STAY_FILES"])
    stay_files.update(HEADLINE_STAY)          # 2006-2010 은 머리 총계 표로 본다
    for series, files, popkey in (("registered", ns["REG_FILES"], "registered"),
                                  ("staying", stay_files, "stay")):
        for year in sorted(files):
            path = files[year]
            if not os.path.exists(path):
                rows.append({"series": series, "year": year, "printed": None,
                             "released": rel.get(popkey, {}).get(year),
                             "note": "원자료 없음"})
                continue
            pt, note = printed_total(path)
            rows.append({"series": series, "year": year, "printed": pt,
                         "released": rel.get(popkey, {}).get(year), "note": note})

    df = pd.DataFrame(rows)
    df["diff_pct"] = (df["released"] - df["printed"]) / df["printed"] * 100
    out = os.path.join(CLEAN, "published_total_check.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print("연감이 인쇄한 총계 대 배포본 전국 합계")
    print()
    for series in ("registered", "staying"):
        sub = df[df["series"] == series].dropna(subset=["diff_pct"])
        print("== %s (%d개 연도)" % (series, len(sub)))
        for _, r in sub.iterrows():
            print("   %d  인쇄 %11s  배포 %11s  %+.3f%%"
                  % (r["year"], format(int(r["printed"]), ","),
                     format(int(r["released"]), ","), r["diff_pct"]))
        if len(sub):
            w = sub.loc[sub["diff_pct"].abs().idxmax()]
            print("   최대 어긋남 %.3f%% (%d년)" % (abs(w["diff_pct"]), w["year"]))
        miss = df[(df["series"] == series) & (df["diff_pct"].isna())]
        if len(miss):
            print("   대조 못 한 해: %s" %
                  ", ".join("%d(%s)" % (r["year"], r["note"] or "인쇄 총계 없음")
                            for _, r in miss.iterrows()))
        print()
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
