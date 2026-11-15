// Annotation page for E1 (caveats), E2 (content selection) and E4 (text accuracy). Blind by design:
// the text appears only after E1 and E2 are locked for a unit, and the system's answers are never
// loaded (they live in system.json). Progress stays in this browser and is exported as JSON.

const TASKS = window.ANNOTATION_TASKS;
const STORE_PREFIX = 'anotacao-tcc:';
const CATEGORIES = [
  ['NUMERO', 'Número incorreto: não bate com a ficha de dados'],
  ['ESCALA', 'Escala errada: o número é de outra escala (raio, área de atendimento, distrito, município, região)'],
  ['NOME', 'Nome ou período incorreto: lugar, ano ou intervalo de anos'],
  ['PALAVRA', 'Palavra incorreta: comparativo, direção ou termo que não corresponde aos dados'],
  ['CONTEXTO', 'Contexto: correto, mas enganoso sem uma ressalva ou contexto que falta'],
  ['NAO_VERIFICAVEL', 'Não verificável com a ficha de dados'],
  ['OUTRO', 'Outro erro'],
];
const E2_MIN = 3;
const E2_MAX = 5;

let state = null;

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

// Deterministic order per annotator, so two annotators see the units in different orders
function hash(text) {
  let h = 2166136261;
  for (const c of text) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

function shuffled(items, seed) {
  let a = seed;
  const random = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const out = [...items];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function save() {
  try {
    localStorage.setItem(STORE_PREFIX + state.annotator, JSON.stringify(state));
  } catch {
    // storage unavailable: the export button still works for this session
  }
  renderProgress();
}

function load(annotator) {
  try {
    const stored = JSON.parse(localStorage.getItem(STORE_PREFIX + annotator));
    if (stored && stored.version === TASKS.version) return stored;
  } catch {
    // nothing stored
  }
  return {
    annotator,
    version: TASKS.version,
    order: shuffled(TASKS.units.map((u) => u.id), hash(annotator)),
    current: 0,
    units: {},
  };
}

function record(id) {
  state.units[id] ??= { e1: {}, e1_notes: {}, e2: [], e4: {}, reviewed: {}, started_at: new Date().toISOString() };
  return state.units[id];
}

function renderProgress() {
  if (!state) return;
  const done = Object.values(state.units).filter((u) => u.done_at).length;
  $('progress').textContent = `${state.annotator} · ${done} de ${TASKS.units.length} unidades concluídas`;
}

function sheet(unit) {
  return el('div', { class: 'sheet' }, unit.sheet.map((section) => el('section', { class: 'sheet-section' },
    el('h3', { text: section.title }),
    el('p', { class: 'source', text: `Fonte: ${section.source}` }),
    el('table', {}, el('tbody', {}, section.rows.map(([label, value]) => el('tr', {},
      el('th', { scope: 'row', text: label }), el('td', { text: value }))))))));
}

function e1Block(unit, rec, locked) {
  return el('section', { class: 'task' },
    el('h2', { text: 'Etapa 1 · Ressalvas' }),
    el('p', { class: 'hint', text: 'Com base apenas na ficha de dados: um texto cuidadoso sobre esta unidade precisaria fazer esta ressalva?' }),
    TASKS.checklist.map((item) => el('fieldset', { class: 'item' },
      el('legend', { text: item.title }),
      el('p', { class: 'hint', text: item.description }),
      el('div', { class: 'choices' }, ['sim', 'nao'].map((choice) => el('label', {},
        el('input', {
          type: 'radio', name: `e1-${item.id}`, value: choice, disabled: locked, checked: rec.e1[item.id] === choice,
          onchange: () => { rec.e1[item.id] = choice; save(); refreshLock(unit, rec); },
        }), choice === 'sim' ? ' Sim' : ' Não'))),
      el('input', {
        type: 'text', class: 'note', placeholder: 'Comentário (opcional)', disabled: locked, value: rec.e1_notes[item.id] || '',
        oninput: (event) => { rec.e1_notes[item.id] = event.target.value; save(); },
      }))));
}

function e2Block(unit, rec, locked) {
  const counter = el('p', { class: 'hint', id: 'e2-count' });
  const update = () => { counter.textContent = `${rec.e2.length} escolhidas (entre ${E2_MIN} e ${E2_MAX}).`; };
  update();
  return el('section', { class: 'task' },
    el('h2', { text: 'Etapa 2 · O que é mais importante' }),
    el('p', { class: 'hint', text: `Escolha de ${E2_MIN} a ${E2_MAX} afirmações que um leitor da página desta unidade mais precisaria saber.` }),
    el('ul', { class: 'statements' }, unit.statements.map((s) => el('li', {}, el('label', {},
      el('input', {
        type: 'checkbox', value: s.id, disabled: locked, checked: rec.e2.includes(s.id),
        onchange: (event) => {
          if (event.target.checked && rec.e2.length >= E2_MAX) {
            event.target.checked = false;
            return;
          }
          rec.e2 = event.target.checked ? [...rec.e2, s.id] : rec.e2.filter((id) => id !== s.id);
          update();
          save();
          refreshLock(unit, rec);
        },
      }), ` ${s.text}`)))),
    counter);
}

function canLock(rec) {
  return TASKS.checklist.every((item) => rec.e1[item.id]) && rec.e2.length >= E2_MIN && rec.e2.length <= E2_MAX;
}

function refreshLock(unit, rec) {
  const button = $('lock');
  if (button) button.disabled = !canLock(rec);
}

function errorForm(sentence, rec, onAdd) {
  const span = el('input', { type: 'text', placeholder: 'Trecho com erro (copie do texto)' });
  const category = el('select', {}, el('option', { value: '', text: 'Categoria…' }),
    CATEGORIES.map(([value, label]) => el('option', { value, text: label })));
  const correction = el('input', { type: 'text', placeholder: 'Correção' });
  const note = el('input', { type: 'text', placeholder: 'Comentário (opcional)' });
  return el('div', { class: 'error-form' }, span, category, correction, note,
    el('button', {
      type: 'button', text: 'Adicionar erro',
      onclick: () => {
        if (!span.value.trim() || !category.value) return;
        (rec.e4[sentence.id] ??= []).push({ span: span.value.trim(), category: category.value, correction: correction.value.trim(), note: note.value.trim() });
        rec.reviewed[sentence.id] = true;
        save();
        onAdd();
      },
    }));
}

function sentenceBlock(sentence, rec, done) {
  const box = el('li', { class: 'sentence' });
  const draw = () => {
    const errors = rec.e4[sentence.id] || [];
    box.replaceChildren(
      el('p', { class: 'sentence-text', text: sentence.text }),
      el('label', { class: 'clean' }, el('input', {
        type: 'checkbox', disabled: done || errors.length > 0, checked: rec.reviewed[sentence.id] && errors.length === 0,
        onchange: (event) => { rec.reviewed[sentence.id] = event.target.checked; save(); refreshDone(rec); },
      }), ' Conferida, sem erros'),
      errors.length ? el('ul', { class: 'errors' }, errors.map((e, i) => el('li', {},
        `[${e.category}] “${e.span}”${e.correction ? ` → ${e.correction}` : ''}${e.note ? ` (${e.note})` : ''} `,
        done ? null : el('button', {
          type: 'button', class: 'link', text: 'remover',
          onclick: () => {
            errors.splice(i, 1);
            if (!errors.length) rec.reviewed[sentence.id] = false;
            save();
            draw();
            refreshDone(rec);
          },
        })))) : null,
      done ? null : errorForm(sentence, rec, () => { draw(); refreshDone(rec); }));
  };
  draw();
  return box;
}

function refreshDone(rec) {
  const unit = TASKS.units.find((u) => u.id === state.order[state.current]);
  const button = $('finish');
  if (button) button.disabled = !unit.sentences.every((s) => rec.reviewed[s.id]);
}

function e4Block(unit, rec) {
  const done = Boolean(rec.done_at);
  return el('section', { class: 'task' },
    el('h2', { text: 'Etapa 3 · Erros no texto' }),
    el('p', { class: 'hint', text: 'Confira cada frase contra a ficha de dados. Marque “sem erros” ou registre cada erro com sua categoria (veja o guia).' }),
    el('ol', { class: 'sentences' }, unit.sentences.map((s) => sentenceBlock(s, rec, done))),
    done ? el('p', { class: 'hint', text: 'Unidade concluída.' }) : el('button', {
      type: 'button', id: 'finish', class: 'primary', text: 'Concluir unidade', disabled: true,
      onclick: () => { rec.done_at = new Date().toISOString(); save(); go(state.current + 1); },
    }));
}

function render() {
  const unit = TASKS.units.find((u) => u.id === state.order[state.current]);
  const rec = record(unit.id);
  const locked = Boolean(rec.locked_at);
  const nav = el('nav', { class: 'unit-nav' },
    el('button', { type: 'button', text: '← Anterior', disabled: state.current === 0, onclick: () => go(state.current - 1) }),
    el('span', { text: `Unidade ${state.current + 1} de ${state.order.length}` }),
    el('button', { type: 'button', text: 'Próxima →', disabled: state.current === state.order.length - 1, onclick: () => go(state.current + 1) }));
  const tasks = el('div', { class: 'tasks' },
    e1Block(unit, rec, locked),
    e2Block(unit, rec, locked),
    locked ? e4Block(unit, rec) : el('button', {
      type: 'button', id: 'lock', class: 'primary', text: 'Confirmar etapas 1 e 2 e ver o texto', disabled: !canLock(rec),
      onclick: () => { rec.locked_at = new Date().toISOString(); save(); render(); },
    }));
  $('unit').replaceChildren(nav, el('div', { class: 'columns' }, sheet(unit), tasks));
  if (locked) refreshDone(rec);
  window.scrollTo(0, 0);
}

function go(index) {
  state.current = Math.max(0, Math.min(state.order.length - 1, index));
  save();
  render();
}

function exportState() {
  if (!state) return;
  const blob = new Blob([JSON.stringify({ ...state, exported_at: new Date().toISOString() }, null, 1)], { type: 'application/json' });
  const link = el('a', { href: URL.createObjectURL(blob), download: `anotacao_${state.annotator}.json` });
  document.body.append(link);
  link.click();
  link.remove();
}

function importState(file) {
  file.text().then((text) => {
    const imported = JSON.parse(text);
    if (imported.version !== TASKS.version) {
      alert('Este arquivo é de outra versão das tarefas.');
      return;
    }
    if (state && imported.annotator !== state.annotator && !confirm(`Substituir as anotações de ${state.annotator} pelas de ${imported.annotator}?`)) return;
    state = imported;
    save();
    $('start').hidden = true;
    $('unit').hidden = false;
    render();
  });
}

$('begin').addEventListener('click', () => {
  const id = $('annotator').value.trim();
  if (!/^[A-Za-z0-9_-]{2,12}$/.test(id)) {
    $('annotator').focus();
    return;
  }
  state = load(id);
  save();
  $('start').hidden = true;
  $('unit').hidden = false;
  render();
});
$('export').addEventListener('click', exportState);
$('import').addEventListener('change', (event) => event.target.files[0] && importState(event.target.files[0]));
