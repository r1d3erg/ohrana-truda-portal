import { useState } from 'react'

const PAGES = {
  dashboard: 'Дашборд',
  offices: 'Офисы',
  modules: 'Модули',
  sout: 'СОУТ',
  opr: 'ОПР',
  fire: 'Пожарная безопасность',
  electro: 'Электробезопасность',
  go: 'ГО ЧС',
  documents: 'Документы',
  notifications: 'Уведомления',
  feedback: 'Обратная связь',
}

const MODULES = [
  { icon: '🛡️', name: 'Охрана труда' },
  { icon: '🚨', name: 'ГО ЧС' },
  { icon: '🔥', name: 'Пожарная безопасность' },
  { icon: '⚡', name: 'Электробезопасность' },
  { icon: '📄', name: 'Документы и журналы' },
  { icon: '🎓', name: 'Обучение' },
  { icon: '📋', name: 'СОУТ' },
  { icon: '⚠️', name: 'ОПР (риски)' },
  { icon: '🔔', name: 'Уведомления' },
  { icon: '💬', name: 'Обратная связь' },
  { icon: '📖', name: 'Инструкция' },
  { icon: '🏋️', name: 'Тренинг обучения' },
]

// Порог индекса соответствия, начиная с которого офис считается в норме
const GOOD_INDEX = 90
// За сколько дней до окончания СОУТ считать её «истекающей»
const SOUT_WARN_DAYS = 90
const DAY_MS = 24 * 60 * 60 * 1000

// Демо-даты СОУТ считаются от текущего дня, чтобы прототип не «устаревал»
const daysFromNow = (days) => new Date(Date.now() + days * DAY_MS).toISOString().slice(0, 10)

const INITIAL_OFFICES = [
  { id: 1, name: 'Офис 1.1', resp: 'Иванов И.И.', index: 95, soutUntil: daysFromNow(400) },
  { id: 2, name: 'Офис 1.2', resp: 'Петров П.П.', index: 88, soutUntil: daysFromNow(45) },
  { id: 3, name: 'Офис 2.1', resp: '—', index: 72, soutUntil: daysFromNow(-20) },
]

const officeStatus = (o) => {
  if (o.index == null) return { label: 'Новый', badge: 'badge-new' }
  if (o.index >= GOOD_INDEX) return { label: 'Хорошо', badge: 'badge-ok' }
  return { label: 'Требует внимания', badge: 'badge-warn' }
}

const soutState = (o, now = Date.now()) => {
  if (!o.soutUntil) return 'none'
  const left = new Date(o.soutUntil).getTime() - now
  if (left < 0) return 'overdue'
  if (left <= SOUT_WARN_DAYS * DAY_MS) return 'expiring'
  return 'ok'
}

const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ru-RU') : '—')

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [role, setRole] = useState('super')
  const [page, setPage] = useState('dashboard')
  const [offices, setOffices] = useState(INITIAL_OFFICES)
  const [nextId, setNextId] = useState(INITIAL_OFFICES.length + 1)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newResp, setNewResp] = useState('')

  if (!loggedIn) {
    return (
      <div className="login-screen">
        <div className="login-box">
          <h2>Портал «Охрана труда»</h2>
          <p>Вход через Active Directory</p>
          <button className="btn" onClick={() => setLoggedIn(true)}>Войти</button>
        </div>
      </div>
    )
  }

  // Показатели дашборда считаются из данных офисов, а не захардкожены
  const indexed = offices.filter(o => o.index != null)
  const avgIndex = indexed.length
    ? Math.round(indexed.reduce((sum, o) => sum + o.index, 0) / indexed.length)
    : null
  const now = Date.now()
  const soutExpiring = offices.filter(o => soutState(o, now) === 'expiring').length
  const soutOverdue = offices.filter(o => soutState(o, now) === 'overdue').length

  const createOffice = () => {
    if (!newName.trim()) return alert('Укажите название офиса')
    setOffices([...offices, { id: nextId, name: newName.trim(), resp: newResp.trim() || '—', index: null, soutUntil: null }])
    setNextId(nextId + 1)
    setNewName('')
    setNewResp('')
    setShowCreate(false)
  }

  const assignOffice = (id) => {
    const office = offices.find(o => o.id === id)
    if (!office) return
    const name = prompt(`Назначить ответственного для «${office.name}»:`, office.resp === '—' ? '' : office.resp)
    if (name !== null) {
      setOffices(offices.map(o => (o.id === id ? { ...o, resp: name.trim() || '—' } : o)))
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">Охрана <span>труда</span></div>
        {Object.entries(PAGES).map(([key, label]) => (
          <div key={key} className={`nav-item ${page === key ? 'active' : ''}`} onClick={() => setPage(key)}>
            {label}
          </div>
        ))}
      </aside>

      <main className="main">
        <div className="header">
          <h1>{PAGES[page]}</h1>
          <div className="user-badge">Роль: <strong>{role === 'super' ? 'Супер-админ' : 'Ответственный офиса'}</strong></div>
        </div>

        <div className="role-switch">
          <button className={`role-btn ${role === 'super' ? 'active' : ''}`} onClick={() => setRole('super')}>Супер-админ</button>
          <button className={`role-btn ${role === 'office' ? 'active' : ''}`} onClick={() => setRole('office')}>Ответственный офиса</button>
        </div>

        {page === 'dashboard' && (
          <div className="cards">
            <div className="card">
              <div className="card-title">Индекс соответствия</div>
              <div className={`card-value ${avgIndex == null ? '' : avgIndex >= GOOD_INDEX ? 'success' : 'warning'}`}>
                {avgIndex == null ? '—' : `${avgIndex}%`}
              </div>
            </div>
            <div className="card"><div className="card-title">Офисов</div><div className="card-value">{offices.length}</div></div>
            <div className="card"><div className="card-title">Истекает СОУТ</div><div className={`card-value ${soutExpiring ? 'warning' : ''}`}>{soutExpiring}</div></div>
            <div className="card"><div className="card-title">Просрочено</div><div className={`card-value ${soutOverdue ? 'danger' : ''}`}>{soutOverdue}</div></div>
          </div>
        )}

        {page === 'offices' && (
          <>
            {role === 'super' && (
              <div className="section">
                <button className="btn" onClick={() => setShowCreate(!showCreate)}>+ Создать офис</button>
                {showCreate && (
                  <div style={{ marginTop: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
                    <div>
                      <label style={{ fontSize: 13, color: '#718096' }}>Название офиса</label><br />
                      <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Офис 3.1" style={{ padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 8, marginTop: 4 }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 13, color: '#718096' }}>Ответственный</label><br />
                      <input value={newResp} onChange={e => setNewResp(e.target.value)} placeholder="Иванов И.И." style={{ padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 8, marginTop: 4 }} />
                    </div>
                    <button className="btn" onClick={createOffice}>Создать</button>
                  </div>
                )}
              </div>
            )}
            <div className="section">
              <h2>Офисы</h2>
              <table>
                <thead><tr><th>Офис</th><th>Ответственный</th><th>Индекс</th><th>СОУТ до</th><th>Статус</th><th>Действия</th></tr></thead>
                <tbody>
                  {offices.map(o => {
                    const status = officeStatus(o)
                    const sout = soutState(o, now)
                    return (
                      <tr key={o.id}>
                        <td>{o.name}</td>
                        <td>{o.resp}</td>
                        <td>{o.index == null ? '—' : `${o.index}%`}</td>
                        <td>
                          {formatDate(o.soutUntil)}
                          {sout === 'overdue' && <span className="badge badge-danger" style={{ marginLeft: 8 }}>просрочена</span>}
                          {sout === 'expiring' && <span className="badge badge-warn" style={{ marginLeft: 8 }}>истекает</span>}
                        </td>
                        <td><span className={`badge ${status.badge}`}>{status.label}</span></td>
                        <td>{role === 'super' && <button onClick={() => assignOffice(o.id)} style={{ fontSize: 12, padding: '4px 8px', border: '1px solid #cbd5e0', borderRadius: 6, background: '#fff', cursor: 'pointer' }}>Назначить</button>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {page === 'modules' && (
          <div className="modules-grid">
            {MODULES.map(m => (
              <div key={m.name} className="module-card">
                <div className="module-icon">{m.icon}</div>
                <div className="module-name">{m.name}</div>
              </div>
            ))}
          </div>
        )}

        {page === 'feedback' && (
          <div className="section">
            <h2>Часто задаваемые вопросы</h2>
            <details open><summary>Что такое СОУТ?</summary><p>СОУТ — специальная оценка условий труда. Обязательная процедура измерения вредных и опасных факторов на рабочих местах.</p></details>
            <details><summary>Что такое ОПР?</summary><p>ОПР — оценка профессиональных рисков. Выявление опасностей и разработка мер по их снижению.</p></details>
            <details><summary>Что такое аналогичные рабочие места?</summary><p>Аналогичные рабочие места позволяют проводить СОУТ только на 20% мест (не менее 2).</p></details>
          </div>
        )}

        {!['dashboard', 'offices', 'modules', 'feedback'].includes(page) && (
          <div className="section">
            <h2>{PAGES[page]}</h2>
            <p>Раздел в разработке. Здесь будут данные по офисам.</p>
          </div>
        )}
      </main>
    </div>
  )
}
