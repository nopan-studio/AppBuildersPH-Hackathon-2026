const BASE = import.meta.env.VITE_API_BASE || ''

async function parse(response) {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return body
}

export async function getHealth(model) {
  const response = await fetch(
    `${BASE}/api/health?model=${encodeURIComponent(model)}`,
  )
  return parse(response)
}

export async function scan(files, { model, ocrTier, minConf }) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  form.append('model', model)
  form.append('ocr_tier', ocrTier)
  form.append('min_conf', String(minConf))
  const response = await fetch(`${BASE}/api/scan`, { method: 'POST', body: form })
  return parse(response)
}

export async function exportXlsx(results) {
  const response = await fetch(`${BASE}/api/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Export failed (${response.status})`)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  const filename = match ? match[1] : 'bookyp-results.xlsx'

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
