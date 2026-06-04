"""
Flight Intelligence Layer (P3) — whole-flight analytics.

This is the layer the operational review found missing: it ingests a whole flight
and answers "was this a good flight?" before "what happened at 148 s?". Pure core
(numpy), no Qt. Everything is computed over the **armed window(s)** so pre-arm bench
time and post-landing idle don't pollute the metrics.

Produces:
  - TrackingMetrics      attitude demand-vs-response error (per axis)
  - SmoothnessMetrics    pilot control activity / smoothness (per axis)
  - YawDiscipline        heading hold + yaw control discipline
  - LandingQuality       touchdown vertical rate + classification
  - Oscillation          per-axis sustained-oscillation detection (FFT)
  - Saturation           motor / controller-output / throttle saturation
  - Finding              automated findings (severity, window, evidence)
  - PilotScorecard       per-category 0-100 scores + grade
  - FlightQuality        overall verdict ("GOOD"/"ACCEPTABLE"/…) + headline
  - FlightReport         the aggregate, with to_dict() for evidence export

Design notes:
  - Robust to missing messages: a metric that can't be computed is None and is
    excluded from scoring (never fabricated).
  - Scores are documented heuristics, conservative, ArduPilot-aligned.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import numpy as np

from core.timeline_model import TimelineModel
from core.rc_model import RCModel, params_from_data
from core.anomaly_detector import detect_anomalies


# ── tunables (documented) ────────────────────────────────────────────────────
_TRACK_TOL_DEG = 5.0        # attitude error within tolerance
_YAW_TOL_DEG = 8.0
_OSC_MIN_HZ, _OSC_MAX_HZ = 0.4, 20.0
_OSC_AMP_WARN, _OSC_AMP_CRIT = 2.0, 5.0     # deg, sustained oscillation amplitude
_OSC_CONCENTRATION = 0.12   # peak power / total AC power → "a single frequency"
_SAT_FRAC_WARN, _SAT_FRAC_CRIT = 0.05, 0.20  # fraction of armed time saturated
_OUT_SAT = 0.95             # |RATE.*Out| above this = controller output saturated
_PWM_MARGIN = 0.03          # within 3% of min/max = motor saturated
_LAND_SMOOTH, _LAND_FIRM, _LAND_HARD = 1.0, 2.0, 3.0   # m/s touchdown rate bands
_GRADES = [(90, 'A'), (80, 'B'), (70, 'C'), (60, 'D'), (0, 'F')]
_AXES = ('roll', 'pitch', 'yaw')


# ── result types ─────────────────────────────────────────────────────────────

@dataclass
class TrackingAxis:
    axis: str
    rms_deg: float
    max_deg: float
    pct_in_tol: float            # 0..100
    score: float                 # 0..100


@dataclass
class SmoothnessAxis:
    axis: str
    activity: float              # mean |stick rate| (norm/s)
    reversals_per_s: float
    score: float


@dataclass
class YawDiscipline:
    tracking_rms_deg: Optional[float]
    activity: Optional[float]
    large_corrections: int
    score: float


@dataclass
class LandingQuality:
    detected: bool
    touchdown_time: Optional[float]
    touchdown_rate_mps: Optional[float]    # +down magnitude
    classification: str                    # SMOOTH/FIRM/HARD/SEVERE/UNKNOWN
    score: Optional[float]


@dataclass
class Oscillation:
    axis: str
    detected: bool
    freq_hz: Optional[float]
    amplitude_deg: Optional[float]
    severity: str                          # OK/WARNING/CRITICAL


@dataclass
class Saturation:
    motor_pct: Optional[float]             # % armed time any motor saturated
    output_pct: Optional[float]            # % time controller output saturated
    throttle_pct: Optional[float]
    severity: str
    score: float


@dataclass
class Finding:
    severity: str                          # INFO/WARNING/ERROR/CRITICAL
    category: str
    title: str
    detail: str
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    evidence: list = field(default_factory=list)   # signal/metric references


@dataclass
class CategoryScore:
    name: str
    score: Optional[float]
    grade: Optional[str]
    detail: str = ''


@dataclass
class PilotScorecard:
    categories: list                       # [CategoryScore]
    overall: Optional[float]
    grade: Optional[str]


@dataclass
class FlightQuality:
    score: Optional[float]                 # 0..100
    verdict: str                           # GOOD/ACCEPTABLE/MARGINAL/POOR/NO DATA
    headline: str
    factors: list                          # short strings


@dataclass
class FlightReport:
    armed_duration_s: float
    flight_count: int
    quality: FlightQuality
    scorecard: PilotScorecard
    tracking: list                         # [TrackingAxis]
    smoothness: list                       # [SmoothnessAxis]
    yaw: YawDiscipline
    landing: LandingQuality
    oscillations: list                     # [Oscillation]
    saturation: Saturation
    findings: list                         # [Finding]

    def to_dict(self) -> dict:
        return asdict(self)


# ── helpers ──────────────────────────────────────────────────────────────────

def _grade(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    for thr, g in _GRADES:
        if score >= thr:
            return g
    return 'F'


def _ang_err(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Signed smallest angular difference a-b (deg), yaw-wrap aware."""
    return (a - b + 180.0) % 360.0 - 180.0


class FlightAnalytics:
    def __init__(self, data: dict, timeline: Optional[TimelineModel] = None):
        self._d = data or {}
        self._tl = timeline or TimelineModel(self._d)
        self._params = params_from_data(self._d)
        self._rc = RCModel(self._params)
        regions = self._tl.arm_regions()
        if regions:
            self._windows = [(r.t_start, r.t_end) for r in regions]
        else:
            span = self._tl.log_span()
            self._windows = [span] if span[1] > span[0] else []
        self._armed_s = sum(b - a for a, b in self._windows)

    # -- series access (armed-window-masked) --

    def _series(self, msg: str, col: str):
        df = self._d.get(msg)
        if df is None or getattr(df, 'empty', True):
            return None, None
        if 'TimeS' not in df.columns or col not in df.columns:
            return None, None
        t = df['TimeS'].to_numpy(float)
        v = df[col].to_numpy(float)
        order = np.argsort(t)
        t, v = t[order], v[order]
        if self._windows:
            mask = np.zeros(t.shape, bool)
            for a, b in self._windows:
                mask |= (t >= a) & (t <= b)
            t, v = t[mask], v[mask]
        good = np.isfinite(v)
        return t[good], v[good]

    def _aligned(self, msg: str, col_a: str, col_b: str):
        """Two columns of one message on the same (col_a's) time grid."""
        ta, a = self._series(msg, col_a)
        tb, b = self._series(msg, col_b)
        if ta is None or tb is None or ta.size < 2 or tb.size < 2:
            return None, None, None
        b_on_a = np.interp(ta, tb, b)
        return ta, a, b_on_a

    # ── tracking ────────────────────────────────────────────────────────────

    def tracking(self) -> list:
        out = []
        cols = {'roll': ('Roll', 'DesRoll'), 'pitch': ('Pitch', 'DesPitch'),
                'yaw': ('Yaw', 'DesYaw')}
        for axis, (act, des) in cols.items():
            t, a, d = self._aligned('ATT', act, des)
            if t is None:
                continue
            err = np.abs(_ang_err(a, d))
            rms = float(np.sqrt(np.mean(err ** 2)))
            mx = float(np.max(err))
            tol = _YAW_TOL_DEG if axis == 'yaw' else _TRACK_TOL_DEG
            pct = float(np.mean(err <= tol) * 100.0)
            # score: 100 at 0 rms, ~0 at 3×tol rms
            score = float(np.clip(100.0 * (1.0 - rms / (3.0 * tol)), 0, 100))
            out.append(TrackingAxis(axis, rms, mx, pct, score))
        return out

    # ── pilot control smoothness ──────────────────────────────────────────────

    def _norm_input(self, axis: str):
        """Normalised pilot input series for an axis (−1..1 / 0..1)."""
        ch = self._rc.channel_for(axis)
        t, pwm = self._series('RCIN', f'C{ch}')
        if t is None or t.size < 3:
            return None, None
        cfg = self._rc.config_for(axis)
        if axis == 'throttle':
            span = max(cfg.pmax - cfg.pmin, 1.0)
            n = np.clip((pwm - cfg.pmin) / span, 0, 1)
        else:
            half = max((cfg.pmax - cfg.pmin) / 2.0, 1.0)
            n = np.clip((pwm - cfg.ptrim) / half, -1, 1)
        return t, n

    def smoothness(self) -> list:
        out = []
        for axis in _AXES:
            t, n = self._norm_input(axis)
            if t is None or t.size < 3:
                continue
            dt = np.diff(t)
            dt[dt <= 0] = np.nan
            rate = np.diff(n) / dt
            rate = rate[np.isfinite(rate)]
            if rate.size == 0:
                continue
            activity = float(np.mean(np.abs(rate)))
            # reversals: sign changes of rate above a small deadband
            sig = np.sign(np.where(np.abs(rate) > 0.05, rate, 0))
            sig = sig[sig != 0]
            reversals = int(np.sum(np.abs(np.diff(sig)) > 0)) if sig.size > 1 else 0
            rev_per_s = reversals / max(self._armed_s, 1e-6)
            # score: smooth ~ low reversal rate; ~100 at 0, ~0 at 2 rev/s
            score = float(np.clip(100.0 * (1.0 - rev_per_s / 2.0), 0, 100))
            out.append(SmoothnessAxis(axis, activity, rev_per_s, score))
        return out

    # ── yaw discipline ────────────────────────────────────────────────────────

    def yaw_discipline(self) -> YawDiscipline:
        t, a, d = self._aligned('ATT', 'Yaw', 'DesYaw')
        rms = None
        if t is not None:
            rms = float(np.sqrt(np.mean(_ang_err(a, d) ** 2)))
        # yaw control activity + large corrections (from yaw stick)
        ty, ny = self._norm_input('yaw')
        activity = large = None
        if ty is not None and ty.size > 2:
            activity = float(np.mean(np.abs(ny)))
            large = int(np.sum(np.abs(ny) > 0.5))
        # score: blend tracking + restraint
        parts = []
        if rms is not None:
            parts.append(np.clip(100 * (1 - rms / (3 * _YAW_TOL_DEG)), 0, 100))
        if activity is not None:
            parts.append(np.clip(100 * (1 - activity / 0.5), 0, 100))
        score = float(np.mean(parts)) if parts else None
        return YawDiscipline(rms, activity, int(large or 0), score)

    # ── landing quality ───────────────────────────────────────────────────────

    def _agl(self):
        # reuse the timeline's altitude profile (documented hierarchy)
        ap = self._tl.altitude_profile(max_points=100000)
        return (ap.times, ap.agl) if not ap.empty else (None, None)

    def _vspeed_series(self):
        for msg, col, sign in [('BARO[0]', 'CRt', 1.0), ('BARO', 'CRt', 1.0),
                               ('CTUN', 'CRt', 1.0)]:
            t, v = self._series(msg, col)
            if t is not None and t.size > 1:
                return t, sign * v
        # derive from AGL
        ta, agl = self._agl()
        if ta is not None and ta.size > 2:
            return ta[1:], np.diff(agl) / np.clip(np.diff(ta), 1e-3, None)
        return None, None

    def landing(self) -> LandingQuality:
        ta, agl = self._agl()
        if ta is None or ta.size < 3 or not self._windows:
            return LandingQuality(False, None, None, 'UNKNOWN', None)
        end = self._windows[-1][1]
        in_win = ta <= end
        ta, agl = ta[in_win], agl[in_win]
        # last clearly-airborne sample (>3 m), then the FIRST ground contact after
        # it — that crossing is the touchdown (not the end of ground-idle).
        air = np.where(agl > 3.0)[0]
        if air.size == 0:
            return LandingQuality(False, None, None, 'UNKNOWN', None)
        after = np.where((np.arange(agl.size) > air[-1]) & (agl < 1.0))[0]
        if after.size == 0:
            return LandingQuality(False, None, None, 'UNKNOWN', None)
        td_t = float(ta[after[0]])
        tv, vs = self._vspeed_series()
        rate = None
        if tv is not None:
            # peak descent rate in the 3 s up to touchdown
            w = (tv >= td_t - 3.0) & (tv <= td_t + 0.25)
            if np.any(w):
                rate = float(abs(min(0.0, float(np.min(vs[w])))))
        if rate is None:
            return LandingQuality(True, td_t, None, 'UNKNOWN', None)
        if rate < _LAND_SMOOTH:
            cls, score = 'SMOOTH', 100.0
        elif rate < _LAND_FIRM:
            cls, score = 'FIRM', 80.0
        elif rate < _LAND_HARD:
            cls, score = 'HARD', 50.0
        else:
            cls, score = 'SEVERE', 20.0
        return LandingQuality(True, td_t, rate, cls, score)

    # ── oscillation ───────────────────────────────────────────────────────────

    def oscillations(self) -> list:
        out = []
        cols = {'roll': ('Roll', 'DesRoll'), 'pitch': ('Pitch', 'DesPitch'),
                'yaw': ('Yaw', 'DesYaw')}
        for axis, (act, des) in cols.items():
            t, a, d = self._aligned('ATT', act, des)
            if t is None or t.size < 32:
                out.append(Oscillation(axis, False, None, None, 'OK'))
                continue
            err = _ang_err(a, d)
            res = self._fft_osc(t, err)
            out.append(Oscillation(axis, *res))
        return out

    @staticmethod
    def _fft_osc(t: np.ndarray, sig: np.ndarray):
        """(detected, freq, amplitude_deg, severity) via uniform resample + rFFT.
        Oscillation = a concentrated spectral peak in [_OSC_MIN_HZ, _OSC_MAX_HZ]."""
        t0, t1 = t[0], t[-1]
        dur = t1 - t0
        if dur < 2.0:
            return (False, None, None, 'OK')
        fs = 50.0
        n = int(dur * fs)
        if n < 32:
            return (False, None, None, 'OK')
        tu = np.linspace(t0, t1, n)
        su = np.interp(tu, t, sig)
        su = su - np.mean(su)
        su *= np.hanning(n)
        spec = np.abs(np.fft.rfft(su))
        freqs = np.fft.rfftfreq(n, 1.0 / fs)
        band = (freqs >= _OSC_MIN_HZ) & (freqs <= _OSC_MAX_HZ)
        if not np.any(band):
            return (False, None, None, 'OK')
        ac_power = float(np.sum(spec[freqs > 0.05] ** 2)) + 1e-9
        bspec = spec.copy(); bspec[~band] = 0
        pk = int(np.argmax(bspec))
        peak_power = float(spec[pk] ** 2)
        # amplitude of the peak sinusoid (un-windowed scale ≈ 2/N * coherent gain)
        amp = float(spec[pk] * 2.0 / n / 0.5)
        concentration = peak_power / ac_power
        freq = float(freqs[pk])
        detected = (amp >= _OSC_AMP_WARN and concentration >= _OSC_CONCENTRATION)
        if not detected:
            return (False, freq if amp >= _OSC_AMP_WARN else None,
                    amp if amp >= 0.5 else None, 'OK')
        sev = 'CRITICAL' if amp >= _OSC_AMP_CRIT else 'WARNING'
        return (True, freq, amp, sev)

    # ── saturation ────────────────────────────────────────────────────────────

    def saturation(self) -> Saturation:
        motor_pct = self._motor_sat_pct()
        output_pct = self._output_sat_pct()
        throttle_pct = self._throttle_sat_pct()
        worst = max([p for p in (motor_pct, output_pct, throttle_pct) if p is not None],
                    default=None)
        if worst is None:
            sev, score = 'OK', 100.0
        else:
            frac = worst / 100.0
            sev = ('CRITICAL' if frac >= _SAT_FRAC_CRIT
                   else 'WARNING' if frac >= _SAT_FRAC_WARN else 'OK')
            score = float(np.clip(100.0 * (1.0 - frac / _SAT_FRAC_CRIT), 0, 100))
        return Saturation(motor_pct, output_pct, throttle_pct, sev, score)

    def _motor_range(self):
        lo = self._params.get('MOT_PWM_MIN', 0) or 0
        hi = self._params.get('MOT_PWM_MAX', 0) or 0
        if not (lo and hi and hi > lo):
            lo, hi = 1000.0, 2000.0
        return float(lo), float(hi)

    def _motor_sat_pct(self):
        """% of armed time the most-saturated motor sits within _PWM_MARGIN of the
        physical PWM range (MOT_PWM_MIN/MAX, default 1000–2000)."""
        if 'RCOU' not in self._d:
            return None
        lo, hi = self._motor_range()
        margin = _PWM_MARGIN * (hi - lo)
        fracs = []
        for c in ('C1', 'C2', 'C3', 'C4'):
            t, v = self._series('RCOU', c)
            if t is None or t.size == 0:
                continue
            sat = (v >= hi - margin) | (v <= lo + margin)
            fracs.append(float(np.mean(sat)))
        return max(fracs) * 100.0 if fracs else None

    def _output_sat_pct(self):
        if 'RATE' not in self._d:
            return None
        fracs = []
        for col in ('ROut', 'POut', 'YOut'):
            t, v = self._series('RATE', col)
            if t is not None and t.size:
                fracs.append(np.mean(np.abs(v) >= _OUT_SAT))
        if not fracs:
            return None
        return float(np.max(fracs) * 100.0)

    def _throttle_sat_pct(self):
        t, v = self._series('CTUN', 'ThO')
        if t is None or t.size == 0:
            return None
        return float(np.mean(v >= _OUT_SAT) * 100.0)

    # ── findings (automated) ──────────────────────────────────────────────────

    def findings(self, tracking, oscillations, saturation, landing, yaw) -> list:
        f = []
        # oscillation
        for o in oscillations:
            if o.detected:
                f.append(Finding(o.severity, 'OSCILLATION',
                                 f'{o.axis.capitalize()} oscillation',
                                 f'Sustained {o.freq_hz:.1f} Hz oscillation, '
                                 f'amplitude {o.amplitude_deg:.1f}°',
                                 evidence=[f'ATT.{o.axis.capitalize()}',
                                           f'ATT.Des{o.axis.capitalize()}']))
        # tracking
        for tr in tracking:
            if tr.score < 60:
                f.append(Finding('WARNING', 'TRACKING',
                                 f'Poor {tr.axis} tracking',
                                 f'{tr.axis.capitalize()} demand-vs-response RMS '
                                 f'{tr.rms_deg:.1f}°, only {tr.pct_in_tol:.0f}% in tolerance',
                                 evidence=[f'ATT.{tr.axis.capitalize()}',
                                           f'ATT.Des{tr.axis.capitalize()}']))
        # saturation
        if saturation.severity != 'OK':
            worst = max([p for p in (saturation.motor_pct, saturation.output_pct,
                                     saturation.throttle_pct) if p is not None], default=0)
            f.append(Finding(saturation.severity, 'SATURATION',
                             'Controller / actuator saturation',
                             f'Saturated {worst:.0f}% of armed time '
                             f'(motors {saturation.motor_pct or 0:.0f}%, '
                             f'output {saturation.output_pct or 0:.0f}%)',
                             evidence=['RCOU.C1-4', 'RATE.ROut/POut/YOut']))
        # landing
        if landing.detected and landing.classification in ('HARD', 'SEVERE'):
            sev = 'CRITICAL' if landing.classification == 'SEVERE' else 'WARNING'
            f.append(Finding(sev, 'LANDING', f'{landing.classification.title()} landing',
                             f'Touchdown descent rate {landing.touchdown_rate_mps:.1f} m/s',
                             t_start=landing.touchdown_time,
                             evidence=['BARO.CRt', 'POS.RelHomeAlt']))
        # yaw discipline
        if yaw.score is not None and yaw.score < 60:
            f.append(Finding('WARNING', 'YAW', 'Excessive yaw correction',
                             f'Yaw discipline score {yaw.score:.0f} '
                             f'({yaw.large_corrections} large yaw inputs)',
                             evidence=['ATT.Yaw', 'ATT.DesYaw', 'RCIN(yaw)']))
        # systems anomalies (reuse existing detector; convert rel→abs)
        t0 = self._tl.log_span()[0]
        for tr, sev, cat, msg in detect_anomalies(self._d):
            f.append(Finding(sev, cat, f'{cat} anomaly', msg, t_start=tr + t0,
                             evidence=[cat]))
        order = {'CRITICAL': 0, 'ERROR': 1, 'WARNING': 2, 'INFO': 3}
        f.sort(key=lambda x: (order.get(x.severity, 9), x.t_start if x.t_start else 0))
        return f

    # ── scorecard + overall ───────────────────────────────────────────────────

    def scorecard(self, tracking, smoothness, yaw, landing) -> PilotScorecard:
        cats = []
        if tracking:
            s = float(np.mean([tr.score for tr in tracking]))
            cats.append(CategoryScore('Attitude tracking', s, _grade(s),
                                      'demand vs response'))
        if smoothness:
            s = float(np.mean([sm.score for sm in smoothness]))
            cats.append(CategoryScore('Control smoothness', s, _grade(s),
                                      'pilot input activity'))
        if yaw.score is not None:
            cats.append(CategoryScore('Yaw discipline', yaw.score, _grade(yaw.score),
                                      'heading hold + restraint'))
        if landing.score is not None:
            cats.append(CategoryScore('Landing quality', landing.score,
                                      _grade(landing.score), landing.classification))
        scores = [c.score for c in cats if c.score is not None]
        overall = float(np.mean(scores)) if scores else None
        return PilotScorecard(cats, overall, _grade(overall))

    def quality(self, tracking, oscillations, saturation, scorecard, findings) -> FlightQuality:
        if self._armed_s <= 0 or not tracking:
            return FlightQuality(None, 'NO DATA',
                                 'Insufficient data for a flight-quality assessment.', [])
        comps, factors = [], []
        track = float(np.mean([t.score for t in tracking]))
        comps.append(('Tracking', track, 0.30))
        factors.append(f'tracking {track:.0f}')
        stab = min([100.0] + [(40 if o.severity == 'CRITICAL' else 70)
                              for o in oscillations if o.detected])
        comps.append(('Stability', stab, 0.25))
        if stab < 100:
            factors.append('oscillation detected')
        comps.append(('Saturation', saturation.score, 0.15))
        if saturation.severity != 'OK':
            factors.append('saturation')
        if scorecard.overall is not None:
            comps.append(('Pilot', scorecard.overall, 0.30))
        crit = sum(1 for f in findings if f.severity == 'CRITICAL')
        wgt = sum(w for _, _, w in comps)
        score = sum(s * w for _, s, w in comps) / wgt if wgt else None
        if crit:
            score = min(score, 55.0) if score is not None else None
            factors.append(f'{crit} critical finding(s)')
        if score is None:
            verdict, head = 'NO DATA', 'Insufficient data.'
        elif score >= 85:
            verdict, head = 'GOOD', 'Good flight — clean tracking and stable control.'
        elif score >= 70:
            verdict, head = 'ACCEPTABLE', 'Acceptable flight with minor issues.'
        elif score >= 50:
            verdict, head = 'MARGINAL', 'Marginal flight — review the findings.'
        else:
            verdict, head = 'POOR', 'Poor flight — significant issues detected.'
        return FlightQuality(score, verdict, head, factors)

    # ── top-level ─────────────────────────────────────────────────────────────

    def report(self) -> FlightReport:
        tracking = self.tracking()
        smoothness = self.smoothness()
        yaw = self.yaw_discipline()
        landing = self.landing()
        osc = self.oscillations()
        sat = self.saturation()
        findings = self.findings(tracking, osc, sat, landing, yaw)
        scorecard = self.scorecard(tracking, smoothness, yaw, landing)
        quality = self.quality(tracking, osc, sat, scorecard, findings)
        return FlightReport(
            armed_duration_s=self._armed_s, flight_count=len(self._windows),
            quality=quality, scorecard=scorecard, tracking=tracking,
            smoothness=smoothness, yaw=yaw, landing=landing,
            oscillations=osc, saturation=sat, findings=findings)


def analyze(data: dict, timeline: Optional[TimelineModel] = None) -> FlightReport:
    return FlightAnalytics(data, timeline).report()
