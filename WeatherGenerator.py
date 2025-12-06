# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the 
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General 
# Public License for more details.

# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>. 
#
#
# This needs to be a STARTUP SCRIPT
#
# Generates cloud cover and keeps a rolling 48-hour forecast internally,
# using the following memory variables
# - IMCURRENTTIME (input)
# - IMDAYOFWEEK (input)
# - IMCLOUDCOVERPCT (output, NOW only)
#
# Start style preserved at bottom:
# weather = WeatherGenerator(); weather.setName('Weather generator'); weather.start()
import java
import jmri
import math
import csv # for loading the tab-delimited climate.csv

# ============================== CONSTANT PARAMETERS ==============================
# >>> Tab-delimited climate CSV <<<
try:
    CLIMATE_CSV_PATH = jmri.util.FileUtil.getExternalFilename("profile:jython/config/climate.csv")
except Exception:
    CLIMATE_CSV_PATH = "jython/config/climate.csv"

# Read climate preset from memory (IMWX_CLIMATE) if present, else default
try:
    mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
    mem = mm.provideMemory('IMWX_CLIMATE')
    val = mem.getValue()
    CLIMATE_NAME = str(val).strip() if val else 'SouthWales_EarlySep'
except:
    CLIMATE_NAME = 'SouthWales_EarlySep'

# Deterministic "world" seed for weather. Change to get a different (but repeatable) world.
BASE_SEED = 12345

# Forecast issuance cadence in simulated minutes (forecast remains stable between issues).
FORECAST_ISSUE_PERIOD_MIN = 180 # every 3 hours

# Forecast horizon and resolution (kept internal for now).
FORECAST_HOURS = 48
FORECAST_STEP_MIN = 60 # 60 = hourly points

# Era-dependent forecast accuracy (0..100). 100 = modern/best, 0 = vintage/worst.
FORECAST_ACCURACY = 80

# Memory override for forecast reliability (%)
try:
    ACCURACY_MEM = mm.provideMemory('IMWX_FORECAST_ACCURACY')
    if ACCURACY_MEM.getValue() is None:
        ACCURACY_MEM.setValue(int(FORECAST_ACCURACY))
except Exception:
    ACCURACY_MEM = None

# Issue-extension margin: if forward coverage from "now" is ever < (48h - margin), extend.
FORECAST_COVERAGE_MARGIN_MIN = 180 # 3 hours

# If True, print a concise forecast summary when new issues are generated (for debugging only).
LOG_FORECAST_ON_ISSUE = True
# ================================================================================

# -------------------------- NEW: Published forecast Memories --------------------
# Single-source-of-truth publication for UIs (schema WG2).
IMWX_SCHEMA    = 'IMWX_SCHEMA'              # 'WG2'
IMWX_FC_STEP   = 'IMWX_FC_STEP_MIN'         # int
IMWX_FC_LEN    = 'IMWX_FC_LENGTH'           # int
IMWX_FC_ISSUE  = 'IMWX_FC_ISSUE_ABSMIN'     # int
IMWX_FC_POINTS = 'IMWX_FC_POINTS'           # 'absMin:pct,absMin:pct,...' (length=FORECAST_HOURS)
IMWX_UPDATED   = 'IMWX_UPDATED_ABSMIN'      # int

# Optional: rolling list of recent issues (newest last) and one series per issue.
IMWX_FC_ISSUES = 'IMWX_FC_ISSUES'           # 'issue1,issue2,...'
# For each listed issue i, memory name is 'IMWX_FC_<i>' -> same 'absMin:pct' CSV

# Back-compat (simple list for legacy readers)
IMWX_FC_LIST   = 'IMWX_FC_LIST'             # 'p0,p1,...,p47'
# -------------------------------------------------------------------------------

# ------------------------------ Built-in fallback climate preset ----------------
# If the TSV row is missing/unreadable, we fall back to this dict.
BUILTIN_CLIMATES = {
  'SouthWales_EarlySep': {
    'mean_cloud' : 0.68,
    'long_amp' : 0.12,
    'short_amp' : 0.06,
    'noise_pp' : 0.04, # peak-to-peak micro-variability (±2%)
    'p_clear' : 0.15,
    'p_overcast' : 0.35,
    'event_clear_strength' : 0.45,
    'event_overcast_strength' : 0.45,
    'event_duration_min' : 180,
    'event_duration_max' : 540,
    'clear_ceiling' : 0.20
  }
}
# -------------------------------------------------------------------------------

# ------------------------- Tiny deterministic PRNG/Math helpers -----------------
def _hash32(*parts):
    h = 2166136261
    for p in parts:
        try:
            x = int(p)
        except Exception:
            x = 0
        h ^= (x & 0xffffffff)
        h = (h * 16777619) & 0xffffffff # FNV-1a style
    return h

def _prng01(seed):
    # Cheap LCG -> [0,1)
    x = (1103515245 * (seed & 0xffffffff) + 12345) & 0x7fffffff
    return x / float(0x7fffffff)

def _gauss(seed_a, seed_b, sigma):
    # Box–Muller with deterministic seeds
    u1 = max(1e-12, _prng01(seed_a))
    u2 = max(1e-12, _prng01(seed_b))
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return z * sigma

def _lerp(a, b, t):
    return a + (b - a) * t

# Accuracy anchors (percentage-point std-dev) for horizons ~1h, 24h, 48h.
# We linearly interpolate with horizon and then blend Vintage<- >Modern by accuracy scale.
MODERN_SIGMA = { 1: 5.0, 24: 10.0, 48: 18.0 }
VINTAGE_SIGMA = { 1: 10.0, 24: 22.0, 48: 35.0 }

def _sigma_for_horizon(hours_ahead, era_scale_0to1):
    def interp(anchor):
        if hours_ahead <= 1:
            return anchor[1]
        if hours_ahead >= 48:
            return anchor[48]
        if hours_ahead <= 24:
            return _lerp(anchor[1], anchor[24], (hours_ahead - 1.0) / (24.0 - 1.0))
        return _lerp(anchor[24], anchor[48], (hours_ahead - 24.0) / (48.0 - 24.0))
    m = interp(MODERN_SIGMA)
    v = interp(VINTAGE_SIGMA)
    return _lerp(v, m, era_scale_0to1)

def _dow_idx(name):
    order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    try:
        return order.index(str(name))
    except Exception:
        return 0

def _fmt_hhmm(mins_of_day):
    hh = int((mins_of_day % 1440) // 60)
    mm = int(mins_of_day % 60)
    return ("%02d:%02d" % (hh, mm))

def _dow_name_from_abs_minute(abs_minute):
    order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    day_index = int((abs_minute // 1440) % 7)
    return order[day_index]
# -------------------------------------------------------------------------------

# ------------------------- TSV climate loading helpers --------------------------
_CLIMATE_FIELDS_FLOAT = [
  'mean_cloud','long_amp','short_amp','noise_pp',
  'p_clear','p_overcast','event_clear_strength','event_overcast_strength','clear_ceiling'
]
_CLIMATE_FIELDS_INT = ['event_duration_min','event_duration_max']

def _parse_float(s, default):
    try:
        if s is None or s == '':
            return float(default)
        return float(s)
    except Exception:
        return float(default)

def _parse_int(s, default):
    try:
        if s is None or s == '':
            return int(default)
        return int(s)
    except Exception:
        return int(default)

def _load_climate_from_tsv(path, name, fallback_dict):
    """
    Load the climate row with 'name' from a TAB-delimited climate.csv.
    Returns a dict with typed fields; falls back to 'fallback_dict' on any error.
    """
    try:
        f = open(path, 'r')
        try:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row.get('name') == name:
                    cfg = dict(fallback_dict) # start from fallback schema for missing fields
                    # copy/convert known fields:
                    for k in _CLIMATE_FIELDS_FLOAT:
                        cfg[k] = _parse_float(row.get(k), fallback_dict[k])
                    for k in _CLIMATE_FIELDS_INT:
                        cfg[k] = _parse_int(row.get(k), fallback_dict[k])
                    return cfg
        finally:
            f.close()
    except Exception as e:
        print('Climate CSV load failed: {}'.format(e))
    return fallback_dict
# -------------------------------------------------------------------------------

# ------------------------------- Weather Generator ------------------------------
class WeatherGenerator(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):
        # Inputs (existing memories)
        self.clockMem = memories.getMemory('IMCURRENTTIME')
        self.dowMem = memories.getMemory('IMDAYOFWEEK')

        # Output (existing)
        self.cloudNowMem = memories.getMemory('IMCLOUDCOVERPCT')
        if self.cloudNowMem is None:
            self.cloudNowMem = jmri.InstanceManager.getDefault(jmri.MemoryManager).provideMemory('IMCLOUDCOVERPCT')
        if self.cloudNowMem.getValue() is None:
            self.cloudNowMem.setValue(0)

        self.timebase = jmri.InstanceManager.getDefault(jmri.Timebase)

        # Forecast store:
        # key = issuance absolute minute (within 7-day cycle)
        # value = list of 48 ints (0..100) for hourly horizons H00..H47
        self.issued = {}

        # Era accuracy scale from memory override (fallback to constant)
        try:
            v = ACCURACY_MEM.getValue() if ('ACCURACY_MEM' in globals() and ACCURACY_MEM is not None) else None
            acc = float(v) if (v is not None and str(v).strip() != '') else float(FORECAST_ACCURACY)
        except Exception:
            acc = float(FORECAST_ACCURACY)
        self.eraScale01 = max(0.0, min(1.0, acc / 100.0))

        # Track accuracy mem for live updates
        self.accMem = ACCURACY_MEM if ('ACCURACY_MEM' in globals() and ACCURACY_MEM is not None) else jmri.InstanceManager.getDefault(jmri.MemoryManager).provideMemory('IMWX_FORECAST_ACCURACY')

        # Load climate from TAB-delimited CSV (or fallback to built-in)
        builtin = BUILTIN_CLIMATES.get(CLIMATE_NAME, BUILTIN_CLIMATES['SouthWales_EarlySep'])
        self.climate = _load_climate_from_tsv(CLIMATE_CSV_PATH, CLIMATE_NAME, builtin)

        # --- One-line initial write: publish a value immediately at startup ---
        self.cloudNowMem.setValue(int(self._true_cloud_pct_at(self._abs_minute_now(), BASE_SEED)))

        # Publication memories for UIs (WG2 + back-compat)
        mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
        self.fcSchemaMem  = mm.provideMemory(IMWX_SCHEMA)
        self.fcStepMem    = mm.provideMemory(IMWX_FC_STEP)
        self.fcLenMem     = mm.provideMemory(IMWX_FC_LEN)
        self.fcIssueMem   = mm.provideMemory(IMWX_FC_ISSUE)
        self.fcPointsMem  = mm.provideMemory(IMWX_FC_POINTS)
        self.fcUpdatedMem = mm.provideMemory(IMWX_UPDATED)
        self.fcIssuesListMem = mm.provideMemory(IMWX_FC_ISSUES)

        # Back-compat list memory
        self.fcListMem    = mm.provideMemory(IMWX_FC_LIST)

        # Static fields (schema/shape) – write once
        self.fcSchemaMem.setValue('WG2')
        self.fcStepMem.setValue(int(FORECAST_STEP_MIN))
        self.fcLenMem.setValue(int(FORECAST_HOURS))

    # ---------------- Deterministic "true" weather ----------------
    def _daily_event_params(self, baseSeed, daySerial):
        """
        Picks the day's event type (clear/overcast/none) and its timing/duration,
        using climate-specific probabilities and deterministic RNG.
        """
        c = self.climate
        s = _hash32(baseSeed, 0xD00D, daySerial) # event identity per day
        # Deterministic roll in [0,1)
        u = _prng01(s)
        if u < c['p_clear']:
            etype = 'clear'
        elif u < c['p_clear'] + c['p_overcast']:
            etype = 'overcast'
        else:
            etype = None
        # Start window & duration (deterministic)
        latest_start = 1440 - c['event_duration_max']
        if latest_start < 0:
            latest_start = 0
        start = int(_prng01(_hash32(s, 1)) * (latest_start + 1))
        dur = c['event_duration_min'] + int(
            _prng01(_hash32(s, 2)) * (max(0, c['event_duration_max'] - c['event_duration_min']) + 1))
        return etype, start, dur

    def _true_cloud_pct_at(self, abs_minute, baseSeed):
        """
        Climate-aware 'true' cloud cover at absolute minute (0..100 int).
        """
        c = self.climate
        day = int(abs_minute // 1440)
        md = int(abs_minute % 1440)
        # Climate-shaped baseline
        base = c['mean_cloud'] \
             + c['long_amp'] * math.sin(2 * math.pi * abs_minute / 2880.0) \
             + c['short_amp'] * math.sin(2 * math.pi * abs_minute / 720.0)
        # Tiny deterministic micro-variability, peak-to-peak = noise_pp (e.g., 0.04 -> ±0.02)
        noise = (_prng01(_hash32(baseSeed, 0xBEEF, abs_minute // 10)) - 0.5) * c['noise_pp']
        base += noise
        # Climate-weighted daily event with smooth cosine transition
        etype, start, dur = self._daily_event_params(baseSeed, day)
        modifier = 0.0
        if etype is not None:
            end = start + dur
            if start <= md <= end:
                t = (md - start) / float(dur)
                blend = 0.5 * (1 - math.cos(math.pi * t)) # 0..1 smooth
                if etype == 'clear':
                    modifier = -c['event_clear_strength'] * blend
                elif etype == 'overcast':
                    modifier = c['event_overcast_strength'] * blend
        cloud = base + modifier
        # Keep "clear" genuinely clear (climate-specific ceiling)
        if etype == 'clear':
            while cloud > c['clear_ceiling']:
                cloud /= 2.0
        # Clamp [0,1] and convert to %
        cloud = max(0.0, min(1.0, cloud))
        return int(round(cloud * 100.0))

    # ---------------- Forecast generation ----------------
    def _issue_time_for(self, abs_minute):
        """Floor to issuance cadence boundary."""
        return abs_minute - (abs_minute % FORECAST_ISSUE_PERIOD_MIN)

    def _forecast_values_for_issue(self, issueAbsMin, baseSeed):
        """Deterministic forecast for a specific issuance time."""
        vals = []
        for k in range(FORECAST_HOURS):
            t = issueAbsMin + k * FORECAST_STEP_MIN
            true_pct = self._true_cloud_pct_at(t, baseSeed)
            # Forecast error ~ N(0, sigma(h)^2), sigma depends on era and horizon.
            h = max(1, k) # treat H00 ~ 1h ahead for sensible sigma
            sigma = _sigma_for_horizon(h, self.eraScale01)
            # Deterministic error per (issue, horizon), stable for that issuance
            err = _gauss(_hash32(baseSeed, 0xFACE, issueAbsMin, k),
                         _hash32(baseSeed, 0xFEED, issueAbsMin, k),
                         sigma)
            fc = int(round(max(0, min(100, true_pct + err))))
            vals.append(fc)
        return vals

    def _ensure_issue_present_for_time(self, abs_minute):
        """
        Ensure we have a forecast issuance at or before abs_minute.
        If none exists yet, create one exactly at that issuance boundary.
        If all existing issues are after abs_minute (e.g., we started later and warped back),
        generate backward in cadence steps until we cover the boundary at/before abs_minute.
        """
        if not self.issued:
            issue = self._issue_time_for(abs_minute)
            self.issued[issue] = self._forecast_values_for_issue(issue, BASE_SEED)
            if LOG_FORECAST_ON_ISSUE:
                print('Forecast issued @ {} {} [init]'.format(
                    _dow_name_from_abs_minute(issue), _fmt_hhmm(issue % 1440)
                ))
            return
        earliest = min(self.issued.keys())
        if earliest > abs_minute:
            # Backfill until we have an issuance at/before abs_minute
            issue = earliest
            while issue > abs_minute:
                issue -= FORECAST_ISSUE_PERIOD_MIN
            # Generate all missing issues up to the previous earliest
            t = issue
            while t < earliest:
                if t not in self.issued:
                    self.issued[t] = self._forecast_values_for_issue(t, BASE_SEED)
                    if LOG_FORECAST_ON_ISSUE:
                        print('Forecast issued @ {} {} [backfill]'.format(
                            _dow_name_from_abs_minute(t), _fmt_hhmm(t % 1440)
                        ))
                t += FORECAST_ISSUE_PERIOD_MIN

    def _ensure_forward_coverage(self, abs_now):
        """
        Ensure that there is at least (48h - margin) hours of forecast available beyond 'now'.
        We do this by issuing additional forecasts in cadence steps into the future
        until coverage_end >= abs_now + (48h - margin).
        """
        if not self.issued:
            self._ensure_issue_present_for_time(abs_now)
        latest_issue = max(self.issued.keys())
        coverage_end = latest_issue + FORECAST_HOURS * FORECAST_STEP_MIN
        target_end = abs_now + (FORECAST_HOURS * FORECAST_STEP_MIN - FORECAST_COVERAGE_MARGIN_MIN)
        while coverage_end < target_end:
            latest_issue += FORECAST_ISSUE_PERIOD_MIN
            if latest_issue not in self.issued:
                self.issued[latest_issue] = self._forecast_values_for_issue(latest_issue, BASE_SEED)
                if LOG_FORECAST_ON_ISSUE:
                    print('Forecast issued @ {} {} [extend]'.format(
                        _dow_name_from_abs_minute(latest_issue), _fmt_hhmm(latest_issue % 1440)
                    ))
            coverage_end = latest_issue + FORECAST_HOURS * FORECAST_STEP_MIN

        # Optional pruning: drop very old issues whose entire window ends >24h before now
        prune_before = abs_now - 24 * 60
        to_drop = [i for i in self.issued.keys() if (i + FORECAST_HOURS * FORECAST_STEP_MIN) < prune_before]
        for i in to_drop:
            del self.issued[i]

    def _forecast_value_at(self, abs_minute):
        """
        Return the forecast value that would have been 'in force' at abs_minute:
        choose the latest issuance <= abs_minute, then take the appropriate horizon bin.
        Assumes _ensure_issue_present_for_time(abs_minute) has already been called.
        """
        issue_candidates = [i for i in self.issued.keys() if i <= abs_minute]
        if not issue_candidates:
            self._ensure_issue_present_for_time(abs_minute)
            issue_candidates = [i for i in self.issued.keys() if i <= abs_minute]
        issue = max(issue_candidates)
        k = int((abs_minute - issue) // FORECAST_STEP_MIN)
        if k < 0: k = 0
        if k >= FORECAST_HOURS: k = FORECAST_HOURS - 1 # should be prevented by coverage
        return self.issued[issue][k]

    # ------------------------------ Time helpers ---------------------------------
    def _get_minutes_of_day(self):
        t = self.timebase.getTime()
        fmt = java.text.SimpleDateFormat('HH:mm')
        hh, mm = fmt.format(t).split(':')
        return int(hh) * 60 + int(mm)

    def _abs_minute_now(self):
        """
        Stateless absolute-minute model:
        - Uses IMDAYOFWEEK to derive a weekly day index (Mon=0..Sun=6).
        - Combines with minutes-of-day to form an absolute minute within a 7-day cycle.
        This is robust to large forward/backward time warps without depending on prior state.
        """
        weekly_index = _dow_idx(self.dowMem.getValue()) # 0..6
        return weekly_index * 1440 + self._get_minutes_of_day()

    # --------------------------- Publication helpers (WG2) -----------------------
    def _publish_issue_points(self, issueAbsMin):
        """
        Publish the active issuance in the WG2 format, plus a back-compat simple list.
        """
        vals = self.issued.get(issueAbsMin)
        if vals is None:
            vals = self._forecast_values_for_issue(issueAbsMin, BASE_SEED)
            self.issued[issueAbsMin] = vals

        # Build absMin:pct CSV for each horizon point
        pairs = []
        for k, pct in enumerate(vals):
            t = issueAbsMin + k * FORECAST_STEP_MIN
            pairs.append(str(int(t)) + ':' + str(int(pct)))
        csv_pairs = ','.join(pairs)

        # WG2 memories
        self.fcIssueMem.setValue(int(issueAbsMin))
        self.fcPointsMem.setValue(csv_pairs)
        self.fcUpdatedMem.setValue(int(self._abs_minute_now()))

        # Back-compat simple list
        self.fcListMem.setValue(','.join(str(int(v)) for v in vals))

        # Maintain a small list of recent issues (e.g., last 4) and store each series
        try:
            existing = str(self.fcIssuesListMem.getValue() or '').strip()
            items = [int(x) for x in existing.split(',') if x.strip()!='']
        except Exception:
            items = []
        if not items or items[-1] != issueAbsMin:
            items.append(issueAbsMin)
            items = items[-4:]
            self.fcIssuesListMem.setValue(','.join(str(x) for x in items))
        # Per-issue series
        mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
        per_issue_mem = mm.provideMemory('IMWX_FC_' + str(issueAbsMin))
        per_issue_mem.setValue(csv_pairs)

    # ------------------------------- Main Automaton ------------------------------
    def handle(self):
        # Wake on simulated time OR DOW change (robust to warps)
        self.waitChange([self.clockMem, self.dowMem, self.accMem])

        abs_now = self._abs_minute_now()
        
        # Recalculate accuracy scale if memory changed
        try:
            v = self.accMem.getValue()
            acc = float(v) if (v is not None and str(v).strip() != '') else float(FORECAST_ACCURACY)
            self.eraScale01 = max(0.0, min(1.0, acc / 100.0))
        except Exception:
            pass

        # Ensure we have an effective forecast in force at 'now' and enough forward coverage
        self._ensure_issue_present_for_time(abs_now)
        self._ensure_forward_coverage(abs_now)

        # 1) Publish actual cloud cover "now" (deterministic true world, climate-aware)
        now_pct = self._true_cloud_pct_at(abs_now, BASE_SEED)
        self.cloudNowMem.setValue(int(now_pct))

        # 2) Publish the issuance in force at 'now' so UIs can read it
        issue = self._issue_time_for(abs_now)
        self._publish_issue_points(issue)

        return True

# -- Start in your preferred style --
weather = WeatherGenerator()
weather.setName('Weather generator')
weather.start()