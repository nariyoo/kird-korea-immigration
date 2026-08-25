# -*- coding: utf-8 -*-
"""공개 저장소가 싣는 그림을 논문 그림과 같은 것으로 맞춘다.

저장소 README 가 거는 그림 셋 가운데 둘은 2026-06 에 한 번 짓고 그 뒤로 손대지
않은 것이었다. 자료가 두 번 바뀌고 색 규칙이 생기는 동안 그림만 그 자리에
있었다. 같은 것을 두 벌 그리면 반드시 갈라지므로, 논문 그림을 그대로 가져다
저장소 이름으로 놓는다. 원본은 하나다.

    overview_maps.png  <- 01_data_descriptor/.../fig3_twolayer.png
    moj_vs_mois.png    <- 01_data_descriptor/.../fig_moj_mois.png

`file_coverage.png` 는 배포본 CSV 에서 연도를 읽어 짓는 그림이라
`make_coverage_figure.py` 가 따로 만든다.

    python 02_code/sync_repo_figures.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kird import RELEASE, ROOT          # noqa: E402

SRC = os.path.join(ROOT, "06_paper", "01_data_descriptor", "2_tables_and_figures")
TARGETS = [
    os.path.join(RELEASE, "figures"),
    os.path.join(RELEASE, "data deposit", "kird_dataset_github", "figures"),
]

# 논문 파일 -> 저장소 이름. README 가 거는 이름이므로 바꾸지 않는다.
PAIRS = [
    ("fig3_twolayer.png", "overview_maps.png"),
    ("fig_moj_mois.png", "moj_vs_mois.png"),
]


def newest_release_csv():
    """배포본에서 가장 나중에 쓰인 CSV 의 시각. 그림이 자료보다 낡았는지 잰다."""
    d = os.path.join(RELEASE, "data")
    ts = [os.path.getmtime(os.path.join(d, f))
          for f in os.listdir(d) if f.endswith(".csv")]
    return max(ts) if ts else 0


def main():
    missing = [a for a, _ in PAIRS if not os.path.exists(os.path.join(SRC, a))]
    if missing:
        print("논문 그림이 아직 없다: %s" % missing)
        print("먼저 06_paper/01_data_descriptor/1_data_and_code 의 make_sd_*.py 를 돌린다.")
        return 0
    # 논문 그림이 자료보다 낡았으면 낡은 그림을 저장소로 옮기게 된다. 조용히
    # 넘어가지 않고 알린다.
    data_t = newest_release_csv()
    stale = [a for a, _ in PAIRS
             if os.path.getmtime(os.path.join(SRC, a)) < data_t]
    if stale:
        print("!! 자료보다 낡은 그림: %s" % stale)
        print("   make_sd_twolayer.py / make_sd_moj_mois.py 를 먼저 다시 돌린다.")
    n = 0
    for dst_dir in TARGETS:
        if not os.path.isdir(dst_dir):
            print("  폴더가 없다:", dst_dir)
            continue
        for a, b in PAIRS:
            src = os.path.join(SRC, a)
            dst = os.path.join(dst_dir, b)
            same = (os.path.exists(dst)
                    and os.path.getsize(dst) == os.path.getsize(src))
            shutil.copyfile(src, dst)
            print("  %-34s <- %-22s %s" % (b, a, "" if same else "(바뀜)"))
            n += 0 if same else 1
    print()
    print("%d개를 새 그림으로 바꿨다" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
