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

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [role, setRole] = useState('super')
  const [page, setPage] = useState('dashboard')
  const [offices, setOffices] = useState([
    { name: 'Офис 1.1', resp: 'Иванов И.И.', index: '95%', status: 'Хорошо' },
    { name: 'Офис 1.2', resp: 'Петров П.П.', index: '88%', status: 'Требует внимания' },
    { name: 'Офис 2.1', resp: '—', index: '72%', status: 'Требует внимания' },
  ])
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

  const createOffice = () => {
    if (!newName.trim()) return alert('Укажите название офиса')
    setOffices([...offices, { name: newName.trim(), resp: newResp.trim() || '—', index: '—', status: 'Новый' }])
    setNewName('')
    setNewResp('')
    setShowCreate(false)
  }

  const assignOffice = (idx) => {
    const current = offices[idx].resp
    const name = prompt(`Назначить ответственного для «${offices[idx].name}»:`, current === '—' ? '' : current)
    if (name !== null) {
      const updated = [...offices]
      updated[idx].resp = name.trim() || '—'
      setOffices(updated)
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
            <div className="card"><div className="card-title">Индекс соответствия</div><div className="card-value success">87%</div></div>
            <div className="card"><div className="card-title">Офисов</div><div className="card-value">142</div></div>
            <div className="card"><div className="card-title">Истекает СОУТ</div><div className="card-value warning">12</div></div>
            <div className="card"><div className="card-title">Просрочено</div><div className="card-value danger">5</div></div>
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
                <thead><tr><th>Офис</th><th>Ответственный</th><th>Индекс</th><th>Статус</th><th>Действия</th></tr></thead>
                <tbody>
                  {offices.map((o, i) => (
                    <tr key={i}>
                      <td>{o.name}</td>
                      <td>{o.resp}</td>
                      <td>{o.index}</td>
                      <td><span className={`badge ${o.status === 'Хорошо' ? 'badge-ok' : 'badge-warn'}`}>{o.status}</span></td>
                      <td>{role === 'super' && <button onClick={() => assignOffice(i)} style={{ fontSize: 12, padding: '4px 8px', border: '1px solid #cbd5e0', borderRadius: 6, background: '#fff', cursor: 'pointer' }}>Назначить</button>}</td>
                    </tr>
                  ))}
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
