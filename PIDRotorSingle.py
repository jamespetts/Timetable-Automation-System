# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>.
#
# PIDRotorSingle.py (PART 1 OF 4)
# Shared helpers: settings, font selection, time parsing, and misc utilities.
# JMRI 5.14 / Jython 2.7 / ASCII only / CamelCase / Thread-safe EDT discipline.
#
# IMPORTANT: The STOPPING AT list must NOT include the destination.
# (This rule is enforced in the calling-pattern logic in later parts.)
#
# <<PID-DISP-NAME: Platform rotary departure board>>
# <<DESCRIPTION: Mechanical departure board for a platform showing destination and calling pattern on individual rotors>>
# <<SETTING DESCRIPTION COLOR: Platform rotary board background colour>>
# <<SETTING DESCRIPTION NUMBER: Platform rotary board stopping rows per column>>
# <<SETTING DESCRIPTION NUMBER: Platform rotary board minimum destination rotors>>
# <<SETTING DESCRIPTION NUMBER: Platform rotary board delayed threshold minutes>>

import javax.swing as swing
import java.awt as awt
import java.beans as beans
import java.awt.event as awtevent

import jmri
from jmri import InstanceManager

import os
import csv
import math
import java.text.SimpleDateFormat as SimpleDateFormat

# TAS helpers
import TASBeanLookup as TBL

import TASPathResolver
# Optional TAS registers
try:
    import TimingRegister as TR
except:
    TR = None
try:
    import PlatformAllocationRegister as PAR
except:
    PAR = None
try:
    from DisruptionRegister import getDisruption
except:
    getDisruption = None

# -----------------------------------------------------------------------------
# Settings / memories
# -----------------------------------------------------------------------------
# User-configurable settings (stored in Memories). These are suffix/prefix agnostic
# by virtue of TASBeanLookup.

SETTING_BG_RGB = "TAS_USER_SETTING_PLATFORM_ROTARY_BOARD_BACKGROUND_COLOUR"
SETTING_STOP_ROWS_PER_COL = "TAS_USER_SETTING_PLATFORM_ROTARY_BOARD_STOPPING_ROWS_PER_COLUMN"
SETTING_DEST_ROTORS_MIN = "TAS_USER_SETTING_PLATFORM_ROTARY_BOARD_MINIMUM_DESTINATION_ROTORS"
SETTING_DELAYED_THRESHOLD_MIN = "TAS_USER_SETTING_PLATFORM_ROTARY_BOARD_DELAYED_THRESHOLD_MINUTES"

# Existing standard memories (suffixes)
MEM_CURRENT_TIME = "CURRENTTIME"
MEM_DAY_OF_WEEK = "DAYOFWEEK"
MEM_CURRENT_TIMETABLE = "CURRENTTIMETABLE"
MEM_PID_DEPARTURE_TP = "PID_DEPARTURE_TP"
MEM_PID_PLATFORM_OVERRIDES = "PID_PLATFORM_OVERRIDES"

# -----------------------------------------------------------------------------
# Safe reading helpers for settings
# -----------------------------------------------------------------------------

def ReadInt(MemSuffix, DefaultVal, MinVal=None, MaxVal=None):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(MemSuffix, str(int(DefaultVal)))
        n = int(float(str(raw).strip()))
        if MinVal is not None:
            n = max(int(MinVal), n)
        if MaxVal is not None:
            n = min(int(MaxVal), n)
        return int(n)
    except:
        return int(DefaultVal)


def ReadBool(MemSuffix, DefaultVal=False):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(MemSuffix, "true" if DefaultVal else "false")
        t = str(raw).strip().lower()
        if t in ["1", "true", "yes", "y", "on", "enabled"]:
            return True
        if t in ["0", "false", "no", "n", "off", "disabled"]:
            return False
        return bool(DefaultVal)
    except:
        return bool(DefaultVal)


def ReadStr(MemSuffix, DefaultVal=""):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(MemSuffix, str(DefaultVal))
        return str(raw if raw is not None else "").strip()
    except:
        try:
            return str(DefaultVal if DefaultVal is not None else "").strip()
        except:
            return ""


def ParseRgb(MemSuffix, DefaultValRgbTuple):
    # Expects "R,G,B" where each is 0..255.
    # Returns java.awt.Color.
    try:
        raw = ReadStr(MemSuffix, "%d,%d,%d" % (int(DefaultValRgbTuple[0]), int(DefaultValRgbTuple[1]), int(DefaultValRgbTuple[2])))
        parts = [p.strip() for p in str(raw).split(",")]
        if len(parts) != 3:
            raise Exception("RGB must have 3 components")
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
        return awt.Color(int(r), int(g), int(b))
    except:
        return awt.Color(int(DefaultValRgbTuple[0]), int(DefaultValRgbTuple[1]), int(DefaultValRgbTuple[2]))


# Defaults (used if memories not set)
DEFAULT_BG_RGB = (20, 80, 120)
DEFAULT_STOP_ROWS_PER_COL = 10
DEFAULT_DEST_ROTORS_MIN = 1
DEFAULT_DELAYED_THRESHOLD_MIN = 2

# Seed user setting memories with defaults so TASSetup reflects the actual defaults.
# TASSetup will not create/seed these values itself; it only edits existing memories.
def _IsBlank(s):
 try:
  return (s is None) or (str(s).strip() == '')
 except:
  return True

def _IsValidRgbStr(s):
 try:
  parts = [p.strip() for p in str(s).split(',')]
  if len(parts) != 3:
   return False
  for p in parts:
   v = int(float(p))
   if v < 0 or v > 255:
    return False
  return True
 except:
  return False

def _SeedSettingIfMissingOrBlank(MemSuffix, DefaultStr, ValidatorFn=None):
 try:
  raw = TBL.SafeGetOrCreateMemoryValue(MemSuffix, str(DefaultStr))
 except:
  raw = None
 ok = True
 if ValidatorFn is not None:
  try:
   ok = bool(ValidatorFn(raw))
  except:
   ok = False
 if _IsBlank(raw) or (not ok):
  try:
   TBL.SafeSetMemoryValue(MemSuffix, str(DefaultStr))
  except:
   pass

# Apply defaults (only when missing/blank/invalid).
_SeedSettingIfMissingOrBlank(SETTING_BG_RGB, '%d,%d,%d' % (DEFAULT_BG_RGB[0], DEFAULT_BG_RGB[1], DEFAULT_BG_RGB[2]), _IsValidRgbStr)
_SeedSettingIfMissingOrBlank(SETTING_STOP_ROWS_PER_COL, str(int(DEFAULT_STOP_ROWS_PER_COL)))
_SeedSettingIfMissingOrBlank(SETTING_DEST_ROTORS_MIN, str(int(DEFAULT_DEST_ROTORS_MIN)))
_SeedSettingIfMissingOrBlank(SETTING_DELAYED_THRESHOLD_MIN, str(int(DEFAULT_DELAYED_THRESHOLD_MIN)))


# -----------------------------------------------------------------------------
# Time parsing helpers (tolerant 12/24-hour, with/without seconds)
# -----------------------------------------------------------------------------

Parser12 = SimpleDateFormat("h:mm a")
Parser24 = SimpleDateFormat("H:mm")
Parser12S = SimpleDateFormat("h:mm:ss a")
Parser24S = SimpleDateFormat("H:mm:ss")


def ParseMinutes(TimeStr):
 s = (TimeStr or "").strip()
 if s == "":
  return None
 # Accept minutes-since-midnight numeric values directly
 try:
  if str(s).strip().isdigit():
   v = int(str(s).strip())
   if v >= 0 and v <= (24 * 60 - 1):
    return v
   if len(str(s).strip()) == 4:
    hh = int(str(s).strip()[:2])
    mm = int(str(s).strip()[2:])
    if hh >= 0 and hh <= 23 and mm >= 0 and mm <= 59:
     return hh * 60 + mm
 except:
  pass
 # Normalize dot separator (e.g. 12.17 -> 12:17)
 try:
  if ('.' in s) and (':' not in s):
   t = s.replace(' ', '').lower()
   t = t.replace('am', '').replace('pm', '')
   if t.replace('.', '').isdigit():
    s = s.replace('.', ':', 1)
 except:
  pass
 # Normalize AM/PM without a space (e.g. 1:37PM)
 try:
  u = s.upper()
  if u.endswith('AM') and (not u.endswith(' AM')):
   s = s[:-2].strip() + ' AM'
  elif u.endswith('PM') and (not u.endswith(' PM')):
   s = s[:-2].strip() + ' PM'
 except:
  pass
 for p in [Parser12, Parser24, Parser12S, Parser24S]:
  try:
   d = p.parse(s)
   return d.getHours() * 60 + d.getMinutes()
  except:
   pass
 try:
  if ":" in s and len(s) <= 8:
   parts = s.split(":")
   if len(parts) >= 2:
    h = int(parts[0])
    m2 = int(parts[1])
    return h * 60 + m2
 except:
  pass
 return None

def MinutesToHHmm(TotalMinutes):
    if TotalMinutes is None:
        return ""
    tm = int(TotalMinutes) % (24 * 60)
    h = tm // 60
    m = tm % 60
    return "%02d:%02d" % (int(h), int(m))


# -----------------------------------------------------------------------------
# Fonts (Gill Sans MT first) and graphics helpers
# -----------------------------------------------------------------------------


def AvailableFamilies():
    try:
        ge = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []


def PickFontFamily(FontPrefs, FallbackFamily="SansSerif"):
    # Returns first available font family from FontPrefs (case-insensitive), else fallback.
    try:
        fams = AvailableFamilies()
        famLower = {}
        for f in fams:
            try:
                famLower[str(f).strip().lower()] = str(f)
            except:
                pass
        for p in (FontPrefs or []):
            try:
                key = str(p).strip().lower()
            except:
                key = ""
            if key != "" and key in famLower:
                return famLower[key]
    except:
        pass
    return FallbackFamily


FONT_FAMILY_MAIN = PickFontFamily([
    "Gill Sans MT",
    "Gill Sans",
    "Liberation Sans",
    "Arial",
    "SansSerif"
], "SansSerif")


def MakeFont(Family, Size, Bold=False):
    try:
        style = awt.Font.BOLD if Bold else awt.Font.PLAIN
        return awt.Font(str(Family), style, int(Size))
    except:
        return awt.Font("SansSerif", awt.Font.PLAIN, int(Size))


# -----------------------------------------------------------------------------
# Timetable access helpers (profile-relative path)
# -----------------------------------------------------------------------------


def ActiveProfilePath():
    try:
        return jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    except:
        return None


def TimetablePathFromMemory():
    # CURRENTTIMETABLE is expected to hold the base timetable filename (no extension).
    try:
        name = (TBL.SafeGetOrCreateMemoryValue(MEM_CURRENT_TIMETABLE, "") or "").strip()
    except:
        name = ""
    if name == "":
        return None
    prof = ActiveProfilePath()
    if not prof:
        return None
    return TASPathResolver.GetTimetableCsvPath(name)
def CsvRows():
    # Returns list of dict rows from the timetable (tab-delimited), or [].
    path = TimetablePathFromMemory()
    if not (path and os.path.exists(path)):
        return []
    rows = []
    try:
        f = open(path, "r")
        try:
            rdr = csv.DictReader(f, delimiter="	")
            for r in rdr:
                rows.append(r)
        finally:
            try:
                f.close()
            except:
                pass
    except Exception as ex:
        try:
            print("[PIDRotorSingle] Failed to read timetable: " + str(ex))
        except:
            pass
        return []
    return rows


def CaseInsensitive(Row, Key):
    # Case-insensitive field lookup for CSV header variance.
    target = (Key or "").strip().lower()
    try:
        keys = Row.keys() or []
    except:
        keys = []
    for k in keys:
        try:
            if (k or "").strip().lower() == target:
                v = Row.get(k, "")
                return (v or "").strip()
        except:
            pass
    return ""


def PlatformField(Row):
    v = (Row.get("Plat", "") or "").strip()
    if v == "":
        v = (Row.get("Platform", "") or "").strip()
    return v


# -----------------------------------------------------------------------------
# Overrides parsing (PID_PLATFORM_OVERRIDES)
# -----------------------------------------------------------------------------


def ParseOverrides(Text):
    # Parses "2G56=2;1W76=1" or comma separated.
    out = {}
    if not Text:
        return out
    try:
        parts = str(Text).replace(",", ";").split(";")
    except:
        return out
    for p in parts:
        try:
            pp = (p or "").strip()
        except:
            pp = ""
        if pp == "":
            continue
        if "=" in pp:
            try:
                k, v = pp.split("=", 1)
                out[(k or "").strip()] = (v or "").strip()
            except:
                pass
    return out


def GetPlatformOverride(ReportingNumber):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(MEM_PID_PLATFORM_OVERRIDES, "")
    except:
        raw = ""
    try:
        mapping = ParseOverrides(raw)
        return mapping.get(str(ReportingNumber))
    except:
        return None


# -----------------------------------------------------------------------------
# Departed-at-TP helper (PID_DEPARTURE_TP or profile name)
# -----------------------------------------------------------------------------


def ActiveProfileBaseTPName():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""


def DepartureTPList():
    names = []
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(MEM_PID_DEPARTURE_TP, "")
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                t = (p or "").strip()
                if t != "":
                    names.append(t)
    except:
        names = []
    if not names:
        base = ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names


def HasDepartedAtConfiguredTP(ReportingNumber, DayName, NowMinutes):
    if TR is None:
        return False
    tps = DepartureTPList()
    if not tps:
        return False
    for tp in tps:
        try:
            entries = TR.getTiming(tp) or []
        except:
            entries = []
        for rec in entries:
            try:
                rn = rec[0]
                tstr = rec[2]
                d = rec[3]
            except:
                continue
            if str(rn) != str(ReportingNumber):
                continue
            if str(d) != str(DayName):
                continue
            mm = ParseMinutes(tstr)
            if mm is None:
                continue
            try:
                if int(mm) <= int(NowMinutes):
                    return True
            except:
                pass
    return False


# -----------------------------------------------------------------------------
# Simple EDT helper (used later by UI parts)
# -----------------------------------------------------------------------------


def InvokeLater(RunnableFn):
    try:
        swing.SwingUtilities.invokeLater(RunnableFn)
    except:
        try:
            RunnableFn()
        except:
            pass

# -----------------------------------------------------------------------------
# Memory beans (suffix-based, prefix agnostic)
# -----------------------------------------------------------------------------

try:
    TimeMem = TBL.ProvideMemoryBySuffix(MEM_CURRENT_TIME, "")
except:
    TimeMem = None
try:
    DayMem = TBL.ProvideMemoryBySuffix(MEM_DAY_OF_WEEK, "")
except:
    DayMem = None
try:
    TTMem = TBL.ProvideMemoryBySuffix(MEM_CURRENT_TIMETABLE, "")
except:
    TTMem = None

# -----------------------------------------------------------------------------
# Timetable rows filtered by day
# -----------------------------------------------------------------------------

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def RowsForCurrentDay(AllRows, DayName):
    out = []
    dn = str(DayName or "").strip()
    if dn == "":
        return out
    for r in (AllRows or []):
        try:
            v = (r.get(dn, "") or "").strip().lower()
        except:
            v = ""
        if v == "true":
            out.append(r)
    return out


# -----------------------------------------------------------------------------
# Platform discovery
# -----------------------------------------------------------------------------


def DetectPlatforms(AllRows):
    # Distinct non-blank platforms from the timetable (over the whole file).
    plats = set()
    for r in (AllRows or []):
        try:
            p = (PlatformField(r) or "").strip()
        except:
            p = ""
        if p:
            plats.add(p)
    # Sort numeric platforms sensibly, then non-numeric.
    def _Key(s):
        ss = str(s)
        if ss.isdigit():
            return (0, int(ss), "")
        return (1, 0, ss)
    return sorted(list(plats), key=_Key)


# -----------------------------------------------------------------------------
# Calling pattern parsing (STOPPING AT excludes destination)
# -----------------------------------------------------------------------------


def ParseStopsExcludingDestination(CallingPatternText, DestinationText):
    # Calling pattern is comma-separated list of stop names.
    # Rule: STOPPING AT must NOT include the destination.
    stops = []
    try:
        raw = str(CallingPatternText or "")
    except:
        raw = ""
    for t in raw.split(","):
        s = (t or "").strip()
        if s != "":
            stops.append(s)
    # Remove destination anywhere in the list (case-insensitive).
    try:
        dest = str(DestinationText or "").strip().lower()
    except:
        dest = ""
    if dest != "":
        filtered = []
        for s in stops:
            try:
                if str(s).strip().lower() == dest:
                    continue
            except:
                pass
            filtered.append(s)
        stops = filtered
    return stops


# -----------------------------------------------------------------------------
# Departed/timing helpers
# -----------------------------------------------------------------------------


def HasAnyTimingToday(ReportingNumber, DayName):
    # True if ANY timing point has an entry for this RN on this day.
    if TR is None:
        return False
    try:
        tps = TR.listTimingPoints() or []
    except:
        tps = []
    for tp in tps:
        try:
            entries = TR.getTiming(tp) or []
        except:
            entries = []
        for rec in entries:
            try:
                rn = rec[0]
                d = rec[3]
            except:
                continue
            if str(rn) == str(ReportingNumber) and str(d) == str(DayName):
                return True
    return False


# -----------------------------------------------------------------------------
# Disruption/delay resolution with formation inheritance (Forms chain)
# -----------------------------------------------------------------------------


def ResolveDelayWithInheritance(RowsToday, ReportingNumber, SchedDepMin, Visited=None):
    # Returns tuple: (kind, value)
    # kind in: 'ontime', 'delay', 'cancel'
    # value: minutes for delay, None for cancel, 0 for ontime
    if Visited is None:
        Visited = set()
    rn = str(ReportingNumber)
    if rn in Visited:
        return ("ontime", 0)
    Visited.add(rn)

    # 1) Direct disruption
    delayVal = None
    if getDisruption is not None:
        try:
            delayVal = getDisruption(rn)
        except:
            delayVal = None
    if delayVal is not None:
        try:
            delay = int(delayVal)
        except:
            delay = 0
        if delay >= 1440:
            return ("cancel", None)
        if delay > 0:
            return ("delay", delay)
        # delay == 0 means: attempt inheritance

    # 2) Inherit from former(s): rows where Forms == this RN
    formers = []
    for r in (RowsToday or []):
        try:
            child = CaseInsensitive(r, "Forms")
        except:
            child = ""
        if str(child) != rn:
            continue
        try:
            arrStr = CaseInsensitive(r, "Arr")
        except:
            arrStr = ""
        arrMin = ParseMinutes(arrStr) if arrStr else None
        formers.append((r, arrMin))

    if not formers:
        return ("ontime", 0)

    chosen = None
    if SchedDepMin is not None:
        before = [t for t in formers if t[1] is not None and int(t[1]) <= int(SchedDepMin)]
        if before:
            before.sort(key=lambda t: int(t[1]))
            chosen = before[-1][0]
    if chosen is None:
        chosen = formers[0][0]

    formerRn = ""
    try:
        formerRn = CaseInsensitive(chosen, "Reporting number")
    except:
        formerRn = ""
    if formerRn == "":
        return ("ontime", 0)
    return ResolveDelayWithInheritance(RowsToday, formerRn, SchedDepMin, Visited)


# -----------------------------------------------------------------------------
# Next service selection per platform (single service)
# -----------------------------------------------------------------------------


def CurrentDayName():
    try:
        if DayMem is not None:
            return (DayMem.getValue() or "").strip()
    except:
        pass
    return ""


def CurrentMinutesFromCurrentTimeMem():
 # Prefer the JMRI fast clock (Timebase) if available, matching PIDSmall.
 try:
  tb = InstanceManager.getDefault(jmri.Timebase)
 except:
  tb = None
 if tb is not None:
  try:
   d = tb.getTime()
   return d.getHours() * 60 + d.getMinutes()
  except:
   pass
 # Fallback to CURRENTTIME memory
 try:
  if TimeMem is not None:
   s = TimeMem.getValue()
  else:
   s = TBL.SafeGetOrCreateMemoryValue(MEM_CURRENT_TIME, "")
 except:
  s = ""
 mm = ParseMinutes(s)
 if mm is not None:
  return mm
 return None

def EffectivePlatformForRow(Row, ReportingNumber):
    # Precedence: allocation register > overrides > timetable field.
    rn = str(ReportingNumber or "").strip()
    if rn == "":
        return (PlatformField(Row) or "").strip()
    if PAR is not None:
        try:
            alloc = PAR.getPlatform(rn)
            if alloc is not None and str(alloc).strip() != "":
                return str(alloc).strip()
        except:
            pass
    try:
        ov = GetPlatformOverride(rn)
        if ov is not None and str(ov).strip() != "":
            return str(ov).strip()
    except:
        pass
    return (PlatformField(Row) or "").strip()


def GetNextServiceForPlatform(PlatformText):
    # Returns a dict (service model) or None.
    allRows = CsvRows()
    day = CurrentDayName()
    nowMin = CurrentMinutesFromCurrentTimeMem()
    if day == "" or nowMin is None:
        return None

    rowsToday = RowsForCurrentDay(allRows, day)

    # Delay threshold for DELAYED plate.
    delayedThresh = ReadInt(SETTING_DELAYED_THRESHOLD_MIN, DEFAULT_DELAYED_THRESHOLD_MIN, 0, 240)

    candidates = []
    for r in rowsToday:
        depStr = CaseInsensitive(r, "Dep")
        if depStr == "":
            continue
        depMin = ParseMinutes(depStr)
        if depMin is None:
            continue
        rn = CaseInsensitive(r, "Reporting number")
        if rn == "":
            continue

        plat = EffectivePlatformForRow(r, rn)
        if str(plat) != str(PlatformText):
            continue

        dest = CaseInsensitive(r, "Destination")
        callText = CaseInsensitive(r, "Calling pattern")
        special = CaseInsensitive(r, "Special")

        # Resolve delay/cancel (direct or inherited)
        kind, val = ResolveDelayWithInheritance(rowsToday, rn, depMin, Visited=set())

        isCancelled = (kind == "cancel")
        delayMin = 0
        adjMin = depMin
        statusKey = "ONTIME"
        if isCancelled:
            statusKey = "CANCELLED"
        elif kind == "delay" and val is not None and int(val) > 0:
            delayMin = int(val)
            adjMin = int(depMin) + int(delayMin)
            statusKey = "DELAYED"

        # Departed check: only remove when departed at configured timing point(s)
        # Cancelled services are kept until shortly after booked time, matching PIDRotaryLarge behavior.
        if isCancelled:
            try:
                if int(nowMin) > (int(depMin) + 1):
                    continue
            except:
                continue
        else:
            if HasDepartedAtConfiguredTP(rn, day, nowMin):
                continue

        # Resilience filter (only for on-time with no timing evidence and no disruption entry)
        directDisruption = None
        if getDisruption is not None:
            try:
                directDisruption = getDisruption(rn)
            except:
                directDisruption = None
        if directDisruption is None and statusKey == "ONTIME" and (not HasAnyTimingToday(rn, day)):
            if int(depMin) < int(nowMin):
                continue

        # Exclude trains that are already in the past (unless delayed pushes them forward)
        if (not isCancelled) and int(adjMin) < int(nowMin):
            continue

        stops = ParseStopsExcludingDestination(callText, dest)

        candidates.append({
            'RN': str(rn),
            'Platform': str(plat),
            'Destination': str(dest),
            'DepMin': int(depMin),
            'AdjMin': int(adjMin),
            'DelayMin': int(delayMin),
            'StatusKey': str(statusKey),
            'IsCancelled': bool(isCancelled),
            'IsDelayedForPlate': bool((not isCancelled) and int(delayMin) >= int(delayedThresh)),
            'Stops': list(stops),
            'Special': str(special),
        })

    if not candidates:
        return None

    candidates.sort(key=lambda m: int(m.get('AdjMin', 999999)))
    return candidates[0]


# -----------------------------------------------------------------------------
# Platform manager (no UI here; Part 4 attaches real windows/controllers)
# -----------------------------------------------------------------------------

class PlatformPIDManager(object):
    # Discovers platforms and provides refresh notifications.
    def __init__(self):
        self.Platforms = []
        self._pcl = None
        self._listeners = []  # callbacks: fn(platformList)
        self.RebuildPlatforms()
        self._InstallListeners()

    def AddListener(self, CallbackFn):
        # Callback receives (platformList)
        if CallbackFn is None:
            return
        self._listeners.append(CallbackFn)

    def _Notify(self):
        pls = list(self.Platforms or [])
        for cb in list(self._listeners or []):
            try:
                cb(pls)
            except:
                pass

    def RebuildPlatforms(self):
        allRows = CsvRows()
        self.Platforms = DetectPlatforms(allRows)

    def _InstallListeners(self):
        # Rebuild platform list when timetable changes.
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb):
                innerSelf.Cb = cb
            def propertyChange(innerSelf, e):
                try:
                    innerSelf.Cb(e)
                except:
                    pass
        self._pcl = PCL(self._OnAnyChange)
        try:
            if TTMem is not None:
                TTMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        # Also respond to overrides and allocation changes (platform set may change).
        try:
            ovMem = TBL.ProvideMemoryBySuffix(MEM_PID_PLATFORM_OVERRIDES, "")
            if ovMem is not None:
                ovMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if PAR is not None:
                PAR.addPlatformListener(self._pcl)
        except:
            pass

    def _OnAnyChange(self, e=None):
        try:
            self.RebuildPlatforms()
            self._Notify()
        except:
            pass

    def Cleanup(self):
        try:
            if TTMem is not None and self._pcl is not None:
                TTMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            ovMem = TBL.ProvideMemoryBySuffix(MEM_PID_PLATFORM_OVERRIDES, "")
            if ovMem is not None and self._pcl is not None:
                ovMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if PAR is not None and self._pcl is not None:
                PAR.removePlatformListener(self._pcl)
        except:
            pass
        self._pcl = None
        self._listeners = []
#
# Key constraints:
# - Each rotor is a cuboid: 3 painted faces + 1 blank.
# - For a given timetable, the station/destination names on each rotor are static.
# - STOPPING AT must NOT include the destination (enforced in Part 2 parsing).
# - STOPPING AT display uses two equal columns; order is newspaper style:
#   down the left column, then down the right column.


# -----------------------------------------------------------------------------
# Normalization
# -----------------------------------------------------------------------------

def NormKey(s):
    try:
        return str(s or "").strip().lower()
    except:
        return ""


# -----------------------------------------------------------------------------
# Destination rotor plan
# -----------------------------------------------------------------------------

class DestinationRotorPlan(object):
    # Faces: list of lists: each rotor has faces ["", A, B, C] (some faces may be missing if <3)
    # Map: destLower -> (rotorIndex, faceIndex)
    def __init__(self):
        self.RotorFaces = []
        self.DestToRotorFace = {}
        self.DestDisplayName = {}  # destLower -> original text


def BuildDestinationRotorPlan(AllRows, PlatformText):
    # Build a static plan from the timetable only.
    # Platform matching here uses the timetable platform field, not allocations/overrides,
    # because real physical rotors are static for the timetable.
    plan = DestinationRotorPlan()

    dests = []
    seen = set()
    for r in (AllRows or []):
        try:
            p = (PlatformField(r) or "").strip()
        except:
            p = ""
        if str(p) != str(PlatformText):
            continue
        d = CaseInsensitive(r, "Destination")
        dk = NormKey(d)
        if dk == "":
            continue
        if dk in seen:
            continue
        seen.add(dk)
        dests.append(str(d).strip())
        plan.DestDisplayName[dk] = str(d).strip()

    # Stable order: alphabetical by upper-case display text
    try:
        dests.sort(key=lambda x: str(x).upper())
    except:
        pass

    # User preferred minimum rotors
    minRotors = ReadInt(SETTING_DEST_ROTORS_MIN, DEFAULT_DEST_ROTORS_MIN, 1, 50)

    # Chunk into groups of 3
    idx = 0
    rotorIdx = 0
    while idx < len(dests):
        faces = [""]
        for k in range(3):
            if idx + k < len(dests):
                faces.append(str(dests[idx + k]).strip())
        # Ensure exactly 4 faces (blank + 3), padding with blank
        while len(faces) < 4:
            faces.append("")
        plan.RotorFaces.append(faces)
        for fi in range(1, 4):
            dn = str(faces[fi] or "").strip()
            if dn != "":
                plan.DestToRotorFace[NormKey(dn)] = (rotorIdx, fi)
        rotorIdx += 1
        idx += 3

    # Pad to minimum
    while len(plan.RotorFaces) < int(minRotors):
        plan.RotorFaces.append(["", "", "", ""])

    return plan


# -----------------------------------------------------------------------------
# STOPPING AT rotor plan (3 stations per rotor + blank)
# -----------------------------------------------------------------------------

class StopRotorPlan(object):
    # RotorFaces: list length EffectiveTotalRotors; each is ["", A, B, C]
    # StationToRotorFace: stationLower -> (rotorIndex, faceIndex)
    # DisplayName: stationLower -> original casing
    # RowsPerColumn: number of rotors in each column (equal)
    # RequiredTotalRotors: minimal required rotors from constraints
    def __init__(self):
        self.RotorFaces = []
        self.StationToRotorFace = {}
        self.DisplayName = {}
        self.RowsPerColumn = 0
        self.RequiredTotalRotors = 0


def _ParseDayFlags(Row):
    # Return list of day field names that are true for this row.
    out = []
    try:
        for k in (Row.keys() or []):
            try:
                v = (Row.get(k, "") or "").strip().lower()
            except:
                v = ""
            if v == "true":
                lk = (k or "").strip().lower()
                if lk in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                    out.append(k)
    except:
        pass
    return out


def _RowsRunAnyDay(Row):
    try:
        for k in (Row.keys() or []):
            try:
                v = (Row.get(k, "") or "").strip().lower()
            except:
                v = ""
            if v == "true":
                return True
    except:
        pass
    return False


def _BuildStopSequences(AllRows, PlatformText, DisplayNameMap):
    # Build sequences of station keys for all services on this platform, across the whole week.
    # Uses ParseStopsExcludingDestination to enforce the no-destination rule.
    seqs = []
    for r in (AllRows or []):
        # Ignore non-running rows
        if not _RowsRunAnyDay(r):
            continue
        try:
            p = (PlatformField(r) or "").strip()
        except:
            p = ""
        if str(p) != str(PlatformText):
            continue
        dest = CaseInsensitive(r, "Destination")
        call = CaseInsensitive(r, "Calling pattern")
        stops = ParseStopsExcludingDestination(call, dest)
        keys = []
        last = None
        for s in (stops or []):
            k = NormKey(s)
            if k == "":
                continue
            if k == last:
                continue
            keys.append(k)
            last = k
            if k not in DisplayNameMap:
                DisplayNameMap[k] = str(s).strip()
        if keys:
            seqs.append(keys)
    return seqs


def _BuildConstraints(seqs):
    # Preds, Succs, Co as in PIDRotaryLarge but restricted to stops only.
    Preds = {}
    Succs = {}
    Co = {}

    def _AddNode(n):
        if n not in Preds:
            Preds[n] = set()
        if n not in Succs:
            Succs[n] = set()
        if n not in Co:
            Co[n] = set()

    for seq in (seqs or []):
        for n in seq:
            _AddNode(n)
        # adjacency order constraints
        for i in range(len(seq) - 1):
            a = seq[i]
            b = seq[i + 1]
            if a == b:
                continue
            Succs[a].add(b)
            Preds[b].add(a)
        # co-occurrence: any pair in same sequence
        for i in range(len(seq)):
            a = seq[i]
            for j in range(i + 1, len(seq)):
                b = seq[j]
                if a == b:
                    continue
                Co[a].add(b)
                Co[b].add(a)

    return Preds, Succs, Co


def _TopoOrderOrFallback(Preds, Succs):
    nodes = sorted(list(Preds.keys()))
    indeg = {}
    for n in nodes:
        indeg[n] = len(Preds.get(n, set()))
    ready = [n for n in nodes if indeg[n] == 0]
    ready.sort()
    out = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in sorted(list(Succs.get(n, set()))):
            indeg[m] = int(indeg.get(m, 0)) - 1
            if indeg[m] == 0:
                ready.append(m)
                ready.sort()
    if len(out) != len(nodes):
        # cycle detected
        return nodes, True
    return out, False


def _RowConflict(n, rowStations, Preds, Succs, Co):
    # Physical constraint: max 3 stations per rotor
    if len(rowStations) >= 3:
        return True
    for other in (rowStations or []):
        # do not place stations that co-occur or are ordered relative to each other on same rotor
        if other in Co.get(n, set()):
            return True
        if other in Preds.get(n, set()) or other in Succs.get(n, set()):
            return True
        if n in Preds.get(other, set()) or n in Succs.get(other, set()):
            return True
    return False


def SolveStopsToRotors(AllRows, PlatformText):
    # Returns (StationToRow, RowFaces, StationToFace, Cycle, RowsUsed, DisplayNameMap)
    displayName = {}
    seqs = _BuildStopSequences(AllRows, PlatformText, displayName)
    Preds, Succs, Co = _BuildConstraints(seqs)
    order, cycle = _TopoOrderOrFallback(Preds, Succs)

    StationToRow = {}
    RowToStations = []

    maxUsed = 0
    for n in order:
        # With cycles, precedence cannot be strictly enforced. We therefore do not
        # enforce a min-row based on predecessors when cycle=True.
        minRow = 0
        if not cycle:
            for p in Preds.get(n, set()):
                if p in StationToRow:
                    try:
                        minRow = max(minRow, int(StationToRow[p]) + 1)
                    except:
                        pass
        r = int(minRow)
        while True:
            while r >= len(RowToStations):
                RowToStations.append([])
            if not _RowConflict(n, RowToStations[r], Preds, Succs, Co):
                RowToStations[r].append(n)
                StationToRow[n] = r
                if (r + 1) > maxUsed:
                    maxUsed = r + 1
                break
            r += 1

    rowsUsed = int(maxUsed)

    # Build faces per row: blank + up to 3 stations
    RowFaces = []
    StationToFace = {}
    for r in range(len(RowToStations)):
        faces = [""]
        for s in RowToStations[r]:
            faces.append(s)
        while len(faces) < 4:
            faces.append("")
        RowFaces.append(faces)
        for fi in range(1, 4):
            k = str(faces[fi] or "").strip()
            if k != "":
                StationToFace[k] = fi

    return StationToRow, RowFaces, StationToFace, cycle, rowsUsed, displayName


def BuildStopRotorPlan(AllRows, PlatformText):
    plan = StopRotorPlan()

    # Preferred rows per column
    prefRowsPerCol = ReadInt(SETTING_STOP_ROWS_PER_COL, DEFAULT_STOP_ROWS_PER_COL, 1, 200)
    prefTotal = int(prefRowsPerCol) * 2

    stToRow, rowFaces, stToFace, cycle, used, displayName = SolveStopsToRotors(AllRows, PlatformText)

    # Minimal required total rotors is max row index used + 1
    requiredTotal = int(used)
    if requiredTotal < 0:
        requiredTotal = 0

    # Effective total rotors is max(required, preferred) and must be even
    effectiveTotal = max(int(requiredTotal), int(prefTotal))
    if (effectiveTotal % 2) != 0:
        effectiveTotal += 1

    rowsPerCol = int(effectiveTotal // 2)

    # Build final RotorFaces list of length effectiveTotal
    facesOut = []
    for i in range(int(effectiveTotal)):
        if i < len(rowFaces):
            # Convert normalized station keys into display strings for faces
            faces = [""]
            for fi in range(1, 4):
                k = rowFaces[i][fi] if fi < len(rowFaces[i]) else ""
                if k == "":
                    faces.append("")
                else:
                    faces.append(displayName.get(k, k))
            while len(faces) < 4:
                faces.append("")
            facesOut.append(faces)
        else:
            facesOut.append(["", "", "", ""])

    # Build station mapping with rotor index and face index
    stationMap = {}
    for k, r in stToRow.items():
        try:
            rr = int(r)
        except:
            continue
        if rr < 0 or rr >= int(effectiveTotal):
            continue
        fi = 0
        try:
            fi = int(stToFace.get(k, 0))
        except:
            fi = 0
        if fi < 0:
            fi = 0
        if fi > 3:
            fi = 3
        stationMap[k] = (rr, fi)

    plan.RotorFaces = facesOut
    plan.StationToRotorFace = stationMap
    plan.DisplayName = displayName
    plan.RowsPerColumn = int(rowsPerCol)
    plan.RequiredTotalRotors = int(requiredTotal)

    return plan


def IsServiceRepresentable(ServiceModel, DestPlan, StopPlan):
    # Returns False if the service refers to a destination/stops not present in the static plans.
    if ServiceModel is None:
        return True
    try:
        d = NormKey(ServiceModel.get('Destination', ''))
    except:
        d = ""
    if d != "":
        if d not in (DestPlan.DestToRotorFace or {}):
            return False
    try:
        stops = ServiceModel.get('Stops', []) or []
    except:
        stops = []
    for s in stops:
        k = NormKey(s)
        if k == "":
            continue
        if k not in (StopPlan.StationToRotorFace or {}):
            return False
    return True


# -----------------------------------------------------------------------------
# Rotor animation state (no drawing here; Part 4 renders using these states)
# -----------------------------------------------------------------------------

class RotorAnimState(object):
    # Represents one rotor cuboid window.
    def __init__(self, Faces):
        self.Faces = list(Faces or ["", "", "", ""])
        if len(self.Faces) < 2:
            self.Faces = ["", "", "", ""]
        # Ensure 4 faces
        while len(self.Faces) < 4:
            self.Faces.append("")
        if len(self.Faces) > 4:
            self.Faces = self.Faces[:4]
        self.FaceIdx = 0
        self.TargetFaceIdx = 0
        self.OffsetPx = 0
        self.IsRolling = False

    def SetTargetByText(self, Text):
        # Find face index matching Text (case-insensitive). If not found, target blank.
        t = str(Text or "").strip().lower()
        if t == "":
            self.TargetFaceIdx = 0
            return
        for i in range(1, len(self.Faces)):
            try:
                if str(self.Faces[i] or "").strip().lower() == t:
                    self.TargetFaceIdx = int(i)
                    return
            except:
                pass
        self.TargetFaceIdx = 0

    def Step(self, CellHeightPx, PixPerFrame):
     # One animation step. Returns True if still rolling after this step.
     # This version performs a single flip from the current face to the target face.
     # That guarantees the target text is the incoming face during the animation.
     h = int(CellHeightPx)
     if h < 1:
      h = 1
     step = int(PixPerFrame)
     if step < 1:
      step = 1
     # Already aligned
     if int(self.FaceIdx) == int(self.TargetFaceIdx) and int(self.OffsetPx) == 0:
      self.IsRolling = False
      return False
     self.IsRolling = True
     off = int(self.OffsetPx) + int(step)
     if int(off) >= int(h):
      # Finish the flip into the target face
      try:
       self.FaceIdx = int(self.TargetFaceIdx)
      except:
       pass
      self.OffsetPx = 0
      self.IsRolling = False
      return False
     self.OffsetPx = int(off)
     return True

    def CurrentText(self):
        try:
            return str(self.Faces[int(self.FaceIdx) % int(len(self.Faces))] or "")
        except:
            return ""

    def NextText(self):
     try:
      # During a roll, treat the target face as the incoming face so the
      # displayed text moves with the rotor instead of appearing only at the end.
      if bool(getattr(self, 'IsRolling', False)) and int(self.FaceIdx) != int(self.TargetFaceIdx):
       ti = int(self.TargetFaceIdx) % int(len(self.Faces))
       return str(self.Faces[ti] or '')
     except:
      pass
     try:
      ni = (int(self.FaceIdx) + 1) % int(len(self.Faces))
      return str(self.Faces[ni] or '')
     except:
      return ''

# -----------------------------------------------------------------------------
# Rendering helpers
# -----------------------------------------------------------------------------

def _TruncateToFit(g2, FontObj, Text, MaxWidth):
    try:
        t = str(Text or "")
    except:
        t = ""
    try:
        g2.setFont(FontObj)
        fm = g2.getFontMetrics(FontObj)
        if fm.stringWidth(t) <= int(MaxWidth):
            return t
        while len(t) > 1 and fm.stringWidth(t + "...") > int(MaxWidth):
            t = t[:-1]
        if len(t) > 1:
            return t + "..."
        return ""
    except:
        return str(Text or "")


def _WrapWordsToTwoLines(g2, FontObj, Text, MaxWidth):
    # Simple two-line wrap; last line may be truncated.
    try:
        words = [w for w in str(Text or "").split() if w != ""]
    except:
        words = []
    if not words:
        return ["", ""]
    try:
        g2.setFont(FontObj)
        fm = g2.getFontMetrics(FontObj)
    except:
        return [" ".join(words), ""]
    line1 = ""
    line2 = ""
    i = 0
    while i < len(words):
        cand = words[i] if line1 == "" else (line1 + " " + words[i])
        try:
            if fm.stringWidth(cand) <= int(MaxWidth):
                line1 = cand
                i += 1
                continue
        except:
            line1 = cand
            i += 1
            continue
        break
    if i >= len(words):
        return [line1, ""]
    # Remaining words into line2
    while i < len(words):
        cand = words[i] if line2 == "" else (line2 + " " + words[i])
        try:
            if fm.stringWidth(cand) <= int(MaxWidth):
                line2 = cand
                i += 1
                continue
        except:
            line2 = cand
            i += 1
            continue
        break
    if i < len(words):
        # Too long; truncate line2 with ellipsis
        line2 = _TruncateToFit(g2, FontObj, line2 + " " + " ".join(words[i:]), MaxWidth)
    return [line1, line2]


def DrawRecessShading(g2, R):
    # Aperture shading (top and bottom gradients)
    try:
        gpTop = awt.GradientPaint(float(R.x), float(R.y), awt.Color(0, 0, 0, 210),
                                  float(R.x), float(R.y + 7), awt.Color(0, 0, 0, 0))
        g2.setPaint(gpTop)
        g2.fillRect(int(R.x), int(R.y), int(R.width), min(7, int(R.height)))
        gpBot = awt.GradientPaint(float(R.x), float(R.y + R.height - 7), awt.Color(0, 0, 0, 0),
                                  float(R.x), float(R.y + R.height), awt.Color(0, 0, 0, 210))
        g2.setPaint(gpBot)
        g2.fillRect(int(R.x), int(R.y + max(0, int(R.height) - 7)), int(R.width), min(7, int(R.height)))
    except:
        pass


def DrawRidgeLine(g2, x1, x2, y):
    # Draw the ridge line and restore the caller's color.
    oldCol = None
    try:
        try:
            oldCol = g2.getColor()
        except:
            oldCol = None
        g2.setColor(awt.Color(255, 255, 255, 40))
        g2.drawLine(int(x1), int(y), int(x2), int(y))
        g2.setColor(awt.Color(0, 0, 0, 200))
        g2.drawLine(int(x1), int(y + 1), int(x2), int(y + 1))
    except:
        pass
    try:
        if oldCol is not None:
            g2.setColor(oldCol)
    except:
        pass

def DrawRotorWindow(g2, R, CurText, NextText, OffsetPx, FontObj, TextColor, SurroundColor):
    # Cuboid rotor aperture.
    # - Blank face should use the background color but still be outlined as a panel.
    # - Text should be centered within the aperture.
    # - During rolling, draw outgoing/incoming text centered within the visible
    #   top/bottom halves of the aperture.
    oldClip = None
    try:
        oldClip = g2.getClip()
        g2.setClip(int(R.x), int(R.y), int(R.width), int(R.height))
    except:
        oldClip = None
    try:
        try:
            g2.setFont(FontObj)
            fm = g2.getFontMetrics(FontObj)
        except:
            fm = None

        off = int(OffsetPx)
        h = int(R.height)
        if h < 1:
            h = 1

        outlineCol = awt.Color(90, 90, 90)

        # Blank face
        if str(CurText or '') == '' and off == 0:
            g2.setColor(SurroundColor)
            g2.fillRect(int(R.x), int(R.y), int(R.width), int(R.height))
            g2.setColor(outlineCol)
            g2.drawRect(int(R.x), int(R.y), int(R.width), int(R.height))
            return

        # Visible aperture
        g2.setColor(awt.Color(0, 0, 0))
        g2.fillRect(int(R.x), int(R.y), int(R.width), int(R.height))
        g2.setColor(awt.Color(10, 10, 10))
        g2.drawRect(int(R.x), int(R.y), int(R.width), int(R.height))
        DrawRecessShading(g2, R)
        g2.setColor(TextColor)

        def _DrawCenteredLinesInRect(text, RectY, RectH):
            if fm is None:
                return
            lines = _WrapWordsToTwoLines(g2, FontObj, text, int(R.width) - 6)
            lh = fm.getHeight()
            nlines = 1 if lines[1] == '' else 2
            hh = int(RectH)
            if hh < 1:
                hh = 1
            y0 = int(RectY) + (hh - (lh * nlines)) // 2 + fm.getAscent()
            for i, ln in enumerate(lines[:nlines]):
                s = str(ln).upper()
                try:
                    tw = fm.stringWidth(s)
                except:
                    tw = 0
                tx = int(R.x) + (int(R.width) - tw) // 2
                ty = int(y0 + i * lh)
                g2.drawString(s, tx, ty)

        if off <= 0:
            t = str(CurText or '')
            if t != '':
                _DrawCenteredLinesInRect(t, int(R.y), int(h))
            return

        ridgeY = int(R.y + (h - off))
        DrawRidgeLine(g2, int(R.x) + 1, int(R.x + R.width) - 2, ridgeY)
        # Ensure text color after ridge drawing
        try:
            g2.setColor(TextColor)
        except:
            pass

        t1 = str(CurText or '')
        t2 = str(NextText or '')

        # Top half (outgoing)
        topH = int(ridgeY - int(R.y))
        if topH < 0:
            topH = 0
        if t1 != '' and topH > 0:
            try:
                g2.setClip(int(R.x), int(R.y), int(R.width), int(topH))
            except:
                pass
            _DrawCenteredLinesInRect(t1, int(R.y), int(topH))

        # Bottom half (incoming)
        botY = int(ridgeY)
        botH = int(int(R.y + h) - botY)
        if botH < 0:
            botH = 0
        if t2 != '' and botH > 0:
            try:
                g2.setClip(int(R.x), int(botY), int(R.width), int(botH))
            except:
                pass
            _DrawCenteredLinesInRect(t2, int(botY), int(botH))

        # Restore full aperture clip
        try:
            g2.setClip(int(R.x), int(R.y), int(R.width), int(R.height))
        except:
            pass
    finally:
        try:
            if oldClip is not None:
                g2.setClip(oldClip)
            else:
                g2.setClip(None)
        except:
            pass

def DrawAnalogClock(g2, Cx, Cy, Radius, MinutesSinceMidnight, FaceColor, HandColor, TickColor):
    # Draw a simple analogue clock with hour and minute hands.
    try:
        r = int(Radius)
        if r < 10:
            return
        cx = int(Cx)
        cy = int(Cy)
        g2.setColor(FaceColor)
        g2.fillOval(cx - r, cy - r, 2 * r, 2 * r)
        g2.setColor(awt.Color(0, 0, 0))
        g2.drawOval(cx - r, cy - r, 2 * r, 2 * r)

        # Tick marks
        g2.setColor(TickColor)
        for i in range(60):
            ang = (math.pi * 2.0) * (float(i) / 60.0) - (math.pi / 2.0)
            inner = r - (8 if (i % 5) == 0 else 4)
            x1 = cx + int(inner * math.cos(ang))
            y1 = cy + int(inner * math.sin(ang))
            x2 = cx + int((r - 2) * math.cos(ang))
            y2 = cy + int((r - 2) * math.sin(ang))
            g2.drawLine(x1, y1, x2, y2)

        # Hands

        try:

         mm = float(MinutesSinceMidnight) % float(24 * 60)

        except:

         mm = float(int(MinutesSinceMidnight) % (24 * 60))

        hourF = (mm / 60.0) % 12.0

        minuteF = mm % 60.0

        # hour hand angle includes minutes

        angH = (math.pi * 2.0) * (float(hourF) / 12.0) - (math.pi / 2.0)

        angM = (math.pi * 2.0) * (float(minuteF) / 60.0) - (math.pi / 2.0)

        g2.setColor(HandColor)

        # hour hand

        hx = cx + int((r * 0.55) * math.cos(angH))

        hy = cy + int((r * 0.55) * math.sin(angH))

        g2.setStroke(awt.BasicStroke(3.0))

        g2.drawLine(cx, cy, hx, hy)

        # minute hand

        mx = cx + int((r * 0.80) * math.cos(angM))

        my = cy + int((r * 0.80) * math.sin(angM))

        g2.setStroke(awt.BasicStroke(2.0))

        g2.drawLine(cx, cy, mx, my)

        # hub
        g2.setColor(awt.Color(0, 0, 0))
        g2.fillOval(cx - 3, cy - 3, 6, 6)
    except:
        pass


def DrawPlate(g2, R, Text, IsAlert, FontObj):
    # Plate at bottom: black for special, red for DELAYED/CANCELLED.
    try:
        t = str(Text or "").strip()
    except:
        t = ""
    if t == "":
        return
    bg = awt.Color(180, 0, 0) if IsAlert else awt.Color(0, 0, 0)
    fg = awt.Color(255, 255, 255)
    try:
        g2.setColor(bg)
        g2.fillRect(int(R.x), int(R.y), int(R.width), int(R.height))
        g2.setColor(awt.Color(0, 0, 0))
        g2.drawRect(int(R.x), int(R.y), int(R.width), int(R.height))
        g2.setFont(FontObj)
        fm = g2.getFontMetrics(FontObj)
        lines = _WrapWordsToTwoLines(g2, FontObj, t, int(R.width) - 8)
        nlines = 1 if lines[1] == "" else 2
        lh = fm.getHeight()
        y0 = int(R.y) + (int(R.height) - (lh * nlines)) // 2 + fm.getAscent()
        g2.setColor(fg)
        for i, ln in enumerate(lines[:nlines]):
            s = str(ln).upper()
            tx = int(R.x) + (int(R.width) - fm.stringWidth(s)) // 2
            ty = int(y0 + i * lh)
            g2.drawString(s, tx, ty)
    except:
        pass


# -----------------------------------------------------------------------------
# Panel
# -----------------------------------------------------------------------------

class RotorSinglePanel(swing.JPanel):
    # Controller must provide GetRenderState() returning dict with geometry and state.
    def __init__(self, Controller):
        swing.JPanel.__init__(self)
        self.Controller = Controller
        self.setLayout(None)
        self.setOpaque(True)
        try:
            self.setBackground(ParseRgb(SETTING_BG_RGB, DEFAULT_BG_RGB))
        except:
            self.setBackground(awt.Color(DEFAULT_BG_RGB[0], DEFAULT_BG_RGB[1], DEFAULT_BG_RGB[2]))

    def paintComponent(self, g):
        if self.isOpaque():
            try:
                g.setColor(self.getBackground())
                g.fillRect(0, 0, self.getWidth(), self.getHeight())
            except:
                pass
        g2 = g.create()
        try:
            try:
                g2.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
                g2.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
                g2.setRenderingHint(awt.RenderingHints.KEY_FRACTIONALMETRICS, awt.RenderingHints.VALUE_FRACTIONALMETRICS_ON)
            except:
                pass
            ctrl = self.Controller
            if ctrl is None:
                return
            st = ctrl.GetRenderState() or {}

            bg = self.getBackground()
            textCol = awt.Color(255, 255, 255)

            # Geometry
            w = int(st.get('W', self.getWidth()))
            h = int(st.get('H', self.getHeight()))
            frameT = int(st.get('FrameT', 10))
            sepT = int(st.get('SepT', 8))
            frameCol = awt.Color(160, 140, 120)
            frameDark = awt.Color(70, 60, 50)
            # Cabinet frame (grey/brown)
            try:
                g2.setColor(frameCol)
                g2.fillRect(0, 0, int(w), int(h))
                g2.setColor(bg)
                g2.fillRect(int(frameT), int(frameT), int(w - 2 * frameT), int(h - 2 * frameT))
                # Thin dark line to suggest a joint/groove
                mid = max(1, int(frameT) // 2)
                g2.setColor(frameDark)
                g2.drawRect(int(mid), int(mid), int(w - 2 * mid - 1), int(h - 2 * mid - 1))
                g2.drawRect(int(frameT), int(frameT), int(w - 2 * frameT - 1), int(h - 2 * frameT - 1))
            except:
                pass
            pad = int(frameT) + int(st.get('Pad', 12))
            destRotors = st.get('DestRotors') or []
            stopRotors = st.get('StopRotors') or []
            rowsPerCol = int(st.get('StopRowsPerCol', 10))

            plateText = st.get('PlateText') or ""
            plateAlert = bool(st.get('PlateAlert', False))

            # Sizes
            destH = int(st.get('DestCellH', 28))
            destW = int(st.get('DestCellW', 260))
            stopH = int(st.get('StopCellH', 22))
            stopW = int(st.get('StopCellW', 220))
            gapY = int(st.get('GapY', 10))
            colGap = int(st.get('ColGap', 18))

            # Fonts
            fontDest = MakeFont(FONT_FAMILY_MAIN, int(st.get('DestFont', 14)), True)
            fontStop = MakeFont(FONT_FAMILY_MAIN, int(st.get('StopFont', 12)), False)
            fontHdr = MakeFont(FONT_FAMILY_MAIN, int(st.get('HdrFont', 16)), True)
            fontPlate = MakeFont(FONT_FAMILY_MAIN, int(st.get('PlateFont', 14)), True)

            y = pad

            # Destination rotors (stacked)
            if destRotors:
                xDest = pad + (w - 2 * pad - destW) // 2
                for dr in destRotors:
                    R = awt.Rectangle(int(xDest), int(y), int(destW), int(destH))
                    try:
                        curT = dr.CurrentText()
                        nxtT = dr.NextText()
                        off = int(getattr(dr, 'OffsetPx', 0))
                    except:
                        curT = ""; nxtT = ""; off = 0
                    DrawRotorWindow(g2, R, curT, nxtT, off, fontDest, textCol, bg)
                    y += destH + 4
                y += gapY

            # Clock row
            clockRowH = int(st.get('ClockRowH', 90))
            clockR = int(min(40, (clockRowH - 10) // 2))
            cy = int(y + clockRowH // 2)
            cx = int(pad + (w - 2 * pad) // 2)

            # TRAIN / DEPARTS
            try:
                g2.setFont(fontHdr)
                fmH = g2.getFontMetrics(fontHdr)
                train = "TRAIN"
                departs = "DEPARTS"
                tw = fmH.stringWidth(train)
                dw = fmH.stringWidth(departs)
                g2.setColor(textCol)
                g2.drawString(train, int(cx - clockR - 20 - tw), int(cy + fmH.getAscent() // 2))
                g2.drawString(departs, int(cx + clockR + 20), int(cy + fmH.getAscent() // 2))
            except:
                pass

            # Clock face
            mins = st.get('NowMinutes', None)
            if mins is None:
                mins = 0
            DrawAnalogClock(g2, cx, cy, clockR, mins, awt.Color(245, 245, 245), awt.Color(0, 0, 0), awt.Color(0, 0, 0))

            y += clockRowH + gapY
            # Cabinet separator between top block (destination/clock) and STOPPING AT panel
            try:
                ySep = int(y - max(0, gapY // 2) - (sepT // 2))
                g2.setColor(frameCol)
                g2.fillRect(int(frameT), int(ySep), int(w - 2 * frameT), int(sepT))
                g2.setColor(frameDark)
                g2.drawLine(int(frameT), int(ySep + (sepT // 2)), int(w - frameT), int(ySep + (sepT // 2)))
            except:
                pass


            # STOPPING AT header
            try:
                g2.setFont(fontHdr)
                fmH = g2.getFontMetrics(fontHdr)
                hdr = "STOPPING AT"
                g2.setColor(textCol)
                txHdr = int((w - fmH.stringWidth(hdr)) // 2)
                g2.drawString(hdr, txHdr, int(y + fmH.getAscent()))
                y += fmH.getHeight() + 6
            except:
                y += 24

            # STOPPING AT rotors - two columns
            leftX = pad
            rightX = pad + stopW + colGap
            # Center both columns in available width
            totalStopW = (stopW * 2) + colGap
            leftX = pad + (w - 2 * pad - totalStopW) // 2
            rightX = leftX + stopW + colGap

            # Draw in newspaper order: down left then down right
            for i in range(int(rowsPerCol)):
                idx = i
                R = awt.Rectangle(int(leftX), int(y + i * (stopH + 4)), int(stopW), int(stopH))
                if idx < len(stopRotors):
                    sr = stopRotors[idx]
                    DrawRotorWindow(g2, R, sr.CurrentText(), sr.NextText(), int(getattr(sr, 'OffsetPx', 0)), fontStop, textCol, bg)
                else:
                    DrawRotorWindow(g2, R, '', '', 0, fontStop, textCol, bg)
            for i in range(int(rowsPerCol)):
                idx = int(rowsPerCol) + i
                R = awt.Rectangle(int(rightX), int(y + i * (stopH + 4)), int(stopW), int(stopH))
                if idx < len(stopRotors):
                    sr = stopRotors[idx]
                    DrawRotorWindow(g2, R, sr.CurrentText(), sr.NextText(), int(getattr(sr, 'OffsetPx', 0)), fontStop, textCol, bg)
                else:
                    DrawRotorWindow(g2, R, '', '', 0, fontStop, textCol, bg)

            yStopsEnd = int(y + int(rowsPerCol) * (stopH + 4))
            y = yStopsEnd + gapY

            # Plate
            plateH = int(st.get('PlateH', 30))
            if str(plateText or "").strip() != "":
                pr = awt.Rectangle(int(pad + 10), int(y), int(w - 2 * pad - 20), int(plateH))
                DrawPlate(g2, pr, plateText, plateAlert, fontPlate)
        finally:
            try:
                g2.dispose()
            except:
                pass
# PIDRotorSingle.py (PART 4B OF 4)
# Controller and windows: per-platform rotor PID, timers, listeners, and startup.
# Requires PART 1..3 and PART 4A.

# ---- Optional imports when running as separate files ----
try:
    from PIDRotorSingle_part1 import *
except:
    pass
try:
    from PIDRotorSingle_part2 import *
except:
    pass
try:
    from PIDRotorSingle_part3 import *
except:
    pass
try:
    from PIDRotorSingle_part4a import *
except:
    pass

# -----------------------------------------------------------------------------
# Controller per platform
# -----------------------------------------------------------------------------

POLL_MS = 1000
ANIM_MS = 50
ANIM_PIX_PER_FRAME = 1

class PlatformRotorWindow(object):
    def __init__(self, PlatformText, OnCloseCallback=None):
        self.Platform = str(PlatformText)
        self.OnCloseCallback = OnCloseCallback

        self.Frame = None
        self.Panel = None

        self.DestPlan = DestinationRotorPlan()
        self.StopPlan = StopRotorPlan()

        self.DestRotors = []
        self.StopRotors = []

        self.PlateText = ""
        self.PlateAlert = False
        self.ClockMinutes = None
        self.ClockDisplayDial = None
        self.ClockTargetDial = None
        self.ClockAnimStepsRemaining = 0
        self.ClockAnimDeltaPerStep = 0.0

        self.UiScale = 1.0
        self.RenderSizes = None

        self._lastMinuteKey = None
        self._lastServiceRn = None

        self._pollTimer = None
        self._animTimer = None

        self._pcl = None
        self._bgWorker = None

        self._BuildUiOnEdt()
        self._InstallListeners()
        self._RebuildPlansAsync()
        self._StartTimers()

    def _BuildUiOnEdt(self):
        def _Run():
            self.Frame = swing.JFrame("Passenger information display: platform " + self.Platform)
            self.Frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
            self.Frame.setResizable(False)

            try:
                from TASIcon import SetFrameClockIcon
                SetFrameClockIcon(self.Frame, 32)
            except:
                pass

            cp = self.Frame.getContentPane()
            cp.setLayout(None)

            self.Panel = RotorSinglePanel(self)
            cp.add(self.Panel)

            class CloseHandler(awtevent.WindowAdapter):
                def windowClosing(innerSelf, e):
                    try:
                        self.Cleanup()
                    except:
                        pass
                def windowClosed(innerSelf, e):
                    try:
                        self.Cleanup()
                    except:
                        pass

            self.Frame.addWindowListener(CloseHandler())
            self._LayoutFrame()
            self.Frame.setVisible(True)

        InvokeLater(_Run)

    def _LayoutFrame(self):
        # Compute a conservative size from current settings and plan sizes.
        def _Apply():
                        # Read current settings
            rowsPerCol = int(ReadInt(SETTING_STOP_ROWS_PER_COL, DEFAULT_STOP_ROWS_PER_COL, 1, 200))
            stopRowsPerCol = int(max(1, rowsPerCol))
            try:
                if self.StopPlan is not None and int(getattr(self.StopPlan, 'RowsPerColumn', 0)) > 0:
                    stopRowsPerCol = int(self.StopPlan.RowsPerColumn)
            except:
                pass
            destRotors = int(ReadInt(SETTING_DEST_ROTORS_MIN, DEFAULT_DEST_ROTORS_MIN, 1, 50))
            try:
                if self.DestPlan is not None and len(getattr(self.DestPlan, 'RotorFaces', []) or []) > 0:
                    destRotors = int(len(self.DestPlan.RotorFaces))
            except:
                pass
            
            # Base geometry
            basePad = 12
            baseStopW = 220
            baseStopH = 22
            baseColGap = 18
            baseDestW = 260
            baseDestH = 28
            baseClockRowH = 90
            basePlateH = 30
            baseGapY = 10
            baseHdrH = 24
            baseFrameT = 10
            baseSepT = 8
            
            h0 = baseFrameT * 2 + basePad * 2
            h0 += int(destRotors) * (baseDestH + 4) + baseGapY
            h0 += baseClockRowH + baseGapY
            h0 += baseSepT
            h0 += baseHdrH
            h0 += int(stopRowsPerCol) * (baseStopH + 4) + baseGapY
            h0 += basePlateH + 10
            
            scale = 1.0
            try:
                ge = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
                maxB = ge.getMaximumWindowBounds()
                maxH = int(maxB.height) - 20
                if int(h0) > int(maxH) and int(h0) > 0:
                    scale = float(maxH) / float(h0)
            except:
                scale = 1.0
            if scale > 1.0:
                scale = 1.0
            if scale < 0.45:
                scale = 0.45
            self.UiScale = float(scale)
            
            pad = int(round(basePad * scale))
            stopW = int(round(baseStopW * scale))
            stopH = int(round(baseStopH * scale))
            colGap = int(round(baseColGap * scale))
            destW = int(round(baseDestW * scale))
            destH = int(round(baseDestH * scale))
            clockRowH = int(round(baseClockRowH * scale))
            plateH = int(round(basePlateH * scale))
            gapY = int(round(baseGapY * scale))
            hdrH = int(round(baseHdrH * scale))
            frameT = int(round(baseFrameT * scale))
            sepT = int(round(baseSepT * scale))
            if pad < 6: pad = 6
            if stopH < 14: stopH = 14
            if destH < 18: destH = 18
            if frameT < 3: frameT = 3
            if sepT < 3: sepT = 3
            
            self.RenderSizes = {
                'Pad': pad,
                'DestCellW': destW,
                'DestCellH': destH,
                'StopCellW': stopW,
                'StopCellH': stopH,
                'ColGap': colGap,
                'GapY': gapY,
                'ClockRowH': clockRowH,
                'PlateH': plateH,
                'FrameT': frameT,
                'SepT': sepT,
            }
            
            w = frameT * 2 + pad * 2 + (stopW * 2) + colGap
            h = frameT * 2 + pad * 2
            h += int(destRotors) * (destH + 4) + gapY
            h += clockRowH + gapY
            h += sepT
            h += hdrH
            h += int(stopRowsPerCol) * (stopH + 4) + gapY
            h += plateH + 10
            
            try:
                self.Panel.setBounds(0, 0, int(w), int(h))
            except:
                pass
            try:
                self.Frame.addNotify()
                ins = self.Frame.getInsets()
                iw = ins.left + ins.right
                ih = ins.top + ins.bottom
            except:
                iw = 0
                ih = 0
            try:
                self.Frame.setSize(int(w + iw), int(h + ih))
            except:
                pass

        InvokeLater(_Apply)

    def _InstallListeners(self):
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb):
                innerSelf.Cb = cb
            def propertyChange(innerSelf, e):
                try:
                    innerSelf.Cb(e)
                except:
                    pass

        self._pcl = PCL(self._OnAnyChange)
        try:
            if TimeMem is not None:
                TimeMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if DayMem is not None:
                DayMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if TTMem is not None:
                TTMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            ovMem = TBL.ProvideMemoryBySuffix(MEM_PID_PLATFORM_OVERRIDES, "")
            if ovMem is not None:
                ovMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if PAR is not None:
                PAR.addPlatformListener(self._pcl)
        except:
            pass

    def _OnAnyChange(self, e=None):
        # Timetable change implies plans must be rebuilt.
        try:
            if TTMem is not None:
                # any change could be time/day too; detect by name
                pass
        except:
            pass
        # Always refresh display; rebuild plans if timetable likely changed.
        try:
            self._RefreshServiceAndTargets()
        except:
            pass

    def _StartTimers(self):
        # Poll timer for time changes and service updates.
        def _Poll(ev=None):
            try:
                self._RefreshServiceAndTargets()
            except:
                pass
        try:
            self._pollTimer = swing.Timer(int(POLL_MS), _Poll)
            self._pollTimer.setRepeats(True)
            self._pollTimer.start()
        except:
            self._pollTimer = None

        # Animation timer always runs; light-weight stepping.
        def _Anim(ev=None):
            try:
                self._StepAnimation()
            except:
                pass
        try:
            self._animTimer = swing.Timer(int(ANIM_MS), _Anim)
            self._animTimer.setRepeats(True)
            self._animTimer.start()
        except:
            self._animTimer = None

    def _RebuildPlansAsync(self):
        # Plan building can be moderately expensive; do it off the EDT.
        try:
            from java.lang import Thread
        except:
            Thread = None

        def _Work():
            allRows = CsvRows()
            destPlan = BuildDestinationRotorPlan(allRows, self.Platform)
            stopPlan = BuildStopRotorPlan(allRows, self.Platform)

            def _Apply():
                self.DestPlan = destPlan
                self.StopPlan = stopPlan
                self._BuildRotorStatesFromPlans()
                self._LayoutFrame()
                self._RefreshServiceAndTargets()
                try:
                    if self.Panel is not None:
                        self.Panel.repaint()
                except:
                    pass

            InvokeLater(_Apply)

        if Thread is None:
            _Work()
        else:
            try:
                Thread(_Work).start()
            except:
                _Work()

    def _BuildRotorStatesFromPlans(self):
        # Build/resize the RotorAnimState arrays from the plans.
        dr = []
        for faces in (self.DestPlan.RotorFaces or []):
            dr.append(RotorAnimState(faces))
        self.DestRotors = dr

        sr = []
        for faces in (self.StopPlan.RotorFaces or []):
            sr.append(RotorAnimState(faces))
        self.StopRotors = sr

    def _DialFromMinutes(self, MinutesVal):

     try:

      mm = float(MinutesVal)

     except:

      try:

       mm = float(int(MinutesVal))

      except:

       mm = 0.0

     try:

      d = mm % 720.0

     except:

      d = 0.0

     if d < 0.0:

      d = d + 720.0

     return float(d)

    def _StartClockAnimationTo(self, TargetMinutes):

     tgt = self._DialFromMinutes(TargetMinutes)

     if self.ClockDisplayDial is None:

      self.ClockDisplayDial = float(tgt)

     cur = float(self.ClockDisplayDial)

     try:

      fwd = (tgt - cur) % 720.0

     except:

      fwd = 0.0

     back = fwd - 720.0

     delta = back if abs(back) < abs(fwd) else fwd

     if abs(delta) < 0.01:

      self.ClockDisplayDial = float(tgt)

      self.ClockTargetDial = float(tgt)

      self.ClockAnimStepsRemaining = 0

      self.ClockAnimDeltaPerStep = 0.0

      return

     try:

      dur = 0.6 + (abs(delta) / 360.0) * 1.4

     except:

      dur = 1.0

     if dur < 0.4:

      dur = 0.4

     if dur > 2.5:

      dur = 2.5

     try:

      steps = int((dur * 1000.0) / float(ANIM_MS))

     except:

      steps = 20

     if steps < 1:

      steps = 1

     self.ClockTargetDial = float(tgt)

     self.ClockAnimStepsRemaining = int(steps)

     try:

      self.ClockAnimDeltaPerStep = float(delta) / float(steps)

     except:

      self.ClockAnimDeltaPerStep = 0.0


    def _SetTargetsForService(self, svc):
        # Destination: all blank except the rotor containing the destination.
        destText = ""
        try:
            destText = str(svc.get('Destination', '') or '').strip()
        except:
            destText = ""
        # Clock should show the time of the next train (adjusted for delay)
        try:
            self.ClockMinutes = int(svc.get('AdjMin', self.ClockMinutes))
        except:
            pass

        for r in (self.DestRotors or []):
            r.SetTargetByText("")

        if destText != "":
            dk = NormKey(destText)
            try:
                ri, fi = self.DestPlan.DestToRotorFace.get(dk)
                ri = int(ri)
                fi = int(fi)
            except:
                ri = None
                fi = None
            if ri is not None and 0 <= int(ri) < len(self.DestRotors):
                # Activate only this rotor
                self.DestRotors[int(ri)].SetTargetByText(destText)

        # Stops: blank all then set face for each stop.
        for r in (self.StopRotors or []):
            r.SetTargetByText("")

        stops = []
        try:
            stops = svc.get('Stops', []) or []
        except:
            stops = []

        for s in stops:
            k = NormKey(s)
            if k == "":
                continue
            try:
                rr, ff = self.StopPlan.StationToRotorFace.get(k)
                rr = int(rr)
                ff = int(ff)
            except:
                continue
            if rr < 0 or rr >= len(self.StopRotors):
                continue
            # Set target by display text at that face
            try:
                txt = str(self.StopRotors[rr].Faces[ff] or '')
            except:
                txt = str(s)
            self.StopRotors[rr].SetTargetByText(txt)

        # Plate priority: CANCELLED > DELAYED (threshold) > Special.
        plateText = ""
        plateAlert = False
        try:
            if bool(svc.get('IsCancelled', False)):
                plateText = "CANCELLED"
                plateAlert = True
            elif bool(svc.get('IsDelayedForPlate', False)):
                plateText = "DELAYED"
                plateAlert = True
            else:
                plateText = str(svc.get('Special', '') or '').strip()
                plateAlert = False
        except:
            plateText = ""
            plateAlert = False

        self.PlateText = plateText
        self.PlateAlert = bool(plateAlert)

    def _RefreshServiceAndTargets(self):
        # Refresh on minute change or when the RN changes.
        nowMin = CurrentMinutesFromCurrentTimeMem()
        if nowMin is None:
            nowMin = 0
        try:
            if self.ClockMinutes is not None:
                nowMin = int(self.ClockMinutes)
        except:
            pass
        minuteKey = int(nowMin)

        svc = GetNextServiceForPlatform(self.Platform)
        rn = None
        try:
            rn = str(svc.get('RN')) if svc is not None else None
        except:
            rn = None

        needUpdate = False
        if self._lastMinuteKey is None or int(self._lastMinuteKey) != int(minuteKey):
            needUpdate = True
        if str(rn) != str(self._lastServiceRn):
            needUpdate = True
        rnChanged = (str(rn) != str(self._lastServiceRn))
        # Animate clock hands only when a different train is displayed
        if rnChanged and svc is not None:
         try:
          self._StartClockAnimationTo(int(svc.get('AdjMin', 0)))
         except:
          pass

        self._lastMinuteKey = int(minuteKey)
        self._lastServiceRn = rn

        # Apply targets even if not representable: unknown stops will be ignored.
        if svc is not None:
            self._SetTargetsForService(svc)
        else:
            # No service: blank everything and clear plate.
            for r in (self.DestRotors or []):
                r.SetTargetByText("")
            for r in (self.StopRotors or []):
                r.SetTargetByText("")
            self.PlateText = ""
            self.PlateAlert = False

        if needUpdate:
            try:
                if self.Panel is not None:
                    self.Panel.repaint()
            except:
                pass

    def _StepAnimation(self):
     # Step all rotors; repaint if any rotor state changes (including the final
     # alignment frame when Step() returns False).
     changed = False
     destH = 28
     stopH = 22
     try:
      if self.RenderSizes is not None:
       destH = int(self.RenderSizes.get('DestCellH', destH))
       stopH = int(self.RenderSizes.get('StopCellH', stopH))
     except:
      pass
     for r in (self.DestRotors or []):
      try:
       bFace = int(getattr(r, 'FaceIdx', 0))
       bOff = int(getattr(r, 'OffsetPx', 0))
       bRoll = bool(getattr(r, 'IsRolling', False))
      except:
       bFace = 0
       bOff = 0
       bRoll = False
      try:
       still = bool(r.Step(destH, ANIM_PIX_PER_FRAME))
      except:
       still = False
      if still:
       changed = True
      else:
       try:
        if int(getattr(r, 'FaceIdx', 0)) != bFace or int(getattr(r, 'OffsetPx', 0)) != bOff or bool(getattr(r, 'IsRolling', False)) != bRoll:
         changed = True
       except:
        pass
     for r in (self.StopRotors or []):
      try:
       bFace = int(getattr(r, 'FaceIdx', 0))
       bOff = int(getattr(r, 'OffsetPx', 0))
       bRoll = bool(getattr(r, 'IsRolling', False))
      except:
       bFace = 0
       bOff = 0
       bRoll = False
      try:
       still = bool(r.Step(stopH, ANIM_PIX_PER_FRAME))
      except:
       still = False
      if still:
       changed = True
      else:
       try:
        if int(getattr(r, 'FaceIdx', 0)) != bFace or int(getattr(r, 'OffsetPx', 0)) != bOff or bool(getattr(r, 'IsRolling', False)) != bRoll:
         changed = True
       except:
        pass
     # Clock hand animation step
     clockChanged = False
     try:
      if int(getattr(self, 'ClockAnimStepsRemaining', 0)) > 0 and self.ClockDisplayDial is not None:
       self.ClockDisplayDial = float(self.ClockDisplayDial) + float(self.ClockAnimDeltaPerStep)
       if self.ClockDisplayDial >= 720.0:
        self.ClockDisplayDial = self.ClockDisplayDial - 720.0
       if self.ClockDisplayDial < 0.0:
        self.ClockDisplayDial = self.ClockDisplayDial + 720.0
       self.ClockAnimStepsRemaining = int(self.ClockAnimStepsRemaining) - 1
       clockChanged = True
       if int(self.ClockAnimStepsRemaining) <= 0 and self.ClockTargetDial is not None:
        self.ClockDisplayDial = float(self.ClockTargetDial)
        self.ClockAnimDeltaPerStep = 0.0
     except:
      pass
     if changed or clockChanged:
      try:
       if self.Panel is not None:
        self.Panel.repaint()
      except:
       pass

    def GetRenderState(self):
        # Provide render state for the panel.
        nowMin = CurrentMinutesFromCurrentTimeMem()
        if nowMin is None:
         nowMin = 0
        try:
         if self.ClockDisplayDial is not None:
          nowMin = float(self.ClockDisplayDial)
         elif self.ClockMinutes is not None:
          nowMin = float(int(self.ClockMinutes) % (24 * 60))
        except:
         pass

        # Use stop plan to size columns.
        rowsPerCol = int(self.StopPlan.RowsPerColumn) if self.StopPlan is not None else int(ReadInt(SETTING_STOP_ROWS_PER_COL, DEFAULT_STOP_ROWS_PER_COL, 1, 200))
        if rowsPerCol < 1:
            rowsPerCol = 1

        # Current panel size
        try:
            w = int(self.Panel.getWidth())
            h = int(self.Panel.getHeight())
        except:
            w = 520
            h = 420

        sz = self.RenderSizes or {}
        destH = int(sz.get('DestCellH', 28))
        destW = int(sz.get('DestCellW', 260))
        stopH = int(sz.get('StopCellH', 22))
        stopW = int(sz.get('StopCellW', 220))
        colGap = int(sz.get('ColGap', 18))
        gapY = int(sz.get('GapY', 10))
        clockRowH = int(sz.get('ClockRowH', 110))
        plateH = int(sz.get('PlateH', 30))
        frameT = int(sz.get('FrameT', 10))
        sepT = int(sz.get('SepT', 8))
        sc = float(getattr(self, 'UiScale', 1.0))
        if sc <= 0.0: sc = 1.0
        destFont = int(max(10, round(14 * sc)))
        stopFont = int(max(9, round(12 * sc)))
        hdrFont = int(max(14, round(24 * sc)))
        plateFont = int(max(10, round(14 * sc)))

        return {
            'Pad': int(sz.get('Pad', 12)),
            'W': w,
            'H': h,
            'NowMinutes': nowMin,
            'DestRotors': list(self.DestRotors or []),
            'StopRotors': list(self.StopRotors or []),
            'StopRowsPerCol': int(rowsPerCol),
            'PlateText': str(self.PlateText or ''),
            'PlateAlert': bool(self.PlateAlert),
            # Geometry tunables
            'DestCellH': int(destH),
            'DestCellW': int(destW),
            'StopCellH': int(stopH),
            'StopCellW': int(stopW),
            'GapY': int(gapY),
            'ColGap': int(colGap),
            'ClockRowH': int(clockRowH),
            'PlateH': int(plateH),
 'FrameT': int(frameT),
 'SepT': int(sepT),
            # Font sizes
            'DestFont': int(destFont),
            'StopFont': int(stopFont),
            'HdrFont': int(hdrFont),
            'PlateFont': int(plateFont),
        }

    def Cleanup(self):
        # Stop timers
        try:
            if self._pollTimer is not None:
                self._pollTimer.stop()
        except:
            pass
        self._pollTimer = None
        try:
            if self._animTimer is not None:
                self._animTimer.stop()
        except:
            pass
        self._animTimer = None

        # Remove listeners
        try:
            if TimeMem is not None and self._pcl is not None:
                TimeMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if DayMem is not None and self._pcl is not None:
                DayMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if TTMem is not None and self._pcl is not None:
                TTMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            ovMem = TBL.ProvideMemoryBySuffix(MEM_PID_PLATFORM_OVERRIDES, "")
            if ovMem is not None and self._pcl is not None:
                ovMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if PAR is not None and self._pcl is not None:
                PAR.removePlatformListener(self._pcl)
        except:
            pass
        self._pcl = None

        # Inform system
        try:
            if self.OnCloseCallback is not None:
                self.OnCloseCallback(self.Platform)
        except:
            pass

        # Dispose frame
        try:
            if self.Frame is not None:
                self.Frame.dispose()
        except:
            pass
        self.Frame = None


# -----------------------------------------------------------------------------
# System manager: one window per platform
# -----------------------------------------------------------------------------

class PIDRotorSingleSystem(object):
    def __init__(self):
        self.Manager = PlatformPIDManager()
        self.Windows = {}  # platform -> PlatformRotorWindow
        self.Manager.AddListener(self._OnPlatformsChanged)
        self._OnPlatformsChanged(self.Manager.Platforms)

    def _OnPlatformsChanged(self, PlatformsList):
        plats = list(PlatformsList or [])
        # Create missing
        for p in plats:
            if p not in self.Windows:
                self.Windows[p] = PlatformRotorWindow(p, self._OnWindowClosed)
        # Remove surplus
        toRemove = [p for p in list(self.Windows.keys()) if p not in plats]
        for p in toRemove:
            try:
                self.Windows[p].Cleanup()
            except:
                pass
            try:
                del self.Windows[p]
            except:
                pass
        # Cascade positions
        x0, y0 = 50, 50
        dx, dy = 40, 40
        idx = 0
        for p in plats:
            try:
                w = self.Windows.get(p)
                if w is not None and w.Frame is not None:
                    w.Frame.setLocation(int(x0 + dx * idx), int(y0 + dy * idx))
            except:
                pass
            idx += 1

    def _OnWindowClosed(self, PlatformText):
        try:
            if PlatformText in self.Windows:
                del self.Windows[PlatformText]
        except:
            pass

    def Cleanup(self):
        try:
            if self.Manager is not None:
                self.Manager.Cleanup()
        except:
            pass
        self.Manager = None
        for p in list(self.Windows.keys()):
            try:
                self.Windows[p].Cleanup()
            except:
                pass
        self.Windows = {}


# -----------------------------------------------------------------------------
# RUN (avoid duplicates on re-run)
# -----------------------------------------------------------------------------

try:
    if 'PIDRotorSingle_Manager' in globals() and PIDRotorSingle_Manager is not None:
        PIDRotorSingle_Manager.Cleanup()
except:
    pass

PIDRotorSingle_Manager = PIDRotorSingleSystem()
