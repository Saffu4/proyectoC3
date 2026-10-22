-- Migración 0003: datos semilla de roles y permisos (idénticos al local SQLite)

insert into roles (id, name, description) values
  (1, 'admin', 'Acceso administrativo total'),
  (2, 'user', 'Acceso autorizado estándar')
on conflict (id) do nothing;

insert into permissions (code, description) values
  ('access.granted', 'Puede pasar por el punto de acceso'),
  ('panel.admin', 'Acceso al panel de administración')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select 1, id from permissions where code in ('access.granted','panel.admin')
on conflict do nothing;

insert into role_permissions (role_id, permission_id)
select 2, id from permissions where code = 'access.granted'
on conflict do nothing;
