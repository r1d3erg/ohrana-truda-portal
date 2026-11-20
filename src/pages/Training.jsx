import { useEffect, useMemo, useState } from 'react'
import { EXAM, EXAM_SETTINGS } from '../data/exam.js'
import { Icon } from '../icons.jsx'

const STORE = 'ot-exam-history'

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(STORE) || '[]') } catch { return [] }
}
function saveHistory(h) {
  try { localStorage.setItem(STORE, JSON.stringify(h.slice(0, 10))) } catch { /* без сохранения */ }
}

function shuffle(arr) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

// Попытка: случайные вопросы, варианты ответов перемешаны
function buildAttempt(mode) {
  const pool = mode === 'all' ? shuffle(EXAM) : shuffle(EXAM).slice(0, EXAM_SETTINGS.questions)
  return pool.map(q => {
    const order = shuffle(q.options.map((_, i) => i))
    return { ...q, order, correct: order.indexOf(q.answer) }
  })
}

const fmtTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
const plural = (n, one, few, many) => {
  const a = n % 100, b = n % 10
  if (a > 10 && a < 20) return many
  return b === 1 ? one : b >= 2 && b <= 4 ? few : many
}

// ---------------------------------------------------------------------------
function Intro({ onStart, history }) {
  const [mode, setMode] = useState('exam')
  const [instant, setInstant] = useState(false)
  const topics = useMemo(() => [...new Set(EXAM.map(q => q.topic))], [])
  const best = history.reduce((m, h) => Math.max(m, h.percent), 0)
  return (
    <>
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Тренажёр проверки знаний по охране труда</h2>
            <p className="muted">
              Формат приближен к проверке знаний: случайные вопросы из банка, один верный ответ, зачёт — от {EXAM_SETTINGS.passPercent} %
              правильных. Вопросы по программе А и общим требованиям: обучение и инструктажи, СОУТ, ОПР, первая помощь,
              несчастные случаи, ответственность. Учтены изменения с 31.08.2026.
            </p>
          </div>
        </div>
        <div className="exam-facts">
          <div><span className="muted">Вопросов в банке</span><strong>{EXAM.length}</strong></div>
          <div><span className="muted">В попытке</span><strong>{mode === 'all' ? EXAM.length : EXAM_SETTINGS.questions}</strong></div>
          <div><span className="muted">Зачёт</span><strong>от {EXAM_SETTINGS.passPercent} %</strong></div>
          <div><span className="muted">Ориентир по времени</span><strong>{mode === 'all' ? 60 : EXAM_SETTINGS.minutes} мин</strong></div>
          <div><span className="muted">Лучший результат</span><strong>{history.length ? `${best} %` : '—'}</strong></div>
        </div>
        <div className="form-row">
          <div className="seg-control" role="group" aria-label="Режим">
            <button className={mode === 'exam' ? 'active' : ''} onClick={() => setMode('exam')}>Экзамен · {EXAM_SETTINGS.questions} вопросов</button>
            <button className={mode === 'all' ? 'active' : ''} onClick={() => setMode('all')}>Все вопросы</button>
          </div>
          <label className="check"><input type="checkbox" checked={instant} onChange={e => setInstant(e.target.checked)} /> Показывать правильный ответ сразу (тренировка)</label>
        </div>
        <div className="form-row">
          <button className="btn" onClick={() => onStart(mode, instant)}><Icon name="graduation-cap" size={20} /> Начать</button>
        </div>
        <p className="muted mt-16">Темы: {topics.join(' · ')}</p>
      </section>

      {history.length > 0 && (
        <section className="section">
          <h2>Последние попытки</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Дата</th><th>Режим</th><th>Результат</th><th>Время</th><th>Итог</th></tr></thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={i}>
                    <td>{new Date(h.at).toLocaleString('ru-RU')}</td>
                    <td>{h.mode === 'all' ? 'Все вопросы' : 'Экзамен'}{h.instant ? ' · тренировка' : ''}</td>
                    <td>{h.correct} из {h.total} · {h.percent} %</td>
                    <td>{fmtTime(h.seconds)}</td>
                    <td><span className={`badge ${h.passed ? 'badge-ok' : 'badge-danger'}`}>{h.passed ? '✓ Сдано' : '✕ Не сдано'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
function Runner({ attempt, instant, onFinish, onCancel }) {
  const [idx, setIdx] = useState(0)
  const [answers, setAnswers] = useState(() => attempt.map(() => null))
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSeconds(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [])

  const q = attempt[idx]
  const chosen = answers[idx]
  const answered = answers.filter(a => a !== null).length
  const reveal = instant && chosen !== null
  const choose = (i) => {
    if (instant && chosen !== null) return
    setAnswers(a => a.map((v, k) => (k === idx ? i : v)))
  }
  const finish = () => onFinish(answers, seconds)
  const unanswered = attempt.length - answered

  return (
    <section className="section exam-runner">
      <div className="exam-top">
        <span className="muted">Вопрос {idx + 1} из {attempt.length} · {q.topic}</span>
        <span className="muted num">Отвечено {answered} · {fmtTime(seconds)}</span>
      </div>
      <div className="progress-bar exam-progress"><div className="progress-fill ok" style={{ width: `${(answered / attempt.length) * 100}%` }} /></div>

      <h2 className="exam-q">{q.q}</h2>
      <div className="exam-options" role="radiogroup" aria-label="Варианты ответа">
        {q.order.map((orig, i) => {
          let state = ''
          if (chosen === i) state = 'chosen'
          if (reveal && i === q.correct) state = 'right'
          else if (reveal && chosen === i) state = 'wrong'
          return (
            <button key={orig} type="button" role="radio" aria-checked={chosen === i}
                    className={`exam-option ${state}`} onClick={() => choose(i)}>
              <span className="exam-letter">{'АБВГ'[i]}</span>
              <span>{q.options[orig]}</span>
            </button>
          )
        })}
      </div>
      {reveal && (
        <div className={`alert ${chosen === q.correct ? 'alert-ok' : 'alert-danger'}`}>
          <strong>{chosen === q.correct ? 'Верно.' : 'Неверно.'}</strong> {q.why} <span className="muted">Основание: {q.basis}</span>
        </div>
      )}

      <div className="exam-nav">
        <button className="btn btn-secondary" disabled={idx === 0} onClick={() => setIdx(i => i - 1)}>Назад</button>
        <div className="exam-dots" aria-label="Переход к вопросу">
          {attempt.map((_, i) => (
            <button key={i} type="button" className={`exam-dot ${i === idx ? 'current' : ''} ${answers[i] !== null ? 'done' : ''}`}
                    onClick={() => setIdx(i)} aria-label={`Вопрос ${i + 1}`} />
          ))}
        </div>
        {idx < attempt.length - 1
          ? <button className="btn" onClick={() => setIdx(i => i + 1)}>Далее</button>
          : <button className="btn" onClick={finish}>Завершить</button>}
      </div>
      <div className="exam-foot">
        <button className="btn-link" onClick={onCancel}>Прервать попытку</button>
        {idx < attempt.length - 1 && (
          <button className="btn-link" onClick={finish}>
            Завершить досрочно{unanswered ? ` (без ответа: ${unanswered})` : ''}
          </button>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
function Result({ attempt, answers, seconds, onRestart, onBack }) {
  const correct = attempt.filter((q, i) => answers[i] === q.correct).length
  const percent = Math.round((correct * 100) / attempt.length)
  const passed = percent >= EXAM_SETTINGS.passPercent
  const byTopic = {}
  attempt.forEach((q, i) => {
    const t = (byTopic[q.topic] ||= { total: 0, ok: 0 })
    t.total++
    if (answers[i] === q.correct) t.ok++
  })
  const wrong = attempt.map((q, i) => ({ q, a: answers[i] })).filter(x => x.a !== x.q.correct)

  return (
    <>
      <section className="section">
        <div className="exam-result">
          <div>
            <div className={`exam-score ${passed ? 'lvl-good' : 'lvl-bad'}`}>{percent} %</div>
            <span className={`badge ${passed ? 'badge-ok' : 'badge-danger'}`}>{passed ? '✓ Сдано' : '✕ Не сдано'}</span>
          </div>
          <div className="exam-facts">
            <div><span className="muted">Правильных</span><strong>{correct} из {attempt.length}</strong></div>
            <div><span className="muted">Порог</span><strong>{EXAM_SETTINGS.passPercent} %</strong></div>
            <div><span className="muted">Время</span><strong>{fmtTime(seconds)}</strong></div>
          </div>
        </div>
        <div className="form-row">
          <button className="btn" onClick={onRestart}>Новая попытка</button>
          <button className="btn btn-secondary" onClick={onBack}>К описанию теста</button>
        </div>
      </section>

      <section className="section">
        <h2>По темам</h2>
        <div className="cat-bars">
          {Object.entries(byTopic).sort((a, b) => a[1].ok / a[1].total - b[1].ok / b[1].total).map(([t, v]) => {
            const p = Math.round((v.ok * 100) / v.total)
            return (
              <div key={t} className="cat-bar-row">
                <div>{t}</div>
                <div className="progress-bar"><div className={`progress-fill ${p >= EXAM_SETTINGS.passPercent ? 'ok' : p >= 50 ? 'warn' : 'danger'}`} style={{ width: `${p}%` }} /></div>
                <div className="cat-bar-pct">{v.ok}/{v.total}</div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="section">
        <h2>{wrong.length ? `Разбор ошибок · ${wrong.length} ${plural(wrong.length, 'вопрос', 'вопроса', 'вопросов')}` : 'Ошибок нет'}</h2>
        {wrong.length === 0 ? <p className="lvl-good">✓ Все ответы верные.</p> : (
          <div className="exam-review">
            {wrong.map(({ q, a }) => (
              <article key={q.q} className="faq-item">
                <div className="faq-cat">{q.topic}</div>
                <h3>{q.q}</h3>
                <p className="lvl-bad">✕ {a === null ? 'Нет ответа' : `Ваш ответ: ${q.options[q.order[a]]}`}</p>
                <p className="lvl-good">✓ Правильно: {q.options[q.answer]}</p>
                <p>{q.why}</p>
                <div className="faq-basis">Основание: {q.basis}</div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

// ---------------------------------------------------------------------------
export default function Training() {
  const [stage, setStage] = useState('intro')
  const [attempt, setAttempt] = useState(null)
  const [settings, setSettings] = useState({ mode: 'exam', instant: false })
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState(loadHistory)

  const start = (mode, instant) => {
    setSettings({ mode, instant })
    setAttempt(buildAttempt(mode))
    setResult(null)
    setStage('run')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const finish = (answers, seconds) => {
    const correct = attempt.filter((q, i) => answers[i] === q.correct).length
    const percent = Math.round((correct * 100) / attempt.length)
    const entry = {
      at: new Date().toISOString(), mode: settings.mode, instant: settings.instant,
      total: attempt.length, correct, percent, seconds, passed: percent >= EXAM_SETTINGS.passPercent,
    }
    const h = [entry, ...history].slice(0, 10)
    setHistory(h)
    saveHistory(h)
    setResult({ answers, seconds })
    setStage('result')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (stage === 'run') {
    return <Runner key={attempt.map(q => q.q).join('|')} attempt={attempt} instant={settings.instant}
                   onFinish={finish} onCancel={() => setStage('intro')} />
  }
  if (stage === 'result') {
    return <Result attempt={attempt} answers={result.answers} seconds={result.seconds}
                   onRestart={() => start(settings.mode, settings.instant)} onBack={() => setStage('intro')} />
  }
  return <Intro onStart={start} history={history} />
}
