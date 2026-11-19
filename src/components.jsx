import { useEffect, useState } from 'react'
import { LEVEL_BADGE, STATUS_BADGE, STATUS_LABEL, fmtPct, thresholds } from './api.js'

const LEVEL_MARK = { good: '✓', warn: '!', bad: '✕', new: '·' }

// Цвет никогда не единственный носитель смысла: у бейджа уровня есть значок
export function LevelBadge({ level, label }) {
  return <span className={`badge ${LEVEL_BADGE[level] || 'badge-new'}`}><span aria-hidden="true">{LEVEL_MARK[level] || '·'}</span>{label}</span>
}

export function StatusBadge({ status }) {
  return <span className={`badge ${STATUS_BADGE[status] || 'badge-new'}`}>{STATUS_LABEL[status] || status}</span>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return (
    <div className="alert alert-danger">
      <strong>{error.message}</strong>
      {error.errors?.length > 0 && (
        <ul>{error.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
      )}
    </div>
  )
}

export function Warnings({ items }) {
  if (!items?.length) return null
  return (
    <div className="alert alert-warn">
      <strong>Предупреждения</strong>
      <ul>{items.map((w, i) => <li key={i}>{w}</li>)}</ul>
    </div>
  )
}

// Таблица «Сводка по разделам» — те же колонки, что на листе Excel
export function CategoryTable({ rows, total }) {
  if (!rows?.length) return <p className="muted">Нет данных</p>
  return (
    <table>
      <thead>
        <tr><th>Раздел</th><th>Всего</th><th>Есть</th><th>В работе</th><th>Нет</th><th>% готовности</th></tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.category}>
            <td>{r.category}</td><td>{r.total}</td><td>{r.done}</td><td>{r.in_progress}</td>
            <td>{r.missing + (r.not_set || 0)}</td>
            <td><Progress value={r.readiness} /></td>
          </tr>
        ))}
        {total && (
          <tr className="total-row">
            <td>ИТОГО</td><td>{total.total}</td><td>{total.done}</td><td>{total.in_progress}</td>
            <td>{total.missing + (total.not_set || 0)}</td>
            <td><Progress value={total.readiness} /></td>
          </tr>
        )}
      </tbody>
    </table>
  )
}

export function Progress({ value }) {
  const v = value ?? 0
  const cls = v >= thresholds.good ? 'ok' : v >= thresholds.warn ? 'warn' : 'danger'
  return (
    <div className="progress">
      <div className="progress-bar"><div className={`progress-fill ${cls}`} style={{ width: `${Math.min(v, 100)}%` }} /></div>
      <span>{fmtPct(value)}</span>
    </div>
  )
}

// Скелетон вместо текста «Загрузка…»
export function Skeleton({ lines = 4 }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: lines }, (_, i) => <i key={i} />)}
    </div>
  )
}

// Удаление в два шага прямо в строке вместо системного confirm()
export function ConfirmButton({ label = 'Удалить', confirmLabel = 'Удалить?', onConfirm }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 4000)
    return () => clearTimeout(t)
  }, [armed])
  if (!armed) return <button type="button" className="btn-small" onClick={() => setArmed(true)}>{label}</button>
  return (
    <span className="inline-edit">
      <button type="button" className="btn-small danger" onClick={() => { setArmed(false); onConfirm() }}>{confirmLabel}</button>
      <button type="button" className="btn-small" onClick={() => setArmed(false)}>Отмена</button>
    </span>
  )
}
