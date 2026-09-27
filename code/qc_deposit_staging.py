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
ROOT = os.path.dirname(HERE)          # 04_dataset_release
# 2026-09-19: 아래 기본 경로가 ROOT 밑에 폴더 이름을 한 번 더 붙이고
# 있었다. 인자 없이 돌리면 README.md 를 못 찾아 죽고, 인자를 주고 돌리면
# inventory 의 `rel` 이 없는 폴더를 가리켜 **릴리스 대 스테이징 대조가
# 조용히 건너뛰어졌다.** 그 대조야말로 2026-08-31 에 diaspora 가 빠진 것을
# 잡으려고 넣은 검사다. 빠진 표를 잡는 검사가 빠져 있었다.

# 받은 사람이 그대로 돌릴 수 있어야 한다. 인자로 준 폴더를 보고, 없으면 작업
# 트리의 스테이징을 본다. 내려받은 기탁본 폴더를 주면 그 자리에서 검증된다.
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
STG = (os.path.abspath(_ARGS[0]) if _ARGS
       else os.path.join(ROOT, "data deposit",
                         "kird_openicpsr_deposit_staging"))
# 이전 판과의 대조는 그 zip 이 있을 때만 한다(선택).
PUBZIP = (os.path.abspath(_ARGS[1]) if len(_ARGS) > 1
          else os.path.join(ROOT, "data deposit",
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
    rel = os.path.join(ROOT, "data")
    if not os.path.isdir(rel):
        print("  --   릴리스 폴더가 없어 대조를 건너뛴다: %s" % rel)
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
        bad = release_vs_deposit(rel, STG)
        check(not bad, "릴리스의 표와 기탁본의 같은 칸이 값까지 같다(기탁본은 wide 열만 더한다)",
              bad[:4])
        bad = dictionary_vs_deposit(os.path.join(ROOT, "data_dictionary.csv"),
                                    os.path.join(STG, "data_dictionary.csv"))
        check(not bad, "릴리스 사전과 기탁본 사전이 같은 (파일, 변수) 행에서 같다", bad[:4])
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
WIDE_PREFIX = ("nat_", "visa_", "lang_", "mc_")
WIDE_EXTRA = {"n_enclaves", "settlement_type"}


def release_vs_deposit(rel, stg):
    """릴리스 data/ 의 표와 기탁본의 같은 표가 같은 칸에서 값까지 같은가.

    2026-09-26 (3차 대조): 두 폴더의 요약 파일 넷이 같은 칸에서 달랐다(릴리스의
    broad_apportioned 는 TRUE/FALSE, 기탁본은 True/False; national_annual 의 광의
    수는 891341.0 대 891341; summary_by_sido 의 n_nationalities_observed 는 19.0 대 19).
    세부 표는 바이트까지, 요약 파일은 릴리스의 모든 칸이 같아야 하고 기탁본이 더한
    칸은 wide 열과 n_enclaves, settlement_type 뿐이어야 한다.
    """
    import filecmp
    out = []
    for f in sorted(x for x in os.listdir(rel) if x.endswith(".csv")):
        cands = [os.path.join(stg, "data", "detailed_data", f), os.path.join(stg, "data", f)]
        q = next((c for c in cands if os.path.exists(c)), None)
        if q is None:
            continue
        if "detailed_data" in q:
            if not filecmp.cmp(os.path.join(rel, f), q, shallow=False):
                out.append("%s: detail table differs" % f)
            continue
        a = pd.read_csv(os.path.join(rel, f), encoding="utf-8-sig", dtype=str,
                        keep_default_na=False)
        b = pd.read_csv(q, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        miss = [c for c in a.columns if c not in b.columns]
        more = [c for c in b.columns if c not in a.columns
                and not c.startswith(WIDE_PREFIX) and c not in WIDE_EXTRA]
        diff = [c for c in a.columns if c in b.columns and len(a) == len(b)
                and not (a[c].values == b[c].values).all()]
        if len(a) != len(b) or miss or more or diff:
            out.append("%s: rows %d/%d, missing %s, unexpected %s, differ %s"
                       % (f, len(a), len(b), miss, more, diff))
    return out


def dictionary_vs_deposit(p_rel, p_stg):
    if not (os.path.exists(p_rel) and os.path.exists(p_stg)):
        return []
    a = pd.read_csv(p_rel, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    b = pd.read_csv(p_stg, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    m = a.merge(b, on=["file", "variable"], how="left", suffixes=("", "_d"))
    out = ["%s.%s: not in the deposit dictionary" % (r.file, r.variable)
           for r in m[m["type_d"].isna()].itertuples()]
    for c in ("type", "description_en", "description_ko"):
        d = m[m["type_d"].notna() & (m[c] != m[c + "_d"])]
        out += ["%s.%s: %s differs" % (r.file, r.variable, c) for r in d.itertuples()]
    return out


def readme_numbers():
    """README 들이 인용하는 수가 기탁 파일에서 다시 얻는 값과 같은가(readme_facts).

    2026-09-26 (3차 대조): F-6·F-2·F-4 수, 2006-2014 전국 총계, 공개 저장소의 파일 표
    (귀화 패널 2009-2024, 15,636행)가 2차 고침 전 빌드의 값으로 남아 있었다.
    """
    print("== 3a. README 의 인용 수 (readme_facts --check)")
    import readme_facts
    buf = io.StringIO()
    from contextlib import redirect_stdout
    with redirect_stdout(buf):
        rc = readme_facts.main(["--check"])
    out = buf.getvalue()
    for line in out.strip().splitlines():
        print("   " + line)
    check(rc == 0, "README 의 인용 수가 기탁 파일과 같다", out[-400:] if rc else "")


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

    # 관측 국적 수: 전국 2013=19, 2014=188 (문서의 「193」은 이름 합치기 전 값). 2026-09-26
    # 최종 감사부터 국적 아닌 칸(무국적·미등록국가·기타)을 세지 않는다. 그전의 190 은
    # 2014년 화성시의 무국적 한 명을 국적 하나로 센 값이었다. 같은 날 저녁부터 나라
    # 이름이 없는 줄(국적불명·국제연합·국제연합전문기구)도 세지 않아 189 가 188 이 된다
    # (2014년 국제연합).
    obs = dict(zip(na["year"], na["n_nationalities_observed"]))
    check(obs.get(2013) == 19 and obs.get(2014) == 188,
          "national n_nationalities_observed 2013=19, 2014=188",
          {y: obs.get(y) for y in (2013, 2014)})
    check("193 in 2014" not in txt and ", 193" not in txt,
          "README 에 옛 값 193 이 남아 있지 않다")

    # 광의/등록 배율
    r08 = na.loc[na.year == 2008, "broad_total"].iloc[0] / \
        na.loc[na.year == 2008, "foreign_total"].iloc[0]
    r24 = na.loc[na.year == 2024, "broad_total"].iloc[0] / \
        na.loc[na.year == 2024, "foreign_total"].iloc[0]
    # 2026-09-26 (4차 대조): 1.05 -> 1.04 in 2008, once the district files stopped
    # losing the 화성시 sub-office line and the columns that fold onto one country.
    check(abs(r08 - 1.04) < 0.005 and abs(r24 - 1.74) < 0.005,
          "broad/registered 1.04 (2008), 1.74 (2024)",
          (round(r08, 3), round(r24, 3)))

    # adm_code 붙임율: README 의 범위 서술과 실측이 맞는가
    emd_pct = {}
    for y, g in emd.groupby("year"):
        emd_pct[int(y)] = 100.0 * g["adm_code"].notna().sum() / len(g)
    lo, hi = min(emd_pct.values()), max(emd_pct.values())
    # README 가 적은 하한·상한이 실측을 담는가. 문장 꼴이 바뀌어도 읽히도록
    # 백분율 둘을 찾아 견준다.
    # 2026-09-26: README 는 이제 2014·2015 를 해마다, 그 뒤는 하한만 적는다
    # (「96.3% in 2014, 97.9% in 2015, and 99.7% or more in every later year」).
    rx = __import__("re")
    m = rx.search(r"([\d.]+)% in 2014, ([\d.]+)% in 2015, and ([\d.]+)% or more in "
                  r"every later year", txt)
    if m:
        later = min(v for y, v in emd_pct.items() if y >= 2016)
        ok = (abs(float(m.group(1)) - emd_pct[2014]) < 0.06
              and abs(float(m.group(2)) - emd_pct[2015]) < 0.06
              and float(m.group(3)) <= later + 1e-9 and later - float(m.group(3)) < 0.1)
        check(ok, "adm_code 붙임율 서술이 실측(2014 %.1f, 2015 %.1f, 이후 최저 %.2f%%)과 같다"
              % (emd_pct[2014], emd_pct[2015], later), m.group(0))
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

    # 귀화 화해: 국적별 표를 유형마다 더하면 연간표와 다섯 이내로 맞는다
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
    # 2026-09-25: 전에는 일곱 칸이 다섯을 넘었고 README 가 그것을 「원자료가
    # 그렇다」고 적었다. 실제로는 파서가 2017년 중국 행의 「한국계 포함」을 무시하고
    # 2014-2018 년의 「취득인지」·「재취득」 칸을 읽지 않았으며, 2019 년과 2024 년의
    # 기타를 두 번 세고 있었다. 고친 뒤로는 어느 칸도 다섯을 넘지 않는다(2018 년
    # 네 유형에서 1-5).
    WANT = {}
    check({(int(y), t): int(v) for (y, t), v in over.items()} == WANT,
          "연간표 대비 유형별 차이가 모두 다섯 이하다", dict(over))

    # wide 층 합. 2026-09-26 (3차 대조)까지는 시도 wide 열을 시도 이름으로 더해
    # 2008-2011 세종 몫이 빠지고(시도 행이 없다) 군위군이 2022년까지 대구에 들어갔다.
    # 이제 시군구는 그 해 속한 시도(sigungu_code 앞 두 자리)에 든다. 해마다, 시도마다
    # 사람 하나까지 같아야 한다.
    sd = pd.read_csv(D + "summary_by_sido.csv", encoding="utf-8-sig",
                     low_memory=False)
    wide = [c for c in s.columns if c.startswith(("nat_", "visa_", "lang_"))
            and c in sd.columns]
    cc = lambda v: "" if v != v else str(v).split(".")[0]
    lo_ = (s.assign(_p=s["sigungu_code"].map(lambda v: cc(v)[:2]))
            .groupby(["year", "_p"])[wide].sum())
    hi_ = (sd.assign(_p=sd["sido_code"].map(lambda v: cc(v).zfill(2)))
             .groupby(["year", "_p"])[wide].sum())
    j_ = lo_.join(hi_, lsuffix="_lo", rsuffix="_hi", how="outer").fillna(0)
    gap_ = max(float((j_[c + "_lo"] - j_[c + "_hi"]).abs().max()) for c in wide)
    check(gap_ < 0.5, "wide 층 합: 해마다 시도마다 시군구 합(그 해의 시도) = 시도",
          "최대 차이 %s" % gap_)
    check(not rx.search(r"short by exactly the 세종", txt),
          "README 에 옛 세종 wide 예외 문장이 남아 있지 않다")

    # 2026-09-25: README 가 다문화 말단이 소계보다 모자란 읍면동을 「about 1,400」
    # 이라 적었는데 2024 년에 2,143 이었다. 문장의 2024 값을 자료에서 센다.
    mc = pd.read_csv(DD + "multicultural_households.csv", encoding="utf-8-sig",
                     low_memory=False)
    fam = {"결혼이민자귀화자_소계": ["결혼이민자", "귀화자등"],
           "자녀_소계": ["자녀_귀화인지외국국적", "자녀_국내출생"],
           "기타동거인_소계": ["기타동거인_내국인", "기타동거인_외국인"]}
    g = mc[mc["year"] == 2024].pivot_table(
        index=["sido", "sigungu", "eupmyeondong"], columns="category",
        values="n", aggfunc="sum")
    short = np.zeros(len(g), bool)
    for sub, leaves in fam.items():
        L = g.reindex(columns=leaves).fillna(0).sum(axis=1)
        S = g.reindex(columns=[sub]).iloc[:, 0]
        short |= (S.notna() & (L < S)).values
    m = rx.search(r"\(([\d,]+) of ([\d,]+)\s+in 2024\)", txt)
    said = tuple(int(v.replace(",", "")) for v in m.groups()) if m else None
    check(said == (int(short.sum()), len(g)),
          "README 의 다문화 소계 부족 읍면동 수(2024)가 자료와 같다",
          (said, (int(short.sum()), len(g))))


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
    # 2026-09-25: 난민 국적표만 러시아를 「러시아」로 적어 crosswalk_country 의 표준
    # 이름(러시아(연방))과 붙지 않았다. 다른 국적표와 같이 표준 이름만 쓰는지 본다.
    rn = pd.read_csv(os.path.join(STG, "data", "detailed_data",
                                  "refugee_by_nationality.csv"), encoding="utf-8-sig")
    cw = pd.read_csv(os.path.join(STG, "data", "detailed_data",
                                  "crosswalk_country.csv"), encoding="utf-8-sig")
    off = sorted(set(rn["country"]) - set(cw["country"]))
    check(not off, "난민 국적표의 국적이 모두 crosswalk_country 의 표준 이름이다", off)


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
        # (c2) 거꾸로도: 등록외국인이 있는 요약 행마다 상세 행이 있는가. 2026-09-26 최종
        # 감사에서 앞 방향만 보던 것을 찾았다. 요약의 2015 창원시(1명) 행에 자격 행이
        # 없는데, 그 해 시군구x체류자격 표가 창원시 줄을 싣지 않고 그 사람을 마산합포구
        # 줄(2,160)에 넣기 때문이다(국적 표는 창원시 1 + 마산합포구 2,159). 그 한 곳만
        # 원자료대로 비고, 다른 빈 곳은 결함이다.
        EMPTY_OK = {"visa_by_sigungu.csv": {(2015, "경상남도", "창원시")}}
        have = set(map(tuple, n[n["n"] > 0][key].drop_duplicates().values.tolist()))
        want = set(map(tuple, s[s["registered_foreigners"] > 0][key].values.tolist()))
        lack = sorted(want - have)
        ok_ = EMPTY_OK.get(name, set())
        check([k for k in lack if k not in ok_] == [] and ok_ <= set(lack),
              "등록외국인이 있는 요약 행마다 %s 행이 있다 (원자료대로 빈 곳 %d)"
              % (name, len(ok_)), "없는 곳 %s" % lack[:5])

    # (d) 영문 이름만으로 join 하면 안 된다는 것이 문서에 있는가
    d24 = s[s["year"] == s["year"].max()]
    n_dup = int(d24["sigungu_en"].duplicated().sum())
    txt = io.open(os.path.join(STG, "README.md"), encoding="utf-8").read()
    warned = ("sigungu_en" in txt and
              ("not unique" in txt or "on its own" in txt or "동구" in txt))
    check(n_dup == 0 or warned,
          "sigungu_en 이 유일하지 않다는 것을 README 가 알린다 (중복 %d개)" % n_dup)


# ------------------------------------------------- 7. README 의 읽기 요리법
def readme_recipe():
    """README 가 권하는 읽기 코드를 그대로 모든 표에 돌려 본다.

    2026-09-26 (4차 대조): README 는 코드 칸을 글자로 읽으라며
    `dtype=codes, keep_default_na=False` 를 「join 하는 모든 파일」에 권했다.
    keep_default_na=False 는 코드 칸만이 아니라 파일 전체의 빈칸을 빈 글자로 바꿔,
    summary_by_sigungu 의 nat_japan 같은 wide 열이 글자와 수가 섞인 칸이 되고
    `.sum()` 이 TypeError 로 죽었다(summary_by_sido 는 경고도 없이 숫자를 이어
    붙였다). README 의 코드 블록을 꺼내 실행하고, 평범하게 읽은 것과 비교한다.
    """
    print("== 7. README 의 읽기 요리법")
    import re as _re
    import warnings as _w
    docs = [os.path.join(STG, "README.md")]
    rel_readme = os.path.join(ROOT, "README.md")
    if os.path.exists(rel_readme):
        docs.append(rel_readme)
    for doc in docs:
        md = io.open(doc, encoding="utf-8").read()
        m = _re.search(r"\*\*Read the code columns as text\.\*\*.*?```python\s*\n(.*?)```",
                       md, _re.S)
        label = os.path.relpath(doc, ROOT)
        check(m is not None, "%s: 코드 칸 읽기 요리법이 있다" % label)
        if m is None:
            continue
        code = m.group(1)
        bad = []
        for cp in all_csvs():
            ns = {"pd": pd, "path": cp}
            with _w.catch_warnings():
                _w.simplefilter("error")
                try:
                    exec(code, ns)
                except Exception as e:          # a warning counts as a failure
                    bad.append("%s: %s" % (os.path.basename(cp), type(e).__name__))
                    continue
            got = ns.get("df")
            plain = pd.read_csv(cp, encoding="utf-8-sig", low_memory=False)
            codes = [c for c in ("sido_code", "sigungu_code", "adm_code") if c in got.columns]
            for c in plain.columns:
                if c in codes:
                    v = got[c]
                    if not (v.map(type) == str).all() or v.str.endswith(".0").any():
                        bad.append("%s.%s: code column not plain text"
                                   % (os.path.basename(cp), c))
                elif (pd.api.types.is_numeric_dtype(plain[c])
                      and not pd.api.types.is_numeric_dtype(got[c])):
                    bad.append("%s.%s: numeric column read as %s"
                               % (os.path.basename(cp), c, got[c].dtype))
        check(not bad, "%s: 그 요리법으로 %d개 표를 모두 읽으면 코드 칸은 글자, 수 칸은 수"
              % (label, len(all_csvs())), bad[:5])


def main():
    inventory()
    parity()
    readme_claims()
    readme_numbers()
    against_published()
    refugee_language()
    as_a_user()
    readme_recipe()
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
