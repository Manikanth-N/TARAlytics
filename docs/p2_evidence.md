# P2 — Evidence & Investigation Capture
### Status: implemented, tested (309 passing), validated end-to-end (capture → manage → export JSON/MD/PDF). Snapshot placeholder replaced with a real system.

P2 closes the investigation loop: an engineer can **select an event → investigate it
→ capture findings → export evidence**, without leaving TARAlytics. Plus two
investigation aids (vertical speed, EKF / position divergence) wired into the live
surfaces and the snapshot.

---

## 1. Investigation Snapshot System  ([core/snapshot.py](../core/snapshot.py))

`build_snapshot()` is **pure** — it resolves every field at the cursor time through
the shared services (`SampleService` / `TimelineModel` / `RCModel` / `diagnostics`),
so a snapshot is exactly what the live surfaces show, with provenance. Each
`InvestigationSnapshot` captures all required contents:

| Group | Fields |
|-------|--------|
| Identity | index, captured-at (wall clock), cursor time, log path |
| Event | nearest/selected event (time, severity, type, message) |
| Flight | flight window index / total |
| State | phase, mode, position (lat/lng), altitude AGL (+source), vertical speed (+source), ground speed, GPS fix, satellites |
| Control | **Pilot** (RCIN), **Demand** (ATT.Des*/CTUN.ThO), **Aircraft Response** (ATT.*/RCOU), per-axis divergence |
| Diagnostics | EKF health, position divergence |
| Verification | verification state |
| Investigation | notes, status |

The `★ Snapshot` button in the persistent dock now captures a real snapshot at the
cursor (replacing the placeholder).

## 2. Snapshot Management  ([ui/modules/mod_evidence.py](../ui/modules/mod_evidence.py))

A new **Evidence** module (nav ⑨): a list of the session's snapshots (#, time, event,
status), a rendered detail report for the selected one, and per-snapshot **status**
(`OPEN/REVIEWED/FLAGGED`) + **notes** editing and **delete**. Selecting a snapshot
**returns the shared cursor to that moment**, so captures stay live and
re-investigable. Snapshots are held by `AppState` (`capture_snapshot` /
`remove_snapshot` / `clear_snapshots`, `snapshots_changed` signal) and cleared on log
reload.

## 3. Evidence Export  ([core/evidence_export.py](../core/evidence_export.py))

| Format | How | Use |
|--------|-----|-----|
| **JSON** | `evidence_export.to_json` (pure) | machine-readable record (round-trips) |
| **Markdown** | `evidence_export.to_markdown` (pure) | human report |
| **PDF** | `mod_evidence.export_pdf` — Qt `QTextDocument → QPdfWriter` | shareable evidence (no extra dependency) |

A report carries flight identity + verification state as a header, then one section
per snapshot with the field table and the Pilot/Demand/Actual/Δ control table. Sample
artifacts: [sample_evidence.md](screenshots/sprint_p2/sample_evidence.md) ·
`sample_evidence.json` · `sample_evidence.pdf` in `docs/screenshots/sprint_p2/`.

---

## 4. Investigation Aids (not cosmetic)  ([core/diagnostics.py](../core/diagnostics.py))

Each returns a value **plus a state** (OK / CAUTION / CRITICAL) and the **source
field**, surfaced in the dock Context panel (colour-flagged) and captured in every
snapshot:

- **Vertical speed** — `BARO.CRt → CTUN.CRt → −GPS.VZ → POS.RelHomeAlt d/dt` (m/s, +up).
- **EKF health** — worst XKF4 normalised test ratio (SV/SP/SH/SM; ≥1.0 = the filter is
  rejecting that measurement) and the fault bitmask `FS`. Thresholds 0.5 caution / 1.0
  critical; any fault flag → critical.
- **Position divergence** — horizontal EKF position-innovation magnitude
  `hypot(XKF3.IPN, IPE)` in metres (how far the estimate sits from its measurements).
  0.5 caution / 2.0 critical.

All never fabricate — absent sources return `None` / `OK` with `source='none'`.

---

## 5. Success Criteria — the full loop

```
1. Select an event      → Events table / Timeline pin / stepping  (jump_to_event)
2. Investigate it       → Context + Matrix(Δ) + Horizon + RC + Map + V.Speed/EKF/PosDiv
3. Capture findings     → ★ Snapshot  (full provenance-bearing InvestigationSnapshot)
4. Export evidence      → Evidence module → JSON / Markdown / PDF
```

Validated on log 02 (screenshots in `docs/screenshots/sprint_p2/`):
- **`window_indicators_log02.png`** — the dock Context now shows **V.Speed +0.5 m/s**
  (in CLIMB), **EKF OK**, **Pos Div 0.0 m** alongside the existing readouts + matrix.
- **`window_evidence_log02.png`** — the Evidence module: three snapshots
  (REVIEWED / FLAGGED / OPEN), the rendered detail report, edit controls, and the
  JSON / Markdown / PDF export actions.
- Sample exported report (`sample_evidence.md/.json/.pdf`) committed as reference.

The 3D Replay tab is the only surface not yet wired into snapshot capture (it cannot
init OpenGL under the offscreen test/capture platform); that is independent of P2.

---

## 6. Tests (`tests/test_p2_evidence.py`, +19; suite 286 → 309)

| Area | Tests |
|------|-------|
| diagnostics | vertical speed (BARO + derivative fallback), EKF OK/caution/critical + fault-flag override, position divergence, absent-source safety |
| snapshot | all fields captured, nearest-event within window, no event when far, `to_dict` serializable |
| export | JSON round-trips, Markdown contains key fields, empty report, **PDF written (`%PDF` header)** |
| AppState | capture appends + signals, remove, clear, **cleared on reload**, no-data returns None |
| Evidence module | capture adds row, select shows detail + **re-investigates** (moves cursor), status/notes edit persist, delete, **export writes JSON/MD/PDF** |

Plus the dock snapshot test updated to assert real capture. Full suite **309 passed**,
no regressions. `test_ui_main` updated for the 9-tab stack.

---

## 7. Conclusion
The Mission Investigation Workstation now has an evidence trail: findings captured at a
cursor moment with full provenance and diagnostics, managed in-session, and exported as
JSON / Markdown / PDF — the complete select → investigate → capture → export loop,
entirely within TARAlytics. Awaiting direction for what follows.
