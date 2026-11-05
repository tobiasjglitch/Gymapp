# Premium exercise animation upgrade

The public app stays unchanged until every active Tobias exercise has passed the
local gallery review. Work is split into durable Git commits so it can be
resumed from this file and `git log` in a later session.

## Shared visual system

- [x] Premium incline dumbbell press proof of concept
- [ ] Shared human rig, lighting, materials, camera and floor
- [ ] Bench/body intersection fixed in the shared rig
- [ ] Shared muscle-highlight system
- [ ] Desktop and mobile gallery layouts

## Batch 1: Press and chest

- [ ] Lutande hantelpress (`incline_press`)
- [ ] Kabel-flyes (`cable_fly`)
- [ ] Hantelpress plan bank (`bench_press`)
- [ ] Brostpressmaskin (`machine_chest_press`)

## Batch 2: Shoulders and rows

- [ ] Broststodd roddmaskin (`chest_supported_machine_row`)
- [ ] Sidolyft hantlar (`lateral_raise`)
- [ ] Broststodd high row (`chest_supported_high_row`)
- [ ] Sidolyft i kabel (`cable_lateral_raise`)
- [ ] Omvand pec deck - bakre axlar (`reverse_pec_deck`)

## Batch 3: Back, cable and arms

- [ ] Latsdrag, neutralt grepp (`neutral_grip_pulldown`)
- [ ] Sittande roddmaskin (`seated_machine_row`)
- [ ] Triceps pushdown (`triceps_pushdown`)
- [ ] Kabel-crunch (`cable_crunch`)

## Batch 4: Legs

- [ ] Benpress (`leg_press`)
- [ ] Sittande larurl (`leg_curl`)
- [ ] Benspark (`leg_extension`)
- [ ] Vadpress i maskin (`machine_calf_raise`)

## Release gate

- [ ] All 17 modes render nonblank and animate
- [ ] Equipment and movement visually match every exercise
- [ ] No figure/equipment intersections that obscure the movement
- [ ] Pause control works in every preview
- [ ] Existing Python and JavaScript tests pass
- [ ] Local gallery approved by Tobias
- [ ] One final push and live Streamlit verification
