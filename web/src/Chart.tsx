// A year of closing prices as a simple line chart, drawn by hand (no chart library).
import { useState } from 'react'
import type { Instrument, Series } from './data'
import { pct, price } from './format'

const W = 720
const H = 260
const PAD = { top: 16, right: 86, bottom: 30, left: 8 }

function shortDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
}

export default function Chart({ stock, series }: { stock: Instrument; series: Series }) {
  const [hover, setHover] = useState<number | null>(null)
  const { dates, closes } = series
  const low = Math.min(...closes)
  const high = Math.max(...closes)
  const span = high - low || 1
  const x = (i: number) => PAD.left + (i / (closes.length - 1)) * (W - PAD.left - PAD.right)
  const y = (v: number) => PAD.top + (1 - (v - low) / span) * (H - PAD.top - PAD.bottom)
  const line = closes.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${x(closes.length - 1).toFixed(1)},${H - PAD.bottom} L${x(0).toFixed(1)},${H - PAD.bottom} Z`
  const last = closes.length - 1
  const shown = hover ?? last
  const change = (closes[last] / closes[0] - 1) * 100

  function move(event: React.PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect()
    const at = ((event.clientX - box.left) / box.width) * W
    const i = Math.round(((at - PAD.left) / (W - PAD.left - PAD.right)) * last)
    setHover(Math.max(0, Math.min(last, i)))
  }

  return (
    <figure className="chart">
      <figcaption>
        <b>{price(stock, closes[shown])}</b> <span className="muted">close on {shortDate(dates[shown])}</span>
        <span className="chart-change muted">
          {dates.length} trading days: <span className={change < 0 ? 'down' : 'up'}>{pct(change)}</span>
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`} role="img" onPointerMove={move} onPointerLeave={() => setHover(null)}
        aria-label={`Closing price of ${stock.symbol} from ${shortDate(dates[0])} to ${shortDate(dates[last])}: low ${price(stock, low)}, high ${price(stock, high)}.`}
      >
        {[high, (high + low) / 2, low].map((v) => (
          <g key={v}>
            <line className="chart-grid" x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} />
            <text className="chart-label" x={W - PAD.right + 8} y={y(v) + 4}>{price(stock, v)}</text>
          </g>
        ))}
        <path className="chart-area" d={area} />
        <path className="chart-line" d={line} />
        <line className="chart-cursor" x1={x(shown)} x2={x(shown)} y1={PAD.top} y2={H - PAD.bottom} />
        <circle className="chart-dot" cx={x(shown)} cy={y(closes[shown])} r="4" />
        <text className="chart-label" x={PAD.left} y={H - 6}>{shortDate(dates[0])}</text>
        <text className="chart-label" x={W - PAD.right} y={H - 6} textAnchor="end">{shortDate(dates[last])}</text>
      </svg>
    </figure>
  )
}
