// "Compared with the other facilities": where this facility's 1 km surroundings rank among the
// facilities of its category, and, for public primary care units, need and supply on the residents
// the unit is expected to serve. The figures come with the narrative, from the computation its
// peer, need_supply and territory sentences cite. Peer ranks exist only for the 1 km reference
// radius (rule C20); the catchment figures do not depend on the radius.

import { el } from './charts.js';
import { TYPE_GROUPS, formatCount, formatDistance, formatNumber } from './fields.js';
import { pick, t } from './i18n.js';

const percent = (value) => `${formatNumber(value, 1)}%`;
const INDICATORS = [
  { key: 'deprived', label: () => t('peers.ind.deprived'), format: percent },
  { key: 'precarious', label: () => t('ind.precarious'), format: percent },
  { key: 'off_network', label: () => t('ind.noSewage'), format: percent },
  { key: 'no_garbage', label: () => t('ind.noGarbage'), format: percent },
  { key: 'crowded', label: () => t('peers.ind.crowded'), format: percent },
  { key: 'far_primary', label: () => t('ter.access.far'), format: percent },
  { key: 'income', label: () => t('ind.income'), format: (value) => `R$ ${formatCount(value)}` },
];
// Outside the central band a rank is extreme enough for the text to mention it (peer_extreme 0.8)
const BAND = [0.1, 0.9];

/** Same rounding as the narrative's rank slot: ceil, at least 1. */
function position(share) {
  if (share > 0.4 && share < 0.6) return t('peers.nearMedian');
  const top = share >= 0.5;
  const rank = Math.max(1, Math.ceil((top ? 1 - share : share) * 100));
  return t(top ? 'peers.top' : 'peers.bottom', { rank });
}

function rankRow(label, valueText, share, count) {
  const where = position(share);
  return el('div', {
    class: 'rank-row', role: 'listitem', title: t('peers.rowTitle', { label, value: valueText, where, count: formatCount(count) }),
  },
    el('span', { class: 'rank-label', text: label }),
    el('span', { class: 'rank-track', style: { '--p': share.toFixed(4) } },
      el('span', { class: 'rank-band', style: { '--lo': BAND[0], '--hi': BAND[1] } }),
      el('span', { class: 'rank-median' }),
      el('span', { class: 'rank-dot' })),
    el('span', { class: 'rank-value' }, el('strong', { text: valueText }), ` · ${where}`));
}

function scaleHeader() {
  return el('div', { class: 'rank-row rank-head', 'aria-hidden': 'true' },
    el('span'),
    el('span', { class: 'rank-ends' }, el('span', { text: t('peers.low') }), el('span', { text: t('peers.high') })),
    el('span'));
}

/** Need and supply among public primary care units: on the unit's catchment, or on the 1 km radius. */
function needBlock(reference) {
  if (reference.need_percentile === undefined || reference.load_percentile === undefined) return [];
  const count = reference.public_primary_size;
  if (reference.supply_measure === 'catchment') {
    return [
      el('h4', { class: 'rank-subtitle', text: t('peers.need', { count: formatCount(count) }) }),
      el('p', { class: 'scope scope-catchment', text: t('peers.catchmentScope') }),
      el('div', { class: 'ranks', role: 'list' },
        rankRow(t('peers.served'), formatCount(reference.values.served), reference.load_percentile, count),
        rankRow(t('peers.servedDeprived'), percent(reference.values.served_deprived), reference.need_percentile, count)),
      el('p', { class: 'hint', text: t('peers.catchmentHint', { distance: formatDistance(reference.mean_catchment_m || 0) }) }),
      reference.near_edge ? el('p', { class: 'notice', text: t('peers.nearEdge', { distance: formatDistance(reference.edge_m || 0) }) }) : null,
    ];
  }
  return [
    el('h4', { class: 'rank-subtitle', text: t('peers.need', { count: formatCount(count) }) }),
    el('div', { class: 'ranks', role: 'list' },
      rankRow(t('peers.ind.deprived'), percent(reference.values.deprived), reference.need_percentile, count),
      rankRow(t('peers.load'), formatCount(reference.values.load), reference.load_percentile, count)),
  ];
}

function legend() {
  return el('p', { class: 'hint rank-legend' },
    el('span', { class: 'rank-key-dot' }), t('peers.legendDot'),
    el('span', { class: 'rank-key-median' }), t('peers.legendMedian'),
    el('span', { class: 'rank-key-band' }), t('peers.legendBand'));
}

export function renderPeers(container, reference, facts, radius) {
  if (!reference) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  const title = el('h3', { class: 'card-title', text: t('peers.title') });
  const atReference = radius === reference.radius;
  // The catchment does not depend on the radius on screen; everything else here does (rule C20)
  const catchment = reference.supply_measure === 'catchment' ? needBlock(reference) : [];
  if (!atReference) {
    container.replaceChildren(title, ...catchment,
      el('p', { class: 'hint', text: t('peers.onlyReference', { radius: formatDistance(reference.radius) }) }),
      catchment.length ? legend() : null);
    return;
  }
  const group = TYPE_GROUPS.find((g) => g.id === reference.group);
  const rows = INDICATORS
    .filter(({ key }) => reference.percentiles[key] !== undefined)
    .map(({ key, label, format }) => rankRow(label(), format(reference.values[key]), reference.percentiles[key], reference.group_size));
  const territory = facts.find((f) => f.id === 'territory')?.slots.type?.text;

  container.replaceChildren(
    title,
    el('p', { class: 'scope scope-radius', text: t('peers.scope', {
      radius: formatDistance(reference.radius), count: formatCount(reference.group_size),
      group: group ? pick(group.label).toLowerCase() : reference.group,
    }) }),
    territory ? el('p', { text: t('peers.type', {
      type: territory, count: formatCount(reference.type_size), total: formatCount(reference.facilities),
    }) }) : null,
    el('div', { class: 'ranks', role: 'list' }, scaleHeader(), rows),
    ...needBlock(reference),
    legend(),
    el('p', { class: 'hint', text: t('peers.deprivedHint') }));
}
