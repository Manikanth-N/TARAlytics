import math
import numpy as np


def lla_to_enu(lat: float, lon: float, alt: float,
               lat0: float, lon0: float, alt0: float) -> tuple:
    R = 6378137.0
    d_lat = math.radians(lat - lat0)
    d_lon = math.radians(lon - lon0)
    d_alt = alt - alt0
    n = R * d_lat
    e = R * math.cos(math.radians(lat0)) * d_lon
    u = d_alt
    return e, n, u


def gps_df_to_enu(gps_df, lat_col='Lat', lng_col='Lng', alt_col='Alt'):
    if gps_df is None or gps_df.empty:
        return None
    if lat_col not in gps_df.columns or lng_col not in gps_df.columns:
        return None                 # source carries no position → caller falls through
    lats = gps_df[lat_col].values
    lngs = gps_df[lng_col].values
    alts = gps_df[alt_col].values if alt_col in gps_df.columns else np.zeros(len(lats))

    valid = np.abs(lats) > 0.001
    if not np.any(valid):
        return None

    lat0 = lats[valid][0]
    lon0 = lngs[valid][0]
    alt0 = alts[valid][0]

    R = 6378137.0
    cos_lat0 = math.cos(math.radians(lat0))
    east = R * np.radians(lngs - lon0) * cos_lat0
    north = R * np.radians(lats - lat0)
    up = alts - alt0

    rng = np.sqrt((east - east[0]) ** 2 + (north - north[0]) ** 2).max()
    if rng < 1.0:
        return None

    times = gps_df['TimeS'].values if 'TimeS' in gps_df.columns else np.zeros(len(lats))
    return {
        'east': east,
        'north': north,
        'up': up,
        'times': times,
        'origin_lat': lat0,
        'origin_lon': lon0,
        'origin_alt': alt0,
    }


def sim2_df_to_enu(sim2_df):
    if sim2_df is None or sim2_df.empty:
        return None
    required = {'PN', 'PE', 'PD'}
    if not required.issubset(sim2_df.columns):
        return None
    east = sim2_df['PE'].values.astype(float)
    north = sim2_df['PN'].values.astype(float)
    up = -sim2_df['PD'].values.astype(float)
    times = sim2_df['TimeS'].values if 'TimeS' in sim2_df.columns else np.zeros(len(east))
    return {
        'east': east,
        'north': north,
        'up': up,
        'times': times,
        'origin_lat': 0.0,
        'origin_lon': 0.0,
        'origin_alt': 0.0,
    }


# Peak-to-peak (metres) below which an altitude channel is treated as "flat" — a
# source carrying no real vertical motion (e.g. an unpopulated GPS.Alt = 0).
_ALT_FLAT_EPS = 1.0


def _alt_candidates(data: dict) -> list:
    """Altitude channels in preferred order: POS.RelHomeAlt (AGL) → BARO.Alt →
    GPS.Alt. Returns (label, times, values, home_relative) tuples for those present."""
    out = []
    pos = data.get('POS')
    if pos is not None and 'RelHomeAlt' in pos.columns and 'TimeS' in pos.columns:
        out.append(('POS.RelHomeAlt', pos['TimeS'].values.astype(float),
                    pos['RelHomeAlt'].values.astype(float), True))
    for bkey in ('BARO', 'BARO[0]'):
        b = data.get(bkey)
        if b is not None and 'Alt' in b.columns and 'TimeS' in b.columns:
            out.append((f'{bkey}.Alt', b['TimeS'].values.astype(float),
                        b['Alt'].values.astype(float), False))
            break
    for gkey in ['GPS'] + [f'GPS[{i}]' for i in range(8)]:
        g = data.get(gkey)
        if g is not None and 'Alt' in g.columns and 'TimeS' in g.columns:
            out.append((f'{gkey}.Alt', g['TimeS'].values.astype(float),
                        g['Alt'].values.astype(float), False))
            break
    return out


def _best_altitude(data: dict, times: np.ndarray):
    """Pick the highest-priority *non-flat* altitude channel and interpolate it onto
    the trajectory's timestamps. Returns (up, source_label) or (None, None).

    POS.RelHomeAlt is kept absolute (0 = home / AGL); other channels are made
    relative to their first sample so the path still starts near zero.
    """
    cands = _alt_candidates(data)
    chosen = None
    for label, ts, vs, home_rel in cands:
        if vs.size and np.ptp(vs) >= _ALT_FLAT_EPS:   # reject flat channels
            chosen = (label, ts, vs, home_rel)
            break
    if chosen is None:
        return None, None     # no varying channel → caller keeps existing altitude
    label, ts, vs, home_rel = chosen
    if ts.size >= 2 and np.ptp(ts) > 0:
        order = np.argsort(ts)
        up = np.interp(times, ts[order], vs[order])
    else:
        up = np.full(len(times), float(vs[0]) if vs.size else 0.0)
    if not home_rel and len(up):
        up = up - up[0]
    return up, label


def best_trajectory(data: dict) -> dict:
    # ── Horizontal track (E/N + time base) ───────────────────────────────────
    enu = None
    src = None
    for key in ['GPS'] + [f'GPS[{i}]' for i in range(8)]:
        gps_df = data.get(key)
        if gps_df is None:
            continue
        enu = gps_df_to_enu(gps_df)
        if enu is not None:
            src = key
            break

    if enu is None:
        pos_df = data.get('POS')
        if pos_df is not None:
            enu = gps_df_to_enu(pos_df)
            if enu is not None:
                src = 'POS'

    if enu is None:
        sim2_df = data.get('SIM2')
        enu = sim2_df_to_enu(sim2_df) if sim2_df is not None else None
        if enu is not None:
            src = 'SIM2'

    if enu is None:
        sim_df = data.get('SIM')
        if sim_df is not None:
            for pn, pe, pd_col in [('PN', 'PE', 'PD'), ('Px', 'Py', 'Pz')]:
                if {pn, pe, pd_col}.issubset(sim_df.columns):
                    east = sim_df[pe].values.astype(float)
                    north = sim_df[pn].values.astype(float)
                    up = -sim_df[pd_col].values.astype(float)
                    times = sim_df['TimeS'].values if 'TimeS' in sim_df.columns else np.zeros(len(east))
                    enu = {'east': east, 'north': north, 'up': up, 'times': times,
                           'origin_lat': 0.0, 'origin_lon': 0.0, 'origin_alt': 0.0}
                    src = 'SIM'
                    break

    if enu is None:
        return None

    # ── Altitude (Z): prefer a varying AGL/baro/GPS channel over a flat one ───
    # The horizontal source's own altitude (e.g. GPS.Alt) is often flat/zero while
    # real vertical motion lives in POS.RelHomeAlt or BARO — so re-select it.
    up2, alt_src = _best_altitude(data, enu['times'])
    if up2 is not None:
        enu['up'] = up2
        enu['alt_source'] = alt_src
    else:
        enu['alt_source'] = f'{src}.Alt' if src else 'unknown'
    enu['pos_source'] = src
    return enu
