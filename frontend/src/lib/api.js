export class Unauthorized extends Error {}

const csrfToken = () =>
  document.cookie
    .split('; ')
    .find((c) => c.startsWith('csrftoken='))
    ?.split('=')[1] ?? ''

export async function api(url, { method = 'GET', body } = {}) {
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const json = await res.json().catch(() => ({}))
  if (res.status === 401 && url === '/api/pulse') throw new Unauthorized()
  if (!res.ok) throw Object.assign(new Error(json.error || `HTTP ${res.status}`), { status: res.status })
  return json
}
