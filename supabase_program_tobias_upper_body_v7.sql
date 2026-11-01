begin;

do $$
begin
  if (select count(*) from public.profiles where name = 'Tobias') <> 1 then
    raise exception 'Expected exactly one Tobias profile';
  end if;
end;
$$;

insert into public.exercises(name)
values ('Bröststödd high row')
on conflict (name) do nothing;

-- Replace the small chest booster with more upper-back work.
update public.program_exercises pe
set active = false
from public.profiles p, public.exercises e
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 2'
  and e.name = 'Kabel-flyes';

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
  1,
  3,
  8,
  12,
  2.5,
  true
from public.profiles p
cross join public.exercises e
where p.name = 'Tobias'
  and e.name = 'Bröststödd high row'
on conflict (profile_id, day_name, exercise_id) do update set
  sort_order = excluded.sort_order,
  sets = excluded.sets,
  rep_min = excluded.rep_min,
  rep_max = excluded.rep_max,
  weight_step_kg = excluded.weight_step_kg,
  active = true;

-- Preserve the remaining Pass 2 order after the replacement.
update public.program_exercises pe
set sort_order = ordering.sort_order
from public.profiles p,
     public.exercises e,
     (values
       ('Benpress', 2),
       ('Sittande lårcurl', 3),
       ('Benspark', 4),
       ('Kabel-crunch', 5)
     ) as ordering(exercise_name, sort_order)
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 2'
  and e.name = ordering.exercise_name;

-- Shift direct shoulder volume toward side and rear delts.
update public.program_exercises pe
set sets = targets.sets
from public.profiles p,
     public.exercises e,
     (values
       ('Pass 1', 'Sidolyft hantlar', 4),
       ('Pass 3', 'Sidolyft i kabel', 4),
       ('Pass 3', 'Omvänd pec deck - bakre axlar', 3)
     ) as targets(day_name, exercise_name, sets)
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = targets.day_name
  and e.name = targets.exercise_name;

-- Biceps still receives indirect work; this keeps Pass 3 within 40 minutes.
update public.program_exercises pe
set active = false
from public.profiles p, public.exercises e
where pe.profile_id = p.id
  and pe.exercise_id = e.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 3'
  and e.name = 'Bicepscurl i kabel eller maskin';

commit;
