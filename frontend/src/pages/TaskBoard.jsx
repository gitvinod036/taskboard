import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import TaskSubmissionModal from '../components/molecules/TaskSubmissionModal'
import TechStackFilter from '../components/molecules/TechStackFilter'

const emptyForm = { title: '', description: '', due_date: '' }

export default function TaskBoard() {
  const { user, isAdmin, logout } = useAuth()
  const [tasks, setTasks] = useState([])
  const [myTasks, setMyTasks] = useState([])
  const [selectedTask, setSelectedTask] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [editingId, setEditingId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [myTasksLoading, setMyTasksLoading] = useState(false)
  const [assignmentPending, setAssignmentPending] = useState(null)
  const [submissionAssignment, setSubmissionAssignment] = useState(null)
  const [techStacks, setTechStacks] = useState([])
  const [selectedStacks, setSelectedStacks] = useState([])

  async function loadTasks() {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/tasks/')
      setTasks(data)
      setSelectedTask((current) => data.find((task) => task.id === current?.id) || data[0] || null)
    } catch {
      setError('Tasks could not be loaded. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTasks() }, [])

  async function loadMyTasks() {
    setMyTasksLoading(true)
    try {
      const { data } = await api.get('/my/tasks/')
      setMyTasks(data)
    } catch {
      setError('Your assigned tasks could not be loaded.')
    } finally {
      setMyTasksLoading(false)
    }
  }

  useEffect(() => {
    if (!isAdmin) loadMyTasks()
  }, [isAdmin])

  useEffect(() => {
    if (!isAdmin) {
      api.get('/tasks/tech-stacks/')
        .then(({ data }) => setTechStacks(Array.isArray(data) ? data : []))
        .catch(() => {/* non-critical — filter just won't populate */})
    }
  }, [isAdmin])

  async function toggleAssignment(task) {
    const assigning = !task.is_assigned
    setAssignmentPending(task.id)
    setError('')
    setNotice('')
    try {
      await (assigning ? api.post(`/tasks/${task.id}/assign/`) : api.delete(`/tasks/${task.id}/assign/`))
      setNotice(assigning ? 'Task assigned.' : 'Task unassigned.')
      await Promise.all([loadTasks(), loadMyTasks()])
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

  // async function saveTask(event) {
  //   event.preventDefault()
  //   setSaving(true)
  //   setError('')
  //   setNotice('')
  //   try {
  //     const request = editingId
  //       ? api.patch(`/tasks/${editingId}/`, form)
  //       : api.post('/tasks/', form)
  //     const { data } = await request
  //     setNotice(editingId ? 'Task updated.' : 'Task created.')
  //     setForm(emptyForm)
  //     setEditingId(null)
  //     await loadTasks()
  //     setSelectedTask(data)
  //   } catch (requestError) {
  //     setError(requestError.response?.data?.title?.[0] || requestError.response?.data?.description?.[0] || 'Task could not be saved.')
  //   } finally {
  //     setSaving(false)
  //   }
  // }
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
    if (!window.confirm(`Delete “${task.title}”?`)) return
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
      <section className="page-intro"><div><p className="eyebrow">Workspace</p><h1>Tasks</h1><p>Browse every task, inspect the details, and keep your assignments moving.</p></div><div className="page-summary"><strong>{tasks.length}</strong><span>visible tasks</span></div></section>
      <div className="workspace-grid">
        <section className="task-list-panel surface-panel" aria-labelledby="task-list-title">
          <div className="section-heading"><div><p className="section-kicker">Workspace</p><h2 id="task-list-title">All tasks</h2></div>{isAdmin && <button type="button" onClick={startCreate}>New task</button>}</div>
          {loading && <p className="state-message">Loading tasks...</p>}
          {!loading && error && <p className="form-error" role="alert">{error}</p>}
          {!loading && !error && tasks.length === 0 && <p className="state-message">No tasks yet.</p>}
          <div className="task-list">{tasks.map((task) => <div className={`task-row ${selectedTask?.id === task.id ? 'task-row-active' : ''}`} key={task.id}><button type="button" className="task-select" onClick={() => setSelectedTask(task)}><strong>{task.title}</strong><span>{task.due_date ? `Due ${task.due_date}` : 'No due date'}</span></button>{!isAdmin && <button type="button" className={task.is_assigned ? 'assignment-button assignment-button-active' : 'assignment-button'} disabled={assignmentPending === task.id} onClick={() => toggleAssignment(task)}>{assignmentPending === task.id ? 'Updating...' : task.is_assigned ? 'Assigned · Unassign' : 'Assign'}</button>}</div>)}</div>
        </section>
        <section className="task-detail-panel surface-panel" aria-labelledby="task-detail-title">
          {selectedTask ? <><p className="section-kicker">Task detail</p><h2 id="task-detail-title">{selectedTask.title}</h2><p className="task-description">{selectedTask.description}</p><p className="task-due">{selectedTask.due_date ? `Due ${selectedTask.due_date}` : 'No due date'}</p>{isAdmin && <div className="detail-actions"><button type="button" onClick={() => startEdit(selectedTask)}>Edit</button><button type="button" className="button-danger" onClick={() => deleteTask(selectedTask)}>Delete</button></div>}</> : <p className="state-message">Select a task to see its details.</p>}
        </section>
        {isAdmin && <form className="task-form-panel surface-panel" onSubmit={saveTask}><p className="section-kicker">Admin tools</p><h2>{editingId ? 'Edit task' : 'Create task'}</h2><label htmlFor="task-title">Title<input id="task-title" required maxLength="200" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label htmlFor="task-description">Description<textarea id="task-description" required rows="5" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><label htmlFor="task-due-date">Due date <span className="optional">(optional)</span><input id="task-due-date" type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></label><div className="form-actions"><button type="submit" disabled={saving} aria-busy={saving}>{saving ? 'Saving...' : editingId ? 'Save changes' : 'Create task'}</button>{editingId && <button type="button" className="button-muted" onClick={startCreate}>Cancel</button>}</div></form>}
      </div>
      {!isAdmin && (() => {

        const filteredMyTasks = selectedStacks.length
  ? myTasks.filter((a) => {
      const taskTechStacks = Array.isArray(a.task.tech_stack)
        ? a.task.tech_stack
        : []

      console.log("SELECTED:", selectedStacks)
      console.log("TASK TECH STACKS:", taskTechStacks)

      const matches = selectedStacks.every((selected) =>
        taskTechStacks.some(
          (tech) =>
            String(tech).trim().toLowerCase() ===
            String(selected).trim().toLowerCase()
        )
      )

      console.log("MATCH:", matches)

      return matches
    })
  : myTasks
        return (
          <section className="my-tasks-panel surface-panel" id="my-tasks" aria-labelledby="my-tasks-title">
            <div className="section-heading">
              <div>
                <p className="section-kicker">Personal view</p>
                <h2 id="my-tasks-title">My tasks</h2>
                <p className="section-description">Your private list of tasks assigned to you.</p>
              </div>
            </div>

            {/* Technology filter — only visible once tasks have loaded */}
            {!myTasksLoading && myTasks.length > 0 && (
              <div className="my-tasks-filter-bar">
                <TechStackFilter
                  options={techStacks}
                  selected={selectedStacks}
                  onChange={setSelectedStacks}
                  loading={!techStacks.length}
                  supportingText="Filter your assigned tasks by technology"
                />
              </div>
            )}

            {myTasksLoading && <p className="state-message">Loading your tasks...</p>}

            {!myTasksLoading && myTasks.length === 0 && (
              <p className="empty-state">
                <strong>No assigned tasks yet</strong>
                <span>Assign a task from the list above to see it here.</span>
              </p>
            )}

            {!myTasksLoading && myTasks.length > 0 && filteredMyTasks.length === 0 && (
              <p className="empty-state">
                <strong>No tasks match the selected technologies</strong>
                <span>Try removing a filter or selecting different technologies.</span>
              </p>
            )}

            {!myTasksLoading && filteredMyTasks.length > 0 && (
              <div className="my-task-list">
                {filteredMyTasks.map((assignment) => (
                  <article className="my-task-item" key={assignment.id}>
                    <div>
                      <h3>{assignment.task.title}</h3>
                      <p>{assignment.task.description}</p>
                      <span>
                        {assignment.task.due_date ? `Due ${assignment.task.due_date}` : 'No due date'}
                        {' · '}
                        Assigned {new Date(assignment.assigned_date).toLocaleDateString()}
                      </span>
                      {assignment.task.tech_stack.length > 0 && (
                        <span className="tech-stack-chips">
                          {assignment.task.tech_stack.map((name) => (
                            <span className="tech-stack-chip" key={name}>{name}</span>
                          ))}
                        </span>
                      )}
                      {assignment.submission && (
                        <span className={`submission-status submission-${assignment.submission.status.toLowerCase()}`}>
                          {assignment.submission.status === 'PENDING' ? 'Pending Review' : assignment.submission.status}
                          {assignment.submission.feedback ? ` · ${assignment.submission.feedback}` : ''}
                        </span>
                      )}
                    </div>
                    <div className="my-task-actions">
                      <button
                        type="button"
                        className="button-muted"
                        disabled={assignmentPending === assignment.task.id}
                        onClick={() => toggleAssignment({ ...assignment.task, is_assigned: true })}
                      >
                        {assignmentPending === assignment.task.id ? 'Updating...' : 'Unassign'}
                      </button>
                      {(!assignment.submission || assignment.submission.status === 'REJECTED') && (
                        <button type="button" onClick={() => setSubmissionAssignment(assignment)}>
                          {assignment.submission ? 'Resubmit' : 'Submit'}
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )
      })()}
      {(notice || error) && <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>{error || notice}</p>}
      {submissionAssignment && <TaskSubmissionModal assignment={submissionAssignment} onClose={() => setSubmissionAssignment(null)} onSubmitted={loadMyTasks} />}
    </main>
  )
}