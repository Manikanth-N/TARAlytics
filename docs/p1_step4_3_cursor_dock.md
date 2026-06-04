# P1 Step 4.3 — CursorDock
## Status: implemented, wired as the persistent right context surface, tested, benchmarked, validated on logs 02 / 11 / 12 with the three diagnosis cases.

A single persistent dock, visible across every module, that answers "what was
happening at the cursor" without opening a plot. Three stacked pieces, all driven
by the Step-4.1 shared cursor and the shared services:

```
CursorDock (300 px, persistent right)
├── CursorContextPanel   flight# · time · phase · mode · AGL · speed · GPS · sats · verify
│     └── AttitudeMatrix  R/P/Y × Pilot · Demand · Actual  (divergence colour-flagged)
└── ValuesAtCursorTable   configurable watchlist · one SampleService.batch() · hover provenance
```

One subscriber to `cursor_time_changed` (`'CursorDock'`); it fans each move out to
the context panel (incl. matrix) and the values table.

---

## 1. ValuesAtCursorTable

- **One `SampleService.batch()` per cursor move.** The whole table resolves in a
  single call (verified by a test that counts `batch` invocations == 1 per move).
  No per-row sampling on the hot path.
- **Configurable rows** via `set_rows([RowSpec(label, msg, col, unit, fmt)])`. Items
  are created once; `refresh()` only sets value text, so scrubbing is
  allocation-free. The default watchlist is **complementary** to the rest of the
  dock — power (`BAT.Volt/Curr`), motor outputs (`RCOU.C1–C4`), vibration
  (`IMU[0].AccZ`, `VIBE.VibeZ`) — i.e. the raw engineering signals *not* already
  surfaced by the context panel/matrix.
- **Provenance on hover.** Hovering a value runs one `sample_at` for that row only
  (cold path) and sets a tooltip: source `msg.col`, the value, and whether it was an
  exact sample (`@ t`) or interpolated (`between t0–t1`).
- **Never fabricates.** Out-of-range → `—` (greyed); confirmed by an out-of-range
  test at `t < data start`.

## 2. CursorContextPanel

Nine flight-level readouts in a 2-column grid, resolved through the shared services:

| Field | Source |
|-------|--------|
| Flight # | `TimelineModel.flight_windows()` — which window contains t, of N |
| Time | shared cursor |
| Phase | `TimelineModel.phase_at(t)` |
| Mode | `TimelineModel.mode_at(t)` |
| Alt (AGL) | hierarchy `POS.RelHomeAlt → BARO[0].Alt → BARO.Alt → POS.Alt` via `SampleService` |
| Speed | `GPS[*].Spd` (ground speed) |
| GPS Status | `GPS[*].Status` → `GPS_FIX_NAMES` (zero-order hold) |
| Satellites | `GPS[*].NSats` |
| Verification | `AppState.verification.state` (live; updates on `verification_changed`) |

Pre-arm / out-of-range degrade to `—` (e.g. `— / N` flight before the first ARM).

## 3. Pilot · Controller · Aircraft Matrix

The diagnosis grid — Roll / Pitch / Yaw × three columns:

| Column | Meaning | Source |
|--------|---------|--------|
| **Pilot** | what the stick commanded (−1..+1, 0 = trim) | `RCModel.pilot_input(svc, t)` (RCIN, vehicle's own RCMAP/limits) |
| **Demand** | what the controller asked for (deg) | `ATT.DesRoll / DesPitch / DesYaw` |
| **Actual** | what the aircraft did (deg) | `ATT.Roll / Pitch / Yaw` |

**Divergence flag.** `|Demand − Actual|` (yaw-wrap-aware) colours the *Actual* cell:
≥ 8° caution (amber), ≥ 20° critical (red). This turns "is the aircraft following
the controller?" into a glance.

---

## 4. Validation — the three cases (logs 02 / 11 / 12)

Screenshots in `docs/screenshots/sprint_p1_step4_3/`. Real frames, real numbers:

### Case 1 — Pilot-driven maneuver · `dock_pilot_maneuver_log11.png` (log 11 @ 1485.2 s)
```
Flight 2/3 · HOVER · LOITER · 1.1 m · 2.1 m/s · DGPS · 31 sats · STRUCTURE ERROR
            PILOT   DEMAND  ACTUAL
   R        +0.68     +6°     +4°
   P        -0.67     -8°     -6°
   Y        +0.00   +143°   +145°
```
**Pilot commanding** (right roll + forward pitch, ±0.68 stick); the controller
translates it to small attitude demands and the aircraft tracks tightly — no flag.
The truncated log shows **STRUCTURE ERROR** in Verify.

### Case 2 — Autopilot stabilization · `dock_stabilization_log12.png` (log 12 @ 892.1 s)
```
Flight 1/1 · HOVER · LOITER · 3.1 m · 1.5 m/s · DGPS · 28 sats
            PILOT   DEMAND  ACTUAL
   R        +0.00     -7°     -8°
   P        +0.00     -7°     -8°
   Y        +0.00   +340°   +340°
```
**Pilot hands-off** (all +0.00); the autopilot is actively commanding −7° attitude
to hold position in LOITER and the aircraft follows within 1° — clean closed-loop
stabilization, no flag.

### Case 3 — Demand ≠ Response divergence · `dock_divergence_log12.png` (log 12 @ 876.1 s)
```
Flight 1/1 · HOVER · LOITER · 3.3 m · 0.8 m/s · DGPS · 28 sats
            PILOT   DEMAND  ACTUAL
   R        +0.00     +1°     -8°   ← amber (9°)
   P        +0.00     +6°    +17°   ← amber (11°)
   Y        +0.00   +143°   +188°   ← red   (45°)
```
**Pilot hands-off**, yet the aircraft is well off the controller's demand —
especially **45° in yaw (red)** with roll/pitch amber. The divergence is visible
instantly without opening a single plot.

(`dock_autopilot_track_log02.png`, log 02 @ 150 s — a clean SITL reference: pilot 0,
demand == actual to the degree, no flag.)

---

## 5. Performance

| Measurement | Value |
|-------------|-------|
| Dock refresh / cursor move (context + matrix + 8-row table, full data + widget update) | **487 µs** (~2050 moves/s) |
| ValuesAtCursorTable | **1** `batch()` call / move (measured) |
| Headroom vs 60 fps (16.7 ms) | **~34×** |

Cost is flat across log size (the data layer is O(log n), proven in Steps 1–3).
"Fast enough for continuous scrubbing" — yes, with ~34× headroom even with the
Timeline overlay repaint running alongside.

---

## 6. Usability Review

**Q1 — Can a flight-test engineer tell what happened at the cursor in < 5 s?**
Yes. The dock is always on screen; the top six readouts give the *situation*
(flight, time, phase, mode, altitude, speed) and the matrix gives the *control
story* (pilot/demand/actual) at a glance. The divergence frame above reads "yaw is
red, pilot is hands-off" in ~1 s.

**Q2 — Can pilot vs controller vs aircraft be understood without a plot?**
Yes — that is exactly what the matrix encodes, and the three validation cases prove
it discriminates: pilot-driven (Case 1), autopilot-driven (Case 2), and
controller-vs-aircraft divergence (Case 3) are each distinguishable from the three
columns alone.

**Q3 — Is any information duplicated unnecessarily?**
No. The split is deliberate: the **matrix** owns attitude/control, the **context
panel** owns flight-level state, and the **values table** is intentionally
*complementary* (power / motors / vibration), so nothing is repeated. The only
shared concept is altitude, which appears once (context) — the table's defaults
exclude it.

**Q4 — Is anything important still hidden?**
A few items, surfaced honestly for prioritisation (not yet shown):
- **Throttle axis** — the matrix is R/P/Y per spec; pilot throttle + motor outputs
  exist (RCModel throttle / RCOU rows) but aren't in the matrix. *Recommend a 4th
  matrix row.*
- **Vertical speed / climb rate** — only AGL is shown; `BARO.CRt` would sharpen
  HOVER vs CLIMB/DESCENT reading.
- **EKF / innovation health at cursor** and **position/velocity divergence** — the
  divergence flag is attitude-only today; lateral drift isn't surfaced.
- **Battery remaining %** and **RC link / RSSI**.
These are candidate additions; several land naturally in the upcoming **Horizon**,
**RC Visualization**, and **Unified Events** surfaces. Holding for approval rather
than expanding scope now.

*Note:* the validation screenshots show `UNVERIFIED` / `STRUCTURE ERROR` because the
capture script loads no public key; in-app with a key loaded the same field shows
`VERIFIED` (log 02/12) or the true `STRUCTURE_ERROR` (truncated log 11).

---

## 7. Tests (`tests/test_cursor_dock.py`, +12; suite 254 → 266)

| Area | Tests |
|------|-------|
| ValuesAtCursorTable | **single batch / move**, value formatting, configurable rows, out-of-range `—`, hover provenance tooltip |
| CursorContextPanel | all fields populate, verify state reflected, pre-arm has no flight number |
| AttitudeMatrix | pilot/demand/actual track during maneuver, **divergence colour-flagged (critical)**, tracked flight not flagged, blank without data |

Full suite: **266 passed**, no regressions.

---

## 8. Conclusion / Next
CursorDock is implemented, wired as the persistent right surface, single-batch and
provenance-aware, sub-millisecond per move (~34× headroom), and validated on the
three diagnosis cases with real frames from logs 11/12 (+02 reference). Per the
approved order, **only after CursorDock validation** does the next block begin —
**Unified Events**, then **Horizon**, **RC Visualization**, **Map Sync** — awaiting
your go-ahead.
