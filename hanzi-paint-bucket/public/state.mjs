export async function digest(value) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))), x => x.toString(16).padStart(2, '0')).join('');
}
export function validateProgress(value, bank) {
  if (!value || value.revision !== bank.revision || !Array.isArray(value.passed)) throw new Error('存档与当前题集不匹配');
  const passed = [...new Set(value.passed)].sort((a,b) => a-b);
  if (passed.length !== value.passed.length || passed.some((n,i) => !Number.isSafeInteger(n) || n < 1 || n > bank.puzzles.length || n > i + 3)) throw new Error('存档进度无效');
  return {revision: bank.revision, passed};
}
export async function encodeSave(value, bank) {
  const nonce = crypto.getRandomValues(new Uint32Array(4)).join('-');
  const body = 'PAINT1.' + btoa(JSON.stringify({nonce, ...validateProgress(value, bank)}));
  return body + '.' + (await digest(body)).slice(0,16);
}
export async function decodeSave(code, bank) {
  if (code.length > 65536) throw new Error('存档码过长');
  const parts = code.replace(/\s/g, '').split('.');
  if (parts.length !== 3 || parts[0] !== 'PAINT1' || (await digest(parts.slice(0,2).join('.'))).slice(0,16) !== parts[2]) throw new Error('存档码无效或已损坏');
  return validateProgress(JSON.parse(atob(parts[1])), bank);
}
export function nextLevel(passed, current, total) {
  const unlocked = Math.min(total, passed.size + 3);
  for (let n = current + 1; n <= unlocked; n++) if (!passed.has(n)) return n;
  for (let n = 1; n <= unlocked; n++) if (!passed.has(n)) return n;
  return null;
}
