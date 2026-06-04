# TARAlytics — Investigation Evidence

**Log:** /home/manikanth/Downloads/00000012(1).BIN  
**Generated:** 2026-06-04T07:48:02  
**Aircraft:** — · ArduCopter V4.6.3 · QUAD/PLUS  
**Verification:** NOT_LOADED  
**Snapshots:** 3

---
## Snapshot 1 — EV: EV_62

**Status:** REVIEWED  ·  **Captured:** 2026-06-04T07:48:02  ·  **Flight time:** 135.00 s  ·  **Flight window:** 1 / 1

**Event:** EV: EV_62 @ 135.49 s

| Field | Value |
|---|---|
| Phase | CLIMB |
| Mode | GUIDED |
| Position | -35.363262, 149.165237 |
| Altitude (AGL) | 1.8 m (POS.RelHomeAlt) |
| Vertical speed | +1.50 m/s (BARO[0].CRt) |
| Ground speed | 0.0 m/s |
| GPS | RTK_FIXED · 10 sats |
| EKF health | OK (ratio 0.01, SV) |
| Position divergence | 0.01 m (OK) |
| Verification | NOT_LOADED |

**Control — Pilot / Demand / Actual:**

| Axis | Pilot | Demand | Actual | Δ |
|---|---|---|---|---|
| Roll | +0.00 | +0° | +0° | 0° |
| Pitch | +0.00 | +0° | +0° | 0° |
| Yaw | +0.00 | +354° | +354° | 0° |
| Throttle | 0.00 | — | 0.64 | — |

**Notes:** climb-out, EKF nominal

<details><summary>Data provenance (25 sampled values)</summary>

| Field | Source | Value | Sample t (s) | Interp. | Bracket (s) |
|---|---|---|---|---|---|
| pilot_roll | RCIN.C1 | 1500 | — | yes | 134.949–135.049 |
| servo_roll | RCOU.C1 | 1639 | — | yes | 134.949–135.049 |
| pilot_pitch | RCIN.C2 | 1500 | — | yes | 134.949–135.049 |
| servo_pitch | RCOU.C2 | 1639 | — | yes | 134.949–135.049 |
| pilot_yaw | RCIN.C4 | 1500 | — | yes | 134.949–135.049 |
| servo_yaw | RCOU.C4 | 1639 | — | yes | 134.949–135.049 |
| pilot_throttle | RCIN.C3 | 1000 | — | yes | 134.949–135.049 |
| servo_throttle | RCOU.C3 | 1639 | — | yes | 134.949–135.049 |
| demand_roll | ATT.DesRoll | 0.4482 | — | yes | 134.949–135.049 |
| demand_pitch | ATT.DesPitch | 0.4227 | — | yes | 134.949–135.049 |
| demand_yaw | ATT.DesYaw | 353.9 | — | yes | 134.949–135.049 |
| demand_throttle | CTUN.ThO | — | — | no | — |
| response_roll | ATT.Roll | 0.3512 | — | yes | 134.949–135.049 |
| response_pitch | ATT.Pitch | 0.3278 | — | yes | 134.949–135.049 |
| response_yaw | ATT.Yaw | 353.9 | — | yes | 134.949–135.049 |
| altitude_agl | POS.RelHomeAlt | 1.766 | — | yes | 134.949–135.049 |
| vertical_speed | BARO[0].CRt | 1.5 | — | yes | 134.949–135.049 |
| ground_speed | GPS[0].Spd | 0.04057 | — | yes | 134.989–135.189 |
| gps_status | GPS[0].Status | 6 | 134.989 | no | — |
| gps_sats | GPS[0].NSats | 10 | 134.989 | no | — |
| position_lat | GPS[0].Lat | -35.36 | — | yes | 134.989–135.189 |
| position_lng | GPS[0].Lng | 149.2 | — | yes | 134.989–135.189 |
| ekf_worst | XKF4[0].SV | 0.01 | — | yes | 134.949–135.049 |
| posdiv_ipn | XKF3[0].IPN | -0.005069 | — | yes | 134.949–135.049 |
| posdiv_ipe | XKF3[0].IPE | 0.005069 | — | yes | 134.949–135.049 |

</details>

---
## Snapshot 2 — MODE: Mode: LAND

**Status:** FLAGGED  ·  **Captured:** 2026-06-04T07:48:02  ·  **Flight time:** 150.00 s  ·  **Flight window:** 1 / 1

**Event:** MODE: Mode: LAND @ 148.08 s

| Field | Value |
|---|---|
| Phase | LAND |
| Mode | LAND |
| Position | -35.363262, 149.165237 |
| Altitude (AGL) | 9.2 m (POS.RelHomeAlt) |
| Vertical speed | -0.53 m/s (BARO[0].CRt) |
| Ground speed | 0.0 m/s |
| GPS | RTK_FIXED · 10 sats |
| EKF health | OK (ratio 0.01, SM) |
| Position divergence | 0.01 m (OK) |
| Verification | NOT_LOADED |

**Control — Pilot / Demand / Actual:**

| Axis | Pilot | Demand | Actual | Δ |
|---|---|---|---|---|
| Roll | +0.00 | +0° | +0° | 0° |
| Pitch | +0.00 | +0° | +0° | 0° |
| Yaw | +0.00 | +352° | +352° | 0° |
| Throttle | 0.00 | — | 0.59 | — |

**Notes:** descent / LAND mode entry

<details><summary>Data provenance (25 sampled values)</summary>

| Field | Source | Value | Sample t (s) | Interp. | Bracket (s) |
|---|---|---|---|---|---|
| pilot_roll | RCIN.C1 | 1500 | — | yes | 149.949–150.049 |
| servo_roll | RCOU.C1 | 1589 | — | yes | 149.949–150.049 |
| pilot_pitch | RCIN.C2 | 1500 | — | yes | 149.949–150.049 |
| servo_pitch | RCOU.C2 | 1588 | — | yes | 149.949–150.049 |
| pilot_yaw | RCIN.C4 | 1500 | — | yes | 149.949–150.049 |
| servo_yaw | RCOU.C4 | 1589 | — | yes | 149.949–150.049 |
| pilot_throttle | RCIN.C3 | 1000 | — | yes | 149.949–150.049 |
| servo_throttle | RCOU.C3 | 1588 | — | yes | 149.949–150.049 |
| demand_roll | ATT.DesRoll | 0.1932 | — | yes | 149.949–150.049 |
| demand_pitch | ATT.DesPitch | 0.2175 | — | yes | 149.949–150.049 |
| demand_yaw | ATT.DesYaw | 352.4 | — | yes | 149.949–150.049 |
| demand_throttle | CTUN.ThO | — | — | no | — |
| response_roll | ATT.Roll | 0.1817 | — | yes | 149.949–150.049 |
| response_pitch | ATT.Pitch | 0.2134 | — | yes | 149.949–150.049 |
| response_yaw | ATT.Yaw | 352.4 | — | yes | 149.949–150.049 |
| altitude_agl | POS.RelHomeAlt | 9.225 | — | yes | 149.949–150.049 |
| vertical_speed | BARO[0].CRt | -0.5313 | — | yes | 149.949–150.049 |
| ground_speed | GPS[0].Spd | 0.006946 | — | yes | 149.989–150.189 |
| gps_status | GPS[0].Status | 6 | 149.989 | no | — |
| gps_sats | GPS[0].NSats | 10 | 149.989 | no | — |
| position_lat | GPS[0].Lat | -35.36 | — | yes | 149.989–150.189 |
| position_lng | GPS[0].Lng | 149.2 | — | yes | 149.989–150.189 |
| ekf_worst | XKF4[0].SM | 0.01 | — | yes | 149.949–150.049 |
| posdiv_ipn | XKF3[0].IPN | -0.01 | — | yes | 149.949–150.049 |
| posdiv_ipe | XKF3[0].IPE | 0.005086 | — | yes | 149.949–150.049 |

</details>

---
## Snapshot 3 — EV: EV_56

**Status:** OPEN  ·  **Captured:** 2026-06-04T07:48:02  ·  **Flight time:** 175.00 s  ·  **Flight window:** — / 1

**Event:** EV: EV_56 @ 170.57 s

| Field | Value |
|---|---|
| Phase | POST |
| Mode | LAND |
| Position | -35.363262, 149.165237 |
| Altitude (AGL) | 0.0 m (POS.RelHomeAlt) |
| Vertical speed | +0.00 m/s (BARO[0].CRt) |
| Ground speed | 0.0 m/s |
| GPS | RTK_FIXED · 10 sats |
| EKF health | OK (ratio 0.00, SV) |
| Position divergence | 0.00 m (OK) |
| Verification | NOT_LOADED |

**Control — Pilot / Demand / Actual:**

| Axis | Pilot | Demand | Actual | Δ |
|---|---|---|---|---|
| Roll | +0.00 | +0° | +0° | 0° |
| Pitch | +0.00 | -0° | +0° | 0° |
| Yaw | +0.00 | +352° | +352° | 0° |
| Throttle | 0.00 | — | 0.00 | — |

**Notes:** post-flight, disarmed

<details><summary>Data provenance (25 sampled values)</summary>

| Field | Source | Value | Sample t (s) | Interp. | Bracket (s) |
|---|---|---|---|---|---|
| pilot_roll | RCIN.C1 | 1500 | — | yes | 174.949–175.049 |
| servo_roll | RCOU.C1 | 1000 | — | yes | 174.949–175.049 |
| pilot_pitch | RCIN.C2 | 1500 | — | yes | 174.949–175.049 |
| servo_pitch | RCOU.C2 | 1000 | — | yes | 174.949–175.049 |
| pilot_yaw | RCIN.C4 | 1500 | — | yes | 174.949–175.049 |
| servo_yaw | RCOU.C4 | 1000 | — | yes | 174.949–175.049 |
| pilot_throttle | RCIN.C3 | 1000 | — | yes | 174.949–175.049 |
| servo_throttle | RCOU.C3 | 1000 | — | yes | 174.949–175.049 |
| demand_roll | ATT.DesRoll | 0.0002184 | — | yes | 174.949–175.049 |
| demand_pitch | ATT.DesPitch | -0.0003247 | — | yes | 174.949–175.049 |
| demand_yaw | ATT.DesYaw | 351.8 | — | yes | 174.949–175.049 |
| demand_throttle | CTUN.ThO | — | — | no | — |
| response_roll | ATT.Roll | 0.1868 | — | yes | 174.949–175.049 |
| response_pitch | ATT.Pitch | 0.1783 | — | yes | 174.949–175.049 |
| response_yaw | ATT.Yaw | 351.8 | — | yes | 174.949–175.049 |
| altitude_agl | POS.RelHomeAlt | 0.01431 | — | yes | 174.949–175.049 |
| vertical_speed | BARO[0].CRt | 0 | — | yes | 174.949–175.049 |
| ground_speed | GPS[0].Spd | 0 | — | yes | 174.989–175.189 |
| gps_status | GPS[0].Status | 6 | 174.989 | no | — |
| gps_sats | GPS[0].NSats | 10 | 174.989 | no | — |
| position_lat | GPS[0].Lat | -35.36 | — | yes | 174.989–175.189 |
| position_lng | GPS[0].Lng | 149.2 | — | yes | 174.989–175.189 |
| ekf_worst | XKF4[0].SV | 0 | — | yes | 174.949–175.049 |
| posdiv_ipn | XKF3[0].IPN | 0 | — | yes | 174.949–175.049 |
| posdiv_ipe | XKF3[0].IPE | 0 | — | yes | 174.949–175.049 |

</details>

---