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

STATE_BADGE_COLORS = {
    'VERIFIED':        ('#198754', '#d1e7dd'),
    'UNVERIFIED':      ('#856404', '#fff3cd'),
    'KEY_MISMATCH':    ('#e65100', '#ffe0b2'),
    'TAMPERED':        ('#dc3545', '#f8d7da'),
    'STRUCTURE_ERROR': ('#dc3545', '#f8d7da'),
    'NOT_SIGNED':      ('#6c757d', '#e2e3e5'),
}


def badge_style(state: str) -> tuple:
    return STATE_BADGE_COLORS.get(state, ('#6c757d', '#e2e3e5'))
