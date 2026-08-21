import { useAuth } from '../context/AuthContext'
import WorkspaceNav from '../components/WorkspaceNav'

export default function Dashboard() {
  const { user, isAdmin } = useAuth()

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="dashboard" />
      <section className="dashboard-hero" aria-labelledby="dashboard-title">
        <div><p className="eyebrow">Overview</p><h1 id="dashboard-title">Good to see you, {user.username}.</h1><p className="intro">{isAdmin ? 'Keep your team and task assignments organized from one place.' : 'Pick up where you left off and keep your assigned work visible.'}</p></div>
        <a className="primary-link" href="/tasks">View tasks <span aria-hidden="true">-&gt;</span></a>
      </section>
      <section className="dashboard-grid" aria-label="Workspace shortcuts">
        <a className="dashboard-card" href="/tasks"><span className="card-icon" aria-hidden="true">01</span><strong>Tasks</strong><span>Browse tasks and inspect the details.</span></a>
        {!isAdmin && <a className="dashboard-card" href="/tasks#my-tasks"><span className="card-icon" aria-hidden="true">02</span><strong>My tasks</strong><span>See the tasks you have claimed.</span></a>}
        {isAdmin && <><a className="dashboard-card" href="/admin/users"><span className="card-icon" aria-hidden="true">02</span><strong>Users</strong><span>Review users and their assignments.</span></a><a className="dashboard-card" href="/admin/assignments"><span className="card-icon" aria-hidden="true">03</span><strong>Assignments</strong><span>Make precise assignment changes.</span></a><a className="dashboard-card" href="/admin/submissions"><span className="card-icon" aria-hidden="true">04</span><strong>Submissions</strong><span>Review submissions and share feedback.</span></a></>}
      </section>
    </main>
  )
}