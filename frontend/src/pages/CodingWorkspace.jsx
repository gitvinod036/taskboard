import { useCallback, useEffect, useMemo, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import CodeEditor from '../components/CodeEditor'
import Pagination from '../components/Pagination'
import { DifficultyBadge } from './CodingProblems'
import {
  DEFAULT_LANGUAGE,
  languageDisplayName,
  languagesForProblem,
  monacoLanguage,
  starterCodeFor,
} from '../languages'

const PENDING_NOTICE = 'PENDING — queued for execution. Code execution arrives in a future release.'

function relativeTime(iso) {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

export default function CodingWorkspace({ problemId }) {
  const [problem, setProblem] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [language, setLanguage] = useState(DEFAULT_LANGUAGE)
  const [code, setCode] = useState('')
  const [availableLanguages, setAvailableLanguages] = useState([])
  const [draftsByLanguage, setDraftsByLanguage] = useState({})

  const [submitting, setSubmitting] = useState(false)
  const [running, setRunning] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [latestSubmission, setLatestSubmission] = useState(null)

  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })

  useEffect(() => {
    if (!problemId) return
    let cancelled = false
    setLoading(true)
    api.get(`/coding/problems/${problemId}/`)
      .then(({ data }) => {
        if (cancelled) return
        setProblem(data)
        const langs = languagesForProblem(data)
        setAvailableLanguages(langs)
        const initial = langs.includes(DEFAULT_LANGUAGE) ? DEFAULT_LANGUAGE : langs[0] || DEFAULT_LANGUAGE
        setLanguage(initial)
        setCode(starterCodeFor(data, initial))
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err.response?.data?.detail || 'Problem could not be loaded.')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [problemId])

  const loadHistory = useCallback((pageNumber = page) => {
    if (!problemId) return
    setHistoryLoading(true)
    api.get('/coding/submissions/', { params: { problem: problemId, page: pageNumber } })
      .then(({ data }) => {
        setHistory(Array.isArray(data?.results) ? data.results : [])
        setPagination({ count: data?.count ?? 0, next: data?.next ?? null, previous: data?.previous ?? null })
      })
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false))
  }, [page, problemId])

  useEffect(() => { loadHistory(page) }, [page]) // eslint-disable-line react-hooks/exhaustive-deps

  function switchLanguage(nextLanguage) {
    if (!problem || nextLanguage === language) return
    setDraftsByLanguage((prev) => ({ ...prev, [language]: code }))
    setLanguage(nextLanguage)
    const savedDraft = draftsByLanguage[nextLanguage]
    // Preserve in-progress work per language; otherwise load that language's starter code.
    setCode(savedDraft !== undefined ? savedDraft : starterCodeFor(problem, nextLanguage))
    setActionError('')
  }

  async function executeCode(mode) {
    setNotice('')
    if (!code.trim()) {
      setActionError('Write some code before submitting.')
      return
    }
    if (mode === 'RUN') {
      setRunning(true)
    } else {
      setSubmitting(true)
    }
    setActionError('')
    try {
      const endpoint = mode === 'RUN' ? 'run' : 'submissions'
      const { data } = await api.post(`/coding/problems/${problemId}/${endpoint}/`, {
        language,
        source_code: code,
      })
      setLatestSubmission(data)
      setPage(1)
      loadHistory(1)
    } catch (err) {
      const detail = err.response?.data
      const message = typeof detail === 'string'
        ? detail
        : Object.values(detail || {}).flat().join(' ') || 'The request could not be completed.'
      setActionError(message)
    } finally {
      setRunning(false)
      setSubmitting(false)
    }
  }

  const statusBadgeClass = useCallback(
    (submission) => `submission-status submission-${String(submission.status).toLowerCase().replace(/_/g, '-')}`,
    [],
  )

  if (loading) return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      <p className="state-message">Loading workspace…</p>
    </main>
  )

  if (!problem) return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      {loadError && <p className="form-error" role="alert">{loadError}</p>}
      {!loadError && <p className="empty-state"><strong>Problem unavailable</strong><span>This problem may not be published.</span></p>}
    </main>
  )

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />

      <section className="page-intro">
        <div>
          <p className="eyebrow">Coding Workspace</p>
          <h1>{problem.title}</h1>
          <div className="meta-badges">
            <DifficultyBadge difficulty={problem.difficulty} />
            <span className="language-chip">{languageDisplayName(language)}</span>
          </div>
        </div>
        <div className="workspace-actions">
          <a className="button-muted" href={`/coding/problems/${problem.id}`}>View problem</a>
          <button
            type="button"
            className="button-muted"
            onClick={() => executeCode('RUN')}
            disabled={running || submitting}
          >
            {running ? 'Running…' : 'Run Code'}
          </button>
          <button
            type="button"
            className="button-primary"
            onClick={() => executeCode('SUBMIT')}
            disabled={submitting || running}
          >
            {submitting ? 'Submitting…' : 'Submit Solution'}
          </button>
        </div>
      </section>

      {(actionError || notice) && (
        <section className="workspace-result-bar">
          {actionError && <p className="form-error" role="alert">{actionError}</p>}
          {notice && !actionError && <p className="form-success">{notice}</p>}
        </section>
      )}

      <div className="coding-workspace-grid">
        <article className="admin-panel coding-problem-panel surface-panel">
          <h3>Description</h3>
          <p className="problem-description">{problem.description}</p>

          {(problem.input_format || problem.output_format) && (
            <>
              <h4>Input Format</h4>
              <p>{problem.input_format}</p>
              <h4>Output Format</h4>
              <p>{problem.output_format}</p>
            </>
          )}

          {problem.constraints && (<><h4>Constraints</h4><p>{problem.constraints}</p></>)}

          {Array.isArray(problem.examples) && problem.examples.length > 0 && (
            <>
              <h4>Examples</h4>
              {problem.examples.map((ex, i) => (
                <div key={i} className="example-block">
                  {ex.input && (<><strong>Input:</strong><pre className="code-block">{ex.input}</pre></>)}
                  {ex.output && (<><strong>Output:</strong><pre className="code-block">{ex.output}</pre></>)}
                  {ex.explanation && (<><strong>Explanation:</strong><p>{ex.explanation}</p></>)}
                </div>
              ))}
            </>
          )}

          {problem.explanation && (<><h4>Explanation</h4><p>{problem.explanation}</p></>)}
        </article>

        <article className="admin-panel coding-editor-panel surface-panel">
          <div className="panel-toolbar">
            <label htmlFor="workspace-language">Language</label>
            <select
              id="workspace-language"
              className="input-bordered"
              value={language}
              onChange={(e) => switchLanguage(e.target.value)}
            >
              {availableLanguages.map((lang) => (
                <option key={lang} value={lang}>{languageDisplayName(lang)}</option>
              ))}
            </select>
          </div>

          <CodeEditor
            value={code}
            language={monacoLanguage(language)}
            onChange={setCode}
          />
          <p className="editor-hint">Your code is only sent to the server when you press Submit Solution.</p>
        </article>
      </div>

      <section className="admin-panel admin-wide-panel surface-panel coding-history-panel">
        <h3>Execution Result</h3>
        {latestSubmission ? (
          <div className="submission-card">
            <div className="submission-card-header">
              <div>
                <p className="section-kicker">
                  #{latestSubmission.id} · {languageDisplayName(latestSubmission.language)} · {latestSubmission.mode === 'RUN' ? 'Run (public tests)' : 'Full submission'}
                </p>
                <h2>{latestSubmission.status_label || latestSubmission.status}</h2>
                <p className="submission-owner">
                  {new Date(latestSubmission.created_at).toLocaleString()}
                  {latestSubmission.execution_time != null && ` · ${latestSubmission.execution_time}s`}
                  {latestSubmission.memory_used != null && ` · ${Math.round(latestSubmission.memory_used)} MB`}
                  {latestSubmission.passed_tests != null && latestSubmission.total_tests != null &&
                    ` · ${latestSubmission.passed_tests}/${latestSubmission.total_tests} tests`}
                </p>
              </div>
              <span className={statusBadgeClass(latestSubmission)}>
                {latestSubmission.status}
              </span>
            </div>

            {latestSubmission.feedback && (
              <pre className="code-block">{latestSubmission.feedback}</pre>
            )}

            {Array.isArray(latestSubmission.test_summary) && latestSubmission.test_summary.length > 0 && (
              <div className="test-summary-list">
                {latestSubmission.test_summary.map((item) => (
                  <div className="test-summary-row" key={item.index}>
                    <span className="section-kicker">Public test {item.index}</span>
                    <span className={`submission-status ${item.passed ? 'submission-approved' : 'submission-rejected'}`}>
                      {item.passed ? 'PASSED' : 'FAILED'}
                    </span>
                    {!item.passed && (
                      <div className="test-io">
                        {item.expected_output !== '' && (
                          <><strong>Expected:</strong><pre className="code-block">{item.expected_output}</pre></>
                        )}
                        <strong>Received:</strong>
                        <pre className="code-block">{item.actual_output || '(no output)'}</pre>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className="empty-state"><strong>No submission yet</strong><span>Your latest result will appear here.</span></p>
        )}

        <h3>Submission History</h3>
        {historyLoading && <p className="state-message">Loading submissions…</p>}
        {!historyLoading && history.length === 0 && (
          <p className="empty-state"><strong>No submissions yet</strong><span>Submitted solutions for this problem will be listed here.</span></p>
        )}
        {!historyLoading && history.length > 0 && (
          <div className="submission-list">
            {history.map((submission) => (
              <article className="submission-card" key={submission.id}>
                <div className="submission-card-header">
                  <div>
                    <p className="section-kicker">#{submission.id} · {languageDisplayName(submission.language)}</p>
                    <h2>{submission.status_label || submission.status}</h2>
                    <p className="submission-owner">
                      {relativeTime(submission.created_at)}
                      {submission.execution_time != null && ` · ${submission.execution_time}s`}
                      {submission.memory_used != null && ` · ${Math.round(submission.memory_used)} MB`}
                      {submission.passed_tests != null && submission.total_tests != null &&
                        ` · ${submission.passed_tests}/${submission.total_tests} tests`}
                    </p>
                  </div>
                  <span className={statusBadgeClass(submission)}>
                    {submission.status}
                  </span>
                </div>
              </article>
            ))}
          </div>
        )}

        {pagination.count > 0 && (
          <Pagination
            currentPage={page}
            hasNext={!!pagination.next}
            hasPrevious={!!pagination.previous}
            onNext={() => setPage(page + 1)}
            onPrevious={() => setPage(page - 1)}
            disabled={historyLoading}
          />
        )}
      </section>
    </main>
  )
}