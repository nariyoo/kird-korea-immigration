# -*- coding: utf-8 -*-
"""The three repository figures, drawn from the build's own outputs.

    overview_maps.png       foreign share and nationality diversity by district,
                            2009 / 2014 / 2019 / 2024 (indices.json, korea_sigungu.json)
    moj_vs_mois.png         the two population definitions, nationally and by district
                            (summary_by_sigungu.csv)
    pipeline_flowchart.png  how the dataset is built (counts the released tables)

Until 2026-09-26 these were copied by sync_repo_figures.py out of the data
descriptor's working folder (06_paper/01_data_descriptor/2_tables_and_figures),
which is not part of the release, the deposit or the public repository. On any
other machine that step printed a note and returned 0, so the published figures
could never be rebuilt from the published code. The drawing code of the three
paper scripts (make_sd_twolayer.py, make_sd_moj_mois.py, make_sd_flowchart.py)
now lives here, reads only what run_pipeline.py has just built, and takes its
type from the bundled font through figstyle.py.

    python make_repo_figures.py
"""
import csv
import json
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                       # noqa: E402
import numpy as np                                                    # noqa: E402
from matplotlib.cm import ScalarMappable                              # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize      # noqa: E402
from matplotlib.patches import FancyArrow, Rectangle                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kird import RELEASE, RELEASE_DATA, SITE_DATA                     # noqa: E402
from figstyle import BLUES, FULL, INK, NAVY, RUST, RUSTS, apply       # noqa: E402

TARGETS = [
    os.path.join(RELEASE, "figures"),
    os.path.join(RELEASE, "data deposit", "kird_dataset_github", "figures"),
]
EN = chr(8211)
# PNG metadata carries the matplotlib version and nothing that changes per run,
# so the same inputs give the same bytes.
PNG_META = {"Software": None}


def save_all(fig, name, pad=0.15):
    for d in TARGETS:
        os.makedirs(d, exist_ok=True)
        fig.savefig(os.path.join(d, name), dpi=300, bbox_inches="tight",
                    pad_inches=pad, facecolor="white", metadata=PNG_META)
    plt.close(fig)
    print("wrote", name)


# ------------------------------------------------------------------ overview maps
def overview_maps():
    import geopandas as gpd

    years = [2009, 2014, 2019, 2024]
    nodata = "#e9ecef"
    idx = json.load(open(os.path.join(SITE_DATA, "indices.json"), encoding="utf-8"))["data"]
    geo = gpd.read_file(os.path.join(SITE_DATA, "korea_sigungu.json"))

    def k(sido, sigungu):
        return sido + "|" + sigungu.replace(" ", "")

    def layer(year, fld):
        rows = idx["by_sigungu"][str(year)]
        v = {k(r["sido"], r["sigungu"]): r.get(fld) for r in rows if r.get(fld) is not None}
        if fld == "foreign_share_pct":
            bu = [r for r in rows if r["sido"] == "경기도" and r["sigungu"].startswith("부천시")]
            if bu:
                f = sum(r["foreign_total"] for r in bu)
                p = sum(r.get("total_pop") or 0 for r in bu)
                if p:
                    v[k("경기도", "부천시")] = round(f / p * 100, 2)
        # Sejong has no districts; its one polygon takes the province value
        sj = next((s for s in idx["by_sido"][str(year)]
                   if s["sido"] == "세종특별자치시"), None)
        if sj and sj.get(fld) is not None:
            v[k("세종특별자치시", "세종시")] = sj[fld]
        # polygons that did not yet exist take the value their parent published
        # (Changwon's gu before the 2010 merger; 청주시 서원구 before 2014)
        parent_of = {
            k("경상남도", "창원시 의창구"): ("경상남도", "창원시"),
            k("경상남도", "창원시 성산구"): ("경상남도", "창원시"),
            k("경상남도", "창원시 마산합포구"): ("경상남도", "마산시"),
            k("경상남도", "창원시 마산회원구"): ("경상남도", "마산시"),
            k("충청북도", "청주시 서원구"): ("충청북도", "청주시 흥덕구"),
        }
        by_key = {k(r["sido"], r["sigungu"]): r for r in rows}
        for kk, (psido, psg) in parent_of.items():
            if kk in v:
                continue
            parent = by_key.get(k(psido, psg))
            if parent and parent.get(fld) is not None:
                v[kk] = parent[fld]
        return v

    layers = [("Foreign share of residents (%)", "foreign_share_pct", RUSTS),
              ("Nationality diversity (Shannon H)", "shannon_H", BLUES)]
    fig, axes = plt.subplots(2, len(years), figsize=(FULL, 4.9))
    for ri, (rlabel, fld, cname) in enumerate(layers):
        maps = {y: layer(y, fld) for y in years}
        pool = np.array([x for y in years for x in maps[y].values()], float)
        nm = Normalize(vmin=np.percentile(pool, 2), vmax=np.percentile(pool, 98))
        cmap = LinearSegmentedColormap.from_list("kird", cname[1:])
        for ci, y in enumerate(years):
            ax = axes[ri, ci]
            m = maps[y]
            geo["c"] = [cmap(nm(m[kk])) if m.get(kk) is not None else nodata
                        for kk in geo["match_key"]]
            geo.plot(ax=ax, color=geo["c"], edgecolor="white", linewidth=0.1)
            ax.set_axis_off()
            if ri == 0:
                ax.set_title(str(y), fontsize=10, color=INK, pad=3, loc="center")
        axes[ri, 0].text(-0.04, 0.5, rlabel, transform=axes[ri, 0].transAxes,
                         rotation=90, ha="right", va="center", fontsize=10, color=INK)
        sm = ScalarMappable(norm=nm, cmap=cmap)
        sm.set_array([])
        cax = fig.add_axes([0.33, 0.545 - ri * 0.475, 0.36, 0.018])
        cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
        cb.ax.tick_params(labelsize=10, length=2, colors=INK)
        cb.outline.set_visible(False)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.94, bottom=0.06,
                        hspace=0.02, wspace=0.02)
    save_all(fig, "overview_maps.png", pad=0.12)


# ------------------------------------------------------------------ MOJ vs MOIS
def moj_vs_mois():
    src = os.path.join(RELEASE_DATA, "summary_by_sigungu.csv")
    reg, broad, ratios = defaultdict(float), defaultdict(float), defaultdict(list)
    for r in csv.DictReader(open(src, encoding="utf-8-sig")):
        a, b = r.get("registered_foreigners") or "", r.get("broad_total") or ""
        try:
            a, b = float(a), float(b)
        except ValueError:
            continue
        if a > 0 and b > 0:
            reg[r["year"]] += a
            broad[r["year"]] += b
            ratios[r["year"]].append(b / a)
    years = sorted(reg, key=int)
    yi = [int(y) for y in years]
    plt.rcParams.update({"font.size": 12})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FULL, 3.05))
    mj = [reg[y] / 1e6 for y in years]
    ms = [broad[y] / 1e6 for y in years]
    ax1.fill_between(yi, mj, ms, color="#cbd5e1", alpha=0.5, zorder=1)
    ax1.plot(yi, mj, "-o", color=NAVY, lw=2.2, ms=4, label="MOJ registered", zorder=3)
    ax1.plot(yi, ms, "-o", color=RUST, lw=2.2, ms=4, label="MOIS broad definition",
             zorder=3)
    ax1.annotate("×%.1f" % (broad[years[-1]] / reg[years[-1]]),
                 xy=(yi[-1], (mj[-1] + ms[-1]) / 2),
                 xytext=(yi[-1] - 2.6, (mj[-1] + ms[-1]) / 2), fontsize=10, color=INK,
                 va="center", fontweight="bold")
    ax1.set_ylabel("Foreign residents (millions)")
    ax1.set_xlabel("Year")
    ax1.set_xticks(range(2008, yi[-1] + 1, 4))
    ax1.set_ylim(top=max(ms) * 1.22)
    ax1.legend(loc="upper left", frameon=False, handlelength=1.5, borderaxespad=0.4,
               labelspacing=0.35, fontsize=10)
    ax1.set_title("(a) National totals by definition", loc="left")
    bp = ax2.boxplot([ratios[y] for y in years], positions=yi, widths=0.7,
                     patch_artist=True, showfliers=False,
                     medianprops=dict(color=INK, lw=1.2))
    for patch in bp["boxes"]:
        patch.set(facecolor="#f3d7c6", edgecolor=RUST, linewidth=0.9)
    for w in bp["whiskers"] + bp["caps"]:
        w.set(color=RUST, linewidth=0.9)
    ax2.axhline(1.0, color="#94a3b8", ls="--", lw=1, zorder=0)
    ax2.set_ylabel("MOIS broad ÷ MOJ registered")
    ax2.set_xlabel("Year")
    ax2.set_xticks(range(2008, yi[-1] + 1, 4))
    ax2.set_xticklabels(range(2008, yi[-1] + 1, 4))
    ax2.set_title("(b) District-level ratio distribution", loc="left")
    fig.tight_layout()
    save_all(fig, "moj_vs_mois.png")
    apply()                                   # undo the local font.size


# ------------------------------------------------------------------ flowchart
def pipeline_flowchart():
    source, extract, transform = BLUES[1], "#ffffff", "#eceff1"
    derived, final, edge = RUSTS[1], RUSTS[3], "#5a6672"
    n = len([f for f in os.listdir(RELEASE_DATA) if f.endswith(".csv")])
    head = dict(width=0.004, head_width=0.10, head_length=0.11,
                length_includes_head=True, color=edge, zorder=1)

    def box(ax, x, y, w, h, text, fill, size=10):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=edge,
                               linewidth=0.8, zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
                color=INK, zorder=3, linespacing=1.35)
        return (x, y, w, h)

    def arrow(ax, a, b, bx=None):
        x = a[0] + a[2] * 0.5 if bx is None else bx
        ax.add_patch(FancyArrow(x, a[1], 0, (b[1] + b[3]) - a[1], **head))

    def line(ax, x0, y0, x1, y1):
        ax.plot([x0, x1], [y0, y1], color=edge, lw=0.9, zorder=1, solid_capstyle="butt")

    def bus(ax, tops, target, gap=0.22):
        y = target[1] + target[3] + gap
        xs = [t[0] + t[2] / 2 for t in tops]
        for t, x in zip(tops, xs):
            line(ax, x, t[1], x, y)
        line(ax, min(xs), y, max(xs), y)
        xm = (min(xs) + max(xs)) / 2
        ax.add_patch(FancyArrow(xm, y, 0, -gap, **head))
        return xm

    fig, ax = plt.subplots(figsize=(FULL, 6.7))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.75, 10)
    ax.set_axis_off()
    W, H = 3.10, 0.86
    C1, C2, C3 = 0.0, 3.45, 6.90
    FW = 10.0
    r1 = box(ax, C1, 8.95, W, H, "MOJ immigration yearbook,\n2006" + EN + "2024", source)
    r2 = box(ax, C2, 8.95, W, H, "MOIS foreign-resident\nstatus, 2006" + EN + "2024", source)
    r3 = box(ax, C3, 8.95, W, H, "MOIS resident-registration\npopulation", source)
    e1 = box(ax, C1, 7.65, W, H, "Parse nationality, visa,\ndistrict, age and sex", extract)
    e2 = box(ax, C2, 7.65, W, H, "Parse composition,\nchildren, households", extract)
    e3 = box(ax, C3, 7.65, W, H, "Extract the district\npopulation denominator", extract)
    t1 = box(ax, C1, 6.35, W, H, "Harmonize nationality,\nvisa and district labels",
             transform)
    t2 = box(ax, C2, 6.35, W, H, "Reconcile boundaries,\napportion 2008" + EN + "15 gu rows",
             transform)
    d1 = box(ax, C1, 5.05, W, H, "Harmonized foreign-\nresident counts", derived)
    d2 = box(ax, C2, 5.05, W, H, "Broad-definition residents\nand settlement mix", derived)
    d3 = box(ax, C3, 5.05, W, H, "District population\ndenominator", derived)
    aux = box(ax, C1, 3.55, 2.70, 1.05,
              "Auxiliary inputs:\nEthnologue 24 shares,\nSGIS boundaries", source)
    m1 = box(ax, 3.05, 3.55, 6.95, 1.05,
             "Derive diversity, segregation,\nethnic-enclave, settlement and "
             "language measures", transform)
    m2 = box(ax, C1, 2.05, FW, H,
             "Validate against the published totals, across the two sources, and "
             "by backcasting", transform)
    fin = box(ax, C1, 0.75, FW, H,
              "KIRD: %d tidy bilingual CSV tables, with the data dictionary and "
              "the build code" % n, final)
    for a_, b_ in ((r1, e1), (r2, e2), (r3, e3), (e1, t1), (e2, t2),
                   (t1, d1), (t2, d2), (e3, d3)):
        arrow(ax, a_, b_)
    spine = bus(ax, (d1, d2, d3), m1)
    arrow(ax, m1, m2, bx=spine)
    arrow(ax, m2, fin, bx=spine)
    ax.add_patch(FancyArrow(aux[0] + aux[2], aux[1] + aux[3] / 2,
                            m1[0] - (aux[0] + aux[2]), 0, **head))
    rows = [(("Official source", source), ("Reading the source", extract),
             ("Harmonizing step", transform)),
            (("Intermediate table", derived), ("Released dataset", final))]
    for kk, row in enumerate(rows):
        y = 0.15 - kk * 0.52
        x = 0.0
        for lab, col in row:
            ax.add_patch(Rectangle((x, y - 0.13), 0.34, 0.26, facecolor=col,
                                   edgecolor=edge, linewidth=0.8))
            ax.text(x + 0.46, y, lab, fontsize=10, color=INK, va="center")
            x += 3.45
    save_all(fig, "pipeline_flowchart.png")


def main():
    apply()
    overview_maps()
    moj_vs_mois()
    pipeline_flowchart()
    return 0


if __name__ == "__main__":
    sys.exit(main())
