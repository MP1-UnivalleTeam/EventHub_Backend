-- Esquema base para el aislamiento por organizador.
-- La autenticación usa Supabase Auth (auth.users).
-- El backend obtiene el usuario desde el access token y guarda su UUID
-- en usuario_id; el frontend nunca debe enviar ese identificador.

alter table public.eventos
  add column if not exists usuario_id uuid;

alter table public.subtareas
  add column if not exists usuario_id uuid;

create index if not exists eventos_usuario_id_idx
  on public.eventos (usuario_id);

create index if not exists subtareas_usuario_id_idx
  on public.subtareas (usuario_id);

create index if not exists subtareas_evento_id_idx
  on public.subtareas (evento_id);

-- IMPORTANTE:
-- Antes de hacer NOT NULL, asigna usuario_id a los registros históricos.
-- Ejemplo (solo si corresponde a tu migración):
-- update public.eventos set usuario_id = '<UUID_DEL_ORGANIZADOR>';
-- update public.subtareas set usuario_id = '<UUID_DEL_ORGANIZADOR>';

-- Cuando todos los registros tengan propietario:
-- alter table public.eventos alter column usuario_id set not null;
-- alter table public.subtareas alter column usuario_id set not null;
