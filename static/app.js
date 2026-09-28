/* convertkit front end. No framework, no build step -- edit and reload. */
'use strict';

const $ = (id) => document.getElementById(id);
const state = { files: [], catalog: null, tool: null };

const el = {
  drop: $('drop'), picker: $('picker'), files: $('files'), filelist: $('filelist'),
  tools: $('tools'), toolgrid: $('toolgrid'), run: $('run'), runTitle: $('run-title'),
  runBlurb: $('run-blurb'), params: $('params'), go: $('go'), status: $('status'),
  results: $('results'), resultlist: $('resultlist'), zip: $('zip'), engines: $('engines'),
};

const fmtSize = (n) => {
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${units[i]}`;
};

const extOf = (name) => (name.split('.').pop() || '').toLowerCase();

function groupOf(name) {
  const ext = extOf(name);
  for (const [group, exts] of Object.entries(state.catalog.groups)) {
    if (exts.includes(ext)) return group;
  }
  return null;
}

/* --- intake ------------------------------------------------------------- */
el.drop.addEventListener('click', () => el.picker.click());
el.drop.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.picker.click(); }
});
el.picker.addEventListener('change', () => accept([...el.picker.files]));

for (const type of ['dragenter', 'dragover']) {
  el.drop.addEventListener(type, (e) => { e.preventDefault(); el.drop.classList.add('over'); });
}
for (const type of ['dragleave', 'drop']) {
  el.drop.addEventListener(type, (e) => { e.preventDefault(); el.drop.classList.remove('over'); });
}
el.drop.addEventListener('drop', (e) => accept([...e.dataTransfer.files]));
// Dropping anywhere else shouldn't make the browser navigate to the file.
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => e.preventDefault());

function accept(files) {
  if (!files.length) return;
  state.files = files;
  el.picker.value = '';
  renderFiles();
  renderTools();
  hide(el.run); hide(el.results);
}

function renderFiles() {
  el.filelist.innerHTML = '';
  for (const file of state.files) {
    const group = groupOf(file.name);
    const li = document.createElement('li');
    li.innerHTML = `<span class="tag">${group || extOf(file.name) || '?'}</span>
                    <span class="name"></span>
                    <span class="meta">${fmtSize(file.size)}</span>`;
    li.querySelector('.name').textContent = file.name;
    el.filelist.appendChild(li);
  }
  show(el.files);
}

/* --- tool picking -------------------------------------------------------- */
function renderTools() {
  const groups = new Set(state.files.map((f) => groupOf(f.name)).filter(Boolean));
  const many = state.files.length > 1;
  const fits = state.catalog.tools.filter((t) =>
    (t.accepts.includes('*') || t.accepts.some((a) => groups.has(a))) && (!many || t.multi));

  el.toolgrid.innerHTML = '';
  if (!fits.length) {
    const known = [...groups].join(', ') || 'unrecognised';
    el.toolgrid.innerHTML =
      `<p class="blurb">Nothing here handles ${known} files${many ? ' in a batch' : ''} yet.</p>`;
    show(el.tools);
    return;
  }

  for (const category of [...new Set(fits.map((t) => t.category))]) {
    const heading = document.createElement('p');
    heading.className = 'cat';
    heading.textContent = category;
    el.toolgrid.appendChild(heading);

    const grid = document.createElement('div');
    grid.className = 'grid';
    for (const tool of fits.filter((t) => t.category === category)) {
      const button = document.createElement('button');
      button.className = 'tool';
      button.disabled = !tool.available;
      button.innerHTML = `<strong></strong><span></span>`;
      button.querySelector('strong').textContent = tool.label;
      button.querySelector('span').textContent = tool.blurb;
      if (!tool.available) {
        const hint = document.createElement('code');
        hint.textContent = tool.missing.map((m) => m.hint || m.engine).join(' · ');
        button.appendChild(document.createElement('br'));
        button.appendChild(hint);
      } else {
        button.addEventListener('click', () => selectTool(tool));
      }
      grid.appendChild(button);
    }
    el.toolgrid.appendChild(grid);
  }
  show(el.tools);
}

/* --- parameters ---------------------------------------------------------- */
function selectTool(tool) {
  state.tool = tool;
  el.runTitle.textContent = tool.label;
  el.runBlurb.textContent = tool.blurb;
  el.params.innerHTML = '';
  el.status.hidden = true;

  for (const p of tool.params) {
    const field = document.createElement('div');
    field.className = p.kind === 'bool' ? 'field check' : 'field';
    const id = `p_${p.name}`;
    let input;

    if (p.kind === 'select') {
      input = document.createElement('select');
      for (const [value, label] of p.options) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        if (value === p.default) option.selected = true;
        input.appendChild(option);
      }
    } else if (p.kind === 'bool') {
      input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = Boolean(p.default);
    } else {
      input = document.createElement('input');
      input.type = p.kind === 'number' ? 'number' : (p.kind === 'password' ? 'password' : 'text');
      if (p.default !== null && p.default !== undefined) input.value = p.default;
      input.placeholder = p.placeholder || '';
    }
    input.id = id;
    input.dataset.name = p.name;
    input.dataset.kind = p.kind;

    const label = document.createElement('label');
    label.htmlFor = id;
    label.textContent = p.label + (p.required ? ' *' : '');

    if (p.kind === 'bool') {
      field.append(input, label);
    } else {
      field.append(label, input);
      if (p.help) {
        const help = document.createElement('p');
        help.className = 'help';
        help.textContent = p.help;
        field.appendChild(help);
      }
    }
    el.params.appendChild(field);
  }

  show(el.run);
  hide(el.results);
  el.run.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function collectParams() {
  const out = {};
  for (const input of el.params.querySelectorAll('[data-name]')) {
    const { name, kind } = input.dataset;
    if (kind === 'bool') out[name] = input.checked;
    else if (kind === 'number') out[name] = input.value === '' ? null : Number(input.value);
    else out[name] = input.value;
  }
  return out;
}

/* --- running ------------------------------------------------------------- */
el.go.addEventListener('click', async () => {
  if (!state.tool) return;
  const body = new FormData();
  body.append('tool_id', state.tool.id);
  body.append('params', JSON.stringify(collectParams()));
  for (const file of state.files) body.append('files', file, file.name);

  el.go.disabled = true;
  setStatus('Working…', '');

  try {
    const res = await fetch('/api/run', { method: 'POST', body });
    const data = await res.json().catch(() => ({ error: `Server said ${res.status}` }));
    if (!res.ok) {
      setStatus(data.error || data.detail || `Failed (${res.status})`, 'err');
      return;
    }
    setStatus('', '');
    el.status.hidden = true;
    showResults(data);
  } catch (err) {
    setStatus(`Could not reach the server: ${err.message}`, 'err');
  } finally {
    el.go.disabled = false;
  }
});

function showResults(data) {
  el.resultlist.innerHTML = '';
  for (const file of data.files) {
    const li = document.createElement('li');
    li.innerHTML = `<span class="name"></span>
                    <span class="meta">${fmtSize(file.size)}</span>
                    <a class="link" download>Download</a>`;
    li.querySelector('.name').textContent = file.name;
    const link = li.querySelector('a');
    link.href = file.url;
    link.download = file.name;
    el.resultlist.appendChild(li);
  }
  if (data.zip) {
    el.zip.href = data.zip;
    el.zip.hidden = false;
  } else {
    el.zip.hidden = true;
  }
  show(el.results);
  el.results.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function setStatus(text, kind) {
  el.status.textContent = text;
  el.status.className = `status ${kind}`;
  el.status.hidden = !text;
}

const show = (node) => { node.hidden = false; };
const hide = (node) => { node.hidden = true; };

$('clear').addEventListener('click', () => {
  state.files = []; state.tool = null;
  [el.files, el.tools, el.run, el.results].forEach(hide);
});
$('back').addEventListener('click', () => { hide(el.run); hide(el.results); });
$('again').addEventListener('click', () => { hide(el.results); show(el.tools); });

/* --- boot ---------------------------------------------------------------- */
fetch('/api/catalog')
  .then((r) => r.json())
  .then((catalog) => {
    state.catalog = catalog;
    for (const [name, info] of Object.entries(catalog.engines)) {
      const li = document.createElement('li');
      li.innerHTML = `<span class="dot${info.available ? ' on' : ''}"></span>
                      <span>${name}</span>`;
      if (!info.available && info.hint) {
        const code = document.createElement('code');
        code.textContent = info.hint;
        li.appendChild(code);
      }
      el.engines.appendChild(li);
    }
  })
  .catch(() => {
    el.drop.querySelector('.big').textContent = 'Server not reachable';
  });
