import { useState } from 'react'

import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import AdminCodingProblemEdit from './AdminCodingProblemEdit'

const emptyNormalForm = { title: '', description: '', due_date: '' }
const TASK_TYPES = [
  { id: 'normal', label: 'Normal Task', hint: 'Title, description and due date — assigned from the Task Board.' },
  { id: 'coding', label: 'Coding Task', hint: 'A full coding problem with starter code, languages and test cases.' },
]

// Unified task-creation entry point for administrators.
//
// - "Normal Task" reuses the exact existing contract: POST /api/tasks/
//   ({title, description, due_date}) — the same payload TaskBoard sends.
// - "Coding Task" embeds the existing coding-problem editor, which talks to
//   the existing /api/admin/coding/problems/ API (no new backend endpoint).
// Both type forms stay mounted while switching types so entered data is
// preserved; only the hidden one is not displayed.
export default function AdminCreateTask() {
  const [taskType, setTaskType] = useState('normal')
  const [form, setForm] = useState(emptyNormalForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const activeType = TASK_TYPES.find((type) => type.id === taskType)

  async function saveNormalTask(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await api.post('/tasks/', { ...form, due_date: form.due_date || null })
      setNotice('Task created. Assign it to users from the Task Board.')
      setForm(emptyNormalForm)
    } catch (requestError) {
      setError(
        requestError.response?.data?.title?.[0] ||
        requestError.response?.data?.description?.[0] ||
        requestError.response?.data?.due_date?.[0] ||
        'Task could not be created.'
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="create-task" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Create task</h1>
          <p>One place to create a normal task or a full coding task.</p>
        </div>
      </section>

      <section className="admin-panel admin-wide-panel surface-panel">
        <p className="section-kicker">Task type</p>
        <h2>What kind of task?</h2>
        <div className="task-type-selector" role="tablist" aria-label="Task type">
          {TASK_TYPES.map((type) => (
            <button
              key={type.id}
              type="button"
              role="tab"
              aria-selected={taskType === type.id}
              className={`task-type-option ${taskType === type.id ? 'task-type-option-active' : ''}`}
              onClick={() => setTaskType(type.id)}
            >
              {type.label}
            </button>
          ))}
        </div>
        <p className="section-description">{activeType.hint}</p>
      </section>

      {notice && <p className="toast" role="status">{notice}</p>}
      {error && <p className="toast toast-error" role="alert">{error}</p>}

      {/* Both forms stay mounted so switching types never loses entered data. */}
      <div hidden={taskType !== 'normal'}>
        <form className="task-form-panel surface-panel admin-wide-panel" onSubmit={saveNormalTask}>
          <p className="section-kicker">Normal task</p>
          <h2>New task</h2>
          <label htmlFor="create-task-title">
            Title
            <input
              id="create-task-title"
              required
              maxLength="200"
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
            />
          </label>
          <label htmlFor="create-task-description">
            Description
            <textarea
              id="create-task-description"
              required
              rows="5"
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </label>
          <label htmlFor="create-task-due-date">
            Due date
            <span className="optional">(optional)</span>
            <input
              id="create-task-due-date"
              type="date"
              value={form.due_date}
              onChange={(event) => setForm({ ...form, due_date: event.target.value })}
            />
          </label>
          <div className="form-actions">
            <button type="submit" disabled={saving} aria-busy={saving}>
              {saving ? 'Creating...' : 'Create task'}
            </button>
          </div>
        </form>
      </div>

      <div hidden={taskType !== 'coding'} className="create-task-coding">
        <AdminCodingProblemEdit embedded />
      </div>
    </main>
  )
}
