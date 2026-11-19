import { useCallback, useEffect, useState } from 'react'
import { api, setThresholds } from './api.js'
import { ErrorBox } from './components.jsx'
import { Icon } from './icons.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Documents from './pages/Documents.jsx'
import Offices from './pages/Offices.jsx'
import Opr from './pages/Opr.jsx'
import Sout from './pages/Sout.jsx'
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
  { group: 'Направления', items: [
    { key: 'fire', label: 'Пожарная безопасность', icon: 'fire', soon: true },
    { key: 'electro', label: 'Электробезопасность', icon: 'lightning', soon: true },
    { key: 'go', label: 'ГО ЧС', icon: 'siren', soon: true },
    { key: 'notifications', label: 'Уведомления', icon: 'bell', soon: true },
  ] },
  { group: 'Справка', items: [
    { key: 'modules', label: 'Модули', icon: 'gauge' },
    { key: 'feedback', label: 'Вопросы и ответы', icon: 'question' },
  ] },
]
const PAGES = Object.fromEntries(NAV.flatMap(g => g.items.map(i => [i.key, i])))

const MODULES = [
  { icon: 'hard-hat', name: 'Охрана труда', note: 'Документы СУОТ, инструкции, инструктажи' },
  { icon: 'siren', name: 'ГО ЧС', note: 'Планы и приказы по ГО и ЧС' },
  { icon: 'fire', name: 'Пожарная безопасность', note: 'Противопожарный режим, эвакуация' },
  { icon: 'lightning', name: 'Электробезопасность', note: 'Группы допуска, журналы' },
  { icon: 'files', name: 'Документы и журналы', note: 'Сводная таблица и индекс соответствия' },
  { icon: 'graduation-cap', name: 'Обучение', note: 'Обучение и проверка знаний' },
  { icon: 'clipboard-text', name: 'СОУТ', note: 'Сроки, классы, декларация' },
  { icon: 'warning', name: 'ОПР (риски)', note: 'Уровни рисков и план мер' },
  { icon: 'bell', name: 'Уведомления', note: 'Напоминания о сроках' },
  { icon: 'chat-circle', name: 'Обратная связь', note: 'Вопросы ответственным' },
  { icon: 'book-open', name: 'Инструкция', note: 'Как работать с порталом' },
  { icon: 'barbell', name: 'Тренинг обучения', note: 'Практические занятия' },
]

const FAQ = [
  ['Что такое СОУТ?', 'Специальная оценка условий труда: обязательная процедура измерения вредных и опасных факторов на рабочих местах. Плановая проводится не реже раза в 5 лет.'],
  ['Что такое ОПР?', 'Оценка профессиональных рисков: выявление опасностей на рабочих местах, оценка уровня рисков и план мер по их снижению. Периодичность задаёт работодатель.'],
  ['Что такое аналогичные рабочие места?', 'Места с одинаковыми условиями и оборудованием. Замеры проводят на 20 % таких мест, но не менее чем на двух, и результат распространяют на все.'],
  ['Как обновить индекс соответствия офиса?', 'Заполните сводную таблицу «Чек-лист обязательных документов» и загрузите её в разделе «Документы». Индекс равен доле документов со статусом «Есть».'],
  ['Почему офис подсвечен красным?', 'Индекс ниже 70 %, срок СОУТ истёк, пересмотр ОПР просрочен или есть другое критичное замечание. Подробности — в блоке «Сроки и нарушения» на дашборде.'],
  ['Где посмотреть, каких документов не хватает?', 'На дашборде нажмите на ячейку тепловой карты: откроется чек-лист офиса по выбранному направлению.'],
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
                <button key={i.key} type="button" className={`nav-item ${page === i.key ? 'active' : ''}`}
                        aria-current={page === i.key ? 'page' : undefined} onClick={() => setPage(i.key)}>
                  <Icon name={i.icon} size={20} />
                  {i.label}
                  {i.soon && <span className="nav-soon">скоро</span>}
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
            {MODULES.map(m => (
              <article key={m.name} className="module-card">
                <span className="module-icon"><Icon name={m.icon} size={24} /></span>
                <div>
                  <div className="module-name">{m.name}</div>
                  <div className="muted">{m.note}</div>
                </div>
              </article>
            ))}
          </div>
        )}

        {page === 'feedback' && (
          <section className="section">
            <h2>Частые вопросы</h2>
            <div className="faq">
              {FAQ.map(([q, a]) => (
                <article key={q} className="faq-item"><h3>{q}</h3><p>{a}</p></article>
              ))}
            </div>
          </section>
        )}

        {current?.soon && (
          <section className="section empty-state">
            <h2>Раздел «{current.label}» в разработке</h2>
            <p>Документы по этому направлению уже видны в чек-листе офиса: откройте «Документы» и выберите раздел в фильтре.</p>
            <button className="btn" onClick={() => setPage('documents')}>Открыть документы</button>
          </section>
        )}
      </main>
    </div>
  )
}
