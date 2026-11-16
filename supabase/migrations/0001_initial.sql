-- StocksWatch database, version 1 (PLAN.md section 8.2).
--
-- Two kinds of table:
--   MARKET tables  facts about stocks. Written only by the Python jobs.
--                  Any signed-in user may read them; nobody else can.
--   USER tables    belong to one person. Row-level security (RLS) means the
--                  database itself refuses to show or change another user's rows.
--
-- Safe to run more than once.

-- ============================================================================
-- MARKET TABLES
-- ============================================================================

create table if not exists public.instruments (
  id          bigint generated always as identity primary key,  -- our own id: tickers change
  symbol      text not null,
  market      text not null check (market in ('US', 'UK')),
  exchange    text,
  name        text,
  currency    text,
  price_unit  text not null default 'USD' check (price_unit in ('USD', 'GBP', 'GBX')),
  sector      text,
  type        text,
  is_active   boolean not null default true,
  unique (symbol, market)
);

create table if not exists public.instrument_stats (
  instrument_id      bigint primary key references public.instruments (id) on delete cascade,
  as_of              date not null,          -- last trading day included
  prev_close         numeric,
  sigma_60d          numeric,                -- normal daily move, as a fraction
  avg_volume_20d     numeric,
  dollar_volume_20d  numeric,                -- average money traded per day
  high_52w           numeric,
  low_52w            numeric,
  market_cap         numeric,
  pe_ratio           numeric,
  updated_at         timestamptz not null default now()
);

create table if not exists public.corporate_actions (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references public.instruments (id) on delete cascade,
  ex_date        date not null,
  type           text not null,              -- split, dividend, spin_off ...
  ratio          numeric,                    -- 10 for a 10-for-1 split
  amount         numeric,                    -- cash per share for a dividend
  unique (instrument_id, ex_date, type)
);

create table if not exists public.rules (
  id          bigint generated always as identity primary key,
  name        text not null,
  version     integer not null default 1,
  params      jsonb not null,
  created_at  timestamptz not null default now(),
  unique (name, version)
);

create table if not exists public.scan_runs (
  id               bigint generated always as identity primary key,
  market           text not null,
  source           text not null,            -- e.g. alpaca delayed_sip
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  symbols_scanned  integer,
  alerts_found     integer,
  status           text not null default 'running' check (status in ('running', 'ok', 'failed')),
  note             text
);

-- An alert is a FACT ABOUT A STOCK. It has no user. (Deliveries are in "notifications".)
create table if not exists public.alerts (
  id             bigint generated always as identity primary key,
  instrument_id  bigint not null references public.instruments (id) on delete cascade,
  trading_date   date not null,
  rule_id        bigint references public.rules (id),
  tier           text check (tier in ('Notable', 'Major', 'Severe')),
  status         text not null default 'pending'
                 check (status in ('pending', 'confirmed', 'held')),  -- pending = seen on one scan only
  held_reason    text,
  scans_seen     integer not null default 1,
  triggered_at   timestamptz not null default now(),
  confirmed_at   timestamptz,
  price          numeric,
  pct_change     numeric,
  z_score        numeric,
  rel_volume     numeric,
  vs_index       numeric,
  dollar_volume  numeric,
  push_eligible  boolean not null default false,
  tags           text[] not null default '{}',
  headline       text,
  news           jsonb,
  data_delay     text,
  unique (instrument_id, trading_date, tier)   -- one alert per stock, per day, per tier
);
create index if not exists alerts_by_date on public.alerts (trading_date desc, status);

-- Sell-off mode: one row for a market-wide fall, instead of hundreds of alerts.
create table if not exists public.market_events (
  id            bigint generated always as identity primary key,
  market        text not null,
  trading_date  date not null,
  index_pct     numeric,
  alert_count   integer,
  created_at    timestamptz not null default now(),
  unique (market, trading_date)
);

-- ============================================================================
-- USER TABLES
-- ============================================================================

create table if not exists public.profiles (
  user_id              uuid primary key references auth.users (id) on delete cascade,
  timezone             text not null default 'Europe/London',
  daily_cap_market     integer not null default 5,
  daily_cap_watchlist  integer not null default 10,
  quiet_start          time not null default '22:00',
  quiet_end            time not null default '07:00',
  digest_mode          text not null default 'both' check (digest_mode in ('live', 'digest', 'both')),
  created_at           timestamptz not null default now()
);

create table if not exists public.watchlists (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name        text not null default 'My watchlist',
  created_at  timestamptz not null default now()
);

create table if not exists public.watchlist_items (
  id             bigint generated always as identity primary key,
  watchlist_id   bigint not null references public.watchlists (id) on delete cascade,
  instrument_id  bigint not null references public.instruments (id) on delete cascade,
  threshold_pct  numeric not null default -4,
  threshold_z    numeric not null default -2.5,
  enabled        boolean not null default true,
  unique (watchlist_id, instrument_id)
);

create table if not exists public.push_subscriptions (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  endpoint    text not null unique,
  keys        jsonb not null,
  created_at  timestamptz not null default now(),
  last_ok_at  timestamptz
);

-- A notification is ONE DELIVERY TO ONE USER. Caps and cooldowns count these.
create table if not exists public.notifications (
  id               bigint generated always as identity primary key,
  user_id          uuid not null references auth.users (id) on delete cascade,
  alert_id         bigint references public.alerts (id) on delete cascade,
  market_event_id  bigint references public.market_events (id) on delete cascade,
  kind             text not null check (kind in ('market', 'watchlist', 'sell_off', 'digest', 'test')),
  channel          text not null check (channel in ('web_push', 'telegram')),
  status           text not null check (status in ('sent', 'failed', 'skipped')),
  detail           text,
  sent_at          timestamptz not null default now()
);
create index if not exists notifications_by_user on public.notifications (user_id, sent_at desc);

-- ============================================================================
-- SECURITY
-- ============================================================================

-- RLS on for every table. With RLS on and no policy, nobody but the Python
-- jobs (which use the secret key) can touch a table.
alter table public.instruments        enable row level security;
alter table public.instrument_stats   enable row level security;
alter table public.corporate_actions  enable row level security;
alter table public.rules              enable row level security;
alter table public.scan_runs          enable row level security;
alter table public.alerts             enable row level security;
alter table public.market_events      enable row level security;
alter table public.profiles           enable row level security;
alter table public.watchlists         enable row level security;
alter table public.watchlist_items    enable row level security;
alter table public.push_subscriptions enable row level security;
alter table public.notifications      enable row level security;

-- The Python jobs (secret key) may do everything.
grant all on all tables in schema public to service_role;

-- Signed-in users: read-only on market tables. Visitors who are not signed in get nothing.
grant select on public.instruments, public.instrument_stats, public.corporate_actions,
                public.rules, public.scan_runs, public.alerts, public.market_events
  to authenticated;

-- Signed-in users: their own rows in user tables (which rows is decided by the policies below).
grant select, update on public.profiles to authenticated;
grant select, insert, update, delete on public.watchlists, public.watchlist_items,
                                        public.push_subscriptions to authenticated;
grant select on public.notifications to authenticated;

-- Policies: market tables are readable by any signed-in user.
drop policy if exists "signed-in users can read" on public.instruments;
create policy "signed-in users can read" on public.instruments for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.instrument_stats;
create policy "signed-in users can read" on public.instrument_stats for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.corporate_actions;
create policy "signed-in users can read" on public.corporate_actions for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.rules;
create policy "signed-in users can read" on public.rules for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.scan_runs;
create policy "signed-in users can read" on public.scan_runs for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.alerts;
create policy "signed-in users can read" on public.alerts for select to authenticated using (true);
drop policy if exists "signed-in users can read" on public.market_events;
create policy "signed-in users can read" on public.market_events for select to authenticated using (true);

-- Policies: user tables. "auth.uid()" is the id of whoever is signed in.
drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

drop policy if exists "own watchlists" on public.watchlists;
create policy "own watchlists" on public.watchlists for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

drop policy if exists "items in own watchlists" on public.watchlist_items;
create policy "items in own watchlists" on public.watchlist_items for all to authenticated
  using (exists (select 1 from public.watchlists w
                 where w.id = watchlist_id and w.user_id = (select auth.uid())))
  with check (exists (select 1 from public.watchlists w
                      where w.id = watchlist_id and w.user_id = (select auth.uid())));

drop policy if exists "own push subscriptions" on public.push_subscriptions;
create policy "own push subscriptions" on public.push_subscriptions for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

drop policy if exists "own notifications" on public.notifications;
create policy "own notifications" on public.notifications for select to authenticated
  using (user_id = (select auth.uid()));

-- ============================================================================
-- NEW USERS
-- ============================================================================

-- When someone signs up, give them a profile and an empty watchlist.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id) values (new.id) on conflict do nothing;
  insert into public.watchlists (user_id) values (new.id);
  return new;
end;
$$;

revoke execute on function public.handle_new_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
