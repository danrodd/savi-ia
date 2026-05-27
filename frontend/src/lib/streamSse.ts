export async function* readSseJson<T>(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<T, void, void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })

      let sepIdx: number
      // biome-ignore lint/suspicious/noAssignInExpressions: idiomatic SSE frame parsing
      while ((sepIdx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, sepIdx)
        buf = buf.slice(sepIdx + 2)
        const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
        if (!dataLine) continue
        const payload = dataLine.slice(6).trim()
        if (!payload) continue
        try {
          yield JSON.parse(payload) as T
        } catch {
          // malformed frame, skip
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
