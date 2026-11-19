import { useState } from 'react'
import { api, fmtDate } from '../api.js'
import { ErrorBox, LevelBadge, Progress } from '../components.jsx'
import { Icon } from '../icons.jsx'

// Назначение ответственного — правка прямо в строке таблицы (без системного prompt())
function ResponsibleCell({ office, canEdit, onSave }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(office.responsible || '')
  const [busy, setBusy] = useState(false)

  if (!editing) {
    return (
      <span className="inline-edit">
        {office.responsible || <span className="muted">не назначен</span>}
        {canEdit && (
          <button type="button" className="btn-small" aria-label={`Назначить ответственного для ${office.code}`}
                  onClick={() => { setValue(office.responsible || ''); setEditing(true) }}>
            <Icon name="pencil-simple" size={12} />
          </button>
        )}
      </span>
    )
  }
  const save = async () => {
    setBusy(true)
    const ok = await onSave(value.trim() || null)
    setBusy(false)
    if (ok) setEditing(false)
  }
  return (
    <span className="inline-edit">
      <input className="input" autoFocus value={value} placeholder="Фамилия И.О."
             onChange={e => setValue(e.target.value)}
             onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }} />
      <button type="button" className="btn-small" disabled={busy} onClick={save}>Сохранить</button>
      <button type="button" className="btn-small" onClick={() => setEditing(false)}>Отмена</button>
    </span>
  )
}

export default function Offices({ offices, role, onChanged, onOpenDocuments }) {
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ code: '', name: '', responsible: '' })
  const [error, setError] = useState(null)

  const createOffice = async () => {
    setError(null)
    if (!form.code.trim()) return setError({ message: 'Укажите номер офиса так же, как в шапке таблицы, например cy1' })
    try {
      await api.createOffice({
        code: form.code.trim(),
        name: form.name.trim() || null,
        responsible: form.responsible.trim() || null,
      })
      setForm({ code: '', name: '', responsible: '' })
      setShowCreate(false)
      onChanged()
    } catch (e) {
      setError(e)
    }
  }

  const saveResponsible = async (office, responsible) => {
    try {
      await api.updateOffice(office.code, { responsible })
      onChanged()
      return true
    } catch (e) {
      setError(e)
      return false
    }
  }

  const field = (key, label, placeholder) => (
    <div>
      <label className="field-label" htmlFor={`office-${key}`}>{label}</label>
      <input id={`office-${key}`} className="input" value={form[key]} placeholder={placeholder}
             onChange={e => setForm({ ...form, [key]: e.target.value })} />
    </div>
  )

  return (
    <>
      <ErrorBox error={error} />
      {role === 'super' && (
        <section className="section">
          <div className="section-head">
            <div>
              <h2>Новый офис</h2>
              <p className="muted">Офис также создаётся сам при первой загрузке сводной таблицы с новым номером офиса.</p>
            </div>
            {!showCreate && <button className="btn" onClick={() => setShowCreate(true)}><Icon name="plus" size={20} /> Создать офис</button>}
          </div>
          {showCreate && (
            <div className="form-row">
              {field('code', 'Номер офиса', 'cy1')}
              {field('name', 'Название', 'Лимассол, офис 1')}
              {field('responsible', 'Ответственный', 'Иванов И.И.')}
              <button className="btn" onClick={createOffice}>Создать офис</button>
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Отмена</button>
            </div>
          )}
        </section>
      )}
      <section className="section">
        <h2>Офисы</h2>
        {offices.length === 0 ? (
          <div className="empty-state">
            <h2>Офисов пока нет</h2>
            <p>Загрузите сводную таблицу в разделе «Документы»: офис появится автоматически по номеру из шапки.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Офис</th><th>Ответственный</th><th>Индекс</th><th>Дата проверки</th><th>Статус</th><th></th></tr>
              </thead>
              <tbody>
                {offices.map(o => (
                  <tr key={o.code}>
                    <td><strong>{o.code}</strong>{o.name !== o.code && <div className="muted">{o.name}</div>}</td>
                    <td><ResponsibleCell office={o} canEdit={role === 'super'} onSave={(v) => saveResponsible(o, v)} /></td>
                    <td>{o.readiness == null ? '—' : <Progress value={o.readiness} />}</td>
                    <td>{fmtDate(o.check_date)}</td>
                    <td><LevelBadge level={o.level} label={o.level_label} /></td>
                    <td className="actions">
                      <button className="btn-small" onClick={() => onOpenDocuments(o.code)}>Открыть документы</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
