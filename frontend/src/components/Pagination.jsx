/**
 * Minimal pagination controls for DRF paginated list responses.
 *
 * Props:
 *   currentPage  1-based page number currently displayed
 *   hasNext      whether a next page exists (backend `next` !== null)
 *   hasPrevious  whether a previous page exists (backend `previous` !== null)
 *   onNext       callback to advance one page
 *   onPrevious   callback to go back one page
 *   disabled     true while the list is loading (buttons disabled)
 */
export default function Pagination({ currentPage, hasNext, hasPrevious, onNext, onPrevious, disabled = false }) {
  return (
    <nav className="pagination-controls" aria-label="List pages">
      <button
        type="button"
        className="button-muted"
        onClick={onPrevious}
        disabled={disabled || !hasPrevious}
        aria-label="Go to previous page"
      >
        &larr; Previous
      </button>
      <span className="pagination-indicator" aria-current="page">
        Page {currentPage}
      </span>
      <button
        type="button"
        className="button-muted"
        onClick={onNext}
        disabled={disabled || !hasNext}
        aria-label="Go to next page"
      >
        Next &rarr;
      </button>
    </nav>
  )
}
