const KPI_CARDS = [
  { key: 'total_tasks', label: 'Total tasks' },
  { key: 'completed', label: 'Completed' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'pending_review', label: 'Pending review' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'total_users', label: 'Total users' },
  { key: 'active_users', label: 'Active users' },
]

const ASSIGNMENT_ROWS = [
  { key: 'without_submission', label: 'No submission yet' },
  { key: 'pending_review', label: 'Pending review' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
]

const TASK_ROWS = [
  { key: 'assigned', label: 'Assigned' },
  { key: 'unassigned', label: 'Unassigned' },
]

function count(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function percent(value, total) {
  return total > 0 ? Math.round((count(value) / total) * 100) : 0
}

function formatDate(value) {
  if (!value) return 'No due date'
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString()
}

function DistributionBars({ rows, total }) {
  return (
    <ul className="metric-bars">
      {rows.map((row) => (
        <li key={row.label}>
          <span className="metric-bar-label">{row.label}</span>
          <span className="metric-bar-track"><span className="metric-bar-fill" style={{ width: `${percent(row.value, total)}%` }} /></span>
          <span className="metric-bar-value">{count(row.value)} · {percent(row.value, total)}%</span>
        </li>
      ))}
    </ul>
  )
}

export default function DashboardMetrics({ data }) {
  const summary = data?.summary || {}
  const tasks = data?.status_distribution?.tasks || {}
  const assignments = data?.status_distribution?.assignments || {}
  const technologies = (data?.technology_distribution || []).filter((row) => count(row?.task_count) > 0)
  const trend = data?.completion_trend || []
  const topUsers = data?.top_users || []
  const overdueTasks = data?.overdue_tasks || []
  const trendPeak = trend.reduce((peak, point) => Math.max(peak, count(point?.completed)), 0)
  const trendTotal = trend.reduce((sum, point) => sum + count(point?.completed), 0)

  return (
    <>
      <section className="metric-kpi-grid" aria-label="Key metrics">
        {KPI_CARDS.map((card) => (
          <article className="metric-kpi" key={card.key}>
            <strong>{count(summary[card.key])}</strong>
            <span>{card.label}</span>
          </article>
        ))}
      </section>

      <section className="metric-grid" aria-label="Dashboard metrics">
        <article className="metric-panel">
          <p className="section-kicker">Distribution</p>
          <h2>Task status</h2>
          <p className="section-description">{count(tasks.total)} tasks. Tasks have no lifecycle status, so progress is measured on assignments and submissions.</p>
          <DistributionBars rows={TASK_ROWS.map((row) => ({ label: row.label, value: tasks[row.key] }))} total={count(tasks.total)} />
          <h3 className="metric-subheading">Assignments ({count(assignments.total)})</h3>
          {count(assignments.total) === 0
            ? <p className="empty-state"><strong>No assignments yet</strong><span>Assignment progress appears once users claim tasks.</span></p>
            : <DistributionBars rows={ASSIGNMENT_ROWS.map((row) => ({ label: row.label, value: assignments[row.key] }))} total={count(assignments.total)} />}
        </article>

        <article className="metric-panel">
          <p className="section-kicker">Last 30 days</p>
          <h2>Completion trend</h2>
          <p className="section-description">{trendTotal} approved submission{trendTotal === 1 ? '' : 's'} in the last 30 days.</p>
          {trend.length === 0
            ? <p className="empty-state"><strong>No trend data</strong><span>Approved submissions will build this chart.</span></p>
            : <>
              <ul className="metric-trend">
                {trend.map((point) => (
                  <li key={String(point?.date)} title={`${formatDate(point?.date)}: ${count(point?.completed)}`}>
                    <span className="metric-trend-bar" style={{ height: trendPeak > 0 ? `${Math.max((count(point?.completed) / trendPeak) * 100, 3)}%` : '3%' }} />
                  </li>
                ))}
              </ul>
              <p className="metric-trend-axis"><span>{formatDate(trend[0]?.date)}</span><span>{formatDate(trend[trend.length - 1]?.date)}</span></p>
            </>}
        </article>

        <article className="metric-panel">
          <p className="section-kicker">Leaderboard</p>
          <h2>Top users</h2>
          {topUsers.length === 0
            ? <p className="empty-state"><strong>No users yet</strong><span>Users appear here once they have assignments.</span></p>
            : <ul className="metric-list">
              {topUsers.map((user) => (
                <li key={user?.id}>
                  <strong>{user?.name || 'Unknown user'}</strong>
                  <span>{count(user?.completed_count)} completed · {count(user?.assigned_count)} assigned</span>
                </li>
              ))}
            </ul>}
        </article>

        <article className="metric-panel">
          <p className="section-kicker">Attention</p>
          <h2>Overdue work</h2>
          <p className="section-description">{count(summary.overdue)} overdue assignment{count(summary.overdue) === 1 ? '' : 's'} in total.</p>
          {overdueTasks.length === 0
            ? <p className="empty-state"><strong>Nothing overdue</strong><span>Every dated assignment is still on time.</span></p>
            : <ul className="metric-list">
              {overdueTasks.map((row) => (
                <li key={`${row?.task_id}-${row?.user?.id}`}>
                  <strong>{row?.title || 'Untitled task'}</strong>
                  <span>{row?.user?.name || 'Unknown user'} · due {formatDate(row?.due_date)} · {row?.submission_status || 'no submission'}</span>
                </li>
              ))}
            </ul>}
        </article>

        <article className="metric-panel metric-panel-wide">
          <p className="section-kicker">Coverage</p>
          <h2>Technology distribution</h2>
          {technologies.length === 0
            ? <p className="empty-state"><strong>No technologies tagged</strong><span>Add a tech stack to a task to see coverage.</span></p>
            : <DistributionBars rows={technologies.map((row) => ({ label: row?.name || 'Unnamed', value: row?.task_count }))} total={count(tasks.total)} />}
        </article>
      </section>
    </>
  )
}
