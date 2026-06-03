# Sprint-1.2 — Data Accuracy: CONFIRMED FINDINGS
## Evidence gathered (read-only). No logic changed yet.

---

## Headline: a single parser bug explains 3 of 4 anomalies

The impossible altitude, speed, and distance all trace to **one root cause in the
parser**, not the source log, not scaling, not the metric math. The duration
anomaly is a separate metric-definition issue.

---

## Smoking gun: 199968.765625 = the bytes `1HCH`

`199968.765625` decoded as float32 has the byte pattern `31 48 43 48` = **`"1HCH"`**
(`0x48434831`). In `core/signature_verifier.py`:

```
TRAILER_MAGIC = b'1HCH'
CHUNK_MAGIC   = 0x48434831   # "HCH1"
```

This is the **signature hash-chain chunk magic**. The number is not flight data —
it is the cryptographic chunk-record marker bleeding into parsed message fields.

**The parser is reading signature hash-chain chunk records as if they were
flight-data messages.** `DataFlashParser.parse()` strips the 64-byte header and
145-byte trailer, but does **not** exclude the interleaved hash-chain chunk
records (`CHUNK_MAGIC` every 44 bytes, plus the END record). When those bytes
align under the `0xA3 0x95` record scan, spurious records are produced.

### Evidence
- `199968.765625` appears in **40 cells across 12 message types**:
  `SIM2(25), CTRL(4), PIDR(2), BARO[1], PARM, PIDE, PIDY, POS, SURF[1], XKF1[1], XKF3[1], XKY1[1]`.
- The same magic decoded through an **`L`-format field** (int32 ÷ 1e7, used by
  lat/lng): `0x48434831 = 1212698161 → 121.2698°`. This matches the garbage
  `POS.Lat` max of `121.236895°` — i.e. the **distance** anomaly is the *same*
  chunk leak seen through a different field format.

---

## Per-metric attribution

| Metric | Bad value | Source field | Root cause | Layer |
|--------|-----------|--------------|-----------|-------|
| **Altitude** | `199968.77 m` | `POS.Alt` (1 of 586 rows) | `1HCH` chunk magic → float32 | **PARSING** |
| **Speed** | `199968.77 m/s` | `SIM2.VN/VE/VD` (26 rows) | `1HCH` chunk magic → float32 | **PARSING** (same) |
| **Distance** | `44133 km` | `POS.Lat/Lng` (→ ENU) | chunk magic → `L`-format lat `121°` → ENU blow-up | **PARSING** (same) |
| **Duration** | `0:58` | global t-span | metric uses **log span**, not the armed window | **METRIC CALC** (primary); chunk-leaked `TimeUS` a secondary contributor |

### Source data is NOT at fault
The log is a valid signed DGCA log (verifies VERIFIED / 1098 chunks). The clean
data is correct: `SIM2.-PD` altitude peaks at `10.07 m`; `SIM2` speed median
`0.028 m/s`, 99.5th pct `2.5 m/s`; armed window `43.6 s`. The anomalies are
signature infrastructure mis-parsed as data.

### Duration detail
- ARM first `126.993 s`, ARM last (disarm) `170.569 s` → **armed = 43.6 s → `0:43`** (true flight time).
- Global log span `126.993 → 185.564 s = 58.6 s → `0:58`` (currently displayed).
- SITL legitimately logs **5,935 SIM2 rows after disarm** (to `185.56 s`), so the
  span is real; the metric is simply the wrong definition for "flight duration".

---

## Confirmed fix direction (to implement AFTER this plan is approved)

1. **Parser (fixes altitude, speed, distance):** during the data pass, exclude the
   signature hash-chain region. Reuse `signature_verifier`'s chunk/END scan to
   identify `CHUNK_MAGIC` / `END_MAGIC` record ranges and skip them, so chunk bytes
   never enter `_pass2_parse_all`. This removes all 40 sentinel cells at the source.
2. **Metric (fixes duration):** define "flight duration" as the **armed window**
   (first→last ARM, or arm→disarm event), not the global log span. Show log span
   separately if useful.
3. **Defense in depth (display trust):** even after (1), compute Debrief headline
   stats with outlier-robust guards (e.g. drop non-physical rows / use high
   percentile) and **flag** any value that required guarding rather than showing it
   silently. Success criterion: "suspicious data is flagged, not silently trusted."

### Why not just filter harder?
Tightening the magnitude gate (e.g. `1e9 → 1e6`) would mask altitude/speed but is
a band-aid that risks clipping valid large counters and would not fix the `121°`
lat (distance). Excluding the chunk region at the parser is the correct,
root-cause fix.

---

## Validation plan for the fix (when implemented)
- After parser fix: 0 cells equal to `199968.765625`; `POS.Alt` max ≈ `586 m` AMSL
  (or `RelHomeAlt`/`SIM2.-PD` ≈ `10 m`); `SIM2` speed max ≈ `2.5 m/s`; trajectory
  east/north within metres; verification unchanged (operates on raw bytes).
- After metric fix: duration ≈ `0:43`.
- Regression: full suite green; Sprint-1.1 structural invariants intact.
- Add a ground-truth test asserting no `1HCH` sentinel survives parsing.
