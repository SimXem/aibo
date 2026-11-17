"""Render the n-th <svg> of a server-rendered page (ssr.js DUMP output) to PNG,
CSS variables filled from the page's :root. Needs cairosvg (pip, any venv).

    python svgpng.py <page.html> <dumped render.html> <n> <out.png>
"""
import re, sys, cairosvg
page, html, n, out = sys.argv[1], open(sys.argv[2]).read(), int(sys.argv[3]), sys.argv[4]
root = re.search(r":root\s*\{(.*?)\}", open(page).read(), re.S).group(1)
var = dict(re.findall(r"--([\w-]+):\s*([^;]+);", root))
svg = re.findall(r"<svg[\s\S]*?</svg>", html)[n]
svg = re.sub(r"var\(--([\w-]+)\)", lambda m: var.get(m.group(1), "#888").strip(), svg)
head, rest = svg.split(">", 1)
head = re.sub(r'\sstyle="[^"]*"', "", head)
svg = head + ' xmlns="http://www.w3.org/2000/svg" style="background:#fff;font-family:sans-serif">' + rest
cairosvg.svg2png(bytestring=svg.encode(), write_to=out, output_width=1400)
print(out)
