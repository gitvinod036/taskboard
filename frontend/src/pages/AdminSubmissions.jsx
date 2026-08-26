import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import Pagination from '../components/Pagination'

export default function AdminSubmissions() {
  const [submissions, setSubmissions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })
  const [reviewTarget, setReviewTarget] = useState(null)
  const [reviewNote, setReviewNote] = useState('')
  const [submittingReview, setSubmittingReview] = useState(false)
  const [openDetailId, setOpenDetailId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  async function loadSubmissions(pageNumber = page) {
    setLoading(true)
    try {
      // Paginated endpoint: newest submissions first (backend ordering).
      const { data } = await api.get('/admin/submissions/', { params: { page: pageNumber } })
      setSubmissions(Array.isArray(data?.results) ? data.results : [])
      setPagination({ count: data?.count ?? 0, next: data?.next ?? null, previous: data?.previous ?? null })
    } catch { setError('Submissions could not be loaded.') } finally { setLoading(false) }
  }

  useEffect(() => { loadSubmissions(page) }, [page])

  async function toggleDetail(submission) {
    if (openDetailId === submission.id) {
      setOpenDetailId(null)
      setDetail(null)
      setDetailError('')
      return
    }
    setOpenDetailId(submission.id)
    setDetail(null)
    setDetailError('')
    setDetailLoading(true)
    try {
      const { data } = await api.get(`/admin/submissions/${submission.id}/`)
      setDetail(data)
    } catch {
      setDetailError('Submission details could not be loaded.')
    } finally {
      setDetailLoading(false)
    }
  }


  function openReview(submission, status) {
    setError('')
    setReviewNote('')
    setReviewTarget({ submission, status })
  }

  function closeReview() {
    if (submittingReview) return
    setReviewTarget(null)
    setReviewNote('')
  }

  async function submitReview(event) {
    event.preventDefault()
    // A review comment is optional: admins may approve/reject with or without one.
    const { submission, status } = reviewTarget
    setSubmittingReview(true)
    setError('')
    try {
      await api.patch(`/admin/submissions/${submission.id}/`, { status, feedback: reviewNote })
      setNotice(`Submission ${status.toLowerCase()}.`)
      setReviewTarget(null)
      setReviewNote('')
      await loadSubmissions()
    } catch {
      setError('Submission review could not be saved.')
    } finally {
      setSubmittingReview(false)
    }
  }

  return <main className="workspace-shell"><WorkspaceNav active="submissions" /><section className="page-intro"><div><p className="eyebrow">Administration</p><h1>Submissions</h1><p>Review submitted work and provide feedback.</p></div><div className="page-summary"><strong>{pagination.count}</strong><span>submissions</span></div></section><section className="admin-panel admin-wide-panel surface-panel">{loading && <p className="state-message">Loading submissions...</p>}{!loading && !error && submissions.length === 0 && <p className="empty-state"><strong>No submissions yet</strong><span>Submitted work will appear here for review.</span></p>}{error && <p className="form-error" role="alert">{error}</p>}<div className="submission-list">{submissions.map((submission) => <article className="submission-card" key={submission.id}><div className="submission-card-header"><div><p className="section-kicker">{submission.status === 'PENDING' ? 'Pending review' : submission.status}</p><h2>{submission.task_title}</h2><p className="submission-owner">{submission.username} · {new Date(submission.submitted_at).toLocaleDateString()}</p></div><span className={`submission-status submission-${submission.status.toLowerCase()}`}>{submission.status}</span></div><div className="submission-links"><a href={submission.git_url} target="_blank" rel="noreferrer">Git repository</a><a href={submission.linkedin_url} target="_blank" rel="noreferrer">LinkedIn profile</a></div><button type="button" className="button-muted" aria-expanded={openDetailId === submission.id} onClick={() => toggleDetail(submission)}>{openDetailId === submission.id ? 'Hide details' : 'View details'}</button>{openDetailId === submission.id && <div className="submission-detail" role="region" aria-label={`Submission ${submission.id} details`}>{detailLoading && <p className="state-message">Loading details...</p>}{detailError && <p className="form-error" role="alert">{detailError}</p>}{!detailLoading && !detailError && detail && <dl><div><dt>Submission ID</dt><dd>{detail.id}</dd></div><div><dt>Task ID</dt><dd>{detail.task}</dd></div><div><dt>User ID</dt><dd>{detail.user}</dd></div><div><dt>Status</dt><dd>{detail.status}</dd></div><div><dt>Submitted</dt><dd>{new Date(detail.submitted_at).toLocaleString()}</dd></div><div><dt>Note</dt><dd>{detail.note || '—'}</dd></div><div><dt>Feedback</dt><dd>{detail.feedback || '—'}</dd></div><div><dt>Reviewed at</dt><dd>{detail.reviewed_at ? new Date(detail.reviewed_at).toLocaleString() : 'Not reviewed yet'}</dd></div></dl>}</div>}{submission.note && <p className="submission-note">{submission.note}</p>}{submission.feedback && <p className="submission-feedback">Feedback: {submission.feedback}</p>}{submission.status === 'PENDING' && <div className="submission-review-actions"><button type="button" onClick={() => openReview(submission, 'APPROVED')}>Approve</button><button type="button" className="button-danger" onClick={() => openReview(submission, 'REJECTED')}>Reject</button></div>}</article>)}</div>{!loading && !error && <Pagination currentPage={page} hasNext={Boolean(pagination.next)} hasPrevious={Boolean(pagination.previous)} disabled={loading} onNext={() => setPage((current) => current + 1)} onPrevious={() => setPage((current) => Math.max(1, current - 1))} />}</section>{(notice || error) && <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>{error || notice}</p>}
{reviewTarget && (
  <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeReview() }}>
    <section className="submission-modal" role="dialog" aria-modal="true" aria-labelledby="review-submission-title">
      <div className="modal-heading">
        <div>
          <p className="section-kicker">{reviewTarget.status === 'APPROVED' ? 'Approving submission' : 'Rejecting submission'}</p>
          <h2 id="review-submission-title">Review Submission</h2>
          <p className="submission-owner">{reviewTarget.submission.task_title} · {reviewTarget.submission.username}</p>
        </div>
        <button type="button" className="modal-close" aria-label="Close review dialog" onClick={closeReview}>×</button>
      </div>
      <form onSubmit={submitReview}>
        <label htmlFor="review-feedback">Review / Comment <span className="optional">(Optional)</span>
          <textarea id="review-feedback" rows="4" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="form-actions">
          <button
            type="submit"
            className={reviewTarget.status === 'REJECTED' ? 'button-danger' : undefined}
            disabled={submittingReview}
            aria-busy={submittingReview}
          >
            {submittingReview ? 'Saving...' : reviewTarget.status === 'APPROVED' ? 'Confirm Approve' : 'Confirm Reject'}
          </button>
          <button type="button" className="button-muted" disabled={submittingReview} onClick={closeReview}>Cancel</button>
        </div>
      </form>
    </section>
  </div>
)}
</main>
}
