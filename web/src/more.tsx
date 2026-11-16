// Sectors, Digest and Settings pages.
import { useEffect, useState } from 'react'
import type { Alert, ListItem, Profile, SectorRow, Sent } from './data'
import {
  loadArchive, loadList, loadProfile, loadSectors, loadSent, removeItem, saveItem, saveProfile,
} from './data'
import { direction, longDate, pct, price, times } from './format'
import Notify from './Notify'
import { PasswordBox } from './pages'
import { Tag, stockLink } from './parts'

function useLoad<T>(load: () => Promise<T>): { data: T | null; problem: string; reload: () => void } {
  const [data, setData] = useState<T | null>(null)
  const [problem, setProblem] = useState('')
  const [turn, setTurn] = useState(0)
  useEffect(() => {
    let current = true
    load()
      .then((found) => current && setData(found))
      .catch((error: Error) => current && setProblem(error.message))
    return () => {
      current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turn])
  return { data, problem, reload: () => setTurn((n) => n + 1) }
}

// --- Sectors ------------------------------------------------------------------

export function SectorsPage() {
  const { data, problem } = useLoad<SectorRow[]>(loadSectors)
  const total = data?.reduce((sum, row) => sum + row.stocks, 0) ?? 0
  return (
    <main className="wrap story">
      <div className="label">Sectors</div>
      <h1>How each sector moved</h1>
      <p className="standfirst">
        The typical (median) move of the stocks in each sector on {data?.[0] ? longDate(data[0].trading_date) : 'the latest trading day'},
        biggest fall first. {total > 0 && `Covers ${total.toLocaleString('en-GB')} US stocks whose sector is known so far.`}
      </p>
      {problem && <p className="error">Could not load sectors: {problem}</p>}
      {data && data.length === 0 && (
        <p className="muted">Sectors are filled in a few stocks at a time. Check back after the next few scans.</p>
      )}
      {data && data.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr><th>Sector</th><th>Typical move</th><th>Stocks</th><th>Falling</th><th>Down 5% or more</th><th>Biggest fall</th></tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.sector}>
                  <td><b>{row.sector}</b></td>
                  <td className={direction(row.median_pct)}>{pct(row.median_pct)}</td>
                  <td>{row.stocks}</td>
                  <td>{row.falling}</td>
                  <td>{row.big_falls}</td>
                  <td>
                    <a href={stockLink({ id: row.worst_id })}>{row.worst_name ?? 'Stock'}</a>{' '}
                    <span className={direction(row.worst_pct)}>{pct(row.worst_pct)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}

// --- Digest -------------------------------------------------------------------

export function DigestPage() {
  const { data, problem } = useLoad<Alert[]>(loadArchive)
  const sent = useLoad<Sent[]>(loadSent)
  const days = new Map<string, Alert[]>()
  for (const alert of data ?? []) days.set(alert.trading_date, [...(days.get(alert.trading_date) ?? []), alert])

  return (
    <main className="wrap story">
      <div className="label">Digest</div>
      <h1>The last three weeks, day by day</h1>
      <p className="standfirst">Every fall that passed the alert rule, grouped by trading day, largest first.</p>
      {problem && <p className="error">Could not load the digest: {problem}</p>}
      {data && days.size === 0 && <p className="muted">No alerts have been recorded yet.</p>}

      <div className="story-columns">
        <section>
          {[...days.entries()].map(([day, alerts]) => (
            <div key={day} className="digest-day">
              <h2 className="mini-title">{longDate(day)} · {alerts.length} {alerts.length === 1 ? 'fall' : 'falls'}</h2>
              {alerts.map((alert) => (
                <p className="story-line" key={alert.id}>
                  <a href={stockLink(alert.instruments)}><b>{alert.instruments.name ?? alert.instruments.symbol}</b></a>{' '}
                  <span className="down">{pct(alert.pct_change)}</span>
                  <span className="muted"> · {times(alert.z_score)} normal · {price(alert.instruments, alert.price)}</span>
                  {alert.tier && alert.tier !== 'Notable' && <> <Tag kind="solid">{alert.tier}</Tag></>}
                </p>
              ))}
            </div>
          ))}
        </section>
        <aside>
          <h2 className="mini-title">Sent to you</h2>
          {sent.data && sent.data.length === 0 && <p className="muted small">No notifications yet.</p>}
          {sent.data?.map((row) => (
            <p className="story-line small" key={row.id}>
              <span className="muted">
                {new Date(row.sent_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                {row.status !== 'sent' && ` · ${row.status === 'skipped' ? 'held back' : 'failed'}`}
              </span>
              <br />
              {(row.detail ?? row.kind).split('|').slice(-1)[0].replace(/\s*\[[^\]]*\]$/, '').replace(/^test$/, 'Test notification')}
            </p>
          ))}
        </aside>
      </div>
    </main>
  )
}

// --- Settings -----------------------------------------------------------------

function WatchRowEditor({ item, onChange }: { item: ListItem; onChange: () => void }) {
  const [drop, setDrop] = useState(String(Math.abs(item.threshold_pct)))
  const [unusual, setUnusual] = useState(String(Math.abs(item.threshold_z)))
  const [note, setNote] = useState('')

  async function run(action: () => Promise<void>, done: string) {
    setNote('')
    try {
      await action()
      setNote(done)
      onChange()
    } catch (error) {
      setNote((error as Error).message)
    }
  }
  const changed = Number(drop) !== Math.abs(item.threshold_pct) || Number(unusual) !== Math.abs(item.threshold_z)
  const valid = Number(drop) > 0 && Number(unusual) > 0

  return (
    <tr>
      <td>
        <a href={stockLink(item.instruments)}><b>{item.instruments.symbol.replace(/\.L$/, '')}</b></a>
        <small>{item.instruments.name}</small>
      </td>
      <td>
        <input className="number" type="number" min="0.5" max="50" step="0.5" value={drop}
          aria-label={`Fall in percent for ${item.instruments.symbol}`} onChange={(e) => setDrop(e.target.value)} /> %
      </td>
      <td>
        <input className="number" type="number" min="0.5" max="20" step="0.5" value={unusual}
          aria-label={`Times normal move for ${item.instruments.symbol}`} onChange={(e) => setUnusual(e.target.value)} /> ×
      </td>
      <td>
        <label className="check">
          <input type="checkbox" checked={item.enabled}
            onChange={(e) => run(() => saveItem(item.id, { enabled: e.target.checked }), '')} /> Alerts on
        </label>
      </td>
      <td className="row-actions">
        {changed && (
          <button disabled={!valid} onClick={() => run(
            () => saveItem(item.id, { threshold_pct: -Math.abs(Number(drop)), threshold_z: -Math.abs(Number(unusual)) }),
            'Saved')}>Save</button>
        )}
        <button className="link-button" onClick={() => run(() => removeItem(item.id), '')}>Remove</button>
        {note && <small>{note}</small>}
      </td>
    </tr>
  )
}

export function SettingsPage({ email, onChange }: { email: string; onChange: () => void }) {
  const list = useLoad<ListItem[]>(loadList)
  const saved = useLoad<Profile | null>(loadProfile)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [note, setNote] = useState('')
  useEffect(() => setProfile(saved.data), [saved.data])

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!profile) return
    setNote('')
    try {
      await saveProfile(profile)
      setNote('Saved.')
    } catch (error) {
      setNote((error as Error).message)
    }
  }
  const set = (changes: Partial<Profile>) => profile && setProfile({ ...profile, ...changes })

  return (
    <main className="wrap story settings">
      <div className="label">Settings</div>
      <h1>{email}</h1>

      <h2 className="mini-title">Notifications on this device</h2>
      <Notify always />

      <h2 className="mini-title">How often you are notified</h2>
      {profile && (
        <form onSubmit={save} className="settings-form">
          <label>
            Whole-market alerts a day, at most
            <input className="number" type="number" min="0" max="50" value={profile.daily_cap_market}
              onChange={(e) => set({ daily_cap_market: Number(e.target.value) })} />
          </label>
          <label>
            Watchlist alerts a day, at most
            <input className="number" type="number" min="0" max="50" value={profile.daily_cap_watchlist}
              onChange={(e) => set({ daily_cap_watchlist: Number(e.target.value) })} />
          </label>
          <label>
            Quiet hours: nothing is sent from
            <span>
              <input type="time" value={profile.quiet_start.slice(0, 5)} onChange={(e) => set({ quiet_start: e.target.value })} />
              {' to '}
              <input type="time" value={profile.quiet_end.slice(0, 5)} onChange={(e) => set({ quiet_end: e.target.value })} />
            </span>
          </label>
          <label>
            What to send
            <select value={profile.digest_mode} onChange={(e) => set({ digest_mode: e.target.value as Profile['digest_mode'] })}>
              <option value="both">Alerts as they happen, plus an evening summary</option>
              <option value="live">Alerts as they happen only</option>
              <option value="digest">Evening summary only</option>
            </select>
          </label>
          <div>
            <button type="submit">Save</button> {note && <span className="muted small">{note}</span>}
          </div>
        </form>
      )}

      <h2 className="mini-title">Your watchlist</h2>
      <p className="muted small">
        A watchlist stock alerts when it falls by the percentage, or by that many times its normal daily move,
        whichever comes first. To add a stock, search for it and use the button on its page.
      </p>
      {list.problem && <p className="error">{list.problem}</p>}
      {list.data && list.data.length === 0 && <p className="muted">Your watchlist is empty.</p>}
      {list.data && list.data.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Stock</th><th>Fall of</th><th>Or normal move ×</th><th></th><th></th></tr></thead>
            <tbody>
              {list.data.map((item) => (
                <WatchRowEditor key={`${item.id}-${item.threshold_pct}-${item.threshold_z}-${item.enabled}`} item={item}
                  onChange={() => { list.reload(); onChange() }} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="mini-title">Password</h2>
      <PasswordBox email={email} />
    </main>
  )
}
