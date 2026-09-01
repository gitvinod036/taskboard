import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import WorkspaceNav from '../components/WorkspaceNav'

/**
 * Leaderboard — first-class product feature for BOTH roles.
 *
 * Data source: GET /api/coding/leaderboard/ (backend-authoritative, combined
 * Coding + Normal Task points). No values are computed or faked here beyond
 * read-only derivations of the returned rows (e.g. gap to the rank above).
 */
export default function Leaderboard() {
  const { user } = useAuth()
  const [entries, setEntries] = useState([])
  const [state, setState] = useState('loading') // loading | ready | error

  async function load() {
    setState('loading')
    try {
      const { data } = await api.get('/coding/leaderboard/')
      setEntries(Array.isArray(data) ? data : [])
      setState('ready')
    } catch (_) {
      setState('error')
    }
  }

  useEffect(() => { load() }, [])

  // Current user's row: matched on username (stable) with user_id fallback.
  const me = entries.find((e) =>
    (user?.username && e.username === user.username) ||
    (user?.id != null && e.user_id === user.id))

  const podium = entries.slice(0, 3)
  const gap = me && me.rank > 1 ? entries[me.rank - 2].total_points - me.total_points : null

  return (
    <div className="workspace-shell">
      <WorkspaceNav active="leaderboard" />

      <div className="page-intro">
        <div>
          <p className="eyebrow">Leaderboard</p>
          <h1>Developer Leaderboard</h1>
          <p>Track your progress, compare performance, and see who&rsquo;s leading the workspace.</p>
        </div>
        <div className="page-summary" aria-label="Workspace rankings">
          <strong>{entries.length}</strong>
          <span>Workspace Rankings</span>
        </div>
      </div>

      {state === 'loading' && <LeaderboardSkeleton />}

      {state === 'error' && (
        <div className="lb-panel lb-error" role="alert">
          <strong>Unable to load leaderboard</strong>
          <p>We couldn&rsquo;t retrieve the current rankings.</p>
          <button type="button" className="button-primary" onClick={load}>Retry</button>
        </div>
      )}

      {state === 'ready' && entries.length === 0 && (
        <div className="lb-panel lb-empty">
          <strong>Leaderboard is empty</strong>
          <p>Complete tasks or coding problems to start building your ranking.</p>
        </div>
      )}

      {state === 'ready' && entries.length > 0 && (
        <>
          {me && (
            <section className="lb-hero" aria-label="Your position">
              <div className="lb-hero-rank">
                <span className="lb-rank-big">#{String(me.rank).padStart(2, '0')}</span>
                <span className="lb-hero-label">Current Rank</span>
              </div>
              <div className="lb-hero-total">
                <span className="lb-points-big">{me.total_points}</span>
                <span className="lb-hero-label">Total Points</span>
              </div>
              <dl className="lb-hero-breakdown">
                <div><dt>Coding</dt><dd>{me.coding_points}</dd></div>
                <div><dt>Tasks</dt><dd>{me.normal_task_points}</dd></div>
              </dl>
              {gap != null && gap > 0 && (
                <p className="lb-hero-gap">
                  {gap} point{gap === 1 ? '' : 's'} away from rank #{me.rank - 1}
                </p>
              )}
            </section>
          )}

          {podium.length > 0 && (
            <section className="lb-podium" aria-label="Top three">
              {podium.map((e, i) => (
                <article key={e.user_id} className={`lb-podium-card lb-podium-${i + 1}`}>
                  <span className="lb-podium-rank">#{e.rank}</span>
                  <span className="lb-podium-name" title={e.username}>{e.name}</span>
                  <span className="lb-podium-points">{e.total_points} pts</span>
                </article>
              ))}
            </section>
          )}

          <section className="lb-panel" aria-label="Full rankings">
            <table className="lb-table">
              <thead>
                <tr><th scope="col">Rank</th><th scope="col">User</th><th scope="col" className="lb-num">Coding</th><th scope="col" className="lb-num">Tasks</th><th scope="col" className="lb-num">Total</th></tr>
              </thead>
              <tbody>
                {entries.map((e) => {
                  const isMe = me && e.user_id === me.user_id
                  return (
                    <tr key={e.user_id} className={isMe ? 'lb-row-me' : undefined} aria-current={isMe ? 'true' : undefined}>
                      <td data-label="Rank" className="lb-rank-cell">#{String(e.rank).padStart(2, '0')}</td>
                      <td data-label="User" className="lb-user-cell">{e.name}{isMe && <span className="lb-you">You</span>}</td>
                      <td data-label="Coding" className="lb-num">{e.coding_points}</td>
                      <td data-label="Tasks" className="lb-num">{e.normal_task_points}</td>
                      <td data-label="Total" className="lb-num lb-total">{e.total_points}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="lb-how" aria-label="How points work">
            <h2>How points work</h2>
            <ul>
              <li><strong>Coding</strong> — points from accepted coding submissions, judged by the execution engine (Easy 10 / Medium 20 / Hard 30, first accepted submission per problem).</li>
              <li><strong>Tasks</strong> — points from approved normal-task submissions, awarded once server-side based on task difficulty (Easy 10 / Medium 20 / Hard 30).</li>
              <li><strong>Total</strong> — Coding + Task points, ranked by the backend.</li>
            </ul>
          </section>
        </>
      )}
    </div>
  )
}

function LeaderboardSkeleton() {
  return (
    <div className="lb-panel lb-skeleton" aria-hidden="true">
      <div className="lb-skel-row lb-skel-hero" />
      {[...Array(6)].map((_, i) => <div key={i} className="lb-skel-row" />)}
    </div>
  )
}
