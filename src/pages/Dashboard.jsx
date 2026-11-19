import { LEVEL_COLOR, fmtDateTime, fmtPct } from '../api.js'
import { CategoryTable } from '../components.jsx'

export default function Dashboard({ data, onOpenOffices }) {
  if (!data) return <div className="section"><p className="muted">Загрузка…</p></div>
  const d = data.documents
  return (
    <>
      <div className="cards">
        <div className="card">
          <div className="card-title">Индекс соответствия (средний)</div>
          <div className={`card-value ${LEVEL_COLOR[data.avg_level]}`}>{fmtPct(data.avg_readiness)}</div>
        </div>
        <div className="card clickable" onClick={onOpenOffices}>
          <div className="card-title">Офисов</div>
          <div className="card-value">{data.offices_total}</div>
          <div className="card-sub">с данными: {data.offices_with_data}</div>
        </div>
        <div className="card">
          <div className="card-title">Документов «В работе»</div>
          <div className={`card-value ${d.in_progress ? 'warning' : ''}`}>{d.in_progress}</div>
        </div>
        <div className="card">
          <div className="card-title">Документов «Нет»</div>
          <div className={`card-value ${d.missing + d.not_set ? 'danger' : ''}`}>{d.missing + d.not_set}</div>
        </div>
      </div>

      <div className="cards">
        <div className="card"><div className="card-title">Офисов «Хорошо»</div><div className="card-value success">{data.levels.good}</div></div>
        <div className="card"><div className="card-title">«Требует внимания»</div><div className="card-value warning">{data.levels.warn}</div></div>
        <div className="card"><div className="card-title">«Критично»</div><div className="card-value danger">{data.levels.bad}</div></div>
        <div className="card"><div className="card-title">Без данных</div><div className="card-value">{data.levels.new}</div></div>
      </div>

      <div className="section">
        <h2>Сводка по разделам — все офисы</h2>
        <CategoryTable rows={data.by_category} total={data.offices_with_data ? d : null} />
        <p className="muted" style={{ marginTop: 12 }}>Последняя загрузка: {fmtDateTime(data.last_uploaded_at)}</p>
      </div>
    </>
  )
}
