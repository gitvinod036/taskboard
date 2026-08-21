import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import TechStackChip from '../components/atoms/TechStackChip'
import TechStackFilter from '../components/molecules/TechStackFilter'

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [pending, setPending] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [techStacks, setTechStacks] = useState([])
  const [selectedStacks, setSelectedStacks] = useState([])
  const [search, setSearch] = useState('')
  const [editingStacks, setEditingStacks] = useState([])
  const [savingStacks, setSavingStacks] = useState(false)

  async function loadUsers() {
    setLoading(true)
    setError('')
    try {
      const params = {}
      if (search.trim()) params.search = search.trim()
      if (selectedStacks.length) params.tech_stack = selectedStacks.join(',')
      const { data } = await api.get('/admin/users/', { params })
      setUsers(Array.isArray(data) ? data : [])
      if (selectedUser) {
        loadUser(selectedUser.id)
      }
    } catch {
      setError('Users could not be loaded.')
    } finally {
      setLoading(false)
    }
  }

  async function loadTechStacks() {
    try {
      const { data } = await api.get('/admin/tech-stacks/')
      setTechStacks(Array.isArray(data) ? data : [])
    } catch {
      setError('Tech stack options could not be loaded.')
    }
  }

  async function loadUser(userId) {
    setDetailLoading(true)
    try {
      const { data } = await api.get(`/admin/users/${userId}/`)
      setSelectedUser(data)
      setEditingStacks(data?.tech_stack || [])
    } catch {
      setError('User details could not be loaded.')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    loadTechStacks()
  }, [])

  useEffect(() => {
    const timer = setTimeout(loadUsers, 250)
    return () => clearTimeout(timer)
  }, [search, selectedStacks])

  function selectStacks(next) {
    setSelectedStacks(next)
    setSelectedUser(null)
  }

  function clearFilters() {
    setSearch('')
    setSelectedStacks([])
  }

  async function saveTechStacks() {
    if (!selectedUser) return
    setSavingStacks(true)
    setError('')
    try {
      const { data } = await api.patch(`/admin/users/${selectedUser.id}/`, { tech_stack: editingStacks })
      setSelectedUser(data)
      setNotice('Tech stack updated.')
      await loadUsers()
    } catch (requestError) {
      setError(requestError.response?.data?.tech_stack?.[0] || 'Tech stack could not be updated.')
    } finally {
      setSavingStacks(false)
    }
  }

  async function deleteUser(target) {
    if (!window.confirm('Deleting this user will remove their assignments. Tasks will remain.')) return
    setPending(`delete-${target.id}`)
    setError('')
    try {
      await api.delete(`/admin/users/${target.id}/`)
      setNotice('User deleted.')
      setSelectedUser(null)
      await loadUsers()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'User could not be deleted.')
    } finally {
      setPending(null)
    }
  }

  async function unassign(target, assignment) {
    if (!window.confirm(`Remove ${target.name} from ${assignment.task.title}?`)) return
    setPending(assignment.id)
    setError('')
    try {
      await api.delete(`/admin/users/${target.id}/tasks/${assignment.task.id}/`)
      setNotice('Assignment removed.')
      await Promise.all([loadUser(target.id), loadUsers()])
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Assignment could not be removed.')
    } finally {
      setPending(null)
    }
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="users" />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Users</h1>
          <p>Review your team and manage assignment access.</p>
        </div>
      </section>

      <section className="user-filter-bar surface-panel">
        <input
          aria-label="Search users"
          placeholder="Search users..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <TechStackFilter
          options={techStacks}
          selected={selectedStacks}
          onChange={selectStacks}
          loading={!techStacks.length}
        />
        <button
          type="button"
          className="button-muted"
          onClick={clearFilters}
          disabled={!search && !selectedStacks.length}
        >
          Clear filters
        </button>
      </section>

      <p className="results-count">
        {loading ? 'Loading users...' : `${users.length} users found`}
      </p>

      <div className="admin-grid">
        <section className="admin-panel surface-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Directory</p>
              <h2>Normal users</h2>
            </div>
            <span className="panel-count">{users.length}</span>
          </div>

          {loading && <p className="state-message">Loading users...</p>}
          {!loading && error && <p className="form-error" role="alert">{error}</p>}
          {!loading && !error && users.length === 0 && (
            <p className="empty-state">
              <strong>No matching users</strong>
              <span>Try clearing a filter or adjusting your search.</span>
            </p>
          )}

          <div className="user-list">
            {users.map((item) => (
              <button
                type="button"
                className={`user-row ${selectedUser?.id === item.id ? 'user-row-active' : ''}`}
                key={item.id}
                onClick={() => loadUser(item.id)}
              >
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.email || 'No email'}</small>
                  <span className="tech-stack-chips">
                    {item.tech_stack?.map((name) => (
                      <TechStackChip name={name} key={name} />
                    ))}
                  </span>
                </span>
                <em>{item.assigned_task_count ?? 0} assigned</em>
              </button>
            ))}
          </div>
        </section>

        <section className="admin-panel surface-panel">
          <p className="section-kicker">Selected user</p>
          {!selectedUser && (
            <p className="empty-state">
              <strong>Select a user</strong>
              <span>Choose someone from the directory to view assignments.</span>
            </p>
          )}
          {detailLoading && <p className="state-message">Loading assignments...</p>}
          {selectedUser && !detailLoading && (
            <>
              <div className="user-detail-heading">
                <div>
                  <h2>{selectedUser.name}</h2>
                  <p>{selectedUser.email || 'No email'}</p>
                  <div className="tech-stack-chips">
                    {selectedUser.tech_stack?.map((name) => (
                      <TechStackChip name={name} key={name} />
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  className="button-danger"
                  disabled={pending === `delete-${selectedUser.id}`}
                  onClick={() => deleteUser(selectedUser)}
                >
                  {pending === `delete-${selectedUser.id}` ? 'Deleting...' : 'Delete user'}
                </button>
              </div>

              <div className="stack-editor">
                <TechStackFilter
                  options={techStacks}
                  selected={editingStacks}
                  onChange={setEditingStacks}
                  loading={!techStacks.length}
                />
                <button
                  type="button"
                  onClick={saveTechStacks}
                  disabled={savingStacks}
                >
                  {savingStacks ? 'Saving...' : 'Save tech stack'}
                </button>
              </div>

              <div className="assignment-list">
                {(!selectedUser.assigned_tasks || selectedUser.assigned_tasks.length === 0) && (
                  <p className="empty-state">
                    <strong>No assignments</strong>
                    <span>This user has no assigned tasks.</span>
                  </p>
                )}
                {selectedUser.assigned_tasks?.map((assignment) => (
                  <article className="assignment-row" key={assignment.id}>
                    <div>
                      <strong>{assignment.task?.title}</strong>
                      <small>Assigned {assignment.assigned_date ? new Date(assignment.assigned_date).toLocaleDateString() : 'recently'}</small>
                    </div>
                    <button
                      type="button"
                      className="button-muted"
                      disabled={pending === assignment.id}
                      onClick={() => unassign(selectedUser, assignment)}
                    >
                      {pending === assignment.id ? 'Removing...' : 'Unassign'}
                    </button>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </div>

      {(notice || error) && (
        <p className={error ? 'toast toast-error' : 'toast'} role={error ? 'alert' : 'status'}>
          {error || notice}
        </p>
      )}
    </main>
  )
}