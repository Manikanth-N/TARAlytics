# Follow-up Investigation — Optional Altitude Drop-Lines / Ground Projection

**Status:** OPEN · investigation only · **blocked on visual validation of P2 on a real GPU display**
**Origin:** Map & Replay Spatial Review (P2, "optional altitude drop-lines").

## Scope
Evaluate adding **vertical drop-lines** from the 3D flight path down to the ground grid
(and/or a faint **ground-projected shadow** of the track) to convey height at a glance,
the way mission-planning tools do.

Investigate:
- **Readability** — do periodic drop-lines make climb/descent obvious without clutter?
- **Subsampling / density** — one line per N samples or per fixed time interval; how many
  before the scene gets noisy on long flights.
- **Ground shadow** — a grey projection of the track onto z=0 as a lighter-weight
  alternative (or complement) to drop-lines.
- **Toggle** — off by default; a checkbox in the existing 3D control bar (next to
  "Show Heading").
- **Performance** — each drop-line is a `GLLinePlotItem`; measure item count / FPS on the
  440 MB log before enabling by default.
- **Interaction with vertical exaggeration** — drop-lines must use the same exaggerated Z
  as the path so feet land on the grid consistently.

## Constraints
- **Do NOT** start a terrain engine, Cesium, tiles, or any new mapping/3D engine.
- Additive only; must not change the existing path/aircraft/telemetry behaviour.

## Prerequisite
Validate P2 (vertical exaggeration) visually on a GPU display first — drop-line density
and exaggeration need to be tuned together on real hardware.

## Acceptance (proposed)
With drop-lines (or ground shadow) enabled, a reviewer can read relative height along the
path at a glance; disabling returns to the current view exactly; no measurable FPS
regression on the 440 MB log.
