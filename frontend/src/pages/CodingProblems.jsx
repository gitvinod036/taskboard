import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import Pagination from '../components/Pagination'
import { languageDisplayName } from '../languages'

export function DifficultyBadge({ difficulty }) {
  const level = String(difficulty || '').toLowerCase()
  return (
    <span className={`difficulty-badge difficulty-${level}`}>
      {difficulty || '—'}
    </span>
  )
}

// Display helper for the score chip. The authoritative mapping lives in the
// backend (DIFFICULTY_POINTS on CodingProblem) and the API already returns
// each problem's derived `points`; problems without a value hide the chip.
export function PointsChip({ points }) {
  const value = Number(points)
  if (!Number.isFinite(value) || value <= 0) return null
  return <span className="problem-card-points">{value} points</span>
}

export function LanguageChips({ languages }) {
  const langs = Array.isArray(languages) ? languages : []
  if (!langs.length) return null
  return (
    <div className="language-chip-list">
      {langs.map((lang) => (
        <span className="language-chip" key={lang}>{languageDisplayName(lang)}</span>
      ))}
    </div>
  )
}

function ProblemSkeleton() {
  return (
    <section aria-hidden="true" style={{ maxWidth: 1320, margin: '0 auto' }}>
      <div className="skeleton-block skeleton-problem-card" />
      <div className="skeleton-block skeleton-problem-card" />
      <div className="skeleton-block skeleton-problem-card" />
    </section>
  )
}

export default function CodingProblems() {
  const [problems, setProblems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })

  function loadProblems(pageNumber = page, searchTerm = search) {
    setLoading(true)
    setError('')
    const params = { page: pageNumber }
    if (searchTerm) params.search = searchTerm
    api.get('/coding/problems/', { params })
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
    loadProblems(1, search)
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Practice Arena</p>
          <h1>Coding Problems</h1>
          <p>Sharpen your skills with real problems — write code, run tests, and submit solutions.</p>
        </div>
      </section>

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
          <button type="submit" className="button-primary">Search</button>
        </form>
      </section>

      {error && <p className="error-banner" role="alert">{error}</p>}

      {loading && <ProblemSkeleton />}

      {!loading && !error && problems.length === 0 && (
        <div className="empty-state-hero">
          <strong>No coding problems available yet</strong>
          <span>Published problems will appear here as soon as they are released. Check back soon.</span>
        </div>
      )}

      {!loading && problems.length > 0 && (
        <section className="problem-card-grid">
          {problems.map((problem) => (
            <article className="problem-card" key={problem.id}>
              <div className="problem-card-top">
                <DifficultyBadge difficulty={problem.difficulty} />
                <PointsChip points={problem.points} />
              </div>
              <h2 className="problem-card-title">{problem.title}</h2>
              <p className="problem-card-desc">{problem.description}</p>
              <LanguageChips languages={problem.allowed_languages} />
              <div className="problem-card-meta">
                <div className="problem-card-actions">
                  <button type="button" className="button-primary button-small"
                    onClick={() => (window.location.href = `/coding/problems/${problem.id}/solve`)}>
                    Solve Problem →
                  </button>
                  <button type="button" className="button-secondary button-small"
                    onClick={() => (window.location.href = `/coding/problems/${problem.id}`)}>
                    View Problem
                  </button>
                </div>
                <span className="problem-card-date">
                  {problem.published_at ? `Published ${new Date(problem.published_at).toLocaleDateString()}` : ''}
                </span>
              </div>
            </article>
          ))}
        </section>
      )}

      {pagination.count > 0 && (
        <div className="page-toolbar">
          <Pagination
            currentPage={page}
            hasNext={!!pagination.next}
            hasPrevious={!!pagination.previous}
            onNext={() => setPage(page + 1)}
            onPrevious={() => setPage(page - 1)}
            disabled={loading}
          />
        </div>
      )}
    </main>
  )
}
