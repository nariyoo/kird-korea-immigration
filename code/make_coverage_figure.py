"""Year coverage and spatial resolution of every released file.

Reads the year span out of the released CSVs rather than a hand-kept list, so the
figure cannot fall behind the data. Writes into the release bundle and the public
code repository.
"""
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

from kird import RELEASE, RELEASE_DATA




# file -> (spatial resolution group, source ministry)
LAYOUT = [
    ("Sub-district", [("summary_by_eupmyeondong", "MOIS"),
                      ("multicultural_households", "MOIS")]),
    ("District",     [("summary_by_sigungu", "MOJ"),
                      ("nationality_by_sigungu", "MOJ"),
                      ("visa_by_sigungu", "MOJ"),
                      ("ethnic_enclaves", "MOJ"),
                      ("children_by_age", "MOIS")]),
    ("Province",     [("summary_by_sido", "MOJ")]),
    ("National",     [("national_annual", "MOJ"),
                      ("visa_by_nationality", "MOJ"),
                      ("age_sex_national", "MOJ"),
                      ("language_demand", "MOJ"),
                      ("segregation_by_nationality", "MOJ"),
                      ("region_segregation", "MOJ"),
                      ("naturalization_annual", "MOJ"),
                      ("naturalization_by_country", "MOJ"),
                      ("naturalization_by_age", "MOJ")]),
]

# 색과 글자는 이 폴더의 figstyle.py 에서 온다(논문 그림의 06_paper/_tools/figstyle.py
# 를 그대로 옮겨 둔 사본). 2026-09-25 까지는 sys.path 로 06_paper 를 가리켜서,
# 공개 저장소를 받은 사람은 이 단계에서 ModuleNotFoundError 로 멈췄다.
# MUTE(옅은 회색 글자)는 없앴다. 그림 안의 회색 글자는 인쇄에서 사라진다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import FULL, INK, NAVY as MOJ, RUST as MOIS, apply  # noqa: E402
apply()
RULE = "#e2e8f0"
MUTE = INK


def span(name):
    """(first, last) year in the released file; None for the single-year files."""
    df = pd.read_csv(os.path.join(RELEASE_DATA, name + ".csv"), encoding="utf-8-sig")
    if "year" not in df.columns:
        return None
    return int(df["year"].min()), int(df["year"].max())


def main():
    rows, latest = [], 0
    for group, files in LAYOUT:
        rows.append(("group", group, None, None))
        for name, src in files:
            yrs = span(name)
            rows.append(("file", name, yrs, src))
            if yrs:
                latest = max(latest, yrs[1])

    fig, ax = plt.subplots(figsize=(FULL, 5.6))
    ypos = list(range(len(rows)))[::-1]
    ylabels = []
    for (kind, name, yrs, src), y in zip(rows, ypos):
        if kind == "group":
            ylabels.append(name.upper())
            continue
        ylabels.append(name)
        colour = MOJ if src == "MOJ" else MOIS
        if yrs is None:                       # single year, no year column
            ax.plot([latest], [y], "o", ms=7, color=colour, zorder=3)
            ax.text(latest + 0.45, y, f"{latest}", va="center", fontsize=9, color=MUTE)
            continue
        y0, y1 = yrs
        ax.barh(y, y1 - y0, left=y0, height=0.52, color=colour, zorder=3)
        ax.text(y0 - 0.45, y, f"{y0}", ha="right", va="center", fontsize=9, color=MUTE)
        ax.text(y1 + 0.45, y, f"{y1}", ha="left", va="center", fontsize=9, color=MUTE)

    ax.set_yticks(ypos)
    ax.set_yticklabels(ylabels, fontsize=10.5)
    for lbl, (kind, *_ ) in zip(ax.get_yticklabels(), rows):
        if kind == "group":
            lbl.set_fontweight("bold")
            lbl.set_color(INK)
            lbl.set_fontsize(10)
        else:
            lbl.set_color(INK)
    ax.set_ylim(-0.9, len(rows) - 0.2)
    ax.set_xlim(2003.5, latest + 2.2)
    ax.set_xticks(range(2006, latest + 1, 2))
    ax.tick_params(axis="x", labelsize=10, colors=MUTE)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=RULE, linewidth=0.8)

    ax.legend(handles=[Patch(facecolor=MOJ, label="Ministry of Justice yearbook"),
                       Patch(facecolor=MOIS, label="Ministry of the Interior and Safety")],
              loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2,
              frameon=False, fontsize=10.5)

    fig.tight_layout()
    for d in (os.path.join(RELEASE, "figures"),
              os.path.join(RELEASE, "data deposit", "kird_dataset_github", "figures")):
        os.makedirs(d, exist_ok=True)
        fig.savefig(os.path.join(d, "file_coverage.png"), dpi=300,
                    bbox_inches="tight", pad_inches=0.15, facecolor="white")
        print("wrote", os.path.join(d, "file_coverage.png"))
    plt.close(fig)


if __name__ == "__main__":
    main()
