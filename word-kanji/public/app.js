import { migrateProgress, passedLevels, progressRecord } from "./progress.js";
import { platform } from "./platform.js";
import { EndlessClient, EndlessProgress, endlessModes, REVISION } from "./endless.js";
const $ = (id) => document.getElementById(id);
const oneMode = "campaign-one-standard", twoMode = "campaign-two-standard";
const modes = {
  [oneMode]: { file: "campaign.json", version: "kanji-one-v1", legacyKey: "word-kanji:campaign:v1", key: "word-kanji:campaign:v2", label: "一字标准型", size: 1, completed: 0, passed: new Set(), current: 0 },
  [twoMode]: { file: "campaign-two.json", version: "kanji-two-v1", legacyKey: "word-kanji:campaign-two:v1", key: "word-kanji:campaign-two:v2", label: "二字标准型", size: 2, completed: 0, passed: new Set(), current: 0 },
};
const endlessClient = new EndlessClient();
// Defer storage access until read/write, including browsers that deny the getter.
const endlessProgress = new EndlessProgress({ getItem: key => localStorage.getItem(key), setItem: (key, value) => localStorage.setItem(key, value) });
if (!platform) for (const [i, mode] of endlessModes.entries()) modes[mode] = {
  endless: true, size: i + 1, label: `无尽 · ${i === 0 ? "一" : "二"}字标准型`,
  completed: 0, current: 0, passed: new Set(), data: { revision: REVISION, version: `${REVISION}-${i + 1}`, puzzles: {} },
};
const isEndless = () => Boolean(modes[activeMode].endless);
const isTwo = () => modes[activeMode].size === 2;
const currentPuzzle = () => isEndless() ? modes[activeMode].puzzle : campaign.puzzles[current];
if (!platform) {
  $("endless-start").disabled = false;
  $("endless-start").querySelector(".badge").remove();
  $("endless-start").addEventListener("click", () => navigate("endless-types"));
}
let activeMode = oneMode;
let campaign, completed = 0, current = 0, generation = 0, busy = false, solved = false;
const entries = () => modes[activeMode].size === 2 ? [$("entry"), $("entry-two")] : [$("entry")];
const unlockedCount = () => Math.min(campaign.puzzles.length, completed + 3);
const isPassed = index => modes[activeMode].passed.has(index + 1);
function nextUnpassed(after = -1) {
  const pending = Array.from({ length: unlockedCount() }, (_, i) => i).filter(i => !isPassed(i));
  return pending.find(i => i > after) ?? pending[0];
}
function modeRoute(target, mode = activeMode) {
  if (modes[mode].endless && /^(levels|play|complete)(?=\/|$)/.test(target)) return `endless-${modes[mode].size === 2 ? "two" : "one"}`;
  return mode === twoMode ? target.replace(/^(levels|play|complete)(?=\/|$)/, "$1-two") : target;
}
function activate(mode) {
  modes[activeMode].current = current;
  activeMode = mode;
  campaign = modes[mode].data;
  completed = modes[mode].completed;
  current = modes[mode].current;
}
let composing = false, levelPage = 0;
let pageSize = 60;
let advanceTimer, departureTimer;
const ADVANCE_MS = 900, FADE_MS = 200;

function navigationPath() {
  const currentRoute = location.hash.slice(1) || "home";
  const path = history.state?.wordKanjiPath;
  return Array.isArray(path) && path.at(-1) === currentRoute ? path : [currentRoute];
}

function navigate(target, { replace = false, back = false, mode = activeMode } = {}) {
  target = modeRoute(target, mode);
  const path = navigationPath();
  if (back) {
    const index = path.lastIndexOf(target);
    if (index >= 0 && index < path.length - 1) {
      clearEntry();
      history.go(index - path.length + 1);
      return;
    }
    // Direct links have no in-app parent history; the visible back button still works.
    replace = true;
  }
  if (replace || path.at(-1) === target) path[path.length - 1] = target;
  else path.push(target);
  history[replace || location.hash === `#${target}` ? "replaceState" : "pushState"](
    { wordKanjiPath: path }, "", `#${target}`);
  return route();
}

function scheduleAdvance() {
  // One shared progress animation for every mode; a fresh fill restarts on every pass.
  const indicator = $("next");
  indicator.style.setProperty("--advance-duration", `${ADVANCE_MS}ms`);
  indicator.replaceChildren(document.createElement("span"));
  indicator.hidden = false;
  const request = generation;
  const from = location.hash;
  const next = isEndless() ? current + 1 : nextUnpassed(current);
  const target = next === undefined ? "complete" : `play/${next + 1}`;
  const active = () => request === generation && location.hash === from && solved;
  const mode = activeMode;
  const preparedLevel = modes[mode].completed + 1;
  // Prepare only the next public puzzle while the success animation is visible.
  // A slow Worker extends the completed state, never an empty/flickering board.
  const ready = isEndless() ? endlessClient.get(modes[mode].size, preparedLevel)
    .then(puzzle => {
      if (active()) modes[mode].prepared = { level: preparedLevel, puzzle };
    }, () => { /* Normal navigation retains the loading-error/retry path. */ }) : Promise.resolve();
  departureTimer = setTimeout(async () => {
    await ready;
    if (!active()) return;
    $("puzzle-form").classList.add("departing");
    advanceTimer = setTimeout(() => {
      if (active()) navigate(target, { replace: true });
    }, FADE_MS);
  }, ADVANCE_MS - FADE_MS);
}

function fitLevelGrid() {
  const grid = $("level-grid");
  const bounds = grid.getBoundingClientRect();
  const gap = parseFloat(getComputedStyle(grid).gap);
  const small = window.innerWidth <= 600;
  const columns = Math.max(small ? 3 : 4, Math.min(small ? 5 : 10, Math.floor((bounds.width + gap) / (small ? 88 : 100))));
  const rows = Math.max(1, Math.min(8, Math.floor((bounds.height + gap) / (72 + gap))));
  const anchor = levelPage * pageSize;
  pageSize = columns * rows;
  levelPage = Math.floor(anchor / pageSize);
  grid.style.setProperty("--columns", columns);
  grid.style.gridTemplateRows = `repeat(${rows}, minmax(44px, 1fr))`;
  grid.dataset.pageSize = String(pageSize);
}

function drawLevels() {
  fitLevelGrid();
  const total = campaign.puzzles.length;
  const pages = Math.ceil(total / pageSize);
  levelPage = Math.max(0, Math.min(pages - 1, levelPage));
  $("levels-count").textContent = `${completed} / ${total}`;
  const grid = document.createDocumentFragment();
  for (let index = levelPage * pageSize; index < Math.min(total, (levelPage + 1) * pageSize); index++) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `level-tile${isPassed(index) ? " passed" : ""}`;
    button.textContent = String(index + 1);
    button.disabled = index >= unlockedCount();
    button.setAttribute("aria-label", `第 ${index + 1} 关${isPassed(index) ? "，已通关" : button.disabled ? "，未解锁" : ""}`);
    if (index === nextUnpassed()) button.setAttribute("aria-current", "step");
    button.addEventListener("click", () => navigate(`play/${index + 1}`));
    grid.append(button);
  }
  $("level-grid").replaceChildren(grid);
  $("page-select").replaceChildren(...Array.from({ length: pages }, (_, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${index * pageSize + 1}–${Math.min(total, (index + 1) * pageSize)}`;
    return option;
  }));
  $("page-select").value = String(levelPage);
  $("page-previous").disabled = levelPage === 0;
  $("page-next").disabled = levelPage === pages - 1;
  $("level-pages").hidden = pages === 1;
  $("levels-status").textContent = "";
  $("levels-retry").hidden = true;
}

function readProgress(mode = activeMode) {
  const state = modes[mode];
  if (state.endless) {
    try { state.completed = endlessProgress.read(mode).next - 1; state.progressError = null; }
    catch (error) { state.progressError = error; }
    return state.passed;
  }
  if (platform) return platform.read(mode);
  const passed = new Set();
  if (!state.data) return passed;
  // Keep v1 untouched; old tabs can still advance it without erasing v2 holes.
  for (const key of [state.legacyKey, state.key]) {
    try {
      const raw = JSON.parse(localStorage.getItem(key));
      const value = mode === oneMode ? migrateProgress(raw, state.data.revision) : raw;
      if (value?.revision === state.data.revision) {
        if (key === state.key && !Object.hasOwn(value, "pending")) continue;
        for (const n of passedLevels(value, state.data.puzzles.length)) passed.add(n);
      }
    } catch { /* One damaged/unavailable record must not discard the other. */ }
  }
  return passed;
}

function mergePassed(mode, passed) {
  const state = modes[mode];
  if (state.endless) return;
  for (const n of passed) state.passed.add(n);
  state.completed = state.passed.size;
  if (mode === activeMode) completed = state.completed;
}

function refreshProgressUi() {
  for (const [mode, state] of Object.entries(modes)) {
    if (state.data && !state.endless) $(mode === oneMode ? "saved-progress" : "saved-progress-two").textContent = `${state.completed} / ${state.data.puzzles.length}`;
    if (state.endless) $(`endless-progress-${state.size}`).textContent = `第 ${state.completed + 1} 关`;
  }
  $("progress").value = completed;
  if (campaign && !$("levels").hidden) drawLevels();
}

function syncProgress() {
  for (const [mode, state] of Object.entries(modes)) {
    mergePassed(mode, readProgress(mode));
  }
  completed = modes[activeMode].completed;
  refreshProgressUi();
}

async function saveProgress(mode = activeMode) {
  const state = modes[mode];
  if (state.endless) {
    const saved = await endlessProgress.merge(mode, { revision: REVISION, next: state.completed + 1 });
    state.completed = endlessProgress.read(mode).next - 1;
    state.unsaved = !saved;
    $("save-warning").hidden = !Object.values(modes).some(s => s.unsaved);
    if (mode === activeMode) completed = state.completed;
    refreshProgressUi(); return saved;
  }
  if (platform) {
    platform.save(mode, progressRecord(state.passed, state.data.puzzles.length, state.data.revision));
    refreshProgressUi();
    return true;
  }
  try {
    const write = () => {
      mergePassed(mode, readProgress(mode));
      localStorage.setItem(state.key, JSON.stringify(progressRecord(state.passed, state.data.puzzles.length, state.data.revision)));
    };
    if (navigator.locks) await navigator.locks.request(state.key, write);
    else write();
    if (mode === activeMode) completed = state.completed;
    state.unsaved = false;
    $("save-warning").hidden = !Object.values(modes).some(s => s.unsaved);
    refreshProgressUi();
    return true;
  } catch {
    state.unsaved = true;
    $("save-warning").hidden = false;
    return false;
  }
}

async function loadCampaign(mode = activeMode) {
  const state = modes[mode];
  if (!state.data) {
    if (!state.loading) {
      state.loading = (async () => {
        const response = await fetch(new URL(`./${state.file}`, import.meta.url));
        if (!response.ok) throw new Error("加载失败，请重试");
        const data = await response.json();
        if (data.version !== state.version || !data.puzzles?.length) throw new Error("题集格式无效");
        state.data = data;
        mergePassed(mode, readProgress(mode));
      })().finally(() => { state.loading = undefined; });
    }
    await state.loading;
  }
  if (mode === activeMode) { campaign = state.data; completed = state.completed; }
}

function feedback(text = "", state = "") {
  $("feedback").textContent = text;
  $("feedback").className = `feedback ${state}`;
}

function clearEntry() {
  endlessClient.cancel();
  clearTimeout(advanceTimer);
  clearTimeout(departureTimer);
  $("next").hidden = true;
  $("puzzle-form").classList.remove("departing", "arriving", "reviewing");
  generation++;
  $("reveal").hidden = true;
  $("hide-answer").hidden = true;
  $("review-next").hidden = true;
  $("reveal").disabled = false;
  $("reveal").textContent = "查看答案";
  busy = solved = composing = false;
  for (const input of [$("entry"), $("entry-two")]) {
    input.value = "";
    input.readOnly = false;
    input.classList.remove("solved");
    input.removeAttribute("aria-invalid");
  }
  feedback();
}

function draw() {
  clearEntry();
  const puzzle = currentPuzzle();
  const two = isTwo();
  $("board").classList.toggle("two-board", two);
  $("board").setAttribute("aria-label", `${modes[activeMode].label}题目`);
  for (const element of document.querySelectorAll(".two-cell")) element.hidden = !two;
  for (const side of ["top", "bottom"]) {
    $(side).textContent = two ? puzzle.clues[side][0] : puzzle.clues[side];
    $(`${side}-two`).textContent = two ? puzzle.clues[side][1] : "";
  }
  for (const side of ["left", "right"]) $(side).textContent = puzzle.clues[side];
  $("entry").setAttribute("aria-label", two ? "第一个字" : "填入一个汉字");
  $("entry-two").disabled = !two;
  $("entry-two").readOnly = false;
  $("level-title").textContent = `第 ${current + 1} 关`;
  $("level-count").textContent = isEndless() ? `已通过 ${completed} 关` : `${current + 1} / ${campaign.puzzles.length}`;
  $("progress").hidden = isEndless();
  document.querySelector(".level-nav").hidden = isEndless();
  $("progress").max = isEndless() ? 1 : campaign.puzzles.length;
  $("progress").value = completed;
  $("entry").disabled = false;
  $("submit").hidden = false;
  $("submit").disabled = false;
  $("next").hidden = true;
  $("retry").hidden = true;
  $("previous").disabled = current === 0;
  $("reveal").hidden = isEndless() || !isPassed(current);
  $("review-next").hidden = isEndless();
  $("review-next").disabled = current + 1 >= unlockedCount();
  $("puzzle-form").classList.add("arriving");
  $("entry").focus({ preventScroll: true });
}

async function route() {
  clearEntry();
  for (const input of [$("entry"), $("entry-two")]) input.disabled = true;
  $("submit").disabled = true;
  const [requestedView, requestedLevel] = location.hash.slice(1).split("/");
  let name = requestedView || "home";
  $("play").classList.toggle("endless-play", !platform && ["endless-one", "endless-two"].includes(name));
  if (!platform && ["endless-types", "endless-one", "endless-two"].includes(name)) {
    const selection = name === "endless-types";
    if (!selection) activate(endlessModes[name === "endless-two" ? 1 : 0]);
    for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== (selection ? "endless-types" : "play");
    const request = generation;
    try {
      // Only the next unfinished level is addressable; numeric suffixes cannot skip.
      if (!selection && requestedLevel !== undefined) { navigate(name, { replace: true }); return; }
      syncProgress();
      if (selection) {
        $("endless-status").textContent = endlessModes.some(mode => modes[mode].progressError) ? "部分无尽存档无效，请保留原存档并检查版本" : "";
        $("endless-types-title").focus({ preventScroll: true }); return;
      }
      if (modes[activeMode].progressError) throw modes[activeMode].progressError;
      current = completed;
      for (const label of document.querySelectorAll(".mode-label")) label.textContent = modes[activeMode].label;
      const back = document.querySelector("#play .back"); back.href = "#endless-types"; back.setAttribute("aria-label", "返回题型");
      const state = modes[activeMode];
      const prepared = state.prepared;
      state.prepared = null;
      if (prepared?.level === current + 1) {
        state.puzzle = prepared.puzzle;
        draw();
        return;
      }
      $("level-title").textContent = `第 ${current + 1} 关`;
      $("level-count").textContent = "准备题目…";
      $("progress").hidden = true; document.querySelector(".level-nav").hidden = true;
      $("submit").hidden = true; $("retry").hidden = true; $("next").hidden = true;
      for (const input of [$("entry"), $("entry-two")]) input.disabled = true;
      for (const id of ["top", "bottom", "left", "right", "top-two", "bottom-two"]) $(id).textContent = "";
      const mode = activeMode;
      const puzzle = await endlessClient.get(modes[mode].size, current + 1, (done, target) => {
        if (generation === request) $("level-count").textContent = `恢复进度 ${Math.floor(done / target * 100)}%`;
      });
      if (generation !== request) return;
      modes[mode].puzzle = puzzle;
      draw();
    } catch (error) {
      if (generation !== request) return;
      if (selection) $("endless-status").textContent = error.message;
      else { $("level-count").textContent = ""; feedback(error.message, "error"); $("retry").hidden = false; }
    }
    return;
  }
  $("progress").hidden = false; document.querySelector(".level-nav").hidden = false;
  if (["levels", "play", "complete", "levels-two", "play-two", "complete-two"].includes(name)) {
    activate(name.endsWith("-two") ? twoMode : oneMode);
    name = name.replace(/-two$/, "");
  }
  for (const label of document.querySelectorAll(".mode-label")) label.textContent = modes[activeMode].label;
  for (const link of document.querySelectorAll('#play .back, #complete .back')) { link.href = `#${modeRoute("levels")}`; link.setAttribute("aria-label", "返回选关"); }
  if (!["home", "types", "levels", "play", "complete"].includes(name)) name = "home";
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== name;
  $(name).querySelector("h1")?.focus({ preventScroll: true });
  if (name === "home") return;
  const request = generation;
  try {
    await (name === "types" ? Promise.all(Object.keys(modes).map(loadCampaign)) : loadCampaign());
    if (request !== generation) return;
    syncProgress();
    if (request !== generation) return;
    refreshProgressUi();
    if (name === "levels") {
      fitLevelGrid();
      levelPage = Math.floor((unlockedCount() - 1) / pageSize);
      drawLevels();
    } else if (name === "play") {
      if (requestedLevel !== undefined) {
        const selected = Number(requestedLevel) - 1;
        if (!/^\d+$/.test(requestedLevel) || !Number.isInteger(selected) || selected < 0 || selected >= unlockedCount()) {
          navigate("levels", { back: true });
          return;
        }
        current = selected;
      } else {
        if (completed === campaign.puzzles.length) { navigate("complete", { replace: true }); return; }
        current = nextUnpassed();
      }
      draw();
    } else if (name === "complete") {
      if (completed < campaign.puzzles.length) { navigate("play", { replace: true }); return; }
      $("complete-count").textContent = `${completed} / ${campaign.puzzles.length}`;
    }
  } catch {
    if (request !== generation) return;
    if (name === "play") {
      $("level-title").textContent = "加载失败";
      $("submit").hidden = true;
      $("entry").disabled = true;
      $("retry").hidden = false;
    } else if (name === "levels") {
      $("levels-status").textContent = "加载失败";
      $("levels-retry").hidden = false;
    }
  }
}

$("puzzle-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!campaign || busy || solved || composing || $("entry").disabled) return;
  const values = entries().map(input => input.value.trim().normalize("NFC"));
  const value = values.join("");
  if (!values.every(v => /^\p{Unified_Ideograph}$/u.test(v))) {
    feedback(isTwo() ? "请在两个空格各填一个汉字" : "请输入一个汉字", "error");
    for (const input of entries()) input.setAttribute("aria-invalid", "true");
    $("entry").focus();
    return;
  }
  busy = true;
  $("submit").disabled = true;
  const request = generation;
  const puzzle = currentPuzzle();
  try {
    const bytes = new TextEncoder().encode(`${campaign.version}:${puzzle.id}:${puzzle.salt}:${value}`);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    if (request !== generation) return;
    const check = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    if (check !== puzzle.check) {
      feedback("再想一想", "error");
      for (const input of entries()) input.setAttribute("aria-invalid", "true");
      $("entry").focus();
      $("entry").select();
      return;
    }
    solved = true;
    // Keep the player's current input visible; navigation clears it.
    for (const input of entries()) {
      input.readOnly = true;
      input.classList.add("solved");
      input.removeAttribute("aria-invalid");
    }
    feedback("过关！", "success");
    if (isEndless()) modes[activeMode].completed = Math.max(modes[activeMode].completed, current + 1);
    else mergePassed(activeMode, [current + 1]);
    await saveProgress();
    if (request !== generation) return;
    $("progress").value = completed;
    $("submit").hidden = true;
    scheduleAdvance();
  } catch {
    if (request === generation) feedback("验证失败，请重试", "error");
  } finally {
    if (request === generation) { busy = false; $("submit").disabled = false; }
  }
});

function limitEntry(input) {
  const characters = Array.from(input.value.trim().normalize("NFC"));
  if (isTwo() && characters.length >= 2) {
    // A committed word or pasted phrase fills the whole answer from left to right.
    entries().forEach((field, index) => {
      field.value = characters[index];
      field.removeAttribute("aria-invalid");
    });
  } else {
    input.value = characters[0] || "";
  }
}
function backspaceToFirst(input, event) {
  if (!isTwo() || input !== $("entry-two") || input.value !== "" ||
      input.disabled || input.readOnly || solved || composing || event.isComposing || event.keyCode === 229 ||
      $("entry").disabled || $("entry").readOnly) return;
  event.preventDefault();
  $("entry").value = "";
  // Use the normal input handler to clear errors and cancel any pending validation.
  $("entry").dispatchEvent(new Event("input", { bubbles: true }));
  $("entry").focus({ preventScroll: true });
}
for (const input of [$("entry"), $("entry-two")]) {
  input.addEventListener("compositionstart", () => { composing = true; });
  input.addEventListener("compositionend", () => { composing = false; limitEntry(input); });
  input.addEventListener("input", (event) => {
    if (busy) { generation++; busy = false; $("submit").disabled = false; }
    feedback();
    for (const field of entries()) field.removeAttribute("aria-invalid");
    if (!composing && !event.isComposing) limitEntry(input);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.isComposing || event.keyCode === 229)) event.preventDefault();
    if (event.key === "Backspace") backspaceToFirst(input, event);
    if (isTwo() && !composing && !event.isComposing && event.keyCode !== 229 &&
        !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey &&
        !input.disabled && !input.readOnly && !solved) {
      const target = event.key === "ArrowRight" && input === $("entry") ? $("entry-two") :
        event.key === "ArrowLeft" && input === $("entry-two") ? $("entry") : null;
      if (target && !target.disabled && !target.readOnly) {
        event.preventDefault();
        target.focus({ preventScroll: true });
        target.select();
      }
    }
  });
  input.addEventListener("beforeinput", (event) => {
    if (event.inputType === "deleteContentBackward") backspaceToFirst(input, event);
  });
}
$("previous").addEventListener("click", () => { if (!isEndless() && current > 0) navigate(`play/${current}`, { replace: true }); });
$("hide-answer").addEventListener("click", () => {
  if ($("hide-answer").hidden) return;
  clearEntry();
  $("submit").hidden = false;
  $("submit").disabled = false;
  $("reveal").hidden = false;
  $("review-next").hidden = false;
  $("review-next").disabled = current + 1 >= unlockedCount();
});
$("review-next").addEventListener("click", () => {
  if (!$("review-next").hidden && current + 1 < unlockedCount()) {
    navigate(`play/${current + 2}`, { replace: true });
  }
});
let twoWords;
async function* revealCandidates(mode) {
  if (mode === twoMode) {
    if (!twoWords) {
      const response = await fetch(new URL("./hsk-two-words.json", import.meta.url));
      if (!response.ok) throw new Error("vocabulary load");
      const data = await response.json();
      if (data.version !== "hsk-two-words-v1" || !Array.isArray(data.words)) throw new Error("vocabulary format");
      twoWords = data.words;
    }
    for (let offset = 0; offset < twoWords.length; offset += 256) yield twoWords.slice(offset, offset + 256);
    return;
  }
  const ranges = [[0x4e00, 0x9fff], [0x3400, 0x4dbf], [0, 0x33ff], [0x4dc0, 0x4dff], [0xa000, 0x10ffff]];
  for (const [start, end] of ranges) {
    for (let offset = start; offset <= end; offset += 256) {
      const candidates = [];
      for (let code = offset; code <= Math.min(end, offset + 255); code++) {
        const value = String.fromCodePoint(code);
        if (/^\p{Unified_Ideograph}$/u.test(value)) candidates.push(value);
      }
      yield candidates;
    }
  }
}
$("reveal").addEventListener("click", async () => {
  if (!campaign || isEndless() || !isPassed(current) || busy || solved) return;
  const request = generation;
  const puzzle = campaign.puzzles[current];
  busy = true;
  $("reveal").disabled = true;
  $("reveal").textContent = "查看中…";
  $("submit").disabled = true;
  for (const input of entries()) input.readOnly = true;
  const encoder = new TextEncoder();
  const prefix = `${campaign.version}:${puzzle.id}:${puzzle.salt}:`;
  try {
    for await (const candidates of revealCandidates(activeMode)) {
      if (request !== generation) return;
        const matches = await Promise.all(candidates.map(async value => {
          const digest = await crypto.subtle.digest("SHA-256", encoder.encode(prefix + value.normalize("NFC")));
          const check = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
          return check === puzzle.check ? value : null;
        }));
        if (request !== generation) return;
        const match = matches.find(Boolean);
        if (match) {
          $("puzzle-form").classList.add("reviewing");
          entries().forEach((input, i) => {
            input.value = Array.from(match)[i];
            input.classList.add("solved");
            input.removeAttribute("aria-invalid");
          });
          solved = true;
          $("submit").hidden = true;
          $("reveal").hidden = true;
          $("hide-answer").hidden = false;
          $("review-next").hidden = false;
          $("review-next").disabled = current + 1 >= unlockedCount();
          feedback("答案已显示", "success");
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 0));
    }
    throw new Error("No matching candidate");
  } catch {
    if (request === generation) feedback("查看失败，请重试", "error");
  } finally {
    if (request === generation) {
      busy = false;
      $("reveal").disabled = false;
      $("reveal").textContent = "查看答案";
      $("submit").disabled = false;
      for (const input of entries()) input.readOnly = solved;
    }
  }
});
$("retry").addEventListener("click", route);
$("levels-retry").addEventListener("click", route);
$("page-previous").addEventListener("click", () => { levelPage--; drawLevels(); });
$("page-next").addEventListener("click", () => { levelPage++; drawLevels(); });
$("page-select").addEventListener("change", () => { levelPage = Number($("page-select").value); drawLevels(); });
window.addEventListener("hashchange", route);
document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="#"]');
  if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(link.hash.slice(1), { back: link.classList.contains("back"), mode: link.id === "start" ? oneMode : activeMode });
});
function selectHelp(size, focus = false) {
  for (const [i, name] of ["one", "two"].entries()) {
    const selected = size === i + 1, tab = $(`help-tab-${name}`);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`help-panel-${name}`).hidden = !selected;
    if (selected && focus) tab.focus();
  }
}
for (const [i, name] of ["one", "two"].entries()) {
  const tab = $(`help-tab-${name}`);
  tab.addEventListener("click", () => selectHelp(i + 1));
  tab.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    selectHelp(event.key === "Home" ? 1 : event.key === "End" ? 2 : 2 - i, true);
  });
}
$("help-open").addEventListener("click", () => {
  selectHelp(modes[activeMode].size);
  $("help-dialog").showModal();
});
// WEB-SAVE-BEGIN
if (!platform) {
const { encodeSave, decodeSave } = await import("./save-code.js?v=progress-2");
$("save-open").addEventListener("click", () => {
  $("save-status").textContent = "";
  $("save-dialog").showModal();
});
$("warning-export").addEventListener("click", () => $("save-open").click());
let saveBusy = false;
async function saveAction(action) {
  if (saveBusy) return;
  saveBusy = true;
  $("save-export").disabled = $("save-import").disabled = true;
  try { await Promise.all(Object.keys(modes).map(loadCampaign)); syncProgress(); await action(); }
  catch (error) { $("save-status").textContent = error.message || "操作失败，请重试"; }
  finally { saveBusy = false; $("save-export").disabled = $("save-import").disabled = false; }
}
$("save-export").addEventListener("click", () => saveAction(async () => {
  const progress = {};
  for (const [mode, state] of Object.entries(modes)) {
    if (state.endless) {
      if (state.progressError) throw state.progressError;
      if (state.completed > 0) progress[mode] = endlessProgress.read(mode);
      continue;
    }
    if (mode === oneMode || state.completed > 0) progress[mode] = progressRecord(state.passed, state.data.puzzles.length, state.data.revision);
  }
  const code = await encodeSave(progress);
  $("save-code").value = code;
  try {
    await navigator.clipboard.writeText(code);
    $("save-status").textContent = "存档码已复制";
  } catch {
    $("save-code").focus(); $("save-code").select();
    $("save-status").textContent = "存档码已生成，请长按或手动复制";
  }
}));
$("save-import").addEventListener("click", () => saveAction(async () => {
  const incoming = await decodeSave($("save-code").value);
  const updates = [];
  for (const [mode, state] of Object.entries(modes)) {
    if (!incoming[mode]) continue;
    if (state.endless) {
      if (state.progressError) throw state.progressError;
      updates.push([mode, incoming[mode]]); continue;
    }
    const record = mode === oneMode ? migrateProgress(incoming[mode], state.data.revision) : incoming[mode];
    if (record.revision !== state.data.revision) throw new Error("存档题集与当前版本不同");
    updates.push([mode, passedLevels(record, state.data.puzzles.length)]);
  }
  if (!updates.length) throw new Error("存档中没有支持的模式进度");
  // Validate every supported record before changing either mode.
  clearEntry();
  for (const [mode, passed] of updates) {
    if (modes[mode].endless) modes[mode].completed = Math.max(modes[mode].completed, passed.next - 1);
    else mergePassed(mode, passed);
  }
  completed = modes[activeMode].completed;
  let persisted = true;
  for (const [mode] of updates) if (!await saveProgress(mode)) persisted = false;
  const destination = incoming[activeMode] ? activeMode : updates[0][0];
  activate(destination);
  current = isEndless() ? completed : nextUnpassed() ?? campaign.puzzles.length - 1;
  await navigate(isEndless() ? "play" : "levels", { back: navigationPath().includes(modeRoute("levels")) });
  $("save-status").textContent = !persisted ? "已导入本次游戏，但浏览器未能保存，请保留存档码" :
    "已导入，合并已通过题目";
}));
}
// WEB-SAVE-END
let resizeFrame;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => { if (campaign && !$("levels").hidden) drawLevels(); });
});
window.addEventListener("pagehide", clearEntry);
window.addEventListener("pageshow", (event) => { if (event.persisted) route(); });
if (platform) {
  await platform.start({
    async catalog() {
      await Promise.all(Object.keys(modes).map(loadCampaign));
      return Object.fromEntries(Object.entries(modes).map(([mode, state]) =>
        [mode, { revision: state.data.revision, total: state.data.puzzles.length }]));
    },
    update(records, replace = false) {
      if (replace) {
        clearEntry();
        for (const state of Object.values(modes)) { state.passed.clear(); state.completed = 0; }
      }
      for (const [mode, record] of Object.entries(records)) {
        if (modes[mode]?.data) mergePassed(mode, passedLevels(record, modes[mode].data.puzzles.length));
      }
      refreshProgressUi();
      if (replace) navigate("home", { replace: true });
    },
  });
}
route();
