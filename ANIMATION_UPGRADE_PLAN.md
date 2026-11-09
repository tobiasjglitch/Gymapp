# Premium exercise animation upgrade

The public app stays unchanged until every active Tobias exercise has passed the
local gallery review. Work is split into durable Git commits so it can be
resumed from this file and `git log` in a later session.

## Shared visual system

- [x] Premium incline dumbbell press proof of concept
- [x] Shared human rig, lighting, materials, camera and floor
- [x] Bench/body intersection fixed in the shared rig
- [x] Shared muscle-highlight system
- [x] Desktop and mobile gallery layouts
- [x] Anatomical 3D visual standard with dark-green baked background
- [x] Muted coral muscle highlights and clean silhouettes without alpha halos
- [x] 15 active Tobias modes exported as compact four-frame GIF loops
- [x] Automatic GIF selection with legacy 3D fallback for other exercises

## Batch 1: Press and chest

- [x] Lutande hantelpress (`incline_press`)
- [x] Kabel-flyes (`cable_fly`)
- [x] Hantelpress plan bank (`bench_press`)
- [x] Brostpressmaskin (`machine_chest_press`)

## Batch 2: Shoulders and rows

- [x] Broststodd roddmaskin (`chest_supported_machine_row`)
- [x] Sidolyft hantlar (`lateral_raise`)
- [x] Broststodd high row (`chest_supported_high_row`)
- [x] Sidolyft i kabel (`cable_lateral_raise`)
- [x] Omvand pec deck - bakre axlar (`reverse_pec_deck`)

## Batch 3: Back, cable and arms

- [x] Latsdrag, neutralt grepp (`neutral_grip_pulldown`)
- [x] Sittande roddmaskin (`seated_machine_row`)
- [x] Triceps pushdown (`triceps_pushdown`)
- [x] Kabel-crunch (`cable_crunch`)

## Batch 4: Legs

- [x] Benpress (`leg_press`)
- [x] Sittande larurl (`leg_curl`)
- [x] Benspark (`leg_extension`)
- [x] Vadpress i maskin (`machine_calf_raise`)

## Release gate

- [x] All 17 modes render nonblank and animate
- [x] Equipment and movement visually match every exercise
- [x] No figure/equipment intersections that obscure the movement
- [x] Pause control works in every preview
- [x] Existing Python and JavaScript tests pass
- [ ] Local gallery approved by Tobias
- [ ] One final push and live Streamlit verification
