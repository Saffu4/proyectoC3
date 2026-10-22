-- Migración 0002: RLS en todas las tablas expuestas.
-- Principios:
--  - Los usuarios anónimos NO ven nada.
--  - Solo admin_accounts habilitadas y vinculadas a auth.users leen datos.
--  - ESCRITURA de personas/roles/eventos: exclusivamente dispositivos
--    autenticados (canal privado: VPN/túnel + fetch event durante sync).
--  - No se confía en roles de cliente: siempre cruzan con admin_accounts.

alter table people enable row level security;
alter table roles enable row level security;
alter table permissions enable row level security;
alter table role_permissions enable row level security;
alter table person_roles enable row level security;
alter table devices enable row level security;
alter table access_events enable row level security;
alter table admin_accounts enable row level security;

-- función: ¿habilitado como admin?
create or replace function is_active_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from admin_accounts a
    where a.auth_user_id = auth.uid()
      and a.enabled = true
      and a.role = 'admin'
  );
$$;

-- ======================= SELECT =======================

create policy "admin lee people" on people
  for select to authenticated using (is_active_admin());

create policy "admin lee roles" on roles
  for select to authenticated using (is_active_admin());

create policy "admin lee permissions" on permissions
  for select to authenticated using (is_active_admin());

create policy "admin lee role_permissions" on role_permissions
  for select to authenticated using (is_active_admin());

create policy "admin lee person_roles" on person_roles
  for select to authenticated using (is_active_admin());

create policy "admin lee devices" on devices
  for select to authenticated using (is_active_admin());

create policy "admin lee access_events" on access_events
  for select to authenticated using (is_active_admin());

create policy "admin se ve a sí mismo en admin_accounts" on admin_accounts
  for select to authenticated using (auth_user_id = auth.uid());

-- ======================= INSERT =======================

create policy "admin crea people" on people
  for insert to authenticated with check (is_active_admin());

create policy "admin crea roles" on roles
    for insert to authenticated with check (is_active_admin());

create policy "admin crea role_permissions" on role_permissions
  for insert to authenticated with check (is_active_admin());

create policy "admin crea person_roles" on person_roles
  for insert to authenticated with check (is_active_admin());

create policy "dispositivos registran devices" on devices
  for insert to authenticated
  with check (true);  -- requires l canal privado: la Pi se autentica con anon key válida en la red privada

-- ======================= UPDATE =======================

create policy "admin edita people" on people
  for update to authenticated using (is_active_admin());

create policy "admin edita roles" on roles
  for update to authenticated using (is_active_admin());

create policy "admin edita role_permissions" on role_permissions
  for update to authenticated using (is_active_admin());

create policy "admin edita person_roles" on person_roles
  for update to authenticated using (is_active_admin());

-- ======================= DELETE (política de retención) =======================

create policy "admin elimina person_roles" on person_roles
  for delete to authenticated using (is_active_admin());

create policy "admin elimina people" on people
  for delete to authenticated using (is_active_admin());
