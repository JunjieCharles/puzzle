// Portable progress only: no player inputs, solutions, or identity credentials.
const plain = (value) => value && typeof value === "object" && !Array.isArray(value);
// Add future modes here; absence in an older code means no saved progress.
const knownModes = ["campaign-one-standard"];

export function migrateProgress(record, targetRevision) {
  if (record?.revision === "cbe3a2f1ecd820a5" && targetRevision === "3a92ed63edc4ea56" &&
      Number.isSafeInteger(record.completed) && record.completed >= 0 && record.completed <= 587) {
    return { revision: targetRevision, completed: record.completed - (record.completed >= 197 ? 1 : 0) };
  }
  return record;
}

export function validateModes(modes) {
  if (!plain(modes) || Object.keys(modes).length > 32) throw new Error("存档格式无效");
  const result = {};
  for (const mode of knownModes) {
    if (!Object.hasOwn(modes, mode)) continue;
    const record = modes[mode];
    if (!plain(record) || !/^[a-f0-9]{16}$/.test(record.revision) || !Number.isSafeInteger(record.completed) || record.completed < 0 || record.completed > 1000000) throw new Error("存档进度无效");
    result[mode] = { revision: record.revision, completed: record.completed };
  }
  return result;
}

async function checksum(text) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

export async function encodeSave(modes) {
  const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  const payload = btoa(JSON.stringify({ v: 1, nonce, modes: validateModes(modes) })).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  const body = `HT101-1.${payload}`;
  return `${body}.${await checksum(body)}`;
}

export async function decodeSave(text) {
  if (text.length > 65536) throw new Error("存档码过长");
  const code = text.replace(/\s/g, "");
  const parts = code.split(".");
  if (parts.length !== 3 || parts[0] !== "HT101-1") throw new Error("无法识别此存档版本");
  if (!/^[A-Za-z0-9_-]+$/.test(parts[1]) || !/^[a-f0-9]{16}$/.test(parts[2]) || await checksum(parts.slice(0, 2).join(".")) !== parts[2]) throw new Error("存档码不完整或已损坏");
  let value;
  try { value = JSON.parse(atob(parts[1].replaceAll("-", "+").replaceAll("_", "/"))); }
  catch { throw new Error("存档格式无效"); }
  if (value?.v !== 1 || !/^[a-f0-9]{32}$/.test(value.nonce)) throw new Error("存档格式无效");
  return validateModes(value.modes);
}
