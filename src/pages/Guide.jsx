import { useEffect, useMemo, useRef, useState } from 'react'
import { GUIDE, GUIDE_GROUPS, GUIDE_UPDATED } from '../data/guide.js'
import { Icon } from '../icons.jsx'

function Block({ b }) {
  if (b.h) return <h3 className="guide-h">{b.h}</h3>
  if (b.p) return <p className="guide-p">{b.p}</p>
  if (b.note) return <div className="guide-note">{b.note}</div>
  if (b.warn) return <div className="guide-note guide-warn" role="note"><strong>Важно. </strong>{b.warn}</div>
  if (b.steps) return <ol className="guide-steps">{b.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
  if (b.list) return <ul className="guide-list">{b.list.map((s, i) => <li key={i}>{s}</li>)}</ul>
  if (b.table) {
    return (
      <div className="table-wrap guide-table">
        <table>
          <thead><tr>{b.table.head.map(h => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {b.table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
    )
  }
  return null
}

export default function Guide({ sectionId, onSectionChange }) {
  const [current, setCurrent] = useState(sectionId || GUIDE[0].id)
  const contentRef = useRef(null)

  useEffect(() => { if (sectionId) setCurrent(sectionId) }, [sectionId])

  const index = useMemo(() => Math.max(0, GUIDE.findIndex(s => s.id === current)), [current])
  const section = GUIDE[index]
  const prev = GUIDE[index - 1]
  const next = GUIDE[index + 1]

  const open = (id) => {
    setCurrent(id)
    onSectionChange?.(id)
    contentRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

  return (
    <div className="guide">
      <nav className="guide-toc section" aria-label="Разделы инструкции">
        <div className="guide-toc-head">Инструкция для руководителя</div>
        {GUIDE_GROUPS.map(g => (
          <div key={g} className="guide-toc-group">
            <div className="guide-toc-title">{g}</div>
            {GUIDE.filter(s => s.group === g).map(s => (
              <button key={s.id} type="button" className={`guide-toc-item ${s.id === current ? 'active' : ''}`}
                      aria-current={s.id === current ? 'true' : undefined} onClick={() => open(s.id)}>
                <Icon name={s.icon} size={16} />
                <span>{s.title}</span>
              </button>
            ))}
          </div>
        ))}
        <p className="muted guide-updated">Сверено с нормами на {GUIDE_UPDATED}</p>
      </nav>

      <article className="section guide-body" ref={contentRef} key={section.id}>
        <div className="guide-crumb">{section.group}</div>
        <h2>{section.title}</h2>
        {section.lead && <p className="guide-lead">{section.lead}</p>}
        {section.blocks.map((b, i) => <Block key={i} b={b} />)}

        <div className="guide-pager">
          {prev
            ? <button type="button" className="btn btn-secondary" onClick={() => open(prev.id)}>← {prev.title}</button>
            : <span />}
          {next && <button type="button" className="btn btn-secondary" onClick={() => open(next.id)}>{next.title} →</button>}
        </div>
      </article>
    </div>
  )
}
