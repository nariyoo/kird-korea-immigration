"""Reproducible end-to-end build of the KIRD dataset.

One runner, three phases, ten steps. Phase 1 turns 01_raw_data/ into the
dashboard JSON in 05_dashboard/data/ and the tidy intermediates in
03_cleaned_data/; phase 2 turns those into the public release in
04_dataset_release/; phase 3 stages the openICPSR deposit and runs on demand.
Splitting phases 1 and 2 across separate runners is what once let steps go
missing: the release half is not runnable without phase 1, and phase 1 alone does
not produce a releasable dataset.

Usage:
    python 02_code/run_pipeline.py              # phases 1 and 2
    python 02_code/run_pipeline.py --phase 1    # dashboard only
    python 02_code/run_pipeline.py --phase 2    # release only (phase 1 outputs must exist)
    python 02_code/run_pipeline.py --phase 3    # deposit staging, on demand
    python 02_code/run_pipeline.py --from 08_export_dataset.py   # resume at a step

Paths come from kird.py, which finds the project root from its own
location; set KIRD_ROOT to build a different checkout.

Each step is a standalone script in this directory, numbered for its position,
and the number is the run order. The only unnumbered files are the shared module
kird.py, this runner, and requirements.txt. The steps read and write the
intermediate JSON and CSV in place, so do not reorder them without checking each
one's inputs.
"""
import argparse
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kird import ROOT, RELEASE_DATA  # noqa: E402

# ── Phase 1: raw yearbooks → dashboard JSON ──────────────────────────────────
PHASE1 = [
    # every yearbook -> by-visa / by-region / by-district / age long tables, plus
    # the base 05_dashboard/data JSON (indices, region, data, age)
    "01_parse_yearbooks.py",
    # the language reference tables: Korean/English labels and the Ethnologue 24
    # first-language shares. Everything that touches language reads these, so
    # they come before any of it.
    "02_language_reference.py",
    # the panel, extended: spatial clusters, the province series back to 2006,
    # the national series, one label per country, the visa panel, refugee
    # language, and the 2008-2013 backfills
    "03_extend_panel.py",
    # boundary changes reconciled, every index recomputed on the reconciled set,
    # and the language block trimmed to the released top 20
    "04_reconcile_districts.py",
    # the MOIS sibling tables (행정안전부 외국인주민통계, a broader population
    # definition than MOJ): keys, validation, assembly, the Sejong patches,
    # packaging. Reads the 03_cleaned_data/mois_*.csv that the same file's
    # --reparse mode writes out of the raw 행정안전부 editions.
    "05_mois_layer.py",
]

# ── Phase 2: dashboard JSON → public release ─────────────────────────────────
PHASE2 = [
    # the per-level summaries on the MOJ district grain, and the MOIS CSVs
    "06_build_summaries.py",
    # nationality processing, read out of chapter 4 of every edition
    "07_build_naturalization.py",
    # the tidy release CSVs, then language_demand.csv on the released basis
    "08_export_dataset.py",
    # (the working-name rename runs here, in code below)
    # the released schema, segregation, the dictionary, Stata, and the audit,
    # which must end AUDIT CLEAN before anything is uploaded
    "09_finish_release.py",
    # 저장소가 싣는 그림 셋. 손으로 돌리던 것이라 두 장이 2026-06 판 그대로
    # 남아 있었다. 자료를 지을 때마다 함께 짓게 해서 다시 갈라지지 않게 한다.
    "make_coverage_figure.py",
    "sync_repo_figures.py",
]

# ── Phase 3: the openICPSR deposit ───────────────────────────────────────────
# Not run by default: the refugee files, the wide summary variants, and the
# deposit gate.
PHASE3 = [
    "10_stage_deposit.py",
]

# Working names that export_dataset emits, and the released names they become.
RENAMES = {
    "foreign_residents_by_visa.csv": "visa_by_nationality.csv",
    "foreign_residents_by_sigungu.csv": "nationality_by_sigungu.csv",
    "foreign_residents_by_sigungu_visa.csv": "visa_by_sigungu.csv",
    "foreign_residents_by_age_sex.csv": "age_sex_national.csv",
    "national_summary_annual.csv": "national_annual.csv",
}
# Intermediates that must not survive into the release folder: build_data_dictionary
# asserts the dictionary documents exactly the columns of the files it finds there.
DROP = list(RENAMES) + [
    "language_demand_draft.csv",
    "indices_by_sido.csv", "indices_by_sigungu.csv", "resident_population_by_sigungu.csv",
    "mois_broad_residents_by_eupmyeondong.csv", "mois_broad_residents_by_sigungu.csv",
    "mois_children_by_age.csv", "mois_multicultural_households.csv",
    "mois_multicultural_households_by_sigungu.csv",
]
RENAME_AFTER = "08_export_dataset.py"   # the rename runs once this step is done


def rename_working_files():
    print("\n===== rename working names -> released names =====", flush=True)
    for src, dst in RENAMES.items():
        p = os.path.join(RELEASE_DATA, src)
        if os.path.exists(p):
            shutil.copyfile(p, os.path.join(RELEASE_DATA, dst))
            print(f"  {src} -> {dst}")
    for f in DROP:
        p = os.path.join(RELEASE_DATA, f)
        if os.path.exists(p):
            os.remove(p)
            print(f"  removed intermediate {f}")



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, choices=(1, 2, 3))
    ap.add_argument("--from", dest="start", help="resume at this step filename")
    args = ap.parse_args()

    steps = ({1: PHASE1, 2: PHASE2, 3: PHASE3}.get(args.phase)
             or PHASE1 + PHASE2)   # the default build stops at the release
    if args.start:
        if args.start not in steps:
            sys.exit(f"--from {args.start}: not in this phase's step list")
        steps = steps[steps.index(args.start):]

    missing = [s for s in steps if not os.path.exists(os.path.join(HERE, s))]
    if missing:
        sys.exit(f"step scripts missing from {HERE}: {missing}")

    print(f"KIRD build root: {ROOT}")
    for i, script in enumerate(steps, 1):
        print(f"\n===== [{i}/{len(steps)}] {script} =====", flush=True)
        if subprocess.run([sys.executable, os.path.join(HERE, script)]).returncode != 0:
            sys.exit(f"Pipeline FAILED at step {i}: {script}")
        if script == RENAME_AFTER and args.phase != 1:
            rename_working_files()

    # The public code copies (04_dataset_release/code and the
    # kird-korea-immigration clone) were a hand-run sync and drifted twice —
    # nineteen files on 2026-08-17 and five pipeline steps on 2026-08-24, both
    # found by accident. Regenerate them every build; committing the two
    # repositories stays a human act.
    # 이 단계는 **작업 트리에만** 있다. 공개 번들(04_dataset_release/code 와
    # kird-korea-immigration)에는 sync_public_code.py 를 넣지 않으므로, 번들을
    # 받아 그대로 돌리면 여기서 「Pipeline FAILED」로 끝난다 — 앞의 마흔한 단계가
    # 다 성공해도 그렇다. 없으면 건너뛰고 왜 건너뛰는지 적는다.
    sync = os.path.join(HERE, "sync_public_code.py")
    if not os.path.exists(sync):
        print("\n===== sync public code copies: skipped =====", flush=True)
        print("sync_public_code.py is not part of the published bundle; "
              "it only runs in the authoring tree.", flush=True)
    else:
        print("\n===== sync public code copies =====", flush=True)
        if subprocess.run([sys.executable, sync]).returncode != 0:
            sys.exit("Pipeline FAILED at the public-code sync")
    print("\nPipeline complete: 05_dashboard/data/ and 04_dataset_release/ rebuilt.")


if __name__ == "__main__":
    main()
