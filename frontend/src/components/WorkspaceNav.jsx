import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { ThemeToggle } from '../theme'
import NotificationBell from './NotificationBell'
import GlobalSearch from './GlobalSearch'

const IconMenu = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
)
const IconClose = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
)
const IconSearch = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="15.657" y2="15.657" /></svg>
)
const IconBell = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></svg>
)

function getGroups(isAdmin) {
  const main = [
    { href: '/dashboard', label: 'Dashboard', key: 'dashboard', icon: 'home' },
    { href: '/leaderboard', label: 'Leaderboard', key: 'leaderboard', icon: 'trophy' },
    { href: '/tasks', label: 'Tasks', key: 'tasks', icon: 'list' },
    { href: '/my-tasks', label: 'My tasks', key: 'my-tasks', icon: 'list', userOnly: true },
    { href: '/coding/problems', label: 'Coding Problems', key: 'coding', icon: 'code', userOnly: true },
    { href: '/settings/notifications', label: 'Notifications', key: 'notifications', icon: 'bell' },
  ]
  const workspace = [
    { href: '/admin/create-task', label: 'Create task', key: 'create-task', icon: 'plus', adminOnly: true },
    { href: '/admin/assignments', label: 'Assignments', key: 'assignments', icon: 'users', adminOnly: true },
    { href: '/admin/submissions', label: 'Submissions', key: 'submissions', icon: 'doc', adminOnly: true },
  ]
  const coding = [
    { href: '/admin/coding/problems', label: 'Coding problems', key: 'coding-problems', icon: 'code', adminOnly: true },
    { href: '/admin/coding/submissions', label: 'Code Reviews', key: 'coding-submissions', icon: 'search', adminOnly: true },
  ]
  const admin = [
    { href: '/admin/users', label: 'Users', key: 'users', icon: 'users', adminOnly: true },
    { href: '/admin/monitoring', label: 'Monitoring', key: 'monitoring', icon: 'chart', adminOnly: true },
  ]
  const filter = (arr) => arr.filter((l) => l.adminOnly ? isAdmin : (l.userOnly ? !isAdmin : true))
  return { main: filter(main), workspace: filter(workspace), coding: filter(coding), admin: filter(admin) }
}

const ICON_PATHS = {
  home: <path d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h4v-6h4v6h4a1 1 0 001-1V10" />,
  trophy: <path d="M8 21h8M12 17v4M7 4h10v6a5 5 0 01-10 0V4zM7 5H4v2a3 3 0 003 3M17 5h3v2a3 3 0 01-3 3" />,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  code: <path d="M16 18l6-6-6-6M8 6l-6 6 6 6" />,
  bell: <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />,
  plus: <path d="M12 5v14M5 12h14" />,
  users: <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />,
  doc: <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8" />,
  search: <path d="M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35" />,
  chart: <path d="M18 20V10M12 20V4M6 20v-6" />,
}

const NavIcon = ({ name }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {ICON_PATHS[name] || ICON_PATHS.list}
  </svg>
)

function NavSection({ title, items, active, onSelect }) {
  if (!items.length) return null
  return (
    <div className="nav-drawer-section">
      <div className="nav-drawer-section-title">{title}</div>
      {items.map((item) => (
        <a key={item.key} href={item.href} onClick={onSelect}
          className={`nav-drawer-item${active === item.key ? ' nav-drawer-item-active' : ''}`}
          aria-current={active === item.key ? 'page' : undefined}>
          <span className="nav-drawer-item-icon"><NavIcon name={item.icon} /></span>
          <span>{item.label}</span>
        </a>
      ))}
    </div>
  )
}

export default function WorkspaceNav({ active = 'tasks' }) {
  const { user, isAdmin, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)

  useEffect(() => {
    if (!open) return undefined
    document.body.classList.add('nav-drawer-open')
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.classList.remove('nav-drawer-open')
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const groups = getGroups(isAdmin)
  const role = isAdmin ? 'Administrator' : 'Member'

  return (
    <header className="app-header app-header--compact">
      <a className="brand" href="/dashboard" aria-label="TaskBoard home">
        <span className="brand-mark" aria-hidden="true">T</span><span>TaskBoard</span>
      </a>

      <div className="header-actions">
        <GlobalSearch />
        <NotificationBell />
        <ThemeToggle />
        <span className="header-divider" aria-hidden="true" />
        <div className="header-user" title={user?.username || 'Account'}>
          <span className="header-avatar" aria-hidden="true">{user?.username ? user.username.charAt(0).toUpperCase() : 'A'}</span>
          <span className="header-user-meta"><strong>{user?.username || 'Account'}</strong><small>{role}</small></span>
        </div>
        <button type="button" className="header-icon-btn header-menu-btn"
          aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={open} aria-controls="workspace-drawer" aria-haspopup="true"
          onClick={() => setOpen((v) => !v)}>
          {open ? <IconClose /> : <IconMenu />}
        </button>
      </div>

      <div id="workspace-drawer" className={`nav-drawer${open ? ' nav-drawer--open' : ''}`} aria-hidden={!open}>
        <div className="nav-drawer-backdrop" onClick={close} />
        <aside className="nav-drawer-panel" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="nav-drawer-header">
            <span className="brand"><span className="brand-mark" aria-hidden="true">T</span><span>Navigation</span></span>
            <button type="button" className="header-icon-btn" aria-label="Close navigation menu" onClick={close}><IconClose /></button>
          </div>

          <nav className="nav-drawer-body" aria-label="Workspace sections">
            <NavSection title="Main" items={groups.main} active={active} onSelect={close} />
            <NavSection title="Workspace" items={groups.workspace} active={active} onSelect={close} />
            <NavSection title="Coding" items={groups.coding} active={active} onSelect={close} />
            <NavSection title="Admin" items={groups.admin} active={active} onSelect={close} />
          </nav>

          <div className="nav-drawer-footer">
            <div className="header-user">
              <span className="header-avatar" aria-hidden="true">{user?.username ? user.username.charAt(0).toUpperCase() : 'A'}</span>
              <span className="header-user-meta"><strong>{user?.username || 'Account'}</strong><small>{role}</small></span>
            </div>
            <button type="button" className="button-muted button-small nav-drawer-logout" onClick={async () => { await logout(); window.location.replace('/login') }}>
              Log out
            </button>
          </div>
        </aside>
      </div>
    </header>
  )
}
