// Everything the pages read from the database, in one place.
import { supabase } from './supabase'

export type Stats = {
  as_of: string | null
  prev_close: number | null
  sigma_60d: number | null
  dollar_volume_20d: number | null
  high_52w: number | null
  low_52w: number | null
  market_cap: number | null
  pe_ratio: number | null
}

export type Quote = {
  trading_date: string
  price: number
  pct_change: number | null
  z_score: number | null
  rel_volume: number | null
  dollar_volume: number | null
  updated_at: string
}

export type Instrument = {
  id: number
  symbol: string
  market: 'US' | 'UK'
  name: string | null
  sector: string | null
  price_unit: 'USD' | 'GBP' | 'GBX'
  instrument_stats: Stats | null
  quotes: Quote | null
}

export type NewsItem = { headline: string; source: string | null; url: string | null; datetime: number | null }

export type Alert = {
  id: number
  trading_date: string
  tier: 'Notable' | 'Major' | 'Severe' | null
  status: 'pending' | 'confirmed' | 'held'
  triggered_at: string
  price: number
  pct_change: number
  z_score: number
  rel_volume: number | null
  vs_index: number | null
  dollar_volume: number | null
  push_eligible: boolean
  tags: string[]
  headline: string | null
  news: NewsItem[] | null
  instruments: Instrument
}

export type WatchItem = {
  id: number
  threshold_pct: number
  threshold_z: number
  instruments: Instrument
}

export type Indicator = { key: string; label: string; value: number | null; pct_change: number | null }
export type MarketEvent = { index_pct: number | null; alert_count: number | null }
export type QuoteRow = Quote & { instruments: Instrument }

export type Edition = {
  date: string | null            // the trading day shown
  lastScan: string | null        // when the scanner last finished
  scanned: number | null
  indicators: Indicator[]
  alerts: Alert[]
  watchlist: WatchItem[]
  fallers: QuoteRow[]            // biggest US falls today, alert or not
  uk: QuoteRow[]
  sellOff: MarketEvent | null
}

const STOCK = '*, instrument_stats(*), quotes(*)'

function rows<T>(result: { data: unknown; error: { message: string } | null }): T[] {
  if (result.error) throw new Error(result.error.message)
  return (result.data ?? []) as T[]
}

export async function loadEdition(): Promise<Edition> {
  const latest = rows<{ trading_date: string }>(
    await supabase
      .from('quotes')
      .select('trading_date, instruments!inner(market)')
      .eq('instruments.market', 'US')
      .eq('eligible', true)
      .order('trading_date', { ascending: false })
      .limit(1),
  )
  const date = latest[0]?.trading_date ?? null

  const [indicators, scans, watchlist, uk] = await Promise.all([
    supabase.from('market_indicators').select('*').order('sort_order'),
    supabase.from('scan_runs').select('finished_at, symbols_scanned').eq('status', 'ok')
      .order('finished_at', { ascending: false }).limit(1),
    supabase.from('watchlist_items').select(`*, instruments(${STOCK})`).eq('enabled', true),
    supabase.from('quotes').select('*, instruments!inner(*, instrument_stats(*))')
      .eq('instruments.market', 'UK').order('pct_change'),
  ])

  let alerts: Alert[] = []
  let fallers: QuoteRow[] = []
  let sellOff: MarketEvent | null = null
  if (date) {
    const [a, f, e] = await Promise.all([
      supabase.from('alerts').select(`*, instruments(${STOCK})`).eq('trading_date', date).neq('status', 'held'),
      supabase.from('quotes').select('*, instruments!inner(*, instrument_stats(*))')
        .eq('trading_date', date).eq('eligible', true).eq('instruments.market', 'US')
        .order('pct_change').limit(40),
      supabase.from('market_events').select('index_pct, alert_count').eq('trading_date', date).eq('market', 'US'),
    ])
    alerts = rows<Alert>(a).sort((x, y) => score(y) - score(x))
    fallers = rows<QuoteRow>(f)
    sellOff = rows<MarketEvent>(e)[0] ?? null
  }

  const scan = rows<{ finished_at: string; symbols_scanned: number | null }>(scans)[0]
  return {
    date,
    lastScan: scan?.finished_at ?? null,
    scanned: scan?.symbols_scanned ?? null,
    indicators: rows<Indicator>(indicators),
    alerts,
    watchlist: rows<WatchItem>(watchlist).sort(
      (x, y) => (x.instruments.quotes?.pct_change ?? 0) - (y.instruments.quotes?.pct_change ?? 0),
    ),
    fallers,
    uk: rows<QuoteRow>(uk),
    sellOff,
  }
}

// Front-page order: how unusual the fall is, weighted up for bigger companies.
export function score(alert: Alert): number {
  const traded = Math.max(alert.dollar_volume ?? 2e7, 2e7)
  return Math.abs(alert.z_score) * (1 + Math.log10(traded / 2e7))
}

export async function loadStock(id: number): Promise<{ stock: Instrument; alerts: Alert[] } | null> {
  const stock = rows<Instrument>(await supabase.from('instruments').select(STOCK).eq('id', id))[0]
  if (!stock) return null
  const alerts = rows<Alert>(
    await supabase.from('alerts').select(`*, instruments(${STOCK})`).eq('instrument_id', id)
      .neq('status', 'held').order('trading_date', { ascending: false }).limit(10),
  )
  return { stock, alerts }
}

export async function searchStocks(text: string): Promise<Instrument[]> {
  const q = text.trim().replace(/[%,()*]/g, '')
  if (q.length < 1) return []
  return rows<Instrument>(
    await supabase.from('instruments').select(STOCK)
      .or(`symbol.ilike.${q}*,name.ilike.*${q}*`).eq('is_active', true).order('symbol').limit(8),
  )
}
