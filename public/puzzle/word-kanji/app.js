const $ = (id) => document.getElementById(id);
const storageKey = "word-kanji:campaign:v1";
let campaign, loading, completed = 0, current = 0, generation = 0, busy = false, solved = false;

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
  busy = solved = false;
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
}

async function route() {
  clearEntry();
  let name = location.hash.slice(1) || "home";
  if (!["home", "types", "play", "complete"].includes(name)) name = "home";
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== name;
  $(name).querySelector("h1")?.focus({ preventScroll: true });
  if (name === "home") return;
  const request = generation;
  try {
    await loadCampaign();
    if (request !== generation) return;
    $("saved-progress").textContent = `${completed} / ${campaign.puzzles.length}`;
    if (name === "play") {
      if (completed === campaign.puzzles.length) { location.hash = "complete"; return; }
      current = completed;
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
    }
  }
}

$("puzzle-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!campaign || busy || solved || $("entry").disabled) return;
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

$("entry").addEventListener("input", () => {
  // Invalidate a pending digest if the user changes input before it returns.
  if (busy) { generation++; busy = false; $("submit").disabled = false; }
  feedback();
  $("entry").removeAttribute("aria-invalid");
});
$("entry").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.isComposing || event.keyCode === 229)) event.preventDefault();
});
$("next").addEventListener("click", () => {
  if (!solved) return;
  if (current + 1 === campaign.puzzles.length) location.hash = "complete";
  else { current++; draw(); $("entry").focus(); }
});
$("previous").addEventListener("click", () => { if (current > 0) { current--; draw(); } });
$("resume").addEventListener("click", () => { current = Math.min(completed, campaign.puzzles.length - 1); draw(); });
$("retry").addEventListener("click", route);
$("replay").addEventListener("click", () => { completed = 0; saveProgress(); location.hash = "play"; });
window.addEventListener("hashchange", route);
window.addEventListener("pagehide", clearEntry);
window.addEventListener("pageshow", (event) => { if (event.persisted) route(); });
route();
