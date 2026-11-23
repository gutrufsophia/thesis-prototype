// Small dependency-free DOM and chart helpers shared by both pages.

import { formatNumber } from './fields.js';
import { t } from './i18n.js';

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
 * `reference` draws a tick on the same scale, for a comparison value.
 * @param {{label: string, value: number, note?: string, muted?: boolean, color?: string, reference?: number}[]} items
 * @param {{digits?: number, prefix?: string, suffix?: string, max?: number}} options
 */
export function barList(items, { digits = 0, prefix = '', suffix = '', max } = {}) {
  const scaleMax = max ?? Math.max(...items.flatMap((item) => [item.value || 0, item.reference || 0]), 0);
  const hasReference = items.some((item) => item.reference !== undefined && item.reference !== null);
  return el('div', { class: `bars${hasReference ? ' has-reference' : ''}`, role: 'list' }, items.map((item) => {
    const hasValue = item.value !== null && item.value !== undefined;
    const share = hasValue && scaleMax > 0 ? item.value / scaleMax : 0;
    const valueText = hasValue ? `${prefix}${formatNumber(item.value, digits)}${suffix}` : t('noData');
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
        item.reference !== undefined && item.reference !== null && scaleMax > 0
          ? el('span', { class: 'bar-reference', style: { '--ref': (item.reference / scaleMax).toFixed(4) } })
          : null,
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

/** Label and value rows, as in a record sheet; `numeric` right-aligns the values. */
export function keyValues(entries, { numeric = false } = {}) {
  return el('dl', { class: `profile${numeric ? ' is-numeric' : ''}` }, entries.flatMap(([term, value]) => [
    el('dt', { text: term }),
    el('dd', { text: value || '–' }),
  ]));
}

/**
 * Collapsed note under a figure: sources, definitions and method, kept one click away so the card
 * shows only the figure and a plain sentence (details on demand). Empty when there is nothing to say.
 */
export function about(...children) {
  const content = children.flat().filter((child) => child !== null && child !== undefined && child !== false && child !== '');
  if (!content.length) return null;
  return el('details', { class: 'about' },
    el('summary', { text: t('details.about') }),
    content.map((child) => (typeof child === 'string' ? el('p', { text: child }) : child)));
}

/** Collapsed record rows that a reader seldom needs (codes, legal names, technical position). */
export function moreRows(entries) {
  const shown = entries.filter(([, value]) => value);
  if (!shown.length) return null;
  return el('details', { class: 'about' }, el('summary', { text: t('details.more') }), keyValues(shown));
}

/**
 * Titled block; shows `emptyText` instead of the body when there is nothing to plot. `hint` is a
 * short plain sentence shown under the title; `note` goes into the collapsed "about" note.
 */
export function section(title, body, { hint, note, emptyText } = {}) {
  return el('section', { class: 'block' },
    el('h3', { text: title }),
    hint ? el('p', { class: 'hint', text: hint }) : null,
    body || el('p', { class: 'empty', text: emptyText || t('noneRecorded') }),
    about(note));
}
