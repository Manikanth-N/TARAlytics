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


def best_trajectory(data: dict) -> dict:
    gps_df = data.get('GPS')
    enu = gps_df_to_enu(gps_df) if gps_df is not None else None
    if enu is not None:
        return enu

    sim2_df = data.get('SIM2')
    enu = sim2_df_to_enu(sim2_df) if sim2_df is not None else None
    if enu is not None:
        return enu

    sim_df = data.get('SIM')
    if sim_df is not None:
        for pn, pe, pd_col in [('PN', 'PE', 'PD'), ('Px', 'Py', 'Pz')]:
            if {pn, pe, pd_col}.issubset(sim_df.columns):
                east = sim_df[pe].values.astype(float)
                north = sim_df[pn].values.astype(float)
                up = -sim_df[pd_col].values.astype(float)
                times = sim_df['TimeS'].values if 'TimeS' in sim_df.columns else np.zeros(len(east))
                return {'east': east, 'north': north, 'up': up, 'times': times,
                        'origin_lat': 0.0, 'origin_lon': 0.0, 'origin_alt': 0.0}
    return None
