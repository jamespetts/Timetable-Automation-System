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
# Written with the kind assistance of Dave Sand and Microsoft Copilot
#
# This needs to be a STARTUP SCRIPT
import java
import jmri
import math
import csv
import TASBeanLookup as TBL

# -------------------- Throttle fallback constants (used if Memories missing/invalid) --------------------
LOW_TEMP_DEFAULT = 990  # warm / low CCT fallback address
HIGH_TEMP_DEFAULT = 991 # cool / high CCT fallback address

# -------------------- Configurable Memory names for throttle addresses --------------------
MEM_LOW_ADDR = "LOWCTTHROTTLEADDR"   # integer expected
MEM_HIGH_ADDR = "HIGHCTTHROTTLEADDR" # integer expected

# -------------------- Time-warp blackout configuration --------------------
BLACKOUT_SECONDS_DEFAULT = 2               # default blackout duration in seconds
TIMEWARP_THRESHOLD_MINUTES_DEFAULT = 5     # default warp threshold in minutes
MEM_BLACKOUT_SECONDS = "TIMEWARPBLACKOUTSECONDS"
MEM_TIMEWARP_THRESHOLD = "TIMEWARPTHRESHOLDMINUTES"
MEM_MIN_NIGHT_GLOW = "MINNIGHTGLOW"
MIN_NIGHT_GLOW_DEFAULT = 0.02


# -------------------- Day/Night CSV configuration (tab-delimited) --------------------
# Resolve path relative to the active JMRI profile (no absolute paths).
# This yields something like: </.../JMRI/<YourProfile>/> + "jython/config/daynight.csv"
try:
    DAYNIGHT_CSV_PATH = jmri.util.FileUtil.getExternalFilename("profile:jython/config/daynight.csv")
except Exception:
    # Fallback to relative string if FileUtil is unavailable (shouldn't happen in JMRI)
    DAYNIGHT_CSV_PATH = "jython/config/daynight.csv"

DAYNIGHT_PRESET = 'Maesteg_Sep2017'  # choose which row-set to load

mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)

# Read the preset from memory if present; otherwise fall back to DAYNIGHT_PRESET.
# Also write the resolved value back so other scripts can consume it consistently.
try:
    _mem_obj = TBL.ProvideMemoryBySuffix("DAYNIGHT_PRESET", DAYNIGHT_PRESET)
    _val = _mem_obj.getValue()
    _val = None if _val is None else str(_val).strip()
    ACTIVE_DAYNIGHT_PRESET = _val if _val else DAYNIGHT_PRESET
    _mem_obj.setValue(ACTIVE_DAYNIGHT_PRESET)
except Exception:
    ACTIVE_DAYNIGHT_PRESET = DAYNIGHT_PRESET

# Built-in fallback
FALLBACK_SUN_TIMES = {
    'Monday':    {'civil_dawn': 303, 'sunrise': 401, 'sunset': 1200, 'civil_dusk': 1298},
    'Tuesday':   {'civil_dawn': 305, 'sunrise': 402, 'sunset': 1198, 'civil_dusk': 1296},
    'Wednesday': {'civil_dawn': 306, 'sunrise': 404, 'sunset': 1196, 'civil_dusk': 1294},
    'Thursday':  {'civil_dawn': 308, 'sunrise': 406, 'sunset': 1194, 'civil_dusk': 1292},
    'Friday':    {'civil_dawn': 310, 'sunrise': 407, 'sunset': 1192, 'civil_dusk': 1290},
    'Saturday':  {'civil_dawn': 312, 'sunrise': 409, 'sunset': 1191, 'civil_dusk': 1287},
    'Sunday':    {'civil_dawn': 314, 'sunrise': 410, 'sunset': 1189, 'civil_dusk': 1285}
}
_DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

def _parse_time_to_minutes(s, default_mins):
    """
    Accepts 'HH:MM' or 'HH:MM:SS' (24-hour), or an int number of minutes.
    Returns minutes since midnight; falls back to default_mins on error.
    """
    try:
        if s is None:
            return int(default_mins)
        s = str(s).strip()
        if s.isdigit():
            return int(s) % (24*60) # backwards compatibility: plain minutes
        parts = s.split(':')
        if len(parts) >= 2:
            h = int(parts[0]); m = int(parts[1])
            return ((h % 24) * 60 + (m % 60))
        return int(default_mins)
    except Exception:
        return int(default_mins)

def _to_int_or_none(v):
    try:
        if v is None: return None
        sv = str(v).strip()
        if sv == '': return None
        return int(float(sv)) # tolerate "990.0"
    except Exception:
        return None

def _to_float_or_none(v):
    try:
        if v is None: return None
        sv = str(v).strip()
        if sv == '': return None
        return float(sv)
    except Exception:
        return None

def _load_daynight_from_tsv(path, preset_name, fallback):
    """Load tab-delimited day-night times for a named preset. Fallback per-day if missing."""
    out = dict(fallback) # start with fallback entire week
    try:
        f = open(path, 'r')
        try:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row.get('name') != preset_name:
                    continue
                day = row.get('day')
                if day not in _DAYS:
                    continue
                out[day] = {
                    'civil_dawn': _parse_time_to_minutes(row.get('civil_dawn'), fallback[day]['civil_dawn']),
                    'sunrise':    _parse_time_to_minutes(row.get('sunrise'),    fallback[day]['sunrise']),
                    'sunset':     _parse_time_to_minutes(row.get('sunset'),     fallback[day]['sunset']),
                    'civil_dusk': _parse_time_to_minutes(row.get('civil_dusk'), fallback[day]['civil_dusk']),
                }
        finally:
            f.close()
    except Exception as e:
        print('DayNight CSV load failed from {}: {}'.format(path, e))
    return out

class DayNight(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):
        # ---- Memories ----
        self.clock = TBL.FindMemoryBySuffix("CURRENTTIME")
        self.dayMemory = TBL.FindMemoryBySuffix("DAYOFWEEK")
        self.cloudMemory = TBL.FindMemoryBySuffix("CLOUDCOVERPCT")
        self.minNightGlowMem = TBL.FindMemoryBySuffix(MEM_MIN_NIGHT_GLOW)
        self.minNightGlow = MIN_NIGHT_GLOW_DEFAULT
        if self.minNightGlowMem is not None:
            v = _to_float_or_none(self.minNightGlowMem.getValue())
            if v is not None and 0.0 <= v <= 1.0:
                self.minNightGlow = v

        # New address memories (log error if missing)
        self.lowAddrMem = TBL.FindMemoryBySuffix(MEM_LOW_ADDR)
        self.highAddrMem = TBL.FindMemoryBySuffix(MEM_HIGH_ADDR)
        if self.lowAddrMem is None:
            print("ERROR: Required memory '{}' does not exist. Using fallback address {}."
                  .format(MEM_LOW_ADDR, LOW_TEMP_DEFAULT))
        if self.highAddrMem is None:
            print("ERROR: Required memory '{}' does not exist. Using fallback address {}."
                  .format(MEM_HIGH_ADDR, HIGH_TEMP_DEFAULT))

        # Time-warp configuration memories (optional)
        self.blackoutSecsMem = TBL.FindMemoryBySuffix(MEM_BLACKOUT_SECONDS)
        self.warpThresholdMinsMem = TBL.FindMemoryBySuffix(MEM_TIMEWARP_THRESHOLD)

        # ---- Core services ----
        self.timebase = jmri.InstanceManager.getDefault(jmri.Timebase)

        # ---- Load sun/civil times ----
        # >>> Use ACTIVE_DAYNIGHT_PRESET resolved above (from memory or default)
        self.sunTimes = _load_daynight_from_tsv(DAYNIGHT_CSV_PATH, ACTIVE_DAYNIGHT_PRESET, FALLBACK_SUN_TIMES)

        # Publish the resolved sunrise and sunset used by this controller.
        # These Memories are the single source of truth for dependent systems.
        self.sunriseSecondsMemory = TBL.ProvideMemoryBySuffix("SUNRISESECONDS", "0")
        self.sunsetSecondsMemory = TBL.ProvideMemoryBySuffix("SUNSETSECONDS", "0")
        self.solarDayMemory = TBL.ProvideMemoryBySuffix("SOLARDAY", "")
        initialSolarDay = self.dayMemory.getValue() if self.dayMemory is not None else "Monday"
        if initialSolarDay not in _DAYS:
            initialSolarDay = "Monday"
        self.sunriseSecondsMemory.setValue(str(int(self.sunTimes[initialSolarDay]["sunrise"]) * 60))
        self.sunsetSecondsMemory.setValue(str(int(self.sunTimes[initialSolarDay]["sunset"]) * 60))
        self.solarDayMemory.setValue(initialSolarDay)

        # ---- Determine desired throttle addresses (with validation) ----
        low_addr = _to_int_or_none(self.lowAddrMem.getValue()) if self.lowAddrMem is not None else None
        high_addr = _to_int_or_none(self.highAddrMem.getValue()) if self.highAddrMem is not None else None
        if low_addr is None:
            print("WARNING: '{}' is missing or not an integer. Using fallback {}."
                  .format(MEM_LOW_ADDR, LOW_TEMP_DEFAULT))
            low_addr = LOW_TEMP_DEFAULT
        if high_addr is None:
            print("WARNING: '{}' is missing or not an integer. Using fallback {}."
                  .format(MEM_HIGH_ADDR, HIGH_TEMP_DEFAULT))
            high_addr = HIGH_TEMP_DEFAULT
        self.lowAddr = int(low_addr)
        self.highAddr = int(high_addr)

        # ---- Acquire throttles ----
        self.lowThrottle = self.getThrottle(self.lowAddr, True);  self.lowThrottle.setIsForward(True)
        self.highThrottle = self.getThrottle(self.highAddr, True); self.highThrottle.setIsForward(True)

        # Lighting state
        self.lighthigh = 0.0
        self.lightlow = 0.0

        # Weather-related state retained but unused (weather now external)
        self.weatherEvent = None
        self.weatherEventStart = 0
        self.weatherEventDuration = 0

        self.lastDay = -1
        self.lastDayNumber = -1
        self.lastHour = -1

        # ---- Time-warp config values ----
        def _update_timewarp_config(self_inner=self):
            # Read current config from memories (case-insensitive, numeric expected)
            bs = BLACKOUT_SECONDS_DEFAULT
            wt = TIMEWARP_THRESHOLD_MINUTES_DEFAULT
            if self_inner.blackoutSecsMem is not None:
                v = _to_float_or_none(self_inner.blackoutSecsMem.getValue())
                if v is not None and v >= 0.0:
                    bs = float(v)
            if self_inner.warpThresholdMinsMem is not None:
                v = _to_float_or_none(self_inner.warpThresholdMinsMem.getValue())
                if v is not None and v >= 0.0:
                    wt = float(v)
            self_inner.blackoutSeconds = bs
            # Store as int minutes for comparison; accept fractional but round sensibly
            self_inner.warpThresholdMins = int(round(wt))

        self._update_timewarp_config = _update_timewarp_config
        self._update_timewarp_config()

        # ---- Track last fast-clock minutes to detect warps ----
        self.lastFastClockMinutes = self.getMinutes()

        # ---- Helper to re-acquire throttles if addresses changed at runtime ----
        def _refresh_throttles_if_needed(self_inner=self):
            changed = False
            # Read possible updated values (if memories exist)
            if self_inner.lowAddrMem is not None:
                new_low = _to_int_or_none(self_inner.lowAddrMem.getValue())
                if new_low is not None and int(new_low) != self_inner.lowAddr:
                    self_inner.lowAddr = int(new_low)
                    self_inner.lowThrottle = self_inner.getThrottle(self_inner.lowAddr, True)
                    self_inner.lowThrottle.setIsForward(True)
                    print("INFO: Re-acquired LOW throttle at address {}".format(self_inner.lowAddr))
                    changed = True
            if self_inner.highAddrMem is not None:
                new_high = _to_int_or_none(self_inner.highAddrMem.getValue())
                if new_high is not None and int(new_high) != self_inner.highAddr:
                    self_inner.highAddr = int(new_high)
                    self_inner.highThrottle = self_inner.getThrottle(self_inner.highAddr, True)
                    self_inner.highThrottle.setIsForward(True)
                    print("INFO: Re-acquired HIGH throttle at address {}".format(self_inner.highAddr))
                    changed = True
            return changed
        self._refresh_throttles_if_needed = _refresh_throttles_if_needed

    def handle(self):
        # Wake on time (always), on address changes (if memories exist),
        # and on time-warp config changes (if memories exist)
        wait_list = [self.clock]
        if self.dayMemory is not None: wait_list.append(self.dayMemory)
        if self.lowAddrMem is not None: wait_list.append(self.lowAddrMem)
        if self.highAddrMem is not None: wait_list.append(self.highAddrMem)
        if self.blackoutSecsMem is not None: wait_list.append(self.blackoutSecsMem)
        if self.warpThresholdMinsMem is not None: wait_list.append(self.warpThresholdMinsMem)

        self.waitChange(wait_list)

        # If addresses were updated, re-acquire throttles
        self._refresh_throttles_if_needed()

        # Refresh time-warp config in case memories changed
        self._update_timewarp_config()

        # Current time
        currentTime = self.clock.getValue()
        minutes = self.getMinutes()

        # ---- Detect time warp: compare fast-clock minutes to previous value (with midnight wrap) ----
        def _circular_minute_diff(a, b):
            # Absolute minimal difference around a 1440-minute cycle
            d = abs(a - b)
            return d if d <= 720 else (1440 - d)

        delta = _circular_minute_diff(minutes, self.lastFastClockMinutes)

        if delta > self.warpThresholdMins:
            # Black out immediately, then pause for configured seconds
            print("Time warp detected: delta ={} min > {} min threshold. Blackout for {:.2f}s"
                  .format(delta, self.warpThresholdMins, self.blackoutSeconds))
            try:
                self.lowThrottle.setSpeedSetting(0.0)
                self.highThrottle.setSpeedSetting(0.0)
            except Exception as e:
                print("WARNING: Could not set blackout values: {}".format(e))
            # Pause this automaton thread only; other JMRI threads remain active
            self.waitMsec(int(self.blackoutSeconds * 1000))

        print 'Time changed: {}, minutes = {}'.format(currentTime, minutes)

        # Day name
        self.currentDay = self.dayMemory.getValue()
        if self.currentDay not in _DAYS:
            self.currentDay = 'Monday'

        # Publish the exact resolved solar events for the current simulated day.
        self.sunriseSecondsMemory.setValue(str(int(self.sunTimes[self.currentDay]['sunrise']) * 60))
        self.sunsetSecondsMemory.setValue(str(int(self.sunTimes[self.currentDay]['sunset']) * 60))
        # Publish the day last. This acts as the commit marker for an atomic solar snapshot.
        self.solarDayMemory.setValue(self.currentDay)

        # Read cloud cover from memory (0..100 -> 0.0..1.0)
        try:
            cc = self.cloudMemory.getValue()
            self.cloud_cover = max(0.0, min(1.0, float(cc) / 100.0)) if cc is not None else 0.0
        except Exception:
            self.cloud_cover = 0.0

        # Compute lighting intensities
        self.calcLightingIntensities()

        # Apply to throttles
        self.lowThrottle.setSpeedSetting(self.lightlow)
        self.highThrottle.setSpeedSetting(self.lighthigh)

        print 'Lighting intensities: {:.0f}% cloud :: {:.2f} warm (2,700K) :: {:.2f} cool (6,500K)'.format(
            self.cloud_cover * 100.0, self.lightlow, self.lighthigh
        )

        # Update last minutes for next cycle's warp detection
        self.lastFastClockMinutes = minutes

        return True

    def getMinutes(self):
        # Get the current fast clock time as HH:mm. 24hr clock.
        time = self.timebase.getTime()
        timeStorageFormat = java.text.SimpleDateFormat('HH:mm')
        hhmm = timeStorageFormat.format(time).split(':')
        return int(hhmm[0]) * 60 + int(hhmm[1])

    def calcLightingIntensities(self):
        minutes = self.getMinutes()
        rise = self.sunTimes[self.currentDay]['sunrise']
        set_ = self.sunTimes[self.currentDay]['sunset']
        twilight_start = self.sunTimes[self.currentDay]['civil_dawn']
        twilight_end = self.sunTimes[self.currentDay]['civil_dusk']
        twilight_duration = twilight_end - twilight_start

        cloud_cover = self.cloud_cover # 0.0..1.0
        moonlight_level = self.minNightGlow

        lightlow = 0.0
        lighthigh = 0.0

        def smooth_daylight_intensity(mins, rise, set__):
            if mins < rise or mins > set__:
                return 0.0
            day_duration = set__ - rise
            x = math.pi * (mins - rise) / day_duration
            return math.sin(x)

        if minutes < twilight_start:
            # Full night
            lightlow = 0.0
            lighthigh = moonlight_level
        elif twilight_start <= minutes < rise:
            # Morning twilight
            fraction = float(minutes - twilight_start) / twilight_duration
            lightlow = 0.2 * fraction
            lighthigh = moonlight_level * (1.0 - fraction)
        elif rise <= minutes <= set_:
            # Daylight
            intensity = smooth_daylight_intensity(minutes, rise, set_)
            day_fraction = float(minutes - rise) / (set_ - rise)
            warm_ratio = math.sin(math.pi * day_fraction) ** 0.5  # slower change
            cool_ratio = math.sin(math.pi * day_fraction) ** 1.5  # sharper midday
            lightlow = intensity * warm_ratio
            lighthigh = intensity * cool_ratio
        elif set_ < minutes <= twilight_end:
            # Evening twilight
            fraction = float(twilight_end - minutes) / twilight_duration
            lightlow = 0.2 * fraction
            lighthigh = moonlight_level * (1.0 - fraction)
        else:
            # Full night
            lightlow = 0.0
            lighthigh = moonlight_level

        # Apply cloud cover modifiers (unchanged from your original)
        in_twilight = (twilight_start <= minutes < rise) or (set_ < minutes <= twilight_end)
        if cloud_cover >= 0.66:
            if in_twilight:
                twilight_factor = 1.0 - ((cloud_cover - 0.66) / 0.34)**1.5
                lightlow *= max(0.0, twilight_factor)
            else:
                lightlow *= 0.0
        else:
            lightlow *= 1.0

        lighthigh *= (1.0 - cloud_cover * 0.4)
        lighthigh = max(moonlight_level, min(1.0, lighthigh))

        self.lightlow = max(0.0, min(1.0, lightlow))
        self.lighthigh = max(0.0, min(1.0, lighthigh))

# Preserve your start pattern
dayNight = DayNight()
dayNight.setName('Day/night cycle')
dayNight.start()
