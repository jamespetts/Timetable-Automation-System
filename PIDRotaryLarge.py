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
# Rotary block indicator (large): early mechanical/electro-mechanical departures board.
# JMRI 5.14 / Jython 2.7 / ASCII only / CamelCase / Thread-safe EDT.
# <<PID-DISP-NAME: Departure board (rotary blocks, large)>>
# <<DESCRIPTION: Rotary-block indicator with deterministic destination grouping and per-row roller decks. Animates service changes with true roller motion: faces roll through intermediate positions (numbers and stations). Uses CURRENTTIME memory as primary time source with lightweight polling.>>
# User-configurable settings discovered by TASSetup:
# <<SETTING DESCRIPTION NUMBER: Rotary preferred columns>>
# <<SETTING DESCRIPTION NUMBER: Rotary preferred rows>>
# <<SETTING DESCRIPTION NUMBER: Rotary clear blank hold ms>>
# <<SETTING DESCRIPTION BOOLEAN: Rotary use 12 hour time>>
# <<SETTING DESCRIPTION BOOLEAN: Rotary hide platform until allocated>>
# <<SETTING DESCRIPTION NUMBER: Rotary future window minutes>>
# <<SETTING DESCRIPTION NUMBER: Rotary timewarp threshold minutes>>
# <<SETTING DESCRIPTION STRING: Rotary header font family>>
# <<SETTING DESCRIPTION STRING: Rotary cell font family>>
#

import javax.swing as swing
import java.awt as awt
import java.beans as beans
import java.awt.event as awtevent

import jmri
from jmri import InstanceManager

import os
import csv

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


# -------------------------------
# Settings
# -------------------------------

def ReadInt(MemName, DefaultVal, MinVal=None, MaxVal=None):
    try:
        Raw = TBL.SafeGetOrCreateMemoryValue(MemName, str(int(DefaultVal)))
        N = int(float(str(Raw).strip()))
        if MinVal is not None:
            N = max(int(MinVal), N)
        if MaxVal is not None:
            N = min(int(MaxVal), N)
        return int(N)
    except:
        return int(DefaultVal)


def ReadBool(MemName, DefaultVal=False):
    try:
        Raw = TBL.SafeGetOrCreateMemoryValue(MemName, "true" if DefaultVal else "false")
        T = str(Raw).strip().lower()
        if T in ["1", "true", "yes", "y", "on", "enabled"]:
            return True
        if T in ["0", "false", "no", "n", "off", "disabled"]:
            return False
        return bool(DefaultVal)
    except:
        return bool(DefaultVal)


def ReadStr(MemName, DefaultVal=""):
    try:
        Raw = TBL.SafeGetOrCreateMemoryValue(MemName, str(DefaultVal))
        return str(Raw if Raw is not None else "").strip()
    except:
        try:
            return str(DefaultVal if DefaultVal is not None else "").strip()
        except:
            return ""


try:
    _oldPref = str(TBL.SafeGetMemoryValue("TAS_USER_SETTING_ROTARY_PREFERRED_MAX_COLUMNS", "") or "").strip()
    _newPref = str(TBL.SafeGetMemoryValue("TAS_USER_SETTING_ROTARY_PREFERRED_COLUMNS", "") or "").strip()
    if (_newPref == "") and (_oldPref != ""):
        TBL.SafeSetMemoryValue("TAS_USER_SETTING_ROTARY_PREFERRED_COLUMNS", _oldPref)
except:
    pass
PREF_COLS = ReadInt("TAS_USER_SETTING_ROTARY_PREFERRED_COLUMNS", 15, 1, 200)
PREF_ROWS = ReadInt("TAS_USER_SETTING_ROTARY_PREFERRED_ROWS", 15, 1, 200)
CLEAR_BLANK_HOLD_MS = ReadInt("TAS_USER_SETTING_ROTARY_CLEAR_BLANK_HOLD_MS", 2000, 0, 60000)
USE_12_HOUR_TIME = ReadBool("TAS_USER_SETTING_ROTARY_USE_12_HOUR_TIME", False)
HIDE_PLAT_UNTIL_ALLOC = ReadBool("TAS_USER_SETTING_ROTARY_HIDE_PLATFORM_UNTIL_ALLOCATED", False)
FUTURE_WINDOW_MIN = ReadInt("TAS_USER_SETTING_ROTARY_FUTURE_WINDOW_MINUTES", 0, 0, 10)
TIMEWARP_THRESHOLD_MIN = ReadInt("TAS_USER_SETTING_ROTARY_TIMEWARP_THRESHOLD_MINUTES", 2, 0, 240)
HEADER_FONT_FAMILY = ReadStr("TAS_USER_SETTING_ROTARY_HEADER_FONT_FAMILY", "SansSerif")
CELL_FONT_FAMILY = ReadStr("TAS_USER_SETTING_ROTARY_CELL_FONT_FAMILY", "")

# Timers / animation
POLL_REFRESH_MS = 1000
ROLL_FRAME_MS = 30
ROLL_PIX_PER_FRAME = 3
ROW_FRAME_MS = 30
ROW_PIX_PER_FRAME = 3
ROLLER_GAP = 4 # Reduced gap to allow AM/PM rollers to fit in 90px column width


# -------------------------------
# Paths and data
# -------------------------------

def ActiveProfilePath():
    try:
        return jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    except:
        return None


def ActiveProfileNameUpper():
    try:
        Nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        S = ("" if Nm is None else str(Nm)).strip()
        return S.upper()
    except:
        return ""


def TimetablePathFromMemory():
    try:
        Name = (TBL.SafeGetOrCreateMemoryValue("CURRENTTIMETABLE", "") or "").strip()
    except:
        Name = ""
    if Name == "":
        return None
    Prof = ActiveProfilePath()
    if not Prof:
        return None
    return TASPathResolver.GetTimetableCsvPath(Name)
def CsvRows():
    Path = TimetablePathFromMemory()
    if not (Path and os.path.exists(Path)):
        return []
    Rows = []
    try:
        with open(Path, "r") as F:
            Rdr = csv.DictReader(F, delimiter="\t")
            for R in Rdr:
                Rows.append(R)
    except Exception as Ex:
        try:
            print("[PIDRotaryLarge] Failed to read timetable: " + str(Ex))
        except:
            pass
        return []
    return Rows


def CaseInsensitive(Row, Key):
    Target = (Key or "").strip().lower()
    try:
        Keys = Row.keys() or []
    except:
        Keys = []
    for K in Keys:
        try:
            if (K or "").strip().lower() == Target:
                V = Row.get(K, "")
                return (V or "").strip()
        except:
            pass
    return ""


def PlatformField(Row):
    Val = (Row.get("Plat", "") or "").strip()
    if Val == "":
        Val = (Row.get("Platform", "") or "").strip()
    return Val


# -------------------------------
# Time parsing
# -------------------------------

import java.text.SimpleDateFormat as SimpleDateFormat

Parser12 = SimpleDateFormat("h:mm a")
Parser24 = SimpleDateFormat("H:mm")
Parser12S = SimpleDateFormat("h:mm:ss a")
Parser24S = SimpleDateFormat("H:mm:ss")


def ParseMinutes(S):
    S = (S or "").strip()
    if S == "":
        return None
    for P in [Parser12, Parser24, Parser12S, Parser24S]:
        try:
            D = P.parse(S)
            return D.getHours() * 60 + D.getMinutes()
        except:
            pass
    try:
        if ":" in S and len(S) <= 5:
            H, M = S.split(":")
            return int(H) * 60 + int(M)
    except:
        pass
    return None


def MinutesToDisplayParts(TotalMinutes, Use12Hour):
    if TotalMinutes is None:
        return ("", "", "")
    TotalMinutes = int(TotalMinutes) % (24 * 60)
    H24 = TotalMinutes // 60
    M = TotalMinutes % 60
    if not Use12Hour:
        return ("%02d" % int(H24), "%02d" % int(M), "")
    Am = (H24 < 12)
    H12 = H24 % 12
    if H12 == 0:
        H12 = 12
    # No leading zero on hours or minutes in 12-hour mode.
    return (str(H12), str(int(M)), "AM" if Am else "PM")

def TimeRollerSequences(Use12Hour):
    if not Use12Hour:
        h = [""]
        for i in range(24):
            h.append("%02d" % i)
        m = [""]
        for i in range(60):
            m.append("%02d" % i)
        return {'H': h, 'M': m, 'AP': None}
    h = [""]
    for i in range(1, 13):
        h.append(str(i))
    # No leading zero on minutes in 12-hour mode.
    m = [""]
    for i in range(60):
        m.append(str(i))
    # Blank between PM and AM in the forward direction: blank, AM, PM, blank...
    ap = ["", "AM", "PM"]
    return {'H': h, 'M': m, 'AP': ap}
Timebase = None
try:
    Timebase = InstanceManager.getDefault(jmri.Timebase)
except:
    Timebase = None

DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
TTMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")


def CurrentMinutes():
    try:
        CurStr = TBL.SafeGetOrCreateMemoryValue("CURRENTTIME", "")
    except:
        CurStr = ""
    Mm = ParseMinutes(CurStr)
    if Mm is not None:
        return Mm
    try:
        if Timebase is not None:
            Ft = Timebase.getTime()
            return Ft.getHours() * 60 + Ft.getMinutes()
    except:
        pass
    return None


# -------------------------------
# Service model and delay inheritance
# -------------------------------

def HasDepartedAtConfiguredTP(ReportingNumber, DayName, NowMinutes):
    if TR is None:
        return False
    try:
        Tps = []
        Raw = TBL.SafeGetOrCreateMemoryValue("PID_DEPARTURE_TP", "")
        if Raw:
            for P in str(Raw).replace(",", ";").split(";"):
                T = (P or "").strip()
                if T != "":
                    Tps.append(T)
        if not Tps:
            Base = ""
            try:
                Nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
                Base = ("" if Nm is None else str(Nm)).strip()
            except:
                Base = ""
            if Base != "":
                Tps = [Base]
        for Tp in (Tps or []):
            try:
                Entries = TR.getTiming(Tp) or []
            except:
                Entries = []
            for Rec in Entries:
                try:
                    Rn = Rec[0]
                    TStr = Rec[2]
                    D = Rec[3]
                except:
                    continue
                if str(Rn) != str(ReportingNumber):
                    continue
                if str(D) != str(DayName):
                    continue
                Mm = ParseMinutes(TStr)
                if Mm is None:
                    continue
                if Mm <= int(NowMinutes):
                    return True
    except:
        pass
    return False


def ResolveDelayWithInheritance(RowsToday, Rn, SchedDepMin, Visited=None):
    if Visited is None:
        Visited = set()
    if Rn in Visited:
        return ("ontime", 0)
    Visited.add(Rn)

    DelayVal = None
    if getDisruption is not None:
        try:
            DelayVal = getDisruption(Rn)
        except:
            DelayVal = None

    if DelayVal is not None:
        try:
            Delay = int(DelayVal)
        except:
            Delay = 0
        if Delay >= 1440:
            return ("cancel", None)
        if Delay > 0:
            return ("delay", Delay)

    Formers = []
    try:
        for R in RowsToday:
            if (CaseInsensitive(R, "Forms") or "") == Rn:
                Arr = CaseInsensitive(R, "Arr")
                ArrMin = ParseMinutes(Arr) if Arr else None
                Formers.append((R, ArrMin))
    except:
        Formers = []

    if not Formers:
        return ("ontime", 0)

    Chosen = None
    if SchedDepMin is not None:
        Before = [T for T in Formers if T[1] is not None and T[1] <= SchedDepMin]
        if Before:
            Before.sort(key=lambda T: T[1])
            Chosen = Before[-1][0]
    if Chosen is None:
        Chosen = Formers[0][0]

    FormerRn = CaseInsensitive(Chosen, "Reporting number")
    return ResolveDelayWithInheritance(RowsToday, FormerRn, SchedDepMin, Visited)


def _IsEcsDestination(DestText):
    try:
        d = str(DestText or "").strip().lower()
    except:
        d = ""
    if d.startswith("empty"):
        return True
    if d == "empty to depot":
        return True
    return False


class Service(object):
    def __init__(self, Row, DayName, NowMinutes):
        self.RN = CaseInsensitive(Row, "Reporting number")
        self.Dep = CaseInsensitive(Row, "Dep")
        self.DepMin = ParseMinutes(self.Dep)
        self.Dest = CaseInsensitive(Row, "Destination")
        self.Call = CaseInsensitive(Row, "Calling pattern")
        self.Special = CaseInsensitive(Row, "Special")

        self.HasAlloc = False
        PlatVal = ""
        if PAR is not None:
            try:
                Alloc = PAR.getPlatform(self.RN)
                self.HasAlloc = (Alloc is not None and str(Alloc).strip() != "")
                if self.HasAlloc:
                    PlatVal = str(Alloc).strip()
            except:
                self.HasAlloc = False
        if PlatVal == "":
            PlatVal = (PlatformField(Row) or "").strip()
        if HIDE_PLAT_UNTIL_ALLOC and (not self.HasAlloc):
            PlatVal = ""
        self.Plat = PlatVal

        self.Departed = HasDepartedAtConfiguredTP(self.RN, DayName, NowMinutes)
        self.Status = ""
        self.AdjMin = self.DepMin if self.DepMin is not None else 999999


def NextServicesTodayAll():
    Rows = CsvRows()
    try:
        Day = TBL.SafeGetOrCreateMemoryValue("DAYOFWEEK", "")
    except:
        Day = ""
    Now = CurrentMinutes()
    if Now is None:
        return []

    CurStation = ActiveProfileNameUpper()

    RowsToday = []
    for R in Rows:
        try:
            if ((R.get(Day, "") or "").strip().lower() == "true"):
                RowsToday.append(R)
        except:
            pass

    Models = []
    for R in RowsToday:
        Dep = CaseInsensitive(R, "Dep")
        if Dep == "":
            continue
        M = Service(R, Day, Now)
        if M.DepMin is None:
            continue

        # Exclude arrivals to current station.
        try:
            if CurStation != "" and str(M.Dest or "").strip().upper() == CurStation:
                continue
        except:
            pass

        # Exclude ECS.
        if _IsEcsDestination(M.Dest):
            continue

        Kind, Val = ResolveDelayWithInheritance(RowsToday, M.RN, M.DepMin, Visited=set())

        if Kind == "cancel":
            try:
                if int(Now) > (int(M.DepMin) + 1):
                    continue
            except:
                continue
            M.Status = "CANCELLED"
            M.AdjMin = M.DepMin
        elif Kind == "delay" and Val and int(Val) > 0:
            M.Status = "DELAYED"
            M.AdjMin = M.DepMin + int(Val)
        else:
            if M.DepMin < Now:
                continue
            if M.Departed:
                continue
            M.Status = "ONTIME"
            M.AdjMin = M.DepMin

        Models.append(M)

    Models.sort(key=lambda T: T.AdjMin)

    # Look-ahead window.
    try:
        Lim = int(FUTURE_WINDOW_MIN)
    except:
        Lim = 0
    if Lim > 0:
        try:
            Upper = int(Now) + int(Lim)
        except:
            Upper = None
        if Upper is not None:
            Out = []
            for Svc in Models:
                try:
                    if Svc.DepMin is not None and int(Svc.DepMin) <= int(Upper):
                        Out.append(Svc)
                except:
                    pass
            Models = Out

    return Models


# -------------------------------
# Grouping logic (solvability-based)
# -------------------------------


# ------------------------------------------------------------------
# Minimum columns per group based on look-ahead window
# ------------------------------------------------------------------

def _ParseDayFlags(Row):
    # Return list of day field names that are true for this row.
    out = []
    try:
        for k in (Row.keys() or []):
            try:
                v = (Row.get(k, '') or '').strip().lower()
            except:
                v = ''
            if v == 'true':
                lk = (k or '').strip().lower()
                if lk in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']:
                    out.append(k)
    except:
        pass
    return out

def ComputeMinColumnsByGroup(RowsAll, GroupIndexByDest, FutureWindowMin):
    # Returns dict: groupIndex -> required columns (>=0).
    # Requirement is the maximum number of services in that group that could be displayable at any time,
    # given the look-ahead window and the timetable over the whole week.
    # If FutureWindowMin <= 0, treat as 'no limit'.
    try:
        w = int(FutureWindowMin)
    except:
        w = 0
    if w < 0:
        w = 0

    perDay = {}  # dayName -> groupIndex -> sorted dep minutes

    for R in (RowsAll or []):
        dest = (CaseInsensitive(R, 'Destination') or '').strip()
        if dest == '' or _IsEcsDestination(dest):
            continue
        try:
            gi = GroupIndexByDest.get(str(dest).strip().lower())
        except:
            gi = None
        if gi is None:
            continue
        depStr = (CaseInsensitive(R, 'Dep') or '').strip()
        depMin = ParseMinutes(depStr)
        if depMin is None:
            continue
        for d in _ParseDayFlags(R):
            perDay.setdefault(d, {}).setdefault(int(gi), []).append(int(depMin))

    req = {}
    for d, byGroup in perDay.items():
        for gi, deps in byGroup.items():
            deps.sort()
            if not deps:
                continue
            if w == 0:
                m = len(deps)
            else:
                m = 0
                j = 0
                for i in range(len(deps)):
                    if j < i:
                        j = i
                    limit = deps[i] + w
                    while j < len(deps) and deps[j] <= limit:
                        j += 1
                    cnt = j - i
                    if cnt > m:
                        m = cnt
            if m > int(req.get(int(gi), 0)):
                req[int(gi)] = int(m)

    return req

def _NormKey(s):
    try:
        return str(s or "").strip().lower()
    except:
        return ""


def _RowRunsOnAnyDay(Row):
    try:
        for K in (Row.keys() or []):
            try:
                V = (Row.get(K, "") or "").strip().lower()
            except:
                V = ""
            if V == "true":
                return True
    except:
        pass
    return False


def _ParseStops(CallText):
    Out = []
    for T in str(CallText or "").split(","):
        S = (T or "").strip()
        if S != "":
            Out.append(S)
    return Out


def _EnsureDestAtEnd(Stops, Dest):
    D = (Dest or "").strip()
    if D == "":
        return list(Stops or [])
    S = list(Stops or [])
    if not S:
        return [D]
    try:
        if S[-1].strip().lower() == D.lower():
            return S
    except:
        pass
    S.append(D)
    return S


def _GroupKeyText(Dests):
    try:
        return ",".join(sorted([str(d).upper() for d in (Dests or [])]))
    except:
        return ""


def _Jaccard(A, B):
    try:
        if not A and not B:
            return 0.0
        I = float(len(A.intersection(B)))
        U = float(len(A.union(B)))
        if U <= 0.0:
            return 0.0
        return I / U
    except:
        return 0.0


def _DestProfilesWeek(RowsAll):
    Freq = {}
    StationSet = {}
    DisplayName = {}
    CurStation = ActiveProfileNameUpper()

    for R in (RowsAll or []):
        if not _RowRunsOnAnyDay(R):
            continue
        Dest = (CaseInsensitive(R, "Destination") or "").strip()
        if Dest == "":
            continue

        # Exclude arrivals and ECS.
        try:
            if CurStation != "" and str(Dest).strip().upper() == CurStation:
                continue
        except:
            pass
        if _IsEcsDestination(Dest):
            continue

        Freq[Dest] = int(Freq.get(Dest, 0)) + 1

        Stops = _EnsureDestAtEnd(_ParseStops(CaseInsensitive(R, "Calling pattern")), Dest)
        Sset = StationSet.get(Dest)
        if Sset is None:
            Sset = set()
            StationSet[Dest] = Sset
        for S in Stops:
            k = _NormKey(S)
            if k == "":
                continue
            Sset.add(k)
            if k not in DisplayName:
                DisplayName[k] = str(S).strip()
        dk = _NormKey(Dest)
        if dk != "" and dk not in DisplayName:
            DisplayName[dk] = str(Dest).strip()

    return Freq, StationSet, DisplayName


def _BuildInitialGroups(Freq, StationSet):
    groups = []
    for d in sorted(Freq.keys(), key=lambda x: (0 - int(Freq.get(x, 0)), str(x).upper())):
        groups.append({'Dests': [d], 'Freq': int(Freq.get(d, 0)), 'StationSet': set(StationSet.get(d, set()))})
    return groups


def _BuildGroupServiceSequences(RowsAll, GroupDestsLower):
    seqs = []
    for R in (RowsAll or []):
        if not _RowRunsOnAnyDay(R):
            continue
        Dest = (CaseInsensitive(R, "Destination") or "").strip()
        dk = _NormKey(Dest)
        if dk == "" or dk not in GroupDestsLower:
            continue
        Stops = _EnsureDestAtEnd(_ParseStops(CaseInsensitive(R, "Calling pattern")), Dest)
        keys = []
        for S in Stops:
            k = _NormKey(S)
            if k != "":
                keys.append(k)
        out = []
        last = None
        for k in keys:
            if last is None or k != last:
                out.append(k)
            last = k
        if out:
            seqs.append(out)
    return seqs


def _BuildConstraintsFromSequences(seqs):
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
        for i in range(len(seq) - 1):
            a = seq[i]
            b = seq[i + 1]
            if a == b:
                continue
            Succs[a].add(b)
            Preds[b].add(a)
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
    nodes = sorted(Preds.keys())
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
        return sorted(nodes), True
    return out, False


def SolveGroupRowsForRollerDecks(RowsAll, GroupDests, PreferredRows):
    # Returns: StationToRow, RowFaces (blank + stations), StationToFace, Cycle, RowsUsed
    destLower = set([_NormKey(d) for d in (GroupDests or []) if _NormKey(d) != ""]) 
    seqs = _BuildGroupServiceSequences(RowsAll, destLower)
    Preds, Succs, Co = _BuildConstraintsFromSequences(seqs)
    order, cycle = _TopoOrderOrFallback(Preds, Succs)

    StationToRow = {}
    RowToStations = []

    def _RowConflict(n, rowIdx):
        # Physical constraint: Max 3 stations per row (plus blank)
        if len(RowToStations[rowIdx]) >= 3:
            return True
        for other in (RowToStations[rowIdx] or []):
            if other in Co.get(n, set()):
                return True
            if other in Preds.get(n, set()) or other in Succs.get(n, set()):
                return True
            if n in Preds.get(other, set()) or n in Succs.get(other, set()):
                return True
        return False

    maxUsed = 0

    for n in order:
        minRow = 0
        for p in Preds.get(n, set()):
            if p in StationToRow:
                minRow = max(minRow, int(StationToRow[p]) + 1)
        r = int(minRow)
        while True:
            while r >= len(RowToStations):
                RowToStations.append([])
            if not _RowConflict(n, r):
                RowToStations[r].append(n)
                StationToRow[n] = r
                if (r + 1) > maxUsed:
                    maxUsed = r + 1
                break
            r += 1

    try:
        pref = int(PreferredRows)
    except:
        pref = 15
    if pref < 1:
        pref = 1

    rowsUsed = int(maxUsed)

    if len(RowToStations) < pref:
        while len(RowToStations) < pref:
            RowToStations.append([])

    RowFaces = []
    StationToFace = {}
    for r in range(len(RowToStations)):
        faces = [""]
        for s in RowToStations[r]:
            faces.append(s)
        RowFaces.append(faces)
        for fi in range(1, len(faces)):
            if faces[fi] != "":
                StationToFace[faces[fi]] = fi

    return StationToRow, RowFaces, StationToFace, cycle, rowsUsed


def _RowsRequiredForGroup(RowsAll, Dests, PrefRows):
    try:
        _, _, _, cycle, used = SolveGroupRowsForRollerDecks(RowsAll, Dests, PrefRows)
        if cycle:
            return int(PrefRows) + 1
        return int(used)
    except:
        return int(PrefRows) + 1


def _FindBestMerge(groups, StationSet, capStations, RowsAll, PrefRows):
    Best = None
    for i in range(len(groups)):
        Gi = groups[i]
        for j in range(i + 1, len(groups)):
            Gj = groups[j]
            try:
                unionSize = len(Gi['StationSet'].union(Gj['StationSet']))
            except:
                unionSize = 999999
            if unionSize > int(capStations):
                continue

            newDests = list(Gi.get('Dests') or []) + list(Gj.get('Dests') or [])
            rowsNeed = _RowsRequiredForGroup(RowsAll, newDests, PrefRows)
            # REMOVED CONSTRAINT: Allow merge even if rowsNeed > PrefRows.
            # This enables dynamic row increase to accommodate larger groups.
            
            sim = 0.0
            for da in (Gi.get('Dests') or []):
                for db in (Gj.get('Dests') or []):
                    sim = max(sim, _Jaccard(StationSet.get(da, set()), StationSet.get(db, set())))

            combFreq = int(Gi.get('Freq', 0)) + int(Gj.get('Freq', 0))
            pairKey = "|".join(sorted([_GroupKeyText(Gi.get('Dests')), _GroupKeyText(Gj.get('Dests'))]))

            # Tuple contains 7 values: score, sim, freq, union, key, i, j
            cand = (0 - int(rowsNeed), sim, combFreq, 0 - unionSize, pairKey, i, j)
            if Best is None or cand > Best:
                Best = cand

    return Best


def BuildDestinationGroupsWithCap(RowsAll, TargetGroups, CapStations, PreferredRows):
    Freq, StationSet, _ = _DestProfilesWeek(RowsAll)
    groups = _BuildInitialGroups(Freq, StationSet)

    cap = int(CapStations)
    tgt = int(TargetGroups)
    if tgt < 1:
        tgt = 1

    while len(groups) > tgt:
        best = _FindBestMerge(groups, StationSet, cap, RowsAll, PreferredRows)
        if best is None:
            break
        # Unpack 7 values: score, sim, freq, union, key, i, j
        _, _, _, _, _, i, j = best
        if j < i:
            i, j = j, i
        Gi = groups[i]
        Gj = groups[j]

        newDests = sorted(list(Gi.get('Dests') or []) + list(Gj.get('Dests') or []), key=lambda x: str(x).upper())
        newFreq = int(Gi.get('Freq', 0)) + int(Gj.get('Freq', 0))
        newSet = set(Gi.get('StationSet', set()))
        try:
            newSet.update(Gj.get('StationSet', set()))
        except:
            pass
        groups[i] = {'Dests': newDests, 'Freq': newFreq, 'StationSet': newSet}
        groups.pop(j)

    groups.sort(key=lambda g: (0 - int(g.get('Freq', 0)), _GroupKeyText(g.get('Dests'))))
    return groups


def ComputeHardMinimumGroups(RowsAll, PreferredRows):
    cap = max(3, int(PreferredRows) * 3)
    groups = BuildDestinationGroupsWithCap(RowsAll, 1, cap, PreferredRows)
    return int(len(groups))


def AllocateColumnsToGroups(Groups, TotalColumns):
    Total = int(TotalColumns)
    if Total < 1:
        Total = 1
    if not Groups:
        return []
    if Total < len(Groups):
        Total = len(Groups)
    SumFreq = 0
    for G in Groups:
        SumFreq += int(G.get('Freq', 0))
    if SumFreq <= 0:
        SumFreq = len(Groups)
    Alloc = []
    Used = 0
    Remainders = []
    for idx, G in enumerate(Groups):
        F = int(G.get('Freq', 0))
        Exact = (float(F) * float(Total)) / float(SumFreq)
        Base = int(Exact)
        if Base < 1:
            Base = 1
        Alloc.append(Base)
        Used += Base
        Rem = Exact - float(Base)
        Key = _GroupKeyText(G.get('Dests'))
        Remainders.append((Rem, F, Key, idx))
    if Used > Total:
        NeedRemove = Used - Total
        Remainders.sort(key=lambda T: (T[0], T[1], T[2]))
        k = 0
        while NeedRemove > 0 and k < len(Remainders):
            idx = Remainders[k][3]
            if Alloc[idx] > 1:
                Alloc[idx] -= 1
                NeedRemove -= 1
            else:
                k += 1
    Used = 0
    for a in Alloc:
        Used += int(a)
    if Used < Total:
        NeedAdd = Total - Used
        Remainders.sort(key=lambda T: (0 - T[0], 0 - T[1], T[2]))
        k = 0
        while NeedAdd > 0:
            idx = Remainders[k % len(Remainders)][3]
            Alloc[idx] += 1
            NeedAdd -= 1
            k += 1
    out = []
    for idx, G in enumerate(Groups):
        ng = {'Dests': list(G.get('Dests') or []), 'Freq': int(G.get('Freq', 0)), 'Cols': int(Alloc[idx])}
        ng['StationSet'] = set(G.get('StationSet', set()))
        out.append(ng)
    return out


def BuildGroupIndexByDest(GroupsPlan):
    M = {}
    gi = 0
    for G in (GroupsPlan or []):
        for D in (G.get('Dests') or []):
            M[_NormKey(D)] = gi
        gi += 1
    return M


def StripDiagnosticStationSet(GroupsPlan):
    out = []
    for G in (GroupsPlan or []):
        ng = {}
        for k in G.keys():
            if k != 'StationSet':
                ng[k] = G[k]
        out.append(ng)
    return out


# -------------------------------
# Platform roller sequence
# -------------------------------

def _PlatformParts(PlatText):
    S = (PlatText or "").strip()
    if S == "":
        return (None, "")
    Dig = ""
    Suf = ""
    for Ch in S:
        if Ch.isdigit() and Suf == "":
            Dig += Ch
        else:
            Suf += Ch
    if Dig == "":
        return (None, S.upper())
    try:
        N = int(Dig)
    except:
        N = None
    return (N, (Suf or "").strip().upper())


def BuildPlatformRollerSequence(RowsAll):
    LettersByN = {}
    MinN = None
    MaxN = None
    for R in (RowsAll or []):
        P = PlatformField(R)
        N, Suf = _PlatformParts(P)
        if N is None:
            continue
        if MinN is None or N < MinN:
            MinN = N
        if MaxN is None or N > MaxN:
            MaxN = N
        if Suf != "":
            LettersByN.setdefault(N, set()).add(Suf)
    if MinN is None or MaxN is None:
        return [""]
    if MinN < 1:
        MinN = 1
    Seq = [""]
    for N in range(int(MinN), int(MaxN) + 1):
        Seq.append(str(N))
        Letters = sorted(list(LettersByN.get(N, set())))
        for L in Letters:
            Seq.append(str(N) + str(L))
    return Seq


# -------------------------------
# Rendering helpers (fonts, wrapping, roller drawing)
# -------------------------------

def AvailableFamilies():
    try:
        ge = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []


def PickNarrowFamily():
    prefs = ["Liberation Sans Narrow", "Arial Narrow", "Nimbus Sans Narrow", "Liberation Sans", "Arial", "SansSerif"]
    fams = set([f.lower() for f in AvailableFamilies()])
    for p in prefs:
        if p.lower() in fams:
            return p
    return "SansSerif"


FONT_FAM_NARROW = PickNarrowFamily()
try:
    if CELL_FONT_FAMILY != "":
        FONT_FAM_NARROW = CELL_FONT_FAMILY
except:
    pass

FONT_FAM_SERIF = "Serif"


def MakeFont(Fam, Sz, Bold=False):
    style = awt.Font.BOLD if Bold else awt.Font.PLAIN
    return awt.Font(Fam, style, int(Sz))


def DrawWood(g2, R, Seed):
    base = awt.Color(50, 36, 26)
    g2.setColor(base)
    g2.fillRect(int(R.x), int(R.y), int(R.width), int(R.height))
    try:
        from java.util import Random
        rnd = Random(int(Seed) & 0x7fffffff)
        for i in range(18):
            x = int(R.x) + rnd.nextInt(max(1, int(R.width)))
            a = 10 + rnd.nextInt(20)
            col = awt.Color(70, 50, 35, a)
            g2.setColor(col)
            g2.drawLine(x, int(R.y), x, int(R.y + R.height))
    except:
        pass


def FormatDestList(Dests):
    try:
        L = [str(d).strip().upper() for d in (Dests or []) if str(d).strip() != ""]
    except:
        L = []
    if not L:
        return ""
    if len(L) == 1:
        return L[0]
    if len(L) == 2:
        return L[0] + " & " + L[1]
    return ", ".join(L[:-1]) + " & " + L[-1]


def WrapWordsToLines(Text, MaxWidth, g2, FontObj, MaxLines):
    # Greedy wrap. If we reach the last line, keep adding words until width is exhausted.
    try:
        g2.setFont(FontObj)
        fm = g2.getFontMetrics(FontObj)
    except:
        return [str(Text or "")]

    try:
        words = [w for w in str(Text or "").split() if w != ""]
    except:
        words = []
    if not words:
        return [""]

    lines = []
    cur = ""
    wi = 0
    while wi < len(words):
        w = words[wi]
        cand = w if cur == "" else (cur + " " + w)
        try:
            fits = (fm.stringWidth(cand) <= int(MaxWidth))
        except:
            fits = True
        if fits:
            cur = cand
            wi += 1
            continue

        if cur != "":
            lines.append(cur)
        else:
            lines.append(w)
            wi += 1
        cur = ""

        if len(lines) >= int(MaxLines) - 1:
            while wi < len(words):
                w2 = words[wi]
                cand2 = w2 if cur == "" else (cur + " " + w2)
                try:
                    fits2 = (fm.stringWidth(cand2) <= int(MaxWidth))
                except:
                    fits2 = True
                if fits2:
                    cur = cand2
                    wi += 1
                else:
                    break
            break

    if len(lines) < int(MaxLines):
        if cur == "" and wi < len(words):
            while wi < len(words):
                w3 = words[wi]
                cand3 = w3 if cur == "" else (cur + " " + w3)
                try:
                    fits3 = (fm.stringWidth(cand3) <= int(MaxWidth))
                except:
                    fits3 = True
                if fits3:
                    cur = cand3
                    wi += 1
                else:
                    break
        lines.append(cur)

    return lines


def _TruncateToFit(g2, FontObj, Text, MaxWidth):
    try:
        g2.setFont(FontObj)
        fm = g2.getFontMetrics(FontObj)
        t = str(Text or "")
        if fm.stringWidth(t) <= int(MaxWidth):
            return t
        while len(t) > 1 and fm.stringWidth(t + "...") > int(MaxWidth):
            t = t[:-1]
        if len(t) > 1:
            return t + "..."
        return ""
    except:
        return str(Text or "")


def DrawWrappedCenteredText(g2, Rect, Text, Fam, BaseSize, MinSize, MaxLines):
    maxW = int(Rect.width) - 6
    if maxW < 8:
        maxW = int(Rect.width)
    sz = int(BaseSize)
    if sz < int(MinSize):
        sz = int(MinSize)

    bestLines = [str(Text or "")]
    bestFont = MakeFont(Fam, sz, True)

    while sz >= int(MinSize):
        f = MakeFont(Fam, sz, True)
        try:
            lines = WrapWordsToLines(Text, maxW, g2, f, int(MaxLines))
            fm = g2.getFontMetrics(f)
            ok = True
            for ln in lines:
                if fm.stringWidth(str(ln)) > maxW:
                    ok = False
                    break
            if ok:
                lineH = fm.getHeight()
                if (lineH * len(lines)) <= int(Rect.height) - 4:
                    bestLines = lines
                    bestFont = f
                    break
        except:
            bestLines = [str(Text or "")]
            bestFont = f
            break
        sz -= 1

    try:
        g2.setFont(bestFont)
        fm = g2.getFontMetrics(bestFont)
        outLines = list(bestLines)
        if outLines:
            outLines[-1] = _TruncateToFit(g2, bestFont, outLines[-1], maxW)
        lineH = fm.getHeight()
        yStart = int(Rect.y) + (int(Rect.height) - (lineH * len(outLines))) // 2 + fm.getAscent()
        for i, ln in enumerate(outLines):
            t = str(ln)
            tw = fm.stringWidth(t)
            tx = int(Rect.x + (int(Rect.width) - tw) // 2)
            ty = int(yStart + i * lineH)
            g2.drawString(t, tx, ty)
    except:
        pass


def DrawCellTextTwoLineOffset(g2, Rect, Text, Fam, BaseSize, MinSize, YOffset):
    # Stable (deterministic) fitting used for BOTH static and animated cell text.
    maxW = int(Rect.width) - 4
    if maxW < 8:
        maxW = int(Rect.width)
    sz = int(BaseSize)
    if sz < int(MinSize):
        sz = int(MinSize)

    bestLines = [str(Text or "")]
    bestFont = MakeFont(Fam, sz, False)

    while sz >= int(MinSize):
        f = MakeFont(Fam, sz, False)
        try:
            lines = WrapWordsToLines(Text, maxW, g2, f, 2)
            fm = g2.getFontMetrics(f)
            ok = True
            for ln in lines:
                if fm.stringWidth(str(ln)) > maxW:
                    ok = False
                    break
            if ok:
                lineH = fm.getHeight()
                if (lineH * len(lines)) <= int(Rect.height) - 2:
                    bestLines = lines
                    bestFont = f
                    break
        except:
            bestLines = [str(Text or "")]
            bestFont = f
            break
        sz -= 1
    oldClip = None
    try:
        oldClip = g2.getClip()
        # Preserve any existing clip by intersecting it with this cell rectangle.
        if oldClip is None:
            g2.setClip(int(Rect.x), int(Rect.y), int(Rect.width), int(Rect.height))
        else:
            try:
                b = oldClip.getBounds()
            except:
                b = oldClip
            try:
                rr = awt.Rectangle(int(Rect.x), int(Rect.y), int(Rect.width), int(Rect.height))
                bb = awt.Rectangle(int(b.x), int(b.y), int(b.width), int(b.height))
                ii = bb.intersection(rr)
                g2.setClip(int(ii.x), int(ii.y), int(ii.width), int(ii.height))
            except:
                g2.setClip(int(Rect.x), int(Rect.y), int(Rect.width), int(Rect.height))
    except:
        oldClip = None
    try:
        g2.setFont(bestFont)
        fm = g2.getFontMetrics(bestFont)
        outLines = list(bestLines)
        if outLines:
            outLines[-1] = _TruncateToFit(g2, bestFont, outLines[-1], maxW)
        lineH = fm.getHeight()
        yStart = int(Rect.y) + (int(Rect.height) - (lineH * len(outLines))) // 2 + fm.getAscent()
        yStart = int(yStart) + int(YOffset)
        for i, ln in enumerate(outLines):
            t = str(ln)
            ty = int(yStart + i * lineH)
            g2.drawString(t, int(Rect.x) + 2, ty)
    except:
        pass

    try:
        if oldClip is not None:
            g2.setClip(oldClip)
        else:
            g2.setClip(None)
    except:
        pass


def _DrawRecessApertureShading(g2, R):
    # Recess shading (aperture) to suggest a 3D hole.
    try:
        gpTop = awt.GradientPaint(float(R.x), float(R.y), awt.Color(0, 0, 0, 210), float(R.x), float(R.y + 7), awt.Color(0, 0, 0, 0))
        g2.setPaint(gpTop)
        g2.fillRect(int(R.x), int(R.y), int(R.width), min(7, int(R.height)))
        gpBot = awt.GradientPaint(float(R.x), float(R.y + R.height - 7), awt.Color(0, 0, 0, 0), float(R.x), float(R.y + R.height), awt.Color(0, 0, 0, 210))
        g2.setPaint(gpBot)
        g2.fillRect(int(R.x), int(R.y + max(0, int(R.height) - 7)), int(R.width), min(7, int(R.height)))
    except:
        pass


def _DrawRidgeLine(g2, x1, x2, y):
    # A bright/dark double line to suggest the cuboid edge.
    try:
        g2.setColor(awt.Color(255,255,255, 40))
        g2.drawLine(int(x1), int(y), int(x2), int(y))
        g2.setColor(awt.Color(0, 0, 0, 200))
        g2.drawLine(int(x1), int(y + 1), int(x2), int(y + 1))
    except:
        pass


def DrawRollerAnimated(g2, R, CurText, NextText, OffsetPx, FontObj, TextColor, WoodSeed):
    # Clip-safe roller window with vertical rolling animation.
    oldClip = None
    try:
        oldClip = g2.getClip()
        g2.setClip(int(R.x), int(R.y), int(R.width), int(R.height))
    except:
        oldClip = None

    try:
        if str(CurText or "") == "" and int(OffsetPx) == 0:
            DrawWood(g2, R, WoodSeed)
        else:
            g2.setColor(awt.Color(0, 0, 0))
            g2.fillRect(int(R.x), int(R.y), int(R.width), int(R.height))

        g2.setColor(awt.Color(0, 0, 0))
        g2.drawRect(int(R.x), int(R.y), int(R.width), int(R.height))

        _DrawRecessApertureShading(g2, R)

        g2.setFont(FontObj)
        fm = g2.getFontMetrics(FontObj)
        g2.setColor(TextColor)

        off = int(OffsetPx)
        h = int(R.height)

        if off <= 0:
            t = str(CurText or "")
            if t != "":
                tx = int(R.x + (R.width - fm.stringWidth(t)) // 2)
                ty = int(R.y + (h + fm.getAscent()) // 2 - 2)
                g2.drawString(t, tx, ty)
            return

        ridgeY = int(R.y + (h - off))
        _DrawRidgeLine(g2, int(R.x) + 1, int(R.x + R.width) - 2, ridgeY)
        g2.setColor(TextColor)

        # Rolling shading: slightly dim the outgoing face near the top, incoming face near the bottom.
        try:
            fadeTop = awt.GradientPaint(float(R.x), float(R.y), awt.Color(0, 0, 0, 70), float(R.x), float(R.y + h / 2), awt.Color(0, 0, 0, 0))
            g2.setPaint(fadeTop)
            g2.fillRect(int(R.x), int(R.y), int(R.width), int(h / 2))
            fadeBot = awt.GradientPaint(float(R.x), float(R.y + h / 2), awt.Color(0, 0, 0, 0), float(R.x), float(R.y + h), awt.Color(0, 0, 0, 70))
            g2.setPaint(fadeBot)
            g2.fillRect(int(R.x), int(R.y + h / 2), int(R.width), int(h - h / 2))
            g2.setColor(TextColor)
        except:
            pass

        t1 = str(CurText or "")
        t2 = str(NextText or "")

        if t1 != "":
            tx1 = int(R.x + (R.width - fm.stringWidth(t1)) // 2)
            ty1 = int(R.y + (h + fm.getAscent()) // 2 - 2 - off)
            g2.drawString(t1, tx1, ty1)

        if t2 != "":
            tx2 = int(R.x + (R.width - fm.stringWidth(t2)) // 2)
            ty2 = int(R.y + (h + fm.getAscent()) // 2 - 2 + (h - off))
            g2.drawString(t2, tx2, ty2)

    finally:
        try:
            if oldClip is not None:
                g2.setClip(oldClip)
            else:
                g2.setClip(None)
        except:
            pass


# -------------------------------
# UI Panel
# -------------------------------

class RotaryLargePanel(swing.JPanel):
    def __init__(self, Controller):
        swing.JPanel.__init__(self)
        self.Controller = Controller
        self.setLayout(None)
        self.setOpaque(True)
        self.setBackground(awt.Color(20, 16, 12))

    def paintComponent(self, g):
        if self.isOpaque():
            try:
                g.setColor(self.getBackground())
                g.fillRect(0, 0, self.getWidth(), self.getHeight())
            except:
                pass

        g2 = g.create()
        try:
            g2.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g2.setRenderingHint(awt.RenderingHints.KEY_FRACTIONALMETRICS, awt.RenderingHints.VALUE_FRACTIONALMETRICS_ON)
        except:
            pass

        Ctrl = self.Controller
        if Ctrl is None:
            g2.dispose()
            return

        State = Ctrl.GetRenderState()
        if not State:
            g2.dispose()
            return

        OuterPad = int(State.get('OuterPad', 16))
        ColW = int(State.get('ColW', 90))
        # Use ROLLER_GAP from constants
        ColGap = int(ROLLER_GAP) 
        GroupH = int(State.get('GroupH', 44))
        HeaderH = int(State.get('HeaderH', 92))
        CellH = int(State.get('CellH', 22))
        Rows = int(State.get('Rows', 15))
        SpecialH = int(State.get('SpecialH', 26))

        Groups = State.get('Groups') or []
        Cols = State.get('Columns') or []
        ColAnim = State.get('ColAnim') or {}
        GroupRowFaces = State.get('GroupRowFaces') or {}
        DisplayNameMap = State.get('DisplayNameMap') or {}
        PlatformSeq = State.get('PlatformSeq') or [""]
        TimeSeqs = State.get('TimeSeqs') or TimeRollerSequences(USE_12_HOUR_TIME)

        y0 = OuterPad
        x0 = OuterPad

        # Group headers
        for gi, G in enumerate(Groups):
            startCol = int(G.get('StartCol', 0))
            nCols = int(G.get('Cols', 0))
            if nCols <= 0:
                continue
            gx = x0 + startCol * (ColW + ColGap)
            gw = nCols * ColW + (nCols - 1) * ColGap
            Rg = awt.Rectangle(gx, y0, gw, GroupH)
            g2.setColor(awt.Color(245, 245, 245))
            g2.fillRect(Rg.x, Rg.y, Rg.width, Rg.height)
            g2.setColor(awt.Color(0, 0, 0))
            g2.drawRect(Rg.x, Rg.y, Rg.width, Rg.height)

            dests = G.get('Dests') or []
            title = FormatDestList(dests) + " SERVICES"
            try:
                fam = HEADER_FONT_FAMILY if HEADER_FONT_FAMILY != "" else 'SansSerif'
                g2.setColor(awt.Color(0, 0, 0))
                DrawWrappedCenteredText(g2, Rg, title, fam, 14, 5, 2)
            except:
                pass

        baseY = y0 + GroupH + 6

        timeFont = MakeFont(FONT_FAM_NARROW, 16, False)
        platFont = MakeFont(FONT_FAM_NARROW, 14, False)

        for ci, C in enumerate(Cols):
            cx = x0 + ci * (ColW + ColGap)
            colH = HeaderH + (Rows * CellH) + SpecialH
            Rc = awt.Rectangle(cx, baseY, ColW, colH)
            DrawWood(g2, Rc, 1000 + ci)
            g2.setColor(awt.Color(10, 10, 10))
            g2.drawRect(Rc.x, Rc.y, Rc.width, Rc.height)

            Rh = awt.Rectangle(cx, baseY, ColW, HeaderH)
            DrawWood(g2, Rh, 2000 + ci)
            g2.setColor(awt.Color(0, 0, 0))
            g2.drawRect(Rh.x, Rh.y, Rh.width, Rh.height)

            anim = ColAnim.get(ci) or {}            # Time rollers (narrow and centered)
            hIdx = int(anim.get('TimeHIdx', 0))
            mIdx = int(anim.get('TimeMIdx', 0))
            apIdx = int(anim.get('TimeApIdx', 0))

            try:
                hourTxt = str(TimeSeqs['H'][hIdx % len(TimeSeqs['H'])])
                nextHour = str(TimeSeqs['H'][(hIdx + 1) % len(TimeSeqs['H'])])
            except:
                hourTxt = ""
                nextHour = ""
            try:
                minTxt = str(TimeSeqs['M'][mIdx % len(TimeSeqs['M'])])
                nextMin = str(TimeSeqs['M'][(mIdx + 1) % len(TimeSeqs['M'])])
            except:
                minTxt = ""
                nextMin = ""

            apTxt = ""
            nextAp = ""
            apSeq = TimeSeqs.get('AP')
            if apSeq is not None:
                try:
                    apTxt = str(apSeq[apIdx % len(apSeq)])
                    nextAp = str(apSeq[(apIdx + 1) % len(apSeq)])
                except:
                    apTxt = ""
                    nextAp = ""
            rollerH = 20
            rollerY = baseY + 10
            # Use ROLLER_GAP (4)
            # Narrower digit windows with larger gaps between them.
            rollerGap = 6
            hourW = 22
            minW = 26
            apW = 0
            if apSeq is not None:
                # 12-hour mode: three rollers must fit within the column.
                rollerGap = 6
                hourW = 22
                minW = 26
                apW = 22
            totW = hourW + rollerGap + minW
            if apSeq is not None:
                totW = totW + rollerGap + apW
            startX = cx + (ColW - totW) // 2

            RHour = awt.Rectangle(startX, rollerY, hourW, rollerH)
            RMin = awt.Rectangle(startX + hourW + rollerGap, rollerY, minW, rollerH)

            hOff = int(anim.get('TimeHOffset', 0))
            mOff = int(anim.get('TimeMOffset', 0))
            apOff = int(anim.get('TimeApOffset', 0))

            DrawRollerAnimated(g2, RHour, hourTxt, nextHour, hOff, timeFont, awt.Color(255, 255, 255), 4000 + ci)
            DrawRollerAnimated(g2, RMin, minTxt, nextMin, mOff, timeFont, awt.Color(255, 255, 255), 5000 + ci)
            if apSeq is not None:
                RAp = awt.Rectangle(startX + hourW + rollerGap + minW + rollerGap, rollerY, apW, rollerH)
                DrawRollerAnimated(g2, RAp, apTxt, nextAp, apOff, timeFont, awt.Color(255, 255, 255), 4500 + ci)

            # PLATFORM label
            RpLab = awt.Rectangle(cx + 6, baseY + 40, ColW - 12, 16)
            try:
                lab = "PLATFORM"
                fl = MakeFont(FONT_FAM_SERIF, 12, True)
                g2.setFont(fl)
                g2.setColor(awt.Color(220, 190, 90))
                fm = g2.getFontMetrics(fl)
                tx = int(RpLab.x + (RpLab.width - fm.stringWidth(lab)) // 2)
                ty = int(RpLab.y + (RpLab.height + fm.getAscent()) // 2 - 2)
                g2.drawString(lab, tx, ty)
            except:
                pass

            # Platform roller
            pIdx = int(anim.get('PlatIdx', 0))
            try:
                platTxt = str(PlatformSeq[pIdx % len(PlatformSeq)])
                nextPlat = str(PlatformSeq[(pIdx + 1) % len(PlatformSeq)])
            except:
                platTxt = ""
                nextPlat = ""

            pOff = int(anim.get('PlatOffset', 0))

            RPlat = awt.Rectangle(cx + 32, baseY + 60, ColW - 44, 22)
            DrawRollerAnimated(g2, RPlat, platTxt, nextPlat, pOff, platFont, awt.Color(255, 255, 255), 6000 + ci)

            # "No" label with underline under the o
            NoX = cx + 10
            NoY = baseY + 60
            NoH = 22
            NoW = 18
            RNo = awt.Rectangle(NoX, NoY, NoW, NoH)

            try:
                fl = MakeFont(FONT_FAM_SERIF, 12, True)
                fso = MakeFont(FONT_FAM_SERIF, 9, True)
                g2.setColor(awt.Color(220, 190, 90))

                g2.setFont(fl)
                fm = g2.getFontMetrics(fl)
                nTxt = "N"
                nX = RNo.x
                nY = RNo.y + (RNo.height + fm.getAscent()) // 2 - 2
                g2.drawString(nTxt, nX, nY)

                g2.setFont(fso)
                fm2 = g2.getFontMetrics(fso)
                oTxt = "o"
                oX = nX + fm.stringWidth(nTxt) - 1
                oY = nY - (fm2.getAscent() // 2)
                g2.drawString(oTxt, oX, oY)

                # underline under the 'o'
                ow = fm2.stringWidth(oTxt)
                ulY = oY + 2
                g2.drawLine(oX, ulY, oX + ow, ulY)

            except:
                pass

            status = str(anim.get('Status', '') or '').strip().upper()
            special = str(anim.get('Special', '') or '').strip()

            # Calling rows
            cellsY = baseY + HeaderH
            gi = None
            try:
                gi = int(C.get('GroupIndex'))
            except:
                gi = None
            rowFaces = GroupRowFaces.get(gi) or []
            faceIdxs = anim.get('RowFaceIdxs') or [0] * int(Rows)
            rowAnimRow = int(anim.get('RowAnimRow', -1))
            rowAnimOff = int(anim.get('RowAnimOffset', 0))

            for r in range(int(Rows)):
                ry = cellsY + r * CellH
                Rcell = awt.Rectangle(cx + 6, ry, ColW - 12, CellH - 2)

                idx = 0
                try:
                    idx = int(faceIdxs[r])
                except:
                    idx = 0

                curKey = ""
                nextKey = ""
                mod = 1
                if r < len(rowFaces):
                    try:
                        mod = max(1, len(rowFaces[r]))
                        curKey = str(rowFaces[r][idx % mod] or "")
                        nextKey = str(rowFaces[r][(idx + 1) % mod] or "")
                    except:
                        mod = 1
                        curKey = ""
                        nextKey = ""

                if status == "CANCELLED" and r == 0:
                    curKey = "CANCELLED"
                    nextKey = "CANCELLED"

                off = 0
                if r == rowAnimRow:
                    off = rowAnimOff

                defName = DisplayNameMap.get(curKey, curKey)
                nextName = DisplayNameMap.get(nextKey, nextKey)
                txtU = str(defName).upper()
                nextU = str(nextName).upper()

                # background
                if (curKey == "" and off == 0):
                    DrawWood(g2, Rcell, 7000 + (ci * 100) + r)
                else:
                    g2.setColor(awt.Color(0, 0, 0))
                    g2.fillRect(Rcell.x, Rcell.y, Rcell.width, Rcell.height)
                g2.setColor(awt.Color(10, 10, 10))
                g2.drawRect(Rcell.x, Rcell.y, Rcell.width, Rcell.height)

                # recessed shading
                _DrawRecessApertureShading(g2, Rcell)

                if off == 0:
                    if curKey != "":
                        g2.setColor(awt.Color(255, 255, 255))
                        DrawCellTextTwoLineOffset(g2, Rcell, txtU, FONT_FAM_NARROW, 12, 8, 0)
                else:
                    # ridge between faces
                    h = int(Rcell.height)
                    ridgeY = int(Rcell.y + (h - off))
                    _DrawRidgeLine(g2, int(Rcell.x) + 1, int(Rcell.x + Rcell.width) - 2, ridgeY)
                    g2.setColor(awt.Color(255, 255, 255))

                    if curKey != "":
                        DrawCellTextTwoLineOffset(g2, Rcell, txtU, FONT_FAM_NARROW, 12, 8, 0 - int(off))
                    if nextKey != "":
                        DrawCellTextTwoLineOffset(g2, Rcell, nextU, FONT_FAM_NARROW, 12, 8, int(h - off))            # Special line
            Rs = awt.Rectangle(cx + 6, cellsY + int(Rows) * CellH + 4, ColW - 12, SpecialH)
            # Frame always visible
            DrawWood(g2, Rs, 3000 + ci)
            g2.setColor(awt.Color(0, 0, 0))
            g2.drawRect(Rs.x, Rs.y, Rs.width, Rs.height)

            pad = 3
            Rhole = awt.Rectangle(Rs.x + pad, Rs.y + pad, Rs.width - 2*pad, Rs.height - 2*pad)
            
            sOff = int(anim.get('SpecialOffset', 0))
            
            # Draw Hole Background (Wood/Recess)
            # Only draw if hole is visible (i.e., plate not fully covering it)
            # If special and sOff >= SpecialH, hole is covered.
            if not special or sOff < int(SpecialH):
                 DrawWood(g2, Rhole, 4000 + ci) # Wood background
                 _DrawRecessApertureShading(g2, Rhole) # Shading

            # Draw Plate
            if special:
                oldClip2 = None
                try:
                    oldClip2 = g2.getClip()
                    # Clip to the frame interior Rs
                    g2.setClip(Rs.x, Rs.y, Rs.width, Rs.height)

                    plateRect = awt.Rectangle(Rs.x + pad, Rs.y + pad + sOff, Rs.width - 2*pad, Rs.height - 2*pad)
                    
                    # Black background
                    g2.setColor(awt.Color(0, 0, 0))
                    g2.fillRect(plateRect.x, plateRect.y, plateRect.width, plateRect.height)
                                  
                    # Text must be drawn in a contrasting colour (otherwise it is black-on-black).
                    g2.setColor(awt.Color(255, 255, 255))
                 
                    # Text on plate
                    stxt = str(special).upper()
                    DrawCellTextTwoLineOffset(g2, plateRect, stxt, FONT_FAM_NARROW, 11, 7, 0)
                    
                except Exception as ExInner:
                    # Ignore rendering errors for special plate
                    pass
                finally:
                    try:
                        if oldClip2 is not None:
                            g2.setClip(oldClip2)
                        else:
                            g2.setClip(None)
                    except:
                        pass

        g2.dispose()


# -------------------------------
# Controller / animation engine
# -------------------------------

class RotaryLargeWindow(object):
    def __init__(self):
        self.Frame = None
        self.Panel = None
        self._pcl = None
        self._probeTimer = None
        self._refreshTimer = None
        self._pollTimer = None

        try:
            from java.util.concurrent.locks import ReentrantLock
            self._lock = ReentrantLock()
        except:
            self._lock = None

        self._lastNowMinutes = None


        self._LastRowIncreaseNote = None
        self._LastColWarn = None
        self.GroupsPlan = []
        self.Columns = []
        self.GroupIndexByDest = {}

        self.DisplayNameMap = {}
        self.GroupRowFaces = {}
        self.GroupStationToRow = {}
        self.GroupStationToFace = {}

        self.PlatformSeq = [""]
        self.TimeSeqs = TimeRollerSequences(USE_12_HOUR_TIME)

        self.SvcByRn = {}
        self.DesiredByCol = {}
        self.DisplayByCol = {}
        self.ColAnim = {}

        self.RenderGeom = {
            'OuterPad': 16,
            'ColW': 90,
            'ColGap': int(ROLLER_GAP),
            'GroupH': 44,
            'HeaderH': 92,
            'CellH': 22,
            'Rows': int(PREF_ROWS),
            'SpecialH': 26,
        }

        self.DayMem = DayMem
        self.TimeMem = TimeMem
        self.TTMem = TTMem

        self._BuildUiOnEdt()
        self._InstallListeners()

    def _BuildUiOnEdt(self):
        def _Run():
            self.Frame = swing.JFrame("Departures")
            self.Frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
            try:
                from TASIcon import SetFrameClockIcon
                SetFrameClockIcon(self.Frame, 32)
            except:
                pass

            cp = self.Frame.getContentPane()
            cp.setLayout(None)
            self.Panel = RotaryLargePanel(self)
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
            self.Frame.setVisible(True)

            self._ScheduleProbe()

            # Poll refresh
            try:
                if self._pollTimer is None:
                    def _Poll(ev=None):
                        try:
                            self._ScheduleRefresh()
                        except:
                            pass
                    self._pollTimer = swing.Timer(int(POLL_REFRESH_MS), _Poll)
                    self._pollTimer.setRepeats(True)
                    self._pollTimer.start()
            except:
                pass

        try:
            swing.SwingUtilities.invokeLater(_Run)
        except:
            _Run()

    def _InstallListeners(self):
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb):
                innerSelf.Cb = cb
            def propertyChange(innerSelf, e):
                try:
                    innerSelf.Cb(e)
                except Exception as Ex:
                    try:
                        print("[PIDRotaryLarge] listener error: " + str(Ex))
                    except:
                        pass

        self._pcl = PCL(self.Refresh)
        try:
            if self.TimeMem is not None:
                self.TimeMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if self.DayMem is not None:
                self.DayMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if self.TTMem is not None:
                self.TTMem.addPropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if PAR is not None:
                PAR.addPlatformListener(self._pcl)
        except:
            pass

    def _ScheduleProbe(self):
        try:
            if self._probeTimer is not None:
                self._probeTimer.stop()
        except:
            pass
        self._probeTimer = None

        def _Do(ev=None):
            try:
                if self._probeTimer is not None:
                    self._probeTimer.stop()
            except:
                pass
            self._probeTimer = None
            self._RefreshInBackground()

        try:
            self._probeTimer = swing.Timer(600, _Do)
            self._probeTimer.setRepeats(False)
            self._probeTimer.start()
        except:
            self._RefreshInBackground()

    def _ScheduleRefresh(self):
        try:
            if self._refreshTimer is not None and self._refreshTimer.isRunning():
                return
        except:
            pass

        def _Do(ev=None):
            try:
                if self._refreshTimer is not None:
                    self._refreshTimer.stop()
            except:
                pass
            self._refreshTimer = None
            self._RefreshInBackground()

        try:
            self._refreshTimer = swing.Timer(200, _Do)
            self._refreshTimer.setRepeats(False)
            self._refreshTimer.start()
        except:
            self._RefreshInBackground()

    def Refresh(self, e):
        self._ScheduleRefresh()

    def _LayoutFrameForCols(self, TotalCols, Rows):
        geom = self.RenderGeom
        op = int(geom['OuterPad'])
        cw = int(geom['ColW'])
        cg = int(geom['ColGap'])
        gh = int(geom['GroupH'])
        hh = int(geom['HeaderH'])
        ch = int(geom['CellH'])
        sh = int(geom['SpecialH'])
        w = op * 2 + (int(TotalCols) * cw) + ((int(TotalCols) - 1) * cg)
        h = op * 2 + gh + 6 + hh + (int(Rows) * ch) + sh + 20

        def _Apply():
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

        try:
            swing.SwingUtilities.invokeLater(_Apply)
        except:
            _Apply()

    def _EnsureColAnimState(self, col, rows):
        a = self.ColAnim.get(col)
        if a is None:
            a = {}
            self.ColAnim[col] = a
        if 'Version' not in a:
            a['Version'] = 0
        if 'Phase' not in a:
            a['Phase'] = 'IDLE'
        rf = list(a.get('RowFaceIdxs') or [])
        if len(rf) < int(rows):
            rf.extend([0] * (int(rows) - len(rf)))
        if len(rf) > int(rows):
            rf = rf[:int(rows)]
        a['RowFaceIdxs'] = rf
        if 'TimeHIdx' not in a:
            a['TimeHIdx'] = 0
        if 'TimeMIdx' not in a:
            a['TimeMIdx'] = 0
        if 'TimeApIdx' not in a:
            a['TimeApIdx'] = 0
        if 'PlatIdx' not in a:
            a['PlatIdx'] = 0
        if 'Status' not in a:
            a['Status'] = ''
        if 'Special' not in a:
            a['Special'] = ''
        if 'SpecialOffset' not in a:
            a['SpecialOffset'] = 0
        if 'SpecialTargetOffset' not in a:
            a['SpecialTargetOffset'] = 0
        if 'SvcKey' not in a:
            a['SvcKey'] = None
        if 'TimeHOffset' not in a:
            a['TimeHOffset'] = 0
        if 'TimeMOffset' not in a:
            a['TimeMOffset'] = 0
        if 'TimeApOffset' not in a:
            a['TimeApOffset'] = 0
        if 'PlatOffset' not in a:
            a['PlatOffset'] = 0
        if 'RowAnimRow' not in a:
            a['RowAnimRow'] = -1
        if 'RowAnimOffset' not in a:
            a['RowAnimOffset'] = 0
        return a

    def _BumpVersion(self, col):
        a = self.ColAnim.get(col)
        if a is None:
            a = {}
            self.ColAnim[col] = a
        try:
            a['Version'] = int(a.get('Version', 0)) + 1
        except:
            a['Version'] = 1
        return int(a['Version'])

    def _RefreshInBackground(self):
        try:
            from java.lang import Thread
        except:
            Thread = None

        # Snapshot mutable state used for planning so the worker thread never touches self.* directly.
        try:
            LastNowSnapshot = self._lastNowMinutes
        except:
            LastNowSnapshot = None
        try:
            DisplayByColSnapshot = dict(self.DisplayByCol or {})
        except:
            DisplayByColSnapshot = {}

        def _Work():
            rowsAll = CsvRows()
            capStations = max(3, int(PREF_ROWS) * 3)
            minGroups = ComputeHardMinimumGroups(rowsAll, PREF_ROWS)
            minCols = max(int(PREF_COLS), int(minGroups))
            # Heuristic: fewer, broader groups (reduces over-fragmentation for shared-route destinations).
            try:
                freqAll, _stationSetAll, _dn = _DestProfilesWeek(rowsAll)
                nDests = int(len(freqAll.keys()))
            except:
                nDests = 0
            try:
                desiredGroups = int(round(float(minCols) / 5.0))
            except:
                desiredGroups = 2
            if nDests > 0 and desiredGroups > nDests:
                desiredGroups = nDests
            if nDests >= 3 and desiredGroups < 3:
                desiredGroups = 3
            if desiredGroups < 1:
                desiredGroups = 1
            if desiredGroups < minGroups:
                desiredGroups = minGroups
            groupsRaw = BuildDestinationGroupsWithCap(rowsAll, desiredGroups, capStations, PREF_ROWS)
            # First pass plan to get stable group indices for destinations.
            planSeed = AllocateColumnsToGroups(groupsRaw, max(1, len(groupsRaw or [])))
            giByDest = BuildGroupIndexByDest(planSeed)
            # Compute required columns per group based on the look-ahead window over the whole week.
            minColsByGroup = ComputeMinColumnsByGroup(rowsAll, giByDest, FUTURE_WINDOW_MIN)
            hardMinCols = 0
            for gi in range(len(planSeed or [])):
                try:
                    hardMinCols += int(max(0, int(minColsByGroup.get(int(gi), 0))))
                except:
                    pass
            if hardMinCols < 1:
                hardMinCols = 1
            # Preferred columns is a minimum; the timetable may require more.
            try:
                prefMax = int(PREF_COLS)
            except:
                prefMax = 15
            if prefMax < 1:
                prefMax = 1
            totalCols = int(hardMinCols)
            ColWarnKey = None
            if int(hardMinCols) > int(prefMax):
                try:
                    ColWarnKey = (int(hardMinCols), int(prefMax))
                except:
                    ColWarnKey = ('?', '?')
            # Allocate at least the required columns to each group, then distribute any extra (if ever used).
            plan = []
            for gi, g in enumerate(groupsRaw or []):
                try:
                    need = int(minColsByGroup.get(int(gi), 0))
                except:
                    need = 0
                if need < 0:
                    need = 0
                if need == 0:
                    need = 1
                ng = {'Dests': list(g.get('Dests') or []), 'Freq': int(g.get('Freq', 0)), 'Cols': int(need)}
                ng['StationSet'] = set(g.get('StationSet', set()))
                plan.append(ng)
            # Rebuild destination->group index mapping after final plan.
            # Preferred columns is a minimum; increase columns to at least this value.
            try:
                _prefColsMin = int(PREF_COLS)
            except:
                _prefColsMin = 15
            if _prefColsMin < 1:
                _prefColsMin = 1
            try:
                _have = 0
                for _g in plan:
                    _have += int(_g.get('Cols', 0))
                if _have < int(_prefColsMin) and len(plan) > 0:
                    _extra = int(_prefColsMin) - int(_have)
                    _sumFreq = 0
                    for _g in plan:
                        try:
                            _sumFreq += int(_g.get('Freq', 0))
                        except:
                            pass
                    if _sumFreq <= 0:
                        _sumFreq = len(plan)
                    _bases = [0] * len(plan)
                    _rems = []
                    _used = 0
                    for _i in range(len(plan)):
                        try:
                            _f = int(plan[_i].get('Freq', 0))
                        except:
                            _f = 0
                        if _f < 0:
                            _f = 0
                        try:
                            _exact = (float(_f) * float(_extra)) / float(_sumFreq)
                        except:
                            _exact = 0.0
                        _b = int(_exact)
                        if _b < 0:
                            _b = 0
                        _bases[_i] = _b
                        _used += _b
                        _r = float(_exact) - float(_b)
                        try:
                            _k = str(_GroupKeyText(plan[_i].get('Dests') or [])).upper()
                        except:
                            _k = ""
                        _rems.append((_r, _f, _k, _i))
                    _left = int(_extra) - int(_used)
                    if _left > 0:
                        _rems.sort(key=lambda t: (0.0 - float(t[0]), 0 - int(t[1]), str(t[2]), int(t[3])))
                        _p = 0
                        while _left > 0 and len(_rems) > 0:
                            _i = int(_rems[_p % len(_rems)][3])
                            _bases[_i] = int(_bases[_i]) + 1
                            _left -= 1
                            _p += 1
                    for _i in range(len(plan)):
                        try:
                            plan[_i]['Cols'] = int(plan[_i].get('Cols', 0)) + int(_bases[_i])
                        except:
                            pass
            except:
                pass
            giByDest = BuildGroupIndexByDest(plan)
            platformSeq = BuildPlatformRollerSequence(rowsAll)
            timeSeqs = TimeRollerSequences(USE_12_HOUR_TIME)

            _, _, displayNameMap = _DestProfilesWeek(rowsAll)
            groupRowFaces = {}
            groupStationToRow = {}
            groupStationToFace = {}

            maxRowsNeeded = int(PREF_ROWS)

            for gi, g in enumerate(plan):
                stToRow, rowFaces, stToFace, cycle, used = SolveGroupRowsForRollerDecks(rowsAll, g.get('Dests') or [], PREF_ROWS)
                try:
                    if int(used) > int(maxRowsNeeded):
                        maxRowsNeeded = int(used)
                except:
                    pass
                groupRowFaces[int(gi)] = list(rowFaces)
                groupStationToRow[int(gi)] = dict(stToRow)
                groupStationToFace[int(gi)] = dict(stToFace)

            renderGroups = StripDiagnosticStationSet(plan)
            cols = []
            start = 0
            for gi, g in enumerate(renderGroups):
                n = int(g.get('Cols', 0))
                g['StartCol'] = int(start)
                for k in range(n):
                    cols.append({'GroupIndex': int(gi), 'Index': int(start + k)})
                start += n

            totalCols = len(cols)

            services = NextServicesTodayAll()
            svcByRn = {}
            for s in (services or []):
                rn = str(getattr(s, 'RN', '') or '').strip()
                if rn:
                    svcByRn[rn] = s

            # Basic time-warp reset
            nowMin = CurrentMinutes()
            warpDetected = False
            try:
                lastNow = LastNowSnapshot
            except:
                lastNow = None
            try:
                threshold = int(TIMEWARP_THRESHOLD_MIN)
            except:
                threshold = 2
            if lastNow is not None and nowMin is not None:
                try:
                    a = int(nowMin) % 1440
                    b = int(lastNow) % 1440
                    raw = abs(a - b)
                    delta = min(raw, 1440 - raw)
                    warpDetected = (delta != 0) if threshold == 0 else (delta >= threshold)
                except:
                    warpDetected = True
            LastNowComputed = nowMin

            desiredByCol = {}
            usedRn = set()
            try:
                curDisplay = {} if warpDetected else dict(DisplayByColSnapshot or {})
            except:
                curDisplay = {}

            for ci in range(totalCols):
                desiredByCol[ci] = curDisplay.get(ci)

            for ci in range(totalCols):
                rn = desiredByCol.get(ci)
                if rn and str(rn) not in svcByRn:
                    desiredByCol[ci] = None
                if desiredByCol.get(ci):
                    usedRn.add(str(desiredByCol.get(ci)))

            queues = {}
            for s in (services or []):
                dest = str(getattr(s, 'Dest', '') or '').strip().lower()
                if dest == '':
                    continue
                gi = giByDest.get(dest)
                if gi is None:
                    continue
                rn = str(getattr(s, 'RN', '') or '').strip()
                if rn == '' or rn in usedRn:
                    continue
                queues.setdefault(int(gi), []).append(rn)

            for ci in range(totalCols):
                if desiredByCol.get(ci) is not None:
                    continue
                gi = None
                try:
                    gi = int(cols[ci].get('GroupIndex'))
                except:
                    gi = None
                if gi is None:
                    continue
                q = queues.get(gi) or []
                if not q:
                    continue
                pick = q.pop(0)
                desiredByCol[ci] = pick
                usedRn.add(pick)
                queues[gi] = q

            def _ApplyPlanAndAnimate():
                try:
                    self._lastNowMinutes = LastNowComputed
                except:
                    try:
                        self._lastNowMinutes = nowMin
                    except:
                        pass


                # Only log this once per required column-count to avoid console spam.
                try:
                    if ColWarnKey is not None:
                        if getattr(self, '_LastColWarn', None) != ColWarnKey:
                            try:
                                print('[PIDRotaryLarge] WARN: timetable requires ' + str(ColWarnKey[0]) + ' columns; exceeds preferred ' + str(ColWarnKey[1]))
                            except:
                                pass
                            self._LastColWarn = ColWarnKey
                    else:
                        self._LastColWarn = None
                except:
                    pass

                self.GroupsPlan = list(renderGroups)
                self.Columns = list(cols)
                self.GroupIndexByDest = dict(giByDest)

                self.PlatformSeq = list(platformSeq)
                self.TimeSeqs = dict(timeSeqs)

                self.DisplayNameMap = dict(displayNameMap)
                self.GroupRowFaces = dict(groupRowFaces)
                self.GroupStationToRow = dict(groupStationToRow)
                self.GroupStationToFace = dict(groupStationToFace)

                self.SvcByRn = dict(svcByRn)
                effRows = int(maxRowsNeeded)
                if effRows < int(PREF_ROWS):
                    effRows = int(PREF_ROWS)
                if effRows != int(PREF_ROWS):
                    # Only log this once per effective row-count to avoid console spam.
                    try:
                        if getattr(self, '_LastRowIncreaseNote', None) != int(effRows):
                            print('[PIDRotaryLarge] NOTE: increasing rows from preferred ' + str(PREF_ROWS) + ' to ' + str(effRows))
                            self._LastRowIncreaseNote = int(effRows)
                    except:
                        pass
                else:
                    try:
                        self._LastRowIncreaseNote = None
                    except:
                        pass
                self.RenderGeom['Rows'] = int(effRows)
                for ci in range(totalCols):
                    if ci not in self.DisplayByCol:
                        self.DisplayByCol[ci] = None
                    if ci not in self.DesiredByCol:
                        self.DesiredByCol[ci] = None
                    self._EnsureColAnimState(ci, effRows)

                for ci in range(totalCols):
                    self.DesiredByCol[ci] = desiredByCol.get(ci)

                for ci in range(totalCols):
                    cur = self.DisplayByCol.get(ci)
                    des = self.DesiredByCol.get(ci)
                    a = self.ColAnim.get(ci) or {}

                    if str(cur) == str(des):
                        # Live updates (time/platform/status)
                        if cur is not None and str(a.get('Phase', 'IDLE')) == 'IDLE':
                            svc = self.SvcByRn.get(str(cur))
                            if svc is not None:
                                try:
                                    hh, mm, ap = MinutesToDisplayParts(int(getattr(svc, 'AdjMin', 0)), USE_12_HOUR_TIME)
                                except:
                                    hh, mm, ap = ('', '', '')
                                tgtPlat = str(getattr(svc, 'Plat', '') or '').strip()
                                tgtStatus = str(getattr(svc, 'Status', '') or '').strip().upper()
                                try:
                                    key = str(hh) + '|' + str(mm) + '|' + str(tgtPlat) + '|' + str(tgtStatus)
                                except:
                                    key = None
                                if key is not None and key != a.get('SvcKey'):
                                    ver = self._BumpVersion(ci)
                                    a['Phase'] = 'SET'
                                    a['NextRn'] = cur
                                    a['TargetTimeH'] = str(hh)
                                    a['TargetTimeM'] = str(mm)
                                    a['TargetPlat'] = str(tgtPlat)
                                    a['TargetStatus'] = str(tgtStatus)
                                    a['Status'] = str(tgtStatus)
                                    a['SvcKey'] = key
                                    self._AnimateToTargets(ci, ver)
                        continue

                    if str(a.get('Phase', 'IDLE')) != 'IDLE':
                        continue
                    self._StartColumnTransition(ci, des)

                self._LayoutFrameForCols(totalCols, effRows)
                try:
                    self.Panel.repaint()
                except:
                    pass

            try:
                swing.SwingUtilities.invokeLater(_ApplyPlanAndAnimate)
            except:
                _ApplyPlanAndAnimate()

        if Thread is None:
            _Work()
        else:
            try:
                Thread(_Work).start()
            except:
                _Work()

    def _StartColumnTransition(self, col, newRn):
        rows = int(self.RenderGeom.get('Rows', PREF_ROWS))
        a = self._EnsureColAnimState(col, rows)
        ver = self._BumpVersion(col)

        a['Phase'] = 'CLEAR'
        a['NextRn'] = newRn
        a['TargetRowFaces'] = [0] * rows
        a['TargetTimeH'] = ''
        a['TargetTimeM'] = ''
        a['TargetTimeAp'] = ''
        a['TargetPlat'] = ''
        a['TargetStatus'] = ''
        a['TargetSpecial'] = ''
        a['Status'] = ''
        a['Special'] = ''
        a['SpecialOffset'] = 0
        a['SpecialTargetOffset'] = 0
        a['SvcKey'] = None

        a['TimeHOffset'] = 0
        a['TimeMOffset'] = 0
        a['TimeApOffset'] = 0
        a['PlatOffset'] = 0
        a['RowAnimRow'] = -1
        a['RowAnimOffset'] = 0

        self._AnimateToTargets(col, ver)

    def _AnimateToTargets(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return

        if self._AnimateOneRollerStep(col, ver):
            return
        self._AnimateRowsTopDown(col, ver)

    def _AnimateOneRollerStep(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return False

        if int(a.get('TimeHOffset', 0)) > 0:
            return self._ContinueRoller(col, ver, 'TimeH')
        if int(a.get('TimeMOffset', 0)) > 0:
            return self._ContinueRoller(col, ver, 'TimeM')
        if int(a.get('TimeApOffset', 0)) > 0:
            return self._ContinueRoller(col, ver, 'TimeAp')
        if int(a.get('PlatOffset', 0)) > 0:
            return self._ContinueRoller(col, ver, 'Plat')

        timeSeqs = self.TimeSeqs
        platSeq = self.PlatformSeq

        tgtH = str(a.get('TargetTimeH', '') or '')
        tgtM = str(a.get('TargetTimeM', '') or '')
        tgtA = str(a.get('TargetTimeAp', '') or '')
        tgtP = str(a.get('TargetPlat', '') or '')

        hIdx = int(a.get('TimeHIdx', 0))
        mIdx = int(a.get('TimeMIdx', 0))
        aIdx = int(a.get('TimeApIdx', 0))
        pIdx = int(a.get('PlatIdx', 0))

        try:
            curH = str(timeSeqs['H'][hIdx % len(timeSeqs['H'])])
        except:
            curH = ''
        try:
            curM = str(timeSeqs['M'][mIdx % len(timeSeqs['M'])])
        except:
            curM = ''
        curA = ''
        apSeq = timeSeqs.get('AP')
        if apSeq is not None:
            try:
                curA = str(apSeq[aIdx % len(apSeq)])
            except:
                curA = ''
        try:
            curP = str(platSeq[pIdx % len(platSeq)])
        except:
            curP = ''

        if curH != tgtH:
            a['TimeHOffset'] = 1
            self._RepaintLater(int(ROLL_FRAME_MS), col, ver, self._AnimateToTargets)
            return True
        if curM != tgtM:
            a['TimeMOffset'] = 1
            self._RepaintLater(int(ROLL_FRAME_MS), col, ver, self._AnimateToTargets)
            return True
        if apSeq is not None and curA != tgtA:
            a['TimeApOffset'] = 1
            self._RepaintLater(int(ROLL_FRAME_MS), col, ver, self._AnimateToTargets)
            return True
        if curP != tgtP:
            a['PlatOffset'] = 1
            self._RepaintLater(int(ROLL_FRAME_MS), col, ver, self._AnimateToTargets)
            return True

        return False

    def _ContinueRoller(self, col, ver, kind):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return False

        h = 20
        step = int(ROLL_PIX_PER_FRAME)
        if step < 1:
            step = 1

        if kind == 'TimeH':
            off = int(a.get('TimeHOffset', 0)) + step
            if off >= h:
                a['TimeHOffset'] = 0
                try:
                    a['TimeHIdx'] = (int(a.get('TimeHIdx', 0)) + 1) % len(self.TimeSeqs.get('H') or [''])
                except:
                    a['TimeHIdx'] = int(a.get('TimeHIdx', 0)) + 1
            else:
                a['TimeHOffset'] = off
        elif kind == 'TimeM':
            off = int(a.get('TimeMOffset', 0)) + step
            if off >= h:
                a['TimeMOffset'] = 0
                try:
                    a['TimeMIdx'] = (int(a.get('TimeMIdx', 0)) + 1) % len(self.TimeSeqs.get('M') or [''])
                except:
                    a['TimeMIdx'] = int(a.get('TimeMIdx', 0)) + 1
            else:
                a['TimeMOffset'] = off
        elif kind == 'TimeAp':
            off = int(a.get('TimeApOffset', 0)) + step
            if off >= h:
                a['TimeApOffset'] = 0
                try:
                    a['TimeApIdx'] = (int(a.get('TimeApIdx', 0)) + 1) % len(self.TimeSeqs.get('AP') or [''])
                except:
                    a['TimeApIdx'] = int(a.get('TimeApIdx', 0)) + 1
            else:
                a['TimeApOffset'] = off
        elif kind == 'Plat':
            off = int(a.get('PlatOffset', 0)) + step
            if off >= h:
                a['PlatOffset'] = 0
                try:
                    a['PlatIdx'] = (int(a.get('PlatIdx', 0)) + 1) % len(self.PlatformSeq or [''])
                except:
                    a['PlatIdx'] = int(a.get('PlatIdx', 0)) + 1
            else:
                a['PlatOffset'] = off

        self._RepaintLater(int(ROLL_FRAME_MS), col, ver, self._AnimateToTargets)
        return True

    def _AnimateRowsTopDown(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return

        rows = int(self.RenderGeom.get('Rows', PREF_ROWS))

        if int(a.get('RowAnimOffset', 0)) > 0:
            self._ContinueRow(col, ver)
            return

        rf = list(a.get('RowFaceIdxs') or [0] * rows)
        tgt = list(a.get('TargetRowFaces') or [0] * rows)

        r = 0
        while r < rows:
            mod = 1
            gi = None
            try:
                gi = int((self.Columns[col] or {}).get('GroupIndex'))
            except:
                gi = None
            facesByRow = []
            if gi is not None:
                facesByRow = self.GroupRowFaces.get(int(gi)) or []
            try:
                if r < len(facesByRow):
                    mod = max(1, len(facesByRow[r]))
            except:
                mod = 1
            if (int(rf[r]) % mod) != (int(tgt[r]) % mod):
                break
            r += 1

        if r >= rows:
            self._AnimateSpecialThenComplete(col, ver)
            return

        a['RowAnimRow'] = int(r)
        a['RowAnimOffset'] = 1
        self._RepaintLater(int(ROW_FRAME_MS), col, ver, self._AnimateToTargets)

    def _ContinueRow(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return

        rows = int(self.RenderGeom.get('Rows', PREF_ROWS))
        r = int(a.get('RowAnimRow', -1))
        if r < 0 or r >= rows:
            a['RowAnimOffset'] = 0
            a['RowAnimRow'] = -1
            return

        h = int(self.RenderGeom.get('CellH', 22)) - 2
        step = int(ROW_PIX_PER_FRAME)
        if step < 1:
            step = 1

        off = int(a.get('RowAnimOffset', 0)) + step
        if off >= h:
            a['RowAnimOffset'] = 0

            rf = list(a.get('RowFaceIdxs') or [0] * rows)
            mod = 1
            try:
                gi = int((self.Columns[col] or {}).get('GroupIndex'))
            except:
                gi = None
            facesByRow = []
            if gi is not None:
                facesByRow = self.GroupRowFaces.get(int(gi)) or []
            try:
                if r < len(facesByRow):
                    mod = max(1, len(facesByRow[r]))
            except:
                mod = 1

            rf[r] = (int(rf[r]) + 1) % int(mod)
            a['RowFaceIdxs'] = rf

            tgt = list(a.get('TargetRowFaces') or [0] * rows)
            if (int(rf[r]) % mod) != (int(tgt[r]) % mod):
                a['RowAnimOffset'] = 1
            else:
                a['RowAnimRow'] = -1

        else:
            a['RowAnimOffset'] = off

        self._RepaintLater(int(ROW_FRAME_MS), col, ver, self._AnimateToTargets)

    def _AnimateSpecialThenComplete(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return
        off = int(a.get('SpecialOffset', 0))
        tgt = int(a.get('SpecialTargetOffset', 0))
        if off != tgt:
            step = int(ROW_PIX_PER_FRAME)
            if step < 1:
                step = 1
            if off < tgt:
                off = min(tgt, off + step)
            else:
                off = max(tgt, off - step)
            a['SpecialOffset'] = int(off)
            self._RepaintLater(int(ROW_FRAME_MS), col, ver, self._AnimateSpecialThenComplete)
            return
        self._OnPhaseComplete(col, ver)

    def _OnPhaseComplete(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return

        phase = str(a.get('Phase', 'IDLE'))
        if phase == 'CLEAR':
            self.DisplayByCol[col] = None
            a['SvcKey'] = None
            a['Phase'] = 'HOLD'
            self._RepaintLater(int(CLEAR_BLANK_HOLD_MS), col, ver, self._BeginSetPhase)
            return

        if phase == 'SET':
            self.DisplayByCol[col] = a.get('NextRn')
            a['Phase'] = 'IDLE'
            return

        a['Phase'] = 'IDLE'

    def _BeginSetPhase(self, col, ver):
        a = self.ColAnim.get(col) or {}
        if int(a.get('Version', 0)) != int(ver):
            return

        rn = a.get('NextRn')
        svc = None
        if rn:
            svc = self.SvcByRn.get(str(rn))

        rows = int(self.RenderGeom.get('Rows', PREF_ROWS))
        tgtRowFaces = [0] * rows
        tgtStatus = ''
        tgtSpecial = ''
        tgtPlat = ''
        tgtH = ''
        tgtM = ''
        tgtAp = ''

        if svc is not None:
            tgtStatus = str(getattr(svc, 'Status', '') or '').strip().upper()
            tgtSpecial = str(getattr(svc, 'Special', '') or '').strip()
            tgtPlat = str(getattr(svc, 'Plat', '') or '').strip()

            try:
                hh, mm, ap = MinutesToDisplayParts(int(getattr(svc, 'AdjMin', 0)), USE_12_HOUR_TIME)
            except:
                hh, mm, ap = ('', '', '')
            tgtH = hh
            tgtM = mm
            tgtAp = ap

            gi = None
            try:
                gi = self.GroupIndexByDest.get(_NormKey(getattr(svc, 'Dest', '')))
            except:
                gi = None

            if gi is not None:
                stToRow = self.GroupStationToRow.get(int(gi)) or {}
                stToFace = self.GroupStationToFace.get(int(gi)) or {}

                rawStops = _EnsureDestAtEnd(_ParseStops(getattr(svc, 'Call', '')), getattr(svc, 'Dest', ''))
                for sst in rawStops:
                    k = _NormKey(sst)
                    if k == "":
                        continue
                    try:
                        rix = int(stToRow.get(k))
                    except:
                        rix = None
                    if rix is None:
                        continue
                    if 0 <= rix < rows:
                        try:
                            fi = int(stToFace.get(k, 0))
                        except:
                            fi = 0
                        if fi < 0:
                            fi = 0
                        tgtRowFaces[rix] = fi

        a['TargetRowFaces'] = tgtRowFaces
        a['TargetTimeH'] = tgtH
        a['TargetTimeM'] = tgtM
        a['TargetTimeAp'] = tgtAp
        a['TargetPlat'] = tgtPlat
        a['TargetStatus'] = tgtStatus
        a['TargetSpecial'] = tgtSpecial
        a['Status'] = tgtStatus
        a['Special'] = tgtSpecial
        try:
            sh = int(self.RenderGeom.get('SpecialH', 26))
        except:
            sh = 26
        if str(tgtSpecial or '') != '':
            a['SpecialOffset'] = 0 - int(sh)
            a['SpecialTargetOffset'] = 0
        else:
            a['SpecialOffset'] = 0
            a['SpecialTargetOffset'] = 0

        try:
            a['SvcKey'] = str(tgtH) + '|' + str(tgtM) + '|' + str(tgtPlat) + '|' + str(tgtStatus)
        except:
            a['SvcKey'] = None

        a['Phase'] = 'SET'
        self._AnimateToTargets(col, ver)

    def _RepaintLater(self, delayMs, col, ver, nextFn):
        def _Do(ev=None):
            a = self.ColAnim.get(col) or {}
            if int(a.get('Version', 0)) != int(ver):
                return
            try:
                if self.Panel is not None:
                    self.Panel.repaint()
            except:
                pass
            try:
                nextFn(col, ver)
            except:
                pass

        try:
            t = swing.Timer(int(delayMs), _Do)
            t.setRepeats(False)
            t.start()
        except:
            _Do()

    def GetRenderState(self):
        out = {}
        out.update(self.RenderGeom)
        out['Groups'] = list(self.GroupsPlan or [])
        out['Columns'] = list(self.Columns or [])
        out['ColAnim'] = dict(self.ColAnim or {})
        out['GroupRowFaces'] = dict(self.GroupRowFaces or {})
        out['DisplayNameMap'] = dict(self.DisplayNameMap or {})
        out['PlatformSeq'] = list(self.PlatformSeq or [""])
        out['TimeSeqs'] = dict(self.TimeSeqs or {})
        return out

    def Cleanup(self):
        try:
            if self._probeTimer is not None:
                self._probeTimer.stop()
        except:
            pass
        self._probeTimer = None
        try:
            if self._refreshTimer is not None:
                self._refreshTimer.stop()
        except:
            pass
        self._refreshTimer = None
        try:
            if self._pollTimer is not None:
                self._pollTimer.stop()
        except:
            pass
        self._pollTimer = None

        try:
            if self.TimeMem is not None and self._pcl is not None:
                self.TimeMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if self.DayMem is not None and self._pcl is not None:
                self.DayMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if self.TTMem is not None and self._pcl is not None:
                self.TTMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if PAR is not None and self._pcl is not None:
                PAR.removePlatformListener(self._pcl)
        except:
            pass
        self._pcl = None

        try:
            if self.Frame is not None:
                self.Frame.dispose()
        except:
            pass
        self.Frame = None


# Avoid duplicate instances if script is re-run.
try:
    if 'PIDRotaryLarge_Manager' in globals() and PIDRotaryLarge_Manager is not None:
        PIDRotaryLarge_Manager.Cleanup()
except:
    pass

PIDRotaryLarge_Manager = RotaryLargeWindow()