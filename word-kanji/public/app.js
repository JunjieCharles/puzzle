const $ = (id) => document.getElementById(id);
const storageKey = "word-kanji:campaign:v1";
let campaign, loading, completed = 0, current = 0, generation = 0, busy = false, solved = false;
let composing = false, levelPage = 0;
const pageSize = 60;

function drawLevels() {
  const total = campaign.puzzles.length;
  const pages = Math.ceil(total / pageSize);
  levelPage = Math.max(0, Math.min(pages - 1, levelPage));
  $("levels-count").textContent = `${completed} / ${total}`;
  $("continue-level").href = completed === total ? "#complete" : `#play/${completed + 1}`;
  $("continue-level").textContent = completed === total ? "全部通关 →" : "继续闯关 →";
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
  } catch { /* Progress is still maintained in memory for this session. */ }
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
  $("resume").hidden = current >= Math.min(completed, campaign.puzzles.length - 1);
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
    $("entry").value = "";
    $("entry").readOnly = true;
    $("entry").classList.add("solved");
    $("entry").removeAttribute("aria-invalid");
    feedback("过关！", "success");
    completed = Math.max(completed, current + 1);
    saveProgress();
    $("progress").value = completed;
    $("submit").hidden = true;
    $("next").hidden = false;
    $("next").textContent = current + 1 === campaign.puzzles.length ? "完成闯关 →" : "下一关 →";
    $("next").focus();
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
$("next").addEventListener("click", () => {
  if (!solved) return;
  if (current + 1 === campaign.puzzles.length) location.hash = "complete";
  else location.hash = `play/${current + 2}`;
});
$("previous").addEventListener("click", () => { if (current > 0) location.hash = `play/${current}`; });
$("resume").addEventListener("click", () => { location.hash = `play/${Math.min(completed + 1, campaign.puzzles.length)}`; });
$("retry").addEventListener("click", route);
$("levels-retry").addEventListener("click", route);
$("page-previous").addEventListener("click", () => { levelPage--; drawLevels(); });
$("page-next").addEventListener("click", () => { levelPage++; drawLevels(); });
$("page-select").addEventListener("change", () => { levelPage = Number($("page-select").value); drawLevels(); });
$("replay").addEventListener("click", () => { completed = 0; saveProgress(); location.hash = "play"; });
window.addEventListener("hashchange", route);
window.addEventListener("pagehide", clearEntry);
window.addEventListener("pageshow", (event) => { if (event.persisted) route(); });
route();
