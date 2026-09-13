const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Подсказка префикса из meta и src приложенного скрипта (часто совпадает с API). */
function staticHintPrefix() {
  const meta = document.querySelector('meta[name="budjet-mount"]');
  if (meta?.content != null && String(meta.content).trim()) {
    return String(meta.content).replace(/\/+$/, "");
  }
  const s =
    document.getElementById("budjet-app-script") || document.querySelector('script[src*="/static/app.js"]');
  if (!s?.src) return "";
  try {
    const u = new URL(s.src, window.location.href);
    const path = u.pathname.replace(/\/static\/app\.js(?:\?.*)?$/i, "");
    if (path && path !== "/") return path.replace(/\/+$/, "");
  } catch {
    /* ignore */
  }
  return "";
}

/** Если UI открыт как https://host/foo/bar/, пробуем /foo/bar/api, затем /foo/api и т.д. */
function pathnameDerivedPrefixes() {
  let p = (window.location.pathname || "").replace(/\/+$/, "");
  const out = [];
  if (!p) return out;
  const parts = p.split("/").filter(Boolean);
  if (parts.length && /\.html?$/i.test(parts[parts.length - 1])) {
    parts.pop();
  }
  while (parts.length) {
    out.push(`/${parts.join("/")}`);
    parts.pop();
  }
  return out;
}

function directoryPathFromLocation() {
  let p = window.location.pathname || "/";
  if (p.endsWith("/")) return p;
  const last = p.split("/").pop() || "";
  if (last.includes(".")) {
    const i = p.lastIndexOf("/");
    return i <= 0 ? "/" : p.slice(0, i + 1);
  }
  return `${p}/`;
}

/** Если страница …/budget-app/, пробуем …/budget-app/api/labels (частый случай за обратным прокси). */
async function probeLabelsUrlReturningPrefix(absoluteUrl) {
  try {
    const res = await fetch(absoluteUrl, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const text = await res.text();
    if (!text || !/\{/.test(text)) return null;
    const j = JSON.parse(text);
    if (!(j && (Array.isArray(j.flat) || Array.isArray(j.tree)))) return null;
    const u = new URL(absoluteUrl);
    const ix = u.pathname.indexOf("/api/labels");
    if (ix < 0) return "";
    return u.pathname.slice(0, ix).replace(/\/+$/, "") || "";
  } catch {
    return null;
  }
}

async function probePageDirectoryRelativeApi() {
  const dirPath = directoryPathFromLocation();
  const abs = new URL("api/labels?kind=expense", `${window.location.origin}${dirPath}`).href;
  return probeLabelsUrlReturningPrefix(abs);
}

async function probeLabelsAtPrefix(prefix) {
  const url = joinWithPrefix(prefix, "/api/labels?kind=expense");
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return false;
    const text = await res.text();
    if (!/\{/.test(text)) return false;
    const j = JSON.parse(text);
    return Boolean(j && (Array.isArray(j.flat) || Array.isArray(j.tree)));
  } catch {
    return false;
  }
}

function joinWithPrefix(prefix, pathOrUrl) {
  if (!pathOrUrl || /^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  let path = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  if (path.startsWith("/api/") && !path.startsWith("/api/budget/")) {
    path = `/api/budget${path.slice(4)}`;
  }
  const pre = prefix == null ? "" : String(prefix).replace(/\/+$/, "");
  if (!pre) return path;
  return `${pre}${path}`;
}

function budgetAuthHeaders() {
  try {
    const t = localStorage.getItem("note_token");
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch {
    return {};
  }
}

let _resolvedApiPrefix;
/** @type {Promise<string>|null} */
let _detectApiPrefixPromise = null;

async function probeHealthAtPrefix(prefix) {
  const url = joinWithPrefix(prefix, "/api/health");
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return false;
    const text = await res.text();
    if (!text.trim()) return res.ok;
    try {
      const j = JSON.parse(text);
      return Boolean(j && (j.status === "ok" || j.ok === true));
    } catch {
      return res.ok;
    }
  } catch {
    return false;
  }
}

async function detectApiPrefixOnce() {
  const byPage = await probePageDirectoryRelativeApi();
  if (byPage !== null) {
    console.info("[budjet] API через путь страницы, префикс:", byPage === "" ? "(корень)" : byPage);
    return byPage;
  }

  const ordered = [];
  const seen = new Set();
  const add = (p) => {
    const k = p == null ? "" : String(p).replace(/\/+$/, "");
    if (seen.has(k)) return;
    seen.add(k);
    ordered.push(k);
  };
  const h = staticHintPrefix();
  if (h) add(h);
  for (const x of pathnameDerivedPrefixes()) add(x);
  add("");

  for (const prefix of ordered) {
    if (await probeLabelsAtPrefix(prefix)) {
      if (prefix === "" && ordered.length > 1) {
        console.info("[budjet] API на корне (/api/labels). Префикс пустой.");
      } else if (prefix !== "") {
        console.info("[budjet] Найден API с префиксом:", prefix);
      }
      return prefix;
    }
    if (await probeHealthAtPrefix(prefix)) {
      console.info("[budjet] По /api/health префикс:", prefix === "" ? "(корень)" : prefix);
      return prefix;
    }
  }
  console.warn("[budjet] Не нашли рабочий /api/labels и /api/health — используем корень /api/");
  return "";
}

/** В em-note API бюджета всегда /api/budget, JWT из той же вкладки. */
async function ensureApiPrefix() {
  _resolvedApiPrefix = "";
  return "";
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/** Дата «сегодня» в локальном календаре (не UTC — иначе «По» отстаёт на сутки у UTC+n). */
function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function firstOfMonthISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function toast(msg) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    t.hidden = true;
  }, 3800);
}

async function api(path, opts = {}) {
  await ensureApiPrefix();
  const headers = { Accept: "application/json", ...budgetAuthHeaders(), ...opts.headers };
  if (opts.body && typeof opts.body === "string") headers["Content-Type"] = "application/json";
  const res = await fetch(joinWithPrefix(_resolvedApiPrefix, path), { ...opts, headers });
  const text = await res.text();
  if (!res.ok) {
    let detail = res.statusText || `Ошибка ${res.status}`;
    try {
      const j = JSON.parse(text);
      if (j.detail !== undefined && j.detail !== null) {
        if (Array.isArray(j.detail)) {
          detail = j.detail.map((x) => (typeof x === "object" ? x.msg || JSON.stringify(x) : String(x))).join("; ");
        } else {
          detail = String(j.detail);
        }
      }
    } catch {
      const t = text.trim();
      if (t && t.length < 500) detail = t;
    }
    throw new Error(detail);
  }
  if (res.status === 204 || text === "") return null;
  const ct = res.headers.get("content-type") || "";
  const tryJson =
    ct.includes("application/json") ||
    /^\s*[\[{]/.test(text);
  if (tryJson) {
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  }
  return null;
}

async function patchCategoryParent(catId, parentIdOrNull) {
  const body =
    parentIdOrNull === null || parentIdOrNull === undefined
      ? { parent_id: null }
      : { parent_id: Number(parentIdOrNull) };
  await api(`/api/categories/${catId}`, { method: "PATCH", body: JSON.stringify(body) });
}

async function patchLabelParent(labelId, parentIdOrNull) {
  const body =
    parentIdOrNull === null || parentIdOrNull === undefined
      ? { parent_id: null }
      : { parent_id: Number(parentIdOrNull) };
  await api(`/api/labels/${labelId}`, { method: "PATCH", body: JSON.stringify(body) });
}

/** Узел и все потомки в дереве (ответ GET /api/categories) — нельзя делать родителем себя или свою ветку. */
function descendantIdsInclusive(catId, treeRoots) {
  const out = new Set();

  function walk(nodes) {
    for (const n of nodes || []) {
      if (n.id === catId) {
        collect(n);
        return true;
      }
      if (walk(n.children || [])) return true;
    }
    return false;
  }

  function collect(n) {
    out.add(n.id);
    for (const c of n.children || []) collect(c);
  }

  walk(treeRoots || []);
  return out;
}

async function openMoveCategoryDialog(catId, displayName) {
  const dlg = $("#dlg-move-category");
  const cap = $("#move-cat-caption");
  const sel = $("#move-cat-parent");
  const kind = getSelectedKind("cat-admin-kind");
  if (!dlg || !sel) return;
  dlg.dataset.catId = String(catId);
  const label = displayName.trim() ? `«${displayName}»` : `id ${catId}`;
  if (cap) cap.textContent = `${label} — новый родитель или корень.`;
  sel.innerHTML = '<option value="">— корень верхнего уровня —</option>';
  try {
    const data = await fetchCategories(kind);
    const blocked = descendantIdsInclusive(Number(catId), data.tree);
    for (const o of data.flat || []) {
      if (blocked.has(o.id)) continue;
      const opt = document.createElement("option");
      opt.value = String(o.id);
      opt.textContent = o.label;
      opt.title = o.path || o.label;
      sel.appendChild(opt);
    }
    dlg.showModal();
  } catch (e) {
    toast(String(e.message || e));
  }
}

async function openMoveLabelDialog(labelId, displayName) {
  const dlg = $("#dlg-move-label");
  const cap = $("#move-label-caption");
  const sel = $("#move-label-parent");
  const kind = getSelectedKind("label-admin-kind");
  if (!dlg || !sel) return;
  dlg.dataset.labelId = String(labelId);
  const label = displayName.trim() ? `«${displayName}»` : `id ${labelId}`;
  if (cap) cap.textContent = `${label} — новый родитель или корень.`;
  sel.innerHTML = '<option value="">— корень верхнего уровня —</option>';
  try {
    const data = await fetchLabels(kind);
    const blocked = descendantIdsInclusive(Number(labelId), data.tree);
    for (const o of data.flat || []) {
      if (blocked.has(o.id)) continue;
      const opt = document.createElement("option");
      opt.value = String(o.id);
      opt.textContent = o.label;
      opt.title = o.path || o.label;
      sel.appendChild(opt);
    }
    dlg.showModal();
  } catch (e) {
    toast(String(e.message || e));
  }
}

async function downloadBlob(url, filename) {
  await ensureApiPrefix();
  const res = await fetch(joinWithPrefix(_resolvedApiPrefix, url), {
    headers: { ...budgetAuthHeaders() },
  });
  if (!res.ok) {
    toast(`Ошибка экспорта: ${res.status}`);
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  toast("Файл скачан");
}

function fmtMoney(n) {
  return Number(n).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Экранирует строку для безопасной подстроки в RegExp (совпадение «как текст»). */
function escapeRegexLiteral(str) {
  return String(str).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function phraseToStoredPattern(phrase) {
  const t = String(phrase).trim();
  if (!t) return "";
  return escapeRegexLiteral(t);
}

function patternFromRuleForm(advancedEl, phraseEl, regexEl) {
  if (advancedEl?.checked) return (regexEl?.value || "").trim();
  return phraseToStoredPattern(phraseEl?.value || "");
}

function hintForMatchedRule(rule) {
  const name = (rule.title || "").trim();
  const pat = String(rule.pattern || "");
  const short = pat.length > 52 ? `${pat.slice(0, 49)}…` : pat;
  if (name) return `«${name}»: ${short}`;
  return short;
}

/** Откуда взята категория: по правилу из комментария, вручную или ещё не выбрана. */
let categorySelectionSource = "none";
let commentRulesCache = [];
/** Метки: вручную или по правилам (несколько правил могут добавить несколько меток). */
let labelSelectionSource = "none";
let commentLabelRulesCache = [];

/** Разбиение быстрого ввода: каждая непустая строка — отдельная позиция (Enter = новая строка, не разделитель). */
function splitQuickBulkRaw(raw) {
  return String(raw || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Одна позиция: «250 Хлеб» или «250,50 Молоко». */
function parseQuickBulkSegment(seg) {
  const t = seg.trim();
  if (!t) return null;
  const m = t.match(/^(\d+(?:[.,]\d+)?)\s+(.+)$/);
  if (!m) return null;
  const amount = Number(String(m[1]).replace(",", "."));
  if (!Number.isFinite(amount) || amount <= 0) return null;
  const note = m[2].trim();
  if (!note) return null;
  return { amount, note };
}

function matchedCategoryIdFromCommentRules(noteText) {
  const text = String(noteText ?? "");
  const rules = Array.isArray(commentRulesCache) ? commentRulesCache : [];
  for (const rule of rules) {
    if (matchesCommentRule(rule.pattern, text)) return rule.category_id;
  }
  return null;
}

function matchedLabelIdsFromCommentRules(noteText) {
  const text = String(noteText ?? "");
  const rules = Array.isArray(commentLabelRulesCache) ? commentLabelRulesCache : [];
  const out = [];
  const seen = new Set();
  for (const rule of rules) {
    if (matchesCommentRule(rule.pattern, text)) {
      const lid = Number(rule.label_id);
      if (Number.isFinite(lid) && !seen.has(lid)) {
        seen.add(lid);
        out.push(lid);
      }
    }
  }
  return out;
}

function txnNoteValue() {
  return document.querySelector('#form-tx [name="note"]')?.value ?? "";
}

function txnFormAmountNumber() {
  const raw = document.querySelector('#form-tx [name="amount"]')?.value ?? "";
  const n = Number(String(raw).replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

/** Прячем второстепенные кнопки, пока в форме операции по сути «пусто». */
function updateTxnFormChrome() {
  const f = $("#form-tx");
  if (!f) return;
  const more = $("#txn-form-more");
  const note = txnNoteValue().trim();
  const catVal = $("#txn-category-id")?.value || "";
  const am = txnFormAmountNumber();
  const editingId = (f.querySelector('[name="id"]')?.value || "").trim();
  const hasDraft = !!(note || catVal || am > 0 || editingId);
  const canTemplate = am > 0;
  const canRulesHint = !!(note.trim());
  if (more) more.hidden = !hasDraft;
  $("#btn-apply-rules-once")?.toggleAttribute("hidden", !canRulesHint);
  $("#save-as-template")?.toggleAttribute("hidden", !canTemplate);
  $("#open-rules-modal")?.toggleAttribute("hidden", !canRulesHint);
  $("#reset-tx")?.toggleAttribute("hidden", !hasDraft);
}

function updateCategoryHint(text) {
  const el = $("#txn-category-hint");
  if (el) el.textContent = text || "";
}

function setCategoryManual() {
  categorySelectionSource = "manual";
  updateCategoryHint("");
}

function matchesCommentRule(pattern, text) {
  try {
    return new RegExp(pattern, "i").test(String(text ?? ""));
  } catch {
    return false;
  }
}

async function refreshCommentRulesCache() {
  const kind = getSelectedKind("kind");
  const data = await api(`/api/comment-rules?kind=${encodeURIComponent(kind)}`);
  commentRulesCache = Array.isArray(data) ? data : [];
}

/** Для быстрого ввода: не блокируем POST, если правила временно недоступны (404 и т.п.). */
async function prefetchRulesCachesForQuickBulk() {
  const kind = getSelectedKind("quick-kind");
  const q = encodeURIComponent(kind);
  let cr = [];
  let lr = [];
  try {
    const data = await api(`/api/comment-rules?kind=${q}`);
    cr = Array.isArray(data) ? data : [];
  } catch {
    cr = [];
  }
  try {
    const data = await api(`/api/comment-label-rules?kind=${q}`);
    lr = Array.isArray(data) ? data : [];
  } catch {
    lr = [];
  }
  commentRulesCache = cr;
  commentLabelRulesCache = lr;
}

/** Подстановка категории по найденному правилу в форме операции. */
function applyMatchedRule(rule) {
  const cid = String(rule.category_id);
  const flat = lastTxnFlat || [];
  const ok = flat.some((o) => String(o.id) === cid);
  if (!ok) {
    toast("Категория правила отсутствует в списке — обновите справочник или правило.");
    categorySelectionSource = "none";
    updateCategoryHint("");
    return false;
  }
  txnCategoryCombo?.setValue(cid, true);
  categorySelectionSource = "rule";
  updateCategoryHint(`Подставлено по правилу: ${hintForMatchedRule(rule)}`);
  $("#form-tx")?.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

/**
 * Сопоставляет комментарий с кэшем правил текущего вида операции (расход/доход).
 * Если не force и пользователь уже выбирал категорию вручную — не трогаем.
 */
function tryApplyCommentRules(noteText, force = false) {
  if (!force && categorySelectionSource === "manual") return;
  const text = String(noteText ?? "");
  for (const rule of commentRulesCache || []) {
    if (matchesCommentRule(rule.pattern, text)) {
      applyMatchedRule(rule);
      return;
    }
  }
  updateCategoryHint("");
  if (categorySelectionSource === "rule") {
    txnCategoryCombo?.setValue("", true);
    categorySelectionSource = "none";
  }
}

function updateLabelRulesHint(text) {
  const el = $("#txn-label-hint");
  if (el) el.textContent = text || "";
}

function setTxnFormLabelChecks(ids) {
  const want = new Set(ids.map((x) => String(x)));
  document.querySelectorAll('#txn-labels input.label-txn-check[type="checkbox"]').forEach((cb) => {
    cb.checked = want.has(cb.value);
  });
}

function getTxnFormLabelIds() {
  return [...document.querySelectorAll('#txn-labels input.label-txn-check[type="checkbox"]:checked')]
    .map((cb) => parseInt(cb.value, 10))
    .filter((n) => Number.isFinite(n));
}

async function refreshTxnLabelsPanel() {
  const host = $("#txn-labels");
  if (!host) return;
  const kind = getSelectedKind("kind");
  const prev = new Set([...host.querySelectorAll('input.label-txn-check[type="checkbox"]:checked')].map((cb) => cb.value));
  host.innerHTML = '<span class="muted small">Метки…</span>';
  /** @type {{flat: {id:number,label:string,path?:string}[]}} */
  let data;
  try {
    data = await fetchLabels(kind);
  } catch (e) {
    host.innerHTML = `<span class="muted">${escapeHtml(String(e.message || e))}</span>`;
    return;
  }
  const rows = data.flat || [];
  host.innerHTML = "";
  if (!rows.length) {
    host.innerHTML = `<span class="muted small">Нет меток для «${kind === "income" ? "доход" : "расход"}» — вкладка «Метки».</span>`;
    return;
  }
  for (const l of rows) {
    const lab = document.createElement("label");
    lab.className = "label-check";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "label-txn-check";
    cb.value = String(l.id);
    cb.checked = prev.has(String(l.id));
    cb.addEventListener("change", () => {
      labelSelectionSource = "manual";
      updateLabelRulesHint("");
    });
    lab.appendChild(cb);
    const text = l.path || l.label || String(l.name || l.id);
    lab.appendChild(document.createTextNode(text));
    lab.title = l.path || text;
    host.appendChild(lab);
  }
}

async function refreshCommentLabelRulesCache() {
  const kind = getSelectedKind("kind");
  const data = await api(`/api/comment-label-rules?kind=${encodeURIComponent(kind)}`);
  commentLabelRulesCache = Array.isArray(data) ? data : [];
}

/**
 * Все подходящие правила добавляют метки (объединение). При смене текста сбрасываем только те метки,
 * что были поставлены правилами, если пользователь не правил метки вручную.
 */
function tryApplyCommentLabelRules(noteText, force = false) {
  if (!force && labelSelectionSource === "manual") return;
  const text = String(noteText ?? "");
  const matched = [];
  for (const rule of commentLabelRulesCache || []) {
    if (matchesCommentRule(rule.pattern, text)) matched.push(rule);
  }
  const want = new Set(matched.map((r) => String(r.label_id)));
  const ruleTargetIds = new Set((commentLabelRulesCache || []).map((r) => String(r.label_id)));

  const host = $("#txn-labels");
  if (!host || !host.querySelector("input.label-txn-check")) return;

  document.querySelectorAll('#txn-labels input.label-txn-check[type="checkbox"]').forEach((cb) => {
    if (!ruleTargetIds.has(cb.value)) return;
    cb.checked = want.has(cb.value);
  });

  if (!matched.length) {
    updateLabelRulesHint("");
    if (labelSelectionSource === "rule") labelSelectionSource = "none";
    return;
  }
  labelSelectionSource = "rule";
  const parts = matched.map((r) => hintForMatchedRule(r));
  updateLabelRulesHint(`Метки по правилам: ${parts.join("; ")}`);
  $("#form-tx")?.dispatchEvent(new Event("input", { bubbles: true }));
}

function modalRuleKind() {
  return getSelectedKind("modal-rule-kind");
}

async function refreshMainFormRulesCacheIfKindsMatch(modalKind) {
  if (modalKind !== getSelectedKind("kind")) return;
  try {
    await refreshCommentRulesCache();
    await refreshCommentLabelRulesCache();
    tryApplyCommentRules(txnNoteValue(), false);
    tryApplyCommentLabelRules(txnNoteValue(), false);
  } catch (e) {
    toast(String(e.message || e));
  }
}

function renderRulesRowsIntoHost(host, rows) {
  host.innerHTML = "";
  if (!rows.length) {
    host.innerHTML =
      '<p class="muted small">Пока нет правил. Укажите <strong>слово или фразу</strong> из комментария и категорию — при сохранении операции подстановка сработает сама.</p>';
    return;
  }
  for (const rule of rows) {
    const div = document.createElement("div");
    div.className = "rule-row rule-row-compact";
    div.innerHTML = `
      <div class="rule-row-compact-text">
        <code class="rule-pattern-line">${escapeHtml(rule.pattern)}</code>
        <span class="muted small rule-cat-line">${escapeHtml(rule.category_path || `id ${rule.category_id}`)} · пр. ${rule.sort_order}</span>
      </div>
      <div class="rule-row-actions">
        <button type="button" class="small ghost del-rule" data-id="${rule.id}">Удалить</button>
      </div>
    `;
    host.appendChild(div);
  }
}

async function reloadRulesInto(host, kind) {
  if (!host) return;
  host.innerHTML = '<p class="muted small">Загрузка…</p>';
  let rows;
  try {
    rows = await api(`/api/comment-rules?kind=${encodeURIComponent(kind)}`);
  } catch (e) {
    host.innerHTML = `<p class="muted">${escapeHtml(String(e.message || e))}</p>`;
    return;
  }
  renderRulesRowsIntoHost(host, rows);
}

async function reloadRulesModalList() {
  await reloadRulesInto($("#rules-list-modal"), modalRuleKind());
}

async function reloadRulesInlineList() {
  await reloadRulesInto($("#rules-list-inline"), getSelectedKind("cat-admin-kind"));
}

async function reloadLabelsInlineList() {
  const host = $("#labels-list-inline");
  if (!host) return;
  const kind = getSelectedKind("label-admin-kind");
  host.innerHTML = '<p class="muted small">Загрузка…</p>';
  let data;
  try {
    data = await fetchLabels(kind);
  } catch (e) {
    host.innerHTML = `<p class="muted">${escapeHtml(String(e.message || e))}</p>`;
    return;
  }
  const rows = data.flat || [];
  host.innerHTML = "";
  if (!rows.length) {
    host.innerHTML = '<p class="muted small">Меток пока нет — добавьте формой выше.</p>';
    return;
  }
  for (const l of rows) {
    const div = document.createElement("div");
    div.className = "rule-row rule-row-compact";
    const disp = escapeHtml(l.path || l.label || String(l.name || l.id));
    div.innerHTML = `
      <div class="rule-row-compact-text">
        <strong>${disp}</strong>
        <span class="muted small rule-cat-line">id ${l.id}</span>
      </div>
      <div class="rule-row-actions">
        <button type="button" class="small ghost del-label" data-id="${l.id}">Удалить</button>
      </div>`;
    host.appendChild(div);
  }
}

function renderLabelRulesRowsIntoHost(host, rows) {
  host.innerHTML = "";
  if (!rows.length) {
    host.innerHTML = '<p class="muted small">Пока нет правил автометок.</p>';
    return;
  }
  for (const rule of rows) {
    const div = document.createElement("div");
    div.className = "rule-row rule-row-compact";
    div.innerHTML = `
      <div class="rule-row-compact-text">
        <code class="rule-pattern-line">${escapeHtml(rule.pattern)}</code>
        <span class="muted small rule-cat-line">${escapeHtml(rule.label_path || rule.label_name || `id ${rule.label_id}`)} · пр. ${rule.sort_order}</span>
      </div>
      <div class="rule-row-actions">
        <button type="button" class="small ghost del-label-rule" data-id="${rule.id}">Удалить</button>
      </div>
    `;
    host.appendChild(div);
  }
}

async function reloadLabelRulesInto(host, kind) {
  if (!host) return;
  host.innerHTML = '<p class="muted small">Загрузка…</p>';
  let rows;
  try {
    rows = await api(`/api/comment-label-rules?kind=${encodeURIComponent(kind)}`);
  } catch (e) {
    host.innerHTML = `<p class="muted">${escapeHtml(String(e.message || e))}</p>`;
    return;
  }
  renderLabelRulesRowsIntoHost(host, rows);
}

async function reloadLabelRulesInlineList() {
  await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
}

async function fillInlineRuleLabels() {
  const sel = $("#label-rule-inline-label");
  if (!sel) return;
  const prev = sel.value;
  const kind = getSelectedKind("label-admin-kind");
  let data;
  try {
    data = await fetchLabels(kind);
  } catch (e) {
    toast(String(e.message || e));
    return;
  }
  sel.innerHTML = '<option value="">Метка…</option>';
  for (const o of data.flat || []) {
    const opt = document.createElement("option");
    opt.value = String(o.id);
    opt.textContent = o.path || o.label || String(o.name || o.id);
    opt.title = o.path || o.label || "";
    sel.appendChild(opt);
  }
  if (prev && [...sel.options].some((opt) => opt.value === prev)) sel.value = prev;
}

async function refreshAllRulesListUIs() {
  await Promise.all([
    reloadRulesModalList(),
    reloadRulesInlineList(),
    reloadLabelsInlineList(),
    reloadLabelRulesInlineList(),
  ]);
}

async function fillRuleCategorySelect(selectEl, kind) {
  if (!selectEl) return;
  const prev = selectEl.value;
  const data = await fetchCategories(kind);
  fillCategorySelectRequireChoice(selectEl, data.flat || [], "", prev);
}

async function fillRuleModalCategories() {
  await fillRuleCategorySelect($("#rule-new-category"), modalRuleKind());
}

async function fillInlineRuleCategories() {
  await fillRuleCategorySelect($("#rule-inline-category"), getSelectedKind("cat-admin-kind"));
}

function txnCategoryLabel(r) {
  return r.category_path || r.legacy_category || "—";
}

function txnLabelsLabel(r) {
  const xs = (r.labels || []).map((l) => l.path || l.name).filter(Boolean);
  xs.sort((a, b) => a.localeCompare(b, "ru"));
  return xs.length ? xs.join(", ") : "—";
}

function normName(s) {
  return String(s || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function getSelectedKind(radioName) {
  const el = document.querySelector(`input[name="${radioName}"]:checked`);
  return el ? el.value : "expense";
}

function parseAmount(formData, label) {
  const rawAm = formData.get("amount");
  if (rawAm === "" || rawAm === null || rawAm === undefined) throw new Error("Укажите сумму");
  const amount = Number(String(rawAm).replace(",", "."));
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Сумма должна быть числом больше нуля");
  return amount;
}

function fillSelectFromFlat(selectEl, flat, selectedId) {
  if (!selectEl) return;
  selectEl.innerHTML = '<option value="">— без категории —</option>';
  for (const o of flat || []) {
    const opt = document.createElement("option");
    opt.value = String(o.id);
    opt.textContent = o.label;
    opt.title = o.path || o.label;
    selectEl.appendChild(opt);
  }
  if (selectedId != null && selectedId !== "") {
    selectEl.value = String(selectedId);
  }
}

/** Категория для правил (обязательный выбор). optionalFilterQuery — поиск по подстроке label/path */
function fillCategorySelectRequireChoice(selectEl, flat, optionalFilterQuery, preservedValue) {
  if (!selectEl) return;
  const full = flat || [];
  let rows = filterCategoryFlat(full, optionalFilterQuery || "");
  const want =
    preservedValue !== undefined && preservedValue !== null ? String(preservedValue) : String(selectEl.value || "");
  if (want && !rows.some((o) => String(o.id) === want)) {
    const keep = full.find((o) => String(o.id) === want);
    if (keep) rows = [keep, ...rows];
  }
  selectEl.innerHTML = '<option value="">— выберите категорию —</option>';
  for (const o of rows) {
    const opt = document.createElement("option");
    opt.value = String(o.id);
    opt.textContent = o.label;
    opt.title = o.path || o.label;
    selectEl.appendChild(opt);
  }
  if (want && [...selectEl.options].some((o) => o.value === want)) {
    selectEl.value = want;
  }
}

/** Родитель в корень / подкатегорию — то же дерево без «без категории». */
function fillParentSelect(selectEl, flat, selectedId) {
  if (!selectEl) return;
  selectEl.innerHTML = '<option value="">— корень верхнего уровня —</option>';
  for (const o of flat || []) {
    const opt = document.createElement("option");
    opt.value = String(o.id);
    opt.textContent = o.label;
    opt.title = o.path || o.label;
    selectEl.appendChild(opt);
  }
  if (selectedId != null && selectedId !== "" && [...selectEl.options].some((o) => o.value === String(selectedId))) {
    selectEl.value = String(selectedId);
  }
}

let lastTxnFlat = [];
let lastTplFlat = [];

function filterCategoryFlat(flat, q) {
  const n = normName(q);
  if (!n) return flat || [];
  return (flat || []).filter((o) => normName(o.label).includes(n) || normName(o.path || "").includes(n));
}

/** Список категорий + опция «нет» для операции и шаблона */
function fillSelectOptionalCategory(selectEl, flat, filterQuery, preservedValue) {
  if (!selectEl) return;
  const full = flat || [];
  let rows = filterCategoryFlat(full, filterQuery);
  const want = preservedValue !== undefined ? String(preservedValue) : String(selectEl.value || "");
  if (want && !rows.some((o) => String(o.id) === want)) {
    const keep = full.find((o) => String(o.id) === want);
    if (keep) rows = [keep, ...rows];
  }
  selectEl.innerHTML = '<option value="">— без категории —</option>';
  for (const o of rows) {
    const opt = document.createElement("option");
    opt.value = String(o.id);
    opt.textContent = o.label;
    opt.title = o.path || o.label;
    selectEl.appendChild(opt);
  }
  if (want && [...selectEl.options].some((o) => o.value === want)) {
    selectEl.value = want;
  }
}


async function fetchCategories(kind) {
  return api(`/api/categories?kind=${encodeURIComponent(kind)}`);
}

async function fetchLabels(kind) {
  const data = await api(`/api/labels?kind=${encodeURIComponent(kind)}`);
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return {
      tree: Array.isArray(data.tree) ? data.tree : [],
      flat: Array.isArray(data.flat) ? data.flat : [],
    };
  }
  return { tree: [], flat: [] };
}

/** Поле категории: ввод фильтрует список, по клику — выбор id (Apple-style combo). */
function attachCategoryCombo(prefix, getFlat, hooks = {}, emptyOptionLabel = "— без категории —") {
  const hidden = document.getElementById(`${prefix}-category-id`);
  const qEl = document.getElementById(`${prefix}-category-q`);
  const panel = document.getElementById(`${prefix}-category-panel`);
  const wrap = document.getElementById(`${prefix}-category-combo`);
  const arrow = wrap?.querySelector(".cat-combo-arrow");
  if (!hidden || !qEl || !panel || !wrap) return null;

  function rows() {
    return getFlat() || [];
  }

  function displayOf(o) {
    if (!o) return "";
    const path = String(o.path || "").trim();
    return path || o.label || "";
  }

  function labOf(cid) {
    if (cid === "" || cid == null || cid === undefined) return "";
    const r = rows().find((o) => String(o.id) === String(cid));
    return displayOf(r);
  }

  function close() {
    panel.hidden = true;
    wrap.classList.remove("cat-combo-open");
    qEl.setAttribute("aria-expanded", "false");
    arrow?.setAttribute("aria-expanded", "false");
  }

  function renderPanel() {
    const filterTxt = qEl.value || "";
    const t = normName(filterTxt);
    const full = rows();
    const filtRows = t ? filterCategoryFlat(full, filterTxt) : full.slice();
    panel.innerHTML = "";
    const addLi = (id, label, hint) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.dataset.id = String(id);
      li.textContent = label;
      li.className = "cat-combo-option";
      if (hint && hint !== label) li.title = hint;
      if (String(id) === String(hidden.value || "")) li.classList.add("is-picked");
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        hidden.value = id === "" ? "" : String(id);
        qEl.value = id === "" ? "" : label;
        hooks.onUserChange?.();
        close();
      });
      panel.appendChild(li);
    };
    addLi("", emptyOptionLabel, "");
    for (const o of filtRows) addLi(o.id, displayOf(o), o.path || o.label);
    if (!filtRows.length && t) {
      const li = document.createElement("li");
      li.className = "cat-combo-option cat-combo-msg muted small";
      li.textContent = "Нет совпадений — уточните запрос";
      panel.appendChild(li);
    }
  }

  function open() {
    renderPanel();
    panel.hidden = false;
    wrap.classList.add("cat-combo-open");
    qEl.setAttribute("aria-expanded", "true");
    arrow?.setAttribute("aria-expanded", "true");
  }

  function resolveTyping() {
    const raw = (qEl.value || "").trim();
    if (!raw) {
      hidden.value = "";
      hooks.onUserChange?.();
      return;
    }
    const full = rows();
    const exact = full.find((o) => normName(o.label) === normName(raw) || normName(o.path || "") === normName(raw));
    if (exact) {
      hidden.value = String(exact.id);
      qEl.value = displayOf(exact);
      hooks.onUserChange?.();
      return;
    }
    const fr = filterCategoryFlat(full, raw);
    if (fr.length === 1) {
      hidden.value = String(fr[0].id);
      qEl.value = displayOf(fr[0]);
      hooks.onUserChange?.();
      return;
    }
    qEl.value = labOf(hidden.value);
  }

  function setValue(cid, silent) {
    hidden.value = cid === "" || cid == null ? "" : String(cid);
    qEl.value = labOf(hidden.value);
    close();
    if (!silent) hooks.onUserChange?.();
  }

  function refreshPreserve(prev) {
    const want = prev != null && prev !== undefined ? String(prev) : String(hidden.value || "");
    const full = rows();
    if (!want || !full.some((o) => String(o.id) === want)) {
      hidden.value = "";
      qEl.value = "";
    } else {
      hidden.value = want;
      qEl.value = labOf(want);
    }
    close();
  }

  arrow?.addEventListener("click", (e) => {
    e.preventDefault();
    if (panel.hidden) open();
    else {
      resolveTyping();
      close();
    }
    qEl.focus();
  });

  qEl.addEventListener("focus", () => open());

  qEl.addEventListener("input", () => {
    if (panel.hidden) open();
    else renderPanel();
  });

  qEl.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      qEl.value = labOf(hidden.value);
      close();
      e.preventDefault();
    }
  });

  qEl.addEventListener("blur", () => {
    setTimeout(() => {
      if (!wrap.contains(document.activeElement)) {
        resolveTyping();
        close();
      }
    }, 140);
  });

  document.addEventListener(
    "mousedown",
    (e) => {
      if (!panel.hidden && !wrap.contains(e.target)) {
        resolveTyping();
        close();
      }
    },
    true
  );

  return { setValue, refreshPreserve };
}

const txnCategoryCombo = attachCategoryCombo("txn", () => lastTxnFlat, {
  onUserChange() {
    setCategoryManual();
    updateTxnFormChrome();
    $("#form-tx")?.dispatchEvent(new Event("input", { bubbles: true }));
  },
});

const tplCategoryCombo = attachCategoryCombo("tpl", () => lastTplFlat, {});

/** Разделы деревьев для фильтра журнала: { kind, title?, roots }. */
let ledgerFilterSections = [];

/** @type {Set<number>} */
const ledgerFilterSelectedIds = new Set();

function ledgerFilterTreeByQuery(nodes, q) {
  const n = normName(q);
  if (!n) return nodes || [];
  const out = [];
  for (const node of nodes || []) {
    const kids = ledgerFilterTreeByQuery(node.children || [], q);
    const selfMatch = normName(node.name || "").includes(n);
    if (selfMatch || kids.length) out.push({ ...node, children: kids });
  }
  return out;
}

function ledgerCollectIds(nodes, into) {
  for (const node of nodes || []) {
    const id = Number(node.id);
    if (Number.isFinite(id)) into.add(id);
    ledgerCollectIds(node.children || [], into);
  }
}

function pruneLedgerCategorySelectionToLoadedTree() {
  const allowed = new Set();
  for (const sec of ledgerFilterSections) {
    ledgerCollectIds(sec.roots || [], allowed);
  }
  for (const id of [...ledgerFilterSelectedIds]) {
    if (!allowed.has(id)) ledgerFilterSelectedIds.delete(id);
  }
}

function updateLedgerCategorySummary() {
  const el = $("#ledger-cat-summary");
  if (!el) return;
  const n = ledgerFilterSelectedIds.size;
  el.textContent = n === 0 ? "Любая" : `Выбрано: ${n} веток`;
  refreshLedgerCategoryFilterChrome();
}

function refreshLedgerCategoryFilterChrome() {
  const wrap = $("#ledger-cat-filter-wrap");
  const btn = $("#ledger-cat-toggle");
  const clr = $("#ledger-cat-clear-inline");
  const n = ledgerFilterSelectedIds.size;
  const on = n > 0;
  wrap?.classList.toggle("ledger-filter-wrap--active", on);
  btn?.classList.toggle("ledger-filter-trigger--active", on);
  if (clr) clr.hidden = !on;
}

async function reloadLedgerCategoryFilterData() {
  const [expD, incD] = await Promise.all([fetchCategories("expense"), fetchCategories("income")]);
  ledgerFilterSections = [
    { kind: "expense", title: "Расходы", roots: expD.tree || [] },
    { kind: "income", title: "Доходы", roots: incD.tree || [] },
  ];
  pruneLedgerCategorySelectionToLoadedTree();
}

function ledgerSelectAllRoots() {
  ledgerFilterSelectedIds.clear();
  for (const sec of ledgerFilterSections) {
    for (const r of sec.roots || []) {
      const id = Number(r.id);
      if (Number.isFinite(id)) ledgerFilterSelectedIds.add(id);
    }
  }
  updateLedgerCategorySummary();
}

function ledgerSelectNonRootOnly() {
  ledgerFilterSelectedIds.clear();

  function walk(nodes, depth) {
    for (const n of nodes || []) {
      if (depth > 0) {
        const id = Number(n.id);
        if (Number.isFinite(id)) ledgerFilterSelectedIds.add(id);
      }
      walk(n.children || [], depth + 1);
    }
  }

  for (const sec of ledgerFilterSections) {
    walk(sec.roots || [], 0);
  }
  updateLedgerCategorySummary();
}

function ledgerClearCategorySelection() {
  ledgerFilterSelectedIds.clear();
  updateLedgerCategorySummary();
}

function collectSubtreeCategoryIds(node, into) {
  const nid = Number(node.id);
  if (Number.isFinite(nid)) into.add(nid);
  for (const ch of node.children || []) {
    collectSubtreeCategoryIds(ch, into);
  }
}

function ledgerCategorySubtreeCounts(node) {
  const sub = new Set();
  collectSubtreeCategoryIds(node, sub);
  const total = sub.size;
  let sel = 0;
  for (const id of sub) if (ledgerFilterSelectedIds.has(id)) sel++;
  return { total, sel };
}

function renderLedgerCategoryTreePanel() {
  const body = $("#ledger-cat-tree-body");
  const qEl = $("#ledger-cat-tree-q");
  if (!body) return;
  const filterTxt = (qEl?.value || "").trim();
  body.innerHTML = "";

  function buildLedgerFilterCategoryUl(list) {
    const ul = document.createElement("ul");
    ul.className = "cat-tree ledger-filter-cat-ul";
    for (const node of list || []) {
      const nid = Number(node.id);
      if (!Number.isFinite(nid)) continue;
      const li = document.createElement("li");
      li.dataset.catId = String(nid);

      const line = document.createElement("div");
      line.className = "ledger-filter-cat-line";
      const hasKids = !!(node.children && node.children.length);

      let twisty;
      if (hasKids) {
        twisty = document.createElement("button");
        twisty.type = "button";
        twisty.className = "cat-toggle";
        twisty.setAttribute("aria-expanded", "true");
        twisty.setAttribute("aria-label", "Подкатегории");
        twisty.title = "Свернуть или развернуть";
        twisty.textContent = "▾";
      } else {
        twisty = document.createElement("span");
        twisty.className = "cat-toggle-spacer";
        twisty.setAttribute("aria-hidden", "true");
      }

      const cb = document.createElement("input");
      cb.type = "checkbox";
      const { total, sel } = ledgerCategorySubtreeCounts(node);
      cb.checked = total > 0 && sel === total;
      cb.indeterminate = sel > 0 && sel < total;
      cb.addEventListener("change", () => {
        const sub = new Set();
        collectSubtreeCategoryIds(node, sub);
        if (cb.checked) {
          sub.forEach((id) => ledgerFilterSelectedIds.add(id));
        } else {
          sub.forEach((id) => ledgerFilterSelectedIds.delete(id));
        }
        updateLedgerCategorySummary();
        renderLedgerCategoryTreePanel();
      });
      cb.addEventListener("click", (ev) => ev.stopPropagation());

      const nameSpan = document.createElement("span");
      nameSpan.className = "cat-name";
      nameSpan.textContent = node.name || "";

      line.appendChild(twisty);
      line.appendChild(cb);
      line.appendChild(nameSpan);
      li.appendChild(line);

      if (hasKids) {
        const nestedUl = buildLedgerFilterCategoryUl(node.children);
        nestedUl.classList.add("cat-nested");
        li.appendChild(nestedUl);
        twisty.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const expanded = twisty.getAttribute("aria-expanded") === "true";
          if (expanded) {
            nestedUl.hidden = true;
            twisty.setAttribute("aria-expanded", "false");
            twisty.textContent = "▸";
          } else {
            nestedUl.hidden = false;
            twisty.setAttribute("aria-expanded", "true");
            twisty.textContent = "▾";
          }
        });
      }

      ul.appendChild(li);
    }
    return ul;
  }

  for (const sec of ledgerFilterSections) {
    const roots = ledgerFilterTreeByQuery(sec.roots || [], filterTxt);
    const block = document.createElement("div");
    block.className =
      sec.kind === "expense"
        ? "ledger-filter-kind-block ledger-filter-kind-expense"
        : "ledger-filter-kind-block ledger-filter-kind-income";

    const banner = document.createElement("div");
    banner.className = "ledger-filter-kind-banner";
    banner.textContent = sec.kind === "expense" ? "Расходы" : "Доходы";
    block.appendChild(banner);

    if (!roots.length) {
      const empty = document.createElement("div");
      empty.className = "muted small ledger-filter-kind-empty";
      empty.textContent = filterTxt ? "Нет совпадений" : "Нет категорий";
      block.appendChild(empty);
    } else {
      block.appendChild(buildLedgerFilterCategoryUl(roots));
    }

    body.appendChild(block);
  }
}

/** Деревья меток для фильтра журнала (структура как у категорий). */
let ledgerLabelFilterSections = [];

/** @type {Set<number>} */
const ledgerFilterSelectedLabelIds = new Set();

function pruneLedgerLabelSelectionToLoadedTree() {
  const allowed = new Set();
  for (const sec of ledgerLabelFilterSections) {
    ledgerCollectIds(sec.roots || [], allowed);
  }
  for (const id of [...ledgerFilterSelectedLabelIds]) {
    if (!allowed.has(id)) ledgerFilterSelectedLabelIds.delete(id);
  }
}

async function reloadLedgerLabelFilterData() {
  try {
    const [expD, incD] = await Promise.all([fetchLabels("expense"), fetchLabels("income")]);
    ledgerLabelFilterSections = [
      { kind: "expense", title: "Расходы", roots: expD.tree || [] },
      { kind: "income", title: "Доходы", roots: incD.tree || [] },
    ];
  } catch (e) {
    ledgerLabelFilterSections = [];
    pruneLedgerLabelSelectionToLoadedTree();
    throw e;
  }
  pruneLedgerLabelSelectionToLoadedTree();
}

function ledgerClearLabelSelection() {
  ledgerFilterSelectedLabelIds.clear();
  updateLedgerLabelSummary();
}

function updateLedgerLabelSummary() {
  const el = $("#ledger-label-summary");
  if (!el) return;
  const n = ledgerFilterSelectedLabelIds.size;
  el.textContent = n === 0 ? "Любые" : `Выбрано: ${n}`;
  refreshLedgerLabelFilterChrome();
}

function refreshLedgerLabelFilterChrome() {
  const wrap = $("#ledger-label-filter-wrap");
  const btn = $("#ledger-label-toggle");
  const clr = $("#ledger-label-clear-inline");
  const on = ledgerFilterSelectedLabelIds.size > 0;
  wrap?.classList.toggle("ledger-filter-wrap--active", on);
  btn?.classList.toggle("ledger-filter-trigger--active", on);
  if (clr) clr.hidden = !on;
}

function collectSubtreeLabelIds(node, into) {
  const nid = Number(node.id);
  if (Number.isFinite(nid)) into.add(nid);
  for (const ch of node.children || []) {
    collectSubtreeLabelIds(ch, into);
  }
}

function renderLedgerLabelTreePanel() {
  const body = $("#ledger-label-tree-body");
  const qEl = $("#ledger-label-tree-q");
  if (!body) return;
  const filterTxt = (qEl?.value || "").trim();
  body.innerHTML = "";

  if (!ledgerLabelFilterSections.length) {
    const empty = document.createElement("div");
    empty.className = "muted small ledger-cat-empty";
    empty.textContent = "Метки недоступны — обновите страницу.";
    body.appendChild(empty);
    return;
  }

  function walk(nodes, depth, container) {
    for (const node of nodes || []) {
      const nid = Number(node.id);
      if (!Number.isFinite(nid)) continue;
      const row = document.createElement("label");
      row.className = "ledger-cat-row";

      row.style.paddingLeft = `${6 + depth * 10}px`;

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = ledgerFilterSelectedLabelIds.has(nid);
      cb.addEventListener("change", () => {
        const sub = new Set();
        collectSubtreeLabelIds(node, sub);
        if (cb.checked) {
          sub.forEach((id) => ledgerFilterSelectedLabelIds.add(id));
        } else {
          sub.forEach((id) => ledgerFilterSelectedLabelIds.delete(id));
        }
        updateLedgerLabelSummary();
        renderLedgerLabelTreePanel();
        scheduleLoadLedger();
      });

      const span = document.createElement("span");
      span.textContent = node.name || "";

      row.appendChild(cb);
      row.appendChild(span);
      container.appendChild(row);

      walk(node.children || [], depth + 1, container);
    }
  }

  for (const sec of ledgerLabelFilterSections) {
    const roots = ledgerFilterTreeByQuery(sec.roots || [], filterTxt);
    const block = document.createElement("div");
    block.className =
      sec.kind === "expense"
        ? "ledger-filter-kind-block ledger-filter-kind-expense"
        : "ledger-filter-kind-block ledger-filter-kind-income";

    const banner = document.createElement("div");
    banner.className = "ledger-filter-kind-banner";
    banner.textContent = sec.kind === "expense" ? "Расходы" : "Доходы";
    block.appendChild(banner);

    if (!roots.length) {
      const empty = document.createElement("div");
      empty.className = "muted small ledger-filter-kind-empty";
      empty.textContent = filterTxt ? "Нет совпадений" : "Нет меток";
      block.appendChild(empty);
    } else {
      walk(roots, 0, block);
    }

    body.appendChild(block);
  }
}

async function refreshTxnCategorySelect() {
  const hid = $("#txn-category-id");
  if (!hid) return;
  const prev = hid.value || "";
  const kind = getSelectedKind("kind");
  const data = await fetchCategories(kind);
  lastTxnFlat = data.flat || [];
  txnCategoryCombo?.refreshPreserve(prev);
  await refreshTxnLabelsPanel();
}

async function refreshTplCategorySelect() {
  const hid = $("#tpl-category-id");
  if (!hid) return;
  const prev = hid.value || "";
  const kind = getSelectedKind("tpl_kind");
  const data = await fetchCategories(kind);
  lastTplFlat = data.flat || [];
  tplCategoryCombo?.refreshPreserve(prev);
}

async function refreshAdminParentSelect(kindOverride) {
  const kind = kindOverride || getSelectedKind("cat-admin-kind");
  const sel = $("#new-cat-parent");
  if (!sel) return;
  const prev = sel.value;
  const data = await fetchCategories(kind);
  fillParentSelect(sel, data.flat, prev);
}

/**
 * Если выбран список — его id (новые категории из формы операции не создаём — только вкладка «Категории»).
 */
function categoryIdFromTxnFormSelect(cidRaw) {
  if (cidRaw === "" || cidRaw === null || cidRaw === undefined) return null;
  const s = String(cidRaw).trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function hideDropRootHints() {
  const z = $("#category-drop-root");
  if (z) z.hidden = true;
}

function hideLabelDropRootHints() {
  const z = $("#label-drop-root");
  if (z) z.hidden = true;
}

function catNameElFromRenameBtn(btn) {
  const li = btn.closest("li");
  if (!li) return null;
  for (const ch of li.children) {
    if (ch.classList?.contains("cat-line")) {
      const sp = ch.querySelector(".cat-name");
      return sp || null;
    }
  }
  return null;
}

function renderCategoryTree(nodes, container) {
  container.innerHTML = "";
  hideDropRootHints();

  if (!nodes.length) {
    container.innerHTML = '<p class="muted small">Категорий пока нет — добавьте через форму выше.</p>';
    return;
  }

  function buildUl(list) {
    const ul = document.createElement("ul");
    ul.className = "cat-tree";
    for (const n of list) {
      const li = document.createElement("li");
      li.dataset.catId = String(n.id);

      const line = document.createElement("div");
      line.className = "cat-line";
      line.draggable = true;
      line.dataset.catId = String(n.id);
      const hasKids = !!(n.children && n.children.length);
      line.innerHTML = `
        ${
          hasKids
            ? '<button type="button" class="cat-toggle" aria-expanded="false" aria-label="Подкатегории" title="Развернуть или свернуть вложенные">▸</button>'
            : '<span class="cat-toggle-spacer" aria-hidden="true"></span>'
        }
        <span class="drag-handle" draggable="false" title="За ⠿ — тащить на другую категорию">⠿</span>
        <span class="cat-name">${escapeHtml(n.name)}</span>
        <span class="cat-actions">
          <button type="button" class="linkish cat-move" draggable="false" data-id="${n.id}" title="Выбрать родителя или корень в списке">куда вложить…</button>
          <button type="button" class="linkish cat-rename" draggable="false" data-id="${n.id}">переименовать</button>
          <button type="button" class="linkish cat-del" draggable="false" data-id="${n.id}">удалить</button>
        </span>
      `;

      const handle = line.querySelector(".drag-handle");
      handle?.addEventListener(
        "mousedown",
        () => {
          line.setAttribute("data-cat-drag", "1");
        },
        true
      );

      line.addEventListener("dragstart", (ev) => {
        if (!line.hasAttribute("data-cat-drag")) {
          ev.preventDefault();
          return;
        }
        line.removeAttribute("data-cat-drag");
        ev.dataTransfer.setData("text/plain", String(n.id));
        ev.dataTransfer.effectAllowed = "move";
        line.classList.add("drag-active");
        const root = $("#category-drop-root");
        if (root) root.hidden = false;
      });
      line.addEventListener("dragend", () => {
        line.classList.remove("drag-active");
        container.querySelectorAll(".cat-line").forEach((el) => el.classList.remove("drop-target"));
        hideDropRootHints();
      });
      line.addEventListener("dragenter", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
      });

      line.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        ev.dataTransfer.dropEffect = "move";
        line.classList.add("drop-target");
      });
      line.addEventListener("dragleave", (ev) => {
        const rel = ev.relatedTarget;
        if (rel && line.contains(rel)) return;
        line.classList.remove("drop-target");
      });
      line.addEventListener("drop", async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        line.classList.remove("drop-target");
        const fromId = Number(ev.dataTransfer.getData("text/plain"));
        const toId = n.id;
        if (!fromId || fromId === toId) return;
        try {
          await patchCategoryParent(fromId, toId);
          toast("Категория перенесена");
          await refreshCategoryAdmin();
          await refreshTxnCategorySelect();
          await refreshTplCategorySelect();
          await reloadAllTemplateChips();
        } catch (err) {
          toast(String(err.message || err));
        }
      });

      li.appendChild(line);
      if (hasKids) {
        const nestedUl = buildUl(n.children);
        nestedUl.classList.add("cat-nested");
        nestedUl.hidden = true;
        li.appendChild(nestedUl);
        const tbtn = line.querySelector(".cat-toggle");
        tbtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const expanded = tbtn.getAttribute("aria-expanded") === "true";
          if (expanded) {
            nestedUl.hidden = true;
            tbtn.setAttribute("aria-expanded", "false");
            tbtn.textContent = "▸";
          } else {
            nestedUl.hidden = false;
            tbtn.setAttribute("aria-expanded", "true");
            tbtn.textContent = "▾";
          }
        });
      }
      ul.appendChild(li);
    }
    return ul;
  }

  container.appendChild(buildUl(nodes));

  container.querySelectorAll(".cat-move").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const lineEl = btn.closest(".cat-line");
      const nm = lineEl?.querySelector(".cat-name")?.textContent ?? "";
      openMoveCategoryDialog(Number(id), nm);
    })
  );

  container.querySelectorAll(".cat-rename").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const nameEl = catNameElFromRenameBtn(btn);
      const current = nameEl ? nameEl.textContent : "";
      const name = prompt("Новое название", current);
      if (!name || !name.trim()) return;
      try {
        await api(`/api/categories/${id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) });
        toast("Категория обновлена");
        await refreshCategoryAdmin();
        await refreshTxnCategorySelect();
        await refreshTplCategorySelect();
        await reloadAllTemplateChips();
      } catch (e) {
        toast(String(e.message || e));
      }
    })
  );

  container.querySelectorAll(".cat-del").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить категорию и все вложенные? Ссылки в операциях станут без категории.")) return;
      try {
        await api(`/api/categories/${btn.dataset.id}`, { method: "DELETE" });
        toast("Удалено");
        await refreshCategoryAdmin();
        await refreshTxnCategorySelect();
        await refreshTplCategorySelect();
        await reloadAllTemplateChips();
      } catch (e) {
        toast(String(e.message || e));
      }
    })
  );
}

async function refreshCategoryAdmin() {
  const kind = getSelectedKind("cat-admin-kind");
  const root = $("#category-tree");
  const data = await fetchCategories(kind);
  renderCategoryTree(data.tree, root);
  await refreshAdminParentSelect(kind);
}

let _catDragMouseupWired = false;
function ensureCatDragMouseupCleanup() {
  if (_catDragMouseupWired) return;
  _catDragMouseupWired = true;
  document.addEventListener(
    "mouseup",
    () => {
      document.querySelectorAll(".cat-line[data-cat-drag]").forEach((el) => el.removeAttribute("data-cat-drag"));
      document.querySelectorAll(".cat-line[data-label-drag]").forEach((el) => el.removeAttribute("data-label-drag"));
    },
    true
  );
}

/* Корневая зона дропа */
function wireCategoryDropRoot() {
  ensureCatDragMouseupCleanup();
  const z = $("#category-drop-root");
  if (!z) return;
  z.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    z.classList.add("drop-root-active");
  });
  z.addEventListener("dragleave", (ev) => {
    const rel = ev.relatedTarget;
    if (rel && z.contains(rel)) return;
    z.classList.remove("drop-root-active");
  });
  z.addEventListener("drop", async (ev) => {
    ev.preventDefault();
    z.classList.remove("drop-root-active");
    const fromId = Number(ev.dataTransfer.getData("text/plain"));
    if (!fromId) return;
    try {
      await patchCategoryParent(fromId, null);
      toast("Категория вынесена в корень");
      await refreshCategoryAdmin();
      await refreshTxnCategorySelect();
      await refreshTplCategorySelect();
      await reloadAllTemplateChips();
    } catch (err) {
      toast(String(err.message || err));
    }
  });
}

function renderLabelTree(nodes, container) {
  container.innerHTML = "";
  hideLabelDropRootHints();

  if (!nodes.length) {
    container.innerHTML = '<p class="muted small">Меток пока нет — добавьте через форму выше.</p>';
    return;
  }

  function buildUl(list) {
    const ul = document.createElement("ul");
    ul.className = "cat-tree";
    for (const n of list) {
      const li = document.createElement("li");

      const line = document.createElement("div");
      line.className = "cat-line";
      line.draggable = true;
      line.dataset.labId = String(n.id);
      const hasKids = !!(n.children && n.children.length);
      line.innerHTML = `
        ${
          hasKids
            ? '<button type="button" class="cat-toggle" aria-expanded="false" aria-label="Подметки">▸</button>'
            : '<span class="cat-toggle-spacer" aria-hidden="true"></span>'
        }
        <span class="drag-handle" draggable="false" title="За ⠿ тащить">⠿</span>
        <span class="cat-name">${escapeHtml(n.name)}</span>
        <span class="cat-actions">
          <button type="button" class="linkish lab-move" draggable="false" data-id="${n.id}">куда вложить…</button>
          <button type="button" class="linkish lab-rename" draggable="false" data-id="${n.id}">переименовать</button>
          <button type="button" class="linkish lab-del" draggable="false" data-id="${n.id}">удалить</button>
        </span>
      `;

      const handle = line.querySelector(".drag-handle");
      handle?.addEventListener(
        "mousedown",
        () => {
          line.setAttribute("data-label-drag", "1");
        },
        true
      );

      line.addEventListener("dragstart", (ev) => {
        if (!line.hasAttribute("data-label-drag")) {
          ev.preventDefault();
          return;
        }
        line.removeAttribute("data-label-drag");
        ev.dataTransfer.setData("text/plain", String(n.id));
        ev.dataTransfer.effectAllowed = "move";
        line.classList.add("drag-active");
        const rootZ = $("#label-drop-root");
        if (rootZ) rootZ.hidden = false;
      });
      line.addEventListener("dragend", () => {
        line.classList.remove("drag-active");
        container.querySelectorAll(".cat-line").forEach((el) => el.classList.remove("drop-target"));
        hideLabelDropRootHints();
      });
      line.addEventListener("dragenter", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
      });
      line.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        ev.dataTransfer.dropEffect = "move";
        line.classList.add("drop-target");
      });
      line.addEventListener("dragleave", (ev) => {
        const rel = ev.relatedTarget;
        if (rel && line.contains(rel)) return;
        line.classList.remove("drop-target");
      });
      line.addEventListener("drop", async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        line.classList.remove("drop-target");
        const fromId = Number(ev.dataTransfer.getData("text/plain"));
        const toId = n.id;
        if (!fromId || fromId === toId) return;
        try {
          await patchLabelParent(fromId, toId);
          toast("Метка перенесена");
          await refreshLabelAdmin();
          await reloadLabelsInlineList();
          await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
          await refreshTxnLabelsPanel();
          await fillInlineRuleLabels();
        } catch (err) {
          toast(String(err.message || err));
        }
      });

      li.appendChild(line);
      if (hasKids) {
        const nestedUl = buildUl(n.children);
        nestedUl.classList.add("cat-nested");
        nestedUl.hidden = true;
        li.appendChild(nestedUl);
        const tbtn = line.querySelector(".cat-toggle");
        tbtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const expanded = tbtn.getAttribute("aria-expanded") === "true";
          if (expanded) {
            nestedUl.hidden = true;
            tbtn.setAttribute("aria-expanded", "false");
            tbtn.textContent = "▸";
          } else {
            nestedUl.hidden = false;
            tbtn.setAttribute("aria-expanded", "true");
            tbtn.textContent = "▾";
          }
        });
      }
      ul.appendChild(li);
    }
    return ul;
  }

  container.appendChild(buildUl(nodes));

  container.querySelectorAll(".lab-move").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const lineEl = btn.closest(".cat-line");
      const nm = lineEl?.querySelector(".cat-name")?.textContent ?? "";
      openMoveLabelDialog(Number(id), nm);
    })
  );

  container.querySelectorAll(".lab-rename").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const nameEl = catNameElFromRenameBtn(btn);
      const current = nameEl ? nameEl.textContent : "";
      const name = prompt("Новое название метки", current);
      if (!name || !name.trim()) return;
      try {
        await api(`/api/labels/${id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) });
        toast("Метка обновлена");
        await refreshLabelAdmin();
        await reloadLabelsInlineList();
        await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
        await refreshTxnLabelsPanel();
      } catch (e) {
        toast(String(e.message || e));
      }
    })
  );

  container.querySelectorAll(".lab-del").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить метку и все вложенные? Правила и операции могут их потерять.")) return;
      try {
        await api(`/api/labels/${btn.dataset.id}`, { method: "DELETE" });
        toast("Удалено");
        await refreshLabelAdmin();
        await reloadLabelsInlineList();
        await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
        await refreshTxnLabelsPanel();
        await fillInlineRuleLabels();
      } catch (e) {
        toast(String(e.message || e));
      }
    })
  );
}

async function refreshAdminLabelParentSelect(kindOverride) {
  const kind = kindOverride || getSelectedKind("label-admin-kind");
  const sel = $("#new-label-parent");
  if (!sel) return;
  const prev = sel.value;
  const data = await fetchLabels(kind);
  fillParentSelect(sel, data.flat, prev);
}

async function refreshLabelAdmin() {
  const kind = getSelectedKind("label-admin-kind");
  const root = $("#label-tree");
  if (!root) return;
  try {
    const data = await fetchLabels(kind);
    renderLabelTree(data.tree || [], root);
    await refreshAdminLabelParentSelect(kind);
  } catch (e) {
    const msg = String(e.message || e);
    root.innerHTML = `
      <p class="muted"><strong>${escapeHtml(msg)}</strong></p>
      <p class="muted small">Клиент при загрузке страницы сам ищет работающий <code>GET /api/health</code> (с префиксом и без). Если всё равно ошибка — проверьте в «Сеть» (F12), куда ушёл запрос к <code>/api/labels</code> (часто это 404 из-за прокси). При нестандартном пути можно задать явно
      <code>&lt;meta name="budjet-mount" content="/префикс" /&gt;</code> в <code>index.html</code> и перезагрузить с очисткой кэша (Ctrl+F5).</p>`;
    toast(msg);
    /* Цепочка на вкладке «Метки» продолжается — плоский список ниже попробует загрузиться сам. */
  }
}

function wireLabelDropRoot() {
  ensureCatDragMouseupCleanup();
  const z = $("#label-drop-root");
  if (!z) return;
  z.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    z.classList.add("drop-root-active");
  });
  z.addEventListener("dragleave", (ev) => {
    const rel = ev.relatedTarget;
    if (rel && z.contains(rel)) return;
    z.classList.remove("drop-root-active");
  });
  z.addEventListener("drop", async (ev) => {
    ev.preventDefault();
    z.classList.remove("drop-root-active");
    const fromId = Number(ev.dataTransfer.getData("text/plain"));
    if (!fromId) return;
    try {
      await patchLabelParent(fromId, null);
      toast("Метка вынесена в корень");
      await refreshLabelAdmin();
      await reloadLabelsInlineList();
      await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
      await refreshTxnLabelsPanel();
    } catch (err) {
      toast(String(err.message || err));
    }
  });
}

/* Tabs */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#pane-${btn.dataset.tab}`)?.classList.add("active");

    const tab = btn.dataset.tab;
    document.body.classList.toggle("is-home-tab", tab === "home");
    document.body.classList.toggle(
      "hide-balance-strip",
      tab === "home" || tab === "cats" || tab === "lbl" || tab === "tmpl"
    );
    if (tab === "home") {
      reloadTxnTemplateChips().catch(() => {});
      loadTodayHome().catch(() => {});
      $("#quick-bulk-lines")?.focus();
    }
    if (tab === "cats") {
      refreshCategoryAdmin()
        .then(() => fillInlineRuleCategories())
        .then(() => reloadRulesInlineList())
        .catch((e) => toast(String(e.message || e)));
    }
    if (tab === "lbl") {
      (async () => {
        await refreshLabelAdmin();
        try {
          await fillInlineRuleLabels();
        } catch (e) {
          toast(String(e.message || e));
        }
        try {
          await reloadLabelsInlineList();
        } catch (e) {
          toast(String(e.message || e));
        }
        try {
          await reloadLabelRulesInlineList();
        } catch (e) {
          toast(String(e.message || e));
        }
      })();
    }
    if (tab === "tmpl") {
      refreshTplCategorySelect().catch((e) => toast(String(e.message || e)));
      loadTemplates().catch((e) => toast(String(e.message || e)));
    }
    if (tab === "tx") {
      reloadAllTemplateChips().catch(() => {});
    }
  });
});

/* Transaction form */
const form = $("#form-tx");

function setTxnSubmitMode(editing) {
  const title = $("#form-tx .card-title");
  const btn = $("#submit-tx");
  if (title) title.textContent = editing ? "Изменить операцию" : "Операция";
  if (btn) btn.textContent = editing ? "Изменить операцию" : "Добавить операцию";
}

function resetForm() {
  form.reset();
  form.querySelector('[name="id"]').value = "";
  setTxnSubmitMode(false);
  const occ = form.querySelector('[name="occurred_on"]');
  if (occ) occ.value = todayISO();
  categorySelectionSource = "none";
  updateCategoryHint("");
  labelSelectionSource = "none";
  updateLabelRulesHint("");
  txnCategoryCombo?.setValue("", true);
  refreshTxnCategorySelect()
    .then(() => refreshCommentRulesCache())
    .then(() => tryApplyCommentRules(txnNoteValue(), false))
    .then(() => refreshCommentLabelRulesCache())
    .then(() => tryApplyCommentLabelRules(txnNoteValue(), false))
    .then(() => updateTxnFormChrome())
    .catch((e) => toast(String(e.message || e)));
}

$("#reset-tx")?.addEventListener("click", () => resetForm());

$$('input[name="kind"]').forEach((r) =>
  r.addEventListener("change", () => {
    categorySelectionSource = "none";
    labelSelectionSource = "none";
    updateCategoryHint("");
    txnCategoryCombo?.setValue("", true);
    refreshTxnCategorySelect()
      .then(() => refreshCommentRulesCache())
      .then(() => refreshCommentLabelRulesCache())
      .then(() => {
        tryApplyCommentRules(txnNoteValue(), false);
        tryApplyCommentLabelRules(txnNoteValue(), false);
      })
      .then(() => reloadAllTemplateChips())
      .then(() => updateTxnFormChrome())
      .catch((e) => toast(String(e.message || e)));
  })
);

async function applyTemplate(templateId, occurredOn) {
  const payload = occurredOn ? { occurred_on: occurredOn } : {};
  await api(`/api/transactions/from-template/${templateId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  toast("Операция добавлена по шаблону");
  await loadLedger();
}

function showHomeTxnForm() {
  const tabBtn = document.querySelector('.tab[data-tab="home"]');
  if (tabBtn && !tabBtn.classList.contains("active")) {
    tabBtn.click();
  }
}

async function reloadTxnTemplateChips() {
  const host = $("#txn-template-chips");
  if (!host) return;
  const kind = getSelectedKind("kind");
  host.innerHTML = '<span class="muted small">Шаблоны…</span>';
  let tpls;
  try {
    tpls = await api(`/api/templates?kind=${encodeURIComponent(kind)}`);
  } catch (e) {
    host.innerHTML = `<span class="muted">${escapeHtml(String(e.message || e))}</span>`;
    return;
  }
  host.innerHTML = "";
  if (!tpls.length) {
    host.innerHTML = `<span class="muted small">Нет шаблонов для «${kind === "income" ? "доход" : "расход"}» — вкладка «Шаблоны».</span>`;
    return;
  }
  for (const t of tpls.slice(0, 40)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip tpl-chip";
    b.textContent = t.title.length > 24 ? `${t.title.slice(0, 23)}…` : t.title;
    b.title = `${t.title} · ${fmtMoney(t.amount)}\n${t.category_path || ""}`;
    b.addEventListener("click", () => {
      fillTxnFormFromTpl(t);
      host.querySelectorAll(".tpl-chip").forEach((el) => el.classList.toggle("is-selected", el === b));
    });
    host.appendChild(b);
  }
}

async function reloadAllTemplateChips() {
  await reloadTxnTemplateChips();
}

function fillTxnForm(row) {
  const radio = document.querySelector(`#form-tx [name="kind"][value="${row.kind}"]`);
  if (radio) radio.checked = true;
  refreshTxnCategorySelect()
    .then(() => refreshCommentRulesCache())
    .then(() => {
      txnCategoryCombo?.setValue(row.category_id ? String(row.category_id) : "", true);
      form.querySelector('[name="amount"]').value = row.amount;
      form.querySelector('[name="note"]').value = row.note || "";
      form.querySelector('[name="occurred_on"]').value = row.occurred_on;
      setTxnFormLabelChecks((row.labels || []).map((x) => x.id));
      categorySelectionSource = "manual";
      labelSelectionSource = "manual";
      updateCategoryHint("");
      updateLabelRulesHint("");
      $("#form-tx")?.dispatchEvent(new Event("input", { bubbles: true }));
    })
    .catch((e) => toast(String(e.message || e)));
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(form);
  let amount;
  try {
    amount = parseAmount(fd, "операции");
  } catch (err) {
    toast(String(err.message || err));
    return;
  }

  const id = fd.get("id");
  const cidRaw = fd.get("category_id");

  try {
    const kind = getSelectedKind("kind");
    const category_id = categoryIdFromTxnFormSelect(cidRaw);

    const odRaw = fd.get("occurred_on");
    const occurred_on = odRaw && String(odRaw).trim() ? String(odRaw).trim() : todayISO();

    const labelIdsSnapshot = getTxnFormLabelIds();
    // Если source застрял на "none", но есть отмеченные метки — считаем выбор явным (иначе merge=true обрежет галочки).
    const explicitLabelPick =
      labelSelectionSource === "manual" ||
      (labelSelectionSource === "none" && labelIdsSnapshot.length > 0);

    const body = {
      kind,
      amount,
      category_id,
      note: (fd.get("note") || "").toString().trim() || null,
      occurred_on,
      label_ids: labelIdsSnapshot,
      merge_comment_label_rules: !explicitLabelPick,
    };

    if (id && String(id).trim().length > 0) {
      await api(`/api/transactions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      toast("Операция обновлена");
    } else {
      await api("/api/transactions", { method: "POST", body: JSON.stringify(body) });
      toast("Операция добавлена");
    }
    resetForm();
    await loadLedger();
  } catch (err) {
    toast(String(err.message || err));
  }
});

async function runQuickBulkAdd() {
  const host = $("#quick-bulk-lines");
  const raw = (host?.value || "").trim();
  if (!raw) {
    toast("Введите текст в блоке быстрого ввода");
    return;
  }
  const kind = getSelectedKind("quick-kind");
  const segs = splitQuickBulkRaw(raw);
  if (!segs.length) {
    toast("Не удалось разобрать строки");
    return;
  }
  await prefetchRulesCachesForQuickBulk();
  const day = todayISO();
  let ok = 0;
  const failed = [];
  /** @type {Error|null} */
  let firstPostErr = null;
  for (const seg of segs) {
    const parsed = parseQuickBulkSegment(seg);
    if (!parsed) {
      failed.push(seg);
      continue;
    }
    const category_id = matchedCategoryIdFromCommentRules(parsed.note);
    const label_ids = matchedLabelIdsFromCommentRules(parsed.note);
    try {
      await api("/api/transactions", {
        method: "POST",
        body: JSON.stringify({
          kind,
          amount: parsed.amount,
          category_id,
          note: parsed.note,
          occurred_on: day,
          label_ids,
          merge_comment_label_rules: true,
        }),
      });
      ok += 1;
    } catch (err) {
      failed.push(seg);
      if (!firstPostErr) firstPostErr = err instanceof Error ? err : new Error(String(err));
    }
  }
  if (ok) toast(`Добавлено операций: ${ok}${failed.length ? ` · пропущено: ${failed.length}` : ""}`);
  else if (firstPostErr) toast(firstPostErr.message || String(firstPostErr));
  else toast(failed.length ? "Ни одну строку не удалось сохранить — в каждой строке: «число», пробел, комментарий (напр. 250 хлеб)." : "Нечего добавлять.");
  if (ok) {
    host.value = "";
    await loadLedger().catch((err) => toast(String(err.message || err)));
  }
}

$("#btn-quick-bulk")?.addEventListener("click", () => {
  runQuickBulkAdd().catch((e) => toast(String(e.message || e)));
});

$("#save-as-template")?.addEventListener("click", async () => {
  const fd = new FormData(form);
  let amount;
  try {
    amount = parseAmount(fd, "шаблона");
  } catch (e) {
    toast(String(e.message || e));
    return;
  }
  const title = prompt("Название шаблона", (fd.get("note") || "").toString() || "");
  if (!title || !title.trim()) return;
  const cidRaw = fd.get("category_id");
  try {
    const kind = getSelectedKind("kind");
    const category_id = categoryIdFromTxnFormSelect(cidRaw);
    await api("/api/templates", {
      method: "POST",
      body: JSON.stringify({
        title: title.trim(),
        kind,
        amount,
        category_id,
        note: (fd.get("note") || "").toString().trim() || null,
      }),
    });
    toast("Шаблон сохранён");
    await loadTemplates();
    await reloadAllTemplateChips();
  } catch (e) {
    toast(String(e.message || e));
  }
});

$("#filter-from") && ($("#filter-from").value = firstOfMonthISO());
$("#filter-to") && ($("#filter-to").value = todayISO());
(() => {
  const f = $("#form-tx");
  const od = f?.querySelector('[name="occurred_on"]');
  if (od) od.value = todayISO();
})();

let _loadLedgerDebounceT;

function scheduleLoadLedger() {
  clearTimeout(_loadLedgerDebounceT);
  _loadLedgerDebounceT = setTimeout(() => {
    loadLedger().catch((err) => toast(String(err.message || err)));
  }, 220);
}

/** Дополнительно отсекаем строки по выбранным меткам (если запрос API их не учёл). */
function filterLedgerRowsBySelectedLabels(rows) {
  if (!ledgerFilterSelectedLabelIds.size) return rows;
  const want = ledgerFilterSelectedLabelIds;
  return rows.filter((r) => {
    for (const l of r.labels || []) {
      const id = Number(l.id);
      if (Number.isFinite(id) && want.has(id)) return true;
    }
    return false;
  });
}

function buildLedgerTransactionQueryParams() {
  const params = new URLSearchParams();
  const from = $("#filter-from")?.value;
  const to = $("#filter-to")?.value;
  const kind = $("#filter-kind")?.value;
  const sortEl = $("#filter-sort");
  if (from) params.set("from_date", from);
  if (to) params.set("to_date", to);
  if (kind) params.set("kind", kind);
  if (sortEl?.value) params.set("sort", sortEl.value);
  for (const id of ledgerFilterSelectedIds) {
    const n = Number(id);
    if (Number.isFinite(n) && n > 0) params.append("category_ids", String(n));
  }
  const labelIdsArr = [...ledgerFilterSelectedLabelIds]
    .map((id) => Number(id))
    .filter((n) => Number.isFinite(n) && n > 0);
  labelIdsArr.sort((a, b) => a - b);
  if (labelIdsArr.length) {
    params.set("txn_lids", labelIdsArr.join(","));
    for (const id of labelIdsArr) {
      params.append("label_ids", String(id));
    }
  }
  const nq = ($("#filter-note-q")?.value || "").trim();
  if (nq) params.set("note_q", nq);
  return params;
}

$("#export-xlsx")?.addEventListener("click", () => {
  const params = buildLedgerTransactionQueryParams();
  const qs = params.toString();
  const url = qs ? `/api/export/transactions.xlsx?${qs}` : "/api/export/transactions.xlsx";
  downloadBlob(url, "transactions.xlsx").catch((e) => toast(String(e.message || e)));
});

let allTimeBalanceCached = 0;
let balanceRevealed = false;

function paintBalanceValue() {
  const balEl = $("#global-balance");
  const tile = $("#balance-tile-net");
  if (!balEl) return;
  balEl.classList.remove("kind-income", "kind-expense", "muted", "is-masked");
  if (!balanceRevealed) {
    balEl.textContent = "••••••";
    balEl.classList.add("is-masked");
    if (tile) {
      tile.setAttribute("aria-pressed", "false");
      tile.title = "Нажмите, чтобы показать баланс";
    }
    return;
  }
  const bal = Number(allTimeBalanceCached) || 0;
  balEl.textContent = fmtMoney(bal);
  if (Math.abs(bal) < 1e-9) balEl.classList.add("muted");
  else if (bal > 0) balEl.classList.add("kind-income");
  else balEl.classList.add("kind-expense");
  if (tile) {
    tile.setAttribute("aria-pressed", "true");
    tile.title = "Нажмите, чтобы скрыть баланс";
  }
}

function toggleBalanceReveal() {
  balanceRevealed = !balanceRevealed;
  paintBalanceValue();
}

async function refreshGlobalTotals() {
  const incEl = $("#global-total-income");
  const expEl = $("#global-total-expense");
  const balEl = $("#global-balance");
  if (!incEl || !expEl || !balEl) return;
  const from = $("#filter-from")?.value;
  const to = $("#filter-to")?.value;
  const periodParams = new URLSearchParams();
  if (from) periodParams.set("from_date", from);
  if (to) periodParams.set("to_date", to);
  const periodQs = periodParams.toString();
  const periodUrl = periodQs ? `/api/stats/totals?${periodQs}` : "/api/stats/totals";
  const [periodRes, allTimeRes] = await Promise.allSettled([
    api(periodUrl),
    api("/api/stats/totals-all-time"),
  ]);
  if (periodRes.status === "fulfilled" && periodRes.value && typeof periodRes.value === "object") {
    incEl.textContent = fmtMoney(Number(periodRes.value.total_income) || 0);
    expEl.textContent = fmtMoney(Number(periodRes.value.total_expense) || 0);
  } else {
    incEl.textContent = "—";
    expEl.textContent = "—";
  }
  if (allTimeRes.status === "fulfilled" && allTimeRes.value && typeof allTimeRes.value === "object") {
    allTimeBalanceCached = Number(allTimeRes.value.balance) || 0;
    paintBalanceValue();
  } else if (balanceRevealed) {
    balEl.textContent = "—";
    balEl.classList.remove("kind-income", "kind-expense", "muted", "is-masked");
  }
}

$("#balance-tile-net")?.addEventListener("click", toggleBalanceReveal);
$("#balance-tile-net")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    toggleBalanceReveal();
  }
});

function categoryFlatFromFetch(data) {
  if (Array.isArray(data)) return data;
  return Array.isArray(data?.flat) ? data.flat : [];
}

function categoryPathOptionsHtml(flat, selectedId) {
  const opts = ['<option value="">— без категории —</option>'];
  for (const o of flat || []) {
    const label = escapeHtml(String(o.path || o.label || "").trim() || String(o.id));
    const sel = String(o.id) === String(selectedId ?? "") ? " selected" : "";
    opts.push(`<option value="${escapeHtml(String(o.id))}"${sel}>${label}</option>`);
  }
  return opts.join("");
}

function fillFormAsCopy(row) {
  if (!form || !row) return;
  form.querySelector('[name="id"]').value = "";
  showHomeTxnForm();
  fillTxnForm(row);
  form.querySelector('[name="occurred_on"]').value = todayISO();
  setTxnSubmitMode(false);
  toast("Заполнено копией — дата на сегодня");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function bindLedgerRowActions(el, rows, source = "ledger") {
  if (!el) return;
  el.querySelectorAll(".edit").forEach((b) =>
    b.addEventListener("click", () => {
      const row = rows.find((x) => String(x.id) === b.dataset.id);
      if (!row) return;
      beginLedgerInlineEdit(b.closest("tr"), row, source).catch((e) => toast(String(e.message || e)));
    })
  );
  el.querySelectorAll(".dup").forEach((b) =>
    b.addEventListener("click", () => {
      const row = rows.find((x) => String(x.id) === b.dataset.id);
      if (!row) return;
      fillFormAsCopy(row);
    })
  );
  el.querySelectorAll(".delete").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Удалить операцию?")) return;
      try {
        await api(`/api/transactions/${encodeURIComponent(b.dataset.id)}`, { method: "DELETE" });
        toast("Удалено");
        await loadLedger();
      } catch (err) {
        toast(String(err.message || err));
      }
    })
  );
}

const HOME_LIST_MODE_KEY = "budjet-home-list-mode";

function getHomeListMode() {
  const checked = document.querySelector('input[name="home-list-mode"]:checked');
  return checked?.value === "recent" ? "recent" : "today";
}

function applyHomeListModeToUi() {
  const mode = getHomeListMode();
  const heading = $("#home-today-heading");
  const hint = $("#home-list-hint");
  if (heading) heading.textContent = mode === "recent" ? "10 последних" : "Сегодня";
  if (hint) {
    hint.textContent =
      mode === "recent" ? "Последние добавленные операции, любая дата" : "Все операции за сегодня";
  }
}

function renderTodayHomeRows(el, rows, mode = "today") {
  if (!el) return;
  if (!rows.length) {
    el.innerHTML =
      mode === "recent" ? `<p class="muted">Операций пока нет.</p>` : `<p class="muted">За сегодня операций нет.</p>`;
    return;
  }
  let inc = 0;
  let exp = 0;
  for (const r of rows) {
    if (r.kind === "income") inc += r.amount;
    else exp += r.amount;
  }
  const totalLabel = mode === "recent" ? "Итого в списке" : "Итого за сегодня";
  el.innerHTML = `
    <p class="small muted">${totalLabel}: доход <span class="kind-income">${fmtMoney(inc)}</span> · расход <span class="kind-expense">${fmtMoney(
      exp
    )}</span> · баланс <strong>${fmtMoney(inc - exp)}</strong></p>
    <table>
      <thead><tr><th>Дата</th><th>Тип</th><th>Сумма</th><th>Категория</th><th>Комментарий</th><th></th></tr></thead>
      <tbody>
        ${rows
          .map(
            (r) => `
          <tr data-row-id="${r.id}">
            <td>${escapeHtml(r.occurred_on || "")}</td>
            <td class="${r.kind === "income" ? "kind-income" : "kind-expense"}">${r.kind === "income" ? "доход" : "расход"}</td>
            <td>${fmtMoney(r.amount)}</td>
            <td>${escapeHtml(txnCategoryLabel(r))}</td>
            <td>${escapeHtml(r.note || "")}</td>
            <td class="nowrap">
              <button type="button" class="linkish edit" data-id="${r.id}">изменить</button>
              <button type="button" class="linkish dup" data-id="${r.id}">копия</button>
              <button type="button" class="linkish delete" data-id="${r.id}">удалить</button>
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
  bindLedgerRowActions(el, rows, "today");
}

let homeListLoadSeq = 0;

async function loadTodayHome() {
  const el = $("#home-today-ledger");
  if (!el) return;
  const seq = ++homeListLoadSeq;
  applyHomeListModeToUi();
  const mode = getHomeListMode();
  const params = new URLSearchParams();
  if (mode === "recent") {
    params.set("sort", "id_desc");
    params.set("limit", "10");
  } else {
    const day = todayISO();
    params.set("from_date", day);
    params.set("to_date", day);
    params.set("sort", "date_desc");
  }
  try {
    const raw = await api(`/api/transactions?${params}`);
    if (seq !== homeListLoadSeq) return;
    let rows = Array.isArray(raw) ? raw : [];
    if (mode === "recent") rows = rows.slice(0, 10);
    renderTodayHomeRows(el, rows, mode);
  } catch (e) {
    if (seq !== homeListLoadSeq) return;
    el.innerHTML = `<p class="muted">${escapeHtml(String(e.message || e))}</p>`;
  }
}

function initHomeListMode() {
  const saved = localStorage.getItem(HOME_LIST_MODE_KEY) === "recent" ? "recent" : "today";
  const input = document.querySelector(`input[name="home-list-mode"][value="${saved}"]`);
  if (input) input.checked = true;
  applyHomeListModeToUi();
  document.querySelectorAll('input[name="home-list-mode"]').forEach((r) => {
    r.addEventListener("change", () => {
      try {
        localStorage.setItem(HOME_LIST_MODE_KEY, getHomeListMode());
      } catch {
        /* ignore */
      }
      loadTodayHome().catch((e) => toast(String(e.message || e)));
    });
  });
}

initHomeListMode();

function ledgerInlineLayout(source) {
  if (source === "today") {
    return {
      host: $("#home-today-ledger"),
      amountIdx: 2,
      catIdx: 3,
      noteIdx: 4,
      actionsIdx: 5,
      minCells: 6,
      reload: () => loadTodayHome(),
    };
  }
  return {
    host: $("#ledger"),
    amountIdx: 2,
    catIdx: 3,
    noteIdx: 5,
    actionsIdx: 6,
    minCells: 7,
    reload: () => loadLedger(),
  };
}

async function beginLedgerInlineEdit(tr, row, source = "ledger") {
  if (!tr || !row) return;
  const layout = ledgerInlineLayout(source);
  const host = layout.host;
  const other = host?.querySelector("tr.is-editing");
  if (other && other !== tr) {
    await layout.reload();
    const again = host?.querySelector(`tr[data-row-id="${row.id}"]`);
    if (again) return beginLedgerInlineEdit(again, row, source);
    return;
  }
  if (tr.classList.contains("is-editing")) return;
  let flat = [];
  try {
    flat = categoryFlatFromFetch(await fetchCategories(row.kind));
  } catch (e) {
    toast(String(e.message || e));
    return;
  }
  const tds = tr.querySelectorAll("td");
  if (tds.length < layout.minCells) return;
  tr.classList.add("is-editing");
  tds[layout.amountIdx].innerHTML = `<input type="number" class="inline-amt" step="0.01" min="0.01" value="${Number(row.amount).toFixed(2)}" aria-label="Сумма">`;
  tds[layout.catIdx].innerHTML = `<select class="inline-cat" aria-label="Категория">${categoryPathOptionsHtml(flat, row.category_id)}</select>`;
  tds[layout.noteIdx].innerHTML = `<input type="text" class="inline-note" maxlength="512" value="${escapeHtml(row.note || "")}" aria-label="Комментарий">`;
  tds[layout.actionsIdx].innerHTML = `
    <button type="button" class="linkish inline-save">сохранить</button>
    <button type="button" class="linkish inline-cancel">отмена</button>`;

  const save = async () => {
    const rawAmt = tds[layout.amountIdx].querySelector(".inline-amt")?.value ?? "";
    const amount = Number(String(rawAmt).replace(",", "."));
    if (!Number.isFinite(amount) || amount <= 0) {
      toast("Сумма должна быть числом больше нуля");
      return;
    }
    const cidRaw = tds[layout.catIdx].querySelector(".inline-cat")?.value ?? "";
    const category_id = cidRaw ? Number(cidRaw) : null;
    const note = (tds[layout.noteIdx].querySelector(".inline-note")?.value || "").trim() || null;
    try {
      await api(`/api/transactions/${encodeURIComponent(row.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ amount, category_id, note }),
      });
      toast("Операция обновлена");
      await loadLedger();
    } catch (err) {
      toast(String(err.message || err));
    }
  };

  tds[layout.actionsIdx].querySelector(".inline-save")?.addEventListener("click", () => {
    save().catch((e) => toast(String(e.message || e)));
  });
  tds[layout.actionsIdx].querySelector(".inline-cancel")?.addEventListener("click", () => {
    layout.reload().catch((e) => toast(String(e.message || e)));
  });
  tr.querySelectorAll(".inline-amt, .inline-note").forEach((inp) => {
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        save().catch((err) => toast(String(err.message || err)));
      }
      if (e.key === "Escape") {
        e.preventDefault();
        layout.reload().catch((err) => toast(String(err.message || err)));
      }
    });
  });
  tds[layout.amountIdx].querySelector(".inline-amt")?.focus();
}

async function loadLedger() {
  const params = buildLedgerTransactionQueryParams();
  const qs = params.toString();
  try {
    const raw = await api(qs ? `/api/transactions?${qs}` : "/api/transactions");
  let rows = Array.isArray(raw) ? raw : [];
  if (raw !== null && raw !== undefined && !Array.isArray(raw)) {
    toast("Журнал: неожиданный ответ сервера — обновите страницу.");
  }
  rows = filterLedgerRowsBySelectedLabels(rows);
  const el = $("#ledger");
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = `<p class="muted">За выбранный период операций нет.</p>`;
    return;
  }
  let inc = 0;
  let exp = 0;
  for (const r of rows) {
    if (r.kind === "income") inc += r.amount;
    else exp += r.amount;
  }
  const bal = inc - exp;
  const head = `<p class="small muted">Итого: доход <span class="kind-income">${fmtMoney(inc)}</span> · расход <span class="kind-expense">${fmtMoney(
    exp
  )}</span> · баланс <strong>${fmtMoney(bal)}</strong></p>`;
  const table = `
    <table>
      <thead><tr><th>Дата</th><th>Тип</th><th>Сумма</th><th>Категория</th><th>Метки</th><th>Комментарий</th><th></th></tr></thead>
      <tbody>
        ${rows
          .map(
            (r) => `
          <tr data-row-id="${r.id}">
            <td>${r.occurred_on}</td>
            <td class="${r.kind === "income" ? "kind-income" : "kind-expense"}">${r.kind === "income" ? "доход" : "расход"}</td>
            <td>${fmtMoney(r.amount)}</td>
            <td>${escapeHtml(txnCategoryLabel(r))}</td>
            <td>${escapeHtml(txnLabelsLabel(r))}</td>
            <td>${escapeHtml(r.note || "")}</td>
            <td class="nowrap">
              <button type="button" class="linkish edit" data-id="${r.id}">изменить</button>
              <button type="button" class="linkish dup" data-id="${r.id}">копия</button>
              <button type="button" class="linkish delete" data-id="${r.id}">удалить</button>
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
  el.innerHTML = head + table;
  bindLedgerRowActions(el, rows, "ledger");
  } finally {
    void refreshGlobalTotals().catch(() => {});
    void loadTodayHome().catch(() => {});
  }
}

document.getElementById("apply-filters")?.addEventListener("click", (e) => {
  e.preventDefault();
  loadLedger().catch((err) => toast(String(err.message || err)));
});

$("#filter-note-q")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    loadLedger().catch((err) => toast(String(err.message || err)));
  }
});

$("#ledger-cat-toggle")?.addEventListener("click", async (e) => {
  e.preventDefault();
  e.stopPropagation();
  const p = $("#ledger-cat-popover");
  if (!p) return;
  if (!p.hidden) {
    p.hidden = true;
    return;
  }
  try {
    await reloadLedgerCategoryFilterData();
    renderLedgerCategoryTreePanel();
    updateLedgerCategorySummary();
    const lp = $("#ledger-label-popover");
    if (lp) lp.hidden = true;
    p.hidden = false;
  } catch (err) {
    toast(String(err.message || err));
  }
});

$("#ledger-cat-clear")?.addEventListener("click", (e) => {
  e.preventDefault();
  ledgerClearCategorySelection();
  renderLedgerCategoryTreePanel();
});

$("#ledger-cat-clear-inline")?.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  ledgerClearCategorySelection();
  renderLedgerCategoryTreePanel();
});

$("#ledger-cat-roots")?.addEventListener("click", (e) => {
  e.preventDefault();
  ledgerSelectAllRoots();
  renderLedgerCategoryTreePanel();
});

$("#ledger-cat-subonly")?.addEventListener("click", (e) => {
  e.preventDefault();
  ledgerSelectNonRootOnly();
  renderLedgerCategoryTreePanel();
});

$("#ledger-cat-tree-q")?.addEventListener("input", () => {
  renderLedgerCategoryTreePanel();
});

$("#ledger-label-toggle")?.addEventListener("click", async (e) => {
  e.preventDefault();
  e.stopPropagation();
  const p = $("#ledger-label-popover");
  if (!p) return;
  const pc = $("#ledger-cat-popover");
  if (pc) pc.hidden = true;
  if (!p.hidden) {
    p.hidden = true;
    return;
  }
  try {
    await reloadLedgerLabelFilterData();
    renderLedgerLabelTreePanel();
    updateLedgerLabelSummary();
    p.hidden = false;
  } catch (err) {
    toast(String(err.message || err));
  }
});

$("#ledger-label-clear")?.addEventListener("click", (e) => {
  e.preventDefault();
  ledgerClearLabelSelection();
  renderLedgerLabelTreePanel();
  scheduleLoadLedger();
});

$("#ledger-label-clear-inline")?.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  ledgerClearLabelSelection();
  renderLedgerLabelTreePanel();
  scheduleLoadLedger();
});

$("#ledger-label-tree-q")?.addEventListener("input", () => {
  renderLedgerLabelTreePanel();
});

document.addEventListener(
  "mousedown",
  (e) => {
    const wl = $("#ledger-label-filter-wrap");
    const pl = $("#ledger-label-popover");
    if (wl && pl && !pl.hidden) {
      const t = /** @type {Node} */ (e.target);
      if (!wl.contains(t)) pl.hidden = true;
    }
    const wrap = $("#ledger-cat-filter-wrap");
    const p = $("#ledger-cat-popover");
    if (!wrap || !p || p.hidden) return;
    const t = /** @type {Node} */ (e.target);
    if (!wrap.contains(t)) p.hidden = true;
  },
  true
);

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const pl = $("#ledger-label-popover");
  if (pl && !pl.hidden) pl.hidden = true;
  const p = $("#ledger-cat-popover");
  if (p && !p.hidden) p.hidden = true;
});

$("#filter-from")?.addEventListener("change", () =>
  loadLedger().catch((err) => toast(String(err.message || err)))
);
$("#filter-to")?.addEventListener("change", () =>
  loadLedger().catch((err) => toast(String(err.message || err)))
);

$("#filter-sort")?.addEventListener("change", () =>
  loadLedger().catch((err) => toast(String(err.message || err)))
);

$("#filter-kind")?.addEventListener("change", () => {
  Promise.all([
    reloadLedgerCategoryFilterData().then(() => {
      updateLedgerCategorySummary();
      renderLedgerCategoryTreePanel();
    }),
    reloadLedgerLabelFilterData().then(() => {
      updateLedgerLabelSummary();
      renderLedgerLabelTreePanel();
    }),
  ])
    .then(() => loadLedger())
    .catch((err) => toast(String(err.message || err)));
});


refreshTxnCategorySelect()
  .then(() => refreshCommentRulesCache())
  .then(() => refreshCommentLabelRulesCache())
  .then(() => {
    tryApplyCommentRules(txnNoteValue(), false);
    tryApplyCommentLabelRules(txnNoteValue(), false);
  })
  .finally(() => {
    reloadLedgerCategoryFilterData()
      .then(() => {
        renderLedgerCategoryTreePanel();
        updateLedgerCategorySummary();
      })
      .catch(() => {});
    reloadLedgerLabelFilterData()
      .then(() => {
        renderLedgerLabelTreePanel();
        updateLedgerLabelSummary();
      })
      .catch(() => {});
    loadLedger().catch((e) => toast(String(e.message || e)));
    reloadAllTemplateChips().catch(() => {});
    updateTxnFormChrome();
  });

let txnNoteDebounced;
$("#form-tx [name=\"note\"]")?.addEventListener("input", () => {
  updateTxnFormChrome();
  clearTimeout(txnNoteDebounced);
  txnNoteDebounced = setTimeout(() => {
    tryApplyCommentRules(txnNoteValue(), false);
    tryApplyCommentLabelRules(txnNoteValue(), false);
  }, 220);
});

$("#form-tx")?.addEventListener("input", () => updateTxnFormChrome());
$("#form-tx")?.addEventListener("change", () => updateTxnFormChrome());

$("#btn-apply-rules-once")?.addEventListener("click", () => {
  tryApplyCommentRules(txnNoteValue(), true);
  tryApplyCommentLabelRules(txnNoteValue(), true);
});

$("#open-rules-modal")?.addEventListener("click", () => {
  const m = $("#modal-rules");
  if (!m) return;
  m.hidden = false;
  const fk = getSelectedKind("kind");
  const sync = document.querySelector(`input[name="modal-rule-kind"][value="${fk}"]`);
  if (sync) sync.checked = true;
  fillRuleModalCategories()
    .then(() => reloadRulesModalList())
    .catch((e) => toast(String(e.message || e)));
});

document.querySelectorAll("[data-close-modal]").forEach((el) =>
  el.addEventListener("click", () => {
    const m = $("#modal-rules");
    if (m) m.hidden = true;
  })
);

$$('input[name="modal-rule-kind"]').forEach((r) =>
  r.addEventListener("change", () => {
    fillRuleModalCategories()
      .then(() => reloadRulesModalList())
      .catch((e) => toast(String(e.message || e)));
  })
);

$("#rules-list-modal")?.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.del-rule");
  if (!btn || !btn.dataset.id) return;
  if (!confirm("Удалить это правило?")) return;
  const mk = modalRuleKind();
  try {
    await api(`/api/comment-rules/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
    toast("Правило удалено");
    await refreshAllRulesListUIs();
    await refreshMainFormRulesCacheIfKindsMatch(mk);
  } catch (e) {
    toast(String(e.message || e));
  }
});

$("#rules-list-inline")?.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.del-rule");
  if (!btn || !btn.dataset.id) return;
  if (!confirm("Удалить это правило?")) return;
  const ik = getSelectedKind("cat-admin-kind");
  try {
    await api(`/api/comment-rules/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
    toast("Правило удалено");
    await refreshAllRulesListUIs();
    await refreshMainFormRulesCacheIfKindsMatch(ik);
  } catch (e) {
    toast(String(e.message || e));
  }
});

function resetRuleForm(variant) {
  const ph = document.getElementById(`${variant}-phrase`);
  const adv = document.getElementById(`${variant}-advanced`);
  const rx = document.getElementById(`${variant}-pattern`);
  const ord = document.getElementById(`${variant}-order`);
  if (ph) ph.value = "";
  if (rx) rx.value = "";
  if (ord) ord.value = "100";
  if (adv) {
    adv.checked = false;
    adv.dispatchEvent(new Event("change"));
  }
}

function wireCategoryRuleAdvancedUI() {
  const pairs = [
    ["rule-inline-advanced", "rule-inline-pattern-wrap", "rule-inline-phrase"],
    ["rule-new-advanced", "rule-new-pattern-wrap", "rule-new-phrase"],
    ["label-rule-inline-advanced", "label-rule-inline-pattern-wrap", "label-rule-inline-phrase"],
  ];
  for (const [aid, wid, pid] of pairs) {
    const cb = document.getElementById(aid);
    const wrap = document.getElementById(wid);
    const phrase = document.getElementById(pid);
    if (!cb || !wrap) continue;
    const sync = () => {
      wrap.hidden = !cb.checked;
      if (phrase) {
        phrase.readOnly = !!cb.checked;
        phrase.classList.toggle("field-dimmed", !!cb.checked);
      }
    };
    cb.addEventListener("change", sync);
    sync();
  }
}

$("#form-new-rule")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const phraseEl = $("#rule-new-phrase");
  const advEl = $("#rule-new-advanced");
  const patternEl = $("#rule-new-pattern");
  const orderEl = $("#rule-new-order");
  const catEl = $("#rule-new-category");
  const pattern = patternFromRuleForm(advEl, phraseEl, patternEl);
  const sort_order = Number((orderEl && orderEl.value) || "100");
  const category_id_raw = catEl ? catEl.value : "";
  const phraseShown = (phraseEl?.value || "").trim();
  const titleEffective = !advEl?.checked && phraseShown ? phraseShown.slice(0, 160) : null;
  const kind = modalRuleKind();
  if (!pattern) {
    toast(advEl?.checked ? "Введите regex" : "Введите текст, который искать в комментарии");
    return;
  }
  if (!category_id_raw) {
    toast("Выберите категорию для правила");
    return;
  }
  try {
    await api("/api/comment-rules", {
      method: "POST",
      body: JSON.stringify({
        kind,
        pattern,
        category_id: Number(category_id_raw),
        sort_order: Number.isFinite(sort_order) ? sort_order : 100,
        title: titleEffective,
      }),
    });
    toast("Правило добавлено");
    resetRuleForm("rule-new");
    await refreshAllRulesListUIs();
    await refreshMainFormRulesCacheIfKindsMatch(kind);
  } catch (err) {
    toast(String(err.message || err));
  }
});

$("#form-new-rule-inline")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const phraseEl = $("#rule-inline-phrase");
  const advEl = $("#rule-inline-advanced");
  const patternEl = $("#rule-inline-pattern");
  const orderEl = $("#rule-inline-order");
  const catEl = $("#rule-inline-category");
  const pattern = patternFromRuleForm(advEl, phraseEl, patternEl);
  const sort_order = Number((orderEl && orderEl.value) || "100");
  const category_id_raw = catEl ? catEl.value : "";
  const phraseShown = (phraseEl?.value || "").trim();
  const titleEffective = !advEl?.checked && phraseShown ? phraseShown.slice(0, 160) : null;
  const kind = getSelectedKind("cat-admin-kind");
  if (!pattern) {
    toast(advEl?.checked ? "Введите regex" : "Введите текст, который искать в комментарии");
    return;
  }
  if (!category_id_raw) {
    toast("Выберите категорию для правила");
    return;
  }
  try {
    await api("/api/comment-rules", {
      method: "POST",
      body: JSON.stringify({
        kind,
        pattern,
        category_id: Number(category_id_raw),
        sort_order: Number.isFinite(sort_order) ? sort_order : 100,
        title: titleEffective,
      }),
    });
    toast("Правило добавлено");
    resetRuleForm("rule-inline");
    await refreshAllRulesListUIs();
    await refreshMainFormRulesCacheIfKindsMatch(kind);
  } catch (err) {
    toast(String(err.message || err));
  }
});

$$('input[name="cat-admin-kind"]').forEach((r) =>
  r.addEventListener("change", () => {
    const np = $("#new-cat-parent");
    if (np) np.value = "";
    refreshCategoryAdmin()
      .then(() => fillInlineRuleCategories())
      .then(() => reloadRulesInlineList())
      .catch((e) => toast(String(e.message || e)));
  })
);

$$('input[name="label-admin-kind"]').forEach((r) =>
  r.addEventListener("change", () => {
    const np = $("#new-label-parent");
    if (np) np.value = "";
    refreshLabelAdmin()
      .then(() => fillInlineRuleLabels())
      .then(() => reloadLabelsInlineList())
      .then(() => reloadLabelRulesInlineList())
      .catch((e) => toast(String(e.message || e)));
  })
);

$("#btn-move-cat-cancel")?.addEventListener("click", () => $("#dlg-move-category")?.close());

$("#btn-move-label-cancel")?.addEventListener("click", () => $("#dlg-move-label")?.close());

$("#form-move-category")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const dlg = $("#dlg-move-category");
  const cid = dlg?.dataset?.catId ? Number(dlg.dataset.catId) : 0;
  const raw = ($("#move-cat-parent") && $("#move-cat-parent").value) || "";
  if (!cid) return;
  const parentId = raw === "" ? null : Number(raw);
  try {
    await patchCategoryParent(cid, parentId);
    toast("Категория перемещена");
    dlg?.close();
    await refreshCategoryAdmin();
    const adminKind = getSelectedKind("cat-admin-kind");
    if (adminKind === getSelectedKind("kind")) await refreshTxnCategorySelect();
    if (adminKind === getSelectedKind("tpl_kind")) await refreshTplCategorySelect();
    await reloadAllTemplateChips();
  } catch (err) {
    toast(String(err.message || err));
  }
});

$("#form-move-label")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const dlg = $("#dlg-move-label");
  const lid = dlg?.dataset?.labelId ? Number(dlg.dataset.labelId) : 0;
  const raw = ($("#move-label-parent") && $("#move-label-parent").value) || "";
  if (!lid) return;
  const parentId = raw === "" ? null : Number(raw);
  try {
    await patchLabelParent(lid, parentId);
    toast("Метка перемещена");
    dlg?.close();
    await refreshLabelAdmin();
    await reloadLabelsInlineList();
    await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
    await fillInlineRuleLabels();
    if (getSelectedKind("label-admin-kind") === getSelectedKind("kind")) await refreshTxnLabelsPanel();
  } catch (err) {
    toast(String(err.message || err));
  }
});

$("#labels-list-inline")?.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.del-label");
  if (!btn || !btn.dataset.id) return;
  if (!confirm("Удалить метку и все вложенные? Правила и операции могут потерять ссылку.")) return;
  try {
    await api(`/api/labels/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
    toast("Удалено");
    await refreshLabelAdmin();
    await reloadLabelsInlineList();
    await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
    await fillInlineRuleLabels();
    await refreshTxnLabelsPanel();
  } catch (e) {
    toast(String(e.message || e));
  }
});

$("#label-rules-list-inline")?.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.del-label-rule");
  if (!btn || !btn.dataset.id) return;
  if (!confirm("Удалить это правило автометок?")) return;
  try {
    await api(`/api/comment-label-rules/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
    toast("Правило удалено");
    await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
    await refreshCommentLabelRulesCache();
    await tryApplyCommentLabelRules(txnNoteValue(), false);
  } catch (e) {
    toast(String(e.message || e));
  }
});

$("#form-new-category")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const adminKind = getSelectedKind("cat-admin-kind");
  const fd = new FormData(e.target);
  const name = fd.get("name");
  const pid = fd.get("parent_id");
  if (!name || !String(name).trim()) {
    toast("Введите название категории");
    return;
  }
  try {
    await api("/api/categories", {
      method: "POST",
      body: JSON.stringify({
        kind: adminKind,
        name: String(name).trim(),
        parent_id: pid && String(pid).length ? Number(pid) : null,
      }),
    });
    toast("Категория создана");
    e.target.reset();
    await refreshCategoryAdmin();
    await fillInlineRuleCategories().catch(() => {});
    if (adminKind === getSelectedKind("kind")) await refreshTxnCategorySelect();
    if (adminKind === getSelectedKind("tpl_kind")) await refreshTplCategorySelect();
    await reloadAllTemplateChips();
    $("#category-tree")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    toast(String(err.message || err));
  }
});

document.getElementById("form-new-label-tree")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formEl = /** @type {HTMLFormElement} */ (e.target);
  const kind = getSelectedKind("label-admin-kind");
  const fd = new FormData(formEl);
  const name = fd.get("name");
  const pidRaw = fd.get("parent_id");
  let parent_id = null;
  if (pidRaw != null && String(pidRaw).trim() !== "") {
    const n = Number(pidRaw);
    if (Number.isFinite(n) && n > 0) parent_id = n;
  }
  if (!name || !String(name).trim()) {
    toast("Введите название метки");
    return;
  }
  const submitBtn = formEl.querySelector('button[type="submit"]');
  const fb = $("#new-label-feedback");

  if (submitBtn) submitBtn.disabled = true;
  if (fb) fb.textContent = "";
  try {
    await api("/api/labels", {
      method: "POST",
      body: JSON.stringify({
        kind,
        name: String(name).trim(),
        parent_id,
      }),
    });
    toast("Метка добавлена");
    if (fb) fb.textContent = "";
    formEl.reset();
    const np = $("#new-label-parent");
    if (np) np.value = "";
    await refreshLabelAdmin();
    await reloadLabelsInlineList();
    await fillInlineRuleLabels();
    await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
    if (kind === getSelectedKind("kind")) await refreshTxnLabelsPanel();
    $("#label-tree")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    const m = String(err.message || err);
    if (fb) fb.textContent = m;
    toast(m);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
});

$("#form-new-label-rule-inline")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const phraseEl = $("#label-rule-inline-phrase");
  const advEl = $("#label-rule-inline-advanced");
  const patternEl = $("#label-rule-inline-pattern");
  const orderEl = $("#label-rule-inline-order");
  const labEl = $("#label-rule-inline-label");
  const pattern = patternFromRuleForm(advEl, phraseEl, patternEl);
  const sort_order = Number((orderEl && orderEl.value) || "100");
  const label_id_raw = labEl ? labEl.value : "";
  const phraseShown = (phraseEl?.value || "").trim();
  const titleEffective = !advEl?.checked && phraseShown ? phraseShown.slice(0, 160) : null;
  const kind = getSelectedKind("label-admin-kind");
  if (!pattern) {
    toast(advEl?.checked ? "Введите regex" : "Введите текст или фразу для поиска в комментарии");
    return;
  }
  if (!label_id_raw) {
    toast("Выберите метку");
    return;
  }
  try {
    await api("/api/comment-label-rules", {
      method: "POST",
      body: JSON.stringify({
        kind,
        pattern,
        label_id: Number(label_id_raw),
        sort_order: Number.isFinite(sort_order) ? sort_order : 100,
        title: titleEffective,
      }),
    });
    toast("Правило добавлено");
    resetRuleForm("label-rule-inline");
    await reloadLabelRulesInto($("#label-rules-list-inline"), getSelectedKind("label-admin-kind"));
    await refreshCommentLabelRulesCache();
    await tryApplyCommentLabelRules(txnNoteValue(), false);
  } catch (err) {
    toast(String(err.message || err));
  }
});

/* Templates */
const tplForm = $("#form-template");

function resetTemplateForm() {
  tplForm.reset();
  tplForm.querySelector('[name="id"]').value = "";
  $("#template-editor-title").textContent = "Новый шаблон";
  tplCategoryCombo?.setValue("", true);
}

$("#reset-template-form")?.addEventListener("click", () => resetTemplateForm());

$$('input[name="tpl_kind"]').forEach((r) =>
  r.addEventListener("change", () => {
    refreshTplCategorySelect().catch((e) => toast(String(e.message || e)));
  })
);

tplForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(tplForm);
  const id = fd.get("id");
  const cid = fd.get("category_id");
  let amount;
  try {
    amount = parseAmount(fd, "шаблона");
  } catch (err) {
    toast(String(err.message || err));
    return;
  }
  const payload = {
    title: String(fd.get("title")).trim(),
    kind: getSelectedKind("tpl_kind"),
    amount,
    category_id: cid && String(cid).length ? Number(cid) : null,
    note: (fd.get("note") || "").toString().trim() || null,
  };
  try {
    if (id && String(id).trim().length > 0) {
      await api(`/api/templates/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      toast("Шаблон обновлён");
    } else {
      await api("/api/templates", { method: "POST", body: JSON.stringify(payload) });
      toast("Шаблон создан");
    }
    resetTemplateForm();
    await loadTemplates();
    await reloadAllTemplateChips();
  } catch (err) {
    toast(String(err.message || err));
  }
});

function fillTxnFormFromTpl(tpl) {
  const radio = document.querySelector(`#form-tx [name="kind"][value="${tpl.kind}"]`);
  if (radio) radio.checked = true;
  refreshTxnCategorySelect()
    .then(() => refreshCommentRulesCache())
    .then(() => refreshCommentLabelRulesCache())
    .then(() => {
      form.querySelector('[name="id"]').value = "";
      txnCategoryCombo?.setValue(tpl.category_id ? String(tpl.category_id) : "", true);
      form.querySelector('[name="amount"]').value = tpl.amount;
      form.querySelector('[name="note"]').value = tpl.note || "";
      form.querySelector('[name="occurred_on"]').value = todayISO();
      setTxnSubmitMode(false);
      categorySelectionSource = "manual";
      labelSelectionSource = "none";
      tryApplyCommentLabelRules(txnNoteValue(), true);
      updateCategoryHint("");
      $("#form-tx")?.dispatchEvent(new Event("input", { bubbles: true }));
    })
    .catch((e) => toast(String(e.message || e)));
}

function fillTemplateEditor(tpl) {
  tplForm.querySelector('[name="id"]').value = tpl.id;
  tplForm.querySelector('[name="title"]').value = tpl.title;
  tplForm.querySelector('[name="amount"]').value = tpl.amount;
  tplForm.querySelector('[name="note"]').value = tpl.note || "";
  document.querySelector(`#form-template [name="tpl_kind"][value="${tpl.kind}"]`).checked = true;
  $("#template-editor-title").textContent = "Редактирование шаблона";
  refreshTplCategorySelect()
    .then(() => {
      tplCategoryCombo?.setValue(tpl.category_id ? String(tpl.category_id) : "", true);
    })
    .catch((e) => toast(String(e.message || e)));
}

async function loadTemplates() {
  const list = $("#template-list");
  const tpls = await api("/api/templates");
  if (!tpls.length) {
    list.innerHTML = '<p class="muted">Шаблонов нет — добавьте справа или кнопкой «В шаблон» из операции.</p>';
    return;
  }
  list.innerHTML = tpls
    .map(
      (t) => `
    <div class="template-card" data-tid="${t.id}">
      <div class="template-card-head">
        <strong>${escapeHtml(t.title)}</strong>
        <span class="muted">${t.kind === "income" ? "доход" : "расход"} · ${fmtMoney(t.amount)}</span>
      </div>
      <div class="muted small">${escapeHtml(t.category_path || "—")}</div>
      <div class="template-card-actions">
        <button type="button" class="small tpl-apply-today">Сегодня</button>
        <button type="button" class="small ghost tpl-apply-date">Дата…</button>
        <button type="button" class="small ghost tpl-to-txn">В операцию</button>
        <button type="button" class="small ghost tpl-edit">Править</button>
        <button type="button" class="small ghost tpl-del">Удалить</button>
      </div>
    </div>`
    )
    .join("");

  list.querySelectorAll(".template-card").forEach((card) => {
    const tid = card.dataset.tid;
    const tpl = tpls.find((x) => String(x.id) === tid);

    card.querySelector(".tpl-apply-today").addEventListener("click", async () => {
      try {
        await applyTemplate(tid, null);
      } catch (e) {
        toast(String(e.message || e));
      }
    });

    card.querySelector(".tpl-apply-date").addEventListener("click", async () => {
      const d = prompt("Дата операции (YYYY-MM-DD)", todayISO());
      if (!d) return;
      try {
        await applyTemplate(tid, d);
      } catch (e) {
        toast(String(e.message || e));
      }
    });

    card.querySelector(".tpl-to-txn").addEventListener("click", () => {
      showHomeTxnForm();
      fillTxnFormFromTpl(tpl);
      toast("Заполнена форма операции");
    });

    card.querySelector(".tpl-edit").addEventListener("click", () => {
      fillTemplateEditor(tpl);
    });

    card.querySelector(".tpl-del").addEventListener("click", async () => {
      if (!confirm("Удалить шаблон?")) return;
      try {
        await api(`/api/templates/${tid}`, { method: "DELETE" });
        toast("Удалён");
        await loadTemplates();
        await reloadAllTemplateChips();
      } catch (e) {
        toast(String(e.message || e));
      }
    });
  });
}

/* Charts */
let chartDaily;
let chartExp;
let chartInc;
let chartMonth;

$("#chart-from").value = firstOfMonthISO();
$("#chart-to").value = todayISO();

function destroyChart(ch) {
  if (ch) ch.destroy();
}

$("#chart-refresh").addEventListener("click", async () => {
  if (typeof Chart === "undefined") {
    toast("Chart.js не загрузился — проверьте сеть/CDN.");
    return;
  }
  const from = $("#chart-from").value;
  const to = $("#chart-to").value;
  if (!from || !to) {
    toast("Укажите даты периода");
    return;
  }
  const qs = `from_date=${encodeURIComponent(from)}&to_date=${encodeURIComponent(to)}`;
  const catLv = (($("#chart-cat-level") && $("#chart-cat-level").value) || "leaf").trim().toLowerCase();
  const level = catLv === "root" ? "root" : "leaf";
  try {
    const [daily, catExp, catInc, monthly] = await Promise.all([
      api(`/api/stats/daily?${qs}`),
      api(`/api/stats/by-category?${qs}&kind=expense&level=${encodeURIComponent(level)}`),
      api(`/api/stats/by-category?${qs}&kind=income&level=${encodeURIComponent(level)}`),
      api(`/api/stats/by-month?${qs}`),
    ]);

    const labels = daily.map((d) => d.day);
    destroyChart(chartDaily);
    chartDaily = new Chart($("#chart-daily"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Доход", data: daily.map((d) => d.income), borderColor: "#3ecf8e", tension: 0.2 },
          { label: "Расход", data: daily.map((d) => d.expense), borderColor: "#ef6b6b", tension: 0.2 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { x: { ticks: { maxTicksLimit: 12 } } },
      },
    });

    destroyChart(chartExp);
    chartExp = new Chart($("#chart-cat-expense"), {
      type: "doughnut",
      data: {
        labels: catExp.map((c) => c.category),
        datasets: [{ data: catExp.map((c) => c.amount), backgroundColor: palette(catExp.length) }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } },
    });

    destroyChart(chartInc);
    chartInc = new Chart($("#chart-cat-income"), {
      type: "doughnut",
      data: {
        labels: catInc.map((c) => c.category),
        datasets: [{ data: catInc.map((c) => c.amount), backgroundColor: palette(catInc.length) }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } },
    });

    destroyChart(chartMonth);
    chartMonth = new Chart($("#chart-monthly"), {
      type: "bar",
      data: {
        labels: monthly.map((m) => m.label),
        datasets: [
          { label: "Доход", data: monthly.map((m) => m.income), backgroundColor: "rgba(62, 207, 142, 0.7)" },
          { label: "Расход", data: monthly.map((m) => m.expense), backgroundColor: "rgba(239, 107, 107, 0.7)" },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: false } } },
    });

    toast("Графики обновлены");
  } catch (err) {
    toast(String(err.message || err));
  }
});

function palette(n) {
  const base = ["#3d9cf0", "#3ecf8e", "#ef6b6b", "#c79bff", "#ffb84d", "#5fd4d4", "#f06bb0", "#9ccc65"];
  const out = [];
  for (let i = 0; i < n; i += 1) out.push(base[i % base.length]);
  return out;
}

wireCategoryRuleAdvancedUI();
wireCategoryDropRoot();
wireLabelDropRoot();
