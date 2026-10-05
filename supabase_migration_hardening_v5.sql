begin;

alter table public.program_exercises
  add column if not exists weight_step_kg numeric not null default 2.5
  check (weight_step_kg between 0.5 and 20);

update public.program_exercises pe
set weight_step_kg = 5
from public.exercises e
where e.id = pe.exercise_id
  and lower(e.name) in ('knäböj', 'frontböj', 'marklyft', 'raka marklyft')
  and pe.weight_step_kg = 2.5;

alter table public.workouts
  add column if not exists client_token text;

create unique index if not exists workouts_client_token_idx
  on public.workouts(client_token)
  where client_token is not null;

create table if not exists public.workout_drafts (
  profile_id bigint not null references public.profiles(id) on delete cascade,
  day_name text not null check (day_name in ('Pass 1', 'Pass 2', 'Pass 3', 'Pass 4')),
  workout_date date not null,
  notes text not null default '',
  payload jsonb not null default '[]'::jsonb check (jsonb_typeof(payload) = 'array'),
  updated_at timestamp with time zone not null default now(),
  primary key(profile_id, day_name)
);

create or replace function public.save_workout_atomic(
  p_profile_id bigint,
  p_workout_date date,
  p_day_name text,
  p_notes text,
  p_sets jsonb,
  p_client_token text
) returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  new_workout_id bigint;
begin
  if not exists (select 1 from public.profiles where id = p_profile_id) then
    raise exception 'Profile not found';
  end if;

  if p_day_name not in ('Pass 1', 'Pass 2', 'Pass 3', 'Pass 4') then
    raise exception 'Invalid workout day';
  end if;

  if p_client_token is null or char_length(p_client_token) < 16 then
    raise exception 'Invalid client token';
  end if;

  if jsonb_typeof(p_sets) <> 'array' or jsonb_array_length(p_sets) = 0 then
    raise exception 'At least one set is required';
  end if;

  if exists (
    select 1
    from jsonb_array_elements(p_sets) as item
    where (item->>'set_no')::integer < 1
       or (item->>'reps')::integer < 0
       or (item->>'weight_kg')::numeric < 0
  ) then
    raise exception 'Invalid set values';
  end if;

  select id into new_workout_id
  from public.workouts
  where client_token = p_client_token;

  if new_workout_id is not null then
    return new_workout_id;
  end if;

  insert into public.workouts(
    profile_id, workout_date, day_name, notes, client_token
  )
  values (
    p_profile_id, p_workout_date, p_day_name, coalesce(p_notes, ''), p_client_token
  )
  on conflict (client_token) where client_token is not null do nothing
  returning id into new_workout_id;

  if new_workout_id is null then
    select id into new_workout_id
    from public.workouts
    where client_token = p_client_token;
    return new_workout_id;
  end if;

  insert into public.workout_sets
    (workout_id, exercise_id, set_no, reps, weight_kg, is_pr)
  select
    new_workout_id,
    (item->>'exercise_id')::bigint,
    (item->>'set_no')::integer,
    (item->>'reps')::integer,
    (item->>'weight_kg')::numeric,
    coalesce((item->>'is_pr')::boolean, false)
  from jsonb_array_elements(p_sets) as item;

  return new_workout_id;
end;
$$;

alter table public.profiles enable row level security;
alter table public.exercises enable row level security;
alter table public.program_exercises enable row level security;
alter table public.workouts enable row level security;
alter table public.workout_sets enable row level security;
alter table public.workout_drafts enable row level security;

revoke all on table public.profiles from anon, authenticated;
revoke all on table public.exercises from anon, authenticated;
revoke all on table public.program_exercises from anon, authenticated;
revoke all on table public.workouts from anon, authenticated;
revoke all on table public.workout_sets from anon, authenticated;
revoke all on table public.workout_drafts from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on function public.save_workout_atomic(bigint, date, text, text, jsonb, text)
  from public, anon, authenticated;
revoke all on function public.save_workout_atomic(bigint, date, text, text, jsonb)
  from public, anon, authenticated;

grant all on table public.profiles to service_role;
grant all on table public.exercises to service_role;
grant all on table public.program_exercises to service_role;
grant all on table public.workouts to service_role;
grant all on table public.workout_sets to service_role;
grant all on table public.workout_drafts to service_role;
grant usage, select on all sequences in schema public to service_role;
grant execute on function public.save_workout_atomic(bigint, date, text, text, jsonb, text)
  to service_role;
grant execute on function public.save_workout_atomic(bigint, date, text, text, jsonb)
  to service_role;

commit;
