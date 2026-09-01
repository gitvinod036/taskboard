import { useCallback, useEffect, useState } from 'react'
import api from '../services/api'

const IconBell = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
)
const IconClose = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

function timeAgo(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`
  return `${Math.floor(seconds / 86400)} days ago`
}

/** Bell button + right-side notifications drawer for the workspace header. */
export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busyAll, setBusyAll] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/auth/me/notifications/')
      setItems(data?.results || [])
      setUnread(data?.unread_count || 0)
    } catch (_) {
      setError('Unable to load notifications.')
    } finally {
      setLoading(false)
    }
  }, [])

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next) load()
  }

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    document.body.classList.add('nav-drawer-open')
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.classList.remove('nav-drawer-open')
    }
  }, [open])

  async function openNotification(item) {
    if (!item.is_read) {
      setItems((current) => current.map((n) => (n.id === item.id ? { ...n, is_read: true } : n)))
      setUnread((current) => Math.max(0, current - 1))
      try {
        const { data } = await api.post('/auth/me/notifications/mark-read/', { id: item.id })
        setUnread(data?.unread_count ?? 0)
      } catch (_) { /* non-fatal */ }
    }
    setOpen(false)
    if (item.url) window.location.href = item.url
  }

  async function markAllRead() {
    setBusyAll(true)
    try {
      await api.post('/auth/me/notifications/mark-read/', { all: true })
      setItems((current) => current.map((n) => ({ ...n, is_read: true })))
      setUnread(0)
    } catch (_) {
      setError('Could not mark notifications as read.')
    } finally {
      setBusyAll(false)
    }
  }

  return (
    <>
      <button type="button" className="header-icon-btn notification-bell" aria-label={`Notifications (${unread} unread)`} title="Notifications" aria-expanded={open} aria-controls="notification-drawer" onClick={toggle}>
        <IconBell />
        {unread > 0 && <span className="notification-badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
      </button>

      <div id="notification-drawer" className={`nav-drawer${open ? ' nav-drawer--open' : ''}`} aria-hidden={!open}>
        <div className="nav-drawer-backdrop" onClick={() => setOpen(false)} />
        <aside className="nav-drawer-panel notification-drawer" role="dialog" aria-modal="true" aria-label="Notifications">
          <div className="nav-drawer-header">
            <strong className="notification-title">Notifications</strong>
            <button type="button" className="header-icon-btn" aria-label="Close notifications" onClick={() => setOpen(false)}><IconClose /></button>
          </div>

          <div className="notification-actions">
            <button type="button" className="button-muted button-small" disabled={busyAll || unread === 0} onClick={markAllRead}>
              {busyAll ? 'Marking…' : 'Mark all as read'}
            </button>
          </div>

          <div className="nav-drawer-body notification-list">
            {loading && (
              <div className="notification-skeleton" aria-hidden="true">
                <span className="skeleton-line" /><span className="skeleton-line short" />
                <span className="skeleton-line" /><span className="skeleton-line short" />
              </div>
            )}

            {!loading && error && (
              <div className="notification-state">
                <strong>Unable to load notifications</strong>
                <span>{error}</span>
                <button type="button" className="button-muted button-small" onClick={load}>Retry</button>
              </div>
            )}

            {!loading && !error && items.length === 0 && (
              <div className="notification-state">
                <strong>You're all caught up.</strong>
                <span>New task and review updates will appear here.</span>
              </div>
            )}

            {!loading && !error && items.map((item) => (
              <button type="button" key={item.id}
                className={`notification-item${item.is_read ? '' : ' notification-item-unread'}`}
                onClick={() => openNotification(item)}>
                <span className="notification-item-title">
                  {!item.is_read && <span className="notification-dot" aria-label="Unread" />}
                  {item.title}
                </span>
                <span className="notification-item-message">{item.message}</span>
                <span className="notification-item-time">{timeAgo(item.created_at)}</span>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </>
  )
}
