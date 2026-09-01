import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../services/api'

/**
 * Lightweight global workspace search.
 * - Coding problems: server-side search via /coding/problems/?search=
 * - Tasks: client-side filter over a single /my/tasks/ fetch (debounced)
 * Escape closes, backdrop closes, empty query never hits the API.
 */
export default function GlobalSearch() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [problems, setProblems] = useState([])
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef(null)
  const debounceRef = useRef(null)
  const close = () => { setOpen(false); setQuery(''); setProblems([]); setTasks([]) }

  useEffect(() => {
    if (!open) return undefined
    inputRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') close() }
    document.addEventListener('keydown', onKey)
    document.body.classList.add('nav-drawer-open')
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.classList.remove('nav-drawer-open')
    }
  }, [open])

  useEffect(() => {
    const q = query.trim()
    if (!q) { setProblems([]); setTasks([]); setLoading(false); return undefined }
    setLoading(true)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      const [problemsRes, tasksRes] = await Promise.allSettled([
        api.get('/coding/problems/', { params: { search: q, page_size: 5 } }),
        api.get('/my/tasks/', { params: { page_size: 100 } }),
      ])
      if (problemsRes.status === 'fulfilled') {
        setProblems((problemsRes.value?.data?.results || []).slice(0, 5))
      } else setProblems([])
      if (tasksRes.status === 'fulfilled') {
        const needle = q.toLowerCase()
        setTasks((tasksRes.value?.data?.results || [])
          .filter((t) => (t.task?.title || '').toLowerCase().includes(needle))
          .slice(0, 5))
      } else setTasks([])
      setLoading(false)
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [query])

  const results = useMemo(() => {
    const groups = []
    const probs = problems.slice(0, 5).map((p) => ({
      key: `prob${p.id}`,
      href: `/coding/problems/${p.id}/solve`,
      title: p.title || 'Untitled problem',
      meta: p.difficulty ? `Coding Problem · ${p.difficulty}` : 'Coding Problem',
    }))
    const tsk = tasks.slice(0, 5).map((t) => ({
      key: `task${t.id}`,
      href: '/my-tasks',
      title: t.task?.title || t.task?.name || 'Untitled task',
      meta: 'My Task',
    }))
    if (probs.length) groups.push({ label: 'Coding Problems', items: probs })
    if (tsk.length) groups.push({ label: 'My Tasks', items: tsk })
    return groups
  }, [problems, tasks])

  const go = (href) => { close(); window.location.href = href }

  return (
    <>
      <button
        type="button"
        className="header-icon-btn"
        aria-label="Search"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="15.657" y2="15.657" /></svg>
      </button>
      {open && (
        <div className="search-overlay" role="dialog" aria-modal="true" aria-label="Search workspace">
          <div className="search-overlay-backdrop" onClick={close} />
          <div className="search-palette">
            <div className="search-palette-input-row">
              <span className="search-palette-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="15.657" y2="15.657" /></svg>
              </span>
              <input
                ref={inputRef}
                className="search-palette-input"
                type="text"
                placeholder="Search tasks and coding problems…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search tasks and coding problems"
              />
              <kbd className="search-palette-kbd">Esc</kbd>
            </div>

            <div className="search-palette-body">
              {!query.trim() && (
                <div className="search-palette-state">
                  <span className="search-palette-state-icon" aria-hidden="true">⌕</span>
                  <div className="search-palette-state-title">Search your workspace</div>
                  <div className="search-palette-state-sub">Find tasks and coding problems quickly.</div>
                </div>
              )}
              {query.trim() && loading && (
                <div className="search-palette-state">
                  <div className="search-palette-state-title">Searching…</div>
                </div>
              )}
              {query.trim() && !loading && !results.length && (
                <div className="search-palette-state">
                  <div className="search-palette-state-title">No matches</div>
                  <div className="search-palette-state-sub">Nothing found for “{query.trim()}”.</div>
                </div>
              )}
              {results.map((group) => (
                <div className="search-palette-group" key={group.label}>
                  <div className="search-palette-group-title">{group.label}</div>
                  {group.items.map((item) => (
                    <button type="button" key={item.key} className="search-palette-result" onClick={() => go(item.href)}>
                      <span className="search-palette-result-left">
                        <span className="search-palette-result-title">{item.title}</span>
                        <span className="search-palette-result-meta">{item.meta}</span>
                      </span>
                      <span className="search-palette-result-go" aria-hidden="true">↵</span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
