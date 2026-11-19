import { useEffect, useRef, useState } from 'react'
import { STATUS_LABEL, api, fmtDate, fmtDateTime } from '../api.js'
import { CategoryTable, ConfirmButton, ErrorBox, LevelBadge, Progress, Skeleton, StatusBadge, Warnings } from '../components.jsx'
import { Icon } from '../icons.jsx'

// ---------------------------------------------------------------------------
// Загрузка сводной таблицы
// ---------------------------------------------------------------------------
function UploadSection({ onUploaded }) {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const send = async (dryRun) => {
    if (!file) return setError({ message: 'Выберите файл .xlsx' })
    setBusy(true); setError(null); setResult(null)
    try {
      const res = await api.uploadChecklist(file, { dryRun })
      setResult(res)
      if (res.result === 'created') {
        setFile(null)
        if (inputRef.current) inputRef.current.value = ''
        onUploaded(res.office.code)
      }
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="section">
      <h2>Загрузка сводной таблицы</h2>
      <p className="muted mb-12">
        Файл Excel (.xlsx) по шаблону «Чек-лист обязательных документов». Офис определяется по полю
        «Номер офиса» в шапке; если такого офиса нет — он будет создан.
      </p>
      <div className="upload-row">
        <input ref={inputRef} className="input" type="file" accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
               onChange={e => { setFile(e.target.files[0] || null); setResult(null); setError(null) }} />
        <button className="btn btn-secondary" disabled={busy || !file} onClick={() => send(true)}>Проверить</button>
        <button className="btn" disabled={busy || !file} onClick={() => send(false)}><Icon name="upload-simple" size={20} />{busy ? 'Обработка…' : 'Загрузить'}</button>
      </div>
      <ErrorBox error={error} />
      {result && <UploadResult result={result} />}
    </div>
  )
}

function UploadResult({ result }) {
  const imp = result.import || {}
  const cls = result.result === 'created' ? 'alert-ok' : result.result === 'duplicate' ? 'alert-warn' : 'alert-info'
  const ch = result.changes
  return (
    <div className="mt-16">
      <div className={`alert ${cls}`}>
        <strong>{result.message}</strong>
        <div className="muted">
          Офис: <strong>{result.office.code}</strong>
          {result.result === 'preview' && (result.office.exists ? ' (существует)' : ' (будет создан)')}
          {' · '}дата проверки: {fmtDate(imp.check_date)}
          {imp.inspector && <> · проверил: {imp.inspector}</>}
          {imp.headcount != null && <> · численность: {imp.headcount}</>}
        </div>
        {result.result === 'created' && result.is_current === false && (
          <div>Файл сохранён в истории, но актуальной осталась более поздняя проверка.</div>
        )}
      </div>
      <Warnings items={result.warnings} />
      <CategoryTable rows={result.by_category} total={result.summary} />
      {ch?.has_previous && (
        <div className="mt-16">
          <h3>Изменения относительно предыдущей проверки</h3>
          {ch.changed.length === 0 && !ch.added.length && !ch.removed.length ? (
            <p className="muted">Статусы документов не изменились.</p>
          ) : (
            <>
              <p className="muted">Улучшилось: {ch.improved} · ухудшилось: {ch.worsened}
                {ch.added.length > 0 && <> · новых позиций: {ch.added.length}</>}
                {ch.removed.length > 0 && <> · исключено позиций: {ch.removed.length}</>}
              </p>
              {ch.changed.length > 0 && (
                <table>
                  <thead><tr><th>№</th><th>Документ</th><th>Было</th><th>Стало</th></tr></thead>
                  <tbody>
                    {ch.changed.map(c => (
                      <tr key={c.number} className={c.direction === 'worse' ? 'row-worse' : ''}>
                        <td>{c.number}</td><td>{c.title}</td>
                        <td><StatusBadge status={c.from} /></td><td><StatusBadge status={c.to} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Документы выбранного офиса
// ---------------------------------------------------------------------------
function OfficeChecklist({ offices, code, onSelect, role, reloadKey, onChanged, focus }) {
  const [card, setCard] = useState(null)
  const [items, setItems] = useState([])
  const [history, setHistory] = useState([])
  const [filters, setFilters] = useState({
    status: focus?.status || '', category: focus?.category || '', q: focus?.q || '',
  })
  const [error, setError] = useState(null)
  const sectionRef = useRef(null)
  const checklistRef = useRef(null)

  // Переход с дашборда: выставить фильтр и прокрутить к чек-листу,
  // когда данные офиса загрузятся (ждём появления блока до 3 с)
  useEffect(() => {
    if (!focus) return
    setFilters({ status: focus.status || '', category: focus.category || '', q: focus.q || '' })
    let tries = 0
    const timer = setInterval(() => {
      const el = checklistRef.current
      if (el || ++tries > 30) {
        clearInterval(timer)
        ;(el || sectionRef.current)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }, 100)
    return () => clearInterval(timer)
  }, [focus?.nonce])

  useEffect(() => {
    if (!code) return
    setError(null)
    Promise.all([api.office(code), api.officeImports(code)])
      .then(([c, h]) => { setCard(c); setHistory(h) })
      .catch(setError)
  }, [code, reloadKey])

  useEffect(() => {
    if (!code) return
    const t = setTimeout(() => {
      api.checklist(code, filters).then(r => setItems(r.items)).catch(setError)
    }, filters.q ? 250 : 0)
    return () => clearTimeout(t)
  }, [code, filters, reloadKey])

  const removeImport = async (h) => {
    try {
      await api.deleteImport(h.id)
      onChanged()
    } catch (e) {
      setError(e)
    }
  }

  const categories = card?.by_category?.map(c => c.category) || []
  let lastGroup = null
  let lastSub = null

  return (
    <div className="section" ref={sectionRef}>
      <div className="section-head">
        <h2>Документы офиса</h2>
        <select className="input" value={code || ''} onChange={e => onSelect(e.target.value || null)}>
          <option value="">— выберите офис —</option>
          {offices.map(o => <option key={o.code} value={o.code}>{o.code}{o.name !== o.code ? ` — ${o.name}` : ''}</option>)}
        </select>
      </div>
      <ErrorBox error={error} />
      {!code && <p className="muted">Выберите офис, чтобы посмотреть его документы.</p>}

      {code && card && !card.current_import && (
        <p className="muted">По офису «{code}» ещё не загружено ни одной сводной таблицы.</p>
      )}

      {code && card?.current_import && (
        <>
          <div className="office-meta">
            <div><span className="muted">Индекс</span><Progress value={card.readiness} /></div>
            <div><span className="muted">Статус</span><LevelBadge level={card.level} label={card.level_label} /></div>
            <div><span className="muted">Дата проверки</span>{fmtDate(card.check_date)}</div>
            <div><span className="muted">Проверил</span>{card.current_import.inspector || '—'}</div>
            <div><span className="muted">Численность</span>{card.current_import.headcount ?? '—'}</div>
            <div><span className="muted">Номер редди</span>{card.current_import.reddy_number || '—'}</div>
            <div><span className="muted">Статус МСП</span>{card.current_import.msp_status || '—'}</div>
          </div>

          <h3>Сводка по разделам</h3>
          <CategoryTable rows={card.by_category} total={{ ...card.counts, readiness: card.readiness }} />

          <h3 className="mt-24" style={{ scrollMarginTop: 16 }} ref={checklistRef}>Чек-лист</h3>
          <div className="upload-row mb-12">
            <select className="input" value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}>
              <option value="">Все статусы</option>
              {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select className="input" value={filters.category} onChange={e => setFilters({ ...filters, category: e.target.value })}>
              <option value="">Все разделы</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <input className="input" placeholder="Поиск по наименованию" value={filters.q}
                   onChange={e => setFilters({ ...filters, q: e.target.value })} />
          </div>
          <table>
            <thead><tr><th>№</th><th>Документ</th><th>Статус</th><th>Комментарий</th><th>Ответственный</th><th>Дата</th></tr></thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={6} className="muted">Ничего не найдено</td></tr>}
              {items.flatMap(i => {
                const rows = []
                if (i.group !== lastGroup) {
                  rows.push(<tr key={`g-${i.id}`} className="group-row"><td colSpan={6}>{i.group || i.category}</td></tr>)
                  lastGroup = i.group; lastSub = null
                }
                if (i.subgroup && i.subgroup !== lastSub) {
                  rows.push(<tr key={`s-${i.id}`} className="subgroup-row"><td colSpan={6}>▸ {i.subgroup}</td></tr>)
                  lastSub = i.subgroup
                }
                rows.push(
                  <tr key={i.id}>
                    <td>{i.number}</td>
                    <td>{i.title}</td>
                    <td><StatusBadge status={i.status} /></td>
                    <td>{i.comment || ''}</td>
                    <td>{i.responsible || ''}</td>
                    <td>{i.date ? fmtDate(i.date) : i.date_raw || ''}</td>
                  </tr>
                )
                return rows
              })}
            </tbody>
          </table>
        </>
      )}

      {code && history.length > 0 && (
        <>
          <h3 className="mt-24">История загрузок</h3>
          <table>
            <thead><tr><th>Дата проверки</th><th>Загружено</th><th>Файл</th><th>Проверил</th><th>Готовность</th><th></th></tr></thead>
            <tbody>
              {history.map(h => (
                <tr key={h.id}>
                  <td>{fmtDate(h.check_date)} {h.is_current && <span className="badge badge-ok">актуальная</span>}</td>
                  <td>{fmtDateTime(h.uploaded_at)}</td>
                  <td>{h.filename || '—'}</td>
                  <td>{h.inspector || '—'}</td>
                  <td><Progress value={h.readiness} /></td>
                  <td>{role === 'super' && <ConfirmButton confirmLabel="Удалить загрузку" onConfirm={() => removeImport(h)} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

export default function Documents({ offices, role, selectedCode, onSelect, onChanged, focus }) {
  const [reloadKey, setReloadKey] = useState(0)
  const changed = () => { setReloadKey(k => k + 1); onChanged() }
  return (
    <>
      <UploadSection onUploaded={(code) => { onSelect(code); changed() }} />
      <OfficeChecklist offices={offices} code={selectedCode} onSelect={onSelect} role={role}
                       reloadKey={reloadKey} onChanged={changed} focus={focus} />
    </>
  )
}
