import argparse
from pathlib import Path

from dashboard import page, site
from .conditions import LABELS
from .results import load_runs
from .instrument import SOURCE, parse, synthetic, validate

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Build a local RSI survey preview.")
    parser.add_argument("--instrument", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mockup", type=Path, help="serve the supplied standalone design verbatim")
    mode.add_argument("--results", type=Path, help="parent directory of Baseline runs")
    mode.add_argument("--synthetic", action="store_true", help="exercise answer formats with made-up data")
    parser.add_argument("--publication", action="store_true", help="require complete runs, including both arms of paired runs")
    args = parser.parse_args()
    if args.publication and args.results is None:
        parser.error("--publication requires --results")
    if args.mockup:
        out = args.site or Path("site")
        site.write_site(out, args.mockup.read_text(encoding="utf-8"))
        site.verify(out)
        print(out / "index.html")
        return
    source = args.instrument.read_text(encoding="utf-8")
    sections = parse(source)
    instructions = source.split("## How to answer\n", 1)[1].split("\n## 1.", 1)[0].strip()
    runs = []
    if args.results:
        if not args.results.is_dir():
            parser.error(f"missing results directory: {args.results}")
        runs = load_runs(args.results, source, sections, args.publication)
    response = synthetic(sections) if args.synthetic else None
    if response:
        validate(sections, response)
        runs.append({"id": "synthetic", "web_access": "full-web", "date": None, "answers": response["answers"], "models": [
            {"id": "example", "label": "Example model", **response}]})
    out = args.site or Path("site-synthetic" if response else "site")
    html = page.render(ROOT / "web", {"SURVEY": {"instructions": instructions, "sections": sections, "conditions": LABELS, "runs": runs, "synthetic": bool(response)}})
    site.write_site(out, html)
    site.verify(out)
    print(out / "index.html")


if __name__ == "__main__":
    main()
