# P1 Workflow Layer — Mission Timeline + Unified Event Investigation
## Plan (no code yet). Focus: cut investigation time for real flight-test engineers.

Builds on the trustworthy parser (Sprint-1.2) and the Sprint-1 AppState hub.
Informed by the UAVLogViewer audit: one **shared cursor**, **click-to-jump**, and
**mode/phase context on the time axis** are the highest-leverage patterns.

---

## A. Architecture Proposal

### Principle: one cursor, one event source, many views
- **Single shared cursor** — `AppState.cursor_time_changed(t_abs)` (exists). Timeline,
  Plotter, Replay, Events all emit to it and subscribe to it. No view owns time.
- **Single authoritative event source** — `core/event_extractor.py` (exists). All
  event UIs read it; the 3 legacy fragments are removed.
- **Single phase/segment model** — new `core/timeline_model.py` (pure, no Qt):
  derives flight phases and mode segments from MODE/ARM/ALT.

### New core (pure, testable, no Qt)
```
core/timeline_model.py
    class TimelineModel:
        phases(data)      -> [Phase(name, t_start, t_end)]      # PRE-ARM/TAKEOFF/
                                                                # CRUISE/HOVER/RTL/LAND/POST
        mode_segments(data) -> [ModeSeg(mode, t_start, t_end)]  # from MODE changes
        altitude_profile(data) -> (times[], agl[])              # decimated for display
        # phase detection: ARM window + altitude derivative + MODE
```

### New UI modules
```
ui/modules/mod_timeline.py     TimelineModule   (nav item ②, primary surface)
ui/modules/mod_events.py       EventsModule     (nav item ④, replaces fragments)
ui/widgets/timeline_strip.py   TimelineStrip    (also embeddable as persistent bottom strip)
ui/widgets/event_table_unified.py
```

### AppState additions (additive only)
```
signals_preload_requested = pyqtSignal(list)   # health/event -> plotter preset
time_window_changed       = pyqtSignal(float, float)  # zoom range sync (optional)
event_note_changed        = pyqtSignal(int, str)      # persisted note
# existing reused: cursor_time_changed, event_jumped, module_requested, data_changed
```

### Persistence (notes / investigation status)
```
data/investigations/<device_id>_<log_ctr>.json
    { events: { <event_key>: { note, status } } }   # status: open|reviewed|flagged
```
Keyed by device_id + log counter (stable per flight), not file path.

### What gets deleted (de-fragmentation)
- `ui/widgets/event_timeline.py` (legacy bar) → superseded by TimelineStrip.
- `EventTable` + `EventTimeline` usage inside `tab_verification.py` → removed.
- Debrief "Notable Events" stays as a *read-only top-5 summary* that deep-links into
  the Events module (no separate logic — calls `EventExtractor`).

---

## B. Data Flow Diagram

```
                         ┌──────────────── AppState (hub) ────────────────┐
 parse ─ data_changed ──▶│ data, meta, verification                       │
                         │                                                │
   TimelineModel(data) ──┼─▶ phases / mode_segments / altitude_profile     │
   EventExtractor(data) ─┼─▶ events[]                                      │
                         └───────┬───────────────┬───────────────┬────────┘
                                 │               │               │
                 cursor_time_changed (shared, bidirectional)
                                 │               │               │
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │   TIMELINE   │  │   PLOTTER    │  │    REPLAY    │  │    EVENTS    │
        │ alt profile  │◀▶│  crosshair   │◀▶│  playhead    │◀▶│  selection   │
        │ mode/phase   │  │  signals     │  │  vehicle pos │  │  filters     │
        │ event pins   │  │ values@t     │  │              │  │  notes/status│
        └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
               │ event_jumped(t)         signals_preload_requested    │
               └─────────────┴──────────────┴──────────────┴─────────┘
                         (any view → jump everything to t / load signals)

 VERIFY sync: cursor over a chunk range → Verification can highlight which
 hash-chunk covers that time (read-only; uses signature_verifier chunk offsets).
```

**Bidirectional sync contract:** every view, on user interaction, calls
`AppState.set_cursor_time(t_abs)`; every view subscribes to `cursor_time_changed`
and moves its own cursor **without** re-emitting (guard flag), preventing loops.
This is the eventHub pattern from UAVLogViewer, expressed through AppState.

---

## C. UI Mockups (structure only)

### C1. Mission Timeline (primary investigation surface)
```
┌ TIMELINE ─ SN-01 · #002 · armed 0:43 ──────────────── [⤢ full] [◀ev][ev▶] ┐
│ ALTITUDE (AGL, m)                                          values@ 152.30s │
│ 10┤              ╭───────────────╮                         Alt   9.8 m      │
│  5┤          ╭───╯               ╰──╮                      Mode  LOITER     │
│  0┤──────────╯                      ╰──────────            VSpd -0.3 m/s    │
│    ├─────────┬───────────┬───────────┬──────────┬────────────┬──────────┤  │
│PHASE[PRE-ARM][ TAKEOFF ][      HOVER/MISSION     ][  LAND  ][POST]          │
│MODE [STAB   ][ GUIDED                    ][ LOITER ][ LAND ][STAB]          │
│EVENT  ▲arm    ▲ekf-yaw         ⚠hit-gnd          ▲disarm                    │
│       126.99  135.49           168.48            170.57                     │
│  ◀═══════════════════ playhead ▮ (drag to scrub) ═══════════════════▶       │
└────────────────────────────────────────────────────────────────────────────┘
 click anywhere on alt/phase/mode/event → set cursor → Plotter+Replay+Events jump
 [◀ev][ev▶] step to prev/next event ; double-click phase → zoom Plotter to phase
```

### C2. Unified Event Investigation (replaces 4 fragments)
```
┌ EVENTS ─ 29 total · 1 flagged ─────────────────────────────────────────────┐
│ Severity [✓CRIT ✓ERR ✓WARN ✓INFO]   Type [MSG EV ERR ARM MODE]              │
│ Search [ ground____ ]   Status [All ▾]                     showing 6 / 29    │
│ ────────────────────────────────────────────────────────────────────────── │
│  ⚑ TIME      SEV   TYPE  MESSAGE                  PHASE   STATUS   ACTIONS    │
│     126.993  INFO  ARM   Armed                    PRE-ARM open    [~][3D][⏱]  │
│  ⚑  168.483  WARN  MSG   SIM Hit ground 0.50 m/s  LAND    flagged [~][3D][⏱]  │
│     170.569  INFO  ARM   Disarmed (method=13)     LAND    open    [~][3D][⏱]  │
│ ────────────────────────────────────────────────────────────────────────── │
│  SELECTED  168.483s "Hit ground"   [~ plot][3D replay][⏱ timeline]           │
│  Correlated ±2s: BARO.Alt→0.0 , RATE.ADes↓ , ESCX out↓ , Mode=LAND           │
│  Note [ touchdown harder than spec; check landing detector ____ ] [save]     │
│  Status ( )open  ( )reviewed  (•)flagged-for-DGCA                            │
└────────────────────────────────────────────────────────────────────────────┘
 [~]=jump Plotter+preload correlated signals  [3D]=Replay seek  [⏱]=Timeline cursor
```

### C3. Persistent Timeline strip (optional, bottom of every analysis screen)
A 64px-tall always-visible reduction of C1 (alt sparkline + phase band + event
pins + playhead) so the engineer never loses temporal context while in Plotter or
Replay. Driven by the same cursor.

---

## D. Migration Plan (from fragmented event displays)

| Current (fragmented) | Action | Target |
|----------------------|--------|--------|
| Debrief "Notable Events" list | Keep as read-only top-5; clicking opens Events module at that event | calls `EventExtractor` |
| Verification tab `EventTable` | **Remove** from Verification; logic already in `EventExtractor` | → Events module |
| Verification tab `EventTimeline` bar | **Remove**; superseded | → Timeline strip |
| Plotter event-overlay checkboxes | Keep overlay lines (driven by shared events); drop the duplicate category panel | reuse `EventExtractor` |
| `ui/widgets/event_table.py` | Refactor into `event_table_unified.py` (filters/search/notes) | Events module |
| `ui/widgets/event_timeline.py` | Delete after TimelineStrip lands | — |

**Sequence (low-risk, each step shippable):**
1. `core/timeline_model.py` + tests (pure, no UI risk).
2. `TimelineStrip` widget + `TimelineModule`; wire shared cursor to Plotter/Replay.
3. `EventsModule` (filters/search/jump); switch Debrief Notable Events to deep-link.
4. Remove EventTable/EventTimeline from Verification; delete legacy widget.
5. Add notes/status persistence.
Tests updated alongside each step; Verification-tab tests adjusted in step 4's commit.

**Compatibility:** nav rail grows DEBRIEF · **TIMELINE** · SIGNALS · **EVENTS** ·
REPLAY · VERIFY · MAP (MAP may fold under Replay later). Hidden-tab-bar pattern
unchanged; existing references preserved.

---

## E. Workflow Validation (time-to-answer)

### Post-flight review < 30 s
- Land on **Debrief** (already): verdict + real metrics + VERIFIED + top events.
- Glance **Timeline**: altitude profile + phases show the whole flight shape at once.
- **Pass** if Debrief verdict + Timeline shape are readable without interaction. ✓ (P1 makes Timeline the at-a-glance shape; Debrief already gives the verdict.)

### Crash investigation < 2 min
1. Timeline: see where altitude/▼ anomaly + which phase/mode. (~10 s)
2. Click the anomaly/event → Plotter jumps + preloads correlated signals; Replay
   seeks to that position; Events selects it. (~5 s)
3. Read values-at-cursor + correlated signals → cause hypothesis. (~30 s)
4. Step prev/next event to reconstruct the sequence. (~30 s)
- **Target met**: no manual screen-hopping or signal hunting; one cursor drives all.

### Event root-cause analysis
- Events module: filter to ERR/WARN, select event → correlated ±2s signals +
  phase/mode context + jump to plot with the proving signals preloaded → note +
  flag. One surface, evidence attached.

### Flight-mode transition analysis
- Timeline mode bands make transitions explicit; click a transition boundary →
  Plotter zooms to it; values-at-cursor before/after show the effect (e.g. attitude
  response on GUIDED→LOITER). Mode segments come from `TimelineModel.mode_segments`.

---

## Success Metrics (acceptance for P1)
- One cursor verifiably syncs Timeline ↔ Plotter ↔ Replay ↔ Events (no loops).
- Clicking any event jumps all views to its time in < 1 interaction.
- Zero remaining duplicate event displays (single source proven by test).
- Timeline shows altitude + phases + modes + event pins for logs 02 and 11.
- Crash-investigation walkthrough on log 11 completed in < 2 min (timed).

## Out of scope for P1 (deferred)
Trajectory color-coding, derived-signal expressions, EKF/Tx widgets, param-at-cursor
(P2/P3 per the UAVLogViewer priority ranking). Aesthetics frozen.
