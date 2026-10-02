// Portable progress only: no player inputs, solutions, or identity credentials.
import { endlessModes, validateEndless } from "./endless.js";
const plain = (value) => value && typeof value === "object" && !Array.isArray(value);
// Add future modes here; absence in an older code means no saved progress.
const knownModes = ["campaign-one-standard", "campaign-two-standard"];

export function migrateProgress(record, targetRevision) {
  if (record?.revision === "cbe3a2f1ecd820a5" && targetRevision === "3a92ed63edc4ea56" &&
      !Object.hasOwn(record, "pending") && Number.isSafeInteger(record.completed) && record.completed >= 0 && record.completed <= 587) {
    return { revision: targetRevision, completed: record.completed - (record.completed >= 197 ? 1 : 0) };
  }
  return record;
}

export function validateModes(modes) {
  if (!plain(modes) || Object.keys(modes).length > 32) throw new Error("存档格式无效");
  const result = {};
  for (const mode of endlessModes) {
    if (Object.hasOwn(modes, mode)) result[mode] = validateEndless(modes[mode]);
  }
  for (const mode of knownModes) {
    if (!Object.hasOwn(modes, mode)) continue;
    const record = modes[mode];
    if (!plain(record) || !/^[a-f0-9]{16}$/.test(record.revision) || !Number.isSafeInteger(record.completed) || record.completed < 0 || record.completed > 1000000) throw new Error("存档进度无效");
    result[mode] = { revision: record.revision, completed: record.completed };
    if (Object.hasOwn(record, "pending")) {
      if (!Array.isArray(record.pending) || record.pending.length > 3 ||
          record.pending.some((n, i) => !Number.isSafeInteger(n) || n < 1 || n > record.completed + 3 ||
            (i > 0 && n <= record.pending[i - 1]))) throw new Error("未通过题号无效");
      result[mode].pending = [...record.pending];
    }
  }
  return result;
}

// pending contains one-based level numbers within the unlocked prefix only.
// Missing pending is the original sequential save: levels 1..completed passed.
export function normalizeProgress(record, total) {
  const clean = validateModes({ "campaign-one-standard": record })["campaign-one-standard"];
  if (!Number.isSafeInteger(total) || total < 1 || clean.completed > total) throw new Error("进度超出当前关卡数量");
  const unlocked = Math.min(total, clean.completed + 3);
  if (!Object.hasOwn(clean, "pending")) {
    clean.pending = Array.from({ length: unlocked - clean.completed }, (_, i) => clean.completed + i + 1);
  }
  if (clean.pending.length !== unlocked - clean.completed || clean.pending.some(n => n > unlocked)) {
    throw new Error("未通过题号与进度不一致");
  }
  return clean;
}

export function passedLevels(record, total) {
  const clean = normalizeProgress(record, total);
  const pending = new Set(clean.pending);
  return new Set(Array.from({ length: Math.min(total, clean.completed + 3) }, (_, i) => i + 1).filter(n => !pending.has(n)));
}

export function progressRecord(passed, total, revision) {
  const unlocked = Math.min(total, passed.size + 3);
  if ([...passed].some(n => !Number.isSafeInteger(n) || n < 1 || n > unlocked)) throw new Error("已通过题号无效");
  return normalizeProgress({ revision, completed: passed.size,
    pending: Array.from({ length: unlocked }, (_, i) => i + 1).filter(n => !passed.has(n)) }, total);
}
