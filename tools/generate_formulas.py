"""Regenerate equation SVGs: pip install -r requirements-dev.txt, then run this script."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from formula_reference import FORMULA_EQUATIONS


def main():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import math_to_image

    matplotlib.rcParams.update({"mathtext.fontset": "stix", "svg.fonttype": "path",
                                "svg.hashsalt": "simple-circuits-formulas", "savefig.transparent": True})
    output = ROOT / "assets" / "formulas"
    output.mkdir(parents=True, exist_ok=True)
    for equations in FORMULA_EQUATIONS.values():
        for name, expression, _ in equations:
            path = output / (name + ".svg")
            math_to_image("$" + expression + "$", path, prop=FontProperties(size=15),
                          format="svg", color="#222222")
            # Drop the generation timestamp so repeated runs produce stable assets.
            import re
            text = path.read_text()
            text = re.sub(r"\s*<dc:date>.*?</dc:date>", "", text)
            path.write_text(text)
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
