const BASE = '/api'

async function j(method, path, body) {
  const opts = { method, headers: {} }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const r = await fetch(BASE + path, opts)
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}: ${(await r.text()).slice(0, 300)}`)
  return r.json()
}

export const api = {
  listIssues: (params = '') => j('GET', `/issues${params}`),
  getIssue: (id) => j('GET', `/issues/${id}`),
  setStatus: (id, status, dept) => j('POST', `/issues/${id}/status?status=${encodeURIComponent(status)}${dept ? `&dept=${encodeURIComponent(dept)}` : ''}`),
  fileComplaint: (form) => j('POST', '/complaints', form),
  getStatus: (id) => j('GET', `/status/${id}`),
  listComplaints: () => j('GET', '/complaints'),
  health: () => j('GET', '/health'),
}
