import numpy as np


def detect_anomalies(data: dict) -> list:
    """
    Scan parsed log data for common flight anomalies.
    Returns list of (time_s_relative, severity, category, message).
    severity: 'WARNING' | 'ERROR' | 'CRITICAL'
    """
    anomalies = []
    t_offset = _global_t_offset(data)

    # EKF innovation faults
    for key in ['XKF4'] + [f'XKF4[{i}]' for i in range(4)]:
        df = data.get(key)
        if df is None or df.empty or 'TimeS' not in df.columns:
            continue
        for col in ('FS', 'fs'):
            if col in df.columns:
                faults = df[df[col] > 0]
                if not faults.empty:
                    t = float(faults['TimeS'].iloc[0]) - t_offset
                    anomalies.append((t, 'ERROR', 'EKF', f'EKF filter fault FS={int(faults[col].iloc[0])}'))
                break

    # GPS quality
    for key in ['GPS'] + [f'GPS[{i}]' for i in range(4)]:
        df = data.get(key)
        if df is None or df.empty or 'TimeS' not in df.columns:
            continue
        hdop_col = next((c for c in ('HDop', 'Hdop', 'hdop') if c in df.columns), None)
        sats_col = next((c for c in ('NSats', 'NSat') if c in df.columns), None)
        if hdop_col:
            bad = df[df[hdop_col] > 2.5]
            if not bad.empty:
                t = float(bad['TimeS'].iloc[0]) - t_offset
                anomalies.append((t, 'WARNING', 'GPS', f'Poor GPS HDOP={float(bad[hdop_col].max()):.2f}'))
        if sats_col:
            low = df[df[sats_col] < 6]
            if not low.empty:
                t = float(low['TimeS'].iloc[0]) - t_offset
                anomalies.append((t, 'WARNING', 'GPS', f'Low GPS sats={int(low[sats_col].min())}'))
        break  # check first GPS instance only

    # Vibration (VIBE message)
    for key in ['VIBE'] + [f'VIBE[{i}]' for i in range(4)]:
        df = data.get(key)
        if df is None or df.empty or 'TimeS' not in df.columns:
            continue
        for ax in ('VibeX', 'VibeY', 'VibeZ'):
            if ax in df.columns:
                high = df[df[ax] > 30.0]
                if not high.empty:
                    t = float(high['TimeS'].iloc[0]) - t_offset
                    anomalies.append((t, 'WARNING', 'VIBE', f'High vibration {ax}={float(high[ax].max()):.1f} m/s²'))
        break

    # Battery low voltage
    bat_df = data.get('BAT')
    if bat_df is not None and not bat_df.empty and 'TimeS' in bat_df.columns:
        for volt_col in ('Volt', 'VoltR'):
            if volt_col in bat_df.columns:
                volts = bat_df[volt_col].dropna()
                vmax = float(volts.max())
                if vmax > 4.0:  # skip SITL logs with dummy voltage
                    low_v = bat_df[bat_df[volt_col] < vmax * 0.85]
                    if not low_v.empty:
                        t = float(low_v['TimeS'].iloc[0]) - t_offset
                        vmin = float(low_v[volt_col].min())
                        anomalies.append((t, 'WARNING', 'POWER', f'Low battery {vmin:.1f} V'))
                break

    # ERR messages (Subsystem errors)
    err_df = data.get('ERR')
    if err_df is not None and not err_df.empty and 'TimeS' in err_df.columns:
        sub_col = next((c for c in ('Subsys', 'SubSys', 'Sub') if c in err_df.columns), None)
        ecode_col = next((c for c in ('ECode', 'ecode', 'Ecode') if c in err_df.columns), None)
        for _, row in err_df.iterrows():
            t = float(row['TimeS']) - t_offset
            sub = int(row[sub_col]) if sub_col else '?'
            ecode = int(row[ecode_col]) if ecode_col else '?'
            anomalies.append((t, 'ERROR', 'ERR', f'Subsys={sub} ECode={ecode}'))

    anomalies.sort(key=lambda x: x[0])
    return anomalies


def _global_t_offset(data: dict) -> float:
    t_min = None
    for df in data.values():
        if 'TimeS' in df.columns:
            ts = df['TimeS'].dropna()
            if not ts.empty:
                v = float(ts.min())
                if t_min is None or v < t_min:
                    t_min = v
    return t_min or 0.0
