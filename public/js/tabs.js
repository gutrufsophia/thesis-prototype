// Tab bar following the WAI-ARIA tabs pattern. The open tab is kept in the URL hash, so a
// reload or a shared link opens the same tab.

export function setupTabs(list, { initial, onChange } = {}) {
  const tabs = () => [...list.querySelectorAll('[role="tab"]')].filter((tab) => !tab.hidden);
  const byName = (name) => tabs().find((tab) => tab.dataset.tab === name);

  function select(name, { focus = false, updateHash = true } = {}) {
    const target = byName(name) || byName(initial) || tabs()[0];
    for (const tab of list.querySelectorAll('[role="tab"]')) {
      const active = tab === target;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
    }
    if (focus) target.focus();
    // On narrow screens the bar scrolls sideways; keep the open tab in view
    if (list.scrollWidth > list.clientWidth) {
      const offset = target.getBoundingClientRect().left - list.getBoundingClientRect().left;
      list.scrollLeft += offset - (list.clientWidth - target.offsetWidth) / 2;
    }
    if (updateHash) history.replaceState(null, '', `#${target.dataset.tab}`);
    onChange?.(target.dataset.tab);
    return target.dataset.tab;
  }

  list.addEventListener('click', (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab) select(tab.dataset.tab);
  });
  list.addEventListener('keydown', (event) => {
    const visible = tabs();
    const index = visible.indexOf(document.activeElement);
    if (index < 0) return;
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: visible.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    select(visible[(next + visible.length) % visible.length].dataset.tab, { focus: true });
  });
  window.addEventListener('hashchange', () => select(location.hash.slice(1), { updateHash: false }));

  return {
    select,
    /** The tab panel that contains `node`, opened. */
    reveal(node) {
      const panel = node.closest('[role="tabpanel"]');
      const tab = panel && list.querySelector(`[aria-controls="${panel.id}"]`);
      if (tab) select(tab.dataset.tab);
    },
    start() { return select(location.hash.slice(1), { updateHash: false }); },
  };
}
