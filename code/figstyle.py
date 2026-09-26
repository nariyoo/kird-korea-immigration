# -*- coding: utf-8 -*-
"""두 논문의 그림이 쓰는 색과 글자를 한 곳에 둔다.

그림마다 자기 색을 들고 있으면 같은 것이 그림마다 다른 색으로 나온다. 실제로
같은 자료의 같은 계열이 남색이었다가 청록이었다가 기본 팔레트의 형광 파랑이
되어 있었다. 여기서 정하고 모든 그림 스크립트가 이것만 쓴다.

**두 색.** 남색과 녹슨 주황 둘로 간다. 뜻을 고정해서 논문 어디서나 같게 읽히게
한다.

    남색  법무부 등록외국인, 동아시아, 집거지, 「좁은 정의」
    주황  행정안전부 광의 정의, 비(非)동아시아, 다원 목적지, 「넓은 정의」

두 색은 **한 그림 안의 대비**를 나르는 데만 쓴다. 패널이 여럿이면 전부 남색으로
두고 구별은 패널 제목이 나른다. 서로 다른 지표를 색으로 칠하면 없는 대비를
만들어 낸다. 셋째 색은 두지 않는다. 계열이 셋이면 두 색의 옅은 판(STEEL, SAND)과 회색으로
간다. 눈금과 축은 머리카락 굵기의 회색 선이고, **글자는 전부 검정**이다. 그림
안의 옅은 회색 글자는 인쇄에서 사라진다.

**글자 크기.** 설계 크기에서 10 pt 아래로 내려가지 않는다. 전폭 그림은 7.1인치
(180 mm)로 짓고, 그 안에서 10 pt 인 글자가 인쇄면에서도 10 pt 다.

    from figstyle import NAVY, RUST, apply, save
"""
import os

import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

# ---------------------------------------------------------------- 색
INK = "#111111"          # 모든 글자
RULE = "#4a5568"         # 축과 눈금
NAVY = "#1f4e79"
RUST = "#b5502a"
STEEL = "#7ea3c4"        # 남색의 옅은 판
SAND = "#dca07e"         # 주황의 옅은 판
GREY = "#9aa5b1"
PALE = "#c9d4dd"
FAINT = "#f2f3f4"

# 순차 색계단. 두 색에서 뽑아 만들었으므로 지도와 선그림이 같은 집안이 된다.
BLUES = ["#eaf0f6", "#c7d7e6", "#9dbad4", "#6f97be", "#42749f", "#1f4e79"]
RUSTS = ["#fbf0ea", "#f3d7c6", "#e8b494", "#d98f63", "#c66d3e", "#b5502a"]

# 계열이 여럿일 때. 여섯을 넘으면 그림을 나눈다.
SERIES = [NAVY, RUST, STEEL, SAND, GREY, "#6b6b6b"]

# 판 크기
FULL = 7.1               # 학술지 전폭 180 mm
WIDE = 6.0               # 세로가 긴 지도
HALF = 3.4               # 두 개를 나란히

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
    """모든 그림에 같은 글자와 선을 세운다. 그리기 전에 한 번 부른다."""
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
    """자르기 여유를 두고 쓴다. 회전한 축 이름이 잘려 나가는 것을 막는다."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return path

# ---------------------------------------------------------------- 읽기 보조
def grid(ax, axis="x"):
    """값을 읽을 눈금선. **막대 뒤로** 보내고 머리카락 굵기로 둔다.

    눈금선이 없으면 독자가 막대 끝을 축까지 눈으로 좇아야 한다. 학술지 그림에서
    이것이 「단순해 보이는」 가장 큰 까닭이다 (2026-08-29).
    """
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color=FAINT, linewidth=0.8, zorder=0)
    ax.tick_params(length=0)


def label_bars(ax, bars, fmt="%.0f", pad=1.0, inside=False):
    """막대마다 값을 적는다. 글자는 검정, 10 pt 아래로 안 내려간다."""
    for b in bars:
        w = b.get_width()
        if inside and w > 0:
            ax.text(w - pad, b.get_y() + b.get_height() / 2, fmt % w,
                    va="center", ha="right", color="white", fontsize=9.5)
        else:
            ax.text(w + pad, b.get_y() + b.get_height() / 2, fmt % w,
                    va="center", color=INK)


def spanner(ax, y0, y1, text, x=-0.02):
    """층 이름을 왼쪽에 세로로 걸어 묶음을 보이게 한다.

    같은 층의 방식들이 붙어 있어도 이름이 없으면 묶음이 안 보인다. 논문의
    논거가 「층마다 다르다」인데 그림이 층을 안 보여 주면 그림이 논거를 안
    나르는 것이다.
    """
    ax.annotate("", xy=(x, y0), xytext=(x, y1), xycoords=("axes fraction", "data"),
                arrowprops=dict(arrowstyle="-", color=RULE, linewidth=0.9))
    ax.text(x - 0.008, (y0 + y1) / 2, text, transform=ax.get_yaxis_transform(),
            rotation=90, va="center", ha="right", color=INK, fontsize=9.5)


def note(ax, text, x=0.0, y=-0.16):
    """그림 안의 한 줄 설명. 캡션이 아니라 축 밑의 짧은 단서다."""
    ax.text(x, y, text, transform=ax.transAxes, va="top", color=INK,
            fontsize=9.5)
