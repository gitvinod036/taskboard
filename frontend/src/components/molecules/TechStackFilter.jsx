import { useEffect, useRef, useState } from 'react'

function technologyMark(name) {
  if (!name || typeof name !== 'string') return 'TS'
  const alphanumeric = name.replace(/[^a-zA-Z0-9]/g, '')
  if (alphanumeric.length >= 2) return alphanumeric.slice(0, 2).toUpperCase()
  if (alphanumeric.length === 1) return alphanumeric.toUpperCase()
  return name.slice(0, 2).toUpperCase() || 'TS'
}

export default function TechStackFilter({ options = [], selected = [], onChange, loading = false, label = 'Technologies', supportingText = 'Filter users by their tech stack' }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const containerRef = useRef(null)
  const searchRef = useRef(null)

  const safeOptions = Array.isArray(options) ? options : []
  const safeSelected = Array.isArray(selected) ? selected : []

  useEffect(() => {
    function close(event) {
      if (!containerRef.current?.contains(event.target)) setOpen(false)
    }
    function escape(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [])

  useEffect(() => {
    if (open) searchRef.current?.focus()
  }, [open])

  function toggle(name) {
    if (!onChange) return
    const next = safeSelected.includes(name)
      ? safeSelected.filter((item) => item !== name)
      : [...safeSelected, name]
    onChange(next)
  }

  function clearAll(event) {
    event?.stopPropagation()
    if (onChange) onChange([])
    setQuery('')
  }

  const visibleOptions = safeOptions.filter((option) =>
    (option?.name || '').toLowerCase().includes(query.toLowerCase())
  )
  const selectedOptions = safeOptions.filter((option) =>
    safeSelected.includes(option?.name)
  )

  return (
    <div className="tech-stack-filter" ref={containerRef}>
      <span className="filter-label">{label}</span>
      <span className="filter-supporting-text">{supportingText}</span>

      <div
        className={`filter-control ${open ? 'filter-control-open' : ''}`}
        onClick={() => { if (!loading) setOpen(true) }}
      >
        <div className="filter-selected" aria-label="Selected technologies">
          {safeSelected.length === 0 && (
            <button
              type="button"
              className="filter-placeholder"
              onClick={(e) => { e.stopPropagation(); setOpen(true) }}
              disabled={loading}
            >
              {loading ? 'Loading technologies...' : 'Select technologies...'}
            </button>
          )}
          {safeSelected.map((name) => (
            <span className="filter-value-chip" key={name}>
              <span className="tech-stack-icon" aria-hidden="true">
                {technologyMark(name)}
              </span>
              {name}
              <button
                type="button"
                className="chip-remove"
                aria-label={`Remove ${name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  toggle(name)
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <button
          type="button"
          className="filter-chevron"
          aria-label={open ? 'Close technology filter' : 'Open technology filter'}
          aria-expanded={open}
          onClick={(e) => {
            e.stopPropagation()
            setOpen(!open)
          }}
          disabled={loading}
        >
          ⌄
        </button>
      </div>

      {open && (
        <div
          className="filter-menu"
          role="listbox"
          aria-label="Technology options"
          aria-multiselectable="true"
        >
          <div className="filter-search-wrap">
            <span aria-hidden="true">⌕</span>
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search technologies..."
              aria-label="Search technologies"
            />
          </div>

          <div className="filter-section-heading">SELECTED ({safeSelected.length})</div>
          {selectedOptions.length > 0 ? (
            <div className="filter-option-grid filter-selected-grid">
              {selectedOptions.map((option) => (
                <TechnologyOption
                  key={`selected-${option.name}`}
                  option={option}
                  selected={true}
                  onToggle={toggle}
                />
              ))}
            </div>
          ) : (
            <p className="filter-no-results" style={{ padding: '4px 8px', margin: 0, fontSize: '0.78rem' }}>
              No technologies currently selected.
            </p>
          )}

          <div className="filter-section-heading">ALL TECHNOLOGIES</div>
          {visibleOptions.length > 0 ? (
            <div className="filter-option-grid">
              {visibleOptions.map((option) => (
                <TechnologyOption
                  key={`all-${option.name}`}
                  option={option}
                  selected={safeSelected.includes(option.name)}
                  onToggle={toggle}
                />
              ))}
            </div>
          ) : (
            <p className="filter-no-results">No technologies match your search.</p>
          )}

          <div className="filter-menu-footer">
            <span>{safeSelected.length ? `${safeSelected.length} selected` : 'No filters applied'}</span>
            <button type="button" onClick={clearAll} disabled={safeSelected.length === 0}>
              Clear all
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function TechnologyOption({ option, selected, onToggle }) {
  return (
    <label
      className={`filter-option ${selected ? 'filter-option-selected' : ''}`}
      role="option"
      aria-selected={selected}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(option.name)}
      />
      <span className="tech-stack-icon" aria-hidden="true">
        {technologyMark(option.name)}
      </span>
      <span>{option.name}</span>
      {selected && <span className="filter-check" aria-hidden="true">✓</span>}
    </label>
  )
}
