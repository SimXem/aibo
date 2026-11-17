"""Generic dashboard hydration: inject window.__<NAME>__ data blobs into the live demo.

Every graph is fed the same way: a materializer computes a JSON blob from
committed results, then splices it into index.html between HTML comment
markers so re-runs replace (never duplicate) the data:

    from redlines.hydrate import inject
    inject("GRAPH1", blob, json_out="results/graph1_data.json")

produces, inside <head>:

    <!--GRAPH1_DATA-->
    <script>window.__GRAPH1__ = {...};</script>
    <!--/GRAPH1_DATA-->

The React app reads window.__GRAPH1__ and falls back to the mock (dimmed) panel
when absent. The page itself is a build artifact assembled from web/demo/
(redlines.pages); inject() only ever rewrites an existing page.

Moved from code/hydrate.py; code/hydrate.py is now a thin shim re-exporting
this module's names. Two behaviors here are deliberate 2026-08 hardening
changes versus the original inject():

  * '</' in the serialized blob is escaped to '<\\/' in the emitted <script>
    block only — a blob string containing "</script>" can no longer terminate
    the block early. The json_out mirror is NOT escaped: it is a plain JSON
    file, not HTML, and must stay byte-comparable with json.loads round-trips.
    Blobs containing no '</' (all of them, today) serialize identically.
  * A missing target raises FileNotFoundError. (Until 2026-09-10 the default
    page was seeded from the original mock dashboard, now archive/jason-demo.html;
    `python3 -m redlines assemble` is the way to create the page.)
"""
import json
from pathlib import Path

from . import config  # noqa: F401  (puts packages/dashboard on the path)
from dashboard import page as _kit

REPO = Path(__file__).resolve().parent.parent
LIVE = REPO / "index.html"


def inject(name, blob, html_path=LIVE, json_out=None):
    """Splice window.__<name>__ = <blob> into the live html (replace or insert
    at end of <head>). Optionally mirror the blob to json_out for inspection/
    diffing. Returns the html path written."""
    path = Path(html_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist; build it with `python3 -m redlines assemble` "
            "(web/demo/ is the page source) before injecting blobs")
    path.write_text(_kit.splice(path.read_text(), name, blob))
    if json_out:
        out = REPO / json_out
        out.write_text(json.dumps(blob, indent=2) + "\n")
    return path
