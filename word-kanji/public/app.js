import { encodeSave, decodeSave } from "./save-code.js";
const $ = (id) => document.getElementById(id);
const storageKey = "word-kanji:campaign:v1";
const activeMode = "campaign-one-standard";
let campaign, loading, completed = 0, current = 0, generation = 0, busy = false, solved = false;
let composing = false, levelPage = 0;
let pageSize = 60;
let advanceTimer, departureTimer;

function scheduleAdvance() {
  const request = generation;
  const from = location.hash;
  const target = current + 1 === campaign.puzzles.length ? "complete" : `play/${current + 2}`;
  const active = () => request === generation && location.hash === from && solved;
  departureTimer = setTimeout(() => {
    if (active()) $("puzzle-form").classList.add("departing");
  }, 700);
  advanceTimer = setTimeout(() => {
    if (active()) location.hash = target;
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
    button.className = `level-tile${index < completed ? " passed" : ""}`;
    button.textContent = String(index + 1);
    button.disabled = index > completed;
    button.setAttribute("aria-label", `第 ${index + 1} 关${index < completed ? "，已通关" : index > completed ? "，未解锁" : ""}`);
    if (index === completed) button.setAttribute("aria-current", "step");
    button.addEventListener("click", () => { location.hash = `play/${index + 1}`; });
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

function readProgress() {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey));
    if (value?.revision === campaign.revision && Number.isInteger(value.completed)) {
      return Math.max(0, Math.min(campaign.puzzles.length, value.completed));
    }
  } catch { /* Playing remains available when storage is disabled. */ }
  return 0;
}

function saveProgress() {
  // Store only a revision and the unlocked position, never player input.
  try {
    localStorage.setItem(storageKey, JSON.stringify({ revision: campaign.revision, completed }));
    return true;
  } catch { return false; /* Still available for export during this session. */ }
}

async function loadCampaign() {
  if (campaign) return;
  if (!loading) {
    loading = (async () => {
      const response = await fetch(new URL("./campaign.json", import.meta.url));
      if (!response.ok) throw new Error("load");
      const data = await response.json();
      if (data.version !== "kanji-one-v1" || !data.puzzles?.length) throw new Error("format");
      campaign = data;
      completed = readProgress();
    })().finally(() => { loading = undefined; });
  }
  await loading;
}

function feedback(text = "", state = "") {
  $("feedback").textContent = text;
  $("feedback").className = `feedback ${state}`;
}

function clearEntry() {
  clearTimeout(advanceTimer);
  clearTimeout(departureTimer);
  $("puzzle-form").classList.remove("departing", "arriving");
  generation++;
  busy = solved = composing = false;
  $("entry").value = "";
  $("entry").readOnly = false;
  $("entry").classList.remove("solved");
  $("entry").removeAttribute("aria-invalid");
  feedback();
}

function draw() {
  clearEntry();
  const puzzle = campaign.puzzles[current];
  for (const side of ["top", "left", "bottom", "right"]) $(side).textContent = puzzle.clues[side];
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
  $("puzzle-form").classList.add("arriving");
  $("entry").focus({ preventScroll: true });
}

async function route() {
  clearEntry();
  const [requestedView, requestedLevel] = location.hash.slice(1).split("/");
  let name = requestedView || "home";
  if (!["home", "types", "levels", "play", "complete"].includes(name)) name = "home";
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== name;
  $(name).querySelector("h1")?.focus({ preventScroll: true });
  if (name === "home") return;
  const request = generation;
  try {
    await loadCampaign();
    if (request !== generation) return;
    $("saved-progress").textContent = `${completed} / ${campaign.puzzles.length}`;
    if (name === "levels") {
      fitLevelGrid();
      levelPage = Math.floor(Math.min(current, completed, campaign.puzzles.length - 1) / pageSize);
      drawLevels();
    } else if (name === "play") {
      if (requestedLevel !== undefined) {
        const selected = Number(requestedLevel) - 1;
        if (!/^\d+$/.test(requestedLevel) || !Number.isInteger(selected) || selected < 0 || selected > completed || selected >= campaign.puzzles.length) {
          location.hash = "levels";
          return;
        }
        current = selected;
      } else {
        if (completed === campaign.puzzles.length) { location.hash = "complete"; return; }
        current = completed;
      }
      draw();
    } else if (name === "complete") {
      if (completed < campaign.puzzles.length) { location.hash = "play"; return; }
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
  const value = $("entry").value.trim().normalize("NFC");
  if (!/^\p{Unified_Ideograph}$/u.test(value)) {
    feedback("请输入一个汉字", "error");
    $("entry").setAttribute("aria-invalid", "true");
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
      $("entry").setAttribute("aria-invalid", "true");
      $("entry").focus();
      $("entry").select();
      return;
    }
    solved = true;
    // Keep the player's current input visible; navigation clears it.
    $("entry").readOnly = true;
    $("entry").classList.add("solved");
    $("entry").removeAttribute("aria-invalid");
    feedback("过关！", "success");
    completed = Math.max(completed, current + 1);
    saveProgress();
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

function limitEntry() {
  // Count Unicode code points, preserving supplementary-plane Hanzi intact.
  $("entry").value = Array.from($("entry").value.trim().normalize("NFC"))[0] || "";
}
$("entry").addEventListener("compositionstart", () => { composing = true; });
$("entry").addEventListener("compositionend", () => { composing = false; limitEntry(); });
$("entry").addEventListener("input", (event) => {
  // Invalidate a pending digest if the user changes input before it returns.
  if (busy) { generation++; busy = false; $("submit").disabled = false; }
  feedback();
  $("entry").removeAttribute("aria-invalid");
  if (!composing && !event.isComposing) limitEntry();
});
$("entry").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.isComposing || event.keyCode === 229)) event.preventDefault();
});
$("previous").addEventListener("click", () => { if (current > 0) location.hash = `play/${current}`; });
$("retry").addEventListener("click", route);
$("levels-retry").addEventListener("click", route);
$("page-previous").addEventListener("click", () => { levelPage--; drawLevels(); });
$("page-next").addEventListener("click", () => { levelPage++; drawLevels(); });
$("page-select").addEventListener("change", () => { levelPage = Number($("page-select").value); drawLevels(); });
$("replay").addEventListener("click", () => { completed = 0; saveProgress(); location.hash = "play"; });
window.addEventListener("hashchange", route);
$("help-open").addEventListener("click", () => {
  $("help-dialog").showModal();
});
$("save-open").addEventListener("click", () => {
  $("save-status").textContent = "";
  $("save-dialog").showModal();
});
let saveBusy = false;
async function saveAction(action) {
  if (saveBusy) return;
  saveBusy = true;
  $("save-export").disabled = $("save-import").disabled = true;
  try { await loadCampaign(); await action(); }
  catch (error) { $("save-status").textContent = error.message || "操作失败，请重试"; }
  finally { saveBusy = false; $("save-export").disabled = $("save-import").disabled = false; }
}
$("save-export").addEventListener("click", () => saveAction(async () => {
  const code = await encodeSave({ [activeMode]: { revision: campaign.revision, completed } });
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
  const record = incoming[activeMode];
  if (!record) throw new Error("存档中没有当前模式的进度");
  if (record.revision !== campaign.revision) throw new Error("存档题集与当前版本不同");
  if (record.completed > campaign.puzzles.length) throw new Error("进度超出当前关卡数量");
  completed = Math.max(completed, record.completed);
  const persisted = saveProgress();
  current = Math.min(completed, campaign.puzzles.length - 1);
  clearEntry();
  location.hash = "levels";
  await route();
  $("save-status").textContent = !persisted ? "已导入本次游戏，但浏览器未能保存，请保留存档码" :
    "已导入，保留较高进度";
}));
let resizeFrame;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => { if (campaign && !$("levels").hidden) drawLevels(); });
});
window.addEventListener("pagehide", clearEntry);
window.addEventListener("pageshow", (event) => { if (event.persisted) route(); });
route();
