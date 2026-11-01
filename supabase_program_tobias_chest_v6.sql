begin;

do $$
begin
  if (select count(*) from public.profiles where name = 'Tobias') <> 1 then
    raise exception 'Expected exactly one Tobias profile';
  end if;
end;
$$;

with program(day_name, exercise_name, sort_order, sets, rep_min, rep_max, weight_step_kg) as (
  values
    ('Pass 1', 'Lutande hantelpress',                 1, 4,  6, 10, 2.5::numeric),
    ('Pass 1', 'Kabel-flyes',                        2, 3, 10, 15, 2.5::numeric),
    ('Pass 1', 'Bröststödd roddmaskin',              3, 3,  8, 12, 2.5::numeric),
    ('Pass 1', 'Sidolyft hantlar',                   4, 3, 12, 20, 2.5::numeric),

    ('Pass 2', 'Kabel-flyes',                        1, 2, 12, 15, 2.5::numeric),
    ('Pass 2', 'Benpress',                           2, 3,  8, 12, 2.5::numeric),
    ('Pass 2', 'Sittande lårcurl',                   3, 3, 10, 15, 2.5::numeric),
    ('Pass 2', 'Benspark',                           4, 2, 10, 15, 2.5::numeric),
    ('Pass 2', 'Kabel-crunch',                       5, 2, 10, 15, 2.5::numeric),

    ('Pass 3', 'Hantelpress plan bänk',              1, 3,  6, 10, 2.5::numeric),
    ('Pass 3', 'Bröstpressmaskin',                   2, 3,  8, 12, 2.5::numeric),
    ('Pass 3', 'Sidolyft i kabel',                   3, 3, 12, 20, 2.5::numeric),
    ('Pass 3', 'Omvänd pec deck - bakre axlar',      4, 2, 12, 20, 2.5::numeric),
    ('Pass 3', 'Bicepscurl i kabel eller maskin',    5, 2,  8, 12, 2.5::numeric),

    ('Pass 4', 'Latsdrag, neutralt grepp',            1, 3,  8, 12, 2.5::numeric),
    ('Pass 4', 'Sittande roddmaskin',                2, 3,  8, 12, 2.5::numeric),
    ('Pass 4', 'Sittande lårcurl',                   3, 3, 10, 15, 2.5::numeric),
    ('Pass 4', 'Triceps pushdown',                   4, 2, 10, 15, 2.5::numeric),
    ('Pass 4', 'Vadpress i maskin',                  5, 2, 10, 15, 2.5::numeric)
)
insert into public.exercises(name)
select distinct exercise_name
from program
on conflict (name) do nothing;

update public.program_exercises
set active = false
where profile_id = (select id from public.profiles where name = 'Tobias')
  and day_name in ('Pass 1', 'Pass 2', 'Pass 3', 'Pass 4');

with program(day_name, exercise_name, sort_order, sets, rep_min, rep_max, weight_step_kg) as (
  values
    ('Pass 1', 'Lutande hantelpress',                 1, 4,  6, 10, 2.5::numeric),
    ('Pass 1', 'Kabel-flyes',                        2, 3, 10, 15, 2.5::numeric),
    ('Pass 1', 'Bröststödd roddmaskin',              3, 3,  8, 12, 2.5::numeric),
    ('Pass 1', 'Sidolyft hantlar',                   4, 3, 12, 20, 2.5::numeric),
    ('Pass 2', 'Kabel-flyes',                        1, 2, 12, 15, 2.5::numeric),
    ('Pass 2', 'Benpress',                           2, 3,  8, 12, 2.5::numeric),
    ('Pass 2', 'Sittande lårcurl',                   3, 3, 10, 15, 2.5::numeric),
    ('Pass 2', 'Benspark',                           4, 2, 10, 15, 2.5::numeric),
    ('Pass 2', 'Kabel-crunch',                       5, 2, 10, 15, 2.5::numeric),
    ('Pass 3', 'Hantelpress plan bänk',              1, 3,  6, 10, 2.5::numeric),
    ('Pass 3', 'Bröstpressmaskin',                   2, 3,  8, 12, 2.5::numeric),
    ('Pass 3', 'Sidolyft i kabel',                   3, 3, 12, 20, 2.5::numeric),
    ('Pass 3', 'Omvänd pec deck - bakre axlar',      4, 2, 12, 20, 2.5::numeric),
    ('Pass 3', 'Bicepscurl i kabel eller maskin',    5, 2,  8, 12, 2.5::numeric),
    ('Pass 4', 'Latsdrag, neutralt grepp',            1, 3,  8, 12, 2.5::numeric),
    ('Pass 4', 'Sittande roddmaskin',                2, 3,  8, 12, 2.5::numeric),
    ('Pass 4', 'Sittande lårcurl',                   3, 3, 10, 15, 2.5::numeric),
    ('Pass 4', 'Triceps pushdown',                   4, 2, 10, 15, 2.5::numeric),
    ('Pass 4', 'Vadpress i maskin',                  5, 2, 10, 15, 2.5::numeric)
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
  program.day_name,
  e.id,
  program.sort_order,
  program.sets,
  program.rep_min,
  program.rep_max,
  program.weight_step_kg,
  true
from program
cross join public.profiles p
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
