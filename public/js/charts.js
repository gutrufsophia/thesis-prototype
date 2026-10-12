// Small dependency-free DOM and chart helpers shared by both pages.

import { formatNumber } from './fields.js';

/** Create an element. `props` may hold class, text, dataset, style or any attribute. */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'style') for (const [name, v] of Object.entries(value)) {
      if (name.startsWith('--')) node.style.setProperty(name, v);
      else node.style[name] = v;
    }
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}

/**
 * Horizontal bar list, one row per item, value printed at the bar's tip.
 * @param {{label: string, value: number, note?: string, muted?: boolean, color?: string}[]} items
 * @param {{digits?: number, suffix?: string, max?: number}} options
 */
export function barList(items, { digits = 0, suffix = '', max } = {}) {
  const scaleMax = max ?? Math.max(...items.map((item) => item.value || 0), 0);
  return el('div', { class: 'bars', role: 'list' }, items.map((item) => {
    const hasValue = item.value !== null && item.value !== undefined;
    const share = hasValue && scaleMax > 0 ? item.value / scaleMax : 0;
    const valueText = hasValue ? `${formatNumber(item.value, digits)}${suffix}` : 'no data';
    return el('div', {
      class: 'bar-row',
      role: 'listitem',
      title: `${item.label}: ${valueText}${item.note ? ` (${item.note})` : ''}`,
    },
      el('span', { class: 'bar-label', text: item.label }),
      el('span', { class: 'bar-track', style: { '--share': share.toFixed(4) } },
        el('span', {
          class: `bar-fill${item.muted ? ' is-muted' : ''}`,
          style: item.color ? { background: item.color } : {},
        }),
        el('span', { class: 'bar-value' }, valueText,
          item.note ? el('span', { class: 'bar-note', text: ` · ${item.note}` }) : null)));
  }));
}

/** Row of headline numbers. */
export function statTiles(tiles) {
  return el('div', { class: 'tiles' }, tiles.map((tile) =>
    el('div', { class: 'tile' },
      el('div', { class: 'tile-label', text: tile.label }),
      el('div', { class: 'tile-value', text: tile.value }),
      tile.note ? el('div', { class: 'tile-note', text: tile.note }) : null)));
}

/** Titled block; shows `emptyText` instead of the body when there is nothing to plot. */
export function section(title, body, { hint, emptyText } = {}) {
  return el('section', { class: 'block' },
    el('h3', { text: title }),
    hint ? el('p', { class: 'hint', text: hint }) : null,
    body || el('p', { class: 'empty', text: emptyText || 'None recorded.' }));
}
