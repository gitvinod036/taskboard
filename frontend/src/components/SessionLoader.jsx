/**
 * SessionLoader
 * Shown while AuthContext resolves the initial session check.
 * Uses a three-dot sequential bounce — CSS-only, no animation packages.
 */
export default function SessionLoader() {
  return (
    <div className="session-loader-shell" role="status" aria-label="Preparing your workspace">
      <div className="session-loader-card">
        {/* Brand mark */}
        <div className="session-loader-brand">
          <span className="brand-mark" aria-hidden="true">T</span>
          <span className="session-loader-brand-name">TaskBoard</span>
        </div>

        {/* Label */}
        <p className="session-loader-label">Preparing your workspace</p>

        {/* Three-dot bounce */}
        <div className="session-loader-dots" aria-hidden="true">
          <span className="session-loader-dot" style={{ animationDelay: '0ms' }} />
          <span className="session-loader-dot" style={{ animationDelay: '160ms' }} />
          <span className="session-loader-dot" style={{ animationDelay: '320ms' }} />
        </div>
      </div>
    </div>
  )
}
