"""The dashboard kit: a page from its chunks and data, the download, the site folder."""
import json
import zipfile

import pytest

from dashboard import download, page, site


@pytest.fixture
def source(tmp_path):
    d = tmp_path / "web"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"chunks": ["a.html", "b.html"], "blobs": ["ONE", "TWO"]}))
    (d / "a.html").write_text("<html><head><!--ONE_DATA--><!--/ONE_DATA-->")
    (d / "b.html").write_text("<!--TWO_DATA-->\nstale\n<!--/TWO_DATA--></head><body>page</body></html>")
    return d


def test_render_splices_each_blob_into_its_marker_pair(source):
    html = page.render(source, {"ONE": {"n": 1}, "TWO": ["</script>"]})
    assert '<!--ONE_DATA-->\n<script>window.__ONE__ = {"n": 1};</script>\n<!--/ONE_DATA-->' in html
    assert "stale" not in html and '["<\\/script>"]' in html   # data cannot close the script element
    assert page.skeleton(source).count("stale") == 1            # the source is not written to


def test_render_refuses_a_page_without_the_marker_pair(source):
    (source / "a.html").write_text("<html><head>")
    with pytest.raises(ValueError, match="'ONE'"):
        page.render(source, {"ONE": 1, "TWO": 2})


def test_splice_replaces_a_blob_or_adds_it_to_the_head(source):
    html = page.render(source, {"ONE": 1, "TWO": 2})
    assert "window.__ONE__ = 5;" in page.splice(html, "ONE", 5) and "window.__ONE__ = 1;" not in page.splice(html, "ONE", 5)
    added = page.splice(html, "NEW", {"x": 1})
    assert added.index("<!--NEW_DATA-->") < added.index("</head>")


def test_a_new_frontend_keeps_the_published_data_byte_for_byte(source):
    published = page.render(source, {"ONE": {"v": 1}, "TWO": 2}).encode()
    (source / "b.html").write_text("<!--TWO_DATA--><!--/TWO_DATA--></head><body>new layout</body></html>")
    template = page.render(source, {"ONE": {"v": 999}, "TWO": 999}).encode()
    swapped = page.swap_frontend(template, published)
    assert b"new layout" in swapped and page.blocks(swapped) == page.blocks(published)
    with pytest.raises(RuntimeError, match="blocks changed"):
        page.swap_frontend(template.replace(b"TWO", b"TOO"), published)
    with pytest.raises(RuntimeError, match="markers"):
        page.blocks(b"<html>no data</html>")


def test_the_download_keeps_its_members_in_order(tmp_path):
    (tmp_path / "raw.jsonl").write_text("{}\n")
    text = download.csv_text(["a", "b"], [[1, "x,y"], [2, None]])
    assert text == 'a,b\n1,"x,y"\n2,\n'
    names = download.bundle(tmp_path / "out/data.zip", [("README.md", "read me"), ("t.csv", text), ("raw/raw.jsonl", tmp_path / "raw.jsonl")])
    assert names == ["README.md", "t.csv", "raw/raw.jsonl"]
    with zipfile.ZipFile(tmp_path / "out/data.zip") as z:
        assert z.read("t.csv").decode() == text and z.read("raw/raw.jsonl") == b"{}\n"


def test_a_site_is_written_checked_and_hashed(source, tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img/logo.svg").write_text("<svg/>")
    html = page.render(source, {"ONE": 1, "TWO": 2})
    out = site.write_site(tmp_path / "site", html, assets={"web/img": tmp_path / "img", "web/fonts": tmp_path / "absent"})
    assert (out / "web/img/logo.svg").exists() and not (out / "web/fonts").exists()
    with pytest.raises(RuntimeError, match="data.zip"):
        site.verify(out, required=("data.zip",))
    (out / "data.zip").write_bytes(b"zip")
    site.verify(out, required=("data.zip",))
    first = site.snapshot(out, files=("data.zip", "absent.csv"))
    assert set(first["blocks"]) == {"ONE_DATA", "TWO_DATA"} and set(first["files"]) == {"data.zip"}
    (out / "index.html").write_text(page.splice(html, "ONE", 7))
    assert site.snapshot(out, files=("data.zip",))["sha256"] != first["sha256"]
    (out / "link").symlink_to(out / "data.zip")
    with pytest.raises(RuntimeError, match="symlinks"):
        site.verify(out)
