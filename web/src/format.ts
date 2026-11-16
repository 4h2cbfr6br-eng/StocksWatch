// Turning numbers into the text shown on the page.
import type { Instrument } from './data'

const MINUS = '−' // a proper minus sign, the same width as a plus

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null) return '–'
  const sign = value < 0 ? MINUS : value > 0 ? '+' : ''
  return `${sign}${Math.abs(value).toFixed(digits)}%`
}

export function direction(value: number | null | undefined): 'up' | 'down' | 'flat' {
  if (value == null || value === 0) return 'flat'
  return value > 0 ? 'up' : 'down'
}

export function price(stock: Pick<Instrument, 'price_unit'>, value: number | null | undefined): string {
  if (value == null) return '–'
  const text = value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (stock.price_unit === 'GBX') {
    return `${value.toLocaleString('en-GB', { maximumFractionDigits: 1 })}p`
  }
  return `${stock.price_unit === 'GBP' ? '£' : '$'}${text}`
}

export function marketCap(stock: Pick<Instrument, 'market'>, value: number | null | undefined): string {
  if (!value) return '–'
  const sign = stock.market === 'UK' ? '£' : '$'
  if (value >= 1e12) return `${sign}${(value / 1e12).toFixed(2)}tn`
  if (value >= 1e9) return `${sign}${(value / 1e9).toFixed(1)}bn`
  return `${sign}${(value / 1e6).toFixed(0)}m`
}

export function times(z: number | null | undefined): string {
  return z == null ? '–' : `${Math.abs(z).toFixed(1)}×`
}

export function ratio(value: number | null | undefined): string {
  return value == null || value <= 0 ? '–' : value.toFixed(0)
}

export function longDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
}

export function clock(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

// When an alert was recorded. A scan run after the market has shut is reading
// closing prices, so say that instead of showing the time the scan happened.
export function scanTime(iso: string | null, tradingDate: string | null): string {
  if (!iso) return ''
  const day = new Date(iso).toLocaleDateString('en-CA')
  return tradingDate && day !== tradingDate ? 'the close' : `${clock(iso)} scan`
}

export function ago(iso: string | null): string {
  if (!iso) return 'never'
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

export function indexName(market: 'US' | 'UK'): string {
  return market === 'UK' ? 'FTSE 100' : 'S&P 500'
}
