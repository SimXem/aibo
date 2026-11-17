/* ============================ responsive helpers (shared by index.html and timeline.html) ============================ */
// Every chart on the site is an SVG with a viewBox. Until 2026-08-27 each one
// laid itself out at a fixed width (880, 900, 430) and let the browser scale
// the whole drawing to the column — so on a phone a 10px label became a 4px
// label. Now a chart measures the width it actually gets and lays out INTO
// it: W is the column's width, text stays at CSS-pixel size, and each chart
// decides for itself what to drop or move when `narrow` (Graph 1/2 and the
// timeline lose their right-margin labels, which the legend and tooltip
// already carry; the policy chart moves labels above the bars).
function useContainerWidth(ref, fallback) {
  const [w, setW] = useState(fallback);
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const cw = el.getBoundingClientRect().width;
      if (cw > 0) setW(Math.round(cw));
    };
    read();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", read);
      return () => window.removeEventListener("resize", read);
    }
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

// True while the viewport is at most `px` wide; follows rotation and resizes.
function useNarrow(px) {
  const q = "(max-width: " + (px || 760) + "px)";
  const get = () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(q).matches;
  const [narrow, setNarrow] = useState(get);
  React.useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(q);
    const on = e => setNarrow(e.matches);
    if (mq.addEventListener) mq.addEventListener("change", on); else mq.addListener(on);
    return () => { if (mq.removeEventListener) mq.removeEventListener("change", on); else mq.removeListener(on); };
  }, [q]);
  return narrow;
}

// "within 6 months" -> "6 mo", "by 2030" -> "2030": the horizon labels a
// phone-width axis has room for.
function shortHorizon(s) {
  return String(s).replace(/^within\s+/i, "").replace(/\s*months?$/i, " mo").replace(/^by\s+/i, "");
}

// Keep only ticks at least `minGap` px apart (in axis order); 0 keeps all.
function thinTicks(ticks, x, minGap) {
  if (!minGap) return ticks;
  const out = [];
  let last = -Infinity;
  for (const t of ticks) {
    const px = x(t);
    if (px - last >= minGap) { out.push(t); last = px; }
  }
  return out;
}
