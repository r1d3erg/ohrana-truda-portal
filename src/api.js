// Клиент API бэкенда. Все запросы идут на тот же домен (/api):
// в разработке их проксирует Vite, в Docker — nginx.

export class ApiError extends Error {
  constructor(status, message, errors = []) {
    super(message)
    this.status = status
    this.errors = errors
  }
}

// Заголовок защиты от CSRF: бэкенд принимает изменяющие запросы только с ним (docs/auth.md)
const CSRF = { 'X-Requested-With': 'ot-portal' }

// Подписка на «сессия истекла» (401) — App показывает экран входа
let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      ...options,
      headers: { ...CSRF, ...(options.headers || {}) },
    })
  } catch {
    throw new ApiError(0, 'Бэкенд недоступен — проверьте, что сервер запущен')
  }
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { /* не JSON */ }
  if (!res.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail : detail?.message || `Ошибка сервера (${res.status})`
    if (res.status === 401 && !path.startsWith('/auth/')) onUnauthorized()
    throw new ApiError(res.status, message, Array.isArray(detail?.errors) ? detail.errors : [])
  }
  return data
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  // Вход и пользователи
  me: () => request('/auth/me'),
  login: (login, password) => request('/auth/login', json('POST', { login, password })),
  logout: () => request('/auth/logout', { method: 'POST' }),
  changePassword: (current_password, new_password) => request('/auth/password', json('POST', { current_password, new_password })),
  roles: () => request('/roles'),
  users: () => request('/users'),
  createUser: (body) => request('/users', json('POST', body)),
  updateUser: (id, body) => request(`/users/${id}`, json('PATCH', body)),
  config: () => request('/config'),
  dashboard: () => request('/dashboard'),
  offices: () => request('/offices'),
  office: (code) => request(`/offices/${encodeURIComponent(code)}`),
  createOffice: (body) => request('/offices', json('POST', body)),
  updateOffice: (code, body) => request(`/offices/${encodeURIComponent(code)}`, json('PATCH', body)),
  checklist: (code, params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request(`/offices/${encodeURIComponent(code)}/checklist${qs ? `?${qs}` : ''}`)
  },
  officeImports: (code) => request(`/offices/${encodeURIComponent(code)}/imports`),
  deleteImport: (id) => request(`/imports/${id}`, { method: 'DELETE' }),
  // СОУТ и ОПР (kind = 'sout' | 'opr')
  registerSummary: (kind) => request(`/${kind}`),
  officeRegister: (kind, code) => request(`/offices/${encodeURIComponent(code)}/${kind}`),
  createRegister: (kind, code, body) => request(`/offices/${encodeURIComponent(code)}/${kind}`, json('POST', body)),
  updateRegister: (kind, id, body) => request(`/${kind}/${id}`, json('PUT', body)),
  deleteRegister: (kind, id) => request(`/${kind}/${id}`, { method: 'DELETE' }),
  // Пожарная безопасность, электробезопасность, ГО и ЧС (kind = 'fire' | 'electro' | 'go')
  directionSpec: (kind) => request(`/directions/${kind}/spec`),
  directionSummary: (kind) => request(`/directions/${kind}`),
  officeDirection: (kind, code) => request(`/offices/${encodeURIComponent(code)}/directions/${kind}`),
  saveDirection: (kind, code, body) => request(`/offices/${encodeURIComponent(code)}/directions/${kind}`, json('PUT', body)),
  uploadChecklist: (file, { dryRun = false } = {}) => {
    const form = new FormData()
    form.append('file', file)
    return request(`/imports${dryRun ? '?dry_run=true' : ''}`, { method: 'POST', body: form })
  },
}

// --- Подписи и цвета, общие для страниц -------------------------------------
// Пороги приходят из /api/config (переменные READINESS_GOOD / READINESS_WARN бэкенда)
export const thresholds = { good: 90, warn: 70 }
export const setThresholds = (cfg) => {
  if (cfg?.readiness_good != null) thresholds.good = cfg.readiness_good
  if (cfg?.readiness_warn != null) thresholds.warn = cfg.readiness_warn
}
export const LEVEL_BADGE = { good: 'badge-ok', warn: 'badge-warn', bad: 'badge-danger', new: 'badge-new' }
export const LEVEL_COLOR = { good: 'success', warn: 'warning', bad: 'danger', new: '' }
export const STATUS_BADGE = { done: 'badge-ok', in_progress: 'badge-warn', missing: 'badge-danger', not_set: 'badge-new' }
export const STATUS_LABEL = { done: 'Есть', in_progress: 'В работе', missing: 'Нет', not_set: 'Не указан' }

export const fmtDate = (iso) => {
  if (!iso) return '—'
  // Дата без времени («2026-08-17») — без пересчёта часового пояса
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : new Date(iso).toLocaleDateString('ru-RU')
}
export const fmtDateTime = (iso) => (iso ? new Date(iso).toLocaleString('ru-RU') : '—')
export const fmtPct = (v) => (v == null ? '—' : `${v}%`)

export const daysWord = (n) => {
  const a = Math.abs(n) % 100, b = a % 10
  if (a > 10 && a < 20) return 'дней'
  if (b === 1) return 'день'
  if (b >= 2 && b <= 4) return 'дня'
  return 'дней'
}
export const fmtDaysLeft = (n) => {
  if (n == null) return ''
  if (n < 0) return `просрочено на ${-n} ${daysWord(n)}`
  if (n === 0) return 'сегодня'
  return `через ${n} ${daysWord(n)}`
}

// Короткие подписи реестров для списков предупреждений
export const REGISTER_LABEL = { sout: 'СОУТ', opr: 'ОПР', fire: 'ПБ', electro: 'ЭБ', go: 'ГО ЧС' }
