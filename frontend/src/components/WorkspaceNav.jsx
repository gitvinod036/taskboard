import { useAuth } from '../context/AuthContext'

export default function WorkspaceNav({ active = 'tasks' }) {
  const { user, isAdmin, logout } = useAuth()

  async function handleLogout() {
    await logout()
    window.location.replace('/login')
  }

  const links = [
    { href: '/dashboard', label: 'Dashboard', key: 'dashboard' },
    { href: '/tasks', label: 'Tasks', key: 'tasks' },
    ...(!isAdmin ? [{ href: '/tasks#my-tasks', label: 'My tasks', key: 'my-tasks' }] : []),
    ...(isAdmin ? [{ href: '/admin/users', label: 'Users', key: 'users' }, { href: '/admin/assignments', label: 'Assignments', key: 'assignments' }, { href: '/admin/submissions', label: 'Submissions', key: 'submissions' }] : []),
  ]

  return (
    <header className="app-header">
      <a className="brand" href="/dashboard" aria-label="TaskBoard home"><span className="brand-mark" aria-hidden="true">T</span><span>TaskBoard</span></a>
      <nav className="primary-nav" aria-label="Primary navigation">
        {links.map((link) => <a className={active === link.key ? 'nav-link nav-link-active' : 'nav-link'} href={link.href} key={link.key}>{link.label}</a>)}
      </nav>
      <div className="account-nav"><span className="account-name">{user?.username || 'Account'}<small>{isAdmin ? 'Administrator' : 'Member'}</small></span><button type="button" className="button-muted button-small" onClick={handleLogout}>Log out</button></div>
    </header>
  )
}