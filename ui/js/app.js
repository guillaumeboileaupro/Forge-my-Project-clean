'use strict';
// Formulaire hybride du moteur Forge-my-Project. Aucune donnee n'est inseree
// en HTML brut : tout passe par textContent. Le serveur revalide tout.

const $ = selector => document.querySelector(selector);
const NAME = /^[a-z][a-z0-9-]{1,48}[a-z0-9]$/;
const state = {catalog: null, step: 0, lastConfig: null, ready: false, profiles: {}, saveTimer: null,
  approvals: [], candidates: [], decisions: {}, approvalStatus: {}, originalFiles: {}, previewFiles: {},
  selectedPath: null, filesValidated: false, writeRoot: '', comparison: null, resolutions: {}, conflictPath: null};
const DRAFT_KEY = 'forge-my-project.draft.v1';
const ANSWERS_FORMAT = 'forge-my-project/answers';
const MAX_IMPORT_BYTES = 65536;

function element(tag, attributes = {}, text = '') {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text) node.textContent = text;
  return node;
}

function techById(id) {
  return state.catalog.technologies.find(t => t.id === id);
}

function selectedTech() {
  return [...document.querySelectorAll('input[name="tech"]:checked')].map(input => input.value);
}

// --- Rendu a partir du catalogue -----------------------------------------
function renderCatalog() {
  const catalog = state.catalog;
  const type = $('#project_type');
  for (const item of catalog.project_types) type.append(element('option', {value: item.id}, item.label));
  const groups = $('#tech-groups');
  for (const category of catalog.categories) {
    const fieldset = element('fieldset', {'data-category': category.id});
    const bounds = category.max === category.min ? `${category.min}` : `${category.min} a ${category.max}`;
    fieldset.append(element('legend', {}, `${category.label} (${bounds})`));
    for (const tech of catalog.technologies.filter(t => t.category === category.id)) fieldset.append(techRow(tech));
    groups.append(fieldset);
  }
  const agents = $('#agents');
  for (const agent of catalog.agents) {
    const label = element('label', {class: 'check'});
    label.append(element('input', {type: 'checkbox', name: 'agent', value: agent.id}), ` ${agent.name}`);
    agents.append(label);
  }
  const security = $('#security');
  const labels = {strict: 'Strict (defaut)', hardened: 'Renforce : revue de securite, SBOM, actions epinglees'};
  catalog.security_levels.forEach((level, index) => {
    const label = element('label', {class: 'check'});
    const input = element('input', {type: 'radio', name: 'security', value: level});
    if (index === 0) input.checked = true;
    label.append(input, ` ${labels[level] || level}`);
    security.append(label);
  });
}

function techRow(tech) {
  const row = element('div', {class: 'tech', 'data-tech': tech.id});
  const id = `tech-${tech.id}`;
  const label = element('label', {class: 'check', for: id});
  label.append(element('input', {type: 'checkbox', name: 'tech', value: tech.id, id}), ` ${tech.name}`);
  row.append(label, element('span', {class: 'help'}, tech.description));
  if (tech.versions.length) {
    const versionId = `version-${tech.id}`;
    const wrap = element('span', {class: 'version', hidden: ''});
    wrap.append(element('label', {for: versionId}, 'Version'));
    const select = element('select', {id: versionId, 'data-version': tech.id});
    for (const version of tech.versions) {
      const option = element('option', {value: version}, version + (version === tech.preferred ? ' (preferee)' : ''));
      if (version === tech.preferred) option.selected = true;
      select.append(option);
    }
    wrap.append(select);
    row.append(wrap);
  }
  return row;
}

// --- Questions conditionnelles -------------------------------------------
function requirementsMet(tech, selected) {
  return tech.requires.every(options => options.some(id => selected.has(id)));
}

function updateConditional() {
  let selected = new Set(selectedTech());
  let changed = true;
  // Retire en cascade les choix dont les prerequis ont disparu.
  while (changed) {
    changed = false;
    for (const id of [...selected]) {
      if (!requirementsMet(techById(id), selected)) {
        document.getElementById(`tech-${id}`).checked = false;
        selected.delete(id);
        changed = true;
      }
    }
  }
  const hints = [];
  for (const tech of state.catalog.technologies) {
    const row = document.querySelector(`[data-tech="${tech.id}"]`);
    const input = row.querySelector('input[name="tech"]');
    row.hidden = !requirementsMet(tech, selected);
    const conflict = tech.conflicts.find(id => selected.has(id)) ||
      state.catalog.technologies.find(other => selected.has(other.id) && other.conflicts.includes(tech.id));
    input.disabled = Boolean(conflict) && !input.checked;
    if (input.disabled) hints.push(`${tech.name} indisponible : incompatible avec ${techById(conflict.id || conflict).name}`);
    const version = row.querySelector('.version');
    if (version) version.hidden = !input.checked;
  }
  for (const category of state.catalog.categories) {
    const count = state.catalog.technologies.filter(t => t.category === category.id && selected.has(t.id)).length;
    if (count < category.min) hints.push(`${category.label} : au moins ${category.min} choix`);
    if (count > category.max) hints.push(`${category.label} : au plus ${category.max} choix`);
    const fieldset = document.querySelector(`[data-category="${category.id}"]`);
    fieldset.hidden = [...fieldset.querySelectorAll('.tech')].every(row => row.hidden);
  }
  const list = $('#tech-hints');
  list.replaceChildren(...hints.map(text => element('li', {}, text)));
}

// --- Validation et navigation ---------------------------------------------
function stepErrors() {
  const errors = [[], [], [], [], [], []];
  if (!NAME.test($('#name').value)) errors[0].push('Nom de projet invalide');
  const selected = new Set(selectedTech());
  for (const category of state.catalog.categories) {
    const count = state.catalog.technologies.filter(t => t.category === category.id && selected.has(t.id)).length;
    if (count < category.min || count > category.max) errors[1].push(category.label);
  }
  if (!document.querySelector('input[name="agent"]:checked')) errors[2].push('Au moins un agent');
  return errors;
}

function updateBadges() {
  const errors = stepErrors();
  document.querySelectorAll('#steps button').forEach((button, index) => {
    const badge = button.querySelector('.badge');
    badge.hidden = errors[index].length === 0;
    badge.textContent = String(errors[index].length);
    badge.title = errors[index].join(', ');
    button.setAttribute('aria-label', `${button.firstChild.textContent.trim()}${errors[index].length ? ` : ${errors[index].length} erreur(s)` : ''}`);
  });
  return errors;
}

function showStep(index) {
  const steps = document.querySelectorAll('.step');
  state.step = Math.max(0, Math.min(steps.length - 1, index));
  steps.forEach((step, i) => { step.hidden = i !== state.step; });
  document.querySelectorAll('#steps button').forEach((button, i) => {
    if (i === state.step) button.setAttribute('aria-current', 'step'); else button.removeAttribute('aria-current');
  });
  $('#progress').value = state.step + 1;
  $('#prev').disabled = state.step === 0;
  $('#next').disabled = state.step === steps.length - 1;
  steps[state.step].querySelector('h2').focus({preventScroll: false});
}

// --- Configuration et appels serveur ---------------------------------------
function buildConfig() {
  return Object.assign({schema_version: 1}, collectAnswers(), {name: $('#name').value.trim()});
}

function collectAnswers() {
  const technologies = selectedTech();
  const versions = {};
  for (const id of technologies) {
    const select = document.querySelector(`[data-version="${id}"]`);
    if (select) versions[id] = select.value;
  }
  return {
    name: $('#name').value.trim(),
    description: $('#description').value,
    project_type: $('#project_type').value,
    architecture: $('#architecture').value,
    technologies,
    versions,
    agents: [...document.querySelectorAll('input[name="agent"]:checked')].map(input => input.value),
    security: document.querySelector('input[name="security"]:checked').value,
    options: {mcp: selectedMcp().length > 0},
    mcp_servers: selectedMcp(),
    external_skills: state.approvals.map(approval => Object.assign({}, approval)),
  };
}

function requestBody() {
  return JSON.stringify({config: buildConfig(), verify: $('#net-verify').checked, skills: $('#net-skills').checked});
}

function filesRequestBody() {
  const request = JSON.parse(requestBody());
  request.files = state.previewFiles;
  return JSON.stringify(request);
}

async function post(path, body) {
  return fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body});
}

function renderReport(payload) {
  const report = $('#report');
  report.replaceChildren();
  const blocking = payload.diagnostics.filter(d => d.severity === 'error').length;
  report.append(element('p', {class: blocking ? 'error' : 'ok'},
    blocking ? `${blocking} erreur(s) bloquante(s) : generation impossible.` : 'Configuration valide. Relire les avertissements avant de telecharger.'));
  if (payload.error && !payload.diagnostics.length) report.append(element('p', {class: 'error'}, payload.error));
  const list = element('ul', {class: 'diagnostics'});
  for (const diag of payload.diagnostics) {
    list.append(element('li', {class: diag.severity}, `[${diag.severity}] ${diag.message}`));
  }
  report.append(list);
  if (payload.verification) {
    const table = element('ul', {class: 'diagnostics'});
    for (const check of payload.verification) {
      table.append(element('li', {class: check.status === 'PASS' ? 'ok' : check.status === 'FAIL' ? 'error' : 'warning'},
        `${check.status} - ${check.kind} ${check.subject} : ${check.message}`));
    }
    report.append(element('h3', {}, 'Verification en ligne'), table);
  }
}

function isModified(path) {
  return state.previewFiles[path] !== state.originalFiles[path];
}

function modifiedPaths() {
  return Object.keys(state.previewFiles).filter(isModified).sort();
}

function selectFile(path) {
  if (!(path in state.previewFiles)) return;
  state.selectedPath = path;
  $('#files').querySelectorAll('button[data-path]').forEach(button => {
    if (button.dataset.path === path) button.setAttribute('aria-pressed', 'true');
    else button.removeAttribute('aria-pressed');
  });
  $('#file-title').textContent = path;
  $('#content').disabled = false;
  $('#content').value = state.previewFiles[path];
  updateEditorState();
}

function updateEditorState() {
  const path = state.selectedPath;
  const changed = path !== null && isModified(path);
  const count = modifiedPaths().length;
  $('#edit-status').textContent = changed ? 'Modifie' : 'Non modifie';
  $('#edit-status').className = `tag ${changed ? 'warning' : 'ok'}`;
  $('#revert-file').disabled = !changed;
  $('#validate-files').disabled = Object.keys(state.previewFiles).length === 0;
  $('#files').querySelectorAll('[data-modified]').forEach(marker => {
    marker.hidden = !isModified(marker.dataset.modified);
  });
  $('#editor-help').textContent = count
    ? `${count} fichier(s) modifie(s). Valider les contenus avant de creer l'archive.`
    : 'Aucune modification. Valider cet apercu avant de creer l\'archive.';
}

function invalidateFiles() {
  state.filesValidated = false;
  $('#download').disabled = true;
  $('#local-write').disabled = true;
  resetComparison();
}

function renderFiles(contents) {
  state.originalFiles = Object.assign({}, contents);
  state.previewFiles = Object.assign({}, contents);
  state.selectedPath = null;
  state.filesValidated = false;
  const files = $('#files');
  files.replaceChildren();
  const directories = new Map([['', files]]);
  for (const path of Object.keys(contents).sort()) {
    const parts = path.split('/');
    let prefix = '';
    for (const directory of parts.slice(0, -1)) {
      const parent = directories.get(prefix);
      prefix = prefix ? `${prefix}/${directory}` : directory;
      if (!directories.has(prefix)) {
        const item = element('li');
        item.append(element('div', {class: 'directory'}, directory));
        const children = element('ul');
        item.append(children);
        parent.append(item);
        directories.set(prefix, children);
      }
    }
    const item = element('li');
    const button = element('button', {type: 'button', 'data-path': path, title: path});
    button.append(document.createTextNode(parts[parts.length - 1]));
    button.append(element('span', {'data-modified': path, class: 'modified-marker', hidden: ''}, ' •'));
    button.addEventListener('click', () => selectFile(path));
    item.append(button);
    directories.get(prefix).append(item);
  }
  $('#preview').hidden = false;
  // AGENTS.md est le document principal : il est affiche en premier s'il existe.
  const buttons = [...files.querySelectorAll('button[data-path]')];
  const first = buttons.find(b => b.dataset.path === 'AGENTS.md') || buttons[0];
  if (first) first.click();
  updateEditorState();
}

async function validateFiles() {
  if (state.lastConfig !== requestBody()) {
    invalidateFiles();
    $('#status').textContent = 'La configuration a change : relancer la verification.';
    return;
  }
  $('#status').textContent = 'Validation des contenus modifies...';
  $('#validate-files').disabled = true;
  try {
    const response = await post('/api/files/validate', filesRequestBody());
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || 'contenus refuses');
    state.filesValidated = true;
    $('#download').disabled = false;
    $('#local-write').disabled = false;
    $('#status').textContent = `${payload.files.length} fichier(s) valide(s), dont ${payload.modified.length} modifie(s).`;
  } catch (error) {
    invalidateFiles();
    $('#status').textContent = `Validation refusee : ${error.message}`;
  } finally {
    $('#validate-files').disabled = Object.keys(state.previewFiles).length === 0;
  }
}

function navigateFile(offset) {
  const paths = Object.keys(state.previewFiles).sort();
  if (!paths.length) return;
  const current = Math.max(0, paths.indexOf(state.selectedPath));
  selectFile(paths[(current + offset + paths.length) % paths.length]);
  $('#content').focus();
}

function revertFile() {
  if (state.selectedPath === null) return;
  state.previewFiles[state.selectedPath] = state.originalFiles[state.selectedPath];
  $('#content').value = state.previewFiles[state.selectedPath];
  invalidateFiles();
  updateEditorState();
  $('#status').textContent = `Fichier ${state.selectedPath} retabli depuis l'apercu genere.`;
}

async function check() {
  const errors = updateBadges();
  const first = errors.findIndex(list => list.length);
  if (first >= 0 && first < 5) {
    $('#status').textContent = `Section ${first + 1} incomplete : ${errors[first].join(', ')}`;
    return showStep(first);
  }
  $('#status').textContent = 'Verification en cours...';
  $('#download').disabled = true;
  try {
    const body = requestBody();
    const response = await post('/api/plan', body);
    const payload = await response.json();
    renderReport(payload);
    if (response.ok && payload.ok) {
      renderFiles(payload.contents);
      state.lastConfig = body;
      $('#download').disabled = true;
      $('#status').textContent = 'Verification terminee. Examiner puis valider les fichiers.';
    } else {
      $('#preview').hidden = true;
    }
    if (!response.ok) $('#status').textContent = 'Configuration refusee.';
  } catch (error) {
    $('#status').textContent = `Erreur : ${error.message}`;
  }
}

async function download() {
  if (state.lastConfig !== requestBody()) {
    invalidateFiles();
    $('#status').textContent = 'La configuration a change : relancer la verification.';
    return;
  }
  if (!state.filesValidated) {
    $('#status').textContent = 'Valider les contenus avant de creer l\'archive.';
    return;
  }
  $('#status').textContent = 'Controles repetes avant generation...';
  try {
    const response = await post('/api/archive', filesRequestBody());
    if (!response.ok) {
      renderReport(await response.json());
      throw new Error('archive refusee');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = element('a', {href: url, download: `${buildConfig().name}.zip`});
    link.click();
    URL.revokeObjectURL(url);
    $('#status').textContent = 'Archive generee.';
  } catch (error) {
    $('#status').textContent = `Erreur : ${error.message}`;
  }
}

// --- Ecriture locale : destination, comparaison, fusion, confirmation (T17) --
function resetComparison(message = '') {
  state.comparison = null;
  state.resolutions = {};
  state.conflictPath = null;
  $('#comparison').hidden = true;
  $('#conflict').hidden = true;
  $('#write-confirm').checked = false;
  $('#write').disabled = true;
  if (message) $('#write-report').textContent = message;
}

function writeBody(extra) {
  const request = JSON.parse(filesRequestBody());
  return JSON.stringify(Object.assign(request, {destination: $('#destination').value.trim()}, extra));
}

async function browseDestination(path) {
  showAlert('');
  try {
    const response = await post('/api/destination/browse', JSON.stringify(path ? {path} : {}));
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || 'dossier refuse');
    state.writeRoot = payload.root;
    $('#dest-root').textContent = payload.root;
    $('#destination').value = payload.path;
    $('#browse-up').disabled = payload.parent === null;
    $('#browse-up').dataset.parent = payload.parent || '';
    const list = $('#dest-dirs');
    list.replaceChildren();
    for (const name of payload.directories) {
      const button = element('button', {type: 'button', 'data-dir': name}, name);
      button.addEventListener('click', () => browseDestination(`${payload.path}/${name}`));
      const item = element('li');
      item.append(button);
      list.append(item);
    }
    resetComparison();
  } catch (error) {
    showAlert(`Parcours refuse : ${error.message}`);
  }
}

const STATUS_LABELS = {new: 'nouveau', identical: 'identique', conflict: 'conflit', blocked: 'bloque'};
const RESOLUTION_LABELS = {keep: 'conserve', replace: 'remplace', merge: 'fusionne'};
const OPERATION_LABELS = {created: 'cree', replaced: 'remplace', merged: 'fusionne', kept: 'conserve', identical: 'identique', 'rolled-back': 'annule'};

function renderComparison() {
  const {entries, summary, destination} = state.comparison;
  $('#comparison').hidden = false;
  $('#compare-summary').textContent = `${destination.exists ? 'Dossier existant' : 'Nouveau dossier'}${destination.writable ? '' : ' (NON accessible en ecriture)'} : `
    + `${summary.new} nouveau(x), ${summary.identical} identique(s), ${summary.conflict} conflit(s), ${summary.blocked} bloque(s).`;
  const list = $('#compare-list');
  list.replaceChildren();
  for (const entry of entries) {
    const item = element('li', {'data-entry': entry.path, 'data-status': entry.status});
    const button = element('button', {type: 'button'}, entry.path);
    button.disabled = entry.status !== 'conflict';
    button.addEventListener('click', () => selectConflict(entry.path));
    const css = entry.status === 'conflict' || entry.status === 'blocked' ? 'warning' : 'ok';
    const resolution = state.resolutions[entry.path];
    const label = entry.status === 'conflict' ? (resolution ? `conflit : ${RESOLUTION_LABELS[resolution.action]}` : 'conflit : a decider')
      : STATUS_LABELS[entry.status];
    item.append(button, element('span', {class: `tag ${entry.status === 'blocked' ? 'error' : css}`}, label));
    list.append(item);
  }
  updateWriteButton();
}

function selectConflict(path) {
  const entry = state.comparison.entries.find(e => e.path === path);
  state.conflictPath = path;
  $('#conflict').hidden = false;
  $('#conflict-title').textContent = path;
  $('#conflict-reason').textContent = entry.reason;
  $('#diff').textContent = entry.diff || '(diff indisponible : contenu binaire ou trop volumineux)';
  document.querySelector('input[name="resolution"][value="merge"]').disabled = !entry.mergeable;
  const current = state.resolutions[path];
  document.querySelectorAll('input[name="resolution"]').forEach(radio => { radio.checked = current ? radio.value === current.action : false; });
  $('#merge').hidden = !current || current.action !== 'merge';
  $('#merge-content').value = current && current.action === 'merge' ? current.content : (entry.existing || '');
  $('#diff').focus();
}

function resolutionChanged() {
  const path = state.conflictPath;
  const checked = document.querySelector('input[name="resolution"]:checked');
  if (!path || !checked) return;
  if (checked.value === 'merge') {
    $('#merge').hidden = false;
    state.resolutions[path] = {action: 'merge', content: $('#merge-content').value};
  } else {
    $('#merge').hidden = true;
    state.resolutions[path] = {action: checked.value};
  }
  renderComparison();
}

function updateWriteButton() {
  const comparison = state.comparison;
  const pending = comparison ? comparison.entries.filter(e => e.status === 'conflict' && !state.resolutions[e.path]).length : 0;
  const blocked = comparison ? comparison.summary.blocked : 0;
  $('#write').disabled = !comparison || pending > 0 || blocked > 0 || !comparison.destination.writable || !$('#write-confirm').checked;
  if (comparison && (pending || blocked)) {
    $('#write-report').textContent = blocked ? 'Ecriture impossible : entrees non sures (liens symboliques, fichiers speciaux) dans la destination.'
      : `${pending} conflit(s) sans decision : conserver, remplacer ou fusionner chaque fichier.`;
  } else if (comparison) {
    $('#write-report').textContent = '';
  }
}

function stillValid() {
  if (state.lastConfig !== requestBody() || !state.filesValidated) {
    invalidateFiles();
    $('#status').textContent = 'La configuration ou les fichiers ont change : verifier et valider a nouveau.';
    return false;
  }
  return true;
}

async function compareDestination() {
  showAlert('');
  if (!stillValid()) return;
  resetComparison();
  if (!$('#destination').value.trim() && state.writeRoot) $('#destination').value = `${state.writeRoot}/${buildConfig().name}`;
  $('#status').textContent = 'Comparaison avec la destination...';
  try {
    const response = await post('/api/write/compare', writeBody({}));
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      if (payload.diagnostics && payload.diagnostics.length) renderReport(payload);
      throw new Error(payload.error || 'comparaison refusee');
    }
    state.comparison = payload;
    renderComparison();
    $('#status').textContent = 'Comparaison terminee : aucune ecriture effectuee.';
  } catch (error) {
    $('#status').textContent = `Comparaison refusee : ${error.message}`;
  }
}

function renderWriteReport(report, title) {
  const container = $('#write-report');
  container.replaceChildren(element('p', {class: report.status === 'ok' ? 'ok' : 'error'}, title));
  if (report.backup) container.append(element('p', {}, `Sauvegarde des fichiers remplaces : ${report.destination}/${report.backup} (voir MANIFEST.json pour restaurer).`));
  if (report.summary) {
    const s = report.summary;
    container.append(element('p', {}, `${s.created} cree(s), ${s.replaced} remplace(s), ${s.merged} fusionne(s), ${s.kept} conserve(s), ${s.identical} identique(s).`));
  }
  const list = element('ul', {id: 'write-operations'});
  for (const op of report.operations) list.append(element('li', {'data-op': op.action}, `${OPERATION_LABELS[op.action] || op.action} : ${op.path}`));
  container.append(list);
  if (report.journal && report.journal.non_verifie.length) {
    const unverified = element('ul');
    for (const message of report.journal.non_verifie) unverified.append(element('li', {class: 'warning'}, message));
    container.append(element('p', {}, 'Avertissements (a relire, non bloquants) :'), unverified);
  }
  for (const message of report.restore_errors || []) container.append(element('p', {class: 'error'}, `Restauration incomplete : ${message}`));
}

async function writeFiles() {
  showAlert('');
  if (!stillValid() || !state.comparison) return;
  const {summary, destination} = state.comparison;
  const replaced = Object.values(state.resolutions).filter(r => r.action !== 'keep').length;
  if (!window.confirm(`Ecrire dans ${destination.path} : ${summary.new} creation(s), ${replaced} remplacement(s) ou fusion(s) sauvegarde(s) ? Cette action modifie le dossier.`)) return;
  $('#write').disabled = true;
  $('#status').textContent = 'Controles repetes puis ecriture...';
  try {
    const response = await post('/api/write/apply', writeBody({token: state.comparison.token, decisions: state.resolutions, confirm: true}));
    const payload = await response.json();
    if (response.ok && payload.ok) {
      renderWriteReport(payload.report, 'Ecriture terminee.');
      state.comparison = null;
      $('#comparison').hidden = true;
      $('#status').textContent = `Fichiers ecrits dans ${destination.path}.`;
      return;
    }
    if (response.status === 409) {
      resetComparison();
      if (payload.report) renderWriteReport(payload.report, 'Ecriture annulee, etat precedent restaure.');
      $('#status').textContent = `${payload.error}`;
      return;
    }
    if (payload.report) renderWriteReport(payload.report, 'Ecriture interrompue : modifications annulees.');
    throw new Error(payload.error || 'ecriture refusee');
  } catch (error) {
    $('#status').textContent = `Ecriture refusee : ${error.message}`;
    updateWriteButton();
  }
}

function setupLocalWrite() {
  $('#browse').addEventListener('click', () => browseDestination($('#destination').value.trim()));
  $('#browse-up').addEventListener('click', event => browseDestination(event.currentTarget.dataset.parent));
  $('#compare').addEventListener('click', compareDestination);
  $('#destination').addEventListener('input', () => resetComparison());
  document.querySelectorAll('input[name="resolution"]').forEach(radio => radio.addEventListener('change', resolutionChanged));
  $('#merge-content').addEventListener('input', () => {
    if (state.conflictPath && state.resolutions[state.conflictPath]) state.resolutions[state.conflictPath].content = $('#merge-content').value;
  });
  $('#write-confirm').addEventListener('change', updateWriteButton);
  $('#write').addEventListener('click', writeFiles);
  browseDestination('');
}

// --- Application de reponses validees (brouillon, import, profil) ---------
function applyAnswers(answers) {
  if ('name' in answers) $('#name').value = answers.name;
  if ('description' in answers) $('#description').value = answers.description;
  $('#project_type').value = answers.project_type;
  $('#architecture').value = answers.architecture;
  document.querySelectorAll('input[name="tech"]').forEach(input => { input.checked = false; });
  // Coche les technologies dans l'ordre des prerequis pour conserver les choix conditionnels.
  const wanted = new Set(answers.technologies), selected = new Set();
  let progress = true;
  while (progress) {
    progress = false;
    for (const id of wanted) {
      const tech = techById(id);
      if (tech && !selected.has(id) && requirementsMet(tech, selected)) {
        document.getElementById(`tech-${id}`).checked = true;
        selected.add(id);
        progress = true;
      }
    }
  }
  updateConditional();
  for (const [id, version] of Object.entries(answers.versions)) {
    const select = document.querySelector(`[data-version="${id}"]`);
    if (select) select.value = version;
  }
  document.querySelectorAll('input[name="agent"]').forEach(input => { input.checked = answers.agents.includes(input.value); });
  document.querySelectorAll('input[name="security"]').forEach(input => { input.checked = input.value === answers.security; });
  const servers = new Set(answers.mcp_servers || []);
  document.querySelectorAll('input[name="mcp"]').forEach(input => { input.checked = servers.has(input.value); });
  updateMcp();
  setApprovals(answers.external_skills || []);
  invalidateFiles();
  updateBadges();
}

function showAlert(message) {
  $('#alert').textContent = message;
}

async function validateDocument(documentValue) {
  const response = await post('/api/answers/validate', JSON.stringify({document: documentValue}));
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || 'reponses invalides');
  return payload;
}

// --- Serveurs MCP optionnels (T15) -------------------------------------------
// Pertinence calculee ici pour l'affichage ; le serveur la revalide.
function selectedMcp() {
  return [...document.querySelectorAll('input[name="mcp"]:checked')]
    .filter(input => !input.closest('[data-mcp]').hidden).map(input => input.value);
}

function renderMcp() {
  const list = $('#mcp-list');
  list.replaceChildren();
  for (const server of state.catalog.mcp_servers) {
    const item = element('div', {class: 'skill', 'data-mcp': server.id, 'data-types': server.project_types.join(' ')});
    const label = element('label', {class: 'check', for: `mcp-${server.id}`});
    label.append(element('input', {type: 'checkbox', id: `mcp-${server.id}`, name: 'mcp', value: server.id}),
      document.createTextNode(` ${server.name}`));
    const facts = element('dl');
    detail(facts, 'Besoin', server.need);
    detail(facts, 'Pertinence', server.reason);
    detail(facts, 'Provenance', `registre MCP ${server.registry_name}, ${server.repository} (${server.license})`);
    detail(facts, 'Execution', server.transport);
    if (server.token_env) detail(facts, 'Jeton', `variable d'environnement ${server.token_env} (jamais ecrite)`);
    detail(facts, 'Permissions', server.permissions.join(' '));
    item.append(label, facts);
    list.append(item);
  }
}

function updateMcp() {
  const type = $('#project_type').value;
  let visible = 0;
  document.querySelectorAll('[data-mcp]').forEach(item => {
    const types = item.dataset.types ? item.dataset.types.split(' ') : [];
    item.hidden = types.length > 0 && !types.includes(type);
    if (item.hidden) item.querySelector('input').checked = false;
    else visible += 1;
  });
  $('#mcp-empty').hidden = visible > 0;
}

// --- Skills externes (T10) ---------------------------------------------------
// Le navigateur ne decide pas de la confiance : il transmet les approbations,
// que le serveur revalide (format, commit, empreinte) et recontrole a la copie.
function skillKey(item) {
  return [item.repository, item.path, item.name, item.commit].join('|');
}

function setApprovals(approvals, status = 'non verifiee depuis le chargement') {
  state.approvals = approvals.map(approval => Object.assign({}, approval));
  state.approvalStatus = {};
  for (const approval of state.approvals) state.approvalStatus[skillKey(approval)] = {status, message: ''};
  renderApprovals();
}

function approvalsChanged() {
  renderApprovals();
  renderCandidates();
  if (state.lastConfig !== null && state.lastConfig !== requestBody()) invalidateFiles();
  scheduleSave();
}

function skillLink(item) {
  const path = [item.path, item.name].filter(part => part && part !== '.').join('/');
  const href = `https://github.com/${encodeURI(item.repository)}/tree/${encodeURIComponent(item.commit)}/${encodeURI(path)}`;
  return element('a', {href, target: '_blank', rel: 'noopener noreferrer'}, 'Examiner le contenu sur GitHub');
}

function detail(list, term, value) {
  list.append(element('dt', {}, term), element('dd', {}, value));
}

function renderCandidates() {
  const container = $('#skills-candidates');
  container.replaceChildren();
  for (const candidate of state.candidates) {
    const key = skillKey(candidate);
    const decision = state.approvals.some(a => skillKey(a) === key) ? 'approved' : state.decisions[key];
    const item = element('li', {class: `skill ${decision || ''}`.trim(), 'data-skill': candidate.name});
    const title = element('p', {class: 'skill-title'});
    title.append(element('strong', {}, candidate.name), document.createTextNode(' '),
      element('span', {class: candidate.recognized ? 'tag ok' : 'tag warning'},
        candidate.recognized ? 'source reconnue' : 'source non reconnue'));
    const facts = element('dl');
    detail(facts, 'Description', candidate.description || '(aucune)');
    detail(facts, 'Provenance', `${candidate.source} : ${candidate.repository}/${candidate.path}`);
    detail(facts, 'Commit', candidate.commit);
    detail(facts, 'Empreinte', candidate.digest);
    detail(facts, 'Fichiers copies', candidate.copied_files.join(', ') || '(aucun)');
    detail(facts, 'Fichiers ignores', candidate.ignored_files.join(', ') || '(aucun)');
    if (candidate.notes.length) detail(facts, 'A relire', candidate.notes.join(' ; '));
    const actions = element('div', {class: 'row'});
    const approve = element('button', {type: 'button', 'data-action': 'approve', 'aria-label': `Approuver ${candidate.name}`}, 'Approuver');
    const refuse = element('button', {type: 'button', 'data-action': 'refuse', 'aria-label': `Refuser ${candidate.name}`}, 'Refuser');
    approve.disabled = decision === 'approved';
    refuse.disabled = decision === 'refused';
    approve.addEventListener('click', () => approveCandidate(candidate));
    refuse.addEventListener('click', () => refuseCandidate(candidate));
    actions.append(approve, refuse);
    const label = decision === 'approved' ? 'Approuve' : decision === 'refused' ? 'Refuse' : 'En attente de decision';
    item.append(title, facts, skillLink(candidate), actions, element('p', {class: 'help decision'}, label));
    container.append(item);
  }
}

function renderApprovals() {
  const list = $('#skills-approved');
  list.replaceChildren();
  for (const approval of state.approvals) {
    const key = skillKey(approval);
    const check = state.approvalStatus[key] || {status: 'non verifiee', message: ''};
    const css = check.status === 'PASS' ? 'ok' : check.status === 'FAIL' ? 'error' : 'warning';
    const item = element('li', {class: 'skill', 'data-approved': approval.name});
    const title = element('p', {class: 'skill-title'});
    title.append(element('strong', {}, approval.name), document.createTextNode(' '),
      element('span', {class: `tag ${css}`, 'data-status': check.status}, check.status));
    const facts = element('dl');
    detail(facts, 'Depot', `${approval.repository}/${approval.path}`);
    detail(facts, 'Commit', approval.commit);
    detail(facts, 'Empreinte', approval.digest);
    if (check.message) detail(facts, 'Controle', check.message);
    const remove = element('button', {type: 'button', 'aria-label': `Retirer l'approbation de ${approval.name}`}, 'Retirer l\'approbation');
    remove.addEventListener('click', () => refuseCandidate(approval));
    item.append(title, facts, skillLink(approval), remove);
    list.append(item);
  }
  $('#skills-empty').hidden = state.approvals.length > 0;
  $('#skills-verify').disabled = state.approvals.length === 0;
}

function approveCandidate(candidate) {
  showAlert('');
  const key = skillKey(candidate);
  const clash = state.approvals.find(a => a.name === candidate.name && skillKey(a) !== key);
  if (clash) {
    return showAlert(`Un skill nomme « ${candidate.name} » est deja approuve (${clash.repository}) : retirer d'abord cette approbation.`);
  }
  if (!candidate.recognized && !window.confirm(`Source non reconnue (${candidate.repository}). Avez-vous examine tout le contenu de « ${candidate.name} » ?`)) {
    return;
  }
  state.approvals.push(Object.assign({}, candidate.approval));
  state.approvalStatus[key] = {status: 'approuve', message: 'Approuve apres examen dans cette session'};
  state.decisions[key] = 'approved';
  $('#status').textContent = `Skill « ${candidate.name} » approuve au commit ${candidate.commit.slice(0, 12)}.`;
  approvalsChanged();
}

function refuseCandidate(item) {
  const key = skillKey(item);
  state.approvals = state.approvals.filter(a => skillKey(a) !== key);
  delete state.approvalStatus[key];
  state.decisions[key] = 'refused';
  $('#status').textContent = `Skill « ${item.name} » refuse : il ne sera pas copie.`;
  approvalsChanged();
}

async function searchSkills() {
  const errors = updateBadges();
  const first = errors.findIndex(list => list.length);
  if (first >= 0 && first < 4) {
    $('#status').textContent = `Section ${first + 1} incomplete : la recherche depend de la configuration.`;
    return;
  }
  $('#status').textContent = 'Recherche de skills en cours (GitHub)...';
  $('#skills-search').disabled = true;
  try {
    const config = Object.assign(buildConfig(), {external_skills: []});
    const response = await post('/api/skills/search', JSON.stringify({config}));
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || 'recherche refusee');
    state.candidates = payload.candidates;
    const notes = $('#skills-notes');
    notes.replaceChildren(...payload.notes.map(note => element('li', {}, note)));
    renderCandidates();
    $('#status').textContent = `${payload.candidates.length} skill(s) candidat(s) : examiner puis approuver ou refuser.`;
  } catch (error) {
    $('#status').textContent = `Recherche impossible : ${error.message}`;
  } finally {
    $('#skills-search').disabled = false;
  }
}

async function verifySkills() {
  $('#status').textContent = 'Verification des approbations (GitHub)...';
  try {
    const response = await post('/api/skills/verify', JSON.stringify({approvals: state.approvals}));
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'verification refusee');
    for (const check of payload.checks) state.approvalStatus[skillKey(check)] = {status: check.status, message: check.message};
    renderApprovals();
    $('#status').textContent = payload.ok ? 'Approbations verifiees : contenus inchanges.'
      : 'Au moins une approbation n\'est pas verifiee ou le skill a change : retirer ou examiner a nouveau.';
  } catch (error) {
    $('#status').textContent = `Verification impossible : ${error.message}`;
  }
}

// --- Sauvegarde automatique --------------------------------------------------
function storage() {
  try { return window.localStorage; } catch (error) { return null; }
}

function saveDraft() {
  if (!state.ready) return;
  const store = storage();
  if (!store) return;
  try {
    store.setItem(DRAFT_KEY, JSON.stringify({format: ANSWERS_FORMAT, schema_version: 1, answers: collectAnswers()}));
    $('#autosave-status').textContent = `Reponses sauvegardees automatiquement a ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    $('#autosave-status').textContent = 'Sauvegarde automatique indisponible dans ce navigateur.';
  }
}

function scheduleSave() {
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveDraft, 300);
}

async function restoreDraft() {
  const store = storage();
  const raw = store && store.getItem(DRAFT_KEY);
  if (!raw) return;
  try {
    const payload = await validateDocument(JSON.parse(raw));
    applyAnswers(payload.answers);
    $('#autosave-status').textContent = 'Reponses precedentes restaurees.';
  } catch (error) {
    store.removeItem(DRAFT_KEY);
    showAlert(`Brouillon precedent ignore car incompatible : ${error.message}`);
  }
}

function resetForm() {
  const store = storage();
  if (store) store.removeItem(DRAFT_KEY);
  state.ready = false;
  $('#forge').reset();
  updateConditional();
  updateMcp();
  updateBadges();
  $('#download').disabled = true;
  $('#preview').hidden = true;
  state.originalFiles = {};
  state.previewFiles = {};
  state.selectedPath = null;
  state.filesValidated = false;
  $('#content').value = '';
  $('#content').disabled = true;
  $('#report').replaceChildren();
  state.candidates = [];
  state.decisions = {};
  setApprovals([]);
  renderCandidates();
  state.ready = true;
  $('#autosave-status').textContent = 'Questionnaire reinitialise.';
  showStep(0);
}

// --- Import / export JSON ------------------------------------------------------
async function exportAnswers() {
  showAlert('');
  try {
    const payload = await validateDocument({format: ANSWERS_FORMAT, schema_version: 1, answers: collectAnswers()});
    const blob = new Blob([JSON.stringify(payload.export, null, 2) + '\n'], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = element('a', {href: url, download: `${payload.answers.name || 'reponses'}.forge.json`});
    link.click();
    URL.revokeObjectURL(url);
    $('#status').textContent = 'Reponses exportees.';
  } catch (error) {
    showAlert(`Export impossible : ${error.message}`);
  }
}

async function importAnswers(event) {
  const input = event.currentTarget;
  const file = input.files[0];
  input.value = '';
  if (!file) return;
  showAlert('');
  if (file.size > MAX_IMPORT_BYTES) return showAlert('Import refuse : fichier trop volumineux (64 Kio maximum).');
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch (error) {
    return showAlert('Import refuse : le fichier n\'est pas un JSON valide.');
  }
  try {
    const payload = await validateDocument(parsed);
    applyAnswers(payload.answers);
    saveDraft();
    $('#status').textContent = `Configuration importee depuis ${file.name}.`;
  } catch (error) {
    showAlert(`Import refuse : ${error.message}`);
  }
}

// --- Profils -------------------------------------------------------------------
async function refreshProfiles(selectId = '') {
  const select = $('#profile-select');
  try {
    const response = await fetch('/api/profiles');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error);
    state.profiles = {};
    select.replaceChildren(element('option', {value: ''}, 'Choisir un profil...'));
    for (const [label, list] of [['Profils predefinis', payload.predefined], ['Profils personnels', payload.custom]]) {
      if (!list.length) continue;
      const group = element('optgroup', {label});
      for (const profile of list) {
        state.profiles[profile.id] = profile;
        group.append(element('option', {value: profile.id}, profile.label));
      }
      select.append(group);
    }
    select.value = selectId in state.profiles ? selectId : '';
    $('#profile-storage').textContent = `Profils personnels enregistres localement dans ${payload.storage}.`;
  } catch (error) {
    showAlert(`Profils indisponibles : ${error.message}`);
  }
  profileSelected();
}

function profileSelected() {
  const profile = state.profiles[$('#profile-select').value];
  const custom = Boolean(profile) && profile.kind === 'personnalise';
  $('#profile-load').disabled = !profile;
  $('#profile-update').disabled = !custom;
  $('#profile-delete').disabled = !custom;
  $('#profile-info').textContent = profile ? profile.description : '';
  if (custom) {
    $('#profile-label').value = profile.label;
    $('#profile-description').value = profile.description;
  }
}

function loadProfile() {
  const profile = state.profiles[$('#profile-select').value];
  if (!profile) return;
  applyAnswers(profile.answers);
  saveDraft();
  $('#status').textContent = `Profil « ${profile.label} » charge : les reponses restent modifiables.`;
}

async function saveProfile(method) {
  showAlert('');
  const id = $('#profile-select').value;
  const body = JSON.stringify({label: $('#profile-label').value, description: $('#profile-description').value, answers: collectAnswers()});
  const path = method === 'PUT' ? `/api/profiles/${encodeURIComponent(id)}` : '/api/profiles';
  try {
    const response = await fetch(path, {method, headers: {'Content-Type': 'application/json'}, body});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error);
    await refreshProfiles(payload.profile.id);
    $('#status').textContent = `Profil « ${payload.profile.label} » enregistre.`;
  } catch (error) {
    showAlert(`Profil non enregistre : ${error.message}`);
  }
}

async function deleteProfile() {
  const profile = state.profiles[$('#profile-select').value];
  if (!profile || !window.confirm(`Supprimer le profil « ${profile.label} » ?`)) return;
  try {
    const response = await fetch(`/api/profiles/${encodeURIComponent(profile.id)}`, {method: 'DELETE'});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error);
    $('#profile-label').value = '';
    $('#profile-description').value = '';
    await refreshProfiles();
    $('#status').textContent = `Profil « ${profile.label} » supprime.`;
  } catch (error) {
    showAlert(`Suppression impossible : ${error.message}`);
  }
}

async function init() {
  try {
    const response = await fetch('/api/catalog');
    state.catalog = await response.json();
  } catch (error) {
    $('#status').textContent = `Catalogue indisponible : ${error.message}`;
    return;
  }
  renderCatalog();
  renderMcp();
  document.querySelectorAll('.step h2').forEach(h => h.setAttribute('tabindex', '-1'));
  const form = $('#forge');
  form.addEventListener('change', () => {
    updateConditional(); updateMcp(); updateBadges(); scheduleSave();
    if (state.lastConfig !== null && state.lastConfig !== requestBody()) invalidateFiles();
  });
  form.addEventListener('input', () => {
    updateBadges();
    scheduleSave();
    if (state.lastConfig !== null && state.lastConfig !== requestBody()) invalidateFiles();
  });
  form.addEventListener('submit', event => event.preventDefault());
  $('#prev').addEventListener('click', () => showStep(state.step - 1));
  $('#next').addEventListener('click', () => showStep(state.step + 1));
  document.querySelectorAll('#steps button').forEach(button =>
    button.addEventListener('click', () => showStep(Number(button.dataset.goto))));
  $('#check').addEventListener('click', check);
  $('#content').addEventListener('input', event => {
    if (state.selectedPath === null) return;
    state.previewFiles[state.selectedPath] = event.currentTarget.value;
    invalidateFiles();
    updateEditorState();
  });
  $('#previous-file').addEventListener('click', () => navigateFile(-1));
  $('#next-file').addEventListener('click', () => navigateFile(1));
  $('#revert-file').addEventListener('click', revertFile);
  $('#validate-files').addEventListener('click', validateFiles);
  $('#download').addEventListener('click', download);
  setupLocalWrite();
  $('#export').addEventListener('click', exportAnswers);
  $('#import').addEventListener('change', importAnswers);
  $('#reset').addEventListener('click', resetForm);
  // Fermeture ou rechargement : enregistre immediatement la derniere saisie.
  window.addEventListener('pagehide', () => { clearTimeout(state.saveTimer); saveDraft(); });
  $('#profile-select').addEventListener('change', profileSelected);
  $('#profile-load').addEventListener('click', loadProfile);
  $('#profile-create').addEventListener('click', () => saveProfile('POST'));
  $('#profile-update').addEventListener('click', () => saveProfile('PUT'));
  $('#profile-delete').addEventListener('click', deleteProfile);
  $('#skills-search').addEventListener('click', searchSkills);
  $('#skills-verify').addEventListener('click', verifySkills);
  renderApprovals();
  updateConditional();
  updateMcp();
  updateBadges();
  await Promise.all([restoreDraft(), refreshProfiles()]);
  state.ready = true;
  showStep(0);
}

document.addEventListener('DOMContentLoaded', init);
