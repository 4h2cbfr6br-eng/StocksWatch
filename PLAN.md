# PLAN.md — StocksWatch: stock-drop alerts app

> Planning document only. No code has been written. Approved 15 Nov 2026.
> Prices and limits were checked on 15 Nov 2026. Items marked **(verify)** could not be confirmed from an official page and get tested in Phase 0 before anything depends on them.

## 1. Context

**What it is.** An app that scans the stock market, spots unusually large falls, and pushes an alert to your iPhone with enough context (news, how unusual the move is, key numbers) for you to judge it yourself. The home screen is an original newspaper-style "front page of the day's biggest drops".

**Your answers that shaped this plan**

| Question | Answer | What it changes |
|---|---|---|
| Coding experience | None | Fewest moving parts, managed services, no servers to look after, readable Python for the maths |
| Age | 18+ | You can hold every account yourself |
| Apple Developer fee (£79/yr) | Not until launch | Rules out native push for now, so the app is an installable web app |
| Monthly budget | £0 | Free tiers only. "Real-time" means free IEX prices, not a paid full-market feed |
| Ambition | Free first, maybe subscription later, undecided | Build for personal use, but mark exactly what changes when other people use it |
| UK stocks | US first, UK end-of-day | US scanned through the day; UK checked once after the London close |

**The three big decisions (detail later)**

1. **Client:** an installable web app (PWA) with web push. It is the only option that puts notifications on your iPhone for £0.
2. **Stack:** Python for the scanner and backtester, Supabase (hosted Postgres database + login) for data and accounts, a React web app hosted free on Cloudflare Pages. No server of your own until Phase 3.
3. **Data:** Alpaca's free plan for US prices, Finnhub's free plan for news and key numbers, an unofficial Yahoo source for UK end-of-day. All on personal-use licences, which is the main thing that has to change before launch.

---

## 2. Client: how alerts reach the iPhone

| | Installable web app (PWA) + web push | React Native / Expo | Native SwiftUI |
|---|---|---|---|
| Push on a real iPhone for free | **Yes** (iOS 16.4+, after "Add to Home Screen") | No. Push needs the paid Apple account | No. Push needs the paid Apple account |
| Cost now | £0 | £79/yr | £79/yr |
| Languages | One web codebase | TypeScript + native build tooling | Swift, plus a separate website if you ever want one |
| Install | Open link, Share, Add to Home Screen | TestFlight / App Store | TestFlight / App Store |
| Push reliability | Good, not perfect. Subscriptions occasionally drop and need re-enabling | Excellent (Apple's own push service) | Excellent |
| Newspaper layout | Easiest. This is what CSS is built for | Harder; fine typography takes more work | Good, but slowest to build |
| Works on Android / laptop | Yes, same code | Android yes, laptop no | No |
| App Store presence | No | Yes | Yes |

**Recommendation: PWA now.** It is free, it suits a text-heavy newspaper design, and one codebase works on your phone and MacBook. Two safeguards:

- **Backup channel:** a free Telegram bot sends the same alert. If web push ever silently stops, you still get the message and you notice the difference.
- **Door left open:** the app talks to the backend through a normal web API. At launch, if you want the App Store, wrap the same web code with Capacitor (cheapest) or build a native client. Nothing in the backend changes.

---

## 3. Market data

### 3.1 Provider comparison

| Provider | Free tier | Whole market in few calls? | Freshness on free | First paid step | UK (LSE) | Licence on cheap tiers |
|---|---|---|---|---|---|---|
| **Alpaca** | 200 calls/min; websocket limited to 30 symbols; history back to 2016 | Yes, multi-symbol snapshot calls **(verify batch size)** | IEX exchange real-time (a small slice of all trades); full-market (SIP) data only once it is 15 min old | $99/mo: real-time from all US exchanges, unlimited websocket | No | Personal use |
| **Massive** (was Polygon.io) | 5 calls/min, ~2 years history | Yes for end-of-day: one "grouped daily" call returns every US stock **(verify still on free)** | End-of-day | About $29/mo for 15-min delayed with unlimited calls; $199/mo real-time **(verify, pricing page was unclear)** | No | "Individual use only" |
| **Finnhub** | ~60 calls/min; websocket ~50 symbols | No, one symbol per call | US real-time quotes; company news; basic financials | Per-market paid plans | Paid only **(verify)** | Personal use; news redistribution restricted |
| **EODHD** | 20 calls/day (too small to use) | Yes, bulk end-of-day per exchange | End-of-day | $19.99/mo "EOD All World", 100k calls/day, includes bulk API, splits, dividends | **Yes** | Personal; commercial is "contact us" |
| **Twelve Data** | 8 calls/min, 800/day | No | Delayed | Paid tiers are pricey | Paid tiers **(verify)** | Personal |
| **Alpha Vantage** | 25 calls/day | No | End-of-day | ~$50/mo | EOD | Personal |
| **yfinance** (unofficial Yahoo) | Free, no key | Yes, batch download | ~15-20 min delayed | n/a | **Yes** | Unofficial. Personal use only, can break without warning |
| **SEC EDGAR** | Free, official | n/a (filings, not prices) | Minutes after filing | n/a | No | Public domain. Safe to show anyone |

### 3.2 Recommended line-up

| Need | Phases 0-2 (£0) | Phase 3 (£0) | Launch (paid) |
|---|---|---|---|
| US intraday scan | Alpaca snapshots, 15-min delayed full-market | Alpaca IEX real-time, polled every minute; confirmed against delayed full-market | Commercial display licence (Alpaca / Massive business / Tiingo / FMP, get quotes) |
| US history + nightly close | Alpaca daily bars; Massive grouped-daily as a cross-check | same | same vendor |
| UK end-of-day | yfinance, FTSE 350 only | same, or EODHD at $19.99/mo if yfinance proves flaky | EODHD commercial or similar |
| News | Finnhub company news + SEC EDGAR 8-K filings | same | Licensed news feed, or EDGAR/RNS links only |
| Key numbers | Finnhub basic financials (market cap, P/E); 52-week range computed from our own history | same | same vendor as prices |
| Splits / dividends | Alpaca corporate actions | same | same |
| Top ticker strip | yfinance for FTSE 100, S&P 500, GBP/USD, Brent | same | ETF proxies or licensed index data (index providers charge separately) |

Every provider sits behind one small interface (`get_snapshots`, `get_daily_bars`, `get_news`, …). Swapping a provider later means writing one new adapter, not touching the scanner.

### 3.3 Licensing: what you can show whom

- **Only you (Phases 0-3):** every free or personal plan above is fine. The site sits behind a login with one user.
- **Friends:** strictly, this is already "redistribution" under personal licences. Do not add other users until you have either a provider's written OK or a commercial plan.
- **Public (Phase 5):** you need a plan that explicitly grants **display / redistribution** rights. Rules of thumb:
  - Real-time US data from all exchanges carries exchange fees per user. Avoid.
  - 15-minute delayed US data has no exchange fees, but the vendor's own licence still applies.
  - London Stock Exchange data is strict and expensive in real time. End-of-day is the realistic tier.
  - "Derived" figures (a % drop, a z-score) are usually still covered by the vendor's terms.
  - Index names and values (FTSE, S&P) are licensed separately from share prices.
  - News headlines are copyright. Show headline + source + link only under a feed that allows it; official filings (EDGAR) are safe.
- **Budget reality:** commercial display licences are the single biggest launch cost. Expect quotes anywhere from roughly £50 to £500+ a month. Get quotes before committing to Phase 5.

### 3.4 Phase 0 verification results (tested 15 Nov 2026 with real free-plan keys)

| Item | Result |
|---|---|
| Alpaca: whole-market snapshots on the free plan | **Confirmed.** `feed=delayed_sip` (15-min delayed, all exchanges) and `feed=iex` (real-time, IEX only) both work. `feed=sip` (real-time, all exchanges) is refused, as expected |
| Alpaca: stocks per snapshot request | **Confirmed.** 5,000 symbols in one request took 1.4 s. ~12,700 in one request fails (address too long), so split into batches of about 2,000-5,000. A full-market scan is 3-6 requests against a 200/min limit |
| Alpaca: stock list | **Confirmed.** ~14,400 active US assets, ~12,700 on the main exchanges. The list has no market cap or security type, so size filters need another source |
| Alpaca: 5-year daily history, split-adjusted | **Confirmed** |
| Alpaca: splits calendar | **Confirmed.** Returns Nvidia's 10-for-1 split with ex-date 10 Jun 2024 |
| Alpaca: news and market clock | **Confirmed** (news is a bonus second source of headlines) |
| Finnhub: US quote, company profile, market cap, P/E, 52-week range, company news, earnings calendar | **Confirmed**, 60 calls/min |
| Finnhub: UK (London) shares | **Not on the free plan** (access refused). UK stays on yfinance, as planned |
| Massive: grouped-daily on the free plan | **Not tested** (no account). Not needed while Alpaca works; it was only a cross-check |
| Web push reaching the iPhone | **Confirmed.** A test notification sent from Python (pywebpush) arrived on the iPhone 16 Pro through Apple's web push service, with the page installed to the Home Screen. No Apple Developer account needed. Test code is in `push_test/` |

Consequence for the size filter: Finnhub gives market cap one stock at a time (60/min), so the nightly job fetches caps for the liquid shortlist only (pick by Alpaca volume and price first, then look up ~2,500 caps over about 45 minutes, or refresh a slice each night).

---

## 4. Drop detection

### 4.1 The options

| Method | What it measures | Good at | Weak at |
|---|---|---|---|
| **% from previous close** | Today's price vs last night's close | Simple, matches what news reports | Treats a sleepy utility and a wild biotech the same |
| **Intraday from open / day's high** | Fall during the session | Midday news that a close-to-close view hides | Misses overnight gaps |
| **Volatility-adjusted (z-score)** | Today's return divided by the stock's normal daily move | Finds moves that are unusual *for that stock* | Needs ~60 days of history; a quiet stock can trigger on a tiny move |
| **Gap-down** | Opening price vs previous close | Earnings and overnight news | Fires at the open, when prices are jumpiest |
| **Market-relative** | Stock's return minus the index's return | Stops 500 alerts on a day the whole market falls | Needs index data in the same scan |

**The z-score in plain terms.** For each stock, take the last 60 daily returns and compute their standard deviation σ (your A-level stats). If a stock normally moves 1.5% a day and is down 9%, that is z = −6: a six-sigma day. One caveat worth knowing: stock returns are **not** normally distributed. They have fat tails, so a −3σ day happens far more often than the 0.13% a normal curve predicts. Treat z as a ranking tool, not a probability. Safeguards: use a robust σ (median-based, so one old crash does not inflate it) and floor σ at 1% so very quiet stocks do not trigger on small moves.

### 4.2 Recommended rule: combine them

A whole-market alert fires only when **all** of these hold:

| Check | Default |
|---|---|
| Fall from previous close | ≤ −5% |
| Volatility-adjusted | ≤ −3σ |
| Market-relative | at least 3 percentage points worse than its index |
| Volume | running at ≥ 1.5× normal for the time of day |
| Persistence | true on 2 scans in a row |

- **Tiers:** Notable (−5%), Major (−10%), Severe (−20%). Moving up a tier is the only reason to alert twice in a day.
- **Gap-down variant:** open ≤ −4% and ≤ −3σ, checked 5 minutes after the open, not at the bell.
- **Intraday variant (Phase 3):** fell ≥ 4% and ≥ 2.5σ from the day's high within 60 minutes.
- **Watchlist rule:** your own threshold per stock (default −4% **or** −2.5σ). No size filters; you chose the stock.
- **Front-page ranking:** score = size of z × a weight for company size. The top score is the lead story.

### 4.3 Noise filters (whole-market scan only)

| Filter | US default | UK default |
|---|---|---|
| Company size | Market cap ≥ $2bn | FTSE 350 members |
| Penny stocks | Price ≥ $5 | No price filter (many sound UK shares trade under 100p) |
| Liquidity | Average ≥ $20m traded per day | Average ≥ £1m per day |
| Security type | Ordinary shares only. No ETFs, leveraged products, warrants, SPACs, preference shares | same |
| History | ≥ 60 trading days (excludes fresh IPOs) | same |

This leaves roughly 1,500-2,000 US stocks plus 350 UK ones. All thresholds are starting guesses; the backtester (section 7) is what tunes them. Target: 1-5 whole-market alerts on a normal day.

---

## 5. False alerts

| Cause | What goes wrong | Defence |
|---|---|---|
| **Stock splits** | A 10-for-1 split looks like a −90% crash | Load the corporate-actions calendar nightly and adjust the previous close. Extra check: any fall close to −50%, −67%, −75%, −80%, −90% is held until a split is ruled out |
| **Special dividends, spin-offs** | Price drops by the payout on the ex-date | Adjust previous close for the dividend; tag spin-offs and suppress that day |
| **Ticker changes, delistings** | Stale or missing price | Refresh the instrument list nightly; skip anything inactive |
| **Trading halts** | Price freezes, then jumps on resume | Read halt status; show HALTED, alert only after trading resumes and the rule still holds |
| **Bad ticks** | One wrong print shows −40% for a second | Two-scans-in-a-row rule; compare against bid/ask midpoint; for Severe tier, confirm with a second provider before sending |
| **Pence vs pounds (UK)** | LSE quotes in pence. Mixing GBX and GBP gives a fake −99% | Store the price unit on every instrument; reject any move beyond −60% without a second-source match |
| **Pre- and after-market** | Thin trading, wild prices | Off by default. Shown as a PRE-MARKET card only, then confirmed (or dropped) 5 minutes after the open |
| **Results days** | Big moves are expected | Not suppressed, but tagged RESULTS DAY from an earnings calendar |
| **Whole-market sell-off** | Hundreds of stocks trigger together | Market-relative check, plus "sell-off mode": if the index is ≤ −3% or more than 25 stocks trigger, send one market-wide alert |
| **Thin free-tier data (IEX)** | IEX is a small share of trading; quiet stocks show stale prices | Phase 3 alerts carry an UNCONFIRMED tag until the 15-min delayed full-market price agrees |

Every suppressed candidate is logged with its reason, so you can audit what the filters are hiding.

---

## 6. Alert fatigue

- **Dedupe:** one alert per stock, per trading day, per tier.
- **Cooldown:** after an alert, the same stock stays quiet for 24 trading hours unless it crosses the next tier.
- **Daily cap:** default 5 whole-market pushes and 10 watchlist pushes. When the cap bites, the highest-scoring alerts win and the rest appear on the front page only.
- **Quiet hours:** no pushes outside hours you set (default 07:00-22:00 UK).
- **Daily digest (optional):** one notification after the US close (about 21:15 UK) summarising the day; a UK edition after 16:45. Users can choose digest-only.
- **Sell-off mode:** one notification for a market-wide fall (see above).
- **Design split that makes this work:** an *alert* is a fact about a stock (stored once). A *notification* is a delivery to one user (stored per user). Caps, cooldowns and digests all live on the notification side.

---

## 7. Backtesting

**Goal:** before any rule is allowed to buzz your phone, replay history and answer two questions. How often would it have fired? What did the price do next?

- **Data:** 5+ years of daily bars for the US universe (Alpaca, free), stored as Parquet files on your Mac. FTSE 350 from yfinance.
- **Method:** run exactly the same rule code the live scanner uses, one historical day at a time. With daily bars, the day's Low tells us whether a threshold was touched intraday. Minute bars are fetched only for days that triggered, to check timing.
- **Outputs per rule:**
  - alerts per day (median, 95th percentile, worst day)
  - forward return after 1, 5, 20 and 60 trading days, and the same **minus the index**
  - share of alerts that were higher later, median outcome, worst outcome
  - breakdowns by company size, by z-score band, results day vs not
- **Traps, and how the plan handles them:**
  - *Look-ahead bias:* σ and averages use only data from before the day being tested.
  - *Survivorship bias:* free data mostly omits companies that went bust, which flatters "buy the dip". Stated on every report; fixable later with paid delisted data.
  - *Overfitting:* tune on 2019-2023, then test once on 2024-2026 without touching the settings.
  - *Honesty:* falls after bad results often keep drifting down. The backtest is there to show this, not to prove dips are bargains.
- **Use:** results are for tuning thresholds privately. They are never shown to users as evidence that buying drops works (see section 10).

### 7.1 First backtest results (16 Nov 2026)

Data: 2,884 US stocks still listed today, daily bars Oct 2018 to Nov 2026 (Alpaca). Tuned on 2020-2023, checked on 2024 onwards. Full output: `out/backtest.txt` (re-create with `python -m stockswatch backtest`). Company size is approximated by money traded per day, because free data has no historical market cap.

**Finding 1: the default rule is too noisy with the default filters.**

| Rule A (−5%, 3× normal, 3 pts worse than index, volume 1.5×) | Alerts per day 2020-23 (average / typical / busy day) | Alerts per day 2024+ | Days with more than 5 (2024+) |
|---|---|---|---|
| Stocks trading ≥ $20m a day (plan default) | 7.5 / 3 / 26 | 12.1 / 7 / 39 | 61% |
| ≥ $100m a day | 3.2 / 1 / 11 | 5.8 / 3 / 18 | 30% |
| ≥ $250m a day | 1.5 / 1 / 5 | 3.0 / 2 / 9 | 12% |
| ≥ $500m a day | 0.7 / 0 / 3 | 1.5 / 1 / 5 | 4% |

The target was 1-5 a day. Raising the % threshold helps less than raising the size filter (−7% at ≥ $20m still averages 8.9 a day in 2024+).

**Finding 2: market-wide sell-offs swamp everything.** The busiest days were 12 Mar 2020 (285 alerts, index −6.9%) and 3 Apr 2025 (270 alerts, index −4.9%). The "3 points worse than the index" check alone does not stop this; sell-off mode (section 5) is essential.

**Finding 3: a big fall, on its own, told you nothing about what came next.** Twenty days after a Rule A alert the median stock was up about 1%, which is 0.7 points *behind* the index in both periods, almost identical to picking any stock on any day (0.5-0.9 behind). About half went up and half went down. One alert in twenty was down a further 19-29% a month later. This is with survivorship bias flattering the numbers. It supports the plan's stance: alerts are information, and the wording must never imply a fall is a bargain.

**Finding 4: intraday scanning will fire about twice as often.** Only half of the stock-days that touched −5% during the day also closed that low.

**Decision taken into Phase 1 (agreed 16 Nov 2026):**
- **Push notifications:** Rule A, only for stocks trading ≥ $250m a day (roughly the largest 300-400 US companies), plus the daily cap of 5. About 1-3 a day.
- **Front page only (no push):** everything else that passes Rule A at ≥ $20m a day.
- **Sell-off mode** is built in Phase 1, not deferred.
- Watchlist alerts are unaffected: your own stocks, your own thresholds.

---

## 8. Architecture

```
  DATA PROVIDERS            PYTHON JOBS                          STORAGE
  (free tiers)              (GitHub Actions, later a worker)

 ┌────────────────┐ nightly ┌─────────────────────────┐      ┌──────────────────────────┐
 │ Alpaca   (US)  │────────▶│ 1 INGEST                │─────▶│ Price history: Parquet   │
 │ Massive  (EOD) │         │ daily bars, splits,     │      │ files, read with DuckDB  │
 │ Finnhub  (news)│         │ company list, key nums  │      └────────────┬─────────────┘
 │ yfinance (UK)  │         └────────────┬────────────┘                   │
 │ SEC EDGAR      │                      ▼                                ▼
 └───────┬────────┘         ┌─────────────────────────┐      ┌──────────────────────────┐
         │                  │ instrument_stats        │      │ BACKTESTER (on your Mac) │
         │ every 1-5 min    │ prev close, σ, avg vol, │      │ same rule code as live   │
         │ in market hours  │ 52-wk range  (Postgres) │      └──────────────────────────┘
         ▼                  └────────────┬────────────┘
 ┌─────────────────────────┐             │
 │ 2 SCANNER               │◀────────────┘
 │ price snapshots → rules │
 └────────────┬────────────┘
              ▼ candidates
 ┌─────────────────────────┐       ┌─────────────────────────┐
 │ 3 VERIFY + ENRICH       │──────▶│ alerts  (Postgres)      │
 │ split/halt/tick checks, │       └────────────┬────────────┘
 │ news, key numbers       │                    │
 └─────────────────────────┘                    ▼
                                   ┌─────────────────────────┐  web push   ┌────────────┐
                                   │ 4 DISPATCHER            │────────────▶│ iPhone PWA │
                                   │ match users, dedupe,    │  (Telegram  └─────┬──────┘
                                   │ cooldown, caps, digest  │   backup)         │
                                   └─────────────────────────┘                   │
                                   ┌─────────────────────────┐   HTTPS, login,   │
                                   │ SUPABASE                │◀──────────────────┘
                                   │ Postgres + Auth +       │   row-level security
                                   │ automatic REST API      │
                                   └─────────────────────────┘
                                     Frontend: React PWA on Cloudflare Pages
```

### 8.1 The pieces, in plain terms

| Piece | Choice | Why |
|---|---|---|
| Scanner, ingest, dispatcher, backtester | **Python** (pandas, DuckDB) | Most readable language for the maths; one rule module shared by live scanning and backtesting |
| Where the jobs run (Phases 1-2) | **GitHub Actions** on a timer, public repo | Free and unlimited for public repos; nothing to maintain. Timing can slip by several minutes, which is fine on 15-min delayed data |
| Where the jobs run (Phase 3) | One always-on worker on a free cloud VM (Oracle or Google free tier) | A loop every minute needs a machine that stays on |
| Database | **Supabase** free tier (Postgres) | Database, login and an automatic API in one service. 500 MB is plenty because bulk prices are not stored here |
| Price history (time-series) | **Parquet files + DuckDB** | Millions of daily bars compress to a few hundred MB and query in milliseconds. No special time-series database needed |
| API | Supabase's auto-generated REST API, guarded by row-level security | No custom server to write or host in the early phases |
| Frontend | **React + Vite + TypeScript**, PWA plugin | Most widely supported; builds to static files |
| Frontend hosting | **Cloudflare Pages** | Free, fast, and allows commercial use later (some rivals' free tiers do not) |
| Push | Web Push (VAPID keys) sent from Python; service worker in the PWA | Free, no Apple account |
| Monitoring | Each scan writes a `scan_runs` row; the site shows "last scan 3 min ago"; a free heartbeat service emails you if scans stop | Silent failure is the main risk for an alerts app |

### 8.2 Data model (designed for portfolios from day one)

```
instruments         id, symbol, exchange, name, currency, price_unit (USD/GBP/GBX),
                    sector, type, is_active          ← internal id, because tickers change
instrument_stats    instrument_id, as_of, prev_close, sigma_60d, avg_volume_20d,
                    high_52w, low_52w, market_cap, pe_ratio
corporate_actions   instrument_id, ex_date, type, ratio, amount
rules               id, name, params (JSON), version ← live and backtest share these
scan_runs           id, started_at, source, symbols_scanned, status
alerts              id, instrument_id, trading_date, rule_id, tier, triggered_at, price,
                    pct_change, z_score, rel_volume, vs_index, tags, headline, news,
                    data_delay                        ← a fact about a stock, no user
profiles            user_id, timezone, daily_cap, quiet_hours, digest_mode
watchlists          id, user_id, name
watchlist_items     watchlist_id, instrument_id, threshold_pct, threshold_z, enabled
push_subscriptions  id, user_id, endpoint, keys, last_ok_at
notifications       id, user_id, alert_id, channel, sent_at, status   ← per-user delivery

-- Phase 4, slots in with no changes to anything above --
portfolios          id, user_id, name, base_currency
transactions        id, portfolio_id, instrument_id, type (buy/sell/dividend/fee/split),
                    quantity, price, fees, currency, fx_rate, executed_at
holdings            a VIEW calculated from transactions (never stored by hand)
```

Rules that prevent a rewrite later:
- Every user-owned table has `user_id` from Phase 1, even with one user.
- Row-level security is on from the first table: the database itself refuses to return another user's rows.
- Money is stored as exact decimals, never floating point, always with its currency.
- Transactions are an append-only ledger; holdings and profit/loss are calculated from it.
- Alerts are global, notifications are per user. Adding users adds rows, not code.

---

## 9. Accounts, security and GDPR

**Auth**
- Supabase Auth with email magic links (no passwords for you to store or leak). Add Sign in with Apple / Google at launch.
- Phase 1 has exactly one account (yours); sign-ups switched off.

**Security basics**
- API keys live in GitHub Secrets and environment variables, never in code. The repo is public, so this matters from the first commit.
- The powerful database key is used only by the Python jobs. The web app gets the limited public key and is fenced in by row-level security.
- HTTPS everywhere (automatic on Cloudflare and Supabase).
- Tests that prove user A cannot read user B's watchlist, before any second user exists.
- Database hosted in Supabase's London region.

**UK GDPR basics (needed from the moment other people sign up)**
- Collect the minimum: email, watchlist, notification settings, push subscription. Later, portfolio holdings (personal data, not "special category", but sensitive to users).
- Plain-English privacy policy: what, why, where stored, how long, who processes it (Supabase, Cloudflare).
- Lawful basis: providing the service the user signed up for. Marketing emails need separate opt-in.
- In-app "export my data" and "delete my account" (deletes rows for real).
- Register with the ICO and pay the data protection fee (about £52/yr) once it is more than a personal project.
- No tracking or advertising cookies, so no cookie banner. Self-host the fonts so no visitor data goes to Google.
- Terms state 18+ only. Breach plan: tell the ICO within 72 hours if personal data leaks.

---

## 10. UK legal: information, not advice

*I am not a lawyer. This section is a map of the issues, not legal advice. Pay for a short legal review before Phase 5.*

**The line.** In the UK, "advising on investments" is a regulated activity needing FCA authorisation. The FCA's guidance (PERG 8) says advice involves an **opinion or recommendation on the merits of buying or selling a particular investment**. Plain factual information is not advice, but selection and wording can turn information into an implied recommendation. An app whose whole point is "this fell, consider buying" sits close to that line, so wording carries the weight.

**Wording rules for every screen and notification**

| Say | Never say |
|---|---|
| "Nvidia falls 15%" | "Buy the dip", "bargain", "opportunity", "on sale" |
| "5.1× its normal daily move" | "Oversold", "overreaction", "undervalued", "cheap" |
| "Latest news: …" with source | "Fell because…" as our own claim; "expected to recover" |
| "P/E 31, 52-week range $86-$153" | "Fundamentally strong", "quality company", star ratings, buy/sell scores |
| "Biggest falls today" | "Best dips to buy", "top picks" |

- The filters (company size, liquidity) are described as **noise filters**, not as a quality judgement.
- No personalisation that looks like advice. "Stocks on your watchlist" is fine; "suitable for you" is not.
- Backtest results are never published as a reason to act.

**Disclaimers** (footer on every page, shown once at sign-up, linked from notifications)
> Information only. Not investment advice or a personal recommendation. StocksWatch is not authorised or regulated by the Financial Conduct Authority. Prices may be delayed or wrong. The value of investments can fall as well as rise and you may get back less than you invest. Do your own research or speak to an authorised adviser.

Disclaimers help, but they do not rescue content that reads as a recommendation. The wording rules matter more.

**What changes if it becomes a paid, public product**
- It is now clearly "by way of business", so the advice question is live. Get a solicitor's written view on whether the product is information-only (and whether the exemption for news-style publications fits).
- **Financial promotions (FSMA s.21):** communicating an invitation or inducement to invest, in the course of business, needs approval from an FCA-authorised firm. Broker affiliate links, "sign up and buy" buttons and broker adverts all risk this. Keep them out.
- Commercial market-data licences (section 3.3).
- Consumer law: clear pricing, cancellation rights, the new UK subscription-contract rules.
- A limited company to separate your personal liability, proper terms of service, ICO registration.
- If sold through the App Store: Apple's in-app purchase rules and its commission.

---

## 11. Design system (original, newspaper feel)

**Name: StocksWatch** (decided). The masthead reads "StocksWatch" in the masthead serif, as one word.

- Before Phase 5, check the domain, the App Store and the UK trademark register. Similar names ("StockWatch", "Stock Watch") are common in finance, so a clash is possible at public launch. It does not matter while the app is personal.

**Fonts** (all SIL Open Font Licence, free for commercial use, self-hosted)

| Role | Font | Fallback idea |
|---|---|---|
| Masthead | **Playfair Display** (bold, tight tracking) | Libre Caslon Display |
| Headlines | **Newsreader** (display sizes, medium weight) | Source Serif 4 |
| Standfirsts, nav, labels, tags | **Hanken Grotesk** | Figtree, Libre Franklin |
| Prices and % (aligned digits) | Hanken Grotesk with tabular figures | IBM Plex Sans |

**Colour** (own palette, deliberately not the FT's exact values)

| Token | Value | Use |
|---|---|---|
| Paper | `#F8ECDF` | Page background |
| Ink | `#1E1A17` | Text |
| Grey | `#6B625B` | Standfirsts, timestamps |
| Claret | `#8A1C3C` | Section labels, links |
| Navy | `#151E33` | Top ticker strip |
| Up / Down (on paper) | `#17693F` / `#B3261E` | % changes |
| Up / Down (on navy) | `#6FD29A` / `#FF8A80` | Outlined % boxes in the strip |
| Hairline | Ink at 20% | Rules and column dividers |

**Components**
- **Ticker strip:** navy, full width. Name in white, % in a small outlined box, green or red. FTSE 100, S&P 500, GBP/USD, Brent.
- **Masthead row:** menu and search left, centred serif masthead, account right.
- **Nav row:** small uppercase links between hairline rules, active tab underlined. Tabs: Front Page, Watchlist, US, UK, Sectors, Digest, Settings.
- **Lead story:** claret section label (the sector), large serif headline, grey standfirst with the three context facts, related lines underneath.
- **Side column:** "Your Watchlist" with each stock's move today and distance from its threshold.
- **Section title:** centred, letter-spaced uppercase between dotted rules ("MORE DROPS TODAY").
- **Card grid:** four columns on desktop, one on phone. Sector label, headline, tags, time.
- **Tag pills:** LIVE, WATCHLIST, 52-WEEK LOW, GAP DOWN, RESULTS DAY, PRE-MARKET, HALTED, UNCONFIRMED, DELAYED 15 MIN, UK CLOSE.
- **Story page (tap an alert):** price chart, "how unusual" bar (today vs normal range), key numbers table, news list with sources, disclaimer.

**Headlines are templated, not AI-written** (free, and cannot invent a cause): "Nvidia falls 15%, its biggest one-day drop since 2025", with the latest real news headline shown beneath, attributed to its source.

**Legal note on the look:** layout conventions (serif headlines, rules, pills) are free to use. The FT's name, logo, fonts and exact pink are not. A different paper tone, different fonts and an original masthead keep this clearly its own design.

---

## 12. Phases

Effort assumes evenings and weekends around A-levels, with Claude Code writing the code and you testing and deciding.

### Phase 0 — Local prototype (end-of-day, your watchlist)
- **Goal:** a page on your Mac showing how your watchlist stocks moved today and which ones breached your thresholds.
- **Tasks:**
  1. Create accounts: GitHub, Alpaca (paper account, no deposit), Finnhub.
  2. **Verification spike:** confirm every "(verify)" item in section 3 with real API calls; confirm web push reaches your iPhone from a throwaway test page.
  3. Download 5 years of daily bars to Parquet. Build the provider interface.
  4. Write the rule module (% drop, z-score) with tests on known days: Nvidia's −17% day (27 Jan 2025), Meta's −26% results day (3 Feb 2022), Nvidia's 10-for-1 split (10 Jun 2024, must *not* alert), a pence/pounds UK case.
  5. Generate a simple local page from a watchlist file.
- **Tech:** Python, DuckDB, Parquet, pytest.
- **Effort:** 2 weekends. **Cost:** £0.
- **Done when:** one command prints today's watchlist drops and all rule tests pass.
- **Could go wrong:** a free tier does not allow what this plan assumes (the spike catches it early; fallbacks are Massive at ~$29 or yfinance for US); Python setup friction on the Mac.

### Phase 1 — Whole-market scan + push to your phone (delayed data)
- **Goal:** your iPhone buzzes when a large US stock drops sharply, about 15-20 minutes behind the market, plus a UK check after the London close.
- **Tasks:**
  1. **Backtester first.** Tune thresholds until alert volume is sane (section 7).
  2. Supabase project: tables from section 8.2, row-level security, your single login.
  3. Nightly ingest job (bars, splits, company list, stats).
  4. Scanner on a 5-minute GitHub Actions timer in US hours; UK job at 16:45.
  5. Verify + enrich step (splits, halts, bad ticks, news, key numbers).
  6. Dispatcher: dedupe, cooldown, cap, web push, Telegram backup, evening digest.
  7. Bare-bones PWA: log in, enable notifications, list of alerts, edit watchlist.
  8. Heartbeat monitoring.
- **Tech:** Python, GitHub Actions, Supabase, pywebpush, React + Vite PWA, Cloudflare Pages.
- **Effort:** 3-4 weekends. **Cost:** £0.
- **Done when:** a real alert arrives on your phone with news, z-score and key numbers, and a week passes with no false alert from a split or bad tick.
- **Could go wrong:** GitHub's timer runs late or skips (acceptable here, fixed in Phase 3); iOS drops the push subscription (Telegram backup covers it); too many or too few alerts (backtest again); Supabase pauses a free project after 7 idle days (the scheduled jobs keep it active).

### Phase 2 — The newspaper UI
- **Goal:** the full front page from section 11, on phone and MacBook.
- **Tasks:** design tokens and fonts; ticker strip; masthead and nav; lead story, watchlist column, card grid; tags; story page with chart; search; settings (thresholds, caps, quiet hours, digest); disclaimer footer; phone layout and Home Screen icon.
- **Tech:** React, CSS grid, a lightweight chart library, self-hosted fonts.
- **Effort:** 3 weekends. **Cost:** £0 (optional domain ~£10/yr).
- **Done when:** the home screen reads as a front page on a day with real alerts *and* looks deliberate on a quiet day with none.
- **Could go wrong:** quiet days leave the page empty (design a "calm markets" edition: smallest falls, watchlist summary); the design drifts too close to the FT (review against section 11 before calling it done).

### Phase 3 — Near-real-time
- **Goal:** alerts within 1-2 minutes of a move, still for £0.
- **Tasks:**
  1. Move the scanner to an always-on worker running a 1-minute loop.
  2. Whole market: poll Alpaca IEX real-time snapshots; tag UNCONFIRMED until delayed full-market data agrees.
  3. Watchlist: live websocket stream for up to 30 symbols.
  4. Add the intraday-from-high rule and halt handling; pre-market cards.
  5. Live updates on the front page (LIVE tag, auto-refresh).
- **Tech:** Python worker under a process manager, free cloud VM, Supabase Realtime or polling.
- **Effort:** 2-3 weekends. **Cost:** £0 on a free VM; about £4/mo if you choose a small paid server instead; $99/mo only if you later want true full-market real-time.
- **Done when:** on a real drop, your alert beats a mainstream finance app's delayed quote.
- **Could go wrong:** free VMs are fiddly to set up and can be reclaimed (fallback: stay on GitHub Actions, or the £4 server); IEX prices for quieter stocks are stale, causing missed or false alerts (the UNCONFIRMED tag and size filter limit this); more speed means more noise (re-run the backtest on minute data).

### Phase 4 — Accounts + portfolios
- **Goal:** proper multi-user sign-in, and a portfolio section with holdings, transactions and profit/loss. Still invite-only.
- **Tasks:** open sign-up behind an invite code; per-user settings; data export and delete; portfolio tables from section 8.2; add/edit transactions; holdings and P&L calculated from the ledger in GBP and USD; a HOLDING tag on alerts for stocks you own; security tests for row-level rules.
- **Tech:** Supabase Auth and RLS, Postgres views, daily FX rate (free ECB data).
- **Effort:** 5-6 weekends. **Cost:** £0.
- **Done when:** two test accounts cannot see each other's data, and a hand-checked portfolio matches the app's P&L to the penny.
- **Could go wrong:** P&L mistakes around splits, dividends and currency (test against hand-worked examples); tax questions creep in (out of scope: no capital-gains or ISA calculations); letting friends in before data licences allow it (section 3.3).

### Phase 5 — Public launch
- **Goal:** anyone can sign up, legally and safely.
- **Tasks:**
  1. Get commercial data-licence quotes and switch provider adapters.
  2. Legal review of wording, terms and privacy policy; ICO registration.
  3. Decide web-only vs App Store (Capacitor wrap + Apple account).
  4. Rate limiting, abuse protection, error tracking, backups, a status page.
  5. Onboarding, landing page, support email.
  6. If charging: company set-up, payments, subscription rules, financial-promotion check.
- **Effort:** 4+ weekends of work, plus weeks of waiting on licences and reviews.
- **Cost:** see section 13.
- **Done when:** a stranger can sign up, get an accurate alert, and delete their account, and every data source is licensed for display.
- **Could go wrong:** licence costs exceed what a free app can carry (fallback: launch on end-of-day or 15-min delayed data only, or stay invite-only); App Store rejection of a thin web wrapper (stay web-only); regulatory worry about the concept itself (the legal review decides this before you spend on anything else).

---

## 13. Running costs by phase

| Phase | Monthly | One-off / yearly | Notes |
|---|---|---|---|
| 0 Local prototype | £0 | £0 | Runs on your Mac |
| 1 Scan + push | £0 | £0 | GitHub Actions, Supabase, Cloudflare free tiers |
| 2 Newspaper UI | £0 | Domain ~£10/yr (optional) | |
| 3 Near-real-time | £0 | £0 | Free VM. Optional: £4/mo server; $99/mo full real-time |
| 4 Accounts + portfolios | £0 | £0 | Free tier covers thousands of users |
| 5 Public launch | Data licence £50-£500+ (quotes needed); database ~£20 once you outgrow free | Apple £79/yr (App Store only); ICO ~£52/yr; domain ~£10/yr; legal review ~£500+ (optional but wise) | Data licensing decides whether launch is affordable |

---

## 14. Open decisions (with my recommendation)

| # | Decision | Recommendation |
|---|---|---|
| 1 | App name | **Decided: StocksWatch.** Only open point is a domain and trademark check before public launch |
| 2 | Client type | **PWA now.** Revisit App Store at Phase 5 |
| 3 | Stack | **Python + Supabase + React PWA on Cloudflare Pages** as in section 8 |
| 4 | Public or private GitHub repo | **Public.** Unlimited free scheduled runs, and a visible project for university applications. Secrets stay in GitHub Secrets |
| 5 | US data source | **Alpaca free**, with Massive (~$29/mo) as the fallback if the Phase 0 spike fails |
| 6 | UK data source | **yfinance** for FTSE 350 end-of-day, personal use only. Move to EODHD ($19.99/mo) if it proves unreliable |
| 7 | Starting thresholds | Section 4 defaults, then **let the backtest decide** before switching notifications on |
| 8 | Headlines | **Templates.** Revisit AI-written summaries only when there is budget and a legal view |
| 9 | Pre/after-market alerts | **Off.** Front-page cards only, from Phase 3 |
| 10 | Backup notification channel | **Yes, Telegram bot** from Phase 1 |
| 11 | Phase 3 hosting | **Try a free cloud VM**; accept £4/mo for a small server if it wastes more than a weekend |
| 12 | Friends before launch | **No**, until a provider confirms in writing or you hold a commercial licence |
| 13 | Business model | **Decide at Phase 5.** Until then: no ads, no broker links, no affiliate deals |
| 14 | Legal review | **Yes, before any public sign-ups**, even for a free app |

---

## 15. Sources checked (15 Nov 2026)

- Alpaca market data plans: https://docs.alpaca.markets/docs/about-market-data-api
- Massive (formerly Polygon.io) pricing: https://massive.com/pricing and https://massive.com/compare/massive-vs-alpaca
- EODHD plans: https://eodhd.com/help/plans
- Free stock API comparisons: https://qveris.ai/guides/stock-api-free-comparison/ and https://blog.apilayer.com/analyzing-the-top-free-apis-for-stock-data/
- iOS web push: https://firt.dev/notes/pwa-ios/ and https://www.mobiloud.com/blog/pwa-push-notifications
- FCA perimeter guidance on advice: https://handbook.fca.org.uk/handbook/PERG/8/24.html and https://handbook.fca.org.uk/handbook/PERG/8/26.html
- Supabase free-tier limits: https://www.itpathsolutions.com/supabase-free-tier-limits
