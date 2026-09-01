import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import Pagination from '../components/Pagination'
import { languageDisplayName } from '../languages'

export default function AdminCodingSubmissions() {
  const [submissions, setSubmissions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })
  const [openId, setOpenId] = useState(null)

  function load(pageNumber = page) {
    setLoading(true)
    setError('')
    api.get('/admin/coding/submissions/', { params: { page: pageNumber } })
      .then(({ data }) => {
        setSubmissions(Array.isArray(data?.results) ? data.results : [])
        setPagination({ count: data?.count ?? 0, next: data?.next ?? null, previous: data?.previous ?? null })
      })
      .catch((err) => setError(err.response?.data?.detail || 'Submissions could not be loaded.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(page) }, [page]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />

      <section className="page-intro">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Coding Submissions</h1>
          <p>Review submitted solutions and real execution verdicts.</p>
        </div>
      </section>

      {error && <p className="form-error" role="alert">{error}</p>}
      {loading && <p className="state-message">Loading submissions…</p>}
      {!loading && !error && submissions.length === 0 && (
        <p className="empty-state"><strong>No submissions yet</strong><span>User submissions will appear here.</span></p>
      )}

      {!loading && submissions.map((submission) => (
        <section className="submission-card" key={submission.id}>
          <div className="submission-card-header">
            <div className="submission-card-main">
              <p className="section-kicker">#{submission.id} · {languageDisplayName(submission.language)} · {submission.problem_title}</p>
              <h2>{submission.user?.username || 'Unknown user'}</h2>
              <p className="submission-owner">
                {new Date(submission.created_at).toLocaleString()}
                {submission.execution_time != null && ` · ${submission.execution_time}s`}
                {submission.memory_used != null && ` · ${Math.round(submission.memory_used)} MB`}
                {submission.passed_tests != null && submission.total_tests != null &&
                  ` · ${submission.passed_tests}/${submission.total_tests} tests`}
              </p>
            </div>
            <div className="submission-card-side">
              <span className={`submission-status submission-${String(submission.status).toLowerCase().replace(/_/g, '-')}`}>
                {submission.status_label || submission.status}
              </span>
              <button
                type="button"
                className="button-muted button-small"
                onClick={() => setOpenId(openId === submission.id ? null : submission.id)}
              >
                {openId === submission.id ? 'Hide code' : 'View source'}
              </button>
            </div>
          </div>
          {openId === submission.id && (
            <pre className="code-block"><code>{submission.source_code}</code></pre>
          )}
        </section>
      ))}

      {pagination.count > 0 && (
        <Pagination
          currentPage={page}
          hasNext={!!pagination.next}
          hasPrevious={!!pagination.previous}
          onNext={() => setPage(page + 1)}
          onPrevious={() => setPage(page - 1)}
          disabled={loading}
        />
      )}
    </main>
  )
}