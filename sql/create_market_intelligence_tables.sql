-- BizSense market intelligence ingestion tables.
-- Run this once in Supabase SQL editor before using /api/v2/intelligence/refresh.

create table if not exists public.source_registry (
    id uuid primary key default gen_random_uuid(),
    source_name text not null,
    source_url text not null unique,
    source_type text not null default 'rss' check (source_type in ('rss', 'atom')),
    category text not null default 'market',
    country text not null default 'Cameroon',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.market_intelligence_items (
    id uuid primary key default gen_random_uuid(),
    external_id text not null unique,
    title text not null,
    summary text,
    source_name text not null,
    source_url text not null,
    original_url text not null,
    category text not null default 'market',
    industries text[] not null default array['General']::text[],
    regions text[] not null default array['Cameroon']::text[],
    country text not null default 'Cameroon',
    published_at timestamptz,
    fetched_at timestamptz not null default now(),
    credibility_score numeric(3,2) not null default 0.80,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_market_intelligence_category
    on public.market_intelligence_items(category);

create index if not exists idx_market_intelligence_published_at
    on public.market_intelligence_items(published_at desc nulls last);

create index if not exists idx_market_intelligence_industries
    on public.market_intelligence_items using gin(industries);

create index if not exists idx_market_intelligence_regions
    on public.market_intelligence_items using gin(regions);

insert into public.source_registry (source_name, source_url, source_type, category, country, is_active)
values
    ('Business in Cameroon', 'https://www.businessincameroon.com/index.php/component/obrss/fullrss', 'rss', 'business_news', 'Cameroon', true),
    ('Disrupt Africa', 'https://disruptafrica.com/feed/', 'rss', 'startup_news', 'Africa', true)
on conflict (source_url) do nothing;
