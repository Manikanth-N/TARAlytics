"""
Event extraction from parsed flight-log data.

Logic moved verbatim from ui/widgets/event_table.py::_collect_events so that
multiple UI modules can share one definitive event source. Returns a list of
(timestamp_s, severity, type, message) tuples sorted by timestamp.
"""
from __future__ import annotations


MODE_NAMES = {
    0: 'STABILIZE', 1: 'ACRO', 2: 'ALT_HOLD', 3: 'AUTO', 4: 'GUIDED',
    5: 'LOITER', 6: 'RTL', 9: 'LAND', 16: 'POSHOLD', 17: 'BRAKE',
    18: 'THROW', 19: 'AVOID_ADSB', 20: 'GUIDED_NOGPS', 21: 'SMART_RTL',
}

EV_NAMES = {
    10: 'Armed', 11: 'Disarmed', 15: 'Auto_Armed', 16: 'Land_Complete',
    18: 'Not_Landed', 25: 'Set_Home', 26: 'Wrote_EEPROM',
    27: 'Load_Default_Params', 28: 'Pilot_YawSet',
}

ERR_SUBSYS = {
    1: 'Main', 2: 'Radio', 3: 'Compass', 5: 'FailSafe_Radio',
    6: 'FailSafe_Batt', 7: 'FailSafe_GPS', 10: 'FlightMode', 11: 'GPS',
    16: 'EKF_Check', 17: 'FailSafe_EKF', 18: 'Barometer',
}


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return df[n]
    return None


class EventExtractor:
    """Collects timeline events from MSG, EV, ERR, ARM, MODE messages."""

    @staticmethod
    def collect(data: dict) -> list[tuple]:
        """
        Return [(timestamp_s: float, severity: str, type: str, message: str), ...]
        sorted by timestamp ascending.
        severity is one of CRITICAL | ERROR | WARNING | INFO.
        """
        events: list[tuple] = []

        msg_df = data.get('MSG')
        if msg_df is not None and not msg_df.empty:
            ts_col = _col(msg_df, 'TimeS')
            msg_col = _col(msg_df, 'Message', 'Msg')
            if ts_col is not None and msg_col is not None:
                for ts, msg in zip(ts_col, msg_col):
                    msg = str(msg)
                    lo = msg.lower()
                    sev = ('CRITICAL'
                           if any(k in lo for k in ('fail', 'error', 'crash', 'critical'))
                           else 'INFO')
                    events.append((float(ts), sev, 'MSG', msg))

        ev_df = data.get('EV')
        if ev_df is not None and not ev_df.empty:
            ts_col = _col(ev_df, 'TimeS')
            id_col = _col(ev_df, 'Id', 'ID', 'id')
            if ts_col is not None and id_col is not None:
                for ts, eid in zip(ts_col, id_col):
                    name = EV_NAMES.get(int(eid), f'EV_{int(eid)}')
                    events.append((float(ts), 'INFO', 'EV', name))

        err_df = data.get('ERR')
        if err_df is not None and not err_df.empty:
            ts_col = _col(err_df, 'TimeS')
            sub_col = _col(err_df, 'Subsys', 'SubSys', 'subsys')
            ec_col = _col(err_df, 'ECode', 'Ecode', 'ecode')
            if ts_col is not None and sub_col is not None and ec_col is not None:
                for ts, sub, ec in zip(ts_col, sub_col, ec_col):
                    sname = ERR_SUBSYS.get(int(sub), f'Subsys_{int(sub)}')
                    events.append(
                        (float(ts), 'ERROR', 'ERR', f'ERR: {sname} code={int(ec)}')
                    )

        arm_df = data.get('ARM')
        if arm_df is not None and not arm_df.empty:
            ts_col = _col(arm_df, 'TimeS')
            state_col = _col(arm_df, 'ArmState', 'Armed', 'State')
            method_col = _col(arm_df, 'Method', 'method')
            if ts_col is not None and state_col is not None:
                for i, (ts, st) in enumerate(zip(ts_col, state_col)):
                    armed = int(st) == 1
                    sev = 'INFO' if armed else 'WARNING'
                    if method_col is not None:
                        m = int(method_col.iloc[i])
                        msg = 'Armed' if armed else f'Disarmed (method={m})'
                    else:
                        msg = 'Armed' if armed else 'Disarmed'
                    events.append((float(ts), sev, 'ARM', msg))

        mode_df = data.get('MODE')
        if mode_df is not None and not mode_df.empty:
            ts_col = _col(mode_df, 'TimeS')
            mode_col = _col(mode_df, 'Mode', 'ModeNum')
            if ts_col is not None and mode_col is not None:
                for ts, m in zip(ts_col, mode_col):
                    name = MODE_NAMES.get(int(m), f'MODE_{int(m)}')
                    events.append((float(ts), 'INFO', 'MODE', f'Mode: {name}'))

        events.sort(key=lambda e: e[0])
        return events
