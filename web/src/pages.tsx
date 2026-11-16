// The other pages: one stock, the watchlist, a market table, and sign-in.
import { useEffect, useState } from 'react'
import type { Alert, Edition, Instrument, QuoteRow } from './data'
import { loadStock } from './data'
import { direction, indexName, longDate, marketCap, pct, price, ratio, times } from './format'
import { AlertTags, KeyNumbers, Tag, UnusualBar, stockLink } from './parts'
import { supabase } from './supabase'

// --- One stock ----------------------------------------------------------------

export function StockPage({ id, edition }: { id: number; edition: Edition }) {
  const [data, setData] = useState<{ stock: Instrument; alerts: Alert[] } | null | 'missing'>(null)

  useEffect(() => {
    let current = true
    setData(null)
    loadStock(id)
      .then((found) => current && setData(found ?? 'missing'))
      .catch(() => current && setData('missing'))
    return () => {
      current = false
    }
  }, [id])

  if (data === null) return <main className="wrap"><p className="muted pad">Loading…</p></main>
  if (data === 'missing') return <main className="wrap"><p className="muted pad">That stock was not found.</p></main>

  const { stock, alerts } = data
  const quote = stock.quotes
  const today = alerts.find((a) => a.trading_date === quote?.trading_date)
  const earlier = alerts.filter((a) => a !== today)
  const watched = edition.watchlist.find((w) => w.instruments.id === stock.id)

  return (
    <main className="wrap story">
      <a className="back" href="#/">← Front page</a>
      <div className="label">{stock.sector ?? `${stock.market} markets`}</div>
      <h1>{today?.headline ?? `${stock.name} (${stock.symbol.replace(/\.L$/, '')})`}</h1>
      <p className="standfirst">
        {stock.name} ({stock.symbol}) {quote ? (
          <>
            is at {price(stock, quote.price)}, <span className={direction(quote.pct_change)}>{pct(quote.pct_change)}</span>{' '}
            on {longDate(quote.trading_date)}.
          </>
        ) : 'has no price yet.'}
        {today?.vs_index != null && ` That is ${Math.abs(today.vs_index).toFixed(1)} points worse than the ${indexName(stock.market)}.`}
      </p>
      <span className="tags">
        {today && <AlertTags alert={today} edition={edition} />}
        {!today && watched && <Tag kind="outline">Watchlist</Tag>}
      </span>

      <div className="story-columns">
        <section>
          <h2 className="mini-title">How unusual is today's move?</h2>
          <UnusualBar z={quote?.z_score} />
          {today?.rel_volume != null && (
            <p className="story-line">Trading volume: <b>{today.rel_volume.toFixed(1)}×</b> a normal day.</p>
          )}
          {watched && (
            <p className="story-line">
              Your threshold: a fall of <b>{Math.abs(watched.threshold_pct)}%</b> or{' '}
              <b>{Math.abs(watched.threshold_z)}×</b> its normal move.
            </p>
          )}

          {today?.news && today.news.length > 0 && (
            <>
              <h2 className="mini-title">Latest news mentioning {stock.symbol}</h2>
              <div className="news">
                {today.news.map((item) => (
                  <a className="news-item" key={item.headline} href={item.url ?? '#'} target="_blank" rel="noreferrer noopener">
                    <span className="news-headline">{item.headline}</span>
                    {item.source && <span className="news-source">{item.source}</span>}
                  </a>
                ))}
              </div>
              <p className="muted small">
                Headlines are matched by ticker and may not explain the move. StocksWatch does not say why a price fell.
              </p>
            </>
          )}

          {earlier.length > 0 && (
            <>
              <h2 className="mini-title">Earlier alerts</h2>
              {earlier.map((a) => (
                <p className="story-line" key={a.id}>
                  {longDate(a.trading_date)}: <span className="down">{pct(a.pct_change)}</span>, {times(a.z_score)} normal
                </p>
              ))}
            </>
          )}
        </section>

        <aside>
          <h2 className="mini-title">Key numbers</h2>
          <KeyNumbers stock={stock} />
        </aside>
      </div>
    </main>
  )
}

// --- Tables -------------------------------------------------------------------

type TableRow = { stock: Instrument; quote: QuoteRow | Instrument['quotes']; note?: string }

function StockTable({ rows }: { rows: TableRow[] }) {
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Stock</th><th>Price</th><th>Change</th><th>× normal move</th>
            <th>52-week range</th><th>Market cap</th><th>P/E</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ stock, quote, note }) => {
            const s = stock.instrument_stats
            return (
              <tr key={stock.id}>
                <td>
                  <a href={stockLink(stock)}><b>{stock.symbol.replace(/\.L$/, '')}</b></a>
                  <small>{stock.name}</small>
                </td>
                <td>{price(stock, quote?.price)}</td>
                <td className={direction(quote?.pct_change)}>{pct(quote?.pct_change)}</td>
                <td>{times(quote?.z_score)}</td>
                <td>{price(stock, s?.low_52w)} – {price(stock, s?.high_52w)}</td>
                <td>{marketCap(stock, s?.market_cap)}</td>
                <td>{ratio(s?.pe_ratio)}</td>
                <td>{note && <Tag kind="solid">{note}</Tag>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function WatchlistPage({ edition }: { edition: Edition }) {
  const alerted = new Set(edition.alerts.map((a) => a.instruments.id))
  const rows: TableRow[] = edition.watchlist.map((item) => {
    const quote = item.instruments.quotes
    const breached =
      quote != null &&
      ((quote.pct_change != null && quote.pct_change <= item.threshold_pct) ||
        (quote.z_score != null && quote.z_score <= item.threshold_z))
    return {
      stock: item.instruments,
      quote,
      note: breached ? 'Past your threshold' : alerted.has(item.instruments.id) ? 'On the front page' : undefined,
    }
  })
  const breaches = rows.filter((r) => r.note === 'Past your threshold').length
  return (
    <main className="wrap story">
      <div className="label">Your watchlist</div>
      <h1>{breaches ? `${breaches} of your stocks passed a threshold` : 'No watchlist thresholds passed'}</h1>
      <p className="standfirst">
        {rows.length} stocks, each compared with its own threshold. US prices are delayed by 15 minutes; UK prices
        are from the last London close.
      </p>
      {rows.length ? <StockTable rows={rows} /> : <p className="muted">Your watchlist is empty.</p>}
    </main>
  )
}

export function MarketPage({ market, edition }: { market: 'US' | 'UK'; edition: Edition }) {
  const alerted = new Map(edition.alerts.map((a) => [a.instruments.id, a]))
  const source = market === 'US' ? edition.fallers : edition.uk
  const rows: TableRow[] = source.map((row) => ({
    stock: row.instruments,
    quote: row,
    note: alerted.has(row.instruments.id) ? (alerted.get(row.instruments.id)!.tier ?? 'Alert') : undefined,
  }))
  return (
    <main className="wrap story">
      <div className="label">{market} markets</div>
      <h1>{market === 'US' ? 'Biggest US falls today' : 'UK shares at the London close'}</h1>
      <p className="standfirst">
        {market === 'US'
          ? `The ${rows.length} largest falls among ${edition.scanned?.toLocaleString('en-GB') ?? ''} US stocks that pass the price and liquidity filters. A tag marks the ones that also passed the alert rule.`
          : 'UK coverage is end-of-day, and for now only includes the London shares on your watchlist.'}
      </p>
      {rows.length ? <StockTable rows={rows} /> : <p className="muted">No prices yet.</p>}
    </main>
  )
}

// --- Sign-in ------------------------------------------------------------------

export function Login() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [password, setPassword] = useState('')
  const [passwordMessage, setPasswordMessage] = useState('')

  async function send(event: React.FormEvent) {
    event.preventDefault()
    setState('sending')
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin + import.meta.env.BASE_URL },
    })
    if (error) {
      setState('error')
      setMessage(error.message)
    } else {
      setState('sent')
    }
  }

  // The emailed link opens in Safari, which on an iPhone is separate from the
  // Home Screen app. A password (set on the Account page) signs the app in directly.
  async function withPassword(event: React.FormEvent) {
    event.preventDefault()
    setPasswordMessage('')
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    if (error) setPasswordMessage(error.message)
  }

  return (
    <main className="login">
      <div className="masthead-title">StocksWatch</div>
      <div className="login-box">
        <div className="label">Sign in</div>
        {state === 'sent' ? (
          <p className="standfirst">
            Check your inbox. We sent a sign-in link to <b>{email}</b>. On a computer, just click it.
          </p>
        ) : (
          <form onSubmit={send}>
            <p className="standfirst">Enter your email and we'll send a link that signs you in. No password.</p>
            <input
              type="email" required autoComplete="email" placeholder="you@example.com"
              aria-label="Email address" value={email} onChange={(e) => setEmail(e.target.value)}
            />
            <button type="submit" disabled={state === 'sending'}>
              {state === 'sending' ? 'Sending…' : 'Send sign-in link'}
            </button>
            {state === 'error' && <p className="error">{message}</p>}
          </form>
        )}

        <form onSubmit={withPassword} className="login-paste">
          <div className="label">Or use a password</div>
          <p className="muted small login-help">
            For the iPhone Home Screen app. Set a password first on the Account page, wherever you are already
            signed in.
          </p>
          <input
            type="email" required autoComplete="username" placeholder="you@example.com"
            aria-label="Email address" value={email} onChange={(e) => setEmail(e.target.value)}
          />
          <input
            type="password" required autoComplete="current-password" placeholder="Password"
            aria-label="Password" value={password} onChange={(e) => setPassword(e.target.value)}
          />
          <button type="submit">Sign in with password</button>
          {passwordMessage && <p className="error">{passwordMessage}</p>}
        </form>
        {import.meta.env.DEV && (
          <p className="muted small">
            On this Mac only: <a href="/?preview=1">open the design preview without signing in</a>.
          </p>
        )}
      </div>
    </main>
  )
}


// --- Account ------------------------------------------------------------------

export function AccountPage({ email }: { email: string }) {
  const [password, setPassword] = useState('')
  const [state, setState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [message, setMessage] = useState('')

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setState('saving')
    setMessage('')
    const { error } = await supabase.auth.updateUser({ password })
    if (error) {
      setMessage(error.message)
      setState('idle')
    } else {
      setPassword('')
      setState('saved')
    }
  }

  return (
    <main className="wrap story">
      <a className="back" href="#/">← Front page</a>
      <div className="label">Account</div>
      <h1>{email}</h1>
      <div className="login-box account-box">
        <h2 className="mini-title">Set a password</h2>
        <p className="muted small login-help">
          Needed to sign in to the iPhone Home Screen app, where emailed links do not work. At least 10
          characters. Use one you do not use anywhere else.
        </p>
        <form onSubmit={save}>
          <input type="email" autoComplete="username" value={email} readOnly hidden />
          <input
            type="password" required minLength={10} autoComplete="new-password" placeholder="New password"
            aria-label="New password" value={password} onChange={(e) => setPassword(e.target.value)}
          />
          <button type="submit" disabled={state === 'saving'}>
            {state === 'saving' ? 'Saving…' : 'Save password'}
          </button>
          {state === 'saved' && <p className="muted small">Password saved. You can now use it to sign in.</p>}
          {message && <p className="error">{message}</p>}
        </form>
      </div>
    </main>
  )
}
