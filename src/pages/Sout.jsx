import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, fmtDate, fmtDaysLeft } from '../api.js'
import { ErrorBox, LevelBadge } from '../components.jsx'
import {
  AlertList, CheckField, DateField, Fieldset, Modal, NumberField, SelectField, StateCards,
  TextArea, TextField, addDays, addMonths, toBody, toForm,
} from '../registerParts.jsx'

const FIELDS = [
  'kind', 'procedure', 'status', 'reason', 'reason_date', 'due_date', 'contractor', 'contractor_reg_number',
  'commission_order', 'start_date', 'report_date', 'fgis_date', 'valid_until', 'workplaces_total',
  'workplaces_assessed', 'analogous_workplaces', 'employees_covered', 'class_1', 'class_2', 'class_3_1',
  'class_3_2', 'class_3_3', 'class_3_4', 'class_4', 'declaration_submitted', 'declaration_date',
  'declaration_number', 'declaration_terminated', 'familiarized_date', 'employees_familiarized',
  'published_date', 'measures_planned', 'measures_done', 'notes',
]
const NUMBERS = ['workplaces_total', 'workplaces_assessed', 'analogous_workplaces', 'employees_covered',
  'class_1', 'class_2', 'class_3_1', 'class_3_2', 'class_3_3', 'class_3_4', 'class_4',
  'employees_familiarized', 'measures_planned', 'measures_done']
const BOOLS = ['declaration_submitted', 'declaration_terminated']
const CLASS_FIELDS = [['class_1', '1'], ['class_2', '2'], ['class_3_1', '3.1'], ['class_3_2', '3.2'],
  ['class_3_3', '3.3'], ['class_3_4', '3.4'], ['class_4', '4']]

const STATE_ITEMS = [
  ['ok', 'Действует', 'good'], ['declared', 'Декларация', 'good'], ['expiring', 'Истекает', 'warn'],
  ['expired', 'Срок истёк', 'bad'], ['planned', 'Запланирована', 'warn'], ['none', 'Нет данных', 'new'],
]

// Цвет бейджа — по самому статусу; критичные замечания показывает колонка «Замечания»
const STATE_LEVEL = Object.fromEntries(STATE_ITEMS.map(([k, , l]) => [k, l]))

const EMPTY = { kind: 'planned', procedure: 'regular', status: 'completed' }

// Полоса по классам: 1–2 — допустимые, 3.1–3.2 — вредные, 3.3–4 — вредные высоких степеней и опасные
function ClassBar({ classes }) {
  if (!classes) return <span className="muted">—</span>
  const ok = classes.class_1 + classes.class_2
  const mid = classes.class_3_1 + classes.class_3_2
  const hi = classes.class_3_3 + classes.class_3_4 + classes.class_4
  const total = ok + mid + hi
  if (!total) return <span className="muted">не указаны</span>
  return (
    <div className="classbar" title={CLASS_FIELDS.map(([f, l]) => `${l}: ${classes[f]}`).join(' · ')}>
      <div className="dv-bar" style={{ height: 8 }}>
        {ok > 0 && <div className="dv-seg dv-done" style={{ flexGrow: ok, height: 8 }} />}
        {mid > 0 && <div className="dv-seg dv-progress" style={{ flexGrow: mid, height: 8 }} />}
        {hi > 0 && <div className="dv-seg dv-missing" style={{ flexGrow: hi, height: 8 }} />}
      </div>
      <span className="muted">1–2: {ok}{mid ? ` · 3.1–3.2: ${mid}` : ''}{hi ? ` · 3.3–4: ${hi}` : ''}</span>
    </div>
  )
}

function Coverage({ assessed, total }) {
  if (total == null && assessed == null) return <span className="muted">—</span>
  const pct = total ? Math.round((assessed || 0) * 100 / total) : null
  return (
    <div className="coverage">
      <span>{assessed ?? '—'} из {total ?? '—'}</span>
      {pct != null && <div className="progress-bar"><div className={`progress-fill ${pct >= 100 ? 'ok' : 'warn'}`} style={{ width: `${Math.min(pct, 100)}%` }} /></div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Форма
// ---------------------------------------------------------------------------
function SoutForm({ cfg, office, record, onClose, onSaved }) {
  const [form, setForm] = useState(() => record ? toForm(record, FIELDS) : { ...toForm(null, FIELDS), ...EMPTY })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const p = { form, set }

  const years = cfg?.sout_validity_years || 5
  const reasonInfo = cfg?.sout_reasons?.[form.reason]
  const autoValid = !form.valid_until && form.status === 'completed' && (form.fgis_date || form.report_date)
    ? addMonths(form.fgis_date || form.report_date, years * 12) : null
  const autoDue = form.kind === 'unplanned' && form.reason_date && !form.due_date && reasonInfo?.months
    ? addMonths(form.reason_date, reasonInfo.months) : null
  const deadline30 = addDays(form.report_date, 30)
  const classSum = CLASS_FIELDS.reduce((s, [f]) => s + (parseInt(form[f], 10) || 0), 0)
  const assessed = parseInt(form.workplaces_assessed, 10)

  const save = async () => {
    setBusy(true); setError(null)
    try {
      const body = toBody(form, NUMBERS, BOOLS)
      if (record) await api.updateRegister('sout', record.id, body)
      else await api.createRegister('sout', office, body)
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`${record ? 'Изменить' : 'Добавить'} СОУТ — офис ${office}`} onClose={onClose}
           footer={<>
             <button className="btn btn-secondary" onClick={onClose}>Отмена</button>
             <button className="btn" disabled={busy} onClick={save}>{busy ? 'Сохранение…' : 'Сохранить'}</button>
           </>}>
      <ErrorBox error={error} />
      <Fieldset title="Общие сведения">
        <SelectField {...p} name="kind" label="Вид" options={cfg?.sout_kinds} />
        <SelectField {...p} name="procedure" label="Порядок проведения" options={cfg?.sout_procedures}
                     hint="Упрощённый — для малого бизнеса по ПП РФ № 1830 (с 01.09.2026 — 55 видов деятельности)" />
        <SelectField {...p} name="status" label="Статус" options={cfg?.statuses} />
        {form.kind === 'unplanned' && <>
          <SelectField {...p} name="reason" label="Основание (ч. 1 ст. 17 426-ФЗ)" options={cfg?.sout_reasons} empty="— выберите —" wide />
          <DateField {...p} name="reason_date" label="Дата наступления основания" />
          <DateField {...p} name="due_date" label="Срок проведения"
                     hint={autoDue ? `По умолчанию: ${fmtDate(autoDue)} (${reasonInfo.months} мес.)` : 'Новые места — 12 мес., остальные основания — 6 мес.'} />
        </>}
      </Fieldset>

      <Fieldset title="Проведение и отчёт">
        <TextField {...p} name="contractor" label="Организация, проводившая СОУТ" wide
                   placeholder={form.procedure === 'simplified' ? 'не требуется при упрощённом порядке' : 'ООО «…»'} />
        <TextField {...p} name="contractor_reg_number" label="Рег. номер в реестре" />
        <TextField {...p} name="commission_order" label="Приказ о комиссии (№, дата)" />
        <DateField {...p} name="start_date" label="Дата начала" />
        <DateField {...p} name="report_date" label="Утверждение отчёта" hint="Обязательно для завершённой СОУТ" />
        <DateField {...p} name="fgis_date" label="Внесение сведений в ФГИС СОУТ" hint="От этой даты считается срок 5 лет" />
        <DateField {...p} name="valid_until" label="Действует до"
                   hint={autoValid ? `Если не заполнять: ${fmtDate(autoValid)}` : `${years} лет с даты ФГИС (или отчёта)`} />
      </Fieldset>

      <Fieldset title="Рабочие места">
        <NumberField {...p} name="workplaces_total" label="Всего рабочих мест в офисе" />
        <NumberField {...p} name="workplaces_assessed" label="Охвачено результатами СОУТ" hint="включая аналогичные" />
        <NumberField {...p} name="analogous_workplaces" label="Из них аналогичных" hint="замеры — на 20 %, но не менее 2" />
        <NumberField {...p} name="employees_covered" label="Работников на этих местах" />
      </Fieldset>

      <Fieldset title="Итоговые классы условий труда"
                hint={`Количество рабочих мест по итоговому классу. Сумма: ${classSum}${Number.isFinite(assessed) ? ` из ${assessed} охваченных` : ''}`}>
        {CLASS_FIELDS.map(([f, l]) => <NumberField key={f} {...p} name={f} label={`Класс ${l}`} />)}
      </Fieldset>

      <Fieldset title="Декларация соответствия" hint="Подаётся на места с оптимальными и допустимыми условиями (классы 1 и 2). Пока она действует и не наступили обстоятельства ч. 5 ст. 11, повторная СОУТ на этих местах не требуется.">
        <CheckField {...p} name="declaration_submitted" label="Декларация подана" />
        <DateField {...p} name="declaration_date" label="Дата регистрации" />
        <TextField {...p} name="declaration_number" label="Рег. номер декларации" />
        <CheckField {...p} name="declaration_terminated" label="Декларация прекращена" wide
                    hint="Несчастный случай, профзаболевание или нарушение на задекларированном месте — нужна внеплановая СОУТ" />
      </Fieldset>

      <Fieldset title="После утверждения отчёта" hint={deadline30 ? `Срок ознакомления работников и размещения на сайте: до ${fmtDate(deadline30)} (30 календарных дней)` : 'Ознакомление и размещение на сайте — в течение 30 дней с утверждения отчёта'}>
        <DateField {...p} name="familiarized_date" label="Ознакомление завершено" />
        <NumberField {...p} name="employees_familiarized" label="Ознакомлено работников" />
        <DateField {...p} name="published_date" label="Размещено на сайте" hint="если у работодателя есть сайт" />
        <NumberField {...p} name="measures_planned" label="Мероприятий по улучшению УТ" />
        <NumberField {...p} name="measures_done" label="Из них выполнено" />
      </Fieldset>

      <Fieldset title="Примечание"><TextArea {...p} name="notes" label="" /></Fieldset>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Карточка офиса
// ---------------------------------------------------------------------------
function OfficeDetail({ code, cfg, role, reloadKey, onEdit, onAdd, onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    setData(null)
    api.officeRegister('sout', code).then(setData).catch(setError)
  }, [code, reloadKey])

  const remove = async (r) => {
    if (!confirm(`Удалить запись СОУТ от ${fmtDate(r.report_date || r.due_date)}?`)) return
    try { await api.deleteRegister('sout', r.id); onChanged() } catch (e) { setError(e) }
  }

  if (error) return <ErrorBox error={error} />
  if (!data) return <p className="muted">Загрузка…</p>
  const c = data.current
  return (
    <div className="section">
      <div className="section-head">
        <h2>Офис {code}: СОУТ</h2>
        <button className="btn" onClick={onAdd}>+ Добавить СОУТ</button>
      </div>
      <h3 style={{ marginTop: 0 }}>Замечания и сроки</h3>
      <AlertList alerts={data.alerts} />

      {c && <>
        <h3>Действующие результаты</h3>
        <div className="kv-grid">
          <div><span className="muted">Вид / порядок</span>{c.kind_label} · {c.procedure_label}</div>
          <div><span className="muted">Оценщик</span>{c.contractor || '—'}{c.contractor_reg_number ? ` (№ ${c.contractor_reg_number})` : ''}</div>
          <div><span className="muted">Отчёт утверждён</span>{fmtDate(c.report_date)}</div>
          <div><span className="muted">Внесено в ФГИС</span>{fmtDate(c.fgis_date)}</div>
          <div><span className="muted">Действует до</span>{c.declared_indefinite ? 'декларация — без повторной СОУТ' : `${fmtDate(c.valid_until)} (${fmtDaysLeft(c.days_left)})`}</div>
          <div><span className="muted">Рабочие места</span><Coverage assessed={c.workplaces_assessed} total={c.workplaces_total} /></div>
          <div><span className="muted">Аналогичных / работников</span>{c.analogous_workplaces ?? '—'} / {c.employees_covered ?? '—'}</div>
          <div><span className="muted">Классы</span><ClassBar classes={c.classes} /></div>
          <div><span className="muted">Декларация</span>{c.declaration_submitted ? `подана${c.declaration_number ? ` № ${c.declaration_number}` : ''}${c.declaration_terminated ? ', прекращена' : ''}` : 'нет'}</div>
          <div><span className="muted">Ознакомление</span>{c.familiarized_date ? `${fmtDate(c.familiarized_date)}${c.employees_familiarized != null ? `, ${c.employees_familiarized} чел.` : ''}` : `не завершено (срок ${fmtDate(c.familiarization_deadline)})`}</div>
          <div><span className="muted">На сайте</span>{c.published_date ? fmtDate(c.published_date) : 'нет'}</div>
          <div><span className="muted">Мероприятия</span>{c.measures_planned != null ? `${c.measures_done ?? 0} из ${c.measures_planned}` : '—'}</div>
        </div>
        {c.notes && <p className="muted" style={{ marginTop: 8 }}>{c.notes}</p>}
      </>}

      <h3>История</h3>
      {data.records.length === 0 ? <p className="muted">Записей нет — добавьте сведения о проведённой или запланированной СОУТ.</p> : (
        <table>
          <thead><tr><th>Вид</th><th>Статус</th><th>Отчёт</th><th>Действует до / срок</th><th>Места</th><th>Классы</th><th></th></tr></thead>
          <tbody>
            {data.records.map(r => (
              <tr key={r.id}>
                <td>{r.kind_label}{r.reason_label ? <div className="muted">{r.reason_label}</div> : null}</td>
                <td>{r.status_label}{r.due_overdue && <div className="lvl-bad">просрочена</div>}</td>
                <td>{fmtDate(r.report_date)}</td>
                <td>{r.status === 'completed' ? fmtDate(r.valid_until) : fmtDate(r.due_date)}</td>
                <td>{r.workplaces_assessed ?? '—'} / {r.workplaces_total ?? '—'}</td>
                <td><ClassBar classes={r.classes} /></td>
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

// ---------------------------------------------------------------------------
export default function Sout({ cfg, role, focusCode, onChanged }) {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState(null)
  const [selected, setSelected] = useState(focusCode || null)
  const [modal, setModal] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(() => {
    api.registerSummary('sout').then(setSummary).catch(setError)
  }, [])
  useEffect(() => { load() }, [load, reloadKey])
  useEffect(() => { if (focusCode) setSelected(focusCode) }, [focusCode])

  const counts = useMemo(() => {
    const c = {}
    for (const s of summary || []) c[s.state] = (c[s.state] || 0) + 1
    return c
  }, [summary])
  const harmful = (summary || []).reduce((n, s) => n + (s.current?.harmful_workplaces || 0), 0)
  const rows = (summary || []).filter(s => !filter || s.state === filter)

  const changed = () => { setModal(null); setReloadKey(k => k + 1); onChanged?.() }

  return (
    <>
      <ErrorBox error={error} />
      <div className="section">
        <div className="section-head">
          <div>
            <h2>Специальная оценка условий труда</h2>
            <p className="muted">Плановая — не реже 1 раза в 5 лет (срок — от внесения сведений в ФГИС СОУТ). Нажмите на офис, чтобы увидеть детали и историю.</p>
          </div>
          {harmful > 0 && <span className="lvl-pill lvl-warn">! Мест с вредными условиями: {harmful}</span>}
        </div>
        <StateCards items={STATE_ITEMS} counts={counts} active={filter} onPick={setFilter} />
        {summary && summary.length === 0 && <p className="muted">Офисов пока нет. Создайте офис на странице «Офисы» или загрузите сводную таблицу.</p>}
        {rows.length > 0 && (
          <table className="reg-table">
            <thead><tr><th>Офис</th><th>Статус</th><th>Действует до</th><th>Рабочие места</th><th>Классы</th><th>Замечания</th><th></th></tr></thead>
            <tbody>
              {rows.map(s => {
                const c = s.current
                const bad = s.alerts.filter(a => a.severity === 'bad').length
                return (
                  <tr key={s.office_code} className={selected === s.office_code ? 'row-selected' : ''}
                      onClick={() => setSelected(s.office_code)}>
                    <td><strong>{s.office_code}</strong>{s.office_name !== s.office_code && <div className="muted">{s.office_name}</div>}</td>
                    <td><LevelBadge level={STATE_LEVEL[s.state] || s.level} label={s.state_label} /></td>
                    <td>{c ? (c.declared_indefinite ? <span className="muted">декларация</span> : <>{fmtDate(c.valid_until)}<div className={`muted ${c.days_left < 0 ? 'lvl-bad' : ''}`}>{fmtDaysLeft(c.days_left)}</div></>) : '—'}</td>
                    <td><Coverage assessed={c?.workplaces_assessed} total={c?.workplaces_total} /></td>
                    <td><ClassBar classes={c?.classes} /></td>
                    <td>{s.alerts.length ? <span className={bad ? 'lvl-bad' : 'lvl-warn'}>{bad ? '✕' : '!'} {s.alerts.length}</span> : <span className="lvl-good">✓</span>}</td>
                    <td className="actions" onClick={e => e.stopPropagation()}>
                      <button className="btn-small" onClick={() => setModal({ code: s.office_code })}>+ СОУТ</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <OfficeDetail code={selected} cfg={cfg} role={role} reloadKey={reloadKey} onChanged={changed}
                      onAdd={() => setModal({ code: selected })}
                      onEdit={(r) => setModal({ code: selected, record: r })} />
      )}

      {modal && <SoutForm cfg={cfg} office={modal.code} record={modal.record}
                          onClose={() => setModal(null)} onSaved={changed} />}
    </>
  )
}
