// Relations page: disease outcomes against census living conditions, at the scales where
// outcomes exist. Data come from analysis/outcome_relations.py (public/data/relations.json).

import { barList, el, section } from './charts.js';
import { formatCount, formatNumber } from './fields.js';
import { applyStaticTranslations, t } from './i18n.js';
import { dataTable, intervals, legend, scatter } from './plots.js';

applyStaticTranslations();
document.title = `${t('rel.title')} · ${t('brand')}`;
const root = document.getElementById('relations-root');

const money = (v) => `R$ ${formatCount(v)}`;
const pct = (v) => `${formatNumber(v, 1)}%`;
const rate = (v, digits = 1) => formatNumber(v, digits);

function spearman(a, b) {
  const rank = (values) => {
    const order = values.map((v, i) => [v, i]).sort((p, q) => p[0] - q[0]);
    const out = new Array(values.length);
    for (let i = 0; i < order.length;) {
      let j = i;
      while (j + 1 < order.length && order[j + 1][0] === order[i][0]) j += 1;
      for (let k = i; k <= j; k += 1) out[order[k][1]] = (i + j) / 2;
      i = j + 1;
    }
    return out;
  };
  const ra = rank(a);
  const rb = rank(b);
  const mean = (v) => v.reduce((s, x) => s + x, 0) / v.length;
  const ma = mean(ra);
  const mb = mean(rb);
  const cov = ra.reduce((s, x, i) => s + (x - ma) * (rb[i] - mb), 0);
  return cov / Math.sqrt(ra.reduce((s, x) => s + (x - ma) ** 2, 0) * rb.reduce((s, y) => s + (y - mb) ** 2, 0));
}

function pairText(pair) {
  if (!pair || pair.rho === null) return t('rel.noVariation');
  return t('rel.rho', {
    rho: formatNumber(pair.rho, 2), low: formatNumber(pair.ci[0], 2), high: formatNumber(pair.ci[1], 2), n: pair.n,
  });
}

function card(title, subtitle, body, caption, table) {
  return el('section', { class: 'card relation-card' },
    el('h2', { class: 'relation-title', text: title }),
    subtitle ? el('p', { class: 'hint', text: subtitle }) : null,
    body,
    caption ? el('p', { class: 'relation-caption', text: caption }) : null,
    table);
}

function flagsFor(data, scale, outcome) {
  return new Map(data.expected.filter((e) => e.scale === scale && e.outcome === outcome).map((e) => [e.code, e]));
}

function model(data, scale, outcome) {
  return data.models.find((m) => m.scale === scale && m.outcome === outcome);
}

function pair(data, scale, outcome, determinant) {
  return data.pairs.find((p) => p.scale === scale && p.outcome === outcome && p.determinant === determinant);
}

function forestCard(data) {
  const rows = data.pairs.filter((p) => p.rho !== null).map((p) => ({
    label: `${t(`rel.outcome.${p.outcome}`)} × ${t(`rel.short.${p.determinant}`)}`,
    value: p.rho,
    low: p.ci[0],
    high: p.ci[1],
    highlight: p.scale === 'district',
    tooltip: [`ρ ${formatNumber(p.rho, 2)}`, t(`rel.scale.${p.scale}`, { n: p.n }),
      t('rel.interval', { low: formatNumber(p.ci[0], 2), high: formatNumber(p.ci[1], 2) })],
  }));
  rows.sort((a, b) => Number(a.highlight) - Number(b.highlight) || a.value - b.value);
  return card(t('rel.forest.title'), t('rel.forest.subtitle'),
    [legend([{ label: t('rel.legend.municipalities') }, { label: t('rel.legend.districts'), highlight: true }]),
      intervals(rows, { min: -1, max: 1, reference: 0, format: (v) => formatNumber(v, 1), axisLabel: t('rel.forest.axis'), title: t('rel.forest.title') })],
    t('rel.forest.caption'),
    dataTable([
      { label: t('rel.table.relation'), value: (p) => `${t(`rel.outcome.${p.outcome}`)} × ${t(`rel.det.${p.determinant}`)}` },
      { label: t('rel.table.scale'), value: (p) => t(`rel.scale.${p.scale}`, { n: p.n }) },
      { label: 'ρ', numeric: true, value: (p) => (p.rho === null ? '–' : formatNumber(p.rho, 2)) },
      { label: t('rel.table.ci'), value: (p) => (p.ci ? `${formatNumber(p.ci[0], 2)} a ${formatNumber(p.ci[1], 2)}` : t('rel.noVariation')) },
    ], data.pairs, t('rel.table.show')));
}

/** Scatter of an outcome rate against a determinant, with the areas the model flags highlighted. */
function relationCard(data, { scale, outcome, determinant, title, caption, digits = 1, log = false }) {
  const areas = scale === 'district' ? data.districts : data.municipalities;
  const flags = flagsFor(data, scale, outcome);
  const m = model(data, scale, outcome);
  const formatX = determinant === 'income' ? money : pct;
  const formatY = (v) => (outcome === 'teen' ? pct(v) : rate(v, digits));
  const flagged = (a) => m?.used_for_flags && flags.get(a.code)?.flag;
  const points = areas.map((a) => ({
    x: a[determinant],
    y: a.rates[outcome],
    label: a.name,
    highlight: Boolean(flagged(a)),
    tooltip: [a.name, `${t(`rel.outcome.${outcome}`)}: ${formatY(a.rates[outcome])}`,
      `${t(`rel.det.${determinant}`)}: ${formatX(a[determinant])}`,
      ...(flagged(a) ? [t(`rel.flag.${flags.get(a.code).flag}`)] : [])],
  }));
  const fitText = m ? t('rel.model', { share: formatNumber(m.deviance_explained * 100, 0) }) : '';
  return card(title, `${pairText(pair(data, scale, outcome, determinant))} ${fitText}`,
    [m?.used_for_flags ? legend([{ label: t(`rel.legend.${scale}Expected`) }, { label: t('rel.legend.flagged'), highlight: true }]) : null,
      scatter(points, {
        xLabel: t(`rel.det.${determinant}`), yLabel: t(`rel.unit.${outcome}`), xLog: log,
        formatX: determinant === 'income' ? (v) => formatCount(v) : (v) => formatNumber(v, 0), formatY: (v) => formatNumber(v, 0),
        title,
      })],
    caption,
    dataTable([
      { label: t(`rel.table.${scale}`), value: (a) => a.name },
      { label: t(`rel.det.${determinant}`), numeric: true, value: (a) => formatX(a[determinant]) },
      { label: t(`rel.unit.${outcome}`), numeric: true, value: (a) => formatY(a.rates[outcome]) },
      { label: t('rel.table.flag'), value: (a) => (flagged(a) ? t(`rel.flag.${flags.get(a.code).flag}`) : '') },
    ], [...areas].sort((a, b) => b.rates[outcome] - a.rates[outcome]), t('rel.table.show')));
}

/** Funnel plot (Spiegelhalter 2005): rate against population, with 95% and 99.8% limits around the regional rate. */
function funnelCard(data) {
  const areas = data.municipalities;
  const years = data.years.length;
  const cases = areas.reduce((s, a) => s + a.cases.lepto, 0);
  const personYears = areas.reduce((s, a) => s + a.population * years, 0);
  const p = cases / personYears;
  const smallest = Math.min(...areas.map((a) => a.population));
  const largest = Math.max(...areas.map((a) => a.population));
  const sizes = [];
  for (let n = smallest * 0.9; n <= largest * 1.1; n *= 1.1) sizes.push(n);
  const limit = (z, sign) => sizes.map((n) => [n, Math.max(0, (p + sign * z * Math.sqrt(p / (n * years))) * 1e5)]);
  const outside = (a) => Math.abs(a.rates.lepto_raw / 1e5 - p) > 3.09 * Math.sqrt(p / (a.population * years));
  const points = areas.map((a) => ({
    x: a.population, y: a.rates.lepto_raw, label: a.name, highlight: outside(a),
    tooltip: [a.name, t('rel.funnel.cases', { cases: formatCount(a.cases.lepto) }), `${t('rel.unit.lepto')}: ${rate(a.rates.lepto_raw, 2)}`,
      `${t('rel.table.population')}: ${formatCount(a.population)}`],
  }));
  const title = t('rel.funnel.title');
  const beyond = areas.filter(outside).map((a) => `${a.name} (${rate(a.rates.lepto_raw, 2)}, ${t('rel.funnel.cases', { cases: formatCount(a.cases.lepto) })})`);
  return card(title, t('rel.funnel.subtitle', { rate: rate(p * 1e5, 2) }),
    [legend([{ label: t('rel.legend.municipalities') }, { label: t('rel.legend.outside'), highlight: true }]),
      scatter(points, {
        xLabel: t('rel.table.population'), yLabel: t('rel.unit.lepto'), xLog: true, title,
        formatX: (v) => formatCount(v), formatY: (v) => formatNumber(v, 1),
        bands: [
          { points: limit(1.96, 1), className: 'is-inner' }, { points: limit(1.96, -1), className: 'is-inner' },
          { points: limit(3.09, 1) }, { points: limit(3.09, -1) },
        ],
      })],
    `${t('rel.funnel.caption')} ${beyond.length ? t('rel.funnel.beyond', { list: beyond.join('; ') }) : t('rel.funnel.none')}`,
    dataTable([
      { label: t('rel.table.municipality'), value: (a) => a.name },
      { label: t('rel.table.population'), numeric: true, value: (a) => formatCount(a.population) },
      { label: t('rel.funnel.casesColumn'), numeric: true, value: (a) => formatCount(a.cases.lepto) },
      { label: t('rel.unit.lepto'), numeric: true, value: (a) => rate(a.rates.lepto_raw, 2) },
    ], [...areas].sort((a, b) => b.cases.lepto - a.cases.lepto), t('rel.table.show')));
}

function inverseCareCard(data) {
  const panel = (scale, areas) => {
    const usable = areas.filter((a) => a.near !== null);
    const rho = spearman(usable.map((a) => a.precarious), usable.map((a) => a.near));
    return el('div', { class: 'relation-panel' },
      el('h3', { class: 'relation-subtitle', text: t(`rel.care.${scale}`, { rho: formatNumber(rho, 2) }) }),
      scatter(usable.map((a) => ({
        x: a.precarious, y: a.near, label: a.name,
        tooltip: [a.name, `${t('rel.det.near')}: ${pct(a.near)}`, `${t('rel.det.precarious')}: ${pct(a.precarious)}`],
      })), {
        xLabel: t('rel.det.precarious'), yLabel: t('rel.det.near'), title: t(`rel.care.${scale}`, { rho: formatNumber(rho, 2) }),
        formatX: (v) => formatNumber(v, 0), formatY: (v) => formatNumber(v, 0),
      }));
  };
  return card(t('rel.care.title'), t('rel.care.subtitle'),
    el('div', { class: 'relation-pair' }, panel('district', data.districts), panel('municipality', data.municipalities)),
    t('rel.care.caption'));
}

function transferCard(data) {
  return card(t('rel.transfer.title'), t('rel.transfer.subtitle'),
    section(t('rel.transfer.error'), barList(data.scale_transfer.map((r) => ({
      label: t(`rel.transfer.${r.method.replace(/ /g, '_')}`),
      value: r.absolute_error * 100,
      note: r.rank_correlation === null ? t('rel.transfer.noOrder') : t('rel.transfer.order', { rho: formatNumber(r.rank_correlation, 2) }),
    })), { digits: 0, suffix: '%' })),
    t('rel.transfer.caption'));
}

function surpriseCard(data) {
  const rows = data.expected.filter((e) => e.flag && model(data, e.scale, e.outcome)?.used_for_flags)
    .map((e) => ({
      label: `${e.name} · ${t(`rel.outcome.${e.outcome}`)}`,
      value: e.observed / e.expected,
      low: e.lower / e.expected,
      high: e.upper / e.expected,
      highlight: true,
      tooltip: [e.name, t('rel.surprise.counts', { observed: formatCount(e.observed), expected: formatCount(e.expected) }),
        t('rel.surprise.range', { low: formatCount(e.lower), high: formatCount(e.upper) })],
    }))
    .sort((a, b) => b.value - a.value);
  return card(t('rel.surprise.title'), t('rel.surprise.subtitle'),
    intervals(rows, { min: 0, max: Math.max(3, ...rows.map((r) => Math.max(r.value, r.high))), reference: 1,
      format: (v) => `${formatNumber(v, 1)}×`, axisLabel: t('rel.surprise.axis'), title: t('rel.surprise.title') }),
    t('rel.surprise.caption'),
    dataTable([
      { label: t('rel.table.area'), value: (r) => r.label },
      { label: t('rel.surprise.ratio'), numeric: true, value: (r) => `${formatNumber(r.value, 2)}×` },
      { label: t('rel.surprise.rangeColumn'), value: (r) => `${formatNumber(r.low, 2)}× a ${formatNumber(r.high, 2)}×` },
    ], rows, t('rel.table.show')));
}

async function init() {
  let data;
  try {
    data = await (await fetch('data/relations.json')).json();
  } catch (error) {
    root.replaceChildren(el('p', { class: 'notice is-error', text: t('rel.loadError') }));
    return;
  }
  root.replaceChildren(
    forestCard(data),
    el('h2', { class: 'relations-section', text: t('rel.section.tb') }),
    relationCard(data, { scale: 'district', outcome: 'tb', determinant: 'income', log: true, title: t('rel.tb.income.title'), caption: t('rel.tb.income.caption') }),
    relationCard(data, { scale: 'district', outcome: 'tb', determinant: 'crowded', title: t('rel.tb.crowded.title'), caption: t('rel.tb.crowded.caption') }),
    surpriseCard(data),
    transferCard(data),
    el('h2', { class: 'relations-section', text: t('rel.section.vector') }),
    relationCard(data, { scale: 'municipality', outcome: 'dengue_2024', determinant: 'no_garbage', digits: 0, title: t('rel.dengue.title'), caption: t('rel.dengue.caption') }),
    funnelCard(data),
    el('h2', { class: 'relations-section', text: t('rel.section.teen') }),
    relationCard(data, { scale: 'district', outcome: 'teen', determinant: 'income', log: true, title: t('rel.teen.title'), caption: t('rel.teen.caption') }),
    el('h2', { class: 'relations-section', text: t('rel.section.care') }),
    inverseCareCard(data),
    el('p', { class: 'hint relations-source', text: t('rel.source') }));
}

init();
