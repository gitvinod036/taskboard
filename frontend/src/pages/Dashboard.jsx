import { useEffect, useState } from 'react'

import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import WorkspaceNav from '../components/WorkspaceNav'

/**
 * Dashboard — the TaskBoard command center.
 *
 * Everything shown here comes from existing backend APIs (fetched exactly
 * once per load): /my/tasks/ + one evaluation lookup + /coding/leaderboard/
 * for members, /admin/dashboard/ + /coding/leaderboard/ for admins. No
 * metrics are fabricated client-side and no AI request is ever triggered
 * from the dashboard — evaluations are read from stored rows only.
 */

const MY_TASKS_PAGE_SIZE = 100

function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function leaderboardValue(row, key) {
  return row && typeof row[key] === 'number' ? row[key] : 0
}

function formatDue(value) {
  if (!value) return 'No due date'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'No due date' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const STATUS_LABELS = {
  DRAFT: 'Draft',
  PENDING: 'Pending review',
  IN_PROGRESS: 'In progress',
  REVIEW: 'In review',
  APPROVED: 'Completed',
  REJECTED: 'Needs resubmission',
}

const RUBRIC_LABELS = {
  requirement_completion: ['Requirement Completion', 3],
  correctness: ['Correctness', 2],
  quality: ['Quality', 2],
  completeness: ['Completeness', 2],
  clarity: ['Clarity', 1],
}

function deriveTaskRows(results) {
  return (Array.isArray(results) ? results : []).map((item) => ({
    assignmentId: item?.id,
    taskId: item?.task?.id,
    title: item?.task?.title || 'Untitled task',
    difficulty: item?.task?.difficulty || '',
    points: typeof item?.task?.points === 'number' ? item.task.points : 0,
    dueDate: item?.task?.due_date || null,
    submission: item?.submission || null,
    status: item?.submission?.status || null,
    earnedPoints: typeof item?.submission?.earned_points === 'number' ? item.submission.earned_points : 0,
  }))
}

function summarizeTasks(rows) {
  const completed = rows.filter((row) => row.submission?.status === 'APPROVED').length
  const pendingReview = rows.filter((row) => row.submission?.status === 'PENDING' || row.submission?.status === 'REVIEW').length
  const rejected = rows.filter((row) => row.submission?.status === 'REJECTED').length
  const inProgress = rows.length - completed - pendingReview
  return { completed, pendingReview, rejected, inProgress: Math.max(inProgress, 0) }
}

function pickLatestApproved(rows) {
  const approved = rows.filter((row) => row.submission?.status === 'APPROVED' && row.submission?.id)
  if (!approved.length) return null
  return approved.reduce((latest, row) => (
    new Date(row.submission.submitted_at || 0) > new Date(latest.submission.submitted_at || 0) ? row : latest
  ), approved[0])
}

export default function Dashboard() {
  const { user, isAdmin } = useAuth()
  const [phase, setPhase] = useState('loading')
  const [taskRows, setTaskRows] = useState([])
  const [taskCount, setTaskCount] = useState(0)
  const [evaluation, setEvaluation] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [leaders, setLeaders] = useState([])
  const [leaderboardError, setLeaderboardError] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function loadLeaderboard() {
      try {
        const { data } = await api.get('/coding/leaderboard/')
        if (!cancelled) {
          setLeaders(Array.isArray(data) ? data : [])
          setLeaderboardError(false)
        }
      } catch {
        if (!cancelled) setLeaderboardError(true)
      }
    }

    async function load() {
      setPhase('loading')
      setLeaderboardError(false)
      loadLeaderboard()
      try {
        if (isAdmin) {
          const { data } = await api.get('/admin/dashboard/')
          if (cancelled) return
          setMetrics(data || {})
          setTaskRows([])
          setTaskCount(0)
        } else {
          const { data } = await api.get('/my/tasks/', { params: { page_size: MY_TASKS_PAGE_SIZE } })
          if (cancelled) return
          const rows = deriveTaskRows(data?.results)
          setTaskRows(rows)
          setTaskCount(typeof data?.count === 'number' ? data.count : rows.length)
        }
        setPhase('ready')
      } catch {
        if (!cancelled) setPhase('error')
      }
    }

    load()
    return () => { cancelled = true }
  }, [isAdmin])

  const summary = summarizeTasks(taskRows)
  const myRow = leaders.find((row) => row.username === user?.username) || null
  const latestApproved = pickLatestApproved(taskRows)

  const [evaluationState, setEvaluationState] = useState('missing')
  useEffect(() => {
    let cancelled = false
    const submissionId = latestApproved?.submission?.id
    if (!submissionId) {
      setEvaluationState('missing')
      setEvaluation(null)
      return undefined
    }
    setEvaluationState('loading')
    api.get(`/my/tasks/submissions/${submissionId}/evaluation/`)
      .then(({ data }) => {
        if (cancelled) return
        setEvaluation(data || null)
        setEvaluationState(data?.status === 'FAILED' ? 'failed' : 'ready')
      })
      .catch(() => {
        if (!cancelled) setEvaluationState('missing')
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestApproved?.submission?.id])

  const retry = () => { window.location.reload() }

  return (
    <main className="workspace-shell">
      <WorkspaceNav active="dashboard" />

      <section className="page-intro db-hero" aria-labelledby="dashboard-title">
        <div>
          <p className="eyebrow">Overview</p>
          <h1 id="dashboard-title">Dashboard</h1>
          <p>{isAdmin
            ? 'Platform activity and performance at a glance.'
            : 'Track your work, progress, points and performance.'}</p>
        </div>
        <a className="primary-link" href={isAdmin ? '/admin/monitoring' : '/my-tasks'}>
          {isAdmin ? 'Open monitoring' : 'View my tasks'} <span aria-hidden="true">-&gt;</span>
        </a>
      </section>

      {phase === 'loading' && <DashboardSkeleton isAdmin={isAdmin} />}

      {phase === 'error' && (
        <div className="db-panel db-error-panel" role="alert">
          <strong>Unable to load the dashboard</strong>
          <p>We couldn&rsquo;t retrieve your workspace data. Please try again.</p>
          <button type="button" className="button-primary" onClick={retry}>Retry</button>
        </div>
      )}

      {phase === 'ready' && (
        <>
          <KpiStrip
            isAdmin={isAdmin}
            metrics={metrics}
            taskCount={taskCount}
            summary={summary}
            totalPoints={leaderboardValue(myRow, 'total_points')}
            rank={myRow?.rank}
          />

          {isAdmin ? (
            <AdminSections metrics={metrics} leaders={leaders} leaderboardError={leaderboardError} />
          ) : (
            <UserSections
              rows={taskRows}
              summary={summary}
              evaluation={evaluation}
              evaluationState={evaluationState}
              latestApproved={latestApproved}
              leaders={leaders}
              myRow={myRow}
              leaderboardError={leaderboardError}
              username={user?.username}
            />
          )}

          <QuickActions isAdmin={isAdmin} />
        </>
      )}
    </main>
  )
}

function KpiStrip({ isAdmin, metrics, taskCount, summary, totalPoints, rank }) {
  const totals = metrics?.totals || {}
  const items = isAdmin
    ? [
      { label: 'Total users', value: num(totals.total_users), note: 'Workspace members' },
      { label: 'Active users', value: num(totals.active_users), note: 'Engaged this period' },
      { label: 'Total tasks', value: num(totals.total_tasks), note: 'On the board' },
      { label: 'Completed', value: num(totals.completed), note: 'Approved submissions' },
      { label: 'Pending review', value: num(totals.pending_review), note: 'Awaiting review' },
      { label: 'Overdue', value: num(totals.overdue), note: 'Past due date' },
    ]
    : [
      { label: 'My tasks', value: num(taskCount), note: 'Assigned to you' },
      { label: 'Completed', value: num(summary.completed), note: 'Approved submissions' },
      { label: 'In progress', value: num(summary.inProgress), note: 'Waiting on you' },
      { label: 'Pending review', value: num(summary.pendingReview), note: 'With the reviewer' },
      { label: 'Points', value: num(totalPoints), note: 'Task + Coding' },
      { label: 'Rank', value: rank ? `#${rank}` : '—', note: rank ? 'On the leaderboard' : 'Earn points to rank' },
    ]
  return (
    <section className="db-kpi-strip" aria-label={isAdmin ? 'Platform metrics' : 'Your summary'}>
      {items.map((item) => (
        <div className="db-kpi" key={item.label}>
          <span className="db-kpi-label">{item.label}</span>
          <strong className="db-kpi-value">{item.value}</strong>
          <span className="db-kpi-note">{item.note}</span>
        </div>
      ))}
    </section>
  )
}
function Panel({ title, kicker, className = '', actions, children }) {
  return (
    <section className={`db-panel ${className}`.trim()}>
      <div className="db-panel-head">
        <div>
          {kicker && <p className="db-kicker">{kicker}</p>}
          <h2 className="db-panel-title">{title}</h2>
        </div>
        {actions && <div className="db-panel-actions">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

function ProgressBar({ value, max }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0
  return (
    <div className="db-progress">
      <div className="db-progress-track"><div className="db-progress-fill" style={{ width: `${pct}%` }} /></div>
      <span className="db-progress-label">{value} / {max} completed · {pct}%</span>
    </div>
  )
}

function ScoreRow({ label, max, value }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0
  return (
    <div className="db-score-row">
      <span className="db-score-label">{label}</span>
      <div className="db-score-track"><div className="db-score-fill" style={{ width: `${pct}%` }} /></div>
      <span className="db-score-value">{value} / {max}</span>
    </div>
  )
}

function LeaderboardPanel({ leaders, myRow, leaderboardError, username }) {
  const top = leaders.slice(0, 5)
  return (
    <Panel title="Leaderboard" kicker="Workspace rankings"
      actions={<a className="db-link" href="/leaderboard">View full leaderboard <span aria-hidden="true">-&gt;</span></a>}>
      {leaderboardError ? (
        <div className="db-sub-empty">Unable to load leaderboard.</div>
      ) : !top.length ? (
        <div className="db-sub-empty">Leaderboard data isn&rsquo;t available yet.</div>
      ) : (
        <ol className="db-leader-list">
          {top.map((row) => {
            const isMe = row.username === username
            return (
              <li key={row.username} className={isMe ? 'db-leader-row is-you' : 'db-leader-row'}>
                <span className="db-leader-rank">#{row.rank}</span>
                <span className="db-leader-name">{isMe ? 'You' : row.username}</span>
                <span className="db-leader-total">{row.total_points ?? 0}</span>
              </li>
            )
          })}
        </ol>
      )}
      {myRow && myRow.rank > 5 && (
        <div className="db-leader-your-rank">Your rank: <strong>#{myRow.rank}</strong> · {myRow.total_points ?? 0} points</div>
      )}
    </Panel>
  )
}

function PointsPanel({ myRow }) {
  const coding = leaderboardValue(myRow, 'coding_points')
  const tasks = leaderboardValue(myRow, 'normal_task_points')
  const total = leaderboardValue(myRow, 'total_points')
  return (
    <Panel title="Total Points" kicker="How points add up">
      <div className="db-points">
        <div className="db-points-row"><span>Task Points</span><strong>{tasks}</strong></div>
        <div className="db-points-row"><span>Coding Points</span><strong>{coding}</strong></div>
        <div className="db-points-total"><span>Total</span><strong>{total}</strong></div>
      </div>
      <p className="db-points-note">Task points come from your best AI evaluation per task; coding points from accepted coding submissions.</p>
    </Panel>
  )
}
function MyProgressPanel({ summary, taskCount, myRow }) {
  const taskPoints = leaderboardValue(myRow, 'normal_task_points')
  const codingPoints = leaderboardValue(myRow, 'coding_points')
  const totalPoints = leaderboardValue(myRow, 'total_points')
  const rank = myRow?.rank
  return (
    <Panel title="My Progress" kicker="Your performance">
      <ProgressBar value={summary.completed} max={Math.max(taskCount, summary.completed, summary.inProgress + summary.completed)} />
      <div className="db-progress-grid">
        <div><span className="db-metric">Task Points</span><strong>{taskPoints}</strong></div>
        <div><span className="db-metric">Coding Points</span><strong>{codingPoints}</strong></div>
        <div><span className="db-metric">Total Points</span><strong>{totalPoints}</strong></div>
        <div><span className="db-metric">Leaderboard Rank</span><strong>{rank ? `#${rank}` : '—'}</strong></div>
      </div>
    </Panel>
  )
}

function AiPanel({ evaluation, evaluationState, latestApproved }) {
  const scores = evaluation?.scores || {}
  const total = typeof evaluation?.total_score === 'number' ? evaluation.total_score : 0
  const best = typeof evaluation?.best_score === 'number' ? evaluation.best_score : null
  return (
    <Panel title="AI Task Analyzer" kicker="Latest evaluation"
      actions={evaluationState === 'ready' && evaluation?.id
        ? <a className="db-link" href="/my-tasks">View analysis <span aria-hidden="true">-&gt;</span></a>
        : undefined}>
      {evaluationState === 'loading' && <div className="db-sub-muted">Loading evaluation&hellip;</div>}
      {evaluationState === 'missing' && (
        <div className="db-sub-empty">Complete an accepted task to receive your AI evaluation.</div>
      )}
      {evaluationState === 'failed' && (
        <div className="db-sub-empty">Evaluation failed — retry available on the task page.</div>
      )}
      {evaluationState === 'ready' && evaluation && (
        <div className="db-ai">
          <div className="db-ai-head">
            <span className="db-ai-score"><strong>{total}</strong> / 10</span>
            <span className="db-ai-task">{latestApproved?.title}</span>
          </div>
          {best !== null && <p className="db-ai-best">Best score: {best} / 10</p>}
          <div className="db-ai-rows">
            {Object.entries(RUBRIC_LABELS).map(([key, [label, max]]) => (
              <ScoreRow key={key} label={label} max={max} value={num(scores[key])} />
            ))}
          </div>
          {evaluation?.summary && <p className="db-ai-summary">{evaluation.summary}</p>}
        </div>
      )}
    </Panel>
  )
}

function RecentTasksPanel({ rows }) {
  const visible = rows.slice(0, 6)
  return (
    <Panel title="Recent Tasks" kicker="Your assignments">
      {!visible.length ? (
        <div className="db-sub-empty">No tasks assigned yet.</div>
      ) : (
        <ul className="db-task-list">
          {visible.map((row) => (
            <li key={row.assignmentId ?? row.taskId} className="db-task-row">
              <div className="db-task-title">
                <span className="db-task-status-dot" data-status={row.submission?.status || 'NONE'} />
                <span>{row.title}</span>
              </div>
              <div className="db-task-meta">
                {row.difficulty && <span className="db-chip">{row.difficulty}</span>}
                <span className={row.submission ? 'db-status-text' : 'db-status-text is-muted'}>
                  {row.submission ? STATUS_LABELS[row.submission.status] || row.submission.status : 'Not submitted'}
                </span>
                {row.submission?.status === 'APPROVED' && row.earnedPoints > 0 && (
                  <span className="db-chip is-accent">{row.earnedPoints} pts</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function AttentionPanel({ summary, rows }) {
  const items = []
  if (summary.pendingReview > 0) items.push(`${summary.pendingReview} task(s) awaiting review`)
  const rejected = rows.filter((row) => row.submission?.status === 'REJECTED')
  if (rejected.length) items.push(`${rejected.length} task(s) need resubmission`)
  const noSubmission = rows.filter((row) => !row.submission).length
  if (noSubmission > 0) items.push(`${noSubmission} task(s) not started`)
  return (
    <Panel title="Needs Attention" kicker="Action items">
      {!items.length ? (
        <div className="db-sub-empty">You&rsquo;re all caught up.</div>
      ) : (
        <ul className="db-attention-list">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </Panel>
  )
}

function UserSections({ rows, summary, evaluation, evaluationState, latestApproved, leaders, myRow, leaderboardError, username }) {
  return (
    <div className="db-grid">
      <div className="db-col db-col-main">
        <MyProgressPanel summary={summary} taskCount={rows.length} myRow={myRow} />
        <RecentTasksPanel rows={rows} />
      </div>
      <div className="db-col db-col-side">
        <AiPanel evaluation={evaluation} evaluationState={evaluationState} latestApproved={latestApproved} />
        <LeaderboardPanel leaders={leaders} myRow={myRow} leaderboardError={leaderboardError} username={username} />
        <AttentionPanel summary={summary} rows={rows} />
      </div>
    </div>
  )
}

function AdminSections({ metrics, leaders, leaderboardError }) {
  const totals = metrics?.totals || {}
  const statusDist = Array.isArray(metrics?.status_distribution) ? metrics.status_distribution : []
  return (
    <div className="db-grid">
      <div className="db-col db-col-main">
        <Panel title="Task Status" kicker="Live distribution">
          {!statusDist.length ? (
            <div className="db-sub-empty">No task activity yet.</div>
          ) : (
            <ul className="db-status-list">
              {statusDist.map((s) => (
                <li key={s.key} className="db-status-row">
                  <span>{s.label}</span>
                  <strong>{s.count}</strong>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Overdue Tasks" kicker="Requiring attention">
          {!num(totals.overdue) ? (
            <div className="db-sub-empty">No overdue tasks.</div>
          ) : (
            <div className="db-sub-muted">{num(totals.overdue)} task(s) are past their due date.</div>
          )}
        </Panel>
      </div>
      <div className="db-col db-col-side">
        <LeaderboardPanel leaders={leaders} myRow={null} leaderboardError={leaderboardError} username={null} />
        <Panel title="Platform Overview" kicker="At a glance">
          <div className="db-total-tasks">
            <span>{num(totals.completed)}</span> completed / {num(totals.total_tasks)} total tasks
          </div>
        </Panel>
      </div>
    </div>
  )
}

function QuickActions({ isAdmin }) {
  const actions = isAdmin
    ? [
      { href: '/tasks', label: 'Create task' },
      { href: '/admin/users', label: 'Manage users' },
      { href: '/admin/monitoring', label: 'Monitoring' },
      { href: '/leaderboard', label: 'Leaderboard' },
    ]
    : [
      { href: '/my-tasks', label: 'Solve a task' },
      { href: '/tasks', label: 'View tasks' },
      { href: '/leaderboard', label: 'Leaderboard' },
      { href: '/notifications', label: 'Notifications' },
    ]
  return (
    <section className="db-quick" aria-label="Quick actions">
      {actions.map((action) => <a className="db-quick-link" key={action.label} href={action.href}>{action.label}</a>)}
    </section>
  )
}

function DashboardSkeleton() {
  return (
    <div className="db-skeleton" aria-hidden="true">
      <div className="db-kpi-strip">
        {[0, 1, 2, 3, 4, 5].map((i) => <div className="db-skel db-skel-kpi" key={i} />)}
      </div>
      <div className="db-grid">
        <div className="db-col db-col-main">
          <div className="db-skel db-skel-panel" />
          <div className="db-skel db-skel-panel" />
        </div>
        <div className="db-col db-col-side">
          <div className="db-skel db-skel-panel" />
          <div className="db-skel db-skel-panel" />
        </div>
      </div>
    </div>
  )
}