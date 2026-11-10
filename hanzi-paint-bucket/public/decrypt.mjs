const bytes = text => Uint8Array.from(atob(text), char => char.charCodeAt(0));

// Public client key is intentional: this avoids plaintext files, not developer-tool access.
export async function decryptWord(puzzle, encryption) {
  if (encryption.algorithm !== 'AES-GCM') throw new Error('Unsupported encryption');
  const key = await crypto.subtle.importKey('raw', bytes(encryption.key), 'AES-GCM', false, ['decrypt']);
  const plaintext = await crypto.subtle.decrypt({name:'AES-GCM', iv:bytes(puzzle.sealed.iv),
    additionalData:new TextEncoder().encode(puzzle.id)}, key, bytes(puzzle.sealed.ciphertext));
  const word = new TextDecoder('utf-8', {fatal:true}).decode(plaintext);
  if (Array.from(word).length !== puzzle.images.length || !/^\p{Script=Han}+$/u.test(word)) throw new Error('Invalid decrypted content');
  return word;
}
