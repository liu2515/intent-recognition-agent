async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `请求失败（${response.status}）`)
  return body
}

export function recognizeIntent(payload) {
  return request('/api/intents/recognize', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function subscribeTrace(threadId, userId, handlers = {}) {
  const source = new EventSource(
    `/api/intent-graph/traces/${encodeURIComponent(threadId)}/events?user_id=${encodeURIComponent(userId)}`,
  )
  source.addEventListener('trace', event => handlers.onTrace?.(JSON.parse(event.data)))
  source.addEventListener('complete', () => {
    handlers.onComplete?.()
    source.close()
  })
  source.addEventListener('error', event => {
    handlers.onError?.(event)
    source.close()
  })
  return source
}

export function resumeIntent(threadId, payload) {
  return request(`/api/intents/${encodeURIComponent(threadId)}/resume`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getGraphDefinition() {
  return request('/api/intent-graph/definition')
}

export function getKnowledgeRules() {
  return request('/api/knowledge/rules')
}

export function getKnowledgeCandidates() {
  return request('/api/knowledge/candidates')
}

export function getKnowledgeGraph(includeCandidates = true, userId = '', reconcileDeletions = true) {
  const query = new URLSearchParams({
    include_candidates: String(includeCandidates),
    reconcile_deletions: String(reconcileDeletions),
  })
  if (userId) query.set('user_id', userId)
  return request(`/api/knowledge/graph?${query.toString()}`)
}

export function approveKnowledgeCandidate(templateId, reviewer) {
  return request(`/api/knowledge/candidates/${encodeURIComponent(templateId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ reviewer }),
  })
}

export function rejectKnowledgeCandidate(templateId, reviewer, reason) {
  return request(`/api/knowledge/candidates/${encodeURIComponent(templateId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reviewer, reason }),
  })
}

export function deleteKnowledgeTemplate(templateId) {
  return request(`/api/knowledge/templates/${encodeURIComponent(templateId)}`, {
    method: 'DELETE',
  })
}

export function syncKnowledgeGraph() {
  return request('/api/knowledge/graph/sync', { method: 'POST' })
}

export function syncKnowledgeGraphDeletions() {
  return request('/api/knowledge/graph/sync-deletions', { method: 'POST' })
}
