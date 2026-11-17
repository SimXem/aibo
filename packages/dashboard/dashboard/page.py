"""A page is its source directory's chunks, in manifest order, with data spliced in.

    <page_dir>/manifest.json   {"chunks": ["00-head.html", ...], "blobs": ["NAME", ...]}

A blob NAME goes between the marker pair <!--NAME_DATA--><!--/NAME_DATA-->, as
window.__NAME__:

    <!--NAME_DATA-->
    <script>window.__NAME__ = {...};</script>
    <!--/NAME_DATA-->

render() builds a page; splice() replaces one blob in a page that exists;
blocks() and swap_frontend() read the data back out of a published page, so a
new interface can be published around data that stays byte-identical.
"""
import json
import re
from pathlib import Path

DATA_BLOCK = re.compile(rb'<!--([A-Z][A-Z0-9_]*_DATA)-->(.*?)<!--/\1-->', re.S)
DATA_MARKER = re.compile(rb'<!--(/?[A-Z][A-Z0-9_]*_DATA)-->')


def markers(name):
    return f"<!--{name}_DATA-->", f"<!--/{name}_DATA-->"


def block(name, blob):
    """The marker pair around window.__NAME__ = blob. "</" is escaped so a
    string in the data cannot close the script element."""
    start, end = markers(name)
    data = json.dumps(blob).replace("</", "<\\/")
    return f"{start}\n<script>window.__{name}__ = {data};</script>\n{end}"


def manifest(page_dir):
    return json.loads((Path(page_dir) / "manifest.json").read_text(encoding="utf-8"))


def skeleton(page_dir):
    """The page's chunks joined, with every marker pair as the source has it."""
    page_dir = Path(page_dir)
    return "".join((page_dir / name).read_text(encoding="utf-8") for name in manifest(page_dir)["chunks"])


def render(page_dir, blobs):
    """-> the page's text, with each of the manifest's blobs in its marker pair.
    Raises ValueError unless each pair is in the page exactly once."""
    html = skeleton(page_dir)
    for name in manifest(page_dir)["blobs"]:
        start, end = markers(name)
        text = block(name, blobs[name])
        html, n = re.subn(re.escape(start) + r".*?" + re.escape(end), lambda m: text, html, count=1, flags=re.S)
        if n != 1:
            raise ValueError(f"{page_dir}: the marker pair for {name!r} is not in the page exactly once (found {n})")
    return html


def splice(html, name, blob):
    """-> html with blob NAME replaced where its marker pair is, else added at
    the end of <head>."""
    start, end = markers(name)
    text = block(name, blob)
    if start in html:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda m: text, html, flags=re.S)
    return html.replace("</head>", text + "\n</head>", 1)


def blocks(html):
    """{NAME_DATA: the whole block's bytes} for a published page (bytes).
    Raises RuntimeError on a missing, duplicated or malformed block."""
    matches = list(DATA_BLOCK.finditer(html))
    found = DATA_MARKER.findall(html)
    expected = [tag for match in matches for tag in (match[1], b'/' + match[1])]
    if not matches or found != expected or len({m[1] for m in matches}) != len(matches):
        raise RuntimeError('Invalid or duplicate dashboard data markers')
    for match in matches:
        name = match[1].removesuffix(b'_DATA')
        assignment = re.fullmatch(rb'\s*<script>\s*window\.__' + name + rb'__\s*=\s*(.*?)\s*;\s*</script>\s*', match[2], re.S)
        if not assignment:
            raise RuntimeError('Invalid dashboard data assignment: ' + name.decode())
        json.loads(assignment[1])
    return {m[1].decode(): m[0] for m in matches}


def swap_frontend(template, published):
    """The new interface (template) around the published page's data, byte for
    byte. Raises RuntimeError if the two do not carry the same blocks."""
    old, new = blocks(published), blocks(template)
    if old.keys() != new.keys():
        raise RuntimeError('Dashboard data blocks changed; publish validated data or migrate the snapshot explicitly')
    return DATA_BLOCK.sub(lambda m: old[m[1].decode()], template)
