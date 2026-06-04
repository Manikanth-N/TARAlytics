"""Navigation module registry — the single source of truth for which modules exist,
their nav-rail labels, and (critically) the *stable* page index each maps to in the
MainWindow page stack.

The navigation rail can show any ordered subset of these modules; because every nav
item carries its `page_index` (not its list position), filtering/reordering the rail
never mis-routes a click. Visibility/order is persisted as a list of string ids
(forward-compatible if page order ever changes).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDef:
    id: str            # stable persistence key
    label: str         # nav-rail label (UPPER)
    page_index: int    # index in MainWindow's QTabWidget page stack
    title: str         # human-readable title (manager dialog)
    description: str    # one-line description (manager dialog)


# Order here is the canonical / "Full" order (matches the page stack).
MODULES = [
    ModuleDef('debrief',   'DEBRIEF',   0, 'Debrief',      'Flight summary, health cards, verification at a glance'),
    ModuleDef('timeline',  'TIMELINE',  1, 'Timeline',     'Full-flight event timeline and phases'),
    ModuleDef('events',    'EVENTS',    2, 'Events',       'Detected events and anomalies table'),
    ModuleDef('situation', 'SITUATION', 3, 'Situation',    'Situational-awareness overview'),
    ModuleDef('signals',   'SIGNALS',   4, 'Signals',      'Multi-signal plotter'),
    ModuleDef('replay',    'REPLAY',    5, 'Replay',       '3D flight replay and attitude'),
    ModuleDef('verify',    'VERIFY',    6, 'Verification', 'Cryptographic signature verification'),
    ModuleDef('map',       'MAP',       7, 'Map',          '2D map and flight path'),
    ModuleDef('evidence',  'EVIDENCE',  8, 'Evidence',     'Investigation snapshots and report export'),
    ModuleDef('workspace', 'WORKSPACE', 9, 'Workspace',    'Multi-panel investigation workspace'),
]

BY_ID = {m.id: m for m in MODULES}
ALL_IDS = [m.id for m in MODULES]

# Built-in presets — ordered id lists (order IS the rail order). Code constants, not
# persisted, so "Restore defaults" can never be corrupted.
PRESETS = {
    'minimal':    ['debrief', 'workspace', 'verify', 'replay', 'map'],
    'flighttest': ['debrief', 'workspace', 'signals', 'replay', 'verify', 'map', 'timeline', 'events'],
    'full':       list(ALL_IDS),
}

# Human labels for the preset selector.
PRESET_LABELS = [('minimal', 'Minimal'), ('flighttest', 'Flight Test'),
                 ('full', 'Full'), ('custom', 'Custom')]


def sanitize(ids) -> list:
    """Drop unknown/duplicate ids, preserve order, guarantee at least one module."""
    out, seen = [], set()
    for i in (ids or []):
        if i in BY_ID and i not in seen:
            out.append(i)
            seen.add(i)
    return out or list(PRESETS['minimal'])


def detect_preset(ids) -> str:
    """Return the built-in preset name matching this exact ordered list, else 'custom'."""
    ids = list(ids)
    for name in ('minimal', 'flighttest', 'full'):
        if ids == PRESETS[name]:
            return name
    return 'custom'


def order_to_navitems(ids) -> list:
    """Map an ordered id list to (page_index, label) pairs for NavigationRail."""
    return [(BY_ID[i].page_index, BY_ID[i].label) for i in sanitize(ids)]


def hidden_ids(ids) -> list:
    """Modules NOT in the given visible list, in canonical order."""
    visible = set(sanitize(ids))
    return [m.id for m in MODULES if m.id not in visible]
