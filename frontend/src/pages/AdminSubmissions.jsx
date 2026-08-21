import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'

export default function AdminSubmissions() {
  const [submissions, setSubmissions] = useState([])
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadSubmissions() {
    setLoading(true)
    try { setSubmissions((await api.get('/admin/submissions/')).data) } catch { setError('Submissions could not be loaded.') } finally { setLoading(false) }
  }

  useEffect(() => { loadSubmissions() }, [])

  async function review(submission, status) {
    const feedback = window.prompt(status === 'APPROVED' ? 'Optional approval feedback:' : 'Rejection feedback:')
    if (feedback === null) return
    setPending(submission.id)
    setError('')
    try { await api.patch(`/admin/submissions/${submission.id}/`, { status, feedback }); setNotice(`Submission ${status.toLowerCase()}.`); await loadSubmissions() } catch { setError('Submission review could not be saved.') } finally { setPending(null) }
  }

  return <main className="workspace-shell"><WorkspaceNav active="submissions" /><section className="page-intro"><div><p className="eyebrow">Administration</p><h1>Submissions</h1><p>Review submitted work and provide feedback.</p></div><div className="page-summary"><strong>{submissions.length}</strong><span>submissions</span></div></section><section className="admin-panel admin-wide-panel surface-panel">{loading && <p className="state-message">Loading submissions...</p>}{!loading && !error && submissions.length === 0 && <p className="empty-state"><strong>No submissions yet</strong><span>Submitted work will appear here for review.</span></p>}{error && <p className="form-error" role="alert">{error}</p>}<div className="submission-list">{submissions.map((submission) => <article className="submission-card" key={submission.id}><div className="submission-card-header"><div><p className="section-kicker">{submission.status === 'PENDING' ? 'Pending review' : submission.status}</p><h2>{submission.task_title}</h2><p className="submission-owner">{submission.username} · {new Date(submission.submitted_at).toLocaleDateString()}</p></div><span className={`submission-status submission-${submission.status.toLowerCase()}`}>{submission.status}</span></div><div className="submission-links"><a href={submission.git_url} target="_blank" rel="noreferrer">Git repository</a><a href={submission.linkedin_url} target="_blank" rel="noreferrer">LinkedIn profile</a></div>{submission.note && <p className="submission-note">{submission.note}</p>}{submission.feedback && <p className="submission-feedback">Feedback: {submission.feedback}</p>}{submission.status === 'PENDING' && <div className="submission-review-actions"><button type="button" disabled={pending === submission.id} onClick={() => review(submission, 'APPROVED')}>Approve</button><button type="button" className="button-danger" disabled={pending === submission.id} onClick={() => review(submission, 'REJECTED')}>Reject</button></div>}</article>)}</div></section>{(notice || error) && <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>{error || notice}</p>}</main>
}
