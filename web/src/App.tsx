import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import type { Edition } from './data'
import { loadEdition } from './data'
import FrontPage from './FrontPage'
import Notify from './Notify'
import { AccountPage, Login, MarketPage, StockPage, WatchlistPage } from './pages'
import { Footer, Masthead, Nav, TickerStrip, readRoute, type Route } from './parts'
import { PREVIEW, supabase } from './supabase'

const REFRESH_MS = 60_000

export default function App() {
  const [session, setSession] = useState<Session | null | 'loading'>(PREVIEW ? null : 'loading')
  const [edition, setEdition] = useState<Edition | null>(null)
  const [problem, setProblem] = useState('')
  const [route, setRoute] = useState<Route>(readRoute)
  const [menuOpen, setMenuOpen] = useState(false)

  // Who is signed in?
  useEffect(() => {
    if (PREVIEW) return
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next))
    return () => data.subscription.unsubscribe()
  }, [])

  // Which page?
  useEffect(() => {
    const onChange = () => {
      setRoute(readRoute())
      setMenuOpen(false)
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  // Load the edition, then refresh it every minute.
  const signedIn = PREVIEW || (session !== null && session !== 'loading')
  useEffect(() => {
    if (!signedIn) return
    let current = true
    const load = () =>
      loadEdition()
        .then((next) => {
          if (!current) return
          setEdition(next)
          setProblem('')
        })
        .catch((error: Error) => current && setProblem(error.message))
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      current = false
      clearInterval(timer)
    }
  }, [signedIn])

  if (session === 'loading') return null
  if (!signedIn) return <Login />

  const account = PREVIEW ? 'Preview' : (session as Session).user.email ?? 'Account'

  return (
    <>
      <TickerStrip indicators={edition?.indicators ?? []} />
      <Masthead
        account={account}
        onSignOut={PREVIEW ? null : () => supabase.auth.signOut()}
        onMenu={() => setMenuOpen(!menuOpen)}
      />
      <Nav route={route} edition={edition} open={menuOpen} />
      {!PREVIEW && route.page === 'front' && <Notify />}

      {problem && <div className="wrap problem">Could not load the latest data: {problem}</div>}
      {!edition && !problem && <main className="wrap"><p className="muted pad">Loading today's edition…</p></main>}
      {edition && !edition.date && (
        <main className="wrap"><p className="muted pad">No scan has been saved yet. Run the publish command to fill the front page.</p></main>
      )}
      {edition?.date && route.page === 'front' && <FrontPage edition={edition} />}
      {edition?.date && route.page === 'watchlist' && <WatchlistPage edition={edition} />}
      {edition?.date && (route.page === 'us' || route.page === 'uk') && (
        <MarketPage market={route.page === 'us' ? 'US' : 'UK'} edition={edition} />
      )}
      {route.page === 'account' && !PREVIEW && <AccountPage email={account} />}
      {edition?.date && route.page === 'stock' && <StockPage id={route.id} edition={edition} />}

      <Footer edition={edition} preview={PREVIEW} />
    </>
  )
}
