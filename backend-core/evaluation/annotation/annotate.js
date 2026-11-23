// Annotation page for E4 (text accuracy) and content selection: the relevance of every sentence
// (E2b) and the facts left out that should have been told (E2). The system's answers are never
// loaded (they live in system.json). Progress stays in this browser and is exported as JSON.

const TASKS = window.ANNOTATION_TASKS;
const STORE_PREFIX = 'anotacao-tcc:';
const CATEGORIES = [
  ['NUMERO', 'Número incorreto: não bate com os dados'],
  ['ESCALA', 'Escala errada: o número é de outra escala (raio, área de atendimento, distrito, município, região)'],
  ['NOME', 'Nome ou período incorreto: lugar, ano ou intervalo de anos'],
  ['PALAVRA', 'Palavra incorreta: comparativo, direção ou termo que não corresponde aos dados'],
  ['CONTEXTO', 'Contexto: correto, mas enganoso; falta um aviso ou um aviso não faz sentido'],
  ['NAO_VERIFICAVEL', 'Não verificável com os dados mostrados'],
  ['OUTRO', 'Outro erro'],
];

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
  state.units[id] ??= { e4: {}, reviewed: {}, relevance: {}, omitted: [], none: false, started_at: new Date().toISOString() };
  return state.units[id];
}

function renderProgress() {
  if (!state) return;
  const done = Object.values(state.units).filter((u) => u.done_at).length;
  $('progress').textContent = `${state.annotator} · ${done} de ${TASKS.units.length} unidades concluídas`;
}

// What the text left out: tick the facts that should have been told, or "Nenhuma". The two are
// exclusive, and one of them is required, so that no answer is not read as "nothing missing".
function omittedStep(unit, rec, done) {
  const list = el('ul', { class: 'options' });
  const draw = () => {
    const option = (checked, body, onchange, extra = '') => el('li', {}, el('label', { class: `option${checked ? ' is-checked' : ''}${extra}` },
      el('input', { type: 'checkbox', disabled: done, checked, onchange }), body));
    const fact = (o) => el('div', { class: 'option-body' },
      el('p', { class: 'option-title' }, o.scale ? el('span', { class: 'scale-tag', text: o.scale }) : null, el('span', { text: o.title })),
      el('table', {}, el('tbody', {}, o.rows.map(([label, value]) => el('tr', {}, el('th', { scope: 'row', text: capital(label) }), el('td', { text: value }))))));
    const changed = () => { save(); draw(); refreshDone(); };
    list.replaceChildren(
      ...unit.omitted.map((o) => option(rec.omitted.includes(o.id), fact(o), (event) => {
        rec.omitted = event.target.checked ? [...rec.omitted, o.id] : rec.omitted.filter((x) => x !== o.id);
        if (event.target.checked) rec.none = false;
        changed();
      })),
      option(rec.none, el('span', { text: 'Nenhuma: o texto não deixou de fora nada que deveria estar nele' }), (event) => {
        rec.none = event.target.checked;
        if (rec.none) rec.omitted = [];
        changed();
      }, ' is-none'));
  };
  draw();
  return el('section', { class: 'step' },
    stepHead(2, 'O que ficou de fora'),
    el('div', { class: 'step-intro' },
      el('p', { text: 'Estas informações foram calculadas para esta unidade, mas não estão no texto. Alguma delas deveria estar? Marque quantas quiser, ou “Nenhuma”.' }),
      el('p', { class: 'scale-note', text: 'Repare na escala de cada uma, na etiqueta ao lado do título. Dados do município ou do distrito descrevem uma área bem maior que o entorno da unidade: a dengue “no município de São Paulo”, por exemplo, é da cidade inteira, não do bairro.' })),
    list);
}

function stepHead(number, title) {
  return el('h2', { class: 'step-head' }, el('span', { class: 'step-number', text: String(number) }), el('span', { text: `Etapa ${number} de 2 · ${title}` }));
}

const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);

function dataBlocks(blocks) {
  return blocks.map((block) => el('div', { class: 'data-block' },
    el('p', { class: 'data-name', text: block.title }),
    el('table', {}, el('tbody', {}, block.rows.map(([label, value]) => el('tr', {},
      el('th', { scope: 'row', text: capital(label) }), el('td', { text: value })))))));
}

function dataBox(sentence) {
  return el('div', { class: 'data' },
    el('p', { class: 'data-title', text: sentence.kind === 'caveat' ? 'Dados a que o aviso se refere' : 'Dados para conferir' }),
    sentence.data.length ? dataBlocks(sentence.data)
      : el('p', { class: 'data-empty', text: 'Nenhum dado ligado a esta frase. Confira em “Todos os dados desta unidade”, no alto da etapa.' }));
}

function errorForm(sentence, rec, onAdd) {
  const field = (label, control) => el('label', { class: 'field' }, el('span', { text: label }), control);
  const span = el('input', { type: 'text', placeholder: 'copie o trecho do texto' });
  const category = el('select', {}, el('option', { value: '', text: 'Escolha a categoria…' }),
    CATEGORIES.map(([value, label]) => el('option', { value, text: label })));
  const correction = el('input', { type: 'text', placeholder: 'opcional' });
  const warning = el('p', { class: 'form-warning', hidden: true, text: 'Preencha o trecho e a categoria.' });
  return el('details', { class: 'error-form' },
    el('summary', { text: 'Encontrei um erro: registrar' }),
    el('div', { class: 'error-fields' },
      field('Trecho com erro', span), field('Categoria', category), field('Correção', correction), warning,
      el('button', {
        type: 'button', text: 'Adicionar erro',
        onclick: () => {
          if (!span.value.trim() || !category.value) {
            warning.hidden = false;
            return;
          }
          (rec.e4[sentence.id] ??= []).push({ span: span.value.trim(), category: category.value, correction: correction.value.trim() });
          rec.reviewed[sentence.id] = true;
          save();
          onAdd();
        },
      })));
}

function answered(rec, id) {
  return Boolean(rec.reviewed[id] && rec.relevance[id]);
}

function sentenceBlock(sentence, index, total, rec, done) {
  const box = el('li', { class: 'sentence' });
  const badge = el('span', { class: 'answered', text: '✓ respondida' });
  const mark = () => {
    box.classList.toggle('is-answered', answered(rec, sentence.id));
    badge.hidden = !answered(rec, sentence.id);
    refreshDone();
  };
  const draw = () => {
    const errors = rec.e4[sentence.id] || [];
    box.replaceChildren(...[
      el('div', { class: 'sentence-head' }, el('span', { class: 'sentence-number', text: `Frase ${index + 1} de ${total}` }), badge),
      el('p', { class: 'sentence-text', text: sentence.text }),
      sentence.check ? el('div', { class: 'check-note' }, el('p', { class: 'check-note-title', text: 'O que conferir nesta frase' }),
        el('p', { text: sentence.check })) : null,
      dataBox(sentence),
      el('div', { class: 'questions' },
        el('div', { class: 'question' },
          el('p', { class: 'question-label', text: sentence.kind === 'caveat' ? 'O aviso está correto e vale para esta unidade?' : 'A frase bate com os dados?' }),
          el('label', { class: 'check' }, el('input', {
            type: 'checkbox', disabled: done || errors.length > 0, checked: rec.reviewed[sentence.id] && errors.length === 0,
            onchange: (event) => { rec.reviewed[sentence.id] = event.target.checked; save(); mark(); },
          }), el('span', { text: 'Sim, conferida: sem erros' })),
          errors.length ? el('ul', { class: 'errors' }, errors.map((e, i) => el('li', {},
            el('span', { class: 'error-category', text: e.category }),
            el('span', { text: `“${e.span}”${e.correction ? ` → ${e.correction}` : ''}` }),
            done ? null : el('button', {
              type: 'button', class: 'link', text: 'remover',
              onclick: () => {
                errors.splice(i, 1);
                if (!errors.length) rec.reviewed[sentence.id] = false;
                save();
                draw();
              },
            })))) : null,
          done ? null : errorForm(sentence, rec, () => draw())),
        relevanceChoice(sentence, rec, done, mark)),
    ].filter(Boolean));
    mark();
  };
  draw();
  return box;
}

// Precision of content selection: a forced choice for every sentence, so that an unanswered
// sentence is not read as a relevant one.
function relevanceChoice(sentence, rec, done, onChange) {
  const options = [['relevant', 'Relevante'], ['omit', 'Poderia sair do texto']];
  const group = el('div', { class: 'segmented', role: 'radiogroup' });
  const draw = () => group.replaceChildren(...options.map(([value, label]) => el('label', { class: rec.relevance[sentence.id] === value ? 'is-checked' : null },
    el('input', {
      type: 'radio', name: `relevance-${sentence.id}`, value, disabled: done,
      checked: rec.relevance[sentence.id] === value,
      onchange: () => { rec.relevance[sentence.id] = value; save(); draw(); onChange(); },
    }), el('span', { text: label }))));
  draw();
  return el('div', { class: 'question' },
    el('p', { class: 'question-label', text: 'Para quem lê a página, esta frase é:' }), group);
}

function refreshDone() {
  const unit = TASKS.units.find((u) => u.id === state.order[state.current]);
  const rec = record(unit.id);
  const count = unit.sentences.filter((s) => answered(rec, s.id)).length;
  const progress = $('sentence-progress');
  if (progress) progress.textContent = `${count} de ${unit.sentences.length} frases respondidas`;
  const missing = [];
  if (count < unit.sentences.length) missing.push(`${unit.sentences.length - count} ${unit.sentences.length - count === 1 ? 'frase' : 'frases'} da etapa 1`);
  if (!rec.none && rec.omitted.length === 0) missing.push('a etapa 2');
  const button = $('finish');
  if (button) button.disabled = missing.length > 0;
  const status = $('finish-status');
  if (status) status.textContent = missing.length ? `Para concluir, falta responder: ${missing.join(' e ')}.` : 'Tudo respondido.';
}

function errorStep(unit, rec, done) {
  return el('section', { class: 'step' },
    stepHead(1, 'Erros e relevância'),
    el('div', { class: 'step-intro' },
      el('p', { text: 'Para cada frase: compare com os dados logo abaixo dela e marque “sem erros” ou registre o erro com a sua categoria (diferença de arredondamento não é erro). Depois diga se a frase é relevante para quem lê a página.' }),
      el('p', { id: 'sentence-progress', class: 'progress' })),
    el('details', { class: 'all-data' },
      el('summary', { text: 'Todos os dados desta unidade' }), el('div', { class: 'data' }, dataBlocks(unit.data))),
    el('ol', { class: 'sentences' }, unit.sentences.map((s, i) => sentenceBlock(s, i, unit.sentences.length, rec, done))));
}

function render() {
  const unit = TASKS.units.find((u) => u.id === state.order[state.current]);
  const rec = record(unit.id);
  const done = Boolean(rec.done_at);
  const nav = el('nav', { class: 'unit-nav' },
    el('button', { type: 'button', text: '← Anterior', disabled: state.current === 0, onclick: () => go(state.current - 1) }),
    el('span', { class: 'unit-count', text: `Unidade ${state.current + 1} de ${state.order.length}` }),
    el('button', { type: 'button', text: 'Próxima →', disabled: state.current === state.order.length - 1, onclick: () => go(state.current + 1) }));
  $('unit').replaceChildren(nav,
    el('header', { class: 'unit-head' }, el('h1', { text: unit.name }), el('p', { text: unit.type })),
    errorStep(unit, rec, done),
    omittedStep(unit, rec, done),
    el('div', { class: 'finish' }, done ? el('p', { class: 'done', text: '✓ Unidade concluída.' }) : [
      el('button', {
        type: 'button', id: 'finish', class: 'primary', text: 'Concluir unidade e ir para a próxima', disabled: true,
        onclick: () => { rec.done_at = new Date().toISOString(); save(); go(state.current + 1); },
      }),
      el('p', { id: 'finish-status', class: 'finish-status' }),
    ]));
  refreshDone();
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
