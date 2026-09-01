import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import Pagination from '../components/Pagination'
import { DifficultyBadge, LanguageChips, PointsChip } from './CodingProblems'

function ListSkeleton() {
  return (
    <>
      <div className="skeleton-block skeleton-toolbar" />
      <section className="problem-card-grid" aria-hidden="true">
        <div className="skeleton-block skeleton-problem-card" />
        <div className="skeleton-block skeleton-problem-card" />
        <div className="skeleton-block skeleton-problem-card" />
      </section>
    </>
  )
}

export default function AdminCodingProblems() {
  const [problems, setProblems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })

  function loadProblems(pageNumber = page, searchTerm = search, statusTerm = statusFilter) {
    setLoading(true)
    setError('')
    const params = { page: pageNumber }
    if (searchTerm) params.search = searchTerm
    if (statusTerm) params.status = statusTerm
    api.get('/admin/coding/problems/', { params })
      .then(({ data }) => {
        setProblems(Array.isArray(data?.results) ? data.results : [])
        setPagination({ count: data?.count ?? 0, next: data?.next ?? null, previous: data?.previous ?? null })
      })
      .catch((err) => {
        const data = err.response?.data || {}
        setError(data.detail || 'Problems could not be loaded.')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadProblems(page) }, [page])

  function handleSearch(e) {
    e.preventDefault()
    setPage(1)
    loadProblems(1, search, statusFilter)
  }

  function handleStatusChange(e) {
    setStatusFilter(e.target.value)
    setPage(1)
    loadProblems(1, search, e.target.value)
  }

  function deleteProblem(problem) {
    if (!window.confirm(`Delete “${problem.title}”? This cannot be undone.`)) return
    api.delete(`/admin/coding/problems/${problem.id}/`)
      .then(() => {
        setNotice(`“${problem.title}” was deleted.`)
        setPage(1)
        loadProblems(1, search, statusFilter)
      })
      .catch((err) => setError(err.response?.data?.detail || 'The problem could not be deleted.'))
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Coding Problems</h1>
          <p>Generate problems with AI, review them, and publish them to the practice arena.</p>
        </div>
        <button type="button" className="button-primary" onClick={() => (window.location.href = '/admin/coding/problems/new')}>
          + New Problem
        </button>
      </section>

      {error && <p className="error-banner" role="alert">{error}</p>}
      {notice && !error && (
        <div className="empty-state-hero" role="status">{notice}</div>
      )}

      <section className="surface-panel list-toolbar-panel">
        <form className="workspace-toolbar" onSubmit={handleSearch}>
          <input
            type="text"
            className="input-bordered"
            placeholder="Search problems by title…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search problems"
          />
          <select className="input-bordered" value={statusFilter} onChange={handleStatusChange} aria-label="Filter by status">
            <option value="">All statuses</option>
            <option value="DRAFT">Draft</option>
            <option value="PUBLISHED">Published</option>
          </select>
          <button type="submit" className="button-primary">Search</button>
        </form>
      </section>

      {loading && <ListSkeleton />}

      {!loading && !error && problems.length === 0 && (
        <div className="empty-state-hero">
          <strong>No coding problems yet</strong>
          <span>Create your first problem — describe an idea, generate it with AI, then publish it.</span>
          <button type="button" className="button-primary" onClick={() => (window.location.href = '/admin/coding/problems/new')}>
            + New Problem
          </button>
        </div>
      )}

      {!loading && problems.length > 0 && (
        <section className="problem-card-grid">
          {problems.map((problem) => (
            <article className="problem-card" key={problem.id}>
              <div className="problem-card-top">
                <DifficultyBadge difficulty={problem.difficulty} />
                <PointsChip points={problem.points} />
                <span className={`submission-status submission-${problem.status.toLowerCase()}`}>
                  {problem.status === 'PUBLISHED' ? 'Published' : 'Draft'}
                </span>
              </div>
              <h2 className="problem-card-title">{problem.title}</h2>
              <LanguageChips languages={problem.allowed_languages} />
              <div className="problem-card-meta">
                <div className="problem-card-actions">
                  <button type="button" className="button-primary button-small"
                    onClick={() => (window.location.href = `/admin/coding/problems/${problem.id}`)}>
                    Edit
                  </button>
                  {problem.status === 'PUBLISHED' && (
                    <button type="button" className="button-muted button-small"
                      onClick={() => (window.location.href = `/coding/problems/${problem.id}`)}>
                      View
                    </button>
                  )}
                  <button type="button" className="button-danger button-small" onClick={() => deleteProblem(problem)}>
                    Delete
                  </button>
                </div>
                <span className="problem-card-date">
                  Created {new Date(problem.created_at || problem.updated_at).toLocaleDateString()}
                </span>
              </div>
            </article>
          ))}
        </section>
      )}

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
