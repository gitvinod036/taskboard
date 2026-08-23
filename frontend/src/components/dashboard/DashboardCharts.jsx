/**
 * Dependency-free SVG/CSS chart primitives used by admin analytics pages.
 * The project intentionally avoids extra runtime packages, so these are
 * hand-rolled and defensively coded: empty data renders an explicit empty
 * state instead of NaN coordinates or broken shapes.
 */

function safeCount(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

export function DonutChart({ segments = [], size = 168, thickness = 26, ariaLabel = 'Donut chart' }) {
  const total = segments.reduce((sum, segment) => sum + safeCount(segment.count), 0)
  const radius = Math.max((size - thickness) / 2, 1)
  const circumference = 2 * Math.PI * radius

  let consumed = 0
  const arcs = total > 0 ? segments.map((segment) => {
    const count = safeCount(segment.count)
    const fraction = count / total
    const arc = {
      ...segment,
      dash: fraction * circumference,
      offset: -consumed,
    }
    consumed += fraction * circumference
    return arc
  }).filter((arc) => arc.dash > 0) : []

  return (
    <svg className="donut-chart" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={ariaLabel}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e2e8f0" strokeWidth={thickness} />
      {arcs.map((arc) => (
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={arc.color}
          strokeWidth={thickness}
          strokeLinecap="butt"
          strokeDasharray={`${Math.max(arc.dash - 2, 0)} ${circumference - Math.max(arc.dash - 2, 0)}`}
          strokeDashoffset={arc.offset + circumference / 4}
          key={arc.key || arc.label}
        >
          <title>{`${arc.label}: ${safeCount(arc.count)}`}</title>
        </circle>
      ))}
      <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" className="donut-center-value">{total}</text>
      <text x="50%" y="60%" textAnchor="middle" dominantBaseline="middle" className="donut-center-label">total</text>
    </svg>
  )
}

export function TrendChart({ points = [], height = 210, ariaLabel = 'Weekly activity trend line chart' }) {
  const values = points.map((point) => safeCount(point.completions))
  const width = 560
  const padLeft = 36
  const padRight = 14
  const padTop = 16
  const padBottom = 34

  if (points.length < 2) {
    return (
      <div className="chart-empty" role="status">
        <strong>No trend data yet</strong>
        <span>Activity will appear here week by week.</span>
      </div>
    )
  }

  const maxValue = Math.max(...values, 1)
  const stepX = (width - padLeft - padRight) / (points.length - 1)
  const plotHeight = height - padTop - padBottom
  const coords = values.map((value, index) => ({
    x: padLeft + index * stepX,
    y: padTop + plotHeight - (value / maxValue) * plotHeight,
  }))
  const linePath = coords.map((coord, index) => `${index === 0 ? 'M' : 'L'}${coord.x.toFixed(2)},${coord.y.toFixed(2)}`).join(' ')
  const areaPath = `${linePath} L${coords[coords.length - 1].x.toFixed(2)},${padTop + plotHeight} L${padLeft},${padTop + plotHeight} Z`
  const firstLabel = new Date(points[0].week_start)
  const lastLabel = new Date(points[points.length - 1].week_start)

  return (
    <svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel}>
      {[0, 0.5, 1].map((fraction) => {
        const y = padTop + plotHeight * fraction
        return (
          <g key={fraction}>
            <line x1={padLeft} x2={width - padRight} y1={y} y2={y} stroke="#e2e8f0" strokeWidth="1" />
            <text x={padLeft - 8} y={y} textAnchor="end" dominantBaseline="middle" className="trend-axis-label">
              {Math.round(maxValue * (1 - fraction))}
            </text>
          </g>
        )
      })}
      <path d={areaPath} fill="rgba(29, 78, 216, 0.12)" stroke="none" />
      <path d={linePath} fill="none" stroke="#1d4ed8" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {coords.map((coord, index) => (
        <circle cx={coord.x} cy={coord.y} r="4" fill="#fff" stroke="#1d4ed8" strokeWidth="2" key={`${points[index].week_start}-${index}`}>
          <title>{`Week of ${points[index].week_start}: ${values[index]}`}</title>
        </circle>
      ))}
      {values.map((value, index) => (value > 0 ? (
        <text
          x={coords[index].x}
          y={Math.max(coords[index].y - 10, padTop + 4)}
          textAnchor="middle"
          className="trend-point-label"
          key={`label-${points[index].week_start}-${index}`}
        >
          {value}
        </text>
      ) : null))}
      {!Number.isNaN(firstLabel.getTime()) && (
        <text x={padLeft} y={height - 10} textAnchor="start" className="trend-axis-label">{firstLabel.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</text>
      )}
      {!Number.isNaN(lastLabel.getTime()) && (
        <text x={width - padRight} y={height - 10} textAnchor="end" className="trend-axis-label">{lastLabel.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</text>
      )}
    </svg>
  )
}

export function HorizontalBars({ items = [], color = '#1d4ed8' }) {
  if (!items.length) {
    return (
      <p className="empty-state">
        <strong>No data yet</strong>
        <span>Values will appear here as soon as they exist.</span>
      </p>
    )
  }

  const maxValue = Math.max(...items.map((item) => safeCount(item.value)), 1)
  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li className="bar-row" key={item.label}>
          <span className="bar-name">{item.label}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${Math.max((safeCount(item.value) / maxValue) * 100, 2)}%`, background: color }} /></span>
          <span className="bar-value">{safeCount(item.value)}</span>
        </li>
      ))}
    </ul>
  )
}
