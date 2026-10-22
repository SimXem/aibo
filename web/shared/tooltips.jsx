// One app-wide surface and placement policy for text, HTML and React tooltips.
function appTooltip(target, options = {}) {
  return window.tippy(target, {
    theme: "airo", arrow: true, maxWidth: 360, offset: [0, 8],
    placement: "right", appendTo: () => document.body, animation: false,
    ...options,
  });
}

// React owns content; Popper owns viewport-aware placement. Coordinates are SVG
// user units, transformed through the actual screen matrix (including resize).
function PointTooltip({ anchor, box, x, y, children }) {
  const [content] = useState(() => document.createElement("div"));
  const tooltip = React.useRef(null);
  const position = React.useRef(null);
  position.current = { anchor, box, x, y };
  React.useLayoutEffect(() => {
    const p = position.current;
    const target = p.anchor || (p.box && p.box.current);
    if (!target || !window.tippy) return;
    const instance = appTooltip(target, {
      content, trigger: "manual",
      getReferenceClientRect: () => {
        const p = position.current;
        if (p.anchor) return p.anchor.getBoundingClientRect();
        const svg = p.box.current.querySelector("svg");
        const point = svg.createSVGPoint();
        point.x = p.x; point.y = p.y;
        const screen = point.matrixTransform(svg.getScreenCTM());
        return { x: screen.x, y: screen.y, left: screen.x, right: screen.x,
          top: screen.y, bottom: screen.y, width: 0, height: 0 };
      },
    });
    tooltip.current = instance;
    instance.show();
    return () => { instance.destroy(); tooltip.current = null; };
  }, [anchor, box, content]);
  React.useLayoutEffect(() => {
    if (tooltip.current && tooltip.current.popperInstance) tooltip.current.popperInstance.update();
  });
  return ReactDOM.createPortal(children, content);
}
