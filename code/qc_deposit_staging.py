# -*- coding: utf-8 -*-
"""openICPSR 에 올릴 스테이징 트리를 그 안의 파일만으로 전수 점검한다.

`validate_release.py` 가 지표·항등식·사전을 이미 본다(61검사). 이 도구는 그것이
안 보는 것을 본다.

    1. 파일 목록          CSV 27 + DTA 27 + 문서 3 = 57, 다른 것 없음
    2. CSV-DTA 값 일치     모든 쌍을 셀 단위로 대조한다. 10단계의 parity 는 모양
                          (행수x칸수)만 보므로, CSV 를 고치고 .dta 를 안 다시
                          만들면 통과한다 — 값으로 잡는다.
    3. README 의 자료 의존 주장
                          관측 국적 수(190/193), adm_code 붙임율, 귀화 화해,
                          광의/등록 배율(1.05/1.74), 빈칸 목록, 세종 wide 예외.
    4. 공개된 v1.1.0 대비   무엇이 새로 왔고 무엇이 바뀌었는지 파일마다 센다.
                          결과는 OPENICPSR_METADATA.md 의 실측 절과 맞아야 한다.
    5. 난민 언어           아이티크레올어가 인도적체류에 있는가(2026-08-26 확장의
                          표지 사례).

    python qc_deposit_staging.py [<기탁본 폴더> [<이전 판 zip>]]

폴더를 안 주면 작업 트리의 스테이징을 본다. 내려받은 사람은 풀어 놓은 기탁본
폴더를 주면 그 자리에서 같은 검사를 돌릴 수 있다. 이전 판 zip 은 선택이며,
없으면 그 절만 건너뛴다. pandas 와 numpy 만 있으면 된다.

전부 통과하면 0, 하나라도 어긋나면 1로 끝난다.
"""
import glob
import io
import os
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 받은 사람이 그대로 돌릴 수 있어야 한다. 인자로 준 폴더를 보고, 없으면 작업
# 트리의 스테이징을 본다. 내려받은 기탁본 폴더를 주면 그 자리에서 검증된다.
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
STG = (os.path.abspath(_ARGS[0]) if _ARGS
       else os.path.join(ROOT, "04_dataset_release", "data deposit",
                         "kird_openicpsr_deposit_staging"))
# 이전 판과의 대조는 그 zip 이 있을 때만 한다(선택).
PUBZIP = (os.path.abspath(_ARGS[1]) if len(_ARGS) > 1
          else os.path.join(ROOT, "04_dataset_release", "data deposit",
                            "KIRD_openicpsr_deposit_v1.1.0.zip"))

FAILS = []


def check(ok, label, detail=""):
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", label,
                           ("  |  " + str(detail)) if (detail and not ok) else ""))
    if not ok:
        FAILS.append(label)


def all_csvs():
    return (sorted(glob.glob(os.path.join(STG, "data", "*.csv")))
            + sorted(glob.glob(os.path.join(STG, "data", "detailed_data", "*.csv"))))


# ------------------------------------------------------------------ 1. 목록
def inventory():
    print("== 1. 파일 목록")
    files = []
    for dp, _, fns in os.walk(STG):
        for fn in fns:
            files.append(os.path.relpath(os.path.join(dp, fn), STG))
    csvs = [f for f in files if f.endswith(".csv") and f != "data_dictionary.csv"]
    dtas = [f for f in files if f.endswith(".dta")]
    docs = sorted(f for f in files if not f.endswith((".csv", ".dta")))
    check(len(csvs) == 28, "CSV 28개", len(csvs))
    check(len(dtas) == 28, "DTA 28개", len(dtas))
    # **개수만 세면 어느 표가 빠졌는지 모른다.** 2026-08-31 에
    # diaspora_residence_by_sido 가 스테이징에서 빠진 채로 이 검사를 통과했다.
    # 릴리스가 8-29 에 그 표를 새로 냈는데 스테이징을 다시 돌리지 않았고,
    # 기대 개수가 27 로 박혀 있어 27 개인 것이 맞다고 답했다. 작업 트리에서
    # 돌릴 때는 릴리스 폴더와 이름을 맞대어 본다. 받은 사람이 기탁본만 가지고
    # 돌릴 때는 그 폴더가 없으므로 이 검사는 건너뛴다.
    rel = os.path.join(ROOT, "04_dataset_release", "data")
    if os.path.isdir(rel):
        want = {f for f in os.listdir(rel) if f.endswith(".csv")}
        have = {os.path.basename(f) for f in csvs}
        missing = sorted(want - have)
        extra = sorted(have - want)
        check(not missing, "릴리스의 표가 모두 스테이징에 있다", missing)
        # 기탁에만 있는 표(난민 둘)는 릴리스 data/ 에 없다. 이름을 적어 둔다.
        check(set(extra) <= {"refugee_by_nationality.csv",
                             "refugee_language_demand.csv"},
              "스테이징에만 있는 표는 난민 표 둘뿐", extra)
    check(docs == ["LICENSE.txt", "README.md"], "문서는 README 와 LICENSE 뿐", docs)
    check(os.path.exists(os.path.join(STG, "data_dictionary.csv")),
          "data_dictionary.csv 있음")
    # **문서에 없는 파일이 기탁물에 들어가면 안 된다.** 2026-08-31 에 다섯
    # 개(크로스워크 셋, language_weights, diaspora)가 README 의 표에 한 번도
    # 안 나온 채로 스테이징에 있었다. 개수 검사도, CSV-DTA 짝 검사도 그것을
    # 못 본다.
    import re as _re
    _md = io.open(os.path.join(STG, "README.md"), encoding="utf-8").read()
    _in_readme = set(_re.findall(r"\|\s*([a-z0-9_]+)\.csv\s*\|", _md))
    _undocumented = sorted({os.path.basename(f)[:-4] for f in csvs}
                           - _in_readme)
    check(not _undocumented, "모든 표가 README 의 표에 있다", _undocumented)

    pairs = {f[:-4] for f in csvs} ^ {f[:-4] for f in dtas}
    check(not pairs, "모든 CSV 에 .dta 짝", sorted(pairs))


# ------------------------------------------------------- 2. CSV-DTA 값 일치
def parity():
    print("== 2. CSV-DTA 값 일치 (셀 단위)")
    for cp in all_csvs():
        stem = os.path.basename(cp)[:-4]
        dp = cp[:-4] + ".dta"
        c = pd.read_csv(cp, encoding="utf-8-sig", low_memory=False)
        d = pd.read_stata(dp)
        ok = c.shape == d.shape and list(c.columns) == list(d.columns)
        detail = "shape %s vs %s" % (c.shape, d.shape)
        if ok:
            bad = 0
            for col in c.columns:
                a, b = c[col], d[col]
                # broad_apportioned 는 CSV 가 불(True/False)로 읽히고 .dta 는
                # 문자 "True"/"False" 다. 뜻이 같으므로 문자로 눕혀 비교한다.
                if (pd.api.types.is_bool_dtype(a)
                        or set(map(str, b.dropna().unique())) <= {"True", "False"}):
                    m = (a.fillna("").astype(str).str.lower()
                         != b.fillna("").astype(str).str.lower()).to_numpy()
                elif pd.api.types.is_numeric_dtype(a) or pd.api.types.is_numeric_dtype(b):
                    an = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
                    bn = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
                    m = ~np.isclose(an, bn, rtol=0, atol=1e-9, equal_nan=True)
                else:
                    m = (a.fillna("").astype(str).str.strip()
                         != b.fillna("").astype(str).str.strip()).to_numpy()
                bad += int(m.sum())
            ok = bad == 0
            detail = "%d개 셀이 다름" % bad
        check(ok, "parity %s" % stem, detail)


# ------------------------------------------------ 3. README 의 자료 의존 주장
def readme_claims():
    print("== 3. README 의 자료 의존 주장")
    txt = io.open(os.path.join(STG, "README.md"), encoding="utf-8").read()
    D = os.path.join(STG, "data") + os.sep
    DD = os.path.join(STG, "data", "detailed_data") + os.sep
    na = pd.read_csv(D + "national_annual.csv", encoding="utf-8-sig")
    s = pd.read_csv(D + "summary_by_sigungu.csv", encoding="utf-8-sig",
                    low_memory=False)
    emd = pd.read_csv(D + "summary_by_eupmyeondong.csv", encoding="utf-8-sig",
                      low_memory=False)

    # 관측 국적 수: 전국 2013=19, 2014=190 (문서의 「193」은 이름 합치기 전 값)
    obs = dict(zip(na["year"], na["n_nationalities_observed"]))
    check(obs.get(2013) == 19 and obs.get(2014) == 190,
          "national n_nationalities_observed 2013=19, 2014=190",
          {y: obs.get(y) for y in (2013, 2014)})
    check("193 in 2014" not in txt and ", 193" not in txt,
          "README 에 옛 값 193 이 남아 있지 않다")

    # 광의/등록 배율
    r08 = na.loc[na.year == 2008, "broad_total"].iloc[0] / \
        na.loc[na.year == 2008, "foreign_total"].iloc[0]
    r24 = na.loc[na.year == 2024, "broad_total"].iloc[0] / \
        na.loc[na.year == 2024, "foreign_total"].iloc[0]
    check(abs(r08 - 1.05) < 0.005 and abs(r24 - 1.74) < 0.005,
          "broad/registered 1.05 (2008), 1.74 (2024)",
          (round(r08, 3), round(r24, 3)))

    # adm_code 붙임율: README 의 범위 서술과 실측이 맞는가
    emd_pct = {}
    for y, g in emd.groupby("year"):
        emd_pct[int(y)] = 100.0 * g["adm_code"].notna().sum() / len(g)
    lo, hi = min(emd_pct.values()), max(emd_pct.values())
    # README 가 적은 하한·상한이 실측을 담는가. 문장 꼴이 바뀌어도 읽히도록
    # 백분율 둘을 찾아 견준다.
    rx = __import__("re")
    m = rx.search(r"Between ([\d.]+)% \([0-9]{4}\) and ([\d.]+)%", txt)
    if m:
        said_lo, said_hi = float(m.group(1)), float(m.group(2))
        check(abs(said_lo - lo) < 0.06 and abs(said_hi - hi) < 0.06,
              "adm_code 하한·상한 서술이 실측(%.1f-%.1f%%)과 같다" % (lo, hi),
              m.group(0))
    else:
        check(False, "adm_code 서술을 README 에서 못 찾았다 (실측 %.1f-%.1f%%)"
              % (lo, hi))

    # 2008 빈칸: theil 와 ethnic_koreans 뿐
    r = na[na.year == 2008].iloc[0]
    # wide 열(nat_/visa_/lang_)의 빈칸은 「그 해에 따로 실리지 않음」이라는
    # 문서화된 규칙이라 여기서 세지 않는다.
    blanks = [c for c in na.columns
              if pd.isna(r[c]) and not c.startswith(("nat_", "visa_", "lang_"))]
    check(set(blanks) == {"theil_segregation_H", "ethnic_koreans"},
          "national_annual 2008 빈칸은 theil 과 ethnic_koreans 뿐", blanks)

    # 귀화 화해: 다섯 초과 넷 (2017 선택 -10 · 판정 -7, 2018 상실 -8, 2019 상실 +7)
    ann = pd.read_csv(DD + "naturalization_annual.csv", encoding="utf-8-sig")
    byc = pd.read_csv(DD + "naturalization_by_country.csv", encoding="utf-8-sig")
    norm = lambda t: str(t).replace(" ", "")
    ann["t"] = ann["type"].map(norm)
    byc["t"] = byc["type"].map(norm)
    a = ann.groupby(["year", "t"])["n"].sum()
    b = byc.groupby(["year", "t"])["n"].sum()
    both = a.index.intersection(b.index)
    gap = (b[both] - a[both])
    over = gap[gap.abs() > 5]
    WANT = {(2017, "국적선택"): -10, (2017, "국적판정"): -7, (2018, "국적상실"): -8,
            (2019, "국적상실"): 7, (2019, "국적취득(재취득)"): 18,
            (2024, "국적취득(인지)"): 8, (2024, "국적취득(재취득)"): 16}
    check({(int(y), t): int(v) for (y, t), v in over.items()} == WANT,
          "연간표 대비 다섯 초과가 문서의 일곱 자리 그대로", dict(over))

    # 세종 wide 예외: 그 해들의 차이가 세종 값과 정확히 같다
    sd = pd.read_csv(D + "summary_by_sido.csv", encoding="utf-8-sig",
                     low_memory=False)
    wide = [c for c in s.columns if c.startswith(("nat_", "visa_", "lang_"))
            and c in sd.columns]
    lo_ = s.groupby("year")[wide].sum()
    hi_ = sd.groupby("year")[wide].sum()
    sj = s[s.sido == "세종특별자치시"].groupby("year")[wide].sum()
    leak = (lo_ - hi_ - sj.reindex(lo_.index).fillna(0) *
            (lo_.index.to_series() < 2012).values[:, None]).abs()
    # 2012년부터는 차이가 0, 그 전에는 세종 몫과 정확히 일치해야 한다
    ok = True
    for y in lo_.index:
        gap_y = (lo_.loc[y] - hi_.loc[y])
        want = sj.loc[y] if (y < 2012 and y in sj.index) else 0
        if not np.allclose(gap_y.fillna(0), (want if not np.isscalar(want)
                                             else pd.Series(0, index=gap_y.index)).fillna(0)
                           if not np.isscalar(want) else 0, atol=0.5):
            if np.isscalar(want) or not np.allclose(gap_y.fillna(0),
                                                    want.reindex(gap_y.index).fillna(0), atol=0.5):
                ok = False
    check(ok, "wide 층 합: 2012+ 정확, 2008-2011 차이 = 세종 몫")


# --------------------------------------------------- 4. 공개된 v1.1.0 대비
def against_published():
    print("== 4. 공개된 v1.1.0 대비 (zip)")
    import zipfile
    if not os.path.exists(PUBZIP):
        print("     (이전 판 zip 이 없어 건너뛴다: %s)" % PUBZIP)
        return
    zf = zipfile.ZipFile(PUBZIP)
    pub = {}
    for nm in zf.namelist():
        if nm.endswith(".csv") and "data_dictionary" not in nm:
            pub[os.path.basename(nm)] = nm
    new, changed, unchanged = [], [], []
    for cp in all_csvs():
        fn = os.path.basename(cp)
        if fn not in pub:
            new.append(fn)
            continue
        a = io.open(cp, "rb").read()
        b = zf.read(pub[fn])
        (unchanged if a == b else changed).append(fn)
    removed = sorted(set(pub) - {os.path.basename(c) for c in all_csvs()})
    print("     새로 %d  바뀜 %d  그대로 %d  없어짐 %d"
          % (len(new), len(changed), len(unchanged), len(removed)))
    for lab, lst in (("새로", new), ("그대로", unchanged), ("없어짐", removed)):
        print("     %s: %s" % (lab, ", ".join(sorted(lst)) or "없음"))
    check(removed == ["summary_national.csv"],
          "없어진 것은 이름이 바뀐 summary_national 뿐", removed)


# ------------------------------------------------------------- 5. 난민 언어
def refugee_language():
    print("== 5. 난민 언어")
    rl = pd.read_csv(os.path.join(STG, "data", "detailed_data",
                                  "refugee_language_demand.csv"),
                     encoding="utf-8-sig")
    hai = rl[(rl["status"] == "인도적체류") & (rl["language"].str.contains("크레올"))]
    check(len(hai) == 1, "인도적체류에 아이티크레올어가 있다",
          rl[rl["status"] == "인도적체류"]["language"].tolist()[:8])
    en_gap = rl[rl["language_en"].astype(str).str.contains("[가-힣]", regex=True)]
    check(len(en_gap) == 0, "영문 칸에 한글이 없다", en_gap["language_en"].tolist())


# --------------------------------------------------- 6. 쓰는 사람의 자리
def as_a_user():
    """받은 사람이 실제로 하는 일을 그대로 해 본다.

    2026-08-26에 이 자리에서 셋을 찾았다. 기탁본의 `adm_code` 가 `3203062.0` 으로
    저장돼 GIS 열쇠에 소수점이 붙어 있었고(릴리스 파일은 멀쩡했다 — 결측 있는
    정수 칸을 pandas 가 float 로 올려 그대로 쓴 것), 2014년에 같은 동이 두 표기로
    두 번 실려 코드가 391개 겹쳤으며, 창원 성산구 중앙동이 진주시 코드를 달고
    있었다. 셋 다 「열어서 join 해 보면」 바로 걸리지만 스키마 검사로는 안 걸린다.
    """
    print("== 6. 쓰는 사람의 자리")
    D = os.path.join(STG, "data") + os.sep
    DD = os.path.join(STG, "data", "detailed_data") + os.sep

    # (a) 정수여야 할 값에 .0 이 붙어 있지 않은가
    import re
    P = re.compile(r"^-?[0-9]+[.]0$")
    bad = []
    for cp in all_csvs():
        d = pd.read_csv(cp, encoding="utf-8-sig", dtype=str, low_memory=False)
        for c in d.columns:
            if c.endswith("_pct") or c in ("share", "share_pct", "lq",
                                           "dissimilarity_D", "isolation",
                                           "interaction_korean"):
                continue
            v = d[c].dropna()
            if len(v) and v.str.match(P).mean() > 0.5 and v.str.match(P).any():
                bad.append("%s.%s" % (os.path.basename(cp), c))
    check(not bad, "정수 칸에 소수 꼬리(.0)가 없다", bad[:6])

    # (b) 읍면동 코드가 그 해 안에서 유일한 GIS 열쇠인가
    e = pd.read_csv(D + "summary_by_eupmyeondong.csv", encoding="utf-8-sig",
                    dtype={"adm_code": str}, low_memory=False)
    v = e.dropna(subset=["adm_code"]).copy()
    v["adm_code"] = v["adm_code"].str.strip()
    v = v[v["adm_code"] != ""]
    dup = int(v.duplicated(["year", "adm_code"]).sum())
    check(dup == 0, "adm_code 가 연도 안에서 유일하다 (경계 join 이 행을 불리지 않는다)",
          "%d행" % dup)
    v["p4"] = v["adm_code"].str[:4]
    mode = v.groupby(["year", "sido", "sigungu"])["p4"].transform(
        lambda x: x.mode().iloc[0])
    check(int((v["p4"] != mode).sum()) == 0,
          "모든 동 코드가 제 시군구의 코드 대역 안에 있다",
          "%d행" % int((v["p4"] != mode).sum()))

    # (c) 요약과 상세를 한글 열쇠로 붙이면 하나도 안 남는가
    s = pd.read_csv(D + "summary_by_sigungu.csv", encoding="utf-8-sig",
                    low_memory=False)
    for name, key in (("nationality_by_sigungu.csv",
                       ["year", "sido", "sigungu"]),
                      ("visa_by_sigungu.csv", ["year", "sido", "sigungu"])):
        n = pd.read_csv(DD + name, encoding="utf-8-sig", low_memory=False)
        j = n.merge(s[key + ["resident_pop"]], on=key, how="left", indicator=True)
        miss = int((j["_merge"] != "both").sum())
        check(miss == 0, "%s 가 요약에 전부 붙는다" % name, "%d행" % miss)

    # (d) 영문 이름만으로 join 하면 안 된다는 것이 문서에 있는가
    d24 = s[s["year"] == s["year"].max()]
    n_dup = int(d24["sigungu_en"].duplicated().sum())
    txt = io.open(os.path.join(STG, "README.md"), encoding="utf-8").read()
    warned = ("sigungu_en" in txt and
              ("not unique" in txt or "on its own" in txt or "동구" in txt))
    check(n_dup == 0 or warned,
          "sigungu_en 이 유일하지 않다는 것을 README 가 알린다 (중복 %d개)" % n_dup)


def main():
    inventory()
    parity()
    readme_claims()
    against_published()
    refugee_language()
    as_a_user()
    print()
    if FAILS:
        print("%d개 어긋남:" % len(FAILS))
        for f in FAILS:
            print("   " + f)
        return 1
    print("전부 통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
