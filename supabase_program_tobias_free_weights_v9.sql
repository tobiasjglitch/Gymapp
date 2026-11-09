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
  ('Enarms hantelrodd med stöd mot bänk'),
  ('Cable cross')
on conflict (name) do nothing;

-- Replace Tobias active Pass 3 without touching saved workout history.
update public.program_exercises pe
set active = false
from public.profiles p
where pe.profile_id = p.id
  and p.name = 'Tobias'
  and pe.day_name = 'Pass 3';

with program(exercise_name, sort_order, sets, rep_min, rep_max, weight_step_kg) as (
  values
    ('Hantelpress plan bänk',                    1, 4,  6, 10, 2.5::numeric),
    ('Enarms hantelrodd med stöd mot bänk',      2, 3,  8, 12, 2.5::numeric),
    ('Sidolyft hantlar',                         3, 3, 12, 20, 2.5::numeric),
    ('Cable cross',                              4, 3, 10, 15, 2.5::numeric)
)
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
  'Pass 3',
  e.id,
  program.sort_order,
  program.sets,
  program.rep_min,
  program.rep_max,
  program.weight_step_kg,
  true
from public.profiles p
cross join program
join public.exercises e on e.name = program.exercise_name
where p.name = 'Tobias'
on conflict (profile_id, day_name, exercise_id) do update set
  sort_order = excluded.sort_order,
  sets = excluded.sets,
  rep_min = excluded.rep_min,
  rep_max = excluded.rep_max,
  weight_step_kg = excluded.weight_step_kg,
  active = true;

commit;
