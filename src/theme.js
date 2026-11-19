// Тема оформления: 'system' | 'dark' | 'light'. Выбор хранится в браузере
// (localStorage может быть недоступен — тогда просто не сохраняем).
const KEY = 'ot-theme'
const media = () => window.matchMedia?.('(prefers-color-scheme: light)')

export function getThemePref() {
  try { return localStorage.getItem(KEY) || 'system' } catch { return 'system' }
}

export function saveThemePref(pref) {
  try { localStorage.setItem(KEY, pref) } catch { /* без сохранения */ }
}

export function resolveTheme(pref) {
  if (pref === 'dark' || pref === 'light') return pref
  return media()?.matches ? 'light' : 'dark'
}

export function applyTheme(pref) {
  document.documentElement.dataset.theme = resolveTheme(pref)
}

export function watchSystemTheme(cb) {
  const m = media()
  if (!m) return undefined
  m.addEventListener('change', cb)
  return () => m.removeEventListener('change', cb)
}
