import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'
import { DonutChart, HorizontalBars, TrendChart } from '../components/dashboard/DashboardCharts'

const STATUS_COLORS = {
  COMPLETED: '#16a34a',
  IN_PROGRESS: '#64748b',
  PENDING_REVIEW: '#d97706',
}

const ACTIVITY_VERBS = {
  ASSIGNMENT: 'assigned',
  SUBMISSION: 'submitted',
  REVIEW: 'reviewed',
}

const QUICK_ACTIONS = [
  { href: '/tasks', number: '01', title: 'Create task', description: 'Add a new task to the board.' },
  { href: '/tasks', number: '02', title: 'View tasks', description: 'Browse every task on the board.' },
  { href: '/admin/users', number: '03', title: 'Manage users', description: 'Review members and their assignments.' },
  { href: '/admin/users', number: '04', title: 'Manage technology stack', description: 'Update the stacks members work with.' },
]

function asCount(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function asList(value) {
  return Array.isArray(value) ? value : []
}

function formatDate(value) {
  if (!value) return 'No due date'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown date' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatTimestamp(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown time' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatClock(value) {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// Mirrors the backend's Monday-start weekly bucketing so charts line up.
function weekStartOf(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const weekday = (date.getDay() + 6) % 7
  date.setHours(0, 0, 0, 0)
  date.setDate(date.getDate() - weekday)
  return date
}

function weeklySeries(rows, dateKey, weeks = 8) {
  const today = weekStartOf(new Date())
  if (!today) return []
  const first = new Date(today)
  first.setDate(first.getDate() - 7 * (weeks - 1))
  const buckets = new Map()
  for (let index = 0; index < weeks; index += 1) {
    const bucket = new Date(first)
    bucket.setDate(first.getDate() + 7 * index)
    buckets.set(bucket.getTime(), 0)
  }
  asList(rows).forEach((row) => {
    const bucketStart = weekStartOf(row?.[dateKey])
    if (bucketStart && buckets.has(bucketStart.getTime())) {
      buckets.set(bucketStart.getTime(), buckets.get(bucketStart.getTime()) + 1)
    }
  })
  return Array.from(buckets.entries()).map(([timestamp, count]) => ({
    week_start: new Date(timestamp).toISOString().slice(0, 10),
    completions: count,
  }))
}

export default function AdminMonitoring() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(false)
  const [refreshError, setRefreshError] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [reloadToken, setReloadToken] = useState(0)
  // Tracks the latest successful payload so a failed refresh can fall back
  // to an inline warning instead of wiping rendered analytics.
  const dataRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    const isRefresh = reloadToken > 0
    // Initial load shows the skeleton; manual refresh keeps data on screen.
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    Promise.all([
      api.get('/admin/dashboard/'),
      api.get('/admin/submissions/'),
    ])
      .then(([dashboardResponse, submissionsResponse]) => {
        if (cancelled) return
        const payload = {
          dashboard: dashboardResponse.data && typeof dashboardResponse.data === 'object' ? dashboardResponse.data : {},
          // /admin/submissions/ is paginated; aggregate over the current page
          // only. Full-list aggregation remains a future backend optimization.
          submissions: asList(submissionsResponse.data?.results),
        }
        dataRef.current = payload
        setData(payload)
        setError(false)
        setRefreshError(false)
        setLastUpdated(new Date())
      })
      .catch(() => {
        if (cancelled) return
        if (isRefresh && dataRef.current) setRefreshError(true)
        else setError(true)
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
          setRefreshing(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [reloadToken])

  const dash = data?.dashboard ?? {}
  const totals = dash.totals ?? {}
  const submissions = data?.submissions ?? []

  const submissionCounts = { APPROVED: 0, PENDING: 0, REJECTED: 0 }
  submissions.forEach((submission) => {
    const status = submission?.status
    if (status in submissionCounts) submissionCounts[status] += 1
  })
  const submissionTrendPoints = weeklySeries(submissions, 'submitted_at', 8)
  const completionTrendPoints = asList(dash.completion_trend?.points)
  const statusSegments = asList(dash.status_distribution).map((item) => ({
    key: item.key,
    label: item.label,
    count: asCount(item.count),
    color: STATUS_COLORS[item.key] || '#94a3b8',
  }))
  const topUsers = asList(dash.top_users)
  const techItems = asList(dash.technology_distribution).map((item) => ({ label: item.technology || 'Unknown', value: asCount(item.task_count) }))
  const overdueItems = asList(dash.overdue_tasks?.items)
  const overdueTotal = asCount(dash.overdue_tasks?.total)
  const pendingReviewTotal = asCount(totals.pending_review)
  const pendingSubmissions = submissions.filter((submission) => submission?.status === 'PENDING').slice(0, 5)
  const recentActivity = asList(dash.recent_activity)
  const attentionClear = overdueTotal === 0 && pendingReviewTotal === 0

  const kpis = [
    { key: 'total-users', label: 'Total users', value: asCount(totals.total_users), accent: 'blue' },
    { key: 'active-users', label: 'Active users', value: asCount(totals.active_users), accent: 'green' },
    { key: 'total-tasks', label: 'Total tasks', value: asCount(totals.total_tasks), accent: 'blue' },
    { key: 'completed', label: 'Completed', value: asCount(totals.completed), accent: 'green' },
    { key: 'in-progress', label: 'In progress', value: asCount(totals.in_progress), accent: 'slate' },
    { key: 'submissions', label: 'Submissions', value: submissions.length, accent: 'amber' },
    { key: 'pending-review', label: 'Pending review', value: pendingReviewTotal, accent: 'amber' },
    { key: 'overdue', label: 'Overdue', value: overdueTotal, accent: 'red' },
  ]


  function triggerRefresh() {
    if (refreshing || loading) return
    setReloadToken((token) => token + 1)
  }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="monitoring" />
      <section className="dashboard-hero" aria-labelledby="monitoring-title">
        <div>
          <p className="eyebrow">Analytics</p>
          <h1 id="monitoring-title">Monitoring.</h1>
          <p className="intro">Platform activity and performance overview</p>
        </div>
        <div className="monitoring-meta">
          <span className="monitoring-updated">
            {loading ? 'Loading latest data...' : `Last updated ${formatClock(lastUpdated)}`}
          </span>
          <button type="button" className="button-muted" onClick={triggerRefresh} disabled={loading || refreshing}>
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </section>

      {refreshError && !error && (
        <div className="refresh-alert" role="alert">
          <span>Refresh failed — showing the last successfully loaded analytics.</span>
          <button type="button" className="button-small" onClick={triggerRefresh} disabled={refreshing}>Try again</button>
        </div>
      )}

      {error && (
        <section className="surface-panel dashboard-error-panel" role="alert">
          <p className="section-kicker">Monitoring</p>
          <strong>Monitoring data could not be loaded.</strong>
          <p className="route-state">The server did not respond with analytics data. Check your connection and try again.</p>
          <button type="button" onClick={triggerRefresh} disabled={refreshing}>{refreshing ? 'Retrying...' : 'Retry'}</button>
        </section>
      )}

      {!error && loading && (
        <div aria-busy="true" aria-live="polite">
          <p className="state-message">Loading monitoring analytics...</p>
          <div className="stats-grid">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((placeholder) => <div className="stat-card skeleton-card" key={placeholder} />)}
          </div>
        </div>
      )}

      {!error && !loading && data && (
        <>
          <section className="stats-grid" aria-label="Key monitoring metrics">
            {kpis.map((card) => (
              <article className={`stat-card stat-accent-${card.accent}`} key={card.key}>
                <span className="stat-value">{card.value}</span>
                <span className="stat-label">{card.label}</span>
              </article>
            ))}
          </section>


          <section className={`surface-panel attention-section${attentionClear ? ' attention-clear' : ''}`} aria-label="Needs attention">
            <div className="attention-header">
              <p className="section-kicker">Needs attention</p>
              <p className="attention-summary">
                {attentionClear
                  ? 'All clear — nothing is overdue and no reviews are waiting.'
                  : `${overdueTotal} overdue ${overdueTotal === 1 ? 'task' : 'tasks'} · ${pendingReviewTotal} awaiting review`}
              </p>
            </div>
            <div className="attention-grid">
              <div className="attention-cell">
                <p className="attention-heading"><span className="severity-dot severity-red" aria-hidden="true" /><span>Overdue tasks</span>{overdueTotal > 0 && <span className="attention-count">{overdueTotal}</span>}</p>
                {overdueItems.length ? (
                  <ul className="overdue-list">
                    {overdueItems.map((task) => (
                      <li className="overdue-row" key={task.id}>
                        <a className="row-link-inner" href="/tasks"><strong>{task.title || 'Untitled task'}</strong><small>Due {formatDate(task.due_date)}</small></a>
                        <span className="overdue-days">{asCount(task.days_overdue)}d overdue</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-state"><strong>Nothing is overdue</strong><span>Every dated task is done or still on schedule.</span></p>
                )}
                <a className="attention-link" href="/tasks">Open task board <span aria-hidden="true">-&gt;</span></a>
              </div>
              <div className="attention-cell">
                <p className="attention-heading"><span className="severity-dot severity-amber" aria-hidden="true" /><span>Pending reviews</span>{pendingReviewTotal > 0 && <span className="attention-count">{pendingReviewTotal}</span>}</p>
                {pendingSubmissions.length ? (
                  <ul className="overdue-list">
                    {pendingSubmissions.map((submission) => (
                      <li className="overdue-row" key={submission.id}>
                        <a className="row-link-inner" href="/admin/submissions"><strong>{submission.task?.title || 'Untitled task'}</strong><small>{submission.user?.username || 'Unknown user'} · {formatTimestamp(submission.submitted_at)}</small></a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-state"><strong>No pending reviews</strong><span>Nothing is waiting for feedback right now.</span></p>
                )}
                <a className="attention-link" href="/admin/submissions">Review submissions <span aria-hidden="true">-&gt;</span></a>
              </div>
              <div className="attention-cell">
                <p className="attention-heading"><span className="severity-dot severity-slate" aria-hidden="true" /><span>Unassigned tasks</span></p>
                <p className="empty-state"><strong>NOT CURRENTLY SUPPORTED BY DATA MODEL</strong><span>No reliable unassigned-task metric exists in the current APIs.</span></p>
              </div>
            </div>
          </section>


          <div className="dashboard-panels">
            <section className="surface-panel chart-panel" aria-label="Task status distribution">
              <p className="section-kicker">Task status distribution</p>
              <div className="donut-wrap">
                <DonutChart segments={statusSegments} ariaLabel="Task status distribution donut chart" />
                <ul className="donut-legend">
                  {statusSegments.map((segment) => (
                    <li key={segment.key}>
                      <span className="legend-dot" style={{ background: segment.color }} aria-hidden="true" />
                      <span>{segment.label}</span>
                      <strong>{segment.count}</strong>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
            <section className="surface-panel chart-panel" aria-label="Completion trend">
              <p className="section-kicker">Completion trend · trailing 8 weeks</p>
              <TrendChart points={completionTrendPoints} ariaLabel="Tasks completed per week over the trailing eight weeks" />
            </section>
          </div>

          <div className="dashboard-panels">
            <section className="surface-panel chart-panel" aria-label="Submission analytics">
              <p className="section-kicker">Submission analytics</p>
              <div className="submission-chips">
                <div className="chip-stat"><span className="chip-value">{submissions.length}</span><span className="chip-label">Total</span></div>
                <div className="chip-stat chip-amber"><span className="chip-value">{submissionCounts.PENDING}</span><span className="chip-label">Pending review</span></div>
                <div className="chip-stat chip-green"><span className="chip-value">{submissionCounts.APPROVED}</span><span className="chip-label">Approved</span></div>
                <div className="chip-stat chip-red"><span className="chip-value">{submissionCounts.REJECTED}</span><span className="chip-label">Rejected</span></div>
              </div>
              <p className="chart-subheading">Submissions per week · trailing 8 weeks</p>
              <TrendChart points={submissionTrendPoints} height={170} ariaLabel="Submissions per week over the trailing eight weeks" />
            </section>
            <section className="surface-panel chart-panel" aria-label="Top contributors">
              <p className="section-kicker">Top contributors</p>
              {topUsers.length ? (
                <ol className="rank-list">
                  {topUsers.map((entry) => (
                    <li className="rank-row" key={entry.id}>
                      <span className="rank-name">{entry.name || entry.username || 'Unknown user'}</span>
                      <span className="rank-badge">{asCount(entry.completed_tasks)} completed</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="empty-state"><strong>No completions yet</strong><span>Approved submissions will rank members here.</span></p>
              )}
            </section>
            <section className="surface-panel chart-panel" aria-label="Technology distribution">
              <p className="section-kicker">Technology distribution</p>
              <HorizontalBars items={techItems} />
            </section>
          </div>


          <div className="dashboard-panels">
            <section className="surface-panel chart-panel" aria-label="Recent activity">
              <p className="section-kicker">Recent activity</p>
              {recentActivity.length ? (
                <ul className="activity-list">
                  {recentActivity.map((event, index) => (
                    <li className="activity-row" key={`${event.type}-${index}`}>
                      <span className={`activity-type activity-${String(event.type).toLowerCase()}`}>{ACTIVITY_VERBS[event.type] || 'updated'}</span>
                      <div><strong>{event.task_title || 'Untitled task'}</strong><small>{event.actor || 'Someone'} · {formatTimestamp(event.timestamp)}</small></div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-state"><strong>No activity yet</strong><span>Assignments and submissions will show up here.</span></p>
              )}
            </section>
          </div>

          <section className="dashboard-grid" aria-label="Quick actions">
            {QUICK_ACTIONS.map((action) => (
              <a className="dashboard-card" href={action.href} key={action.title}>
                <span className="card-icon" aria-hidden="true">{action.number}</span>
                <strong>{action.title}</strong>
                <span>{action.description}</span>
              </a>
            ))}
          </section>
        </>
      )}
    </main>
  )
}

