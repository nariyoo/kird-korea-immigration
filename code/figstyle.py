# -*- coding: utf-8 -*-
"""Colours and type used by the figures of both papers, kept in one place.

When each figure carries its own colours, the same thing comes out in a different
colour in each figure. In practice the same series of the same data had been navy,
then teal, then the bright blue of the default palette. The colours are set here
and every figure script uses only these.

**Two colours.** Navy and rust orange. Their meaning is fixed so that they read the
same way everywhere in the papers.

    navy    MOJ registered foreigners ('등록외국인'), East Asian, enclave, "narrow definition"
    orange  MOIS broad definition, non-East Asian, plural destinations, "broad definition"

The two colours are used only to carry **a contrast within one figure**. With
several panels, all panels stay navy and the panel titles carry the distinction.
Painting different indicators in different colours creates a contrast that does
not exist. There is no third colour. With three series, use the light versions of
the two colours (STEEL, SAND) and grey. Ticks and axes are hairline grey lines, and
**all text is black**. Light grey text inside a figure disappears in print.

**Type size.** Never below 10 pt at design size. Full-width figures are built at
7.1 inches (180 mm), so text that is 10 pt there is also 10 pt on the printed page.

    from figstyle import NAVY, RUST, apply, save
"""
import os

import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

# ---------------------------------------------------------------- colours
INK = "#111111"          # all text
RULE = "#4a5568"         # axes and ticks
NAVY = "#1f4e79"
RUST = "#b5502a"
STEEL = "#7ea3c4"        # light version of navy
SAND = "#dca07e"         # light version of orange
GREY = "#9aa5b1"
PALE = "#c9d4dd"
FAINT = "#f2f3f4"

# Sequential ramps. Built from the two colours, so maps and line plots belong to
# the same family.
BLUES = ["#eaf0f6", "#c7d7e6", "#9dbad4", "#6f97be", "#42749f", "#1f4e79"]
RUSTS = ["#fbf0ea", "#f3d7c6", "#e8b494", "#d98f63", "#c66d3e", "#b5502a"]

# For several series. Past six, split the figure.
SERIES = [NAVY, RUST, STEEL, SAND, GREY, "#6b6b6b"]

# Figure sizes
FULL = 7.1               # journal full width, 180 mm
WIDE = 6.0               # tall maps
HALF = 3.4               # two side by side

# The release bundle carries its own copy of the typeface (fonts/, SIL Open Font
# License 1.1, see fonts/OFL.txt), so the figure steps run and give the same image
# on any machine. Until 2026-09-26 this list held four paths on the author's own
# computers and raised when none existed, which stopped run_pipeline.py at the
# first figure step for anyone else. The bundled files come first so that every
# machine draws with the same font file; an installed Pretendard is the fallback,
# and without either the figure is drawn in matplotlib's default sans-serif with a
# printed warning rather than an error.
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_BUNDLED = [os.path.join(_FONT_DIR, "Pretendard-Regular.otf"),
            os.path.join(_FONT_DIR, "Pretendard-Bold.otf")]
_INSTALLED = [
    os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/Pretendard-Regular.otf"),
    os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/PretendardVariable.ttf"),
    os.path.expanduser("~/Library/Fonts/Pretendard-Regular.otf"),
    os.path.expanduser("~/.local/share/fonts/Pretendard-Regular.otf"),
    "/usr/share/fonts/opentype/pretendard/Pretendard-Regular.otf",
]


def use_pretendard():
    """Register Pretendard and make it the default family. Returns the family used."""
    found = [p for p in _BUNDLED if os.path.exists(p)]
    if not found:
        found = [p for p in _INSTALLED if os.path.exists(p)][:1]
    if found:
        for p in found:
            fm.fontManager.addfont(p)
        name = fm.FontProperties(fname=found[0]).get_name()
        plt.rcParams["font.family"] = name
        return name
    print("figstyle: Pretendard not found (bundled fonts/ missing, none installed); "
          "drawing in matplotlib's default sans-serif. The image will differ from "
          "the released one in its type only.")
    plt.rcParams["font.family"] = "sans-serif"
    return "sans-serif"


def apply(base=10.0):
    """Set the same type and lines for every figure. Call once before drawing."""
    use_pretendard()
    plt.rcParams.update({
        "font.size": base,
        "axes.titlesize": base + 1,
        "axes.labelsize": base + 0.5,
        "xtick.labelsize": base,
        "ytick.labelsize": base,
        "legend.fontsize": base,
        "figure.titlesize": base + 1,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.edgecolor": RULE,
        "axes.linewidth": 0.7,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlelocation": "left",
        "axes.titlepad": 6,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })


def save(fig, path, dpi=300):
    """Write with a crop margin. Keeps rotated axis labels from being cut off."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return path

# ---------------------------------------------------------------- reading aids
def grid(ax, axis="x"):
    """Gridlines for reading values. Sent **behind the bars**, hairline width.

    Without gridlines the reader has to follow each bar end to the axis by eye. In
    journal figures this is the main reason a figure "looks simple" (2026-08-29).
    """
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color=FAINT, linewidth=0.8, zorder=0)
    ax.tick_params(length=0)


def label_bars(ax, bars, fmt="%.0f", pad=1.0, inside=False):
    """Write the value on each bar. Text is black and never below 10 pt."""
    for b in bars:
        w = b.get_width()
        if inside and w > 0:
            ax.text(w - pad, b.get_y() + b.get_height() / 2, fmt % w,
                    va="center", ha="right", color="white", fontsize=9.5)
        else:
            ax.text(w + pad, b.get_y() + b.get_height() / 2, fmt % w,
                    va="center", color=INK)


def spanner(ax, y0, y1, text, x=-0.02):
    """Hang the tier name vertically on the left so the grouping is visible.

    Even when the methods of one tier sit next to each other, the grouping is not
    visible without a name. The paper's argument is "it differs by tier", so a
    figure that does not show the tiers does not carry the argument.
    """
    ax.annotate("", xy=(x, y0), xytext=(x, y1), xycoords=("axes fraction", "data"),
                arrowprops=dict(arrowstyle="-", color=RULE, linewidth=0.9))
    ax.text(x - 0.008, (y0 + y1) / 2, text, transform=ax.get_yaxis_transform(),
            rotation=90, va="center", ha="right", color=INK, fontsize=9.5)


def note(ax, text, x=0.0, y=-0.16):
    """One-line note inside the figure. A short cue under the axis, not a caption."""
    ax.text(x, y, text, transform=ax.transAxes, va="top", color=INK,
            fontsize=9.5)
