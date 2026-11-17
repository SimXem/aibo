"""Paper figure style: sizes, fonts, and the dashboard's palette in hex.

The dashboard sets its colours as oklch() CSS variables (web/demo/00-head.html);
the hex values here are those variables converted to sRGB, so a series is the
same colour on the page and in the paper. Model colours come from
redlines.registry via each blob (never retyped here).

Two backends:

  pgf  (default) -- text is typeset by pdflatex, so the figure's type matches
                    the paper's. Needs a TeX install. --font picks the preamble.
  agg             -- no TeX; STIX (a Times-alike) via matplotlib. Used by the
                    tests and by anyone without TeX.

Call use() ONCE before importing pyplot anywhere.
"""
from __future__ import annotations

# Column widths, inches. A NeurIPS/ICLR-style single column is 3.25-3.5in;
# a full-width figure ~6.5in. Override per figure if the paper's class differs.
COL_W = 3.3
FULL_W = 6.5

# web/demo/00-head.html CSS variables -> sRGB hex.
INK = "#212730"          # --ink
INK_SOFT = "#575e69"     # --ink-soft
INK_FAINT = "#81868f"    # --ink-faint
LINE_SOFT = "#e3e5e8"    # --line-soft (lightened for print)
WARN = "#754b10"         # --warn-ink
DASH = "#14874e"         # --dash   (our models + retrieval)
SUPER = "#007daa"        # --super  (superforecasters)

PREAMBLES = {
    "cm": r"\usepackage[T1]{fontenc}\usepackage{lmodern}\usepackage{amsmath}",
    "times": r"\usepackage[T1]{fontenc}\usepackage{newtxtext,newtxmath}",
}

_STATE = {"backend": None}


def use(backend: str = "pgf", font: str = "cm") -> None:
    """Select the backend and apply the paper rcParams. Idempotent."""
    import matplotlib

    if backend not in ("pgf", "agg"):
        raise ValueError(f"backend must be pgf or agg, not {backend!r}")
    if font not in PREAMBLES:
        raise ValueError(f"font must be one of {sorted(PREAMBLES)}, not {font!r}")

    matplotlib.use(backend)
    rc = matplotlib.rcParams
    if backend == "pgf":
        rc["pgf.texsystem"] = "pdflatex"
        rc["pgf.rcfonts"] = False
        rc["pgf.preamble"] = PREAMBLES[font]
        rc["font.family"] = "serif"
    else:
        rc["font.family"] = "serif"
        rc["font.serif"] = ["STIX Two Text", "STIXGeneral", "Times New Roman", "DejaVu Serif"]
        rc["mathtext.fontset"] = "stix"

    rc.update({
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "axes.linewidth": 0.6,
        "axes.edgecolor": INK_SOFT,
        "axes.labelcolor": INK,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": LINE_SOFT,
        "grid.linewidth": 0.5,
        "lines.linewidth": 1.0,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,
        "figure.dpi": 150,
    })
    _STATE["backend"] = backend


def backend() -> str | None:
    return _STATE["backend"]


def esc(s: str) -> str:
    """Escape TeX specials in a plain-text label (outside math) under pgf.

    matplotlib's pgf backend escapes nothing, and a bare '%' in a tick label
    comments out the rest of the LaTeX line. Under agg the string is returned
    unchanged. Do not pass math ($...$) through this.
    """
    if _STATE["backend"] != "pgf":
        return s
    for a, b in (("\\", r"\textbackslash{}"), ("%", r"\%"), ("&", r"\&"),
                 ("#", r"\#"), ("_", r"\_")):
        s = s.replace(a, b)
    return s
