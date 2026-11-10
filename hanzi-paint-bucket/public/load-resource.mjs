// Fetch bytes explicitly: a stalled font URL must not leave a pending FontFace forever.
export async function loadResource(url, onProgress = () => {}, timeoutMs = 45000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {signal: controller.signal});
    if (!response.ok) throw new Error('资源加载失败，请重试');
    const total = Number(response.headers.get('content-length')) || 0;
    const reader = response.body.getReader(), chunks = [];
    let loaded = 0;
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      chunks.push(value); loaded += value.length;
      if (total) onProgress(Math.min(0.99, loaded / total));
    }
    const result = new Uint8Array(loaded);
    let offset = 0;
    for (const chunk of chunks) {result.set(chunk, offset); offset += chunk.length;}
    onProgress(1);
    return result;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('下载超时，请重试');
    throw error;
  } finally {clearTimeout(timer);}
}

export async function loadJsonResource(compressedUrl, fallbackUrl, onProgress) {
  if (typeof DecompressionStream === 'undefined') {
    return JSON.parse(new TextDecoder().decode(await loadResource(fallbackUrl, onProgress)));
  }
  const bytes = await loadResource(compressedUrl, onProgress);
  // Hosts may set Content-Encoding: gzip, in which case fetch has already decoded it.
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return JSON.parse(new TextDecoder().decode(bytes));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(stream).text());
}
