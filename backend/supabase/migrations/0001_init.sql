-- Migración 0001: estructura principal (Supabase / PostgreSQL)
-- Extras útiles: extensiones necesarias
create extension if not exists "uuid-ossp";

-- =============== personas, roles y permisos ===============

create table if not exists people (
  id uuid primary key default uuid_generate_v4(),
  full_name text not null,
  document_id text unique,
  status text not null default 'active'
    check (status in ('active','suspended','revoked')),
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists roles (
  id integer primary key,
  name text not null unique,
  description text
);

create table if not exists permissions (
  id integer primary key,
  code text not null unique,
  description text
);

create table if not exists role_permissions (
  role_id integer not null references roles(id) on delete cascade,
  permission_id integer not null references permissions(id) on delete cascade,
  primary key (role_id, permission_id)
);

create table if not exists person_roles (
  person_id uuid not null references people(id) on delete cascade,
  role_id integer not null references roles(id) on delete cascade,
  primary key (person_id, role_id)
);

-- =============== dispositivos y eventos ===============

create table if not exists devices (
  id text primary key,                       -- el propio Pi genera su id estable
  name text not null default 'raspberry-pi-5',
  status text not null default 'online' check (status in ('online','offline','testing')),
  last_seen timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists access_events (
  event_id uuid primary key,                 -- generado en la Pi; evita duplicados en sync
  person_id uuid references people(id) on delete set null,
  device_id text not null references devices(id),
  result text not null check (result in ('granted','denied')),
  reason text not null,
  category text,
  timestamp timestamptz not null,
  confidence real,                           -- distancia LBPH (no probabilidad)
  created_at timestamptz not null default now()
);
create index if not exists idx_events_time on access_events (timestamp desc);
create index if not exists idx_events_person on access_events (person_id);

-- =============== cuentas administrativas (Supabase Auth) ===============

create table if not exists admin_accounts (
  auth_user_id uuid primary key references auth.users(id) on delete cascade,
  username text,
  role text not null default 'admin' check (role in ('admin','viewer')),
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);

-- Único mecanismo para bootstrap del primer admin (se llama desde SQL Editor
-- DESPUÉS de crear el usuario en Auth, sin exponer service_role al cliente):
create or replace function bootstrap_first_admin(target_auth_user_id uuid)
returns void
language sql
security definer
set search_path = public
as $$
  -- solo funciona si aún no existe ningún administrador habilitado
  insert into admin_accounts (auth_user_id, role, enabled)
  select target_auth_user_id, 'admin', true
  where not exists (select 1 from admin_accounts where role = 'admin' and enabled);
$$;

-- updated_at automático para people
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_people_updated_at on people;
create trigger trg_people_updated_at before update on people
for each row execute function set_updated_at();
