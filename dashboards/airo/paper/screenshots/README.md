# Dashboard screenshots

Real Chrome captures of the assembled `index.html`, cropped to two dashboard
views. The page's styling and data are unchanged. `capture.json` records the
capture date, input hash, source runs, viewport, crop bounds, and image hashes.

The September 10, 2026 captures show forecasts through September 8, matching
the manuscript's current data. These are snapshots, not automatically updating
images. When the paper's forecast data change, regenerate the dashboard,
`numbers.tex`, figures, and screenshots together, then update the caption dates.

Run from the repository root with Playwright and Google Chrome installed:

```sh
node code/capture_paper_screenshots.cjs
```

If Playwright is installed outside this repository, set `PLAYWRIGHT_MODULE` to
that package's absolute path. The script checks that all three embedded data
blobs match `results/` before capturing, and fails on browser runtime errors.

In Overleaf, copy `forecast-history.png` to
`fig/dashboard-forecast-history.png` and `frontier-capability.png` to
`fig/dashboard-frontier-capability.png`. They form Figure 1 near the beginning
of the introduction. Compile and visually inspect the figure and surrounding
pages after replacing either image; image dimensions can affect pagination.
