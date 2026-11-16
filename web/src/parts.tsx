// The pieces every page shares: top strip, masthead, navigation, tags, footer.
import { useEffect, useRef, useState } from 'react'
import type { Alert, Edition, Indicator, Instrument } from './data'
import { searchStocks } from './data'
import { ago, direction, longDate, marketCap, pct, price, times } from './format'

export const DISCLAIMER =
  'Information only. Not investment advice or a personal recommendation. StocksWatch is not ' +
  'authorised or regulated by the Financial Conduct Authority. Prices may be delayed or wrong. ' +
  'The value of investments can fall as well as rise and you may get back less than you invest.'

export type Page = 'front' | 'watchlist' | 'us' | 'uk' | 'sectors' | 'digest' | 'settings'
export type Route = { page: Page } | { page: 'stock'; id: number }

export function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const stock = hash.match(/^stock\/(\d+)$/)
  if (stock) return { page: 'stock', id: Number(stock[1]) }
  if (hash === 'account') return { page: 'settings' }
  if (['watchlist', 'us', 'uk', 'sectors', 'digest', 'settings'].includes(hash)) return { page: hash as Page }
  return { page: 'front' }
}

export function stockLink(stock: Pick<Instrument, 'id'>): string {
  return `#/stock/${stock.id}`
}

// --- Top strip ----------------------------------------------------------------

export function TickerStrip({ indicators }: { indicators: Indicator[] }) {
  return (
    <div className="strip">
      <div className="wrap strip-row">
        {indicators.map((item) => (
          <span className="strip-item" key={item.key}>
            <span className="strip-name">{item.label}</span>
            <span className={`strip-box ${direction(item.pct_change)}`}>{pct(item.pct_change, 2)}</span>
          </span>
        ))}
        {indicators.length === 0 && <span className="strip-name">Market figures appear after the first scan</span>}
      </div>
    </div>
  )
}

// --- Masthead -----------------------------------------------------------------

function Search() {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [found, setFound] = useState<Instrument[]>([])
  const box = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) box.current?.focus()
  }, [open])

  useEffect(() => {
    if (!text.trim()) return setFound([])
    let current = true
    const timer = setTimeout(() => {
      searchStocks(text).then((list) => current && setFound(list)).catch(() => current && setFound([]))
    }, 200)
    return () => {
      current = false
      clearTimeout(timer)
    }
  }, [text])

  const close = () => {
    setOpen(false)
    setText('')
  }

  return (
    <div className="search">
      <button className="icon-button" aria-label="Search stocks" aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M15.5 15.5 21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="search-panel">
          <input
            ref={box}
            value={text}
            placeholder="Company or ticker"
            aria-label="Company or ticker"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && close()}
          />
          {found.map((stock) => (
            <a className="search-hit" href={stockLink(stock)} key={stock.id} onClick={close}>
              <span>
                <b>{stock.symbol}</b> {stock.name}
              </span>
              <span className={direction(stock.quotes?.pct_change)}>{pct(stock.quotes?.pct_change)}</span>
            </a>
          ))}
          {text.trim() && found.length === 0 && <div className="search-none">No match</div>}
        </div>
      )}
    </div>
  )
}

export function Masthead({ account, onSignOut, onMenu }: {
  account: string
  onSignOut: (() => void) | null
  onMenu: () => void
}) {
  return (
    <header className="wrap masthead">
      <div className="masthead-side">
        <button className="icon-button menu-button" aria-label="Sections" onClick={onMenu}>
          <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
            <path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
        <Search />
      </div>
      <a className="masthead-title" href="#/">StocksWatch</a>
      <div className="masthead-side right">
        <span className="account" title={account}>
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
          </svg>
          {onSignOut ? (
            <button className="link-button" onClick={onSignOut}>Sign out</button>
          ) : (
            <span>{account}</span>
          )}
        </span>
      </div>
    </header>
  )
}

const TABS: { page: Page; label: string; href: string }[] = [
  { page: 'front', label: 'Front Page', href: '#/' },
  { page: 'watchlist', label: 'Watchlist', href: '#/watchlist' },
  { page: 'us', label: 'US', href: '#/us' },
  { page: 'uk', label: 'UK', href: '#/uk' },
  { page: 'sectors', label: 'Sectors', href: '#/sectors' },
  { page: 'digest', label: 'Digest', href: '#/digest' },
  { page: 'settings', label: 'Settings', href: '#/settings' },
]

export function Nav({ route, edition, open }: { route: Route; edition: Edition | null; open: boolean }) {
  return (
    <nav className={`nav ${open ? 'open' : ''}`}>
      <div className="wrap nav-row">
        <div className="nav-tabs">
          {TABS.map((tab) => (
            <a key={tab.page} href={tab.href} className={route.page === tab.page ? 'active' : ''}>
              {tab.label}
            </a>
          ))}
        </div>
        {edition?.date && (
          <div className="nav-edition">
            {longDate(edition.date)} · Last scan {ago(edition.lastScan)}
          </div>
        )}
      </div>
    </nav>
  )
}

// --- Tags ---------------------------------------------------------------------

export function Tag({ kind = 'plain', children }: { kind?: 'solid' | 'tint' | 'outline' | 'plain' | 'live'; children: string }) {
  return <span className={`tag tag-${kind}`}>{children}</span>
}

export function isLive(edition: Edition): boolean {
  if (!edition.lastScan || !edition.date) return false
  const fresh = Date.now() - new Date(edition.lastScan).getTime() < 20 * 60 * 1000
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
  return fresh && edition.date === today
}

export function AlertTags({ alert, edition }: { alert: Alert; edition: Edition }) {
  const watched = edition.watchlist.some((w) => w.instruments.id === alert.instruments.id)
  return (
    <span className="tags">
      {isLive(edition) && <Tag kind="live">Live</Tag>}
      {alert.tier && alert.tier !== 'Notable' && <Tag kind="solid">{alert.tier}</Tag>}
      {watched && <Tag kind="outline">Watchlist</Tag>}
      {alert.tags.map((tag) => (
        <Tag kind="tint" key={tag}>{tag}</Tag>
      ))}
      {alert.status === 'pending' && <Tag kind="plain">Unconfirmed</Tag>}
    </span>
  )
}

// --- "How unusual" bar --------------------------------------------------------

export function UnusualBar({ z }: { z: number | null | undefined }) {
  if (z == null) return <p className="muted">Not enough history to measure a normal daily move.</p>
  const size = Math.abs(z)
  const max = Math.max(8, Math.ceil(size))
  const marks = Array.from({ length: max + 1 }, (_, i) => i).filter((i) => max <= 10 || i % 2 === 0)
  return (
    <div className="unusual" role="img" aria-label={`${times(z)} its normal daily move`}>
      <div className="unusual-track">
        <div className="unusual-normal" style={{ width: `${(1 / max) * 100}%` }} />
        <div className="unusual-fill" style={{ width: `${(size / max) * 100}%` }} />
      </div>
      <div className="unusual-scale">
        {marks.map((i) => (
          <span key={i} style={{ left: `${(i / max) * 100}%` }}>{i === 0 ? '0' : `${i}×`}</span>
        ))}
      </div>
      <div className="unusual-caption">
        <b>{times(z)}</b> its normal daily move <span className="muted">(shaded band = a normal day)</span>
      </div>
    </div>
  )
}

// --- Key numbers --------------------------------------------------------------

export function KeyNumbers({ stock }: { stock: Instrument }) {
  const s = stock.instrument_stats
  const items: [string, string][] = [
    ['Market cap', marketCap(stock, s?.market_cap)],
    ['P/E ratio', s?.pe_ratio && s.pe_ratio > 0 ? s.pe_ratio.toFixed(0) : '–'],
    ['52-week low', price(stock, s?.low_52w)],
    ['52-week high', price(stock, s?.high_52w)],
    ['Normal daily move', s?.sigma_60d ? `${(s.sigma_60d * 100).toFixed(1)}%` : '–'],
    ['Previous close', price(stock, s?.prev_close)],
  ]
  return (
    <dl className="key-numbers">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

// --- Footer -------------------------------------------------------------------

export function Footer({ edition, preview }: { edition: Edition | null; preview: boolean }) {
  return (
    <footer className="wrap footer">
      <p>
        US prices are delayed by at least 15 minutes (Alpaca). UK prices and the figures in the top strip are
        end-of-day (Yahoo Finance, unofficial). Personal use only.
        {edition?.scanned ? ` ${edition.scanned.toLocaleString('en-GB')} US stocks checked on the last scan.` : ''}
      </p>
      <p>{DISCLAIMER}</p>
      {preview && <p className="preview-note">Design preview on this Mac: reading the database without a sign-in.</p>}
    </footer>
  )
}
