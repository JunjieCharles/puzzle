import { validateModes } from "./progress.js";
export { migrateProgress, validateModes, normalizeProgress, passedLevels, progressRecord } from "./progress.js";

async function checksum(text) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

export async function encodeSave(modes) {
  const clean = validateModes(modes);
  // Retain the legacy encoder for sequential records; current UI supplies pending.
  const campaignRecords = Object.values(clean).filter(record => !Object.hasOwn(record, "next"));
  const version = Object.values(clean).some(record => Object.hasOwn(record, "pending") || Object.hasOwn(record, "next")) ? 2 : 1;
  if (version === 2 && campaignRecords.some(record => !Object.hasOwn(record, "pending"))) throw new Error("未通过题号缺失");
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  const payload = btoa(JSON.stringify({ v: version, nonce, modes: clean })).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  const body = `HT101-${version}.${payload}`;
  return `${body}.${await checksum(body)}`;
}

export async function decodeSave(text) {
  if (text.length > 65536) throw new Error("存档码过长");
  const code = text.replace(/\s/g, "");
  const parts = code.split(".");
  if (parts.length !== 3 || !["HT101-1", "HT101-2"].includes(parts[0])) throw new Error("无法识别此存档版本");
  if (!/^[A-Za-z0-9_-]+$/.test(parts[1]) || !/^[a-f0-9]{16}$/.test(parts[2]) || await checksum(parts.slice(0, 2).join(".")) !== parts[2]) throw new Error("存档码不完整或已损坏");
  let value;
  try { value = JSON.parse(atob(parts[1].replaceAll("-", "+").replaceAll("_", "/"))); }
  catch { throw new Error("存档格式无效"); }
  if (value?.v !== Number(parts[0].slice(-1)) || !/^[a-f0-9]{32}$/.test(value.nonce)) throw new Error("存档格式无效");
  const modes = validateModes(value.modes);
  if (value.v === 1 && Object.values(modes).some(record => Object.hasOwn(record, "pending") || Object.hasOwn(record, "next"))) throw new Error("存档格式无效");
  if (value.v === 2 && Object.values(modes).some(record => !Object.hasOwn(record, "next") && !Object.hasOwn(record, "pending"))) throw new Error("未通过题号缺失");
  return modes;
}
