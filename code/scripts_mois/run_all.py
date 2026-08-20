"""Run the full MOIS pipeline end-to-end.

Order is sequential because consolidate.py depends on outputs from the earlier steps.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STEPS = [
    "parse_2006.py",
    "parse_2007_2010.py",
    "parse_2011_2013.py",
    "parse_2014_2015.py",
    "parse_2016plus.py",
    "parse_nationality.py",
    "parse_children_age.py",
    "parse_extras.py",
    "consolidate.py",
    "extract_total_pop.py",       # 주민등록인구 추출 (외국인 비율 계산용 denominator)
    "tidy_consolidate.py",        # 39 fragmented files → 7 tidy thematic CSVs
    "extract_bcnt_codes.py",      # in-house BCNT lookup from 2015 helper files
]


def main():
    py = sys.executable
    for step in STEPS:
        print(f"\n{'='*60}\nRunning {step}\n{'='*60}")
        r = subprocess.run([py, str(HERE / step)], capture_output=False)
        if r.returncode != 0:
            print(f"\nABORTED: {step} returned {r.returncode}")
            sys.exit(r.returncode)
    print("\nAll steps completed.")


if __name__ == "__main__":
    main()
