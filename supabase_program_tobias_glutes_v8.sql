begin;

do $$
begin
  if (select count(*) from public.profiles where name = 'Tobias') <> 1 then
    raise exception 'Expected exactly one Tobias profile';
  end if;
end;
$$;

insert into public.exercises(name)
values
  ('Hip thrust-maskin/Smith'),
  ('Höftabduktion i kabel/maskin')
on conflict (name) do nothing;

-- Replace only the two selected exercises in Tobias program. Existing workout
-- history remains linked to the old exercises and is never changed or deleted.
update public.program_exercises pe
set active = false
from public.profiles p, public.exercises e
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 2'
  and e.name = 'Benspark';

update public.program_exercises pe
set active = false
from public.profiles p, public.exercises e
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 4'
  and e.name = 'Vadpress i maskin';

insert into public.program_exercises(
  profile_id,
  day_name,
  exercise_id,
  sort_order,
  sets,
  rep_min,
  rep_max,
  weight_step_kg,
  active
)
select
  p.id,
  'Pass 2',
  e.id,
  2,
  4,
  8,
  12,
  5.0,
  true
from public.profiles p
cross join public.exercises e
where p.name = 'Tobias'
  and e.name = 'Hip thrust-maskin/Smith'
on conflict (profile_id, day_name, exercise_id) do update set
  sort_order = excluded.sort_order,
  sets = excluded.sets,
  rep_min = excluded.rep_min,
  rep_max = excluded.rep_max,
  weight_step_kg = excluded.weight_step_kg,
  active = true;

-- Put the main glute lift before the remaining leg work.
update public.program_exercises pe
set sort_order = ordering.sort_order
from public.profiles p,
     public.exercises e,
     (values
       ('Bröststödd high row', 1),
       ('Benpress', 3),
       ('Sittande lårcurl', 4),
       ('Kabel-crunch', 5)
     ) as ordering(exercise_name, sort_order)
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 2'
  and e.name = ordering.exercise_name;

insert into public.program_exercises(
  profile_id,
  day_name,
  exercise_id,
  sort_order,
  sets,
  rep_min,
  rep_max,
  weight_step_kg,
  active
)
select
  p.id,
  'Pass 4',
  e.id,
  5,
  3,
  12,
  20,
  2.5,
  true
from public.profiles p
cross join public.exercises e
where p.name = 'Tobias'
  and e.name = 'Höftabduktion i kabel/maskin'
on conflict (profile_id, day_name, exercise_id) do update set
  sort_order = excluded.sort_order,
  sets = excluded.sets,
  rep_min = excluded.rep_min,
  rep_max = excluded.rep_max,
  weight_step_kg = excluded.weight_step_kg,
  active = true;

commit;
