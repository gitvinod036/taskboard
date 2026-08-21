import { useState } from 'react'

import api from '../../services/api'

export default function TaskSubmissionModal({ assignment, onClose, onSubmitted }) {
  const [form, setForm] = useState({
    git_url: assignment.submission?.git_url || '',
    linkedin_url: assignment.submission?.linkedin_url || '',
    note: assignment.submission?.note || '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await api.post(`/tasks/${assignment.task.id}/submit/`, form)
      onSubmitted()
      onClose()
    } catch (requestError) {
      const data = requestError.response?.data || {}
      setError(data.git_url?.[0] || data.linkedin_url?.[0] || data.detail || 'Submission could not be sent.')
    } finally {
      setLoading(false)
    }
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className="submission-modal" role="dialog" aria-modal="true" aria-labelledby="submission-title"><div className="modal-heading"><div><p className="section-kicker">Task submission</p><h2 id="submission-title">Submit {assignment.task.title}</h2></div><button type="button" className="modal-close" aria-label="Close submission form" onClick={onClose}>×</button></div><form onSubmit={submit}><label htmlFor="git-url">Git repository URL<input id="git-url" type="url" required placeholder="https://github.com/..." value={form.git_url} onChange={(event) => setForm({ ...form, git_url: event.target.value })} /></label><label htmlFor="linkedin-url">LinkedIn URL<input id="linkedin-url" type="url" required placeholder="https://www.linkedin.com/in/..." value={form.linkedin_url} onChange={(event) => setForm({ ...form, linkedin_url: event.target.value })} /></label><label htmlFor="submission-note">Note <span className="optional">(optional)</span><textarea id="submission-note" rows="4" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>{error && <p className="form-error" role="alert">{error}</p>}<div className="form-actions"><button type="submit" disabled={loading}>{loading ? 'Submitting...' : 'Submit for review'}</button><button type="button" className="button-muted" onClick={onClose}>Cancel</button></div></form></section></div>
}
