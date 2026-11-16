-- StocksWatch database, version 2: what the front page needs beyond alerts.
--
--   quotes             the latest price and move for each scanned stock
--                      (watchlist column, "calm markets" edition, market pages)
--   market_indicators  the four figures in the top strip
--
-- Safe to run more than once.

create table if not exists public.quotes (
  instrument_id  bigint primary key references public.instruments (id) on delete cascade,
  trading_date   date not null,
  price          numeric not null,
  prev_close     numeric,
  pct_change     numeric,
  z_score        numeric,
  rel_volume     numeric,
  dollar_volume  numeric,                 -- average money traded per day
  eligible       boolean not null default false,   -- passes the price and liquidity filters
  updated_at     timestamptz not null default now()
);
create index if not exists quotes_by_move on public.quotes (trading_date desc, pct_change);

create table if not exists public.market_indicators (
  key         text primary key,           -- ftse100, sp500, gbpusd, brent
  label       text not null,
  value       numeric,
  pct_change  numeric,
  as_of       date,
  sort_order  integer not null default 0,
  updated_at  timestamptz not null default now()
);

alter table public.quotes            enable row level security;
alter table public.market_indicators enable row level security;

grant all on public.quotes, public.market_indicators to service_role;
grant select on public.quotes, public.market_indicators to authenticated;

drop policy if exists "signed-in users can read" on public.quotes;
create policy "signed-in users can read" on public.quotes for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.market_indicators;
create policy "signed-in users can read" on public.market_indicators for select to authenticated using (true);

-- Tell the API layer the new tables exist.
notify pgrst, 'reload schema';
