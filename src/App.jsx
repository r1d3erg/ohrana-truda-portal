import { useCallback, useEffect, useState } from 'react'
import { api, setThresholds } from './api.js'
import { ErrorBox } from './components.jsx'
import { Icon } from './icons.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Documents from './pages/Documents.jsx'
import Faq from './pages/Faq.jsx'
import Guide from './pages/Guide.jsx'
import Offices from './pages/Offices.jsx'
import Opr from './pages/Opr.jsx'
import Sout from './pages/Sout.jsx'
import Training from './pages/Training.jsx'
import { applyTheme, getThemePref, saveThemePref, watchSystemTheme } from './theme.js'

// Меню: группы → пункты. soon — раздел ещё не реализован (показывается заглушка).
const NAV = [
  { group: null, items: [
    { key: 'dashboard', label: 'Дашборд', icon: 'squares-four' },
    { key: 'offices', label: 'Офисы', icon: 'buildings' },
    { key: 'documents', label: 'Документы', icon: 'files' },
  ] },
  { group: 'Оценки', items: [
    { key: 'sout', label: 'СОУТ', icon: 'clipboard-text' },
    { key: 'opr', label: 'ОПР', icon: 'warning' },
  ] },
  { group: 'Направления · в разработке', items: [
    { key: 'fire', label: 'Пожарная безопасность', icon: 'fire', soon: true, guide: 'fire-electro' },
    { key: 'electro', label: 'Электробезопасность', icon: 'lightning', soon: true, guide: 'fire-electro' },
    { key: 'go', label: 'ГО ЧС', icon: 'siren', soon: true, guide: 'go' },
    { key: 'notifications', label: 'Уведомления', icon: 'bell', soon: true },
  ] },
  { group: 'Обучение и справка', items: [
    { key: 'training', label: 'Тренинг обучения', icon: 'graduation-cap' },
    { key: 'feedback', label: 'Вопросы и ответы', icon: 'question' },
    { key: 'guide', label: 'Инструкция', icon: 'book-open' },
    { key: 'modules', label: 'Модули', icon: 'gauge' },
  ] },
]
const PAGES = Object.fromEntries(NAV.flatMap(g => g.items.map(i => [i.key, i])))

// Модули: open — куда ведёт карточка (страница портала и, для «Инструкции», раздел)
const MODULES = [
  { icon: 'hard-hat', name: 'Охрана труда', note: 'Документы СУОТ, инструкции, инструктажи', open: { page: 'guide', section: 'start' } },
  { icon: 'siren', name: 'ГО ЧС', note: 'Планы и приказы по ГО и ЧС', open: { page: 'guide', section: 'go' } },
  { icon: 'fire', name: 'Пожарная безопасность', note: 'Противопожарный режим, эвакуация', open: { page: 'guide', section: 'fire-electro' } },
  { icon: 'lightning', name: 'Электробезопасность', note: 'Группы допуска, журналы', open: { page: 'guide', section: 'fire-electro' } },
  { icon: 'files', name: 'Документы и журналы', note: 'Сводная таблица и индекс соответствия', open: { page: 'documents' } },
  { icon: 'graduation-cap', name: 'Обучение', note: 'Обучение и проверка знаний', open: { page: 'guide', section: 'internal' } },
  { icon: 'clipboard-text', name: 'СОУТ', note: 'Сроки, классы, декларация', open: { page: 'sout' } },
  { icon: 'warning', name: 'ОПР (риски)', note: 'Уровни рисков и план мер', open: { page: 'opr' } },
  { icon: 'bell', name: 'Уведомления', note: 'Напоминания о сроках' },
  { icon: 'chat-circle', name: 'Обратная связь', note: 'Вопросы ответственным', open: { page: 'feedback' } },
  { icon: 'book-open', name: 'Инструкция', note: 'Пошагово для руководителя', open: { page: 'guide', section: 'start' } },
  { icon: 'barbell', name: 'Тренинг обучения', note: 'Тренажёр проверки знаний по ОТ', open: { page: 'training' } },
]

const THEME_OPTIONS = { system: 'Как в системе', dark: 'Тёмная', light: 'Светлая' }

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [role, setRole] = useState('super')
  const [page, setPage] = useState('dashboard')
  const [offices, setOffices] = useState([])
  const [dashboard, setDashboard] = useState(null)
  const [selectedOffice, setSelectedOffice] = useState(null)
  // Переход с дашборда в документы офиса с готовым фильтром
  const [docFocus, setDocFocus] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [registerFocus, setRegisterFocus] = useState(null)
  const [guideSection, setGuideSection] = useState(null)
  const [error, setError] = useState(null)
  const [themePref, setThemePref] = useState(getThemePref)

  useEffect(() => {
    applyTheme(themePref)
    saveThemePref(themePref)
    return themePref === 'system' ? watchSystemTheme(() => applyTheme('system')) : undefined
  }, [themePref])

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
    api.config().then(c => { setThresholds(c); setCfg(c) }).catch(() => {})
    reload()
  }, [loggedIn, reload])

  if (!loggedIn) {
    return (
      <main className="login-screen">
        <div className="login-box">
          <span className="login-icon"><Icon name="hard-hat" size={24} /></span>
          <h1>Охрана труда</h1>
          <p>Документы, СОУТ и оценка рисков по всем офисам в одном месте. Вход через учётную запись Active Directory.</p>
          <button className="btn" onClick={() => setLoggedIn(true)}><Icon name="sign-in" size={20} /> Войти через AD</button>
        </div>
      </main>
    )
  }

  const openDocuments = (code) => {
    setSelectedOffice(code)
    setDocFocus(null)
    setPage('documents')
  }

  const openRegister = (kind, code) => {
    setRegisterFocus({ code, nonce: Date.now() })
    setPage(kind)
  }

  const drill = ({ code, category = '', status = '', q = '' }) => {
    setSelectedOffice(code)
    setDocFocus({ category, status, q, nonce: Date.now() })
    setPage('documents')
  }

  const current = PAGES[page]

  return (
    <div className="app">
      <a className="skip-link" href="#content">Перейти к содержимому</a>
      <aside className="sidebar">
        <div className="logo"><Icon name="hard-hat" size={24} /> Охрана <span>труда</span></div>
        <nav aria-label="Разделы портала">
          {NAV.map(g => (
            <div key={g.group || 'main'}>
              {g.group && <div className="nav-group">{g.group}</div>}
              {g.items.map(i => (
                <button key={i.key} type="button" className={`nav-item ${page === i.key ? 'active' : ''} ${i.soon ? 'soon' : ''}`}
                        aria-current={page === i.key ? 'page' : undefined} onClick={() => setPage(i.key)}
                        title={i.soon ? 'Раздел в разработке' : undefined}>
                  <Icon name={i.icon} size={20} />
                  <span className="nav-label">{i.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      <main className="main" id="content" tabIndex={-1}>
        <header className="header">
          <h1>{current?.label}</h1>
          <div className="header-tools">
            <div className="role-switch" role="group" aria-label="Роль">
              <button className={`role-btn ${role === 'super' ? 'active' : ''}`} onClick={() => setRole('super')}>Супер-админ</button>
              <button className={`role-btn ${role === 'office' ? 'active' : ''}`} onClick={() => setRole('office')}>Ответственный офиса</button>
            </div>
            <label className="user-badge">
              Тема
              <select className="input" value={themePref} onChange={e => setThemePref(e.target.value)}>
                {Object.entries(THEME_OPTIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
          </div>
        </header>

        <ErrorBox error={error} />

        {page === 'dashboard' && (
          <Dashboard data={dashboard} onOpenOffices={() => setPage('offices')}
                     onOpenDocuments={() => setPage('documents')} onDrill={drill}
                     onOpenRegister={openRegister} />
        )}

        {page === 'offices' && (
          <Offices offices={offices} role={role} onChanged={reload} onOpenDocuments={openDocuments} />
        )}

        {page === 'documents' && (
          <Documents offices={offices} role={role} selectedCode={selectedOffice}
                     onSelect={setSelectedOffice} onChanged={reload} focus={docFocus} />
        )}

        {page === 'sout' && (
          <Sout cfg={cfg} role={role} focusCode={registerFocus?.code} key={`sout-${registerFocus?.nonce || 0}`} onChanged={reload} />
        )}

        {page === 'opr' && (
          <Opr cfg={cfg} role={role} focusCode={registerFocus?.code} key={`opr-${registerFocus?.nonce || 0}`} onChanged={reload} />
        )}

        {page === 'modules' && (
          <div className="modules-grid">
            {MODULES.map(m => {
              const body = (
                <>
                  <span className="module-icon"><Icon name={m.icon} size={24} /></span>
                  <div>
                    <div className="module-name">{m.name}</div>
                    <div className="muted">{m.note}</div>
                  </div>
                </>
              )
              return m.open ? (
                <button key={m.name} type="button" className="module-card module-link" onClick={() => {
                  if (m.open.section) setGuideSection(m.open.section)
                  setPage(m.open.page)
                }}>{body}</button>
              ) : (
                <article key={m.name} className="module-card module-soon" title="Модуль в разработке">{body}</article>
              )
            })}
          </div>
        )}

        {page === 'guide' && <Guide sectionId={guideSection} onSectionChange={setGuideSection} />}

        {page === 'feedback' && <Faq />}

        {page === 'training' && <Training />}

        {current?.soon && (
          <section className="section empty-state">
            <h2>Раздел «{current.label}» в разработке</h2>
            <p>Документы по этому направлению уже видны в чек-листе офиса: откройте «Документы» и выберите раздел в фильтре.</p>
            <div className="upload-row">
              <button className="btn" onClick={() => setPage('documents')}>Открыть документы</button>
              {current.guide && (
                <button className="btn btn-secondary" onClick={() => { setGuideSection(current.guide); setPage('guide') }}>
                  <Icon name="book-open" size={20} /> Что делать по регламенту
                </button>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
