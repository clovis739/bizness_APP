-- ============================================================
-- BizNess OS — business_profile_v2 Migration
-- Run this ONCE in your Supabase SQL editor.
-- Does NOT alter or touch the existing business_profile table.
-- ============================================================

create extension if not exists pgcrypto;

create table if not exists public.business_profile_v2 (
    id                       uuid primary key default gen_random_uuid(),
    business_id              uuid not null references public.business(business_id) on delete cascade,

    -- Fields carried over from V1
    region                   text not null,
    sector                   text not null,
    startup_capital_cfa      numeric(15,2) not null default 0,
    employees                integer not null default 1,
    years_of_experience      integer not null default 0,
    transport_cost_percentage numeric(5,2) not null default 0,
    energy_cost_percentage   numeric(5,2) not null default 0,

    -- New V3 fields
    year_started             integer not null default 2020,
    has_business_plan        boolean not null default false,
    formal_financial_records boolean not null default false,
    registered_formal        boolean not null default false,
    owner_education_level    text not null default 'Secondary',
    competition_level        text not null default 'Medium',
    access_to_financing      text not null default 'No',
    financing_method         text not null default 'Own Resources',
    owner_hours_per_week     integer not null default 40,
    business_type            text not null default 'Sole Proprietorship',

    created_at               timestamptz not null default timezone('utc', now()),
    updated_at               timestamptz not null default timezone('utc', now())
);

-- Unique constraint: one V2 profile per business
create unique index if not exists business_profile_v2_business_id_idx
    on public.business_profile_v2 (business_id);

-- Index for fast lookup
create index if not exists business_profile_v2_region_sector_idx
    on public.business_profile_v2 (region, sector);

-- Auto-update updated_at on every row change
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists set_business_profile_v2_updated_at on public.business_profile_v2;
create trigger set_business_profile_v2_updated_at
    before update on public.business_profile_v2
    for each row execute function public.set_updated_at();

-- Enable RLS
alter table public.business_profile_v2 enable row level security;

-- Policy: authenticated users can only read/write their own business profile
create policy "Users manage their own v2 profile"
    on public.business_profile_v2
    for all
    using (
        business_id in (
            select b.business_id
            from public.business b
            join public.owner o on o.owner_id = b.owner_id
            join public.sme s on s.sme_id = o.sme_id
            where s.sme_id::text = auth.uid()::text
        )
    );

-- Allow service role full access (for backend API calls)
create policy "Service role full access v2"
    on public.business_profile_v2
    for all
    to service_role
    using (true)
    with check (true);
