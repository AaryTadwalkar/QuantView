# Detailed Data Schema & Status Report
**Generated**: 2026-10-12 21:57:56

## 1. Candlestick Data Summary
| Timeframe | Total Rows | Start Date | End Date |
|---|---|---|---|
| 1m | 451,952 | 2022-01-03 09:15:00 | 2026-10-08 15:29:00 |
| 3m | 144,428 | 2022-01-03 09:15:00 | 2026-10-08 15:27:00 |
| 5m | 86,728 | 2022-01-03 09:15:00 | 2026-10-08 15:25:00 |
| 15m | 28,944 | 2022-01-03 09:15:00 | 2026-10-08 15:15:00 |
| 1h | 8,232 | 2022-01-03 09:15:00 | 2026-10-08 15:15:00 |
| 4h | 2,352 | 2022-01-03 09:15:00 | 2026-10-08 13:15:00 |
| 1d | 1,410 | 2021-02-01 00:00:00 | 2026-10-08 00:00:00 |

### Candlestick Missing Row Analysis (Per Timeframe)
#### Timeframe: 1m
- **2022-03-07**: Missing 3 candles (10:22 to 10:24)
- **2024-12-12**: Missing 1 candles (09:42 to 09:42)
- **2025-03-25**: Missing 1 candles (10:42 to 10:42)
- **2025-04-04**: Missing 1 candles (11:57 to 11:57)
- **2025-04-23**: Missing 1 candles (10:36 to 10:36)
- **2026-02-04**: Missing 1 candles (15:29 to 15:29)
- **2026-02-05**: Missing 1 candles (15:29 to 15:29)
- **2026-02-06**: Missing 1 candles (15:29 to 15:29)
- **2026-02-10**: Missing 1 candles (15:29 to 15:29)
- **2026-02-11**: Missing 1 candles (15:29 to 15:29)
- **2026-02-12**: Missing 96 candles (13:54 to 15:29)
- **2026-02-13**: Missing 1 candles (15:29 to 15:29)
- **2026-02-16**: Missing 72 candles (09:15 to 10:25, 15:29 to 15:29)
- **2026-02-17**: Missing 1 candles (15:29 to 15:29)
- **2026-02-21**: Missing 374 candles (09:16 to 15:29)
- **2026-02-23**: Missing 57 candles (14:33 to 15:29)
- **2026-02-25**: Missing 1 candles (15:29 to 15:29)
- **2026-02-26**: Missing 1 candles (15:29 to 15:29)
- **2026-02-27**: Missing 1 candles (15:29 to 15:29)
- **2026-03-02**: Missing 1 candles (15:29 to 15:29)
- **2026-03-04**: Missing 1 candles (15:29 to 15:29)
- **2026-03-05**: Missing 1 candles (15:29 to 15:29)
- **2026-03-06**: Missing 1 candles (15:29 to 15:29)

#### Timeframe: 3m
✅ No missing candles detected within active trading days.

#### Timeframe: 5m
✅ No missing candles detected within active trading days.

#### Timeframe: 15m
✅ No missing candles detected within active trading days.

#### Timeframe: 1h
✅ No missing candles detected within active trading days.

#### Timeframe: 4h
✅ No missing candles detected within active trading days.

#### Timeframe: 1d
✅ No missing candles detected within active trading days.

## 2. Options Data Summary
- **Total Options Snapshots**: 71,617
- **Data Collection Start Date**: 2026-01-20
- **Data Collection End Date**: 2026-10-09
- **Total Expiries Tracked**: 32
- **Total Unique Trading Days**: 110

### Option Chain Schema Changes
- **v1 (2026-01-20 10:15:54)**: ('timestamp', 'strike', 'type', 'ltp', 'oi', 'prev_oi', 'volume', 'bid', 'ask')
- **v2 (2026-01-23 09:35:22)**: ('timestamp', 'strike', 'type', 'oi', 'volume', 'bid', 'ask')
- **v3 (2026-02-12 09:15:27)**: ('timestamp', 'spot_price', 'strike', 'type', 'oi', 'volume', 'ltp', 'bid', 'ask', 'bid_qty', 'ask_qty', 'chng', 'chng_oi', 'iv', 'delta', 'gamma', 'theta', 'vega')

### Expiry Date Validation
- 2026-01-20: ✅ Valid (Tuesday)
- 2026-01-27: ✅ Valid (Tuesday)
- 2026-02-10: ✅ Valid (Tuesday)
- 2026-02-17: ✅ Valid (Tuesday)
- 2026-02-24: ✅ Valid (Tuesday)
- 2026-03-10: ✅ Valid (Tuesday)
- 2026-03-17: ✅ Valid (Tuesday)
- 2026-03-24: ✅ Valid (Tuesday)
- 2026-04-13: ⚠️ Monday (Holiday shifted?)
- 2026-04-21: ✅ Valid (Tuesday)
- 2026-04-28: ✅ Valid (Tuesday)
- 2026-05-12: ✅ Valid (Tuesday)
- 2026-05-19: ✅ Valid (Tuesday)
- 2026-05-26: ✅ Valid (Tuesday)
- 2026-06-02: ✅ Valid (Tuesday)
- 2026-06-09: ✅ Valid (Tuesday)
- 2026-06-16: ✅ Valid (Tuesday)
- 2026-07-07: ✅ Valid (Tuesday)
- 2026-07-14: ✅ Valid (Tuesday)
- 2026-07-21: ✅ Valid (Tuesday)
- 2026-07-28: ✅ Valid (Tuesday)
- 2026-08-04: ✅ Valid (Tuesday)
- 2026-08-11: ✅ Valid (Tuesday)
- 2026-08-18: ✅ Valid (Tuesday)
- 2026-08-25: ✅ Valid (Tuesday)
- 2026-09-01: ✅ Valid (Tuesday)
- 2026-09-08: ✅ Valid (Tuesday)
- 2026-09-15: ✅ Valid (Tuesday)
- 2026-09-22: ✅ Valid (Tuesday)
- 2026-09-29: ✅ Valid (Tuesday)
- 2026-10-06: ✅ Valid (Tuesday)
- 2026-10-13: ✅ Valid (Tuesday)

### Options Data Missing Analysis (30s intervals from 09:15 to 15:30)
#### Expiry: 2026-01-20
- **Total Expected Days**: 1
- **Total Collected Days**: 1
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-01-20: 2 anomalies
    - Late start at 10:15:54
    - Gap from 11:32:42 to 11:33:44 (62s)

#### Expiry: 2026-01-27
- **Total Expected Days**: 5
- **Total Collected Days**: 3
- **Total Missing Days**: 2
- **Missing Dates**: 2026-01-22, 2026-01-26
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-01-21: 2 anomalies
    - Late start at 10:01:33
    - Early end at 13:30:30
  - 2026-01-23: 10 anomalies
    - Late start at 09:29:51
    - Gap from 09:31:53 to 09:32:44 (51s)
    - Gap from 09:43:29 to 09:46:14 (165s)
    - Gap from 10:00:04 to 11:35:21 (5717s)
    - Gap from 11:40:33 to 11:41:21 (48s)
    - ... and 5 more gaps

#### Expiry: 2026-02-10
- **Total Expected Days**: 10
- **Total Collected Days**: 5
- **Total Missing Days**: 6
- **Missing Dates**: 2026-01-28, 2026-01-29, 2026-01-30, 2026-02-02, 2026-02-03, 2026-02-09
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-02-11: 3 anomalies
    - Gap from 12:18:27 to 12:19:28 (61s)
    - Gap from 13:16:22 to 13:17:23 (61s)
    - Early end at 15:29:01

#### Expiry: 2026-02-17
- **Total Expected Days**: 5
- **Total Collected Days**: 4
- **Total Missing Days**: 1
- **Missing Dates**: 2026-02-11
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-02-12: 19 anomalies
    - Gap from 13:40:40 to 13:41:28 (48s)
    - Gap from 13:45:41 to 13:46:28 (47s)
    - Gap from 13:49:30 to 13:50:22 (52s)
    - Gap from 13:59:54 to 14:00:48 (54s)
    - Gap from 14:03:14 to 14:04:31 (77s)
    - ... and 14 more gaps
  - 2026-02-16: 1 anomalies
    - Late start at 10:25:36

#### Expiry: 2026-02-24
- **Total Expected Days**: 5
- **Total Collected Days**: 1
- **Total Missing Days**: 4
- **Missing Dates**: 2026-02-18, 2026-02-19, 2026-02-20, 2026-02-23
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - ✅ All collected days have perfect 30-second snapshot intervals!

#### Expiry: 2026-03-10
- **Total Expected Days**: 10
- **Total Collected Days**: 5
- **Total Missing Days**: 5
- **Missing Dates**: 2026-02-25, 2026-02-26, 2026-02-27, 2026-03-02, 2026-03-03
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-03-10: 1 anomalies
    - Early end at 10:31:22

#### Expiry: 2026-03-17
- **Total Expected Days**: 5
- **Total Collected Days**: 3
- **Total Missing Days**: 3
- **Missing Dates**: 2026-03-12, 2026-03-13, 2026-03-16
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-03-17: 1 anomalies
    - Late start at 09:55:05
  - 2026-03-18: 1 anomalies
    - Late start at 09:51:38

#### Expiry: 2026-03-24
- **Total Expected Days**: 5
- **Total Collected Days**: 1
- **Total Missing Days**: 4
- **Missing Dates**: 2026-03-18, 2026-03-20, 2026-03-23, 2026-03-24
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-03-19: 1 anomalies
    - Late start at 09:34:13

#### Expiry: 2026-04-13
- **Total Expected Days**: 14
- **Total Collected Days**: 3
- **Total Missing Days**: 11
- **Missing Dates**: 2026-03-25, 2026-03-26, 2026-03-27, 2026-03-30, 2026-03-31, 2026-04-01, 2026-04-02, 2026-04-03, 2026-04-06, 2026-04-07, 2026-04-13
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-04-08: 1 anomalies
    - Late start at 10:27:39
  - 2026-04-09: 1 anomalies
    - Late start at 10:02:50

#### Expiry: 2026-04-21
- **Total Expected Days**: 6
- **Total Collected Days**: 3
- **Total Missing Days**: 3
- **Missing Dates**: 2026-04-14, 2026-04-15, 2026-04-17
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-04-16: 2 anomalies
    - Late start at 09:37:52
    - Early end at 13:47:28
  - 2026-04-21: 1 anomalies
    - Gap from 14:16:02 to 14:18:25 (143s)

#### Expiry: 2026-04-28
- **Total Expected Days**: 5
- **Total Collected Days**: 2
- **Total Missing Days**: 3
- **Missing Dates**: 2026-04-22, 2026-04-24, 2026-04-28
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-04-23: 1 anomalies
    - Early end at 11:35:31
  - 2026-04-27: 1 anomalies
    - Late start at 09:51:17

#### Expiry: 2026-05-12
- **Total Expected Days**: 10
- **Total Collected Days**: 1
- **Total Missing Days**: 9
- **Missing Dates**: 2026-04-29, 2026-04-30, 2026-05-01, 2026-05-04, 2026-05-05, 2026-05-06, 2026-05-08, 2026-05-11, 2026-05-12
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - ✅ All collected days have perfect 30-second snapshot intervals!

#### Expiry: 2026-05-19
- **Total Expected Days**: 5
- **Total Collected Days**: 2
- **Total Missing Days**: 3
- **Missing Dates**: 2026-05-13, 2026-05-15, 2026-05-19
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-05-14: 2 anomalies
    - Late start at 09:52:05
    - Early end at 14:30:54

#### Expiry: 2026-05-26
- **Total Expected Days**: 5
- **Total Collected Days**: 1
- **Total Missing Days**: 4
- **Missing Dates**: 2026-05-20, 2026-05-21, 2026-05-22, 2026-05-25
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - ✅ All collected days have perfect 30-second snapshot intervals!

#### Expiry: 2026-06-02
- **Total Expected Days**: 5
- **Total Collected Days**: 2
- **Total Missing Days**: 3
- **Missing Dates**: 2026-05-28, 2026-05-29, 2026-06-01
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-06-02: 1 anomalies
    - Late start at 10:10:04

#### Expiry: 2026-06-09
- **Total Expected Days**: 5
- **Total Collected Days**: 4
- **Total Missing Days**: 1
- **Missing Dates**: 2026-06-09
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-06-04: 1 anomalies
    - Late start at 10:02:36
  - 2026-06-08: 1 anomalies
    - Late start at 09:40:55

#### Expiry: 2026-06-16
- **Total Expected Days**: 5
- **Total Collected Days**: 3
- **Total Missing Days**: 2
- **Missing Dates**: 2026-06-15, 2026-06-16
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-06-10: 2 anomalies
    - Late start at 10:20:03
    - Gap from 12:05:27 to 12:09:21 (234s)
  - 2026-06-11: 1 anomalies
    - Late start at 11:17:53
  - 2026-06-12: 1 anomalies
    - Late start at 09:37:16

#### Expiry: 2026-07-07
- **Total Expected Days**: 15
- **Total Collected Days**: 5
- **Total Missing Days**: 11
- **Missing Dates**: 2026-06-17, 2026-06-18, 2026-06-19, 2026-06-22, 2026-06-23, 2026-06-24, 2026-06-25, 2026-06-26, 2026-06-29, 2026-06-30, 2026-07-01
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-07-02: 1 anomalies
    - Late start at 10:48:44
  - 2026-07-04: 2 anomalies
    - Late start at 10:00:55
    - Early end at 10:01:27
  - 2026-07-06: 4 anomalies
    - Late start at 09:33:24
    - Gap from 11:11:40 to 11:12:26 (46s)
    - Gap from 12:53:24 to 12:56:54 (210s)
    - Gap from 13:20:40 to 13:28:54 (494s)
  - 2026-07-07: 1 anomalies
    - Late start at 09:34:15

#### Expiry: 2026-07-14
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-07-09: 2 anomalies
    - Gap from 09:17:14 to 09:18:02 (48s)
    - Gap from 11:12:01 to 11:13:24 (83s)
  - 2026-07-10: 2 anomalies
    - Gap from 14:18:30 to 14:21:23 (173s)
    - Gap from 14:35:57 to 14:45:50 (593s)
  - 2026-07-13: 1 anomalies
    - Gap from 09:48:03 to 09:50:56 (173s)

#### Expiry: 2026-07-21
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-07-15: 2 anomalies
    - Late start at 10:11:01
    - Gap from 11:13:33 to 11:14:20 (47s)
  - 2026-07-16: 1 anomalies
    - Gap from 11:05:03 to 11:10:38 (335s)
  - 2026-07-17: 2 anomalies
    - Late start at 09:16:00
    - Early end at 15:01:03
  - 2026-07-20: 2 anomalies
    - Late start at 09:34:03
    - Gap from 12:25:37 to 12:28:04 (147s)
  - 2026-07-21: 1 anomalies
    - Gap from 12:25:03 to 12:46:32 (1289s)

#### Expiry: 2026-07-28
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-07-23: 1 anomalies
    - Gap from 09:20:04 to 09:20:51 (47s)
  - 2026-07-27: 2 anomalies
    - Late start at 09:40:59
    - Gap from 10:12:34 to 10:17:36 (302s)
  - 2026-07-28: 1 anomalies
    - Gap from 09:33:34 to 09:54:39 (1265s)

#### Expiry: 2026-08-04
- **Total Expected Days**: 5
- **Total Collected Days**: 3
- **Total Missing Days**: 2
- **Missing Dates**: 2026-08-03, 2026-08-04
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-07-29: 1 anomalies
    - Early end at 14:28:03
  - 2026-07-30: 1 anomalies
    - Late start at 09:31:58
  - 2026-07-31: 1 anomalies
    - Late start at 09:44:11

#### Expiry: 2026-08-11
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-08-05: 1 anomalies
    - Late start at 09:38:53
  - 2026-08-06: 1 anomalies
    - Early end at 13:36:34
  - 2026-08-11: 1 anomalies
    - Early end at 15:23:34

#### Expiry: 2026-08-18
- **Total Expected Days**: 5
- **Total Collected Days**: 4
- **Total Missing Days**: 1
- **Missing Dates**: 2026-08-18
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-08-13: 1 anomalies
    - Gap from 11:50:04 to 11:51:03 (59s)
  - 2026-08-17: 1 anomalies
    - Late start at 09:29:04

#### Expiry: 2026-08-25
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-08-25: 2 anomalies
    - Late start at 09:42:37
    - Early end at 12:16:33

#### Expiry: 2026-09-01
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-08-26: 1 anomalies
    - Late start at 10:43:59
  - 2026-08-31: 1 anomalies
    - Late start at 10:55:05
  - 2026-09-01: 1 anomalies
    - Late start at 09:26:06

#### Expiry: 2026-09-08
- **Total Expected Days**: 5
- **Total Collected Days**: 3
- **Total Missing Days**: 2
- **Missing Dates**: 2026-09-02, 2026-09-07
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-09-03: 1 anomalies
    - Early end at 12:08:03
  - 2026-09-04: 1 anomalies
    - Early end at 12:15:33
  - 2026-09-08: 1 anomalies
    - Late start at 11:17:25

#### Expiry: 2026-09-15
- **Total Expected Days**: 5
- **Total Collected Days**: 4
- **Total Missing Days**: 1
- **Missing Dates**: 2026-09-14
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-09-10: 1 anomalies
    - Late start at 09:50:35
  - 2026-09-15: 2 anomalies
    - Gap from 12:28:33 to 12:32:33 (240s)
    - Gap from 12:38:03 to 12:40:33 (150s)

#### Expiry: 2026-09-22
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-09-18: 1 anomalies
    - Gap from 14:34:33 to 14:35:33 (60s)
  - 2026-09-21: 2 anomalies
    - Gap from 14:04:03 to 14:07:35 (212s)
    - Early end at 15:00:33

#### Expiry: 2026-09-29
- **Total Expected Days**: 5
- **Total Collected Days**: 5
- **Total Missing Days**: 0
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-09-24: 1 anomalies
    - Late start at 09:16:10
  - 2026-09-28: 1 anomalies
    - Late start at 09:45:49

#### Expiry: 2026-10-06
- **Total Expected Days**: 5
- **Total Collected Days**: 4
- **Total Missing Days**: 1
- **Missing Dates**: 2026-10-02
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-10-01: 3 anomalies
    - Late start at 09:25:31
    - Gap from 10:32:34 to 10:33:24 (50s)
    - Gap from 10:33:34 to 10:34:24 (50s)

#### Expiry: 2026-10-13
- **Total Expected Days**: 5
- **Total Collected Days**: 3
- **Total Missing Days**: 2
- **Missing Dates**: 2026-10-12, 2026-10-13
- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**
  - 2026-10-07: 1 anomalies
    - Gap from 14:39:16 to 14:40:29 (73s)
