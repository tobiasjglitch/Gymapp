begin;

alter table public.program_exercises
  add column if not exists start_weight_kg numeric,
  add column if not exists start_reps jsonb;

update public.program_exercises pe
set
  start_weight_kg = values_to_apply.start_weight_kg,
  start_reps = values_to_apply.start_reps
from public.profiles p,
  (values
    ('Pass 1', 'Incline DB Press', 42.5::numeric, '[8, 8, 8, 8]'::jsonb),
    ('Pass 2', 'Pullups', 30::numeric, '[10, 6, 12, 6]'::jsonb),
    ('Pass 2', 'Chest Supported Rows', 25::numeric, '[12, 8, 8, 8]'::jsonb),
    ('Pass 2', 'Lat Pulldown', 55::numeric, '[8, 8, 8]'::jsonb),
    ('Pass 2', 'Face Pulls', 50::numeric, '[8, 10, 10]'::jsonb),
    ('Pass 4', 'Lateral Raises', 6::numeric, '[10, 10, 10, 10]'::jsonb)
  ) as values_to_apply(day_name, exercise_name, start_weight_kg, start_reps),
  public.exercises e
where p.name = 'Johan'
  and pe.profile_id = p.id
  and pe.day_name = values_to_apply.day_name
  and pe.exercise_id = e.id
  and e.name = values_to_apply.exercise_name;

commit;
