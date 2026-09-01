import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'

const PREFERENCES = [
  { key: 'task_assignments', label: 'Task assignments', description: 'Email and in-app alerts when a task is assigned to you.' },
  { key: 'submission_reviews', label: 'Submission reviews', description: 'Alerts when a reviewer action is taken on your submissions.' },
  { key: 'task_deadlines', label: 'Deadlines & overdue', description: 'Reminders as task deadlines approach or pass.' },
  { key: 'admin_announcements', label: 'General announcements', description: 'Platform updates and administrator messages.' },
]

// Surface the actual server-side reason instead of one opaque string.
// The preferences endpoint rarely returns a `detail` key on failure: DRF
// answers validation problems with field-keyed errors (HTTP 400), expired
// sessions answer 401, and network/CORS failures have no response body at
// all. Resolving each shape keeps the save error honest and actionable.
function resolveSaveError(error) {
  const data = error?.response?.data
  if (data?.detail) return String(data.detail)
  if (data && typeof data === 'object') {
    const fieldMessages = Object.entries(data)
      .map(([field, messages]) => (
        `${field.replace(/_/g, ' ')}: ${Array.isArray(messages) ? messages.join(' ') : String(messages)}`
      ))
      .join('; ')
    if (fieldMessages) return `Your changes were not saved — ${fieldMessages}.`
  }
  if (error?.response) {
    return `Could not save your notification preferences (HTTP ${error.response.status}). Please try again.`
  }
  return 'Could not reach the server. Check your connection and try again.'
}

export default function NotificationSettings() {
  const [prefs, setPrefs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.get('/auth/me/notification-preferences/')
      .then(({ data }) => { if (!cancelled) setPrefs(data) })
      .catch((err) => { if (!cancelled) setLoadError(err.response?.data?.detail || 'Notification settings could not be loaded.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // The success confirmation is subtle and dismisses itself.
  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(''), 4000)
    return () => window.clearTimeout(timer)
  }, [notice])

  function toggle(key) {
    setNotice('')
    setSaveError('')
    setPrefs((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  function save(event) {
    event.preventDefault()
    if (!prefs || saving) return
    setSaving(true)
    setNotice('')
    setSaveError('')
    const payload = Object.fromEntries(PREFERENCES.map(({ key }) => [key, !!prefs[key]]))
    api.patch('/auth/me/notification-preferences/', payload)
      .then(({ data }) => {
        setPrefs(data)
        setNotice('Notification preferences saved.')
      })
      .catch((err) => setSaveError(resolveSaveError(err)))
      .finally(() => setSaving(false))
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="notifications" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Account</p>
          <h1>Notification Settings</h1>
          <p>Control which TaskBoard notifications you receive. These preferences apply only to your account.</p>
        </div>
      </section>

      {loadError && <p className="error-banner" role="alert">{loadError}</p>}

      {loading ? (
        <>
          <div className="skeleton-block skeleton-toolbar" aria-hidden="true" />
          <div className="skeleton-block skeleton-problem-card" aria-hidden="true" />
        </>
      ) : prefs && (
        <form className="surface-panel settings-panel" onSubmit={save}>
          <div className="settings-panel-heading">
            <p className="section-kicker">Preferences</p>
            <p className="panel-footnote">Toggle a preference on or off, then save your changes. Turning a preference off stops those notifications for you only.</p>
          </div>

          <div className="pref-list">
            {PREFERENCES.map(({ key, label, description }) => (
              <label className="pref-row" key={key}>
                <span className="pref-text">
                  <strong>{label}</strong>
                  <small>{description}</small>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  className="switch"
                  checked={!!prefs[key]}
                  onChange={() => toggle(key)}
                  aria-label={label}
                />
              </label>
            ))}
          </div>

          <div className="settings-save-row">
            {notice && <p className="form-success" role="status">{notice}</p>}
            {saveError && <p className="form-error" role="alert">{saveError}</p>}
            <button type="submit" className="button-primary" disabled={saving} aria-busy={saving}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      )}
    </main>
  )
}