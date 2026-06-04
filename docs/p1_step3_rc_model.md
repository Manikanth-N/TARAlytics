# P1 Step 3 — RCModel + TimelineModel FlightWindow
## Status: implemented + tested + benchmarked. UI not started.

Also adds the **FlightWindow / Timeline summary** requested at the close of Step 2.

---

## 0. TimelineModel FlightWindow (Step-2 addendum)

```
@dataclass FlightWindow:
    index, start, end, duration, peak_agl, event_count, mode_count, source
TimelineModel.flight_windows() -> [FlightWindow]   # one per arm window (multi-flight)
TimelineModel.summary()        -> {log_span, flight_count, armed_total_s,
                                    peak_agl_m, event_total, flights[]}
Timeline.flights                # included in build()
```
Per-flight stats computed within each arm region (peak AGL, events in window, distinct
modes overlapping). Feeds Debrief, Certification, Fleet analytics, Evidence export.
+4 tests (20 total in `test_timeline_model.py`).

**Real logs:**
```
02: 1 flight  · 44s  · peak 10.0m · 28 ev · 3 modes [ARM]
11: 3 flights · #0 25s/1.6m/25ev · #1 156s/4.8m/16ev · #2 116s/2.7m/17ev [ARM]
12: 1 flight  · 889s · peak 14.0m · 23 ev · 1 mode [EV]
```

---

## 1. Architecture Notes (RCModel)

- **Semantic, not raw.** Exposes **roll / pitch / yaw / throttle**, never C1–C4.
  Roll/pitch/yaw are normalized to **−1..+1** (0 at trim, sign = stick direction);
  throttle to **0..1**.
- **Parameter-driven, matching the autopilot.** Reads the vehicle's own params so the
  mapping/scaling equal what flew:
  - `RCMAP_ROLL/PITCH/THROTTLE/YAW` → channel (default 1/2/3/4).
  - `RC{n}_MIN/MAX/TRIM/DZ` → scaling + deadzone.
  - reversing: `RC{n}_REVERSED` (0/1, new) preferred, legacy `RC{n}_REV` (±1) fallback.
- **Pure core, no Qt.** `from_data(data)` pulls params from PARM; or construct with an
  explicit `{name: value}` dict (testable).
- **Time-resolved via SampleService** (the shared cursor): `pilot_input(svc, t)` reads
  RCIN; `servo_output(svc, t)` reads RCOU with the same mapping/normalization → enables
  pilot-vs-output comparison. Both return a `StickState`.
- **Defensive.** Missing/malformed/NaN params fall back to documented defaults
  (map 1/2/3/4, MIN1000/TRIM1500/MAX2000, no reverse, no deadzone); MIN≥MAX or
  out-of-range TRIM are repaired.

### Outputs feed
RC stick visualization · pilot-vs-controller analysis · investigation snapshots ·
values-at-cursor table.

### Normalization
```
throttle:  n = clamp((pwm−MIN)/(MAX−MIN), 0, 1);    reversed → 1−n
centered:  d = pwm−TRIM; |d|≤DZ → 0;
           half = (MAX−TRIM) if d>0 else (TRIM−MIN);
           n = clamp((|d|−DZ)/(half−DZ), 0, 1) · sign(d);  reversed → −n
```

---

## 2. Test Coverage (`tests/test_rc_model.py`, 23 tests)

| Scenario | Cases |
|----------|-------|
| Default mappings | axis→channel 1/2/3/4; centered trim/full/half; throttle 0–1; clamping |
| Custom mappings | custom RCMAP; custom MIN/MAX/TRIM scaling |
| Reversed channels | `RC_REVERSED` (new), `RC_REV` (legacy), reversed throttle, new-param precedence |
| Deadzone | small inputs centred to 0 just inside/at DZ; non-zero just outside |
| Missing params | None PWM → None; defaults applied |
| Malformed params | MIN≥MAX → defaults; string/NaN params ignored; out-of-range TRIM recentred |
| Time-resolved | `pilot_input`/`servo_output` StickState via SampleService; out-of-range axis → None |
| Real log (02) | params extracted (RCMAP_ROLL=1, RC1 1000/2000); 4 semantic axes within range; pilot + output both available |

Full suite after Step 3: **221 passed**.

---

## 3. Performance + Example Outputs (logs 02 / 11 / 12)

| Log | params | `RCModel` init | pilot+output resolve (8 lookups) |
|-----|--------|----------------|----------------------------------|
| 00000002 | 1397 | 0.35 ms | **20.5 µs** |
| 00000011 | 1063 | 0.37 ms | **21.1 µs** |
| 00000012 | 1063 | 0.41 ms | **20.6 µs** |

Flat with log size (lookups go through SampleService, O(log n)); init is a one-time
PARM scan. Far inside the 60 fps budget.

### Example outputs (pilot vs controller-output, mid-flight)
```
02 @156.3s  PILOT(RCIN):  roll +0.00  pitch +0.00  yaw +0.00  thr +0.00
            OUTPUT(RCOU): roll +0.14  pitch +0.14  yaw +0.14  thr +0.59
   → sticks centred, outputs active = AUTOPILOT stabilizing, no pilot input
     (ch1 cfg: MIN1000 TRIM1500 MAX2000 DZ20 rev=False)

11 @1549.7s PILOT(RCIN):  roll +0.00  pitch +0.00  yaw −1.00  thr +0.00
            OUTPUT(RCOU): roll −0.73  pitch +0.00  yaw +0.14  thr +0.13
   → full LEFT YAW stick = clear PILOT action (calib MIN1051/MAX1951)

12 @562.9s  PILOT(RCIN):  roll −0.01  pitch −0.17  yaw +0.00  thr +0.50
            OUTPUT(RCOU): roll −0.14  pitch +0.00  yaw +0.03  thr +0.52
   → slight back-pitch pilot input; outputs tracking
```
These demonstrate the core investigation value: **the same cursor resolves pilot
intent and controller output in semantic units**, so "pilot action vs autopilot
behavior" is readable without opening a plot — the basis for the Situational
Awareness panel's pilot-vs-controller strip.

### Note (documented)
`servo_output` normalizes RCOU through the same RC{n} MIN/MAX as the input. Motor/
servo outputs share the ~1000–2000 PWM band, so the magnitudes are directly
comparable for investigation; absolute servo calibration (SERVO{n}_*) is a possible
future refinement, not needed for pilot-vs-output intent.

---

## 4. Conclusion / Next
The cursor's data foundation is now complete: **SampleService** (values + provenance),
**TimelineModel** (structure + FlightWindows), **RCModel** (semantic pilot intent).
All pure, tested (221 passed), and fast/flat across 4–440 MB logs. Per the approved
order, the next step is the **Timeline UI** (Step 4), built on this foundation.
