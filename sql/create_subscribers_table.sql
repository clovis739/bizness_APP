-- Stores newsletter subscriptions for the communication routes.
-- Apply this in the Supabase SQL editor before using
-- POST /api/v1/communication/subscribe and /broadcast.

create extension if not exists pgcrypto;

create table if not exists public.subscribers (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    status text not null default 'active',
    source text not null default 'mobile_app',
    created_at timestamptz not null default timezone('utc', now())
);

create index if not exists subscribers_email_idx
    on public.subscribers (email);
