import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import TechStackFilter from '../components/molecules/TechStackFilter'
import TaskSubmissionModal from '../components/molecules/TaskSubmissionModal'
import Pagination from '../components/Pagination'

/**
 * My Tasks — a dedicated page that shows ONLY the logged-in user's assignments.
 * Uses the existing /my/tasks/ API (which already supports ?tech_stack= filtering)
 * and keeps the assignment (unassign) and submission actions here.
 */
export default function MyTasks() {
  const { user, isAdmin } = useAuth()
  const [myTasks, setMyTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [techStacks, setTechStacks] = useState([])
  const [selectedStacks, setSelectedStacks] = useState([])
  const [myStacks, setMyStacks] = useState([])
  const [savingStacks, setSavingStacks] = useState(false)
  const [assignmentPending, setAssignmentPending] = useState(null)
  const [submissionAssignment, setSubmissionAssignment] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null })

  async function loadMyTasks(stackFilter = selectedStacks, pageNumber = page) {
    setLoading(true)
    setError('')
    try {
      // Paginated endpoint: filters apply before the page slice.
      const params = { page: pageNumber }
      if (stackFilter.length) params.tech_stack = stackFilter.join(',')
      const { data } = await api.get('/my/tasks/', { params })
      setMyTasks(Array.isArray(data?.results) ? data.results : [])
      setPagination({ count: data?.count ?? 0, next: data?.next ?? null, previous: data?.previous ?? null })
    } catch {
      setError('Your assigned tasks could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMyTasks(selectedStacks, page)
  }, [selectedStacks, page])

  function changeStackFilter(next) {
    setSelectedStacks(next)
    if (page !== 1) setPage(1) // filter change always restarts at page 1
  }

  useEffect(() => {
    api.get('/tasks/tech-stacks/')
      .then(({ data }) => setTechStacks(Array.isArray(data) ? data : []))
      .catch(() => {/* non-critical — the filter just won't populate */})
  }, [])

  useEffect(() => {
    if (Array.isArray(user?.tech_stack)) setMyStacks(user.tech_stack)
  }, [user?.tech_stack])

  async function unassign(assignment) {
    if (!window.confirm(`Remove yourself from ${assignment.task.title}?`)) return
    setAssignmentPending(assignment.task.id)
    setError('')
    setNotice('')
    try {
      await api.delete(`/tasks/${assignment.task.id}/assign/`)
      setNotice('Task unassigned.')
      await loadMyTasks()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Assignment could not be updated.')
    } finally {
      setAssignmentPending(null)
    }
  }

  async function saveMyStacks() {
    setSavingStacks(true)
    setError('')
    setNotice('')
    try {
      await api.patch('/auth/me/tech-stack/', { tech_stack: myStacks })
      setNotice('Your technologies have been updated.')
    } catch (requestError) {
      setError(requestError.response?.data?.tech_stack?.[0] || 'Your technologies could not be updated.')
    } finally {
      setSavingStacks(false)
    }
  }
if (isAdmin) {
    return (
      <main className="workspace-shell">
        <WorkspaceNav active="my-tasks" />
        <section className="page-intro">
          <div>
            <p className="eyebrow">Workspace</p>
            <h1>My tasks</h1>
            <p>Only members can claim and work on personal tasks.</p>
          </div>
        </section>
        <section className="admin-panel admin-wide-panel surface-panel">
          <p className="empty-state">
            <strong>Admins do not have personal tasks</strong>
            <span>Use <a href="/tasks">Tasks</a> to manage the team workspace.</span>
          </p>
        </section>
      </main>
    )
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="my-tasks" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>My tasks</h1>
          <p>See only the tasks assigned to you and keep your submissions moving.</p>
        </div>
        <div className="page-summary"><strong>{pagination.count}</strong><span>assigned tasks</span></div>
      </section>

      <section className="my-tasks-panel surface-panel" aria-labelledby="my-tasks-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Personal view</p>
            <h2 id="my-tasks-title">My tasks</h2>
            <p className="section-description">Your private list of tasks assigned to you.</p>
          </div>
        </div>

        <div className="my-tasks-filter-bar">
          <TechStackFilter
            options={techStacks}
            selected={selectedStacks}
            onChange={changeStackFilter}
            loading={!techStacks.length}
            supportingText="Filter your assigned tasks by technology"
          />
        </div>

        {loading && <p className="state-message">Loading your tasks...</p>}

        {!loading && myTasks.length === 0 && (
          <p className="empty-state">
            <strong>{selectedStacks.length ? 'No tasks match the selected technologies' : 'No assigned tasks yet'}</strong>
            <span>{selectedStacks.length ? 'Try removing a filter or selecting different technologies.' : 'Browse the available tasks and claim one to see it here.'}</span>
          </p>
        )}

        {!loading && myTasks.length > 0 && (
          <div className="my-task-list">
            {myTasks.map((assignment) => (
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
                    onClick={() => unassign(assignment)}
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
<div className="stack-editor">
          <p className="section-kicker">Your technologies</p>
          <p className="section-description">The technologies you choose are saved to your profile and shown to your admin. Admins cannot change this list.</p>
          <TechStackFilter
            options={techStacks}
            selected={myStacks}
            onChange={setMyStacks}
            loading={!techStacks.length}
            label="Technologies"
            supportingText="Choose your technology stack"
          />
          <button type="button" onClick={saveMyStacks} disabled={savingStacks} aria-busy={savingStacks}>
            {savingStacks ? 'Saving...' : 'Save my technologies'}
          </button>
        </div>
      </section>

      {(notice || error) && <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>{error || notice}</p>}
      {submissionAssignment && <TaskSubmissionModal assignment={submissionAssignment} onClose={() => setSubmissionAssignment(null)} onSubmitted={loadMyTasks} />}
    </main>
  )
}