import { useMemo, useState } from 'react'
import { FAQ, FAQ_CATEGORIES, FAQ_UPDATED } from '../data/faq.js'

const norm = (s) => s.toLowerCase().replace(/ё/g, 'е')

export default function Faq() {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState(null)

  const counts = useMemo(() => {
    const c = {}
    for (const f of FAQ) c[f.cat] = (c[f.cat] || 0) + 1
    return c
  }, [])

  const items = useMemo(() => {
    const needle = norm(q.trim())
    return FAQ.filter(f => (!cat || f.cat === cat) &&
      (!needle || norm(`${f.q} ${f.a} ${f.basis}`).includes(needle)))
  }, [q, cat])

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Вопросы и ответы по охране труда</h2>
          <p className="muted">
            Справочный материал, сверен с нормами на {FAQ_UPDATED} — включая изменения Правил обучения
            с 31.08.2026 (ПП РФ № 805). Не заменяет нормативные акты: при спорной ситуации сверяйтесь с первоисточником.
          </p>
        </div>
        <input className="input faq-search" type="search" placeholder="Поиск: инструктаж, СОУТ, штраф…"
               value={q} onChange={e => setQ(e.target.value)} aria-label="Поиск по вопросам" />
      </div>

      <div className="chips-row" role="group" aria-label="Темы">
        <button className={`chip ${!cat ? 'chip-active' : ''}`} onClick={() => setCat(null)}>Все · {FAQ.length}</button>
        {FAQ_CATEGORIES.map(c => (
          <button key={c} className={`chip ${cat === c ? 'chip-active' : ''}`} onClick={() => setCat(cat === c ? null : c)}>
            {c} · {counts[c] || 0}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <h2>Ничего не нашлось</h2>
          <p>Попробуйте другое слово или сбросьте фильтр темы.</p>
          <button className="btn btn-secondary" onClick={() => { setQ(''); setCat(null) }}>Сбросить</button>
        </div>
      ) : (
        <div className="faq">
          {items.map(f => (
            <article key={f.q} className="faq-item">
              <div className="faq-cat">{f.cat}</div>
              <h3>{f.q}</h3>
              <p>{f.a}</p>
              <div className="faq-basis">Основание: {f.basis}</div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
