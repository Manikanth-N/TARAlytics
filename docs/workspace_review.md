# Workflow Review — Module Switching & an Investigation Workspace

Focus: reducing tab-switching. Not architecture. Grounded in the implemented UI —
nine surfaces in a single-visible-module stack (Debrief · Timeline · Events ·
Situation · Signals · Replay · Verify · Map · Evidence) plus the persistent right
**Context dock** (already always-visible) and the **shared cursor** that already
syncs every surface.

## The core finding
The shared cursor solved **data** synchronization. It did **not** solve **visual
co-presence.** Every real investigation question is multi-view ("is this roll
*oscillation* pilot-induced?" needs the roll *plot* + the *horizon/stick* + *when*
on the timeline, **at the same time**). The app forces you to look at those one at a
time, re-deriving the correlation in your head on each tab switch. The integration is
real but you can't *see* it.

---

## 1. How often does the user switch modules?

Counted against realistic scenarios in today's single-module stack:

| Persona · task | switches | why |
|---|---:|---|
| **Pilot** — "did I overcontrol / was the landing hard?" | ~10–20 | Signals ↔ Situation (stick vs attitude) ↔ Timeline ↔ Map, repeatedly |
| **Flight-test** — "is there a 4 Hz roll oscillation, is it the controller?" | ~20–40 | Signals (Roll/DesRoll/RATE) ↔ Situation (trail) ↔ Timeline ↔ Evidence, per hypothesis |
| **Accident** — "reconstruct the final seconds" | ~30–50 | Timeline ↔ Events ↔ Map ↔ Signals ↔ Situation ↔ Replay ↔ Evidence, and you **lose the spatial picture every time you leave the Map** |

The shared cursor removed *re-navigation* (you don't re-find the moment), but not the
*re-viewing* — and the accident case is the worst, because position, EKF trace,
event, and attitude are four parallel facts that must be read together.

## 2. Which modules are used together?

- **Pilot triad:** Signals + Horizon + RC.
- **Accident quad:** Signals + Timeline + Map + Events.
- **Certification trio:** Evidence + Verification + Timeline.
- **Always-paired:** Timeline + Events (you navigate by event); Context dock + everything (already persistent ✓).
- **Spatial-temporal:** Map + Timeline.

## 3 & 4. Detachable vs docked

| Surface | role | recommendation |
|---|---|---|
| **Context dock** (matrix/values/diagnostics) | reference | **stays docked right** — already correct |
| **Timeline** | navigation spine | **promote to a persistent bottom transport** (always visible; scrub here, all panels follow) |
| **Signals (Plotter)** | primary work surface | **main pane** — the anchor; rarely floated |
| **Horizon, RC, Map, 3-D Replay** | *glance* surfaces (read-only, cursor-driven) | **detachable / floatable** — ideal for a 2nd panel or 2nd monitor |
| **Events** | navigable list | **side dock** (left) or a workspace panel |
| **Debrief, Verification, Evidence** | report/landing surfaces | **full-pane** (not part of the live scrub workspace) |

The rule: **the surfaces you *act on* stay docked (Signals, Timeline transport,
Context); the surfaces you *watch while acting* should float (Horizon, RC, Map,
Replay).**

## 5. Should an Investigation Workspace exist? — **Yes, emphatically.**

It is the missing payoff of the shared cursor. Because every surface is already
cursor-driven and read-only-safe, a workspace is mostly a **layout container** that
hosts several panels at once — not new analysis. The hard part (sync) is done.

---

## Proposed: Workspace mode

A toggle (a `⊞ Workspace` item on the nav rail) that swaps the single-module pane for
a **configurable split grid** of panels, each a dropdown-selectable surface (Signals /
Horizon / RC / Map / Timeline / Events / Replay), **all on the existing shared
cursor.** Persistent around it:

```
┌ flight identity bar ─────────────────────────────────────────────┬───────────┐
│                                                                   │  CONTEXT  │
│   ┌─ panel A ───────────────┐   ┌─ panel B ───────────┐           │  (matrix, │
│   │  Signals (primary)      │   │  Horizon            │           │  values,  │
│   │                         │   ├─────────────────────┤           │  diagnostics)│
│   │                         │   │  RC Inputs          │           │  ← stays  │
│   └─────────────────────────┘   └─────────────────────┘           │           │
├───────────────────────────────────────────────────────────────────┤           │
│  ◀══ TIMELINE transport (persistent scrub bar) ═════ playhead ▮ ══▶ │           │
└───────────────────────────────────────────────────────────────────┴───────────┘
```

**Two changes do most of the work** and are worth shipping even before a full grid:
1. **Timeline as a persistent bottom transport** — removes the single biggest source
   of switching (you stop tab-hopping to Timeline to move the cursor; you scrub once,
   everything follows). Highest leverage, cheapest.
2. **A 2–3 panel split** in the main pane with **saved layouts** — the actual ask.

### The three example layouts (one click each)
```
PILOT ANALYSIS                 ACCIDENT INVESTIGATION         CERTIFICATION
┌───────────┬─────────┐        ┌───────────┬─────────┐        ┌───────────┬─────────┐
│ Signals   │ Horizon │        │ Signals   │  Map    │        │ Evidence  │ Verify  │
│ (R/P/Y)   ├─────────┤        ├───────────┼─────────┤        │           │         │
│           │ RC In   │        │ Events    │ (Timeline│        │           │         │
└───────────┴─────────┘        └───────────┴ bottom) ┘        └───────────┴─────────┘
  + Timeline transport           + Timeline transport           + Timeline transport
```
These map 1:1 to your examples (Pilot = Signals+Horizon+RC; Accident =
Signals+Timeline+Map+Events; Certification = Evidence+Verification+Timeline).

---

## Evaluation — A/B/C/D

**A. Detachable panels — recommend YES (for glance surfaces).** Each workspace panel
gets a `⇱ pop out` → floating window that *still follows the cursor*. Low risk: those
surfaces (Horizon/RC/Map/Replay) are read-only and already synced. This is the
mechanism that enables multi-monitor.

**B. Docking system — recommend a *curated* split, NOT a free-form dock manager.** A
small set of split templates (1 / 2 / 3 / 4-pane) with per-panel surface selection
covers ~95 % of needs. A CAD-style "dock anything anywhere" manager is over-built for
this audience — users get lost rearranging instead of investigating. Curated layouts +
pop-out is the sweet spot. *(This is the one place to resist scope creep.)*

**C. Saved workspace layouts — recommend YES; this is the highest-value piece.** Ship
the three named presets above + a Debrief landing default + "Save current layout as…".
A named layout is what actually keeps the investigator *inside one workspace* — one
click puts the right surfaces on screen for the task at hand.

**D. Multi-monitor — recommend YES, via pop-out (no special logic).** Floating panels
that remember their screen/position cover it: primary monitor = Signals + Timeline +
Context; monitor 2 = Horizon + RC + Map + Replay. Big for flight-test benches and
accident labs. Don't build bespoke multi-monitor code beyond persistent floating
windows.

---

## Honest caveats
- **Don't promise "all six panels on one laptop screen."** Signals needs width, Map and
  Horizon want square; six tiles on 1080p are each unusable. Presets should target
  **2–3 panels per screen** and use pop-out / monitor-2 for the rest. Be explicit about
  this in the UI (presets sized for the current screen).
- **The backbone already exists** (shared cursor, named cursor subscribers, persistent
  Context dock, Situation already co-locates Horizon+RC). So the workspace is a
  layout/host/preset feature, not an analysis rewrite — relatively cheap for the payoff.
- **Replay** must drive the cursor (it now does, P3.3a) for the workspace to animate
  coherently — already handled.

## Priority (max switching-reduction per effort)
1. **Timeline persistent bottom transport** — removes the most switches; cheapest.
2. **Workspace split + the 3 saved layouts** — the core ask; one click = the right view.
3. **Panel pop-out / float (multi-monitor)** — for benches and labs.
4. **User "save custom layout"** — power users.
5. *Skip:* free-form dock-everywhere manager — over-engineered.

**Goal restated:** the investigator scrubs once on a persistent timeline and *watches*
the plot, the attitude, the sticks, the map, and the context update together — never
leaving the workspace. The data is already synchronized; this makes it *visible*.
