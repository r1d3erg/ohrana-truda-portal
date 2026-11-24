// Пользователи и роли (только служба охраны труда). Права ролей — docs/auth.md.
import { useCallback, useEffect, useState } from 'react'
import { api, fmtDateTime } from '../api.js'
import { ErrorBox, Skeleton } from '../components.jsx'
import { Fieldset, Modal } from '../registerParts.jsx'

const ROLE_HELP = {
  admin: 'Всё: пользователи, офисы, загрузки по любому офису, удаление записей.',
  responsible: 'Видит все офисы, изменяет данные только своих: чек-лист, СОУТ, ОПР, ПБ, ЭБ, ГО ЧС.',
  viewer: 'Только просмотр: дашборд, документы, сроки. Для руководителей.',
}

function UserForm({ user, roles, offices, onClose, onSaved }) {
  const isNew = !user
  const [form, setForm] = useState({
    login: user?.login || '',
    full_name: user?.full_name || '',
    role: user?.role || 'responsible',
    offices: user?.offices || [],
    password: '',
    is_active: user?.is_active ?? true,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const toggleOffice = (code) => set('offices', form.offices.includes(code)
    ? form.offices.filter(c => c !== code) : [...form.offices, code])

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      if (isNew) {
        await api.createUser({ login: form.login, full_name: form.full_name, role: form.role,
                               password: form.password, offices: form.role === 'responsible' ? form.offices : [] })
      } else {
        const body = { full_name: form.full_name, role: form.role, is_active: form.is_active,
                       offices: form.role === 'responsible' ? form.offices : [] }
        if (form.password) body.password = form.password
        await api.updateUser(user.id, body)
      }
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={isNew ? 'Новый пользователь' : `Пользователь ${user.login}`} onClose={onClose}
           footer={<>
             <button className="btn btn-secondary" onClick={onClose}>Отмена</button>
             <button className="btn" disabled={busy} onClick={save}>{busy ? 'Сохранение…' : 'Сохранить'}</button>
           </>}>
      <ErrorBox error={error} />
      <Fieldset title="Учётная запись">
        <label className="fld">
          <span>Логин</span>
          <input className="input" value={form.login} disabled={!isNew} maxLength={64} autoComplete="off"
                 onChange={e => set('login', e.target.value.toLowerCase())} />
          <span className="fld-hint">Латиница, цифры, «.», «_», «-», «@». Например: ivanov.i</span>
        </label>
        <label className="fld">
          <span>ФИО</span>
          <input className="input" value={form.full_name} maxLength={255} onChange={e => set('full_name', e.target.value)} />
        </label>
        <label className="fld">
          <span>{isNew ? 'Временный пароль' : 'Сбросить пароль (временный)'}</span>
          <input className="input" type="text" autoComplete="new-password" value={form.password} maxLength={128}
                 placeholder={isNew ? '' : 'Оставьте пустым, чтобы не менять'}
                 onChange={e => set('password', e.target.value)} />
          <span className="fld-hint">Не короче 10 символов. Передайте пользователю лично — при первом входе он задаст свой.</span>
        </label>
        {!isNew && (
          <label className="fld fld-check fld-wide">
            <span><input type="checkbox" checked={form.is_active} onChange={e => set('is_active', e.target.checked)} /> Учётная запись активна</span>
            <span className="fld-hint">Снимите, чтобы заблокировать вход. Открытые сессии пользователя закроются.</span>
          </label>
        )}
      </Fieldset>
      <Fieldset title="Роль">
        {Object.entries(roles).map(([k, label]) => (
          <label key={k} className="fld fld-check fld-wide">
            <span><input type="radio" name="role" checked={form.role === k} onChange={() => set('role', k)} /> {label}</span>
            <span className="fld-hint">{ROLE_HELP[k]}</span>
          </label>
        ))}
      </Fieldset>
      {form.role === 'responsible' && (
        <Fieldset title={`Офисы ответственного · выбрано ${form.offices.length}`}>
          {offices.length === 0 && <p className="muted fld-wide">Офисов пока нет.</p>}
          {offices.map(o => (
            <label key={o.code} className="fld fld-check">
              <span><input type="checkbox" checked={form.offices.includes(o.code)} onChange={() => toggleOffice(o.code)} /> {o.code}{o.name && o.name !== o.code ? ` · ${o.name}` : ''}</span>
            </label>
          ))}
        </Fieldset>
      )}
    </Modal>
  )
}

export default function Users({ offices, currentUserId }) {
  const [users, setUsers] = useState(null)
  const [roles, setRoles] = useState({})
  const [error, setError] = useState(null)
  const [modal, setModal] = useState(null)

  const load = useCallback(() => {
    Promise.all([api.users(), api.roles()])
      .then(([u, r]) => { setUsers(u); setRoles(r); setError(null) })
      .catch(setError)
  }, [])
  useEffect(() => { load() }, [load])

  if (error) return <ErrorBox error={error} />
  if (!users) return <div className="section"><Skeleton lines={6} /></div>

  return (
    <>
      <div className="section">
        <div className="section-head">
          <div>
            <h2>Пользователи и роли</h2>
            <p className="muted">Учётные записи создаёт служба охраны труда. Ответственный видит все офисы, но изменяет данные только своих.</p>
          </div>
          <button className="btn" onClick={() => setModal({})}>+ Пользователь</button>
        </div>
        <div className="kpi-grid">
          {Object.entries(roles).map(([k, label]) => (
            <div key={k} className="kpi">
              <div className="kpi-label">{label}</div>
              <div className="kpi-value">{users.filter(u => u.role === k && u.is_active).length}</div>
              <div className="muted">{ROLE_HELP[k]}</div>
            </div>
          ))}
        </div>
        <table className="reg-table">
          <thead><tr><th>Логин</th><th>ФИО</th><th>Роль</th><th>Офисы</th><th>Последний вход</th><th>Статус</th><th></th></tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td><strong>{u.login}</strong>{u.id === currentUserId && <div className="muted">это вы</div>}</td>
                <td>{u.full_name || '—'}</td>
                <td>{u.role_label}</td>
                <td>{u.role === 'responsible' ? (u.offices.length ? u.offices.join(', ') : <span className="lvl-warn">не назначены</span>) : 'все'}</td>
                <td className="muted">{u.last_login_at ? fmtDateTime(u.last_login_at) : 'не входил'}</td>
                <td>
                  {!u.is_active ? <span className="lvl-bad">заблокирован</span>
                    : u.must_change_password ? <span className="lvl-warn">временный пароль</span>
                    : <span className="lvl-good">активен</span>}
                </td>
                <td className="actions"><button className="btn-small" onClick={() => setModal({ user: u })}>Изменить</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {modal && <UserForm user={modal.user} roles={roles} offices={offices}
                          onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />}
    </>
  )
}
