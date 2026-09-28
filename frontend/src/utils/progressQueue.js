// Shared across mounted course pages; only one replay may run per user's key.
const running = new WeakMap()

function locked(name, action) {
  // Web Locks coordinate same-origin tabs without expiring a lock mid-request.
  if (globalThis.navigator?.locks) return navigator.locks.request(name, action)
  return Promise.resolve().then(action)
}

export function readProgressQueue(storage, key) {
  let items
  try { items = JSON.parse(storage.getItem(key) || '[]') } catch { return [] }
  if (!Array.isArray(items)) return []
  const valid = items.filter((item) => item && typeof item === 'object')
  const normalized = valid.map((item) => ({ ...item, queue_id: item.queue_id || crypto.randomUUID() }))
  // Reading UI state must never write a stale snapshot. Legacy IDs are persisted
  // only inside the short queue mutation lock, before any record is sent.
  return normalized
}

export function appendProgress(storage, key, payload) {
  return locked(`progress:mutate:${key}`, () => {
    const id = payload.request_id || crypto.randomUUID()
    const items = [...readProgressQueue(storage, key), { ...payload, request_id: id, queue_id: id, queued_at: Date.now() }]
    // Do not silently discard unacknowledged learning when the queue exceeds 200.
    // A storage quota failure rejects without replacing the previous queue.
    storage.setItem(key, JSON.stringify(items))
    return items.length
  })
}

export function flushProgress(storage, key, send, isConnectionError, onDiscard = () => {}) {
  let userRuns = running.get(storage)
  if (!userRuns) { userRuns = new Map(); running.set(storage, userRuns) }
  if (userRuns.has(key)) return userRuns.get(key)
  const operation = locked(`progress:replay:${key}`, async () => {
    let sent = 0
    const attempted = new Set()
    while (true) {
      const item = await locked(`progress:mutate:${key}`, () => {
        const items = readProgressQueue(storage, key).map((entry) => ({ ...entry, request_id: entry.request_id || entry.queue_id }))
        if (items.length) storage.setItem(key, JSON.stringify(items))
        return items.find((entry) => !attempted.has(entry.queue_id))
      })
      if (!item) break
      attempted.add(item.queue_id)
      try { await send(item); sent += 1 } catch (error) {
        // Unknown/server failures are recoverable. Discard only explicit permanent
        // failures; a 401 may recover after login, and a 409 may be a write race.
        const status = Number(error?.status || error?.code || error?.response?.status)
        if (!isConnectionError(error) && [400, 403, 404, 410, 422].includes(status)) {
          await locked(`progress:mutate:${key}`, () => storage.setItem(key, JSON.stringify(readProgressQueue(storage, key).filter((entry) => entry.queue_id !== item.queue_id))))
          onDiscard(item, error)
          continue
        }
        // Temporarily unavailable media stay queued without blocking other videos.
        // Each item is attempted once per replay, then the page retries with backoff.
        if (status === 423 && !isConnectionError(error)) continue
        break
      }
      // Remove only the acknowledged item from the live queue, never a snapshot.
      await locked(`progress:mutate:${key}`, () => storage.setItem(key, JSON.stringify(readProgressQueue(storage, key).filter((entry) => entry.queue_id !== item.queue_id))))
    }
    return sent
  }).finally(() => userRuns.delete(key))
  userRuns.set(key, operation)
  return operation
}
