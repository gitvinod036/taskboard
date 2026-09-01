import { useEffect, useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import { languageDisplayName } from '../languages'

const DIFFICULTIES = ['EASY', 'MEDIUM', 'HARD']
const LANGS = ['python', 'javascript', 'java', 'cpp']
// Display-only preview of the score the backend derives from difficulty
// (CodingProblem.points / DIFFICULTY_POINTS: EASY 10, MEDIUM 20, HARD 30).
// Points are never manually editable and never sent in the payload.
const DIFFICULTY_POINTS = { EASY: 10, MEDIUM: 20, HARD: 30 }

function blankProblem() {
  return {
    title: '',
    description: '',
    difficulty: 'EASY',
    input_format: '',
    output_format: '',
    constraints: '',
    examples: [''],
    explanation: '',
    starter_code: LANGS.reduce((acc, l) => ({ ...acc, [l]: '' }), {}),
    allowed_languages: [...LANGS],
    test_cases: [
      { id: `tmp-${Date.now()}-pub`, input: '', expected_output: '', is_hidden: false, order: 1 },
      { id: `tmp-${Date.now()}-hid`, input: '', expected_output: '', is_hidden: true, order: 1001 },
    ],
    status: 'DRAFT',
  }
}

function TestCaseCard({ tc, hidden, onUpdate, onRemove }) {
  return (
    <div className={`test-case-card ${hidden ? 'test-case-hidden' : ''}`}>
      <div className="test-case-card-header">
        <strong>{hidden ? 'Hidden' : 'Public'} test case</strong>
        <button type="button" className="button-danger button-small" onClick={() => onRemove(tc.id)}>
          Delete
        </button>
      </div>
      <div className="test-case-fields">
        <label className="test-case-field">
          <span>Input</span>
          <textarea className="input-bordered font-mono" rows="3" value={tc.input}
            onChange={(e) => onUpdate(tc.id, 'input', e.target.value)} placeholder="stdin for this case" />
        </label>
        <label className="test-case-field">
          <span>Expected Output</span>
          <textarea className="input-bordered font-mono" rows="3" value={tc.expected_output}
            onChange={(e) => onUpdate(tc.id, 'expected_output', e.target.value)}
            placeholder="exact expected stdout" />
        </label>
      </div>
    </div>
  )
}

export default function AdminCodingProblemEdit({ problemId, embedded = false }) {
  const isNew = !problemId || problemId === 'new'
  const [problem, setProblem] = useState(null)
  const [loading, setLoading] = useState(!isNew)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
    const [publishing, setPublishing] = useState(false)
    const [activeLang, setActiveLang] = useState('python')

  useEffect(() => {
    if (isNew) {
      setProblem(blankProblem())
      setLoading(false)
      return
    }
    api.get(`/admin/coding/problems/${problemId}/`)
      .then(({ data }) => setProblem(data))
      .catch((err) => setError(err.response?.data?.detail || 'Could not load problem.'))
      .finally(() => setLoading(false))
  }, [problemId, isNew])

  if (loading) {
    if (embedded) return <p className="state-message" role="status">Loading problem…</p>
    return (
      <main className="workspace-shell">
        <WorkspaceNav active="coding" />
        <p className="state-message">Loading problem…</p>
      </main>
    )
  }

  if (!problem) {
    if (embedded) return error
      ? <p className="form-error" role="alert">{error}</p>
      : null
    return (
      <main className="workspace-shell">
        <WorkspaceNav active="coding" />
        {error && <p className="form-error" role="alert">{error}</p>}
      </main>
    )
  }

  function updateField(name, value) {
    setProblem({ ...problem, [name]: value })
  }

  function updateStarter(lang, code) {
    setProblem({ ...problem, starter_code: { ...problem.starter_code, [lang]: code } })
  }

  function toggleAllowed(lang) {
    const current = problem.allowed_languages || []
    const next = current.includes(lang)
      ? current.filter((l) => l !== lang)
      : [...current, lang]
    setProblem({ ...problem, allowed_languages: next })
  }

    function renumberTestCases() {
    const publicCases = problem.test_cases.filter((tc) => !tc.is_hidden)
    const hiddenCases = problem.test_cases.filter((tc) => tc.is_hidden)
    setProblem({
      ...problem,
      test_cases: [
        ...publicCases.map((tc, i) => ({ ...tc, order: i + 1 })),
        ...hiddenCases.map((tc, i) => ({ ...tc, order: 1001 + i })),
      ],
    })
  }

  function addTestCase(isHidden) {
    const siblingCases = problem.test_cases.filter((tc) => tc.is_hidden === isHidden)
    setProblem({
      ...problem,
      test_cases: [
        ...problem.test_cases,
        {
          id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          input: '',
          expected_output: '',
          is_hidden: isHidden,
          order: isHidden ? 1001 + siblingCases.length : 1 + siblingCases.length,
        },
      ],
    })
  }

  function removeTestCase(id) {
    setProblem({ ...problem, test_cases: problem.test_cases.filter((tc) => tc.id !== id) })
  }

  function updateTestCase(id, field, value) {
    setProblem({
      ...problem,
      test_cases: problem.test_cases.map((tc) => (tc.id === id ? { ...tc, [field]: value } : tc)),
    })
  }

  function normalizePayload() {
    renumberTestCases()
    return {
      title: problem.title,
      description: problem.description,
      difficulty: problem.difficulty,
      input_format: problem.input_format,
      output_format: problem.output_format,
      constraints: problem.constraints,
      examples: problem.examples,
      explanation: problem.explanation,
      starter_code: problem.starter_code,
      allowed_languages: problem.allowed_languages,
      test_cases: problem.test_cases
        .filter((tc) => tc.input !== '' || tc.expected_output !== '')
        .map((tc) => ({
          id: typeof tc.id === 'number' ? tc.id : undefined,
          input: tc.input,
          expected_output: tc.expected_output,
          is_hidden: tc.is_hidden,
          order: tc.order,
        })),
      status: problem.status,
    }
  }

  async function saveAsDraft() {
    setSaving(true)
    setError('')
    try {
      const payload = normalizePayload()
      if (hasPersistedProblem) {
        await api.patch(`/admin/coding/problems/${problem.id}/`, payload)
      } else {
        await api.post('/admin/coding/problems/', payload)
      }
      window.location.href = '/admin/coding/problems'
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not save problem.')
    } finally {
      setSaving(false)
    }
  }

  async function generateWithAI() {
    setGenerating(true)
    setError('')
    try {
      const resp = await api.post('/admin/coding/problems/generate/', {
        title: problem.title,
        idea: problem.description || problem.title,
      })
      setProblem(resp.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'AI generation failed.')
    } finally {
      setGenerating(false)
    }
  }

  function onPublishValid() {
    renumberTestCases()
    const pub = problem.test_cases.filter((tc) => !tc.is_hidden)
    const hid = problem.test_cases.filter((tc) => tc.is_hidden)
    if (!problem.title.trim()) { setError('Title is required.'); return false }
    if (!problem.description.trim()) { setError('Description is required.'); return false }
    if (!problem.input_format.trim()) { setError('Input format is required.'); return false }
    if (!problem.output_format.trim()) { setError('Output format is required.'); return false }
    if (pub.length === 0) { setError('At least one public test case is required.'); return false }
    if (hid.length === 0) { setError('At least one hidden test case is required.'); return false }
    return true
  }

  async function publish() {
    if (!onPublishValid()) return
    setPublishing(true)
    setError('')
    try {
      const payload = { ...normalizePayload(), status: 'PUBLISHED' }
      if (hasPersistedProblem) {
        await api.patch(`/admin/coding/problems/${problem.id}/`, payload)
      } else {
        await api.post('/admin/coding/problems/', payload)
      }
      window.location.href = '/admin/coding/problems'
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not publish problem.')
        } finally {
      setPublishing(false)
    }
  }

  const publicCases = problem.test_cases.filter((tc) => !tc.is_hidden)
  const hiddenCases = problem.test_cases.filter((tc) => tc.is_hidden)
  // Decide CREATE vs UPDATE from the actual persisted state, not the route
  // slug: after AI generation the problem already carries a real id, so the
  // next save must PATCH that row instead of POSTing a duplicate.
  const hasPersistedProblem = Boolean(problem?.id)

  // Body of the editor, reused by both the standalone route and the unified
  // Create Task page (embedded mode skips its own page shell/navigation).
  const body = (
    <>
      {!embedded && <WorkspaceNav active="coding" />}
      <section className="page-intro">
        <div>
          <p className="eyebrow">Administration</p>
          <div className="problem-card-top">
            <h1>{isNew ? 'New Coding Problem' : 'Edit Coding Problem'}</h1>
            <span className={`submission-status submission-${problem.status.toLowerCase()}`}>
              {problem.status === 'PUBLISHED' ? 'Published' : 'Draft'}
            </span>
          </div>
          <p>{isNew
            ? 'Describe the idea, generate a complete problem with AI, then review and publish.'
            : 'Review, refine, and publish this coding problem.'}</p>
        </div>
        <div className="workspace-actions">
          <button type="button" className="button-muted" onClick={generateWithAI} disabled={generating}>
            {generating ? 'Generating…' : 'Generate with AI'}
          </button>
          <button type="button" className="button-muted" disabled={saving} onClick={saveAsDraft}>
            {saving ? 'Saving…' : 'Save Draft'}
          </button>
          <button type="button" className="button-primary" disabled={publishing} onClick={publish}>
            {publishing ? 'Publishing…' : 'Publish'}
          </button>
        </div>
      </section>

      {error && <p className="error-banner" role="alert">{error}</p>}

      <div className="coding-admin-stack">
        <section className="surface-panel">
          <p className="section-kicker">Section 01</p>
          <h2>Basic Information</h2>
          <p className="section-note">The core identity shown in every problem listing.</p>
          <div className="form-grid">
            <div className="field field-span-2">
              <label htmlFor="problem-title">Title *</label>
              <input id="problem-title" className="input-bordered" value={problem.title}
                onChange={(e) => updateField('title', e.target.value)} placeholder="e.g. Two Sum" />
            </div>
            <div className="field">
              <label htmlFor="problem-difficulty">Difficulty</label>
              <select id="problem-difficulty" className="input-bordered" value={problem.difficulty}
                onChange={(e) => updateField('difficulty', e.target.value)}>
                {DIFFICULTIES.map((d) => <option key={d} value={d}>{d} — {DIFFICULTY_POINTS[d] ?? 0} points</option>)}
              </select>
              <span className="field-hint">Score is derived from difficulty: {DIFFICULTY_POINTS[problem.difficulty] ?? 0} points.</span>
            </div>
            <div className="field field-span-2">
              <span className="field-label">Allowed Languages</span>
              <div className="checkbox-chip-list">
                {LANGS.map((lang) => {
                  const on = (problem.allowed_languages || []).includes(lang)
                  return (
                    <label key={lang} className={`checkbox-chip ${on ? 'checkbox-chip-on' : ''}`}>
                      <input type="checkbox" checked={on} onChange={() => toggleAllowed(lang)} />
                      {languageDisplayName(lang)}
                    </label>
                  )
                })}
              </div>
              <span className="field-hint">Users can only submit solutions in these languages.</span>
            </div>
          </div>
        </section>

        <section className="surface-panel">
          <p className="section-kicker">Section 02</p>
          <h2>Problem Statement</h2>
          <p className="section-note">Everything here is editable — including AI-generated content.</p>
          <div className="form-grid">
            <div className="field field-span-2">
              <label htmlFor="problem-description">Description / Idea *</label>
              <textarea id="problem-description" rows="7" className="input-bordered" value={problem.description}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="For new problems, enter the basic idea here. After AI generation this becomes the full description." />
            </div>
            <div className="field">
              <label htmlFor="problem-input">Input Format *</label>
              <textarea id="problem-input" rows="4" className="input-bordered" value={problem.input_format}
                onChange={(e) => updateField('input_format', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="problem-output">Output Format *</label>
              <textarea id="problem-output" rows="4" className="input-bordered" value={problem.output_format}
                onChange={(e) => updateField('output_format', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="problem-constraints">Constraints</label>
              <textarea id="problem-constraints" rows="4" className="input-bordered" value={problem.constraints}
                onChange={(e) => updateField('constraints', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="problem-explanation">Explanation</label>
              <textarea id="problem-explanation" rows="4" className="input-bordered" value={problem.explanation}
                onChange={(e) => updateField('explanation', e.target.value)} />
            </div>
          </div>
        </section>

        <section className="surface-panel">
          <p className="section-kicker">Section 03</p>
          <h2>Starter Code</h2>
          <p className="section-note">Pre-filled in the user's editor when they pick each language.</p>
          <div className="language-tabs" role="tablist" aria-label="Starter code language">
            {LANGS.map((lang) => (
              <button key={lang} type="button" role="tab" aria-selected={activeLang === lang}
                className={`language-tab ${activeLang === lang ? 'language-tab-active' : ''}`}
                onClick={() => setActiveLang(lang)}>
                {languageDisplayName(lang)}
              </button>
            ))}
          </div>
          <label className="field-label" htmlFor={`starter-${activeLang}`}>
            {languageDisplayName(activeLang)}
          </label>
          <textarea id={`starter-${activeLang}`} rows="12"
            className="input-bordered font-mono starter-code-area"
            value={problem.starter_code[activeLang] || ''}
            onChange={(e) => updateStarter(activeLang, e.target.value)}
            placeholder={`Starter code for ${languageDisplayName(activeLang)}…`} />
        </section>

        <section className="surface-panel">
          <p className="section-kicker">Section 04</p>
          <h2>Test Cases</h2>
          <p className="section-note">Public cases run on “Run Code”. Hidden cases only run on final submission.</p>

          <div className="test-case-group">
            <h3 className="test-case-group-heading">
              Public Test Cases <span className="count-pill">{publicCases.length}</span>
            </h3>
            {publicCases.length === 0 && (
              <p className="empty-state">No public test cases yet. Add at least one before publishing.</p>
            )}
            <div className="test-case-cards">
              {publicCases.map((tc) => (
                <TestCaseCard key={tc.id} tc={tc} hidden={false}
                  onUpdate={updateTestCase} onRemove={removeTestCase} />
              ))}
            </div>
            <button type="button" className="button-muted" onClick={() => addTestCase(false)}>
              + Add Public Test Case
            </button>
          </div>

          <div className="test-case-group">
            <h3 className="test-case-group-heading">
              Hidden Test Cases <span className="count-pill">{hiddenCases.length}</span>
            </h3>
            <p className="field-hint">Never shown to users. Required before publishing.</p>
            {hiddenCases.length === 0 && (
              <p className="empty-state">No hidden test cases yet. Add at least one before publishing.</p>
            )}
            <div className="test-case-cards">
              {hiddenCases.map((tc) => (
                <TestCaseCard key={tc.id} tc={tc} hidden
                  onUpdate={updateTestCase} onRemove={removeTestCase} />
              ))}
            </div>
            <button type="button" className="button-muted" onClick={() => addTestCase(true)}>
              + Add Hidden Test Case
            </button>
          </div>
        </section>
      </div>
    </>
  )

  if (embedded) return body

  return <main className="workspace-shell">{body}</main>
}
