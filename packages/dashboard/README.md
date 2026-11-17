# dashboard: the kit every dashboard's site is made of

A dashboard turns its own runs into **blobs** (the JSON its page reads) and
**tables** (the rows of its download). The kit does the rest, and knows nothing
about forecasts. Stdlib only.

```python
from dashboard import page, download, site

html = page.render("web/", {"EEAI": blob})                 # chunks in manifest order, data spliced in
names = download.bundle("site/data.zip", [                 # the zip behind "Download data"
    ("README.md", readme),
    ("forecasts.csv", download.csv_text(columns, rows)),
    ("runs/2026-11-11.jsonl", Path("results/runs/2026-11-11.jsonl")),
])
site.write_site("site/", html, assets={"web/img": "web/img"})
site.verify("site/", required=("data.zip",))               # raises unless complete
site.snapshot("site/", files=("data.zip",))                # what it publishes, hashed
```

| | in | out |
|---|---|---|
| `page.render` | a source directory, `{NAME: blob}` | the page's text |
| `page.splice` | a page's text, a name, a blob | the text with that blob replaced |
| `page.blocks` | a published page's bytes | `{NAME_DATA: the block's bytes}` |
| `page.swap_frontend` | a new page, the published page | the new page around the published data, byte for byte |
| `download.csv_text` | columns, rows | CSV text |
| `download.bundle` | a path, `[(name, text, bytes or Path)]` | the zip's member names |
| `site.write_site` | a folder, the page's text, `{path in site: source dir}` | the folder |
| `site.verify` | a folder, required file names | nothing; raises if incomplete |
| `site.snapshot` | a folder, file names | `{blocks, files, sha256}` |

A page's source directory holds `manifest.json` (`{"chunks": [...], "blobs": [...]}`)
and the chunks. A blob `NAME` goes between `<!--NAME_DATA-->` and
`<!--/NAME_DATA-->` as `window.__NAME__`.

What a dashboard still writes itself: its questions and prompt, its run, the
view from its rows to blobs and tables, and the page's HTML, CSS and JS.

Users: `dashboards/airo` (`redlines.pages`, `redlines.hydrate`,
`redlines.export`), `dashboards/eeai` (`eeai.build`, `eeai.export`) and the
production scheduler (`packages/ops`), which reads published data through it.
