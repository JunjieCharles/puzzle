import { encodeSave, decodeSave, migrateProgress, passedLevels, progressRecord } from "./save-code.js?v=progress-2";
const $ = (id) => document.getElementById(id);
const oneMode = "campaign-one-standard", twoMode = "campaign-two-standard";
const modes = {
  [oneMode]: { file: "campaign.json", version: "kanji-one-v1", legacyKey: "word-kanji:campaign:v1", key: "word-kanji:campaign:v2", label: "一字标准型", size: 1, completed: 0, passed: new Set(), current: 0 },
  [twoMode]: { file: "campaign-two.json", version: "kanji-two-v1", legacyKey: "word-kanji:campaign-two:v1", key: "word-kanji:campaign-two:v2", label: "二字标准型", size: 2, completed: 0, passed: new Set(), current: 0 },
};
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
  const request = generation;
  const from = location.hash;
  const next = nextUnpassed(current);
  const target = next === undefined ? "complete" : `play/${next + 1}`;
  const active = () => request === generation && location.hash === from && solved;
  departureTimer = setTimeout(() => {
    if (active()) $("puzzle-form").classList.add("departing");
  }, 700);
  advanceTimer = setTimeout(() => {
    if (active()) navigate(target, { replace: true });
  }, 900);
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
  for (const n of passed) state.passed.add(n);
  state.completed = state.passed.size;
  if (mode === activeMode) completed = state.completed;
}

function refreshProgressUi() {
  for (const [mode, state] of Object.entries(modes)) {
    if (state.data) $(mode === oneMode ? "saved-progress" : "saved-progress-two").textContent = `${state.completed} / ${state.data.puzzles.length}`;
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
  clearTimeout(advanceTimer);
  clearTimeout(departureTimer);
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
  const puzzle = campaign.puzzles[current];
  const two = activeMode === twoMode;
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
  $("level-count").textContent = `${current + 1} / ${campaign.puzzles.length}`;
  $("progress").max = campaign.puzzles.length;
  $("progress").value = completed;
  $("entry").disabled = false;
  $("submit").hidden = false;
  $("submit").disabled = false;
  $("next").hidden = true;
  $("retry").hidden = true;
  $("previous").disabled = current === 0;
  $("reveal").hidden = !isPassed(current);
  $("review-next").hidden = false;
  $("review-next").disabled = current + 1 >= unlockedCount();
  $("puzzle-form").classList.add("arriving");
  $("entry").focus({ preventScroll: true });
}

async function route() {
  clearEntry();
  const [requestedView, requestedLevel] = location.hash.slice(1).split("/");
  let name = requestedView || "home";
  if (["levels", "play", "complete", "levels-two", "play-two", "complete-two"].includes(name)) {
    activate(name.endsWith("-two") ? twoMode : oneMode);
    name = name.replace(/-two$/, "");
  }
  for (const label of document.querySelectorAll(".mode-label")) label.textContent = modes[activeMode].label;
  for (const link of document.querySelectorAll('#play .back, #complete .back')) link.href = `#${modeRoute("levels")}`;
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
      levelPage = Math.floor(Math.min(current, unlockedCount() - 1) / pageSize);
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
    feedback(activeMode === twoMode ? "请在两个空格各填一个汉字" : "请输入一个汉字", "error");
    for (const input of entries()) input.setAttribute("aria-invalid", "true");
    $("entry").focus();
    return;
  }
  busy = true;
  $("submit").disabled = true;
  const request = generation;
  const puzzle = campaign.puzzles[current];
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
    mergePassed(activeMode, [current + 1]);
    await saveProgress();
    if (request !== generation) return;
    $("progress").value = completed;
    $("submit").hidden = true;
    $("next").hidden = false;
    scheduleAdvance();
  } catch {
    if (request === generation) feedback("验证失败，请重试", "error");
  } finally {
    if (request === generation) { busy = false; $("submit").disabled = false; }
  }
});

function limitEntry(input) {
  const characters = Array.from(input.value.trim().normalize("NFC"));
  if (activeMode === twoMode && characters.length >= 2) {
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
  if (activeMode !== twoMode || input !== $("entry-two") || input.value !== "" ||
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
    if (activeMode === twoMode && !composing && !event.isComposing && event.keyCode !== 229 &&
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
$("previous").addEventListener("click", () => { if (current > 0) navigate(`play/${current}`, { replace: true }); });
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
  if (!campaign || !isPassed(current) || busy || solved) return;
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
$("help-open").addEventListener("click", () => {
  $("help-dialog").showModal();
});
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
    const record = mode === oneMode ? migrateProgress(incoming[mode], state.data.revision) : incoming[mode];
    if (record.revision !== state.data.revision) throw new Error("存档题集与当前版本不同");
    updates.push([mode, passedLevels(record, state.data.puzzles.length)]);
  }
  if (!updates.length) throw new Error("存档中没有支持的模式进度");
  // Validate every supported record before changing either mode.
  clearEntry();
  for (const [mode, passed] of updates) mergePassed(mode, passed);
  completed = modes[activeMode].completed;
  let persisted = true;
  for (const [mode] of updates) if (!await saveProgress(mode)) persisted = false;
  const destination = incoming[activeMode] ? activeMode : updates[0][0];
  activate(destination);
  current = nextUnpassed() ?? campaign.puzzles.length - 1;
  await navigate("levels", { back: navigationPath().includes(modeRoute("levels")) });
  $("save-status").textContent = !persisted ? "已导入本次游戏，但浏览器未能保存，请保留存档码" :
    "已导入，合并已通过题目";
}));
let resizeFrame;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => { if (campaign && !$("levels").hidden) drawLevels(); });
});
window.addEventListener("pagehide", clearEntry);
window.addEventListener("pageshow", (event) => { if (event.persisted) route(); });
route();
