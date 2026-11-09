"use strict";

// All model-generated strings are inserted via textContent, never as HTML.
const SESSION_KEY = "semantic-hierarchy-session-v1";
const $ = (id) => document.getElementById(id);
const dom = {
  form: $("analysis-form"), words: $("expressions"), count: $("word-count"),
  model: $("model"), reasoning: $("reasoning"), output: $("max-output"),
  modelNote: $("model-note"), definitions: $("definitions"),
  submit: $("submit-button"), stop: $("stop-button"), message: $("form-message"),
  status: $("status"), results: $("results"), countResults: $("result-count"),
  sessionAnalyses: $("session-analyses"), sessionTokens: $("session-tokens"),
  sessionCost: $("session-cost"), export: $("export-button"), clear: $("clear-button"),
};

let catalog = [];
let maxWords = 12;
let history = [];
let running = false;
let stopRequested = false;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function append(parent, ...children) { for (const child of children) parent.appendChild(child); return parent; }
function money(value) { return Number.isFinite(value) ? "$" + value.toFixed(6) : "Unavailable"; }
function integer(value) { return (Number(value) || 0).toLocaleString("en-US"); }
function wordLines() {
  return [...new Map(dom.words.value.split(/\r?\n/).map(v => v.trim()).filter(Boolean)
    .map(v => [v.toLocaleLowerCase(), v])).values()];
}
function showMessage(message) { dom.message.textContent = message; dom.message.classList.toggle("hidden", !message); }
function showStatus(message) { dom.status.textContent = message; dom.status.classList.toggle("hidden", !message); }
function save() {
  try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(history)); }
  catch (_error) { /* Storage can be disabled by browser privacy settings. */ }
}
function restore() {
  try {
    const data = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "[]");
    if (Array.isArray(data)) history = data.filter(v => v && typeof v === "object" && (v.error || v.analysis));
  } catch (_error) { history = []; }
}
function updateCount() {
  const count = wordLines().length;
  dom.count.textContent = `${count} ${count === 1 ? "expression" : "expressions"}`;
  dom.count.style.color = count > maxWords ? "#b44e2f" : "";
}
function selectedModel() { return catalog.find(m => m.id === dom.model.value); }
function updateModel() {
  const selected = selectedModel();
  if (!selected) return;
  const formerEffort = dom.reasoning.value || "low";
  dom.reasoning.replaceChildren();
  for (const effort of selected.efforts) {
    const option = new Option(effort.charAt(0).toUpperCase() + effort.slice(1), effort);
    dom.reasoning.add(option);
  }
  dom.reasoning.value = selected.efforts.includes(formerEffort) ? formerEffort : "low";
  dom.modelNote.textContent = `${selected.description}. Input $${selected.input} / 1M · output $${selected.output} / 1M tokens.`;
}
function parseDefinitions(words) {
  const raw = dom.definitions.value.trim();
  if (!raw) return Object.create(null);
  if (raw.startsWith("{")) {
    let mapping;
    try { mapping = JSON.parse(raw); }
    catch (_error) { throw new Error("Dictionary mapping must be valid JSON."); }
    if (!mapping || typeof mapping !== "object" || Array.isArray(mapping)) throw new Error("Expected a JSON object mapping words to arrays of definitions.");
    const result = Object.create(null);
    const selectedWords = new Set(words.map(word => word.toLocaleLowerCase()));
    for (const [word, definitions] of Object.entries(mapping)) {
      const key = word.trim().toLocaleLowerCase();
      if (!selectedWords.has(key)) throw new Error("Dictionary mapping includes a word not selected for analysis: " + word);
      if (Object.hasOwn(result, key)) throw new Error("Duplicate word in dictionary mapping: " + word);
      if (!Array.isArray(definitions) || !definitions.length || definitions.some(d => typeof d !== "string" || !d.trim())) throw new Error("Definitions must be nonempty strings in an array for: " + word);
      result[key] = definitions.map(d => d.trim());
    }
    return result;
  }
  if (words.length !== 1) throw new Error("For multiple expressions, supply definitions as a JSON mapping, or leave the field empty.");
  return { [words[0].toLocaleLowerCase()]: raw.split(/\r?\n/).map(v => v.trim()).filter(Boolean) };
}

function renderResult(entry) {
  const card = el("article", "result-card" + (entry.error ? " error-card" : ""));
  const head = el("div", "card-head");
  const eyebrow = el("div", "card-eyebrow", `${entry.model}  ·  ${new Date(entry.time).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`);
  const main = el("div", "card-main");
  const title = el("h3", "card-title", entry.expression);
  const badge = el("span", "badge " + (entry.error ? "none" : (entry.analysis?.commonality || "none")), entry.error ? "Failed" : entry.analysis.commonality);
  append(main, title, badge);
  append(head, eyebrow, main);
  if (entry.error) {
    append(head, el("p", "error-text", entry.error));
    append(card, head);
    return card;
  }
  const a = entry.analysis;
  append(head, el("div", "core-label", "TOP-LEVEL CONCEPT"), el("p", "core-value", a.top_level_concept || "No useful shared core"));
  append(head, el("p", "core-explanation", a.explanation));
  append(card, head);
  const body = el("div", "card-body");
  append(body, el("div", "subheading", "MEANING FAMILIES"));
  for (const family of (a.sub_concepts || [])) {
    const details = el("details", "family");
    details.open = true;
    details.appendChild(el("summary", "family-title", family.label));
    details.appendChild(el("p", "family-desc", family.concept));
    for (const sense of (family.senses || [])) {
      const box = el("div", "sense");
      append(box, el("div", "sense-meaning", sense.meaning), el("div", "sense-pattern", sense.construction), el("div", "sense-example", `“${sense.example}”`));
      details.appendChild(box);
    }
    body.appendChild(details);
  }
  if (Array.isArray(a.caveats) && a.caveats.length) {
    const caveats = el("div", "caveats");
    append(caveats, el("strong", "", "Keep in mind"));
    const list = el("ul");
    for (const item of a.caveats) list.appendChild(el("li", "", item));
    append(caveats, list);
    body.appendChild(caveats);
  }
  card.appendChild(body);
  const footer = el("div", "card-footer");
  const u = entry.usage || {};
  append(footer,
    el("span", "token-details", entry.usage ? `${integer(u.input_tokens)} input (${integer(u.cached_input_tokens)} cached) · ${integer(u.output_tokens)} output (${integer(u.reasoning_tokens)} reasoning)` : "API token usage unavailable"),
    el("span", "item-cost", money(entry.calculated_cost_usd))
  );
  card.appendChild(footer);
  return card;
}
function render() {
  dom.results.replaceChildren();
  for (const entry of [...history].reverse()) dom.results.appendChild(renderResult(entry));
  if (!history.length) {
    const empty = el("div", "empty-state");
    const symbol = el("div", "empty-symbol");
    append(symbol, el("span", "symbol-main", "a"), el("span", "symbol-arrow", "⟶"), el("span", "symbol-main", "A"));
    append(empty, symbol, el("h3", "", "A word is a starting point."),
      el("p", "", "Enter a word or phrase to uncover its related meanings, usage patterns, and the ideas that connect them."));
    const row = el("div", "example-row");
    append(row, el("span", "", "TRY"));
    for (const word of ["sign off", "run", "bank"]) {
      const btn = el("button", "", word); btn.type = "button";
      btn.addEventListener("click", () => { dom.words.value = word; updateCount(); dom.words.focus(); });
      row.appendChild(btn);
    }
    empty.appendChild(row);
    dom.results.appendChild(empty);
  }
  const successes = history.filter(entry => !entry.error);
  const tokens = successes.reduce((n, entry) => n + (entry.usage?.input_tokens || 0) + (entry.usage?.output_tokens || 0), 0);
  const costs = successes.map(entry => entry.calculated_cost_usd);
  const sum = costs.every(Number.isFinite) ? costs.reduce((a,b) => a + b, 0) : null;
  const hasFailures = history.some(entry => Boolean(entry.error) || !entry.usage);
  dom.sessionAnalyses.textContent = integer(successes.length);
  dom.sessionTokens.textContent = (hasFailures ? "≥" : "") + integer(tokens);
  dom.sessionCost.textContent = sum === null ? "Partial / unknown" : (hasFailures ? "≥" : "") + money(sum);
  dom.countResults.textContent = String(history.length);
  dom.export.disabled = history.length === 0;
  dom.clear.disabled = history.length === 0 || running;
}
function busy(isBusy) {
  running = isBusy;
  if (isBusy) { dom.stop.disabled = false; dom.stop.textContent = "Stop after current word"; }
  dom.submit.disabled = isBusy;
  for (const control of [dom.words, dom.model, dom.reasoning, dom.output, dom.definitions]) {
    control.disabled = isBusy;
  }
  dom.stop.classList.toggle("hidden", !isBusy);
  dom.submit.firstChild.textContent = isBusy ? "Analyzing… " : "Analyze meanings ";
  dom.clear.disabled = isBusy || history.length === 0;
}
async function runAnalysis(event) {
  event.preventDefault();
  if (running) return;
  showMessage("");
  const words = wordLines();
  if (!words.length) { showMessage("Enter at least one word or expression."); return; }
  if (words.length > maxWords) { showMessage(`Limit each run to ${maxWords} expressions to control API spending.`); return; }
  if (words.some(word => word.length > 120)) { showMessage("Keep each expression under 120 characters."); return; }
  let definitions;
  try { definitions = parseDefinitions(words); }
  catch (error) { showMessage(error.message); return; }

  // Capture options once: a multi-word run must not mix models mid-submission.
  const settings = {
    model: dom.model.value,
    reasoning: dom.reasoning.value,
    maxOutputTokens: Number(dom.output.value),
  };
  stopRequested = false;
  busy(true);
  let finished = 0;
  for (const word of words) {
    if (stopRequested) break;
    showStatus(`Analyzing ${finished + 1} of ${words.length}: ${word}`);
    try {
      const response = await fetch("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expression: word, model: settings.model, reasoning: settings.reasoning,
          max_output_tokens: settings.maxOutputTokens,
          definitions: definitions[word.toLocaleLowerCase()] || [],
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const text = typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`;
        throw new Error(text);
      }
      history.push({ ...payload, time: new Date().toISOString() });
    } catch (error) {
      history.push({ expression: word, model: settings.model, time: new Date().toISOString(), error: String(error.message || error) });
    }
    finished++;
    save(); render();
  }
  busy(false);
  showStatus(stopRequested ? `Stopped after ${finished} of ${words.length} expressions.` : `Finished ${finished} of ${words.length} expressions.`);
}

async function init() {
  restore(); render();
  dom.words.addEventListener("input", updateCount);
  dom.model.addEventListener("change", updateModel);
  dom.form.addEventListener("submit", runAnalysis);
  dom.stop.addEventListener("click", () => { stopRequested = true; dom.stop.disabled = true; dom.stop.textContent = "Stopping after current…"; });
  dom.export.addEventListener("click", () => {
    const payload = { exported_at: new Date().toISOString(), cost_note: "Calculated from actual API usage and published standard token rates, not an invoice", results: history };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "semantic-hierarchy-session.json";
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  });
  dom.clear.addEventListener("click", () => {
    if (!confirm("Clear this tab's result history and session totals? Export first if you want to keep them.")) return;
    history = []; save(); render(); showStatus("");
  });
  updateCount();
  dom.submit.disabled = true;  // Wait for model catalog before allowing requests.
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error(`Unable to load configuration (${response.status}).`);
    const config = await response.json();
    catalog = config.models;
    maxWords = config.max_words;
    for (const entry of catalog) dom.model.add(new Option(entry.label, entry.id));
    dom.model.value = config.default_model;
    updateModel();
    dom.submit.disabled = !config.has_api_key;
    if (!config.has_api_key) showMessage("OPENAI_API_KEY is not set on the server. Add it to the environment before analyzing.");
  } catch (error) {
    showMessage(String(error.message || error));
    dom.submit.disabled = true;
  }
}
init();
