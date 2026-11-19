import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, fmtDate, fmtDaysLeft } from '../api.js'
import { ErrorBox, LevelBadge } from '../components.jsx'
import {
  AlertList, DateField, Fieldset, Modal, NumberField, SelectField, StateCards, TextArea, TextField,
  addMonths, toBody, toForm,
} from '../registerParts.jsx'

const FIELDS = [
  'kind', 'status', 'reason', 'performed_by', 'contractor', 'method', 'commission_order', 'assessment_date',
  'next_review_date', 'workplaces_total', 'workplaces_assessed', 'professions_assessed', 'hazards_identified',
  'risks_low', 'risks_medium', 'risks_high', 'plan_approved_date', 'measures_planned', 'measures_done',
  'employees_informed_date', 'notes',
]
const NUMBERS = ['workplaces_total', 'workplaces_assessed', 'professions_assessed', 'hazards_identified',
  'risks_low', 'risks_medium', 'risks_high', 'measures_planned', 'measures_done']
const STATE_ITEMS = [
  ['ok', 'Действует', 'good'], ['review_soon', 'Скоро пересмотр', 'warn'],
  ['review_overdue', 'Пересмотр просрочен', 'bad'], ['planned', 'Запланирована', 'warn'], ['none', 'Нет данных', 'new'],
]
const EMPTY = { kind: 'periodic', status: 'completed', performed_by: 'self', method: 'matrix' }

function RiskBar({ r }) {
  if (!r) return <span className="muted">—</span>
  const total = r.risks_low + r.risks_medium + r.risks_high
  if (!total) return <span className="muted">не указаны</span>
  return (
    <div className="classbar">
      <div className="dv-bar" style={{ height: 8 }}>
        {r.risks_low > 0 && <div className="dv-seg dv-done" style={{ flexGrow: r.risks_low, height: 8 }} />}
        {r.risks_medium > 0 && <div className="dv-seg dv-progress" style={{ flexGrow: r.risks_medium, height: 8 }} />}
        {r.risks_high > 0 && <div className="dv-seg dv-missing" style={{ flexGrow: r.risks_high, height: 8 }} />}
      </div>
      <span className="muted">низк. {r.risks_low} · средн. {r.risks_medium} · <span className={r.risks_high ? 'lvl-bad' : ''}>высок. {r.risks_high}</span></span>
    </div>
  )
}

function Measures({ planned, done }) {
  if (planned == null) return <span className="muted">—</span>
  const pct = planned ? Math.round((done || 0) * 100 / planned) : 100
  return (
    <div className="coverage">
      <span>{done ?? 0} из {planned}</span>
      <div className="progress-bar"><div className={`progress-fill ${pct >= 100 ? 'ok' : 'warn'}`} style={{ width: `${Math.min(pct, 100)}%` }} /></div>
    </div>
  )
}

function OprForm({ cfg, office, record, onClose, onSaved }) {
  const [form, setForm] = useState(() => record ? toForm(record, FIELDS) : { ...toForm(null, FIELDS), ...EMPTY })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const p = { form, set }
  const months = cfg?.opr_review_months || 12
  const autoReview = !form.next_review_date && form.status === 'completed' && form.assessment_date
    ? addMonths(form.assessment_date, months) : null
  const risksTotal = ['risks_low', 'risks_medium', 'risks_high'].reduce((s, k) => s + (parseInt(form[k], 10) || 0), 0)

  const save = async () => {
    setBusy(true); setError(null)
    try {
      const body = toBody(form, NUMBERS)
      if (record) await api.updateRegister('opr', record.id, body)
      else await api.createRegister('opr', office, body)
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`${record ? 'Изменить' : 'Добавить'} оценку профрисков — офис ${office}`} onClose={onClose}
           footer={<>
             <button className="btn btn-secondary" onClick={onClose}>Отмена</button>
             <button className="btn" disabled={busy} onClick={save}>{busy ? 'Сохранение…' : 'Сохранить'}</button>
           </>}>
      <ErrorBox error={error} />
      <Fieldset title="Общие сведения">
        <SelectField {...p} name="kind" label="Вид" options={cfg?.opr_kinds} />
        <SelectField {...p} name="status" label="Статус" options={cfg?.statuses} />
        <SelectField {...p} name="performed_by" label="Кем проводится" options={cfg?.opr_performers} />
        {form.performed_by === 'contractor' && <TextField {...p} name="contractor" label="Организация" wide />}
        <SelectField {...p} name="method" label="Метод оценки" options={cfg?.opr_methods} empty="— не указан —"
                     hint="Метод выбирает работодатель (приказ Минтруда № 776н)" />
        <TextField {...p} name="commission_order" label="Приказ о комиссии (№, дата)" />
        {form.kind === 'unplanned' && <TextField {...p} name="reason" label="Основание внеплановой оценки" wide
                                                 placeholder="новые рабочие места, изменение процесса, несчастный случай…" />}
      </Fieldset>

      <Fieldset title="Сроки" hint="Обязательная периодичность ОПР законом не установлена — её задаёт работодатель в положении о СУОТ / об управлении профрисками.">
        <DateField {...p} name="assessment_date" label="Результаты утверждены" hint="Обязательно для завершённой оценки" />
        <DateField {...p} name="next_review_date" label="Плановый пересмотр"
                   hint={autoReview ? `Если не заполнять: ${fmtDate(autoReview)} (+${months} мес.)` : `По умолчанию — через ${months} мес.`} />
        <DateField {...p} name="employees_informed_date" label="Работники ознакомлены" />
      </Fieldset>

      <Fieldset title="Охват">
        <NumberField {...p} name="workplaces_total" label="Всего рабочих мест" />
        <NumberField {...p} name="workplaces_assessed" label="Оценено рабочих мест" />
        <NumberField {...p} name="professions_assessed" label="Должностей / профессий" />
        <NumberField {...p} name="hazards_identified" label="Выявлено опасностей" hint="по перечню опасностей (прил. к № 776н)" />
      </Fieldset>

      <Fieldset title="Уровни рисков" hint={`Количество оценённых рисков по уровням. Всего: ${risksTotal}`}>
        <NumberField {...p} name="risks_low" label="Низкий" />
        <NumberField {...p} name="risks_medium" label="Средний (умеренный)" />
        <NumberField {...p} name="risks_high" label="Высокий" />
      </Fieldset>

      <Fieldset title="Меры по снижению рисков" hint="При средних и высоких рисках утверждается план мероприятий; иерархия мер — от исключения опасности до СИЗ.">
        <DateField {...p} name="plan_approved_date" label="План мероприятий утверждён" />
        <NumberField {...p} name="measures_planned" label="Мероприятий в плане" />
        <NumberField {...p} name="measures_done" label="Из них выполнено" />
      </Fieldset>

      <Fieldset title="Примечание"><TextArea {...p} name="notes" label="" /></Fieldset>
    </Modal>
  )
}

function OfficeDetail({ code, role, reloadKey, onEdit, onAdd, onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    setData(null)
    api.officeRegister('opr', code).then(setData).catch(setError)
  }, [code, reloadKey])

  const remove = async (r) => {
    if (!confirm(`Удалить запись ОПР от ${fmtDate(r.assessment_date)}?`)) return
    try { await api.deleteRegister('opr', r.id); onChanged() } catch (e) { setError(e) }
  }

  if (error) return <ErrorBox error={error} />
  if (!data) return <p className="muted">Загрузка…</p>
  const c = data.current
  return (
    <div className="section">
      <div className="section-head">
        <h2>Офис {code}: оценка профессиональных рисков</h2>
        <button className="btn" onClick={onAdd}>+ Добавить оценку</button>
      </div>
      <h3 style={{ marginTop: 0 }}>Замечания и сроки</h3>
      <AlertList alerts={data.alerts} />
      {c && <>
        <h3>Действующая оценка</h3>
        <div className="kv-grid">
          <div><span className="muted">Вид</span>{c.kind_label}</div>
          <div><span className="muted">Кем / метод</span>{c.performed_by === 'contractor' ? (c.contractor || 'сторонняя организация') : 'своими силами'}{c.method_label ? ` · ${c.method_label}` : ''}</div>
          <div><span className="muted">Утверждена</span>{fmtDate(c.assessment_date)}</div>
          <div><span className="muted">Пересмотр</span>{fmtDate(c.next_review_date)} ({fmtDaysLeft(c.days_to_review)})</div>
          <div><span className="muted">Рабочие места</span>{c.workplaces_assessed ?? '—'} из {c.workplaces_total ?? '—'}</div>
          <div><span className="muted">Должностей / опасностей</span>{c.professions_assessed ?? '—'} / {c.hazards_identified ?? '—'}</div>
          <div><span className="muted">Риски</span><RiskBar r={c} /></div>
          <div><span className="muted">План мероприятий</span>{c.plan_approved_date ? `утверждён ${fmtDate(c.plan_approved_date)}` : 'не утверждён'}</div>
          <div><span className="muted">Выполнение</span><Measures planned={c.measures_planned} done={c.measures_done} /></div>
          <div><span className="muted">Ознакомление</span>{c.employees_informed_date ? fmtDate(c.employees_informed_date) : 'нет'}</div>
        </div>
        {c.notes && <p className="muted" style={{ marginTop: 8 }}>{c.notes}</p>}
      </>}
      <h3>История</h3>
      {data.records.length === 0 ? <p className="muted">Записей нет — добавьте сведения об оценке профрисков.</p> : (
        <table>
          <thead><tr><th>Вид</th><th>Статус</th><th>Утверждена</th><th>Пересмотр</th><th>Риски</th><th>Мероприятия</th><th></th></tr></thead>
          <tbody>
            {data.records.map(r => (
              <tr key={r.id}>
                <td>{r.kind_label}</td>
                <td>{r.status_label}</td>
                <td>{fmtDate(r.assessment_date)}</td>
                <td>{fmtDate(r.next_review_date)}</td>
                <td><RiskBar r={r} /></td>
                <td><Measures planned={r.measures_planned} done={r.measures_done} /></td>
                <td className="actions">
                  <button className="btn-small" onClick={() => onEdit(r)}>Изменить</button>
                  {role === 'super' && <button className="btn-small" onClick={() => remove(r)}>Удалить</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function Opr({ cfg, role, focusCode, onChanged }) {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState(null)
  const [selected, setSelected] = useState(focusCode || null)
  const [modal, setModal] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(() => { api.registerSummary('opr').then(setSummary).catch(setError) }, [])
  useEffect(() => { load() }, [load, reloadKey])
  useEffect(() => { if (focusCode) setSelected(focusCode) }, [focusCode])

  const counts = useMemo(() => {
    const c = {}
    for (const s of summary || []) c[s.state] = (c[s.state] || 0) + 1
    return c
  }, [summary])
  const high = (summary || []).reduce((n, s) => n + (s.current?.risks_high || 0), 0)
  const rows = (summary || []).filter(s => !filter || s.state === filter)
  const changed = () => { setModal(null); setReloadKey(k => k + 1); onChanged?.() }

  return (
    <>
      <ErrorBox error={error} />
      <div className="section">
        <div className="section-head">
          <div>
            <h2>Оценка профессиональных рисков</h2>
            <p className="muted">Периодичность пересмотра задаёт работодатель; по умолчанию портал напоминает через {cfg?.opr_review_months || 12} мес. Нажмите на офис, чтобы увидеть детали.</p>
          </div>
          {high > 0 && <span className="lvl-pill lvl-bad">✕ Высоких рисков: {high}</span>}
        </div>
        <StateCards items={STATE_ITEMS} counts={counts} active={filter} onPick={setFilter} />
        {rows.length > 0 && (
          <table className="reg-table">
            <thead><tr><th>Офис</th><th>Статус</th><th>Утверждена</th><th>Пересмотр</th><th>Риски</th><th>Мероприятия</th><th>Замечания</th><th></th></tr></thead>
            <tbody>
              {rows.map(s => {
                const c = s.current
                const bad = s.alerts.filter(a => a.severity === 'bad').length
                return (
                  <tr key={s.office_code} className={selected === s.office_code ? 'row-selected' : ''}
                      onClick={() => setSelected(s.office_code)}>
                    <td><strong>{s.office_code}</strong>{s.office_name !== s.office_code && <div className="muted">{s.office_name}</div>}</td>
                    <td><LevelBadge level={s.level} label={s.state_label} /></td>
                    <td>{fmtDate(c?.assessment_date)}</td>
                    <td>{c ? <>{fmtDate(c.next_review_date)}<div className={`muted ${c.days_to_review < 0 ? 'lvl-bad' : ''}`}>{fmtDaysLeft(c.days_to_review)}</div></> : '—'}</td>
                    <td><RiskBar r={c} /></td>
                    <td><Measures planned={c?.measures_planned} done={c?.measures_done} /></td>
                    <td>{s.alerts.length ? <span className={bad ? 'lvl-bad' : 'lvl-warn'}>{bad ? '✕' : '!'} {s.alerts.length}</span> : <span className="lvl-good">✓</span>}</td>
                    <td className="actions" onClick={e => e.stopPropagation()}>
                      <button className="btn-small" onClick={() => setModal({ code: s.office_code })}>+ ОПР</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      {selected && (
        <OfficeDetail code={selected} role={role} reloadKey={reloadKey} onChanged={changed}
                      onAdd={() => setModal({ code: selected })}
                      onEdit={(r) => setModal({ code: selected, record: r })} />
      )}
      {modal && <OprForm cfg={cfg} office={modal.code} record={modal.record}
                         onClose={() => setModal(null)} onSaved={changed} />}
    </>
  )
}
