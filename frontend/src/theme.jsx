import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const THEME_KEY = 'taskflow_theme'

const ThemeContext = createContext(null)

function currentTheme() {
  return typeof document !== 'undefined'
    ? document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
    : 'light'
}

/**
 * Light/Dark theme provider. Applies the selection to <html data-theme="…">
 * so the entire app (including lazy-loaded pages) inherits it, and persists
 * the choice to localStorage. Defaults to the OS preference.
 */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(currentTheme)

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      document.documentElement.dataset.theme = next
      try {
        localStorage.setItem(THEME_KEY, next)
      } catch (_) { /* storage unavailable — still valid for this session */ }
      return next
    })
  }, [])

  const value = useMemo(() => ({ theme, toggle }), [theme, toggle])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}

const IconSun = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></svg>
)
const IconMoon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
)

/** Accessible Light/Dark icon toggle matching the header icon control system. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={isDark}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <span className="theme-toggle-icon" aria-hidden="true">{isDark ? <IconSun /> : <IconMoon />}</span>
    </button>
  )
}
