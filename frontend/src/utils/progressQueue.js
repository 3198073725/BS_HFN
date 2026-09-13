// Shared across mounted course pages; only one replay may run per user's key.
const running = new WeakMap()

export function readProgressQueue(storage, key) {
  let items
  try { items = JSON.parse(storage.getItem(key) || '[]') } catch { return [] }
  if (!Array.isArray(items)) return []
  const valid = items.filter((item) => item && typeof item === 'object')
  const normalized = valid.map((item) => ({ ...item, queue_id: item.queue_id || crypto.randomUUID() }))
  if (valid.some((item) => !item.queue_id)) storage.setItem(key, JSON.stringify(normalized))
  return normalized
}

export function appendProgress(storage, key, payload) {
  const items = [...readProgressQueue(storage, key), { ...payload, queue_id: crypto.randomUUID(), queued_at: Date.now() }]
  storage.setItem(key, JSON.stringify(items.slice(-200)))
  return Math.min(items.length, 200)
}

export function flushProgress(storage, key, send, isConnectionError) {
  let userRuns = running.get(storage)
  if (!userRuns) { userRuns = new Map(); running.set(storage, userRuns) }
  if (userRuns.has(key)) return userRuns.get(key)
  const operation = (async () => {
    let sent = 0
    while (true) {
      const item = readProgressQueue(storage, key)[0]
      if (!item) break
      try { await send(item); sent += 1 } catch (error) {
        if (!isConnectionError(error)) {
          storage.setItem(key, JSON.stringify(readProgressQueue(storage, key).filter((entry) => entry.queue_id !== item.queue_id)))
        }
        break
      }
      // Remove only the acknowledged item from the live queue, never a snapshot.
      storage.setItem(key, JSON.stringify(readProgressQueue(storage, key).filter((entry) => entry.queue_id !== item.queue_id)))
    }
    return sent
  })().finally(() => userRuns.delete(key))
  userRuns.set(key, operation)
  return operation
}
