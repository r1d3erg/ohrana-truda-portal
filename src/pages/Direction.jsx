// Страница направления с ручным вводом: «Пожарная безопасность», «Электробезопасность», «ГО и ЧС».
// Поля формы и правила сроков приходят с бэкенда (/api/directions/<kind>/spec) — см. backend/app/directions.py.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, fmtDate, fmtDateTime, fmtDaysLeft } from '../api.js'
import { ErrorBox, LevelBadge, Skeleton } from '../components.jsx'
import { Icon } from '../icons.jsx'
import { AlertList, CheckField, DateField, Fieldset, Modal, NumberField, SelectField, StateCards, TextArea, TextField } from '../registerParts.jsx'

const STATE_ITEMS = [
  ['ok', 'В норме', 'good'],
  ['soon', 'Скоро срок', 'warn'],
  ['attention', 'Требует внимания', 'warn'],
  ['overdue', 'Просрочено', 'bad'],
  ['none', 'Нет данных', 'new'],
]

function sections(fields) {
  const out = []
  for (const f of fields) {
    let s = out.find(x => x.title === f.section)
    if (!s) { s = { title: f.section, fields: [] }; out.push(s) }
    s.fields.push(f)
  }
  return out
}

function DirectionForm({ spec, code, data, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    const f = {}
    for (const fld of spec.fields) f[fld.key] = data?.[fld.key] ?? (fld.type === 'bool' ? false : '')
    return f
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const save = async () => {
    setBusy(true)
    setError(null)
    const body = {}
    for (const fld of spec.fields) {
      const v = form[fld.key]
      if (fld.type === 'bool') body[fld.key] = !!v
      else if (fld.type === 'int') body[fld.key] = v === '' || v == null ? null : parseInt(v, 10)
      else body[fld.key] = v === '' ? null : v
    }
    try {
      await api.saveDirection(spec.kind, code, body)
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const field = (f) => {
    const p = { form, set, name: f.key, label: f.label, hint: f.hint }
    if (f.type === 'date') return <DateField key={f.key} {...p} />
    if (f.type === 'int') return <NumberField key={f.key} {...p} />
    if (f.type === 'bool') return <CheckField key={f.key} {...p} wide />
    if (f.type === 'enum') return <SelectField key={f.key} {...p} options={f.options} empty="— не выбрано —" wide />
    if (f.type === 'textarea') return <TextArea key={f.key} {...p} />
    return <TextField key={f.key} {...p} wide={f.wide} />
  }

  return (
    <Modal title={`${spec.title}: офис ${code}`} onClose={onClose}
           footer={<>
             <button className="btn btn-secondary" onClick={onClose}>Отмена</button>
             <button className="btn" disabled={busy} onClick={save}>{busy ? 'Сохранение…' : 'Сохранить'}</button>
           </>}>
      <ErrorBox error={error} />
      {sections(spec.fields).map(s => (
        <Fieldset key={s.title} title={s.title}>{s.fields.map(field)}</Fieldset>
      ))}
    </Modal>
  )
}

function fmtValue(f, v) {
  if (v == null || v === '') return '—'
  if (f.type === 'date') return fmtDate(v)
  if (f.type === 'bool') return v ? 'Да' : 'Нет'
  if (f.type === 'enum') return f.options?.[v] ?? v
  return String(v)
}

function OfficeCard({ spec, code, reloadKey, onEdit, onOpenGuide, editable }) {
  const [st, setSt] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    setSt(null)
    api.officeDirection(spec.kind, code).then(setSt).catch(setError)
  }, [spec.kind, code, reloadKey])

  if (error) return <ErrorBox error={error} />
  if (!st) return <div className="section"><Skeleton lines={5} /></div>
  return (
    <div className="section">
      <div className="section-head">
        <div>
          <h2>Офис {code}: {spec.title.toLowerCase()}</h2>
          <p className="muted">{st.updated_at ? `Обновлено ${fmtDateTime(st.updated_at)}` : 'Данные ещё не вносились'}</p>
        </div>
        <div className="upload-row">
          <button className="btn btn-secondary" onClick={onOpenGuide}><Icon name="book-open" size={20} /> Что делать</button>
          {editable && <button className="btn" onClick={onEdit}><Icon name="pencil-simple" size={20} /> {st.data ? 'Изменить' : 'Заполнить'}</button>}
        </div>
      </div>
      <div className="two-col">
        <div>
          <h3>Замечания</h3>
          <AlertList alerts={st.alerts} />
          {st.deadlines.length > 0 && (
            <>
              <h3 className="mt-24">Сроки</h3>
              <table>
                <thead><tr><th>Что</th><th>Срок</th><th></th></tr></thead>
                <tbody>
                  {st.deadlines.map(d => (
                    <tr key={d.label}>
                      <td>{d.label}</td>
                      <td>{fmtDate(d.date)}</td>
                      <td className={d.days_left < 0 ? 'lvl-bad' : d.days_left <= spec.warn_days ? 'lvl-warn' : 'muted'}>{fmtDaysLeft(d.days_left)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
        <div>
          <h3>Данные</h3>
          {st.data ? (
            <div className="kv-list">
              {spec.fields.filter(f => f.type !== 'textarea' || st.data[f.key]).map(f => (
                <div key={f.key} className="kv-row">
                  <span className="muted">{f.label}</span>
                  <span>{fmtValue(f, st.data[f.key])}</span>
                </div>
              ))}
            </div>
          ) : <p className="muted">Нажмите «Заполнить», чтобы внести данные по офису.</p>}
        </div>
      </div>
    </div>
  )
}

export default function Direction({ kind, focusCode, onChanged, onOpenGuide, canEdit = () => true }) {
  const [spec, setSpec] = useState(null)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState(null)
  const [selected, setSelected] = useState(focusCode || null)
  const [modal, setModal] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(() => {
    Promise.all([api.directionSpec(kind), api.directionSummary(kind)])
      .then(([s, sum]) => { setSpec(s); setSummary(sum); setError(null) })
      .catch(setError)
  }, [kind])
  useEffect(() => { load() }, [load, reloadKey])
  useEffect(() => { setSelected(focusCode || null); setFilter(null) }, [kind, focusCode])

  const counts = useMemo(() => {
    const c = {}
    for (const s of summary || []) c[s.state] = (c[s.state] || 0) + 1
    return c
  }, [summary])
  const rows = (summary || []).filter(s => !filter || s.state === filter)

  const changed = () => { setModal(null); setReloadKey(k => k + 1); onChanged?.() }

  if (error) return <ErrorBox error={error} />
  if (!spec || !summary) return <div className="section"><Skeleton lines={6} /></div>

  return (
    <>
      <div className="section">
        <div className="section-head">
          <div>
            <h2>{spec.title} по офисам</h2>
            <p className="muted">Данные вносит ответственный офиса вручную (свои офисы) или служба охраны труда. Портал считает сроки и подсвечивает просрочки; всё это попадает в дашборд. Нажмите на офис, чтобы увидеть детали.</p>
          </div>
          <button className="btn btn-secondary" onClick={() => onOpenGuide(spec.guide)}><Icon name="book-open" size={20} /> Что делать по инструкции</button>
        </div>
        <StateCards items={STATE_ITEMS} counts={counts} active={filter} onPick={setFilter} />
        {summary.length === 0 && <p className="muted">Офисов пока нет. Создайте офис на странице «Офисы» или загрузите сводную таблицу.</p>}
        {rows.length > 0 && (
          <table className="reg-table">
            <thead><tr><th>Офис</th><th>Статус</th><th>Ближайший срок</th><th>Замечания</th><th>Обновлено</th><th></th></tr></thead>
            <tbody>
              {rows.map(s => {
                const bad = s.alerts.filter(a => a.severity === 'bad').length
                const nd = s.next_due
                return (
                  <tr key={s.office_code} className={selected === s.office_code ? 'row-selected' : ''}
                      onClick={() => setSelected(s.office_code)}>
                    <td><strong>{s.office_code}</strong>{s.office_name !== s.office_code && <div className="muted">{s.office_name}</div>}</td>
                    <td><LevelBadge level={s.level} label={s.state_label} /></td>
                    <td>{nd ? <>{nd.label}<div className={`muted ${nd.days_left < 0 ? 'lvl-bad' : ''}`}>{fmtDate(nd.date)} · {fmtDaysLeft(nd.days_left)}</div></> : '—'}</td>
                    <td>{s.alerts.length ? <span className={bad ? 'lvl-bad' : 'lvl-warn'}>{bad ? '✕' : '!'} {s.alerts.length}</span> : <span className="lvl-good">✓</span>}</td>
                    <td className="muted">{s.updated_at ? fmtDate(s.updated_at.slice(0, 10)) : '—'}</td>
                    <td className="actions" onClick={e => e.stopPropagation()}>
                      {canEdit(s.office_code) && <button className="btn-small" onClick={() => setModal({ code: s.office_code, data: s.data })}>{s.data ? 'Изменить' : 'Заполнить'}</button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <OfficeCard spec={spec} code={selected} reloadKey={reloadKey} editable={canEdit(selected)}
                    onEdit={() => setModal({ code: selected, data: summary.find(s => s.office_code === selected)?.data })}
                    onOpenGuide={() => onOpenGuide(spec.guide)} />
      )}

      {modal && <DirectionForm spec={spec} code={modal.code} data={modal.data}
                               onClose={() => setModal(null)} onSaved={changed} />}
    </>
  )
}
