import { useMemo, useState } from 'react'
import { fmtDate, fmtDateTime, fmtPct } from '../api.js'
import { CategoryTable, Skeleton } from '../components.jsx'
import { AlertList } from '../registerParts.jsx'

// Цвета состояний (статусная палитра): цвет никогда не единственный носитель смысла —
// рядом всегда число и подпись.
const LEVEL_TEXT = { good: 'Хорошо', warn: 'Требует внимания', bad: 'Критично', new: 'Нет данных' }
const LEVEL_ICON = { good: '✓', warn: '!', bad: '✕', new: '·' }

// ---------------------------------------------------------------------------
// Всплывающая подсказка
// ---------------------------------------------------------------------------
function useTooltip() {
  const [tip, setTip] = useState(null)
  const bind = (content) => ({
    onMouseEnter: (e) => setTip({ x: e.clientX, y: e.clientY, content }),
    onMouseMove: (e) => setTip({ x: e.clientX, y: e.clientY, content }),
    onMouseLeave: () => setTip(null),
  })
  const node = tip && (
    <div className="dv-tooltip" style={{
      left: Math.min(tip.x + 14, window.innerWidth - 270),
      top: Math.min(tip.y + 14, window.innerHeight - 170),
    }}>{tip.content}</div>
  )
  return [bind, node]
}

function TipRows({ title, rows }) {
  return (
    <>
      <div className="dv-tooltip-title">{title}</div>
      {rows.map(([k, v, cls]) => (
        <div key={k} className="dv-tooltip-row">
          {cls && <span className={`dv-swatch ${cls}`} />}<span>{k}</span><strong>{v}</strong>
        </div>
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Составная полоса «Есть / В работе / Нет»
// ---------------------------------------------------------------------------
function StatusBar({ done, inProgress, missing, height = 10, bind, title }) {
  const total = done + inProgress + missing
  if (!total) return <div className="dv-bar dv-bar-empty" style={{ height }} />
  const seg = (v, cls) => v > 0 && (
    <div className={`dv-seg ${cls}`} style={{ flexGrow: v, height }} />
  )
  return (
    <div className="dv-bar" style={{ height }}
         {...(bind ? bind(<TipRows title={title} rows={[
           ['Есть', `${done} · ${fmtPct(Math.round(done * 1000 / total) / 10)}`, 'dv-done'],
           ['В работе', inProgress, 'dv-progress'],
           ['Нет', missing, 'dv-missing'],
           ['Всего', total],
         ]} />) : {})}>
      {seg(done, 'dv-done')}
      {seg(inProgress, 'dv-progress')}
      {seg(missing, 'dv-missing')}
    </div>
  )
}

function StatusLegend() {
  return (
    <div className="dv-legend">
      <span><i className="dv-swatch dv-done" />Есть</span>
      <span><i className="dv-swatch dv-progress" />В работе</span>
      <span><i className="dv-swatch dv-missing" />Нет</span>
    </div>
  )
}

function Delta({ value }) {
  if (value == null) return null
  if (value === 0) return <span className="dv-delta">±0</span>
  return (
    <span className={`dv-delta ${value > 0 ? 'up' : 'down'}`}>
      {value > 0 ? '▲' : '▼'} {Math.abs(value)}
    </span>
  )
}

// ---------------------------------------------------------------------------
// KPI
// ---------------------------------------------------------------------------
function Kpis({ data, onOpenOffices }) {
  const d = data.documents
  const missing = d.missing + d.not_set
  const lv = data.levels
  const officesTotal = data.offices_total || 1
  return (
    <div className="kpi-grid">
      <div className="kpi">
        <div className="kpi-label">Индекс соответствия</div>
        <div className="kpi-row">
          <span className={`kpi-value lvl-${data.avg_level}`}>{fmtPct(data.avg_readiness)}</span>
          {data.avg_readiness != null && (
            <span className={`lvl-pill lvl-${data.avg_level}`}>{LEVEL_ICON[data.avg_level]} {LEVEL_TEXT[data.avg_level]}</span>
          )}
        </div>
        <div className="kpi-gauge">
          <div className={`kpi-gauge-fill lvl-bg-${data.avg_level}`} style={{ width: `${data.avg_readiness || 0}%` }} />
          <i style={{ left: `${data.thresholds.warn}%` }} title={`Порог «Требует внимания»: ${data.thresholds.warn}%`} />
          <i style={{ left: `${data.thresholds.good}%` }} title={`Порог «Хорошо»: ${data.thresholds.good}%`} />
        </div>
        <div className="kpi-sub">среднее по {data.offices_with_data} офис(ам) с данными</div>
      </div>

      <div className="kpi clickable" onClick={onOpenOffices}>
        <div className="kpi-label">Офисы</div>
        <div className="kpi-row"><span className="kpi-value">{data.offices_total}</span></div>
        <div className="dv-bar" style={{ height: 8 }}>
          {['good', 'warn', 'bad', 'new'].map(k => lv[k] > 0 && (
            <div key={k} className={`dv-seg lvl-bg-${k}`} style={{ flexGrow: lv[k] / officesTotal, height: 8 }} />
          ))}
        </div>
        <div className="kpi-levels">
          <span className="lvl-good">✓ {lv.good}</span>
          <span className="lvl-warn">! {lv.warn}</span>
          <span className="lvl-bad">✕ {lv.bad}</span>
          <span className="muted">· {lv.new} без данных</span>
        </div>
      </div>

      <div className="kpi">
        <div className="kpi-label">Документы по чек-листам</div>
        <div className="kpi-row"><span className="kpi-value">{d.total}</span><span className="muted">позиций</span></div>
        <StatusBar done={d.done} inProgress={d.in_progress} missing={missing} height={8} />
        <div className="kpi-levels">
          <span className="lvl-good">Есть {d.done}</span>
          <span className="lvl-warn">В работе {d.in_progress}</span>
          <span className="lvl-bad">Нет {missing}</span>
        </div>
      </div>

      <div className="kpi">
        <div className="kpi-label">Проседающие направления</div>
        <div className="kpi-row">
          <span className={`kpi-value ${data.weak_spots_total ? 'lvl-bad' : 'lvl-good'}`}>{data.weak_spots_total}</span>
          <span className="muted">офис × направление ниже {data.thresholds.good}%</span>
        </div>
        <div className="kpi-sub">Последняя загрузка: {fmtDateTime(data.last_uploaded_at)}</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Тепловая карта «офис × направление»
// ---------------------------------------------------------------------------
// Направления с ручным вводом (ПБ, ЭБ, ГО ЧС) — backend/app/directions.py
const DIRS = ['fire', 'electro', 'go']

function Heatmap({ data, onDrill, bind, onOpenRegister }) {
  const reg = data.registers
  const [sortKey, setSortKey] = useState('readiness')
  const [onlyProblems, setOnlyProblems] = useState(false)
  const [metric, setMetric] = useState('pct')
  const cats = data.categories
  const good = data.thresholds.good

  const rows = useMemo(() => {
    let r = [...data.matrix]
    if (onlyProblems) r = r.filter(m => Object.values(m.cells).some(c => c.readiness < good))
    if (sortKey === 'code') r.sort((a, b) => a.code.localeCompare(b.code, 'ru', { numeric: true }))
    else if (sortKey.startsWith('cat:')) {
      const cat = sortKey.slice(4)
      const v = (m) => m.cells[cat]?.readiness ?? 101
      r.sort((a, b) => v(a) - v(b) || a.readiness - b.readiness)
    } else r.sort((a, b) => a.readiness - b.readiness || a.code.localeCompare(b.code))
    return r
  }, [data.matrix, sortKey, onlyProblems, good])

  const catInfo = Object.fromEntries(data.by_category.map(c => [c.category, c]))

  return (
    <div className="section">
      <div className="section-head">
        <div>
          <h2>Где проседает: офисы × направления</h2>
          <p className="muted">Клик по ячейке — документы офиса по этому направлению. Клик по заголовку направления — сортировка по нему.</p>
        </div>
        <div className="dv-controls">
          <div className="seg-control">
            <button className={metric === 'pct' ? 'active' : ''} onClick={() => setMetric('pct')}>% готовности</button>
            <button className={metric === 'missing' ? 'active' : ''} onClick={() => setMetric('missing')}>Нет, шт.</button>
          </div>
          <select className="input" value={sortKey.startsWith('cat:') ? 'cat' : sortKey}
                  onChange={e => setSortKey(e.target.value)}>
            <option value="readiness">Сначала проблемные</option>
            <option value="code">По номеру офиса</option>
            {sortKey.startsWith('cat:') && <option value="cat">По «{sortKey.slice(4)}»</option>}
          </select>
          <label className="check"><input type="checkbox" checked={onlyProblems} onChange={e => setOnlyProblems(e.target.checked)} /> только с проблемами</label>
        </div>
      </div>

      <div className="heatmap-wrap">
        <table className="heatmap">
          <thead>
            <tr>
              <th className="hm-office">Офис</th>
              <th className="hm-total">Индекс</th>
              <th className="hm-reg">СОУТ</th>
              <th className="hm-reg">ОПР</th>
              {DIRS.map(k => <th key={k} className="hm-reg">{reg?.directions?.[k]?.short || k}</th>)}
              {cats.map(c => {
                const info = catInfo[c]
                return (
                  <th key={c} className={`hm-cat ${sortKey === `cat:${c}` ? 'sorted' : ''}`}
                      onClick={() => setSortKey(`cat:${c}`)}
                      {...bind(<TipRows title={c} rows={[
                        ['Готовность (все офисы)', fmtPct(info?.readiness)],
                        ['Средняя по офисам', fmtPct(info?.offices_avg)],
                        ['Офисов ниже нормы', `${info?.offices_below_good ?? 0} из ${info?.offices ?? 0}`],
                      ]} />)}>
                    <div className="hm-cat-name">{c}</div>
                    <div className={`hm-cat-avg lvl-${info?.level}`}>{fmtPct(info?.readiness)}</div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={cats.length + 4 + DIRS.length} className="muted">Нет офисов, подходящих под фильтр</td></tr>
            )}
            {rows.map(m => (
              <tr key={m.code}>
                <td className="hm-office" onClick={() => onDrill({ code: m.code })}>
                  <div className="hm-office-code">{m.code}</div>
                  {m.name !== m.code && <div className="muted">{m.name}</div>}
                  <div className="muted">проверка {fmtDate(m.check_date)}</div>
                </td>
                <td className="hm-total">
                  <div className={`hm-total-val lvl-${m.level}`}>{fmtPct(m.readiness)}</div>
                  <Delta value={m.delta} />
                </td>
                <RegCell info={reg?.sout?.by_office?.[m.code]} date={reg?.sout?.by_office?.[m.code]?.valid_until}
                         onClick={() => onOpenRegister('sout', m.code)} bind={bind} title={`${m.code} · СОУТ`} />
                <RegCell info={reg?.opr?.by_office?.[m.code]} date={reg?.opr?.by_office?.[m.code]?.next_review_date}
                         onClick={() => onOpenRegister('opr', m.code)} bind={bind} title={`${m.code} · ОПР`} />
                {DIRS.map(k => {
                  const info = reg?.directions?.[k]?.by_office?.[m.code]
                  return <RegCell key={k} info={info} date={info?.next_due}
                                  onClick={() => onOpenRegister(k, m.code)} bind={bind}
                                  title={`${m.code} · ${reg?.directions?.[k]?.title || k}`} />
                })}
                {cats.map(c => {
                  const cell = m.cells[c]
                  if (!cell) return <td key={c} className="hm-cell hm-none">—</td>
                  const miss = cell.missing + cell.not_set
                  return (
                    <td key={c} className={`hm-cell lvl-tint-${cell.level}`}
                        onClick={() => onDrill({ code: m.code, category: c })}
                        {...bind(<TipRows title={`${m.code} · ${c}`} rows={[
                          ['Готовность', fmtPct(cell.readiness)],
                          ['Есть', cell.done, 'dv-done'],
                          ['В работе', cell.in_progress, 'dv-progress'],
                          ['Нет', miss, 'dv-missing'],
                          ['Всего позиций', cell.total],
                        ]} />)}>
                      <div className="hm-cell-main">
                        {metric === 'pct' ? fmtPct(cell.readiness) : miss}
                      </div>
                      <div className="hm-cell-sub">
                        {metric === 'pct'
                          ? (miss ? `нет ${miss}` : cell.in_progress ? `в работе ${cell.in_progress}` : `${cell.done}/${cell.total}`)
                          : `из ${cell.total}`}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="dv-legend">
        <span><i className="dv-swatch lvl-bg-good" />✓ ≥ {data.thresholds.good}% — хорошо</span>
        <span><i className="dv-swatch lvl-bg-warn" />! {data.thresholds.warn}–{data.thresholds.good}% — требует внимания</span>
        <span><i className="dv-swatch lvl-bg-bad" />✕ &lt; {data.thresholds.warn}% — критично</span>
        <span>— нет позиций</span>
      </div>
    </div>
  )
}

function RegCell({ info, date, onClick, bind, title }) {
  const level = info?.level || 'new'
  return (
    <td className={`hm-cell hm-reg-cell lvl-tint-${level}`} onClick={onClick}
        {...bind(<TipRows title={title} rows={[['Статус', info?.state_label || 'Нет данных'], ['Срок', fmtDate(date)]]} />)}>
      <div className="hm-reg-label">{LEVEL_ICON[level]} {info?.state_label || 'Нет данных'}</div>
      {date && <div className="hm-cell-sub">{fmtDate(date)}</div>}
    </td>
  )
}

// ---------------------------------------------------------------------------
// СОУТ и ОПР: состояния и ближайшие сроки
// ---------------------------------------------------------------------------
function RegistersBlock({ reg, onOpenRegister }) {
  if (!reg) return null
  const s = reg.sout.counts
  const o = reg.opr.counts
  const Item = ({ v, label, cls }) => <div className="reg-kpi-item"><span className={`reg-kpi-val ${cls}`}>{v}</span><span className="muted">{label}</span></div>
  return (
    <div className="two-col">
      <div className="section">
        <div className="section-head"><h2>Оценки и направления по офисам</h2></div>
        <div className="reg-kpi" onClick={() => onOpenRegister('sout')}>
          <div className="reg-kpi-title">СОУТ</div>
          <Item v={s.ok + s.declared} label="действует" cls="lvl-good" />
          <Item v={s.expiring} label="истекает" cls="lvl-warn" />
          <Item v={s.expired} label="истекла" cls="lvl-bad" />
          <Item v={s.none + s.planned} label="нет данных" cls="lvl-new" />
          <Item v={reg.sout.harmful_workplaces} label="мест с вредными УТ" cls={reg.sout.harmful_workplaces ? 'lvl-warn' : 'lvl-new'} />
        </div>
        <div className="reg-kpi" onClick={() => onOpenRegister('opr')}>
          <div className="reg-kpi-title">ОПР</div>
          <Item v={o.ok} label="действует" cls="lvl-good" />
          <Item v={o.review_soon} label="скоро пересмотр" cls="lvl-warn" />
          <Item v={o.review_overdue} label="просрочен" cls="lvl-bad" />
          <Item v={o.none + o.planned} label="нет данных" cls="lvl-new" />
          <Item v={reg.opr.high_risks} label="высоких рисков" cls={reg.opr.high_risks ? 'lvl-bad' : 'lvl-new'} />
        </div>
        {DIRS.map(k => {
          const d = reg.directions?.[k]
          if (!d) return null
          const c = d.counts
          return (
            <div key={k} className="reg-kpi" onClick={() => onOpenRegister(k)}>
              <div className="reg-kpi-title">{d.short}</div>
              <Item v={c.ok} label="в норме" cls="lvl-good" />
              <Item v={c.soon} label="скоро срок" cls="lvl-warn" />
              <Item v={c.attention} label="внимание" cls="lvl-warn" />
              <Item v={c.overdue} label="просрочено" cls="lvl-bad" />
              <Item v={c.none} label="нет данных" cls="lvl-new" />
            </div>
          )
        })}
      </div>
      <div className="section">
        <div className="section-head">
          <h2>Сроки и нарушения</h2>
          {reg.alerts_total > 0 && <span className="muted">{reg.alerts_bad} критичных из {reg.alerts_total}</span>}
        </div>
        <div className="weak-list">
          <AlertList alerts={reg.alerts.slice(0, 12)} showOffice onOffice={(a) => onOpenRegister(a.kind, a.office_code)} />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Слабые места и отсутствующие документы
// ---------------------------------------------------------------------------
function WeakSpots({ data, onDrill, bind }) {
  const items = data.weak_spots
  return (
    <div className="section">
      <h2>Слабые места</h2>
      <p className="muted mb-12">Направления ниже {data.thresholds.good}% — от худших к лучшим</p>
      {items.length === 0 ? <p className="lvl-good">✓ Всё в норме — проседающих направлений нет</p> : (
        <div className="weak-list">
          {items.map(w => (
            <div key={`${w.code}-${w.category}`} className="weak-item" onClick={() => onDrill({ code: w.code, category: w.category })}>
              <div className="weak-head">
                <span><strong>{w.code}</strong> · {w.category}</span>
                <span className={`lvl-pill lvl-${w.level}`}>{LEVEL_ICON[w.level]} {fmtPct(w.readiness)}</span>
              </div>
              <StatusBar done={w.done} inProgress={w.in_progress} missing={w.missing} height={6}
                         bind={bind} title={`${w.code} · ${w.category}`} />
              <div className="muted">нет {w.missing} · в работе {w.in_progress} · есть {w.done} из {w.total}</div>
            </div>
          ))}
          {data.weak_spots_total > items.length && <p className="muted">…и ещё {data.weak_spots_total - items.length}</p>}
        </div>
      )}
    </div>
  )
}

function TopMissing({ data, onDrill }) {
  const items = data.top_missing
  return (
    <div className="section">
      <h2>Чаще всего отсутствует</h2>
      <p className="muted mb-12">Документы со статусом «Нет» — в скольких офисах</p>
      {items.length === 0 ? <p className="lvl-good">✓ Отсутствующих документов нет</p> : (
        <div className="miss-list">
          {items.map(t => (
            <div key={t.title} className="miss-item">
              <div className="miss-title">{t.title}</div>
              <div className="miss-meta">
                <span className="muted">{t.category}</span>
                <span className="miss-count">{t.count} из {data.offices_with_data} офис.</span>
              </div>
              <div className="miss-bar"><div style={{ width: `${t.share}%` }} /></div>
              <div className="miss-offices">
                {t.offices.slice(0, 8).map(code => (
                  <button key={code} className="chip" onClick={() => onDrill({ code, category: t.category, status: 'missing' })}>{code}</button>
                ))}
                {t.offices.length > 8 && <span className="muted">+{t.offices.length - 8}</span>}
              </div>
            </div>
          ))}
          {data.top_missing_total > items.length && <p className="muted">Всего разных отсутствующих документов: {data.top_missing_total}</p>}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Готовность по направлениям (все офисы)
// ---------------------------------------------------------------------------
function CategoryBars({ data, bind }) {
  const [asTable, setAsTable] = useState(false)
  const rows = [...data.by_category].sort((a, b) => a.readiness - b.readiness)
  const d = data.documents
  return (
    <div className="section">
      <div className="section-head">
        <h2>Готовность по направлениям — все офисы</h2>
        <div className="seg-control">
          <button className={!asTable ? 'active' : ''} onClick={() => setAsTable(false)}>График</button>
          <button className={asTable ? 'active' : ''} onClick={() => setAsTable(true)}>Таблица</button>
        </div>
      </div>
      {asTable ? <CategoryTable rows={data.by_category} total={d} /> : (
        <>
          <div className="cat-bars">
            {rows.map(c => (
              <div key={c.category} className="cat-bar-row">
                <div className="cat-bar-name">{c.category}</div>
                <StatusBar done={c.done} inProgress={c.in_progress} missing={c.missing + c.not_set} height={14}
                           bind={bind} title={c.category} />
                <div className={`cat-bar-pct lvl-${c.level}`}>{fmtPct(c.readiness)}</div>
              </div>
            ))}
          </div>
          <StatusLegend />
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
export default function Dashboard({ data, onOpenOffices, onOpenDocuments, onDrill, onOpenRegister }) {
  const [bind, tooltip] = useTooltip()
  if (!data) return <div className="section"><Skeleton lines={6} /></div>

  if (!data.offices_with_data) {
    return (
      <>
      <RegistersBlock reg={data.registers} onOpenRegister={onOpenRegister} />
      <div className="section empty-state">
        <h2>Данных пока нет</h2>
        <p className="muted">Загрузите сводную таблицу «Чек-лист обязательных документов» — офис и показатели появятся автоматически.</p>
        <button className="btn" onClick={onOpenDocuments}>Загрузить таблицу</button>
      </div>
      </>
    )
  }

  return (
    <>
      <Kpis data={data} onOpenOffices={onOpenOffices} />
      <Heatmap data={data} onDrill={onDrill} bind={bind} onOpenRegister={onOpenRegister} />
      <RegistersBlock reg={data.registers} onOpenRegister={onOpenRegister} />
      <div className="two-col">
        <WeakSpots data={data} onDrill={onDrill} bind={bind} />
        <TopMissing data={data} onDrill={onDrill} />
      </div>
      <CategoryBars data={data} bind={bind} />
      {tooltip}
    </>
  )
}
