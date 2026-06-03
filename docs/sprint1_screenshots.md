# Sprint-1 Screenshot Deliverables
## Capture these after each task is complete

Capture screenshots at 1400×900 resolution. Save to `docs/screenshots/sprint1/`.

---

## T2 — Theme Applied

**File:** `t2_theme_applied.png`
**When:** After `apply_theme()` is wired in `main.py` and app launches
**What to show:** Full application window, empty state (no log loaded)
**Acceptance check:**
- Background is deep blue-black (not the old `#1e1e2e` purple-grey)
- Scrollbars are 6px with brand-blue handles
- Font is Rajdhani (not system default)

---

## T10 — Navigation Rail

**File:** `t10_nav_rail.png`
**When:** After `NavigationRail` is wired into `MainWindow`
**What to show:** Left rail visible with all 4 items, DEBRIEF highlighted
**Acceptance check:**
- Rail is exactly 64px wide
- Active item (DEBRIEF) has 3px brand-blue left bar
- Icon and label visible in each item

---

## T11a — MainWindow Refactored (no log)

**File:** `t11a_no_log.png`
**When:** After `MainWindow` refactor, before any log is loaded
**What to show:** Full window — header, flight bar, nav rail, empty state canvas
**Acceptance check:**
- "TARAlytics — MISSION DEBRIEF STATION" visible in header
- Flight identity bar shows "NO LOG LOADED"
- Open Log / Load Key / ▶ Parse buttons in header

---

## T11b — Existing Tabs Via Rail

**File:** `t11b_signals_tab.png`
**When:** After parsing `00000002.BIN`, click SIGNALS in nav rail
**What to show:** Signal plotter visible, nav rail with SIGNALS highlighted
**Acceptance check:**
- Plotter renders correctly
- Nav rail SIGNALS item is highlighted
- Flight identity bar remains visible

---

## T12a — Debrief Module (no log)

**File:** `t12a_debrief_empty.png`
**When:** Debrief module visible before any log is loaded
**What to show:** Debrief module with all `—` placeholders
**Acceptance check:**
- Three-column layout visible (Flight Profile · Health · Verification)
- All metric cards show `—`
- Health cards show `NO DATA` state

---

## T12b — Debrief Module (log loaded, no key)

**File:** `t12b_debrief_no_key.png`
**When:** After parsing `00000002.BIN`, key not yet loaded
**What to show:** Debrief fully populated, UNVERIFIED badge
**Acceptance check:**
- Duration: `0:44`, Max alt: `9.99 m`, Events: `14`
- All 4 health cards: `NOMINAL`
- Verification badge: grey `UNVERIFIED`
- Notable events list shows ARM, EKF alignment, landing

---

## T12c — Debrief Module (log loaded + key loaded)

**File:** `t12c_debrief_verified.png`
**When:** After loading `SN-01_log_public_key.dat`
**What to show:** Debrief with VERIFIED state throughout
**Acceptance check:**
- Flight identity bar badge: blue `VERIFIED`
- Debrief verification section: blue `VERIFIED` badge, `Ed25519-Blake2b`, `1,098 chunks verified`

---

## T12d — Flight Identity Bar Close-up

**File:** `t12d_flight_bar.png`
**When:** Log parsed and key loaded (VERIFIED state)
**What to show:** Cropped to just the flight identity bar (28px strip)
**Content:**
```
SN-01  ·  QUAD/PLUS  ·  ArduCopter 4.6.3  ·  #002  ·  44.0 s  ·  9.99 m  · [● VERIFIED]
```

---

## Full Sprint-1 Regression

**File:** `sprint1_regression.png`
**When:** Final check — all 4 nav items working
**What to show:** 2×2 composite:
- Top-left: DEBRIEF (verified state)
- Top-right: SIGNALS (plotter with some signals)
- Bottom-left: REPLAY (3D trajectory visible)
- Bottom-right: VERIFY (full signature panel)
