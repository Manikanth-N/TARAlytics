"""
SampleService — value-at-time interpolation engine for the shared cursor.

Every cursor-driven surface (Situational Awareness panel, Values-at-Cursor table,
Investigation Snapshot, Timeline readouts) reads its numbers through this one
service, so there is exactly one interpolation implementation in the codebase.

Design:
- One instance built per parsed log (held by AppState, rebuilt on data_changed).
- Lazy + cached: per-message time arrays and per-column value arrays are built on
  first access (numpy views over the existing DataFrames — no bulk precompute).
- O(log n) lookups via binary search (np.searchsorted).
- Time domain is absolute seconds (the 'TimeS' column).
- Never fabricates: returns None outside a message's time range or for missing
  message/column; NaN-aware.

Continuous signals → value_at() (linear interpolation).
Discrete signals (e.g. MODE) → latest_at() (zero-order hold / step).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Iterable, Union
import math
import numpy as np


# A spec for batch(): either (msg, col) or (label, msg, col).
Spec = Union[tuple[str, str], tuple[str, str, str]]


@dataclass(frozen=True)
class Sample:
    """A resolved value plus its provenance — for Snapshots, Evidence Export,
    and certification. Lightweight: no arrays, just the facts of one lookup."""
    value: Optional[float]
    msg: str                       # source message type
    col: str                       # source field
    t: float                       # query (cursor) time, seconds
    interpolated: bool             # True if linearly interpolated between samples
    sample_t: Optional[float] = None      # actual sample time when not interpolated
    bracket: Optional[tuple] = None       # (t_lower, t_upper) when interpolated

    @property
    def ok(self) -> bool:
        return self.value is not None


class SampleService:
    def __init__(self, data: dict):
        self._data = data or {}
        self._times: dict[str, Optional[np.ndarray]] = {}   # msg -> sorted TimeS
        self._order: dict[str, np.ndarray] = {}             # msg -> argsort indices
        self._vals: dict[tuple, Optional[np.ndarray]] = {}  # (msg,col) -> values (time-sorted)

    # ── internal caches ─────────────────────────────────────────────────────

    def _ensure_times(self, msg: str) -> bool:
        if msg in self._times:
            return self._times[msg] is not None
        df = self._data.get(msg)
        if df is None or df.empty or 'TimeS' not in df.columns:
            self._times[msg] = None
            return False
        t = df['TimeS'].to_numpy(dtype=float)
        # Robust to non-monotonic timestamps: sort once, keep the permutation so
        # value columns can be aligned to the sorted time axis.
        order = np.argsort(t, kind='stable')
        self._times[msg] = t[order]
        self._order[msg] = order
        return True

    def _values(self, msg: str, col: str) -> Optional[np.ndarray]:
        key = (msg, col)
        cached = self._vals.get(key, False)
        if cached is not False:
            return cached
        df = self._data.get(msg)
        if df is None or col not in df.columns:
            self._vals[key] = None
            return None
        v = df[col].to_numpy(dtype=float)[self._order[msg]]
        self._vals[key] = v
        return v

    # ── public API ──────────────────────────────────────────────────────────

    def time_range(self, msg: str) -> Optional[tuple[float, float]]:
        """(t_min, t_max) for a message, or None if unavailable."""
        if not self._ensure_times(msg):
            return None
        t = self._times[msg]
        return float(t[0]), float(t[-1])

    def value_at(self, msg: str, col: str, t: float) -> Optional[float]:
        """
        Linearly interpolated value of msg.col at absolute time t.
        None if the message/column is absent or t is outside the message's range.
        NaN-aware: if one bracketing sample is NaN the other is returned; if both
        are NaN, None.
        """
        if not self._ensure_times(msg):
            return None
        times = self._times[msg]
        vals = self._values(msg, col)
        if vals is None or len(times) == 0:
            return None
        if t < times[0] or t > times[-1]:
            return None
        i = int(np.searchsorted(times, t, side='left'))
        if i <= 0:
            return self._finite_or_none(vals[0])
        if i >= len(times):
            return self._finite_or_none(vals[-1])
        if times[i] == t:
            v = self._finite_or_none(vals[i])
            if v is not None:
                return v
        t0, t1 = times[i - 1], times[i]
        v0, v1 = vals[i - 1], vals[i]
        n0, n1 = math.isnan(v0), math.isnan(v1)
        if n0 and n1:
            return None
        if n0:
            return float(v1)
        if n1:
            return float(v0)
        if t1 == t0:
            return float(v0)
        return float(v0 + (v1 - v0) * (t - t0) / (t1 - t0))

    def latest_at(self, msg: str, col: str, t: float) -> Optional[float]:
        """
        Zero-order hold: value of the most recent sample at or before t (for
        discrete channels like MODE). None if t precedes the first sample.
        """
        if not self._ensure_times(msg):
            return None
        times = self._times[msg]
        vals = self._values(msg, col)
        if vals is None or len(times) == 0 or t < times[0]:
            return None
        i = int(np.searchsorted(times, t, side='right')) - 1
        if i < 0:
            return None
        return self._finite_or_none(vals[i])

    def sample_at(self, msg: str, col: str, t: float) -> Sample:
        """
        Like value_at but returns a Sample with provenance (source msg/field,
        query time, whether the value was interpolated, and the source sample
        time(s)). The authoritative record for Snapshots / Evidence Export.
        Cost is the same as value_at (one binary search); use value_at on the
        hot per-frame path and sample_at when capturing evidence.
        """
        if not self._ensure_times(msg):
            return Sample(None, msg, col, t, False)
        times = self._times[msg]
        vals = self._values(msg, col)
        if vals is None or len(times) == 0 or t < times[0] or t > times[-1]:
            return Sample(None, msg, col, t, False)
        i = int(np.searchsorted(times, t, side='left'))
        # exact hit or endpoints -> not interpolated
        if i <= 0:
            return Sample(self._finite_or_none(vals[0]), msg, col, t, False,
                          sample_t=float(times[0]))
        if i >= len(times):
            return Sample(self._finite_or_none(vals[-1]), msg, col, t, False,
                          sample_t=float(times[-1]))
        if times[i] == t:
            v = self._finite_or_none(vals[i])
            if v is not None:
                return Sample(v, msg, col, t, False, sample_t=float(times[i]))
        v = self.value_at(msg, col, t)
        return Sample(v, msg, col, t, True,
                      bracket=(float(times[i - 1]), float(times[i])))

    def sample_time(self, msg: str, t: float) -> Optional[float]:
        """Timestamp of the sample at-or-before t (the value latest_at returns) —
        for provenance of discrete/held channels. None if t precedes the first."""
        if not self._ensure_times(msg):
            return None
        times = self._times[msg]
        if len(times) == 0 or t < times[0]:
            return None
        i = int(np.searchsorted(times, t, side='right')) - 1
        if i < 0:
            return None
        return float(times[i])

    def index_at(self, msg: str, t: float) -> Optional[int]:
        """Index (in time-sorted order) of the sample at or before t — for
        surfaces that need the row, not just a value (e.g. MSG text, replay)."""
        if not self._ensure_times(msg):
            return None
        times = self._times[msg]
        if len(times) == 0 or t < times[0]:
            return None
        return int(np.searchsorted(times, t, side='right')) - 1

    def batch(self, t: float, specs: Iterable[Spec], step: bool = False) -> dict:
        """
        Resolve many (msg,col) at one time in a single call (for the panel and the
        values-at-cursor table). Keys are the provided label, or 'msg.col'.
        step=True uses latest_at (discrete); default uses value_at (continuous).
        """
        out: dict[str, Optional[float]] = {}
        getter = self.latest_at if step else self.value_at
        for spec in specs:
            if len(spec) == 3:
                label, msg, col = spec
            else:
                msg, col = spec
                label = f'{msg}.{col}'
            out[label] = getter(msg, col, t)
        return out

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _finite_or_none(v) -> Optional[float]:
        v = float(v)
        return None if math.isnan(v) else v
