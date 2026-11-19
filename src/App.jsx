import { useCallback, useEffect, useState } from 'react'
import { api, setThresholds } from './api.js'
import { ErrorBox } from './components.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Documents from './pages/Documents.jsx'
import Offices from './pages/Offices.jsx'

const PAGES = {
  dashboard: 'Дашборд',
  offices: 'Офисы',
  documents: 'Документы',
  modules: 'Модули',
  sout: 'СОУТ',
  opr: 'ОПР',
  fire: 'Пожарная безопасность',
  electro: 'Электробезопасность',
  go: 'ГО ЧС',
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

const IMPLEMENTED = ['dashboard', 'offices', 'documents', 'modules', 'feedback']

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [role, setRole] = useState('super')
  const [page, setPage] = useState('dashboard')
  const [offices, setOffices] = useState([])
  const [dashboard, setDashboard] = useState(null)
  const [selectedOffice, setSelectedOffice] = useState(null)
  const [error, setError] = useState(null)

  // Данные портала берутся из API; reload вызывается после любых изменений
  const reload = useCallback(async () => {
    try {
      const [o, d] = await Promise.all([api.offices(), api.dashboard()])
      setOffices(o)
      setDashboard(d)
      setError(null)
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    if (!loggedIn) return
    api.config().then(setThresholds).catch(() => {})
    reload()
  }, [loggedIn, reload])

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

  const openDocuments = (code) => {
    setSelectedOffice(code)
    setPage('documents')
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

        <ErrorBox error={error} />

        {page === 'dashboard' && <Dashboard data={dashboard} onOpenOffices={() => setPage('offices')} />}

        {page === 'offices' && (
          <Offices offices={offices} role={role} onChanged={reload} onOpenDocuments={openDocuments} />
        )}

        {page === 'documents' && (
          <Documents offices={offices} role={role} selectedCode={selectedOffice}
                     onSelect={setSelectedOffice} onChanged={reload} />
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
            <details><summary>Как обновить индекс соответствия офиса?</summary><p>Заполните сводную таблицу «Чек-лист обязательных документов» и загрузите её в разделе «Документы». Индекс = доля документов со статусом «Есть».</p></details>
          </div>
        )}

        {!IMPLEMENTED.includes(page) && (
          <div className="section">
            <h2>{PAGES[page]}</h2>
            <p>Раздел в разработке. Здесь будут данные по офисам.</p>
          </div>
        )}
      </main>
    </div>
  )
}
