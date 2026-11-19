// Общие компоненты страниц «СОУТ» и «ОПР»: модальная форма, поля, предупреждения.
import { useEffect } from 'react'
import { fmtDate } from './api.js'

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Закрыть">×</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

export function Fieldset({ title, hint, children }) {
  return (
    <fieldset className="fs">
      <legend>{title}</legend>
      {hint && <p className="fs-hint">{hint}</p>}
      <div className="fs-grid">{children}</div>
    </fieldset>
  )
}

function Wrap({ label, hint, wide, children }) {
  return (
    <label className={`fld ${wide ? 'fld-wide' : ''}`}>
      <span className="fld-label">{label}</span>
      {children}
      {hint && <span className="fld-hint">{hint}</span>}
    </label>
  )
}

export function TextField({ form, set, name, label, hint, wide, placeholder }) {
  return (
    <Wrap label={label} hint={hint} wide={wide}>
      <input className="input" value={form[name] ?? ''} placeholder={placeholder}
             onChange={e => set(name, e.target.value)} />
    </Wrap>
  )
}

export function NumberField({ form, set, name, label, hint }) {
  return (
    <Wrap label={label} hint={hint}>
      <input className="input" type="number" min="0" step="1" value={form[name] ?? ''}
             onChange={e => set(name, e.target.value)} />
    </Wrap>
  )
}

export function DateField({ form, set, name, label, hint }) {
  return (
    <Wrap label={label} hint={hint}>
      <input className="input" type="date" value={form[name] ?? ''} onChange={e => set(name, e.target.value)} />
    </Wrap>
  )
}

export function SelectField({ form, set, name, label, options, hint, empty, wide }) {
  return (
    <Wrap label={label} hint={hint} wide={wide}>
      <select className="input" value={form[name] ?? ''} onChange={e => set(name, e.target.value)}>
        {empty !== undefined && <option value="">{empty}</option>}
        {Object.entries(options || {}).map(([k, v]) => (
          <option key={k} value={k}>{typeof v === 'string' ? v : v.label}</option>
        ))}
      </select>
    </Wrap>
  )
}

export function CheckField({ form, set, name, label, hint, wide }) {
  return (
    <label className={`fld fld-check ${wide ? 'fld-wide' : ''}`}>
      <span><input type="checkbox" checked={!!form[name]} onChange={e => set(name, e.target.checked)} /> {label}</span>
      {hint && <span className="fld-hint">{hint}</span>}
    </label>
  )
}

export function TextArea({ form, set, name, label }) {
  return (
    <Wrap label={label} wide>
      <textarea className="input" rows={3} value={form[name] ?? ''} onChange={e => set(name, e.target.value)} />
    </Wrap>
  )
}

// Значения формы -> тело запроса: пустые строки -> null, числа -> int
export function toBody(form, numberFields, boolFields = []) {
  const out = {}
  for (const [k, v] of Object.entries(form)) {
    if (boolFields.includes(k)) out[k] = !!v
    else if (numberFields.includes(k)) out[k] = v === '' || v == null ? null : parseInt(v, 10)
    else out[k] = v === '' || v == null ? null : v
  }
  return out
}

// Запись из API -> значения формы
export function toForm(record, fields) {
  const f = {}
  for (const k of fields) f[k] = record?.[k] ?? ''
  return f
}

export function addDays(iso, days) {
  if (!iso) return null
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export function addMonths(iso, months) {
  if (!iso) return null
  const [y, m, day] = iso.split('-').map(Number)
  const t = new Date(Date.UTC(y, m - 1 + months, 1))
  const last = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + 1, 0)).getUTCDate()
  t.setUTCDate(Math.min(day, last))
  return t.toISOString().slice(0, 10)
}

export function AlertList({ alerts, onOffice, showOffice }) {
  if (!alerts?.length) return <p className="lvl-good">✓ Замечаний нет</p>
  return (
    <ul className="alert-list">
      {alerts.map((a, i) => (
        <li key={i} className={`al al-${a.severity}`} onClick={onOffice ? () => onOffice(a) : undefined}
            style={onOffice ? { cursor: 'pointer' } : undefined}>
          <span className="al-icon">{a.severity === 'bad' ? '✕' : '!'}</span>
          <span className="al-text">
            {showOffice && <strong>{a.office_code}{a.kind ? ` · ${a.kind === 'sout' ? 'СОУТ' : 'ОПР'}` : ''}: </strong>}
            {a.text}
          </span>
          {a.due && <span className="al-due">{fmtDate(a.due)}</span>}
        </li>
      ))}
    </ul>
  )
}

export function StateCards({ items, counts, active, onPick }) {
  return (
    <div className="state-cards">
      {items.map(([key, label, level]) => (
        <button key={key} className={`state-card ${active === key ? 'active' : ''}`}
                onClick={() => onPick(active === key ? null : key)}>
          <span className={`state-card-val lvl-${level}`}>{counts?.[key] ?? 0}</span>
          <span className="state-card-label">{label}</span>
        </button>
      ))}
    </div>
  )
}
