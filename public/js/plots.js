// SVG plots for the relations page: scatter (with optional log x-axis, reference bands and
// highlighted points) and dot-with-interval rows. Every mark has a 24px hit area and a
// tooltip on hover and keyboard focus; values also live in each chart's table view.

import { el } from './charts.js';

const NS = 'http://www.w3.org/2000/svg';
// Drawn at about the size it is shown, so 11-12px text stays 11-12px on screen.
const WIDTH = 860;
const HEIGHT = 380;
const MARGIN = { top: 14, right: 24, bottom: 48, left: 70 };
const LABEL_HEIGHT = 13;
const CHAR_WIDTH = 6.4;

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child) node.append(child);
  return node;
}

function niceStep(span, count) {
  const raw = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const unit = [1, 2, 2.5, 5, 10].find((m) => m * magnitude >= raw) * magnitude;
  return unit;
}

function linearScale(min, max, from, to) {
  const step = niceStep(max - min || 1, 5);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const map = (v) => from + ((v - lo) / (hi - lo || 1)) * (to - from);
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return { map, ticks };
}

function logScale(min, max, from, to) {
  const lo = Math.log10(min);
  const hi = Math.log10(max);
  const map = (v) => from + ((Math.log10(v) - lo) / (hi - lo || 1)) * (to - from);
  const ticks = [];
  for (let e = Math.floor(lo); e <= Math.ceil(hi); e += 1) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** e;
      if (v >= min && v <= max) ticks.push(v);
    }
  }
  return { map, ticks };
}

/** One tooltip per plot, filled with textContent only. */
function tooltipLayer(wrapper) {
  const tip = el('div', { class: 'plot-tooltip', role: 'status', hidden: true });
  wrapper.append(tip);
  return {
    show(lines, x, y) {
      tip.replaceChildren(...lines.map((line, i) => el(i === 0 ? 'strong' : 'span', { text: line })));
      tip.hidden = false;
      const box = wrapper.getBoundingClientRect();
      const scale = box.width / WIDTH;
      const left = Math.min(x * scale + 12, box.width - tip.offsetWidth - 4);
      tip.style.left = `${Math.max(4, left)}px`;
      tip.style.top = `${Math.max(4, y * scale - tip.offsetHeight - 10)}px`;
    },
    hide() { tip.hidden = true; },
  };
}

function hitTarget(tooltip, x, y, lines) {
  const hit = svg('circle', { cx: x, cy: y, r: 12, class: 'plot-hit', tabindex: 0, 'aria-label': lines.join(', ') });
  const show = () => tooltip.show(lines, x, y);
  hit.addEventListener('pointerenter', show);
  hit.addEventListener('focus', show);
  hit.addEventListener('pointerleave', () => tooltip.hide());
  hit.addEventListener('blur', () => tooltip.hide());
  return hit;
}

function axes(x, y, { xLabel, yLabel, formatX, formatY }) {
  const plotLeft = MARGIN.left;
  const plotRight = WIDTH - MARGIN.right;
  const plotBottom = HEIGHT - MARGIN.bottom;
  return [
    ...y.ticks.map((v) => svg('g', {},
      svg('line', { x1: plotLeft, x2: plotRight, y1: y.map(v), y2: y.map(v), class: 'plot-grid' }),
      svg('text', { x: plotLeft - 8, y: y.map(v) + 4, class: 'plot-tick', 'text-anchor': 'end' }, formatY(v)))),
    ...x.ticks.map((v) => svg('text', { x: x.map(v), y: plotBottom + 18, class: 'plot-tick', 'text-anchor': 'middle' }, formatX(v))),
    svg('line', { x1: plotLeft, x2: plotRight, y1: plotBottom, y2: plotBottom, class: 'plot-axis' }),
    svg('text', { x: (plotLeft + plotRight) / 2, y: HEIGHT - 8, class: 'plot-label', 'text-anchor': 'middle' }, xLabel),
    svg('text', { x: 14, y: (MARGIN.top + plotBottom) / 2, class: 'plot-label', 'text-anchor': 'middle',
      transform: `rotate(-90 14 ${(MARGIN.top + plotBottom) / 2})` }, yLabel),
  ];
}

function diamond(cx, cy, r) {
  return `M${cx} ${cy - r}L${cx + r} ${cy}L${cx} ${cy + r}L${cx - r} ${cy}Z`;
}

/**
 * @param {{x: number, y: number, label: string, highlight?: boolean, tooltip: string[]}[]} points
 * @param {{xLabel, yLabel, formatX, formatY, xLog?, bands?: {label: string, points: [number, number][]}[], title: string}} options
 */
export function scatter(points, options) {
  const usable = points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y) && (!options.xLog || p.x > 0));
  const xs = usable.map((p) => p.x);
  const ys = usable.map((p) => p.y).concat((options.bands || []).flatMap((b) => b.points.map(([, y]) => y)));
  const plotBottom = HEIGHT - MARGIN.bottom;
  const x = options.xLog
    ? logScale(Math.min(...xs) * 0.9, Math.max(...xs) * 1.1, MARGIN.left, WIDTH - MARGIN.right)
    : linearScale(Math.min(...xs), Math.max(...xs), MARGIN.left, WIDTH - MARGIN.right);
  const y = linearScale(Math.min(0, ...ys), Math.max(...ys), plotBottom, MARGIN.top);

  const wrapper = el('div', { class: 'plot' });
  const tooltip = tooltipLayer(wrapper);
  const bands = (options.bands || []).map((band) => svg('polyline', {
    points: band.points.map(([bx, by]) => `${x.map(bx)},${y.map(by)}`).join(' '),
    class: `plot-band ${band.className || ''}`,
  }));
  const marks = [];
  const hits = [];
  const labels = [];
  // Direct labels only for highlighted points, beside their mark; a label that fits nowhere is
  // left to the tooltip and the table rather than pushed away from its point.
  const boxes = [];
  const overlaps = (b) => boxes.some((o) => b.x1 < o.x2 && b.x2 > o.x1 && b.y1 < o.y2 && b.y2 > o.y1);
  for (const p of [...usable].sort((a, b) => Number(a.highlight || false) - Number(b.highlight || false))) {
    const cx = x.map(p.x);
    const cy = y.map(p.y);
    marks.push(p.highlight
      ? svg('path', { d: diamond(cx, cy, 6), class: 'plot-dot is-highlight' })
      : svg('circle', { cx, cy, r: 4.5, class: 'plot-dot' }));
    hits.push(hitTarget(tooltip, cx, cy, p.tooltip));
  }
  for (const p of usable.filter((q) => q.highlight)) {
    const cx = x.map(p.x);
    const cy = y.map(p.y);
    boxes.push({ x1: cx - 7, x2: cx + 7, y1: cy - 7, y2: cy + 7 });
  }
  for (const p of usable.filter((q) => q.highlight)) {
    const cx = x.map(p.x);
    const cy = y.map(p.y);
    const w = p.label.length * CHAR_WIDTH;
    const candidates = [
      { x: cx + 10, y: cy + 4, anchor: 'start', box: { x1: cx + 9, x2: cx + 11 + w } },
      { x: cx - 10, y: cy + 4, anchor: 'end', box: { x1: cx - 11 - w, x2: cx - 9 } },
      { x: cx, y: cy - 10, anchor: 'middle', box: { x1: cx - w / 2, x2: cx + w / 2 }, above: true },
      { x: cx, y: cy + 18, anchor: 'middle', box: { x1: cx - w / 2, x2: cx + w / 2 }, below: true },
    ].map((c) => ({ ...c, box: { ...c.box, y1: c.y - LABEL_HEIGHT + 2, y2: c.y + 2 } }));
    const spot = candidates.find((c) => c.box.x1 >= MARGIN.left && c.box.x2 <= WIDTH - 4 && !overlaps(c.box));
    if (!spot) continue;
    boxes.push(spot.box);
    labels.push(svg('text', { x: spot.x, y: spot.y, class: 'plot-annotation', 'text-anchor': spot.anchor }, p.label));
  }
  const chart = svg('svg', { viewBox: `0 0 ${WIDTH} ${HEIGHT}`, class: 'plot-svg', role: 'img', 'aria-label': options.title },
    axes(x, y, options), bands, marks, labels, hits);
  wrapper.prepend(chart);
  return wrapper;
}

/**
 * Horizontal rows of a dot with its interval, on one shared scale.
 * @param {{label: string, value: number, low: number, high: number, highlight?: boolean, tooltip: string[]}[]} rows
 * @param {{min: number, max: number, reference: number, format: (v: number) => string, axisLabel: string, title: string}} options
 */
export function intervals(rows, options) {
  const rowHeight = 26;
  const left = options.labelWidth || 260;
  const height = rows.length * rowHeight + 40;
  const x = linearScale(options.min, options.max, left, WIDTH - MARGIN.right);
  const wrapper = el('div', { class: 'plot' });
  const tooltip = tooltipLayer(wrapper);
  const parts = [
    ...x.ticks.map((v) => svg('g', {},
      svg('line', { x1: x.map(v), x2: x.map(v), y1: 6, y2: height - 30, class: 'plot-grid' }),
      svg('text', { x: x.map(v), y: height - 14, class: 'plot-tick', 'text-anchor': 'middle' }, options.format(v)))),
    svg('line', { x1: x.map(options.reference), x2: x.map(options.reference), y1: 6, y2: height - 30, class: 'plot-reference' }),
  ];
  rows.forEach((row, i) => {
    const cy = 20 + i * rowHeight;
    const cx = x.map(row.value);
    parts.push(
      svg('text', { x: left - 10, y: cy + 4, class: 'plot-tick', 'text-anchor': 'end' }, row.label),
      svg('line', { x1: x.map(row.low), x2: x.map(row.high), y1: cy, y2: cy, class: `plot-interval${row.highlight ? ' is-highlight' : ''}` }),
      row.highlight ? svg('path', { d: diamond(cx, cy, 6), class: 'plot-dot is-highlight' }) : svg('circle', { cx, cy, r: 4.5, class: 'plot-dot' }),
      hitTarget(tooltip, cx, cy, row.tooltip));
  });
  parts.push(svg('text', { x: (left + WIDTH - MARGIN.right) / 2, y: height - 1, class: 'plot-label', 'text-anchor': 'middle' }, options.axisLabel));
  wrapper.prepend(svg('svg', { viewBox: `0 0 ${WIDTH} ${height}`, class: 'plot-svg', role: 'img', 'aria-label': options.title }, parts));
  return wrapper;
}

export function legend(items) {
  return el('div', { class: 'plot-legend' }, items.map(({ label, highlight }) => el('span', { class: 'plot-legend-item' },
    el('span', { class: `plot-key${highlight ? ' is-highlight' : ''}`, 'aria-hidden': 'true' }), label)));
}

/** Table view: every value a chart shows, without hovering. */
export function dataTable(columns, rows, summary) {
  return el('details', { class: 'plot-table' },
    el('summary', { text: summary }),
    el('table', {},
      el('thead', {}, el('tr', {}, columns.map((c) => el('th', { text: c.label, class: c.numeric ? 'numeric' : null })))),
      el('tbody', {}, rows.map((r) => el('tr', {}, columns.map((c) => el('td', { text: c.value(r), class: c.numeric ? 'numeric' : null })))))));
}
