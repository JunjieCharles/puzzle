const bytes = text => Uint8Array.from(atob(text), char => char.charCodeAt(0));

// Public client key is intentional: this avoids plaintext files, not developer-tool access.
export async function decryptPuzzle(puzzle, encryption) {
  if (encryption.algorithm !== 'AES-GCM') throw new Error('Unsupported encryption');
  const key = await crypto.subtle.importKey('raw', bytes(encryption.key), 'AES-GCM', false, ['decrypt']);
  const plaintext = await crypto.subtle.decrypt({name:'AES-GCM', iv:bytes(puzzle.sealed.iv),
    additionalData:new TextEncoder().encode(puzzle.id)}, key, bytes(puzzle.sealed.ciphertext));
  const stream = new Blob([plaintext]).stream().pipeThrough(new DecompressionStream('deflate'));
  const result = JSON.parse(await new Response(stream).text());
  if (Array.from(result.word).length !== puzzle.images.length || !/^\p{Script=Han}+$/u.test(result.word) ||
      !Array.isArray(result.strokes) || result.strokes.length !== puzzle.images.length ||
      result.strokes.some(image=>!/^data:image\/(?:svg\+xml|png);base64,[A-Za-z0-9+/=]+$/.test(image))) throw new Error('Invalid decrypted content');
  return result;
}
