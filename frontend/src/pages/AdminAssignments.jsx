import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'

export default function AdminAssignments() {
  const { user, logout } = useAuth()
  const [assignments, setAssignments] = useState([])
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadAssignments() { setLoading(true); try { setAssignments((await api.get('/admin/assignments/')).data) } catch { setError('Assignments could not be loaded.') } finally { setLoading(false) } }
  useEffect(() => { loadAssignments() }, [])

  async function unassign(assignment) {
    if (!window.confirm(`Remove ${assignment.user.name} from ${assignment.task.title}?`)) return
    setPending(assignment.id); setError('')
    try { await api.delete(`/admin/users/${assignment.user.id}/tasks/${assignment.task.id}/`); setNotice('Assignment removed.'); await loadAssignments() } catch (requestError) { setError(requestError.response?.data?.detail || 'Assignment could not be removed.') } finally { setPending(null) }
  }

  return <main className="workspace-shell"><WorkspaceNav active="assignments" /><section className="page-intro"><div><p className="eyebrow">Administration</p><h1>Assignments</h1><p>See who owns each task and make precise assignment changes.</p></div><div className="page-summary"><strong>{assignments.length}</strong><span>total assignments</span></div></section><section className="admin-panel admin-wide-panel surface-panel"><div className="section-heading"><div><p className="section-kicker">Overview</p><h2>All assignments</h2></div></div>{loading && <p className="state-message">Loading assignments...</p>}{!loading && assignments.length === 0 && <p className="empty-state"><strong>No assignments yet</strong><span>Assignments will appear here when users claim tasks.</span></p>}{!loading && assignments.length > 0 && <div className="assignment-table">{assignments.map((assignment) => <article className="assignment-row" key={assignment.id}><div><strong>{assignment.task.title}</strong><small>{assignment.user.name} · {assignment.user.email || 'No email'}</small></div><div className="assignment-actions"><small>Assigned {new Date(assignment.assigned_date).toLocaleDateString()}</small><button type="button" className="button-muted" disabled={pending === assignment.id} onClick={() => unassign(assignment)}>{pending === assignment.id ? 'Removing...' : 'Unassign'}</button></div></article>)}</div>}</section>{(notice || error) && <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>{error || notice}</p>}</main>
}