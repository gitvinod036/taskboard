import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import TechStackFilter from '../components/molecules/TechStackFilter'
import Pagination from '../components/Pagination'

const emptyForm = { title: '', description: '', due_date: '' }

export default function TaskBoard() {
  const { isAdmin } = useAuth()
  const [tasks, setTasks] = useState([])
  const [selectedTask, setSelectedTask] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [assignmentPending, setAssignmentPending] = useState(null)
  const [techStacks, setTechStacks] = useState([])
  const [selectedStacks, setSelectedStacks] = useState([])
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })

  async function loadTasks(stackFilter = selectedStacks, pageNumber = page) {
    setLoading(true)
    setError('')
    try {
      // Paginated endpoint: filters apply before the page slice.
      const params = { page: pageNumber }
      if (stackFilter.length) params.tech_stack = stackFilter.join(',')
      const { data } = await api.get('/tasks/', { params })
      // NOTE: client-side !is_assigned filtering is a known remaining
      // optimization (needs a backend-side "unassigned" filter).
      const available = (Array.isArray(data?.results) ? data.results : []).filter((task) => !task.is_assigned)
      setTasks(available)
      setPagination({ count: data?.count ?? 0, next: data?.next ?? null, previous: data?.previous ?? null })
      setSelectedTask((current) => available.find((task) => task.id === current?.id) || available[0] || null)
    } catch {
      setError('Tasks could not be loaded. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTasks(selectedStacks, page)
  }, [selectedStacks, page])

  function changeStackFilter(next) {
    setSelectedStacks(next)
    if (page !== 1) setPage(1) // filter change always restarts at page 1
  }

  useEffect(() => {
    api.get('/tasks/tech-stacks/')
      .then(({ data }) => setTechStacks(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  async function toggleAssignment(task) {
    setAssignmentPending(task.id)
    setError('')
    setNotice('')
    try {
      await api.post(`/tasks/${task.id}/assign/`)
      setNotice('Task assigned.')
      await loadTasks()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Assignment could not be updated.')
    } finally {
      setAssignmentPending(null)
    }
  }

  function startCreate() {
    setEditingId(null)
    setForm(emptyForm)
    setNotice('')
  }

  function startEdit(task) {
    setEditingId(task.id)
    setForm({ title: task.title, description: task.description, due_date: task.due_date || '' })
    setNotice('')
  }

  async function saveTask(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = {
        ...form,
        due_date: form.due_date || null,
      }
      const request = editingId
        ? api.patch(`/tasks/${editingId}/`, payload)
        : api.post('/tasks/', payload)
      const { data } = await request
      setNotice(editingId ? 'Task updated.' : 'Task created.')
      setForm(emptyForm)
      setEditingId(null)
      await loadTasks()
      setSelectedTask(data)
    } catch (requestError) {
      setError(
        requestError.response?.data?.title?.[0] ||
        requestError.response?.data?.description?.[0] ||
        requestError.response?.data?.due_date?.[0] ||
        'Task could not be saved.'
      )
    } finally {
      setSaving(false)
    }
  }

  async function deleteTask(task) {
    if (!window.confirm(`Delete "${task.title}"?`)) return
    setError('')
    setNotice('')
    try {
      await api.delete(`/tasks/${task.id}/`)
      setNotice('Task deleted.')
      await loadTasks()
    } catch {
      setError('Task could not be deleted.')
    }
  }


  return (
    <main className="workspace-shell">
      <WorkspaceNav active="tasks" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Tasks</h1>
          <p>Browse every task, inspect the details, and keep your assignments moving.</p>
        </div>
        <div className="page-summary">
          <strong>{tasks.length}</strong>
          <span>available tasks</span>
        </div>
      </section>
      <div className="workspace-grid">
        <section className="task-list-panel surface-panel" aria-labelledby="task-list-title">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Workspace</p>
              <h2 id="task-list-title">All tasks</h2>
            </div>
            {isAdmin && <button type="button" onClick={startCreate}>New task</button>}
          </div>
          <div className="my-tasks-filter-bar">
            <TechStackFilter
              options={techStacks}
              selected={selectedStacks}
              onChange={changeStackFilter}
              loading={!techStacks.length}
              supportingText="Filter tasks by technology"
            />
          </div>
          {loading && <p className="state-message">Loading tasks...</p>}
          {!loading && error && <p className="form-error" role="alert">{error}</p>}
          {!loading && !error && tasks.length === 0 && (
            <p className="empty-state">
              <strong>{selectedStacks.length ? 'No tasks match the selected technologies' : 'No tasks yet'}</strong>
              <span>
                {selectedStacks.length
                  ? 'Try removing or adjusting your technology filters.'
                  : 'No tasks are available at this time.'}
              </span>
            </p>
          )}
          {!loading && tasks.length > 0 && (
            <div className="task-list">
              {tasks.map((task) => (
                <div
                  className={`task-row ${selectedTask?.id === task.id ? 'task-row-active' : ''}`}
                  key={task.id}
                >
                  <button type="button" className="task-select" onClick={() => setSelectedTask(task)}>
                    <strong>{task.title}</strong>
                    <span>{task.due_date ? `Due ${task.due_date}` : 'No due date'}</span>
                  </button>
                  {!isAdmin && (
                    <button
                      type="button"
                      className={task.is_assigned ? 'assignment-button assignment-button-active' : 'assignment-button'}
                      disabled={assignmentPending === task.id}
                      onClick={() => toggleAssignment(task)}
                    >
                      {assignmentPending === task.id ? 'Updating...' : task.is_assigned ? 'Assigned - Unassign' : 'Assign'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {!loading && (
            <Pagination
              currentPage={page}
              hasNext={Boolean(pagination.next)}
              hasPrevious={Boolean(pagination.previous)}
              disabled={loading}
              onNext={() => setPage((current) => current + 1)}
              onPrevious={() => setPage((current) => Math.max(1, current - 1))}
            />
          )}
        </section>
        <section className="task-detail-panel surface-panel" aria-labelledby="task-detail-title">
          {selectedTask ? (
            <>
              <p className="section-kicker">Task detail</p>
              <h2 id="task-detail-title">{selectedTask.title}</h2>
              <p className="task-description">{selectedTask.description}</p>
              <p className="task-due">{selectedTask.due_date ? `Due ${selectedTask.due_date}` : 'No due date'}</p>
              {isAdmin && (
                <div className="detail-actions">
                  <button type="button" onClick={() => startEdit(selectedTask)}>Edit</button>
                  <button type="button" className="button-danger" onClick={() => deleteTask(selectedTask)}>Delete</button>
                </div>
              )}
            </>
          ) : (
            <p className="state-message">Select a task to see its details.</p>
          )}
        </section>
        {isAdmin && (
          <form className="task-form-panel surface-panel" onSubmit={saveTask}>
            <p className="section-kicker">Admin tools</p>
            <h2>{editingId ? 'Edit task' : 'Create task'}</h2>
            <label htmlFor="task-title">
              Title
              <input
                id="task-title"
                required
                maxLength="200"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </label>
            <label htmlFor="task-description">
              Description
              <textarea
                id="task-description"
                required
                rows="5"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
            <label htmlFor="task-due-date">
              Due date
              <span className="optional">(optional)</span>
              <input
                id="task-due-date"
                type="date"
                value={form.due_date}
                onChange={(event) => setForm({ ...form, due_date: event.target.value })}
              />
            </label>
            <div className="form-actions">
              <button type="submit" disabled={saving} aria-busy={saving}>
                {saving ? 'Saving...' : editingId ? 'Save changes' : 'Create task'}
              </button>
              {editingId && (
                <button type="button" className="button-muted" onClick={startCreate}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        )}
      </div>
      {(notice || error) && (
        <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>
          {error || notice}
        </p>
      )}
    </main>
  )
}