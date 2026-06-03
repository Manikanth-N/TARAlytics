# Sprint-1 Demo Workflow
## TARAlytics — Theme · Navigation · AppState · Debrief
### For: Tara UAV Engineering Team

---

## Pre-Demo Setup

```bash
cd /path/to/TARAlytics
python3 main.py
```

Have ready: `logs/00000002.BIN` and `SN-01_log_public_key.dat`

---

## Demo Script

### 1. Launch (30 seconds)

Open the application. Point out:
- Dark blue surface — derived from Tara UAV brand blue (`#1A9FD5`)
- Rajdhani typography matching the wordmark weight
- "NO FLIGHT DATA LOADED" empty state — clean, purposeful
- Navigation rail on the left — 4 items: DEBRIEF · SIGNALS · REPLAY · VERIFY
- "TARAlytics — MISSION DEBRIEF STATION" in the header

### 2. Load a Log File (1 minute)

Click **Open Log** → select `logs/00000002.BIN` → click **▶ Parse**

Watch:
- Progress bar fills in the header (thin, 6px, brand blue)
- Status bar shows parse activity
- On completion, **DEBRIEF** module auto-populates

Point out on the Debrief screen:
- **FLIGHT PROFILE** column: Duration `0:44`, Max altitude `9.99 m`, 14 events, 4 mode changes
- **HEALTH ASSESSMENT** grid: all four systems (NAVIGATION · PROPULSION · POWER · STRUCTURAL) show `NOMINAL`
- **VERIFICATION** section: badge shows `UNVERIFIED` — key not yet loaded
- **NOTABLE EVENTS** list: ARM, EKF alignment, landing, DISARM

### 3. Load the Public Key (30 seconds)

Click **Load Key** → select `SN-01_log_public_key.dat`

Watch:
- Verification runs automatically
- **Flight Identity Bar** badge (top right of the bar) changes from `UNVERIFIED` → `VERIFIED`
- Debrief verification section updates: `Ed25519-Blake2b · 1,098 chunks verified`

### 4. Navigate Modules (1 minute)

Click **SIGNALS** in the nav rail:
- Plotter tab appears. Existing signal tree on the left. Existing plot area.
- Point out: the nav rail item highlights (blue left bar, tinted background)

Click **REPLAY** in the nav rail:
- 3D replay view appears. Existing trajectory and controls.

Click **VERIFY** in the nav rail:
- Verification tab appears. Full signature panel, hash rows, chain details.

Click **DEBRIEF** to return:
- All data still present. Module state is preserved between navigation.

### 5. Flight Identity Bar (30 seconds)

Point to the persistent bar below the header:
```
SN-01  ·  QUAD/PLUS  ·  ArduCopter 4.6.3  ·  #002  ·  44.0 s  ·  9.99 m  ·  [VERIFIED]
```
- Always visible regardless of which module is active
- VERIFIED badge uses the brand blue — same color as the Tara UAV logo

---

## Key Messages for Stakeholders

| What they see | What it means |
|---|---|
| Dark blue surfaces | Derived from Tara UAV brand color — not a generic dark theme |
| Rajdhani font | Same typeface family as the Tara UAV wordmark |
| VERIFIED badge in the header | Log integrity confirmed at a glance, on every screen |
| Navigation rail | Post-flight workflow sequence — not a feature menu |
| Debrief as the landing screen | The tool answers "was this flight okay?" before the engineer asks |

---

## Known Sprint-1 Scope Limits (do not demo these)

- Plotter signal curves are not yet upgraded to glow rendering (Sprint-2)
- 3D replay camera modes not yet added (Sprint-2)
- DGCA compliance module not yet built (Sprint-3)
- Fleet dashboard not yet built (Sprint-3)
