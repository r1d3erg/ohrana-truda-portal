// Экран входа и смены пароля (временный пароль после создания или сброса).
import { useState } from 'react'
import { api } from '../api.js'
import { ErrorBox } from '../components.jsx'
import { Icon } from '../icons.jsx'

export function LoginScreen({ onLogin }) {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onLogin(await api.login(login, password))
    } catch (err) {
      setError(err)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-screen">
      <form className="login-box" onSubmit={submit}>
        <span className="login-icon"><Icon name="hard-hat" size={24} /></span>
        <h1>Охрана труда</h1>
        <p className="muted">Документы, СОУТ и оценка рисков по всем офисам в одном месте.</p>
        <label className="fld">
          <span>Логин</span>
          <input className="input" autoComplete="username" autoFocus required maxLength={64}
                 value={login} onChange={e => setLogin(e.target.value)} />
        </label>
        <label className="fld">
          <span>Пароль</span>
          <input className="input" type="password" autoComplete="current-password" required maxLength={128}
                 value={password} onChange={e => setPassword(e.target.value)} />
        </label>
        <ErrorBox error={error} />
        <button className="btn" type="submit" disabled={busy}>
          <Icon name="sign-in" size={20} /> {busy ? 'Вход…' : 'Войти'}
        </button>
        <p className="muted login-hint">Нет учётной записи или забыли пароль — обратитесь в службу охраны труда.</p>
      </form>
    </main>
  )
}

export function ChangePasswordForm({ user, forced, onDone, onCancel, onLogout }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (next !== repeat) { setError(new Error('Новый пароль и повтор не совпадают')); return }
    setBusy(true)
    try {
      onDone(await api.changePassword(current, next))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="login-box" onSubmit={submit}>
      <span className="login-icon"><Icon name="lock" size={24} /></span>
      <h1>{forced ? 'Смените временный пароль' : 'Смена пароля'}</h1>
      <p className="muted">
        {forced ? `${user.full_name || user.login}, для продолжения задайте свой пароль. ` : ''}
        Не короче 10 символов, буквы и цифры или символы, не совпадает с логином.
      </p>
      <input type="text" autoComplete="username" value={user.login} readOnly hidden />
      <label className="fld">
        <span>{forced ? 'Временный пароль' : 'Текущий пароль'}</span>
        <input className="input" type="password" autoComplete="current-password" required maxLength={128}
               value={current} onChange={e => setCurrent(e.target.value)} autoFocus />
      </label>
      <label className="fld">
        <span>Новый пароль</span>
        <input className="input" type="password" autoComplete="new-password" required minLength={10} maxLength={128}
               value={next} onChange={e => setNext(e.target.value)} />
      </label>
      <label className="fld">
        <span>Повторите новый пароль</span>
        <input className="input" type="password" autoComplete="new-password" required minLength={10} maxLength={128}
               value={repeat} onChange={e => setRepeat(e.target.value)} />
      </label>
      <ErrorBox error={error} />
      <div className="upload-row">
        <button className="btn" type="submit" disabled={busy}>{busy ? 'Сохранение…' : 'Сменить пароль'}</button>
        {forced
          ? <button className="btn btn-secondary" type="button" onClick={onLogout}>Выйти</button>
          : <button className="btn btn-secondary" type="button" onClick={onCancel}>Отмена</button>}
      </div>
    </form>
  )
}
