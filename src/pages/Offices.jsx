import { useState } from 'react'
import { api, fmtDate } from '../api.js'
import { ErrorBox, LevelBadge, Progress } from '../components.jsx'

export default function Offices({ offices, role, onChanged, onOpenDocuments }) {
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ code: '', name: '', responsible: '' })
  const [error, setError] = useState(null)

  const createOffice = async () => {
    setError(null)
    if (!form.code.trim()) return setError({ message: 'Укажите номер офиса (как в шапке таблицы, напр. cy1)' })
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

  const assign = async (office) => {
    const name = prompt(`Назначить ответственного для «${office.name}»:`, office.responsible || '')
    if (name === null) return
    try {
      await api.updateOffice(office.code, { responsible: name.trim() || null })
      onChanged()
    } catch (e) {
      setError(e)
    }
  }

  const field = (key, label, placeholder) => (
    <div>
      <label className="field-label">{label}</label><br />
      <input className="input" value={form[key]} placeholder={placeholder}
             onChange={e => setForm({ ...form, [key]: e.target.value })} />
    </div>
  )

  return (
    <>
      <ErrorBox error={error} />
      {role === 'super' && (
        <div className="section">
          <button className="btn" onClick={() => setShowCreate(!showCreate)}>+ Создать офис</button>
          {showCreate && (
            <div className="form-row">
              {field('code', 'Номер офиса', 'cy1')}
              {field('name', 'Название', 'Лимассол, офис 1')}
              {field('responsible', 'Ответственный', 'Иванов И.И.')}
              <button className="btn" onClick={createOffice}>Создать</button>
            </div>
          )}
          <p className="muted" style={{ marginTop: 12 }}>
            Офис также создаётся автоматически при первой загрузке сводной таблицы с новым номером офиса.
          </p>
        </div>
      )}
      <div className="section">
        <h2>Офисы</h2>
        {offices.length === 0 ? (
          <p className="muted">Офисов пока нет. Загрузите сводную таблицу в разделе «Документы».</p>
        ) : (
          <table>
            <thead>
              <tr><th>Офис</th><th>Ответственный</th><th>Индекс</th><th>Дата проверки</th><th>Статус</th><th>Действия</th></tr>
            </thead>
            <tbody>
              {offices.map(o => (
                <tr key={o.code}>
                  <td><strong>{o.code}</strong>{o.name !== o.code && <div className="muted">{o.name}</div>}</td>
                  <td>{o.responsible || '—'}</td>
                  <td>{o.readiness == null ? '—' : <Progress value={o.readiness} />}</td>
                  <td>{fmtDate(o.check_date)}</td>
                  <td><LevelBadge level={o.level} label={o.level_label} /></td>
                  <td className="actions">
                    <button className="btn-small" onClick={() => onOpenDocuments(o.code)}>Документы</button>
                    {role === 'super' && <button className="btn-small" onClick={() => assign(o)}>Назначить</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
