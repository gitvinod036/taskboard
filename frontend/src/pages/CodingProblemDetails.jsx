import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import Pagination from '../components/Pagination'
import { languageDisplayName } from '../languages'
import { DifficultyBadge, LanguageChips, PointsChip } from './CodingProblems'

export default function CodingProblemDetails({ problemId }) {
  const [problem, setProblem] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeLang, setActiveLang] = useState('python')

  useEffect(() => {
    if (!problemId) return
    setLoading(true)
    api.get(`/coding/problems/${problemId}/`)
      .then(({ data }) => {
        setProblem(data)
        const langs = data.allowed_languages || []
        if (langs.length && !langs.includes(activeLang)) {
          setActiveLang(langs[0])
        }
      })
      .catch((err) => {
        const data = err.response?.data || {}
        setError(data.detail || 'Problem could not be loaded.')
      })
      .finally(() => setLoading(false))
  }, [problemId])

  if (loading) return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      <p className="state-message">Loading problem…</p>
    </main>
  )

  if (!problem) return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      {error && <p className="form-error" role="alert">{error}</p>}
    </main>
  )

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="coding" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Practice Arena</p>
          <h1>{problem.title}</h1>
          <div className="meta-badges">
            <DifficultyBadge difficulty={problem.difficulty} />
            <PointsChip points={problem.points} />
            <LanguageChips languages={problem.allowed_languages} />
          </div>
        </div>
        <a className="button-primary" href={`/coding/problems/${problem.id}/solve`}>Solve Problem →</a>
      </section>

      <section className="surface-panel problem-details-panel">
        <p className="section-kicker">Description</p>
        <p className="problem-description">{problem.description}</p>

        {(problem.input_format || problem.output_format) && (
          <div className="form-grid detail-grid">
            {problem.input_format && (
              <div>
                <h4>Input Format</h4>
                <p className="detail-text">{problem.input_format}</p>
              </div>
            )}
            {problem.output_format && (
              <div>
                <h4>Output Format</h4>
                <p className="detail-text">{problem.output_format}</p>
              </div>
            )}
          </div>
        )}

        {problem.constraints && (
          <>
            <h4>Constraints</h4>
            <pre className="code-block">{problem.constraints}</pre>
          </>
        )}

        {Array.isArray(problem.examples) && problem.examples.length > 0 && (
          <>
            <h4>Examples</h4>
            <div className="example-grid">
              {problem.examples.map((ex, i) => (
                <div key={i} className="example-block">
                  <strong>Example {i + 1}</strong>
                  {ex.input && (
                    <>
                      <span>Input</span>
                      <pre className="code-block">{ex.input}</pre>
                    </>
                  )}
                  {ex.output && (
                    <>
                      <span>Output</span>
                      <pre className="code-block">{ex.output}</pre>
                    </>
                  )}
                  {ex.explanation && <p>{ex.explanation}</p>}
                </div>
              ))}
            </div>
          </>
        )}

        {Object.keys(problem.starter_code || {}).length > 0 && (
          <>
            <h4>Starter Code</h4>
            <div className="language-tabs" role="tablist" aria-label="Starter code language">
              {(problem.allowed_languages || Object.keys(problem.starter_code)).map((lang) => (
                <button key={lang} type="button" role="tab" aria-selected={activeLang === lang}
                  className={`language-tab ${activeLang === lang ? 'language-tab-active' : ''}`}
                  onClick={() => setActiveLang(lang)}>
                  {languageDisplayName(lang)}
                </button>
              ))}
            </div>
            <pre className="code-block"><code>{problem.starter_code[activeLang] || '(no starter code for this language)'}</code></pre>
          </>
        )}

        {problem.explanation && (
          <>
            <h4>Explanation</h4>
            <p className="detail-text">{problem.explanation}</p>
          </>
        )}
      </section>
    </main>
  )
}
