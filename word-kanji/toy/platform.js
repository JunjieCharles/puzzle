import { CloudProgress, boards } from "./cloud.js";

const $ = id => document.getElementById(id);
let cloud, hooks, activeBoard = 1, rankRequest = 0, connecting = false, restore;
const rankCache = new Map();
let rankPending, rankRetryAt = 0, rankFailures = 0;
let rankData, rankPage = 0, rankPageSize = 1;
function sdk() {
  if (!window.toy?.getCloudStorage) throw Object.assign(new Error("请在 B站 Toy 中打开，或稍后重试"), { type: "unsupported" });
  return window.toy;
}
function status(message, connected) {
  const failed = /待同步|失败|较多|损坏|失效|不可用|无效|请先登录/.test(message);
  const label = /请先登录/.test(message) ? "需登录" : failed ? "待同步" : /已自动保存|已同步|已自动读取/.test(message) ? "已保存" : "读取中";
  $("cloud-status").textContent = `云存档 · ${label}`;
  $("cloud-status").dataset.message = message;
  $("cloud-status").setAttribute("aria-label", `云存档：${message}`);
  $("cloud-state").title = message;
  $("cloud-state").classList.toggle("needs-attention", failed);
  $("cloud-retry").hidden = !failed;
  $("cloud-retry").disabled = connecting;
  if (message.startsWith("账号已变化")) queueMicrotask(() => void restore?.());
}
function update(records, replace) {
  rankCache.clear();
  if (replace) {
    rankData = undefined; rankPage = 0;
    rankRequest++; $("rank-mine").textContent = "";
    $("rank-rows").replaceChildren();
  }
  hooks.update(records, replace);
}
function drawRankPage() {
  const data = rankData;
  if (!data || !$("rank-dialog").open) return;
  const pages = Math.max(1, Math.ceil(data.rows.length / rankPageSize));
  rankPage = Math.min(rankPage, pages - 1);
  const fragment = document.createDocumentFragment();
  for (const item of data.rows.slice(rankPage * rankPageSize, (rankPage + 1) * rankPageSize)) {
    const row = document.createElement("tr");
    for (const value of [item.rank, item.nickname, item.score]) {
      const cell = document.createElement("td"); cell.textContent = String(value); cell.title = String(value); row.append(cell);
    }
    fragment.append(row);
  }
  $("rank-rows").replaceChildren(fragment);
  $("rank-page").textContent = `${rankPage + 1} / ${pages}`;
  $("rank-prev").disabled = rankPage === 0;
  $("rank-next").disabled = rankPage >= pages - 1;
}
function fitRankPage() {
  if (!rankData || !$("rank-dialog").open) return;
  const anchor = rankPage * rankPageSize;
  rankPage = 0; rankPageSize = 1; drawRankPage();
  const row = $("rank-rows").firstElementChild;
  if (row) {
    const table = $("rank-rows").closest("table");
    const overhead = table.getBoundingClientRect().height - row.getBoundingClientRect().height;
    rankPageSize = Math.max(1, Math.floor(($("rank-list-space").clientHeight - overhead - 2) / row.getBoundingClientRect().height));
    rankPage = Math.floor(anchor / rankPageSize);
  }
  drawRankPage();
}
function showRanks(data) {
  rankData = data;
  $("rank-mine").textContent = data.mine ? data.mine.ranked ?
    `我的排名：第 ${data.mine.rank} 名 · 已通过 ${data.mine.score} 题` : "尚未上榜" : "登录 B站后可查看我的排名";
  $("rank-status").textContent = data.rows.length ? "" : "还没有人上榜，来完成第一关吧";
  fitRankPage();
}
async function loadRanks(refresh = false) {
  const board = activeBoard, request = ++rankRequest;
  $("rank-one").setAttribute("aria-pressed", String(board === 1));
  $("rank-two").setAttribute("aria-pressed", String(board === 2));
  $("rank-rows").replaceChildren(); $("rank-mine").textContent = "";
  rankData = undefined;
  $("rank-prev").disabled = $("rank-next").disabled = true;
  $("rank-page").textContent = "—";
  if (!refresh && rankCache.has(board)) { showRanks(rankCache.get(board)); return; }
  if (rankPending) {
    $("rank-status").textContent = "正在加载…";
    await rankPending;
    if (request === rankRequest) void loadRanks(refresh);
    return;
  }
  if (Date.now() < rankRetryAt) { $("rank-status").textContent = "请稍后再刷新榜单"; return; }
  $("rank-status").textContent = "正在加载…";
  $("rank-refresh").disabled = true;
  rankPending = (async () => {
    const epoch = cloud?.epoch;
    const api = sdk();
    const rows = await api.getRankList({ board, period: "all", limit: 100 });
    let mine;
    if (cloud?.identity) {
      await cloud.verify(epoch);
      mine = await api.getMyRank({ board, period: "all" });
      cloud.assert(epoch);
    }
    if (!Array.isArray(rows)) throw new Error("榜单格式无效");
    if (epoch !== cloud?.epoch) return;
    const data = { rows, mine }; rankCache.set(board, data);
    rankFailures = 0; rankRetryAt = 0;
    if (request === rankRequest) showRanks(data);
  })().catch(error => {
    rankRetryAt = Date.now() + Math.min(60000, 2000 * 2 ** Math.min(rankFailures++, 5));
    if (request === rankRequest) $("rank-status").textContent = error.code === 307044 ?
      "请求较多，请稍后刷新" : "排行榜暂不可用，请稍后刷新";
  }).finally(() => { rankPending = undefined; $("rank-refresh").disabled = false; });
  await rankPending;
}
function openRanks() {
  rankPage = 0;
  $("rank-dialog").showModal(); void loadRanks();
}

export const platform = {
  read(mode) { return cloud?.read(mode) || new Set(); },
  save(mode, record) { cloud?.save(mode, record); },
  async start(bridge) {
    hooks = bridge;
    $("rank-open").addEventListener("click", openRanks);
    $("rank-one").addEventListener("click", () => { activeBoard = 1; rankPage = 0; void loadRanks(); });
    $("rank-two").addEventListener("click", () => { activeBoard = 2; rankPage = 0; void loadRanks(); });
    $("rank-refresh").addEventListener("click", () => { rankPage = 0; void loadRanks(true); });
    $("rank-prev").addEventListener("click", () => { if (rankPage > 0) { rankPage--; drawRankPage(); } });
    $("rank-next").addEventListener("click", () => { if (rankData && (rankPage + 1) * rankPageSize < rankData.rows.length) { rankPage++; drawRankPage(); } });
    window.addEventListener("resize", fitRankPage);
    window.visualViewport?.addEventListener("resize", fitRankPage);
    let retryTimer, attempts = 0;
    restore = async () => {
      if (connecting) return;
      connecting = true; $("cloud-retry").disabled = true;
      clearTimeout(retryTimer);
      document.querySelector("main").inert = true;
      try {
        sdk();
        const catalog = await bridge.catalog();
        if (!cloud) cloud = new CloudProgress({ sdk, storage: () => localStorage, catalog, update, status });
        await cloud.connect(); attempts = 0;
      } catch (error) {
        const auth = ["unauthorized", "denied"].includes(error.type);
        status(auth ? "请先登录 B站，登录后将自动读取云存档" : error.message || "云存档暂不可用，稍后自动重试", false);
        if (!auth && !error.permanent && attempts < 5) {
          retryTimer = setTimeout(() => void restore(), Math.min(60000, 2000 * 2 ** attempts++) + Math.random() * 1000);
        }
      } finally { connecting = false; $("cloud-retry").disabled = false; document.querySelector("main").inert = false; }
    };
    const resume = () => { if (cloud?.identity) void cloud.flush(); else void restore(); };
    $("cloud-retry").addEventListener("click", resume);
    window.addEventListener("online", resume);
    document.addEventListener("visibilitychange", () => {
      // Revalidate identity after leaving the page; no polling of account/profile.
      if (!document.hidden) resume();
    });
    status("正在读取云存档…", false);
    await restore();
  },
};
