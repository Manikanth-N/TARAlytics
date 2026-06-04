# Follow-up Investigation — 3D Camera Positioning Review

**Status:** OPEN · investigation only · **blocked on visual validation of P2 on a real GPU display**
**Origin:** Map & Replay Spatial Review (P2). Altitude-source root cause is fixed (P0,
completed bug fix); auto vertical exaggeration (P2) is implemented but not yet eyeballed
on hardware.

## Scope
Evaluate the 3D replay camera so altitude changes (takeoff / climb / hover / descent /
landing) are easy to perceive across the three reference logs.

Investigate:
- **Default elevation/pitch** — current default is 30° (somewhat top-down). A lower,
  more side-on elevation may read altitude profiles better; quantify on real flights.
- **Distance / framing** vs. the auto vertical-exaggeration factor (`auto_z_exag`,
  log 11 ≈ ×2.8, log 12 ≈ ×2.0, log 02 ≈ ×1.0) — confirm the combination is legible and
  not distorted.
- **Follow-vehicle vs. whole-track** framing during playback.
- Whether a one-tap **"side / profile view"** preset (azimuth aligned to the dominant
  travel axis, low elevation) helps investigators read climb/descent.

## Constraints
- **Do NOT** start a terrain engine, Cesium, tiles, or any new mapping/3D engine.
- Reuse the existing `pyqtgraph.opengl` view; camera/preset tuning only.
- Telemetry and path colour must keep showing **true** altitude.

## Prerequisite
Validate P2 (vertical exaggeration) visually on a GPU display first; this environment
cannot render `pyqtgraph.opengl` (`Requires >= OpenGL 2.1` fails headless).

## Acceptance (proposed)
A reviewer can distinguish takeoff/climb/hover/descent/landing from the replay alone on
logs 00000002 / 00000011 / 00000012 without reading the telemetry numbers.
