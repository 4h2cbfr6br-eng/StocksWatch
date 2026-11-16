-- StocksWatch database, version 3: what the price chart and the Sectors page need.
--
--   price_series    about a year of daily closing prices per stock, kept as two
--                   lists in one row (small, and replaced once a day)
--   sector_summary  a ready-made summary of today's moves by sector
--
-- Safe to run more than once.

create table if not exists public.price_series (
  instrument_id  bigint primary key references public.instruments (id) on delete cascade,
  dates          date[] not null,
  closes         numeric[] not null,
  updated_at     timestamptz not null default now()
);

alter table public.price_series enable row level security;
grant all on public.price_series to service_role;
grant select on public.price_series to authenticated;
drop policy if exists "signed-in users can read" on public.price_series;
create policy "signed-in users can read" on public.price_series for select to authenticated using (true);

-- "security_invoker" makes the view obey the same row rules as the tables under it.
create or replace view public.sector_summary with (security_invoker = true) as
select
  i.sector,
  max(q.trading_date)                                            as trading_date,
  count(*)::int                                                  as stocks,
  percentile_cont(0.5) within group (order by q.pct_change)      as median_pct,
  (count(*) filter (where q.pct_change <= -5))::int              as big_falls,
  (count(*) filter (where q.pct_change < 0))::int                as falling,
  min(q.pct_change)                                              as worst_pct,
  (array_agg(i.id order by q.pct_change))[1]                     as worst_id,
  (array_agg(i.name order by q.pct_change))[1]                   as worst_name
from public.quotes q
join public.instruments i on i.id = q.instrument_id
where q.eligible and i.market = 'US' and i.sector is not null and q.pct_change is not null
  and q.trading_date = (select max(q2.trading_date) from public.quotes q2 where q2.eligible)
group by i.sector;

grant select on public.sector_summary to authenticated, service_role;

-- Tell the API layer the new table and view exist.
notify pgrst, 'reload schema';
