def viridis(t: float) -> tuple:
    stops = [
        (0.267, 0.005, 0.329),
        (0.190, 0.407, 0.553),
        (0.128, 0.566, 0.551),
        (0.369, 0.788, 0.383),
        (0.993, 0.906, 0.144),
    ]
    t = max(0.0, min(1.0, t))
    idx = t * (len(stops) - 1)
    lo = stops[int(idx)]
    hi = stops[min(int(idx) + 1, len(stops) - 1)]
    f = idx - int(idx)
    return tuple(lo[i] * (1 - f) + hi[i] * f for i in range(3))


def viridis_rgba(t: float, alpha: float = 1.0) -> tuple:
    r, g, b = viridis(t)
    return (r, g, b, alpha)


# Mission-planner altitude ramp: low → high = blue → green → yellow → orange → red.
# Intuitive for altitude (unlike viridis), matching the on-map legend.
_ALT_STOPS = [
    (0.00, (40, 110, 255)),    # lowest  — blue
    (0.25, (40, 200, 120)),    # low     — green
    (0.50, (245, 225, 40)),    # medium  — yellow
    (0.75, (255, 140, 30)),    # high    — orange
    (1.00, (230, 40, 40)),     # highest — red
]


def altitude_rgb(t: float) -> tuple:
    """Altitude fraction 0..1 → (r,g,b) 0-255, blue(low) → red(high)."""
    t = max(0.0, min(1.0, t))
    for i in range(len(_ALT_STOPS) - 1):
        t0, c0 = _ALT_STOPS[i]
        t1, c1 = _ALT_STOPS[i + 1]
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(c0[k] * (1 - f) + c1[k] * f) for k in range(3))
    return _ALT_STOPS[-1][1]


SIGNAL_PALETTE = [
    '#1f77b4',
    '#ff7f0e',
    '#2ca02c',
    '#d62728',
    '#9467bd',
    '#8c564b',
    '#e377c2',
    '#7f7f7f',
    '#bcbd22',
    '#17becf',
    '#aec7e8',
    '#ffbb78',
]


def signal_color(index: int) -> str:
    return SIGNAL_PALETTE[index % len(SIGNAL_PALETTE)]


SEVERITY_COLORS = {
    'CRITICAL': '#dc3545',
    'ERROR':    '#fd7e14',
    'WARNING':  '#ffc107',
    'INFO':     '#4a90d9',
}

SEVERITY_ROW_BG = {
    'CRITICAL': 'rgba(220,53,69,0.15)',
    'ERROR':    'rgba(253,126,20,0.15)',
    'WARNING':  'rgba(255,193,7,0.15)',
    'INFO':     'transparent',
}

def badge_style(state: str) -> tuple:
    """(foreground, background) hex for a verification badge.

    Delegates to the single source of truth in core.verification_model so badge
    colours never drift from the operational classification. Accepts operational or
    legacy state strings (normalized inside the model).
    """
    from core import verification_model as vmodel
    return vmodel.badge_colors(state)
