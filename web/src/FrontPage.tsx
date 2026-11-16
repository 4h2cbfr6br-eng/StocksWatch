// The front page: the day's biggest significant drops, laid out like a newspaper.
import type { Alert, Edition, QuoteRow, WatchItem } from './data'
import { direction, indexName, pct, price, scanTime, times } from './format'
import { AlertTags, KeyNumbers, Tag, UnusualBar, stockLink } from './parts'

function standfirst(alert: Alert): string {
  const stock = alert.instruments
  const parts = [
    `Down ${pct(alert.pct_change).slice(1)} to ${price(stock, alert.price)}, ${times(alert.z_score)} its normal daily move`,
  ]
  if (alert.vs_index != null) {
    parts.push(`${Math.abs(alert.vs_index).toFixed(1)} points worse than the ${indexName(stock.market)}`)
  }
  let text = parts.join(' and ') + '.'
  if (alert.rel_volume != null) text += ` Trading volume was ${alert.rel_volume.toFixed(1)}× normal.`
  return text
}

function News({ alert, limit }: { alert: Alert; limit: number }) {
  const items = (alert.news ?? []).slice(0, limit)
  if (items.length === 0) return null
  return (
    <div className="news">
      <div className="news-label">Latest news mentioning {alert.instruments.symbol}</div>
      {items.map((item) => (
        <a className="news-item" key={item.headline} href={item.url ?? '#'} target="_blank" rel="noreferrer noopener">
          <span className="news-headline">{item.headline}</span>
          {item.source && <span className="news-source">{item.source}</span>}
        </a>
      ))}
    </div>
  )
}

function Lead({ alert, edition }: { alert: Alert; edition: Edition }) {
  const stock = alert.instruments
  return (
    <>
      <article className="lead">
        <div className="label">{stock.sector ?? `${stock.market} markets`}</div>
        <h1>
          <a href={stockLink(stock)}>{alert.headline ?? `${stock.name} falls ${pct(alert.pct_change).slice(1)}`}</a>
        </h1>
        <p className="standfirst">{standfirst(alert)}</p>
        <AlertTags alert={alert} edition={edition} />
        <News alert={alert} limit={2} />
      </article>

      <a className="figure" href={stockLink(stock)}>
        <div className="figure-top">
          <div className="figure-symbol">{stock.symbol}</div>
          <div className="figure-move down">{pct(alert.pct_change)}</div>
          <div className="figure-price">
            {price(stock, alert.price)} <span className="muted">at {scanTime(alert.triggered_at, alert.trading_date)}</span>
          </div>
        </div>
        <div className="figure-body">
          <UnusualBar z={alert.z_score} />
          <KeyNumbers stock={stock} />
        </div>
      </a>
    </>
  )
}

function CalmLead({ edition }: { edition: Edition }) {
  const worst = edition.fallers[0]
  return (
    <>
      <article className="lead">
        <div className="label">US markets</div>
        <h1>Calm markets: no large falls today</h1>
        <p className="standfirst">
          None of the {edition.scanned?.toLocaleString('en-GB') ?? ''} US stocks checked fell by 5% or more while
          also moving at least three times its normal amount and clearly more than the market.
        </p>
      </article>
      <div className="figure">
        <div className="figure-top">
          <div className="figure-symbol">Biggest fall today</div>
          {worst ? (
            <>
              <div className="figure-move down">{pct(worst.pct_change)}</div>
              <div className="figure-price">
                {worst.instruments.name} ({worst.instruments.symbol}),{' '}
                {times(worst.z_score)} its normal daily move
              </div>
            </>
          ) : (
            <div className="figure-price">No prices yet</div>
          )}
        </div>
      </div>
    </>
  )
}

function WatchRow({ item, alerted }: { item: WatchItem; alerted: boolean }) {
  const stock = item.instruments
  const quote = stock.quotes
  const breached =
    quote != null &&
    ((quote.pct_change != null && quote.pct_change <= item.threshold_pct) ||
      (quote.z_score != null && quote.z_score <= item.threshold_z))
  return (
    <a className="watch-row" href={stockLink(stock)}>
      <span className="watch-name">
        <b>{stock.symbol.replace(/\.L$/, '')}</b>
        <small>{stock.name}</small>
      </span>
      <span className="watch-move">
        <span className={direction(quote?.pct_change)}>{pct(quote?.pct_change)}</span>
        <small>{quote?.z_score != null ? `${times(quote.z_score)} normal` : price(stock, quote?.price)}</small>
      </span>
      {(breached || alerted) && (
        <span className="watch-tags">
          <Tag kind="solid">{breached ? 'Past your threshold' : 'On the front page'}</Tag>
        </span>
      )}
    </a>
  )
}

function WatchColumn({ edition }: { edition: Edition }) {
  const alerted = new Set(edition.alerts.map((a) => a.instruments.id))
  return (
    <aside className="watch">
      <a className="label" href="#/watchlist">Your Watchlist</a>
      {edition.watchlist.length === 0 && (
        <p className="muted">Your watchlist is empty. Stocks you add will appear here with today's move.</p>
      )}
      {edition.watchlist.map((item) => (
        <WatchRow key={item.id} item={item} alerted={alerted.has(item.instruments.id)} />
      ))}
    </aside>
  )
}

function Card({ alert, edition }: { alert: Alert; edition: Edition }) {
  const stock = alert.instruments
  return (
    <article className="card">
      <div className="label">{stock.sector ?? `${stock.market} markets`}</div>
      <h3>
        <a href={stockLink(stock)}>{alert.headline ?? `${stock.name} falls ${pct(alert.pct_change).slice(1)}`}</a>
      </h3>
      <p className="card-facts">
        <span className="down">{pct(alert.pct_change)}</span> · {times(alert.z_score)} normal move ·{' '}
        {price(stock, alert.price)}
      </p>
      <AlertTags alert={alert} edition={edition} />
      {alert.news?.[0] && (
        <a className="card-news" href={alert.news[0].url ?? '#'} target="_blank" rel="noreferrer noopener">
          {alert.news[0].headline}
        </a>
      )}
      <div className="card-time">At {scanTime(alert.triggered_at, alert.trading_date)}</div>
    </article>
  )
}

function FallerCard({ row }: { row: QuoteRow }) {
  const stock = row.instruments
  return (
    <article className="card">
      <div className="label">{stock.sector ?? stock.symbol}</div>
      <h3>
        <a href={stockLink(stock)}>{stock.name}</a>
      </h3>
      <p className="card-facts">
        <span className={direction(row.pct_change)}>{pct(row.pct_change)}</span> · {times(row.z_score)} normal move ·{' '}
        {price(stock, row.price)}
      </p>
    </article>
  )
}

export default function FrontPage({ edition }: { edition: Edition }) {
  const [lead, ...rest] = edition.alerts
  const alertedIds = new Set(edition.alerts.map((a) => a.instruments.id))
  const others = edition.fallers.filter((f) => !alertedIds.has(f.instruments.id)).slice(0, 4)

  return (
    <main className="wrap">
      {edition.sellOff && (
        <div className="sell-off">
          <Tag kind="solid">Market-wide fall</Tag>
          <span>
            The S&P 500 is {pct(edition.sellOff.index_pct)} and {edition.sellOff.alert_count} stocks passed the
            rule today. Individual falls say less than usual on a day like this.
          </span>
        </div>
      )}

      <section className="top">
        {lead ? <Lead alert={lead} edition={edition} /> : <CalmLead edition={edition} />}
        <WatchColumn edition={edition} />
      </section>

      {rest.length > 0 && (
        <>
          <h2 className="section-title"><span>More drops today</span></h2>
          <section className="grid">
            {rest.map((alert) => (
              <Card key={alert.id} alert={alert} edition={edition} />
            ))}
          </section>
        </>
      )}

      {others.length > 0 && (
        <>
          <h2 className="section-title"><span>Other large falls, within their normal range</span></h2>
          <section className="grid">
            {others.map((row) => (
              <FallerCard key={row.instruments.id} row={row} />
            ))}
          </section>
        </>
      )}
    </main>
  )
}
