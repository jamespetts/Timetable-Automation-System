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
# Lightbox-style concourse Passenger Information Display for JMRI 5.14
#
# <<PID-DISP-NAME: Lightbox concourse departure indicator>>
# <<DESCRIPTION: A concourse lightbox display showing the next trains on all platforms, with Solari-style persistent assignment and optional direction grouping>>
#
# User-configurable settings discovered by TASSetup.py (do not modify TASSetup.py):
# <<SETTING DESCRIPTION NUMBER: Concourse columns>>
# <<SETTING DESCRIPTION NUMBER: Calling and destination row limit>>
# <<SETTING DESCRIPTION NUMBER: Show trains scheduled less than this many minutes in the future>>
# <<SETTING DESCRIPTION BOOLEAN: Only show trains whose platform has been allocated (requires platform allocation setup)>>
# <<SETTING DESCRIPTION BOOLEAN: Hide empty stock workings>>
#
# Notes on behaviour:
# - Uses PIDLightboxSingle.py style: fonts, colours, padding, fade animations.
# - Each column represents one service (one working). Columns are persistent: a working stays in its assigned column
#   until it clears, and other workings do not move to fill gaps (Solari-style).
# - One service per platform is shown at any time.
# - Direction grouping:
#   * Platforms are grouped by their unique Direction value across the whole timetable (all days).
#   * Columns are allocated to groups proportionional to platform count (ungrouped platforms count as one group).
# - The calling/destination section uses static apertures:
#   * Calling point apertures are derived from timetable calling patterns (canonical line-of-route order).
#   * If there are more calling points than the apertures allow, "AND ALL STATIONS TO" is included (smaller font)
#     and is illuminated only when the service calls at any station not present in the displayed calling apertures.
#   * Destination apertures are one row per unique destination, illuminated for the service's destination.
# - If destinations exceed the configured row limit, the board height expands automatically.
#
# Jython 2.7 / ASCII only / CamelCase / Thread-safe EDT

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, RenderingHints, Dimension
from java.awt import BasicStroke
from java.awt import GraphicsEnvironment
from java.awt import RadialGradientPaint
from java.awt.image import BufferedImage
from java.awt.geom import Point2D
from javax.swing import Timer
from javax.swing import SwingUtilities
from java.lang import Runnable
import java.beans as beans
import java.text.SimpleDateFormat as SimpleDateFormat
import jmri
from jmri import InstanceManager
import os, csv, math

import TASBeanLookup as TBL
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption


# ------------------------------------------------------------
# EDT helper
# ------------------------------------------------------------
def InvokeLater(fn):
    class _R(Runnable):
        def run(self):
            try:
                fn()
            except Exception as ex:
                try:
                    print("[PIDLightbox] EDT invoke failed:", ex)
                except:
                    pass
    try:
        SwingUtilities.invokeLater(_R())
    except:
        try:
            fn()
        except:
            pass


# ------------------------------------------------------------
# TAS user settings (via TASSetup.py)
# ------------------------------------------------------------
def _SettingMemoryName(label):
    # Must match TASSetup.py memory naming
    try:
        s = str(label).strip()
    except:
        s = ""
    import re as _re
    key = _re.sub(r"[^A-Za-z0-9]+", "_", s).upper()
    return "TAS_USER_SETTING_" + key


def ReadIntSetting(label, defaultVal, minVal=None, maxVal=None):
    mem = _SettingMemoryName(label)
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(mem, str(int(defaultVal)))
        n = int(float(str(raw).strip()))
    except:
        n = int(defaultVal)
    if minVal is not None:
        n = max(int(minVal), n)
    if maxVal is not None:
        n = min(int(maxVal), n)
    return int(n)


def ReadBoolSetting(label, defaultVal=False):
    mem = _SettingMemoryName(label)
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(mem, "true" if defaultVal else "false")
        t = str(raw).strip().lower()
        if t in ["1", "true", "yes", "y", "on", "enabled"]:
            return True
        if t in ["0", "false", "no", "n", "off", "disabled"]:
            return False
    except:
        pass
    return bool(defaultVal)


# ------------------------------------------------------------
# Theme / geometry (from PIDLightboxSingle.py style)
# ------------------------------------------------------------
CABINET_COLOR = Color(0, 0, 0)
BORDER_COLOR = Color(0, 0, 0)
HEADER_BG = Color(20, 20, 20)
HEADER_TEXT = Color(245, 245, 245)
CELL_BG = Color(34, 34, 34)
UNLIT_TEXT = Color(28, 28, 28)
LIT_TEXT = Color(255, 230, 190)

CABINET_PAD = 10
CELL_PAD_X = 18
HEADER_PAD_Y = 24
CELL_PAD_Y = 18
GRID_STROKE = BasicStroke(4.0)

HEADER_FONT_SIZE = 34
CELL_FONT_SIZE = 30

# "AND ALL STATIONS TO" uses a smaller font (otherwise same style)
AND_FONT_SCALE = 0.75

# Default column width (per service)
BASE_COL_W = 320

# Platform numerals row height is computed from CELL_FONT and padding;
# no vertical separators between platform tokens, just even spacing.
PLATFORM_ROW_MIN_LINES = 1

# Animation (from PIDLightboxSingle.py style)
ANIM_FPS_MS = 40
RISE_TAU_S = 0.06
FALL_TAU_S = 0.08
PERIODIC_REFRESH_MS = 60000


# ------------------------------------------------------------
# Memories / fast clock
# ------------------------------------------------------------
TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

Timebase = InstanceManager.getDefault(jmri.Timebase)
TimeParser12 = SimpleDateFormat("h:mm a")
TimeParser24 = SimpleDateFormat("H:mm")


def ParseTimeToMinutes(timeStr):
    s = (timeStr or "").strip()
    if s == "":
        return None
    for parser in [TimeParser12, TimeParser24]:
        try:
            parsed = parser.parse(s)
            return parsed.getHours() * 60 + parsed.getMinutes()
        except:
            pass
    return None


def CurrentMinutes():
    try:
        if Timebase is not None:
            ft = Timebase.getTime()
            return ft.getHours() * 60 + ft.getMinutes()
    except:
        pass
    try:
        return ParseTimeToMinutes(TimeMem.getValue() or "")
    except:
        return None


def ActiveProfileNameUpper():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        s = ("" if nm is None else str(nm)).strip()
        return s.upper()
    except:
        return ""


# ------------------------------------------------------------
# Timetable access
# ------------------------------------------------------------
def TimetablePath():
    try:
        name = TimetableMem.getValue() or ""
    except:
        name = ""
    name = str(name).strip()
    if name == "":
        return None
    try:
        profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    except:
        return None
    return os.path.join(profilePath, "timetable", name + ".csv")


def CsvRows():
    path = TimetablePath()
    if not (path and os.path.exists(path)):
        return []
    rows = []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            for r in rdr:
                rows.append(r)
    except Exception as ex:
        try:
            print("[PIDLightbox] Failed to read timetable:", ex)
        except:
            pass
        return []
    return rows


def PlatformField(row):
    try:
        v = (row.get("Plat", "") or "").strip()
    except:
        v = ""
    if not v:
        try:
            v = (row.get("Platform", "") or "").strip()
        except:
            v = ""
    return v


def CaseInsensitive(row, key):
    target = (key or "").strip().lower()
    try:
        for k in (row.keys() or []):
            if (k or "").strip().lower() == target:
                v = row.get(k, "")
                return (v or "").strip()
    except:
        pass
    return ""


def DirectionField(row):
    try:
        return (CaseInsensitive(row, "Direction") or "").strip()
    except:
        return ""


def DetectAllPlatforms(rows):
    plats = []
    seen = set()
    for r in (rows or []):
        p = PlatformField(r)
        if not p:
            continue
        if p in seen:
            continue
        seen.add(p)
        plats.append(p)
    try:
        plats.sort(key=lambda s: (not str(s).isdigit(), int(s) if str(s).isdigit() else str(s)))
    except:
        pass
    return plats


# ------------------------------------------------------------
# Platform overrides (same contract as LightboxSingle)
# ------------------------------------------------------------
def ParseOverrides(s):
    out = {}
    if not s:
        return out
    parts = str(s).replace(",", ";").split(";")
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def GetPlatformOverride(reportingNumber):
    try:
        if OverridesMem is None:
            return None
        mapping = ParseOverrides(OverridesMem.getValue())
        return mapping.get(reportingNumber)
    except:
        return None


# ------------------------------------------------------------
# Departure timing point logic (same contract as LightboxSingle)
# ------------------------------------------------------------
def _DepartureTPList():
    names = []
    try:
        raw = DepartTPMem.getValue() if DepartTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        try:
            nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
            base = ("" if nm is None else str(nm)).strip()
            if base:
                names = [base]
        except:
            pass
    return names


def HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    tps = _DepartureTPList()
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
            if str(rn) != str(reportingNumber):
                continue
            if str(d) != str(dayName):
                continue
            mm = ParseTimeToMinutes(tstr)
            if mm is None:
                continue
            if mm <= int(nowMinutes):
                return True
    return False


def HasAnyTimingToday(reportingNumber, dayName):
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
            if str(rn) == str(reportingNumber) and str(d) == str(dayName):
                return True
    return False


# ------------------------------------------------------------
# Disruption-aware ordering (inherited delays) - from LightboxSingle rule
# ------------------------------------------------------------
def ResolveDelayWithInheritance(rowsToday, rn, schedDepMin, visited=None):
    if visited is None:
        visited = set()
    if rn in visited:
        return ("ontime", 0)
    visited.add(rn)
    try:
        d = getDisruption(rn)
    except:
        d = None
    if d is not None:
        try:
            delay = int(d)
        except:
            delay = 0
        if delay >= 1440:
            return ("cancel", None)
        if delay > 0:
            return ("delay", delay)

    formers = []
    for r in rowsToday:
        try:
            if (r.get("Forms", "") or "").strip() == rn:
                arr = (r.get("Arr", "") or "").strip()
                arrMin = ParseTimeToMinutes(arr) if arr else None
                formers.append((r, arrMin))
        except:
            pass
    if not formers:
        return ("ontime", 0)

    chosen = None
    if schedDepMin is not None:
        before = [t for t in formers if t[1] is not None and t[1] <= schedDepMin]
        if before:
            before.sort(key=lambda t: t[1])
            chosen = before[-1][0]
    if chosen is None:
        chosen = formers[0][0]
    formerRN = (chosen.get("Reporting number", "") or "").strip()
    return ResolveDelayWithInheritance(rowsToday, formerRN, schedDepMin, visited)


# ------------------------------------------------------------
# Font selection (same strategy as LightboxSingle)
# ------------------------------------------------------------
def AvailableFamilies():
    try:
        ge = GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []


def PickFamily():
    prefs = ["Johnston 100", "Johnston100", "Railway", "Railway Sans", "Granby", "Liberation Sans", "Helvetica", "Arial", "SansSerif"]
    fams = [f for f in AvailableFamilies()]
    low = set([f.lower() for f in fams])
    for p in prefs:
        if p.lower() in low:
            return p
    for f in fams:
        if "railway" in f.lower():
            return f
    return "SansSerif"


FONT_FAM = PickFamily()
HEADER_FONT = Font(FONT_FAM, Font.BOLD, HEADER_FONT_SIZE)
CELL_FONT = Font(FONT_FAM, Font.BOLD, CELL_FONT_SIZE)
AND_FONT = Font(FONT_FAM, Font.BOLD, int(max(10, int(round(float(CELL_FONT_SIZE) * AND_FONT_SCALE)))))


# ------------------------------------------------------------
# Text wrapping
# ------------------------------------------------------------
def WrapTextLines(text, fm, maxWidth):
    s = str(text or "").strip()
    if s == "":
        return [""]
    words = s.split()
    lines = []
    cur = ""
    for w in words:
        trial = w if cur == "" else (cur + " " + w)
        if fm.stringWidth(trial) <= maxWidth:
            cur = trial
        else:
            if cur != "":
                lines.append(cur)
                cur = w
            else:
                lines.append(w)
                cur = ""
    if cur != "":
        lines.append(cur)
    if not lines:
        lines = [s]
    return lines


# ------------------------------------------------------------
# Simple ECS heuristic
# ------------------------------------------------------------
def IsEcsDestination(destUpper):
    try:
        s = str(destUpper or "").strip().upper()
        return s.startswith("EMPTY") or s.startswith("ECS")
    except:
        return False


# ------------------------------------------------------------
# Canonical calling order from calling patterns
# ------------------------------------------------------------
def _ParseStops(callText):
    out = []
    for t in str(callText or "").split(","):
        s = (t or "").strip()
        if s == "":
            continue
        # 'Terminates here' and 'THIS STATION' mean the same thing; do not display them as calling points.
        try:
            sl = s.strip().lower()
        except:
            sl = ""
        # Normalise internal whitespace and strip common trailing punctuation.
        try:
            import re as _re
            sln = _re.sub(r"\s+", " ", sl).strip()
        except:
            sln = sl
        sln = sln.rstrip(" .,:;!?)")
        if sln == "terminates here" or sln == "this station":
            continue
        out.append(s)
    return out


def BuildCanonicalStopOrder(rowsForGroup):
    seqs = []
    firstSeen = []
    seenFirst = set()
    for r in (rowsForGroup or []):
        ct = CaseInsensitive(r, "Calling pattern")
        stops = _ParseStops(ct)
        if not stops:
            continue
        seqs.append(stops)
        for s in stops:
            k = s.lower()
            if k not in seenFirst:
                seenFirst.add(k)
                firstSeen.append(s)

    if not seqs:
        return []

    nodes = {}
    indeg = {}
    adj = {}
    for seq in seqs:
        for s in seq:
            k = s.lower()
            if k not in nodes:
                nodes[k] = s
            if k not in indeg:
                indeg[k] = 0
            if k not in adj:
                adj[k] = set()
        for i in range(len(seq) - 1):
            a = seq[i].lower()
            b = seq[i + 1].lower()
            if a == b:
                continue
            if b not in adj.get(a, set()):
                adj.setdefault(a, set()).add(b)
                indeg[b] = indeg.get(b, 0) + 1

    q = []
    for k in nodes.keys():
        if indeg.get(k, 0) == 0:
            q.append(k)

    def _FirstIndex(k):
        try:
            return [x.lower() for x in firstSeen].index(k)
        except:
            return 999999

    try:
        q.sort(key=lambda kk: _FirstIndex(kk))
    except:
        pass

    outKeys = []
    while q:
        k = q.pop(0)
        outKeys.append(k)
        for nb in list(adj.get(k, set())):
            indeg[nb] = indeg.get(nb, 0) - 1
            if indeg[nb] == 0:
                q.append(nb)
        try:
            q.sort(key=lambda kk: _FirstIndex(kk))
        except:
            pass

    if len(outKeys) != len(nodes.keys()):
        return list(firstSeen)

    out = []
    for k in outKeys:
        out.append(nodes.get(k, k))
    return out


# ------------------------------------------------------------
# Group detection by Direction/Platform correspondence
# ------------------------------------------------------------
def BuildPlatformDirectionGroups(rows):
    p2dirs = {}
    for r in (rows or []):
        p = PlatformField(r)
        if not p:
            continue
        d = DirectionField(r)
        d = (d or "").strip()
        if p not in p2dirs:
            p2dirs[p] = set()
        p2dirs[p].add(d)

    directional = {}
    ungrouped = []
    for p, ds in p2dirs.items():
        if len(ds) == 1:
            dv = list(ds)[0]
            directional.setdefault(dv, []).append(p)
        else:
            ungrouped.append(p)

    def _PlatSortKey(s):
        try:
            if str(s).isdigit():
                return (0, int(s))
        except:
            pass
        return (1, str(s))

    for dv in directional.keys():
        try:
            directional[dv].sort(key=_PlatSortKey)
        except:
            pass
    try:
        ungrouped.sort(key=_PlatSortKey)
    except:
        pass

    hasGroups = (len(directional.keys()) > 0)
    return hasGroups, directional, ungrouped


# ------------------------------------------------------------
# Service collection
# ------------------------------------------------------------
def _RowsToday(rows, dayName):
    out = []
    for r in (rows or []):
        try:
            if (r.get(dayName, "") or "").strip().lower() == "true":
                out.append(r)
        except:
            pass
    return out


def _DisplayDestinationKey(destUpper, profUpper):
    if destUpper == profUpper:
        return "THIS STATION"
    return destUpper


def _ServicePlatformForRow(row, rn):
    alloc = None
    try:
        alloc = PAR.getPlatform(rn)
    except:
        alloc = None
    hasAlloc = (alloc is not None and str(alloc).strip() != "")
    if hasAlloc:
        return (str(alloc).strip(), True)
    ov = GetPlatformOverride(rn)
    if ov is not None and str(ov).strip() != "":
        return (str(ov).strip(), False)
    return (str(PlatformField(row) or "").strip(), False)


def CollectUpcomingServicesAll(rowsAll, dayName, nowMin, requireAlloc, hideEcs, lookAheadMin):
    if nowMin is None:
        return []

    rowsToday = _RowsToday(rowsAll, dayName)
    profUpper = ActiveProfileNameUpper()
    out = []

    upper = None
    try:
        la = int(lookAheadMin)
    except:
        la = 0
    if (not requireAlloc) and la > 0:
        upper = int(nowMin) + int(la)

    for r in (rowsToday or []):
        dep = (r.get("Dep", "") or "").strip()
        if dep == "":
            continue
        depMin = ParseTimeToMinutes(dep)
        if depMin is None:
            continue
        rn = (r.get("Reporting number", "") or "").strip()
        if rn == "":
            continue

        plat, hasAlloc = _ServicePlatformForRow(r, rn)
        if requireAlloc and (not hasAlloc):
            continue
        if plat == "":
            continue

        try:
            kind, val = ResolveDelayWithInheritance(rowsToday, rn, depMin, visited=set())
        except:
            kind, val = ("ontime", 0)
        if kind == "cancel":
            continue

        try:
            if HasDepartedAtConfiguredTP(rn, dayName, nowMin):
                continue
        except:
            pass

        if kind == "ontime":
            try:
                direct = getDisruption(rn)
            except:
                direct = None
            if (direct is None) and (not HasAnyTimingToday(rn, dayName)):
                if depMin < nowMin:
                    continue

        effMin = depMin
        if kind == "delay" and val and val > 0:
            try:
                effMin = depMin + int(val)
            except:
                effMin = depMin

        if upper is not None:
            try:
                if int(effMin) > int(upper):
                    continue
            except:
                pass

        destRaw = (r.get("Destination", "") or "").strip()
        destUpper = destRaw.upper() if destRaw else ""
        destKey = ""
        if destUpper != "":
            if hideEcs and IsEcsDestination(destUpper):
                continue
            destKey = _DisplayDestinationKey(destUpper, profUpper)

        callText = (CaseInsensitive(r, "Calling pattern") or "").strip()
        stopsList = _ParseStops(callText)
        stopsSet = set([s.lower() for s in stopsList])

        dirVal = (DirectionField(r) or "").strip()

        out.append({
            "rn": rn,
            "plat": plat,
            "dir": dirVal,
            "effMin": effMin,
            "destKey": destKey,
            "stopsList": list(stopsList),
            "stopsSet": set(stopsSet)
        })

    out.sort(key=lambda t: t.get("effMin", 999999))
    return out


# ------------------------------------------------------------
# Painting panel
# ------------------------------------------------------------
class LightboxPanel(swing.JPanel):
    def __init__(self, window):
        swing.JPanel.__init__(self)
        self.Window = window
        self.setOpaque(True)
        self.setBackground(CABINET_COLOR)

    def paintComponent(self, g):
        g.setColor(self.getBackground())
        g.fillRect(0, 0, self.getWidth(), self.getHeight())
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            w = self.getWidth()
            h = self.getHeight()
            pad = int(CABINET_PAD)
            self.Window.PaintContent(g2, pad, pad, w - 2 * pad, h - 2 * pad)
        finally:
            g2.dispose()


# ------------------------------------------------------------
# Property change listener (EDT safe)
# ------------------------------------------------------------
class _PidPropertyChangeListener(beans.PropertyChangeListener):
    def __init__(self, callback):
        self._callback = callback

    def propertyChange(self, event):
        def _do():
            try:
                self._callback(event)
            except Exception as ex:
                try:
                    print("[PIDLightbox] propertyChange callback failed:", ex)
                except:
                    pass
        InvokeLater(_do)


# ------------------------------------------------------------
# Group layout model
# ------------------------------------------------------------
class GroupLayout(object):
    def __init__(self, groupId, titleText, platforms, colCount, isUngrouped):
        self.GroupId = str(groupId)
        self.TitleText = str(titleText or "")
        self.Platforms = list(platforms or [])
        self.ColCount = int(colCount)
        self.IsUngrouped = bool(isUngrouped)

        self.X = 0
        self.Width = 0

        self.HeaderHeight = 0
        self.HasPlatformLabelRow = False
        self.PlatformLabelHeight = 0
        self.PlatformTokens = list(self.Platforms)
        self.PlatformRowHeight = 0

        self.BodyRows = []
        self.AssignedRNs = [None] * int(self.ColCount)


# ------------------------------------------------------------
# Main window/controller
# ------------------------------------------------------------
class PIDLightboxConcourseWindow(object):
    def __init__(self):
        self.Cleaned = False

        self.NumCols = 4
        self.RowLimit = 8
        self.LookAheadMin = 10
        self.RequireAlloc = False
        self.HideEcs = False

        self.Groups = []
        self.TotalCols = 0
        self._lastAnimMs = None

        self.Brightness = {}

        self.Frame = swing.JFrame("Concourse departures")
        self.Frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        self.Frame.setResizable(False)
        self.Panel = LightboxPanel(self)
        self.Frame.setContentPane(self.Panel)

        self._displayListener = _PidPropertyChangeListener(self.UpdateDisplay)
        try:
            TimeMem.addPropertyChangeListener(self._displayListener)
        except:
            pass
        try:
            DayMem.addPropertyChangeListener(self._displayListener)
        except:
            pass
        try:
            if TimetableMem is not None:
                TimetableMem.addPropertyChangeListener(self._displayListener)
        except:
            pass
        try:
            if OverridesMem is not None:
                OverridesMem.addPropertyChangeListener(self._displayListener)
        except:
            pass
        try:
            if DepartTPMem is not None:
                DepartTPMem.addPropertyChangeListener(self._displayListener)
        except:
            pass
        try:
            PAR.addPlatformListener(self._displayListener)
        except:
            pass

        self.AnimTimer = Timer(ANIM_FPS_MS, self.OnAnimTick)
        self.AnimTimer.start()
        self.RefreshTimer = Timer(PERIODIC_REFRESH_MS, self.UpdateDisplay)
        self.RefreshTimer.start()

        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(inner_self, e):
                self.Cleanup(e)
            def windowClosed(inner_self, e):
                self.Cleanup(e)
        self.Frame.addWindowListener(CloseHandler())

        self.RebuildStaticLayout()
        self.UpdateDisplay()

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.Frame, 32)
        except:
            pass

        self.Frame.setVisible(True)

    def ReadSettings(self):
        self.NumCols = ReadIntSetting("Concourse columns", 4, 1, 12)
        self.RowLimit = ReadIntSetting("Calling and destination row limit", 8, 1, 40)
        self.LookAheadMin = ReadIntSetting("Show trains scheduled less than this many minutes in the future", 10, 0, 240)
        self.RequireAlloc = ReadBoolSetting("Only show trains whose platform has been allocated (requires platform allocation setup)", False)
        self.HideEcs = ReadBoolSetting("Hide empty stock workings", False)

    def _LineAdvance(self, fm):
        adv = fm.getAscent() + fm.getDescent()
        if adv <= 0:
            adv = fm.getHeight()
        if adv <= 0:
            adv = 1
        return int(adv)

    def _MeasureFonts(self):
        img = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
        g2 = img.createGraphics()
        try:
            g2.setFont(HEADER_FONT)
            fmH = g2.getFontMetrics(HEADER_FONT)
            g2.setFont(CELL_FONT)
            fmC = g2.getFontMetrics(CELL_FONT)
            g2.setFont(AND_FONT)
            fmA = g2.getFontMetrics(AND_FONT)
            return fmH, fmC, fmA
        finally:
            try:
                g2.dispose()
            except:
                pass

    def _PickGroupHeadingDestinations(self, rowsForGroup, maxCount=3):
        profUpper = ActiveProfileNameUpper()
        dests = []
        seen = set()
        for r in (rowsForGroup or []):
            d = (CaseInsensitive(r, "Destination") or "").strip()
            if d == "":
                continue
            du = d.upper()
            if self.HideEcs and IsEcsDestination(du):
                continue
            dk = _DisplayDestinationKey(du, profUpper)
            key = str(dk).upper()
            if key in seen:
                continue
            seen.add(key)
            dests.append(key)
        dests.sort()
        if maxCount <= 0:
            return dests
        return dests[:int(maxCount)]

    def _MakeGroupHeadingText(self, destList):
        if not destList:
            return "TRAINS FROM PLATFORM"
        if len(destList) == 1:
            return "TRAINS TO " + destList[0] + " FROM PLATFORM"
        if len(destList) == 2:
            return "TRAINS TO " + destList[0] + " & " + destList[1] + " FROM PLATFORM"
        body = ", ".join(destList[:-1]) + ", & " + destList[-1]
        return "TRAINS TO " + body + " FROM PLATFORM"

    def _BuildGroups(self, rowsAll):
        hasGroups, directional, ungroupedPlats = BuildPlatformDirectionGroups(rowsAll)

        if not hasGroups:
            plats = DetectAllPlatforms(rowsAll)
            g = GroupLayout("UNGROUPED", "", plats, int(self.NumCols), True)
            return [g]

        groups = []
        dirKeys = list(directional.keys())
        dirKeys.sort(key=lambda s: str(s))
        for d in dirKeys:
            plats = directional.get(d, [])
            if plats:
                groups.append({"id": "DIR_" + str(d), "dir": d, "plats": list(plats), "ungrouped": False})

        if ungroupedPlats:
            groups.append({"id": "UNGROUPED", "dir": "", "plats": list(ungroupedPlats), "ungrouped": True})

        totalPlatforms = 0
        for g in groups:
            totalPlatforms += len(g.get("plats", []))

        if totalPlatforms <= 0:
            plats = DetectAllPlatforms(rowsAll)
            return [GroupLayout("UNGROUPED", "", plats, int(self.NumCols), True)]

        alloc = []
        for g in groups:
            pcount = len(g.get("plats", []))
            raw = float(self.NumCols) * float(pcount) / float(totalPlatforms)
            base = int(math.floor(raw))
            if base < 1:
                base = 1
            alloc.append(base)

        s = sum(alloc)
        if s > int(self.NumCols):
            while s > int(self.NumCols):
                idx = None
                best = -1
                for i in range(len(alloc)):
                    if alloc[i] > 1 and alloc[i] > best:
                        best = alloc[i]
                        idx = i
                if idx is None:
                    break
                alloc[idx] -= 1
                s -= 1
        elif s < int(self.NumCols):
            while s < int(self.NumCols):
                idx = None
                best = -1
                for i in range(len(groups)):
                    pc = len(groups[i].get("plats", []))
                    if pc > best:
                        best = pc
                        idx = i
                if idx is None:
                    break
                alloc[idx] += 1
                s += 1

        out = []
        for i, g in enumerate(groups):
            colCount = int(alloc[i]) if i < len(alloc) else 1
            plats = g.get("plats", [])
            isUng = bool(g.get("ungrouped", False))
            title = ""
            out.append(GroupLayout(g.get("id", "G" + str(i)), title, plats, colCount, isUng))
        return out

    def _BuildStaticAperturesForGroup(self, gl, rowsAll):
        fmH, fmC, fmA = self._MeasureFonts()

        if gl.IsUngrouped:
            labelCount = int(gl.ColCount)
            if labelCount < 1:
                labelCount = 1
            lineH = fmH.getHeight()
            gl.HeaderHeight = (2 * HEADER_PAD_Y) + (labelCount * lineH)
            gl.HasPlatformLabelRow = True
            gl.PlatformLabelHeight = fmH.getHeight() + (2 * HEADER_PAD_Y)
        else:
            gl.HeaderHeight = fmH.getHeight() + (2 * HEADER_PAD_Y)
            gl.HasPlatformLabelRow = False
            gl.PlatformLabelHeight = 0

        lineAdvanceC = self._LineAdvance(fmC)
        gl.PlatformRowHeight = (2 * CELL_PAD_Y) + (PLATFORM_ROW_MIN_LINES * lineAdvanceC)

        platsSet = set([str(p) for p in (gl.Platforms or [])])
        groupRows = []
        for r in (rowsAll or []):
            p = PlatformField(r)
            if p and str(p) in platsSet:
                groupRows.append(r)

        profUpper = ActiveProfileNameUpper()
        destSet = {}
        for r in (groupRows or []):
            d = (CaseInsensitive(r, "Destination") or "").strip()
            if d == "":
                continue
            du = d.upper()
            if self.HideEcs and IsEcsDestination(du):
                continue
            dk = _DisplayDestinationKey(du, profUpper)
            key = str(dk).upper()
            if key not in destSet:
                destSet[key] = key
        destKeys = list(destSet.keys())
        destKeys.sort()

        callCanonical = BuildCanonicalStopOrder(groupRows)
        callKeys = []
        callSeen = set()
        for s in (callCanonical or []):
            k = str(s).strip().upper()
            if k == "":
                continue
            lk = k.lower()
            if lk in callSeen:
                continue
            callSeen.add(lk)
            callKeys.append(k)

        S = len(callKeys)
        D = len(destKeys)
        L = int(self.RowLimit)

        includeAndLabel = False
        callingShown = []

        if D <= L:
            if S <= (L - D):
                callingShown = list(callKeys)
                includeAndLabel = False
            else:
                includeAndLabel = True
                cap = max(0, (L - D - 1))
                callingShown = callKeys[:cap]
        else:
            cap = min(S, L)
            callingShown = callKeys[:cap]
            includeAndLabel = (S > cap)

        if not gl.IsUngrouped:
            dPick = self._PickGroupHeadingDestinations(groupRows, maxCount=3)
            gl.TitleText = self._MakeGroupHeadingText(dPick)

        gl.BodyRows = []

        def AddBodyRow(rtype, text, fontMetrics):
            maxTextW = int(BASE_COL_W) - (2 * CELL_PAD_X)
            lines = WrapTextLines(text, fontMetrics, maxTextW)
            lineAdv = self._LineAdvance(fontMetrics)
            h = (2 * CELL_PAD_Y) + (len(lines) * lineAdv)
            gl.BodyRows.append({"type": rtype, "key": text, "text": text, "lines": lines, "height": int(h)})

        for s in callingShown:
            AddBodyRow("call", s, fmC)

        if includeAndLabel:
            AddBodyRow("and", "AND ALL STATIONS TO", fmA)

        for d in destKeys:
            AddBodyRow("dest", d, fmC)

    def _BuildColumnMaps(self):
        x = 0
        for g in self.Groups:
            g.X = int(x)
            g.Width = int(g.ColCount) * int(BASE_COL_W)
            x += g.Width
        self.TotalCols = 0
        for g in self.Groups:
            self.TotalCols += int(g.ColCount)

    def _ComputeWindowSize(self):
        maxH = 0
        for g in self.Groups:
            h = 0
            h += int(g.HeaderHeight)
            if g.HasPlatformLabelRow:
                h += int(g.PlatformLabelHeight)
            h += int(g.PlatformRowHeight)
            for r in (g.BodyRows or []):
                h += int(r.get("height", 0))
            if h > maxH:
                maxH = h

        contentW = int(self.TotalCols) * int(BASE_COL_W)
        contentH = int(maxH)
        totalW = contentW + (2 * CABINET_PAD)
        totalH = contentH + (2 * CABINET_PAD)
        totalW = max(totalW, 520)
        totalH = max(totalH, 240)
        return (totalW, totalH)

    def _InitBrightnessState(self):
        self.Brightness = {}
        for gi, g in enumerate(self.Groups):
            for ti, tok in enumerate(g.PlatformTokens or []):
                for ci in range(int(g.ColCount)):
                    self.Brightness[("plat", gi, ti, ci)] = {"b": 0.0, "t": 0.0}

            for r in (g.BodyRows or []):
                rtype = r.get("type", "")
                key = r.get("key", "")
                norm = str(key or "").strip().lower()
                for ci in range(int(g.ColCount)):
                    self.Brightness[("row", gi, rtype, norm, ci)] = {"b": 0.0, "t": 0.0}

            if g.IsUngrouped:
                labelCount = int(g.ColCount)
                for li in range(labelCount):
                    for ci in range(int(g.ColCount)):
                        self.Brightness[("hdr", gi, li, ci)] = {"b": 0.0, "t": 0.0}

    def RebuildStaticLayout(self):
        self.ReadSettings()
        rowsAll = CsvRows()

        self.Groups = self._BuildGroups(rowsAll)
        for g in self.Groups:
            self._BuildStaticAperturesForGroup(g, rowsAll)

        self._BuildColumnMaps()
        (w, h) = self._ComputeWindowSize()

        try:
            self.Panel.setPreferredSize(Dimension(int(w), int(h)))
            self.Frame.pack()
        except:
            try:
                self.Frame.setSize(int(w) + 40, int(h) + 60)
            except:
                pass

        for g in self.Groups:
            if g.AssignedRNs is None or len(g.AssignedRNs) != int(g.ColCount):
                g.AssignedRNs = [None] * int(g.ColCount)

        self._InitBrightnessState()

    def _AssignServicesToGroups(self, servicesAll):
        svcByRn = {}
        for s in (servicesAll or []):
            rn = str(s.get("rn", "") or "")
            if rn != "":
                svcByRn[rn] = s

        for gi, g in enumerate(self.Groups):
            newRNs = list(g.AssignedRNs)
            platsSet = set([str(p) for p in (g.Platforms or [])])

            for i in range(int(g.ColCount)):
                rn = newRNs[i]
                if rn is None:
                    continue
                rnStr = str(rn)
                svc = svcByRn.get(rnStr)
                if svc is None:
                    newRNs[i] = None
                    continue
                if str(svc.get("plat", "")) not in platsSet:
                    newRNs[i] = None
                    continue

            usedPlatforms = set()
            usedRNs = set()
            for i in range(int(g.ColCount)):
                rn = newRNs[i]
                if rn is None:
                    continue
                svc = svcByRn.get(str(rn))
                if svc is None:
                    newRNs[i] = None
                    continue
                plat = str(svc.get("plat", "") or "")
                if plat == "":
                    newRNs[i] = None
                    continue
                if plat in usedPlatforms:
                    newRNs[i] = None
                    continue
                usedPlatforms.add(plat)
                usedRNs.add(str(rn))

            candidates = []
            for s in (servicesAll or []):
                plat = str(s.get("plat", "") or "")
                if plat == "" or plat not in platsSet:
                    continue
                rn = str(s.get("rn", "") or "")
                if rn == "" or rn in usedRNs:
                    continue
                if plat in usedPlatforms:
                    continue
                candidates.append(s)

            candidates.sort(key=lambda t: t.get("effMin", 999999))
            cIdx = 0
            for i in range(int(g.ColCount)):
                if newRNs[i] is not None:
                    continue
                while cIdx < len(candidates):
                    pick = candidates[cIdx]
                    cIdx += 1
                    rn = str(pick.get("rn", "") or "")
                    plat = str(pick.get("plat", "") or "")
                    if rn == "" or plat == "":
                        continue
                    if rn in usedRNs or plat in usedPlatforms:
                        continue
                    newRNs[i] = rn
                    usedRNs.add(rn)
                    usedPlatforms.add(plat)
                    break

            g.AssignedRNs = list(newRNs)

        return svcByRn

    def _UpdateTargets(self, svcByRn):
        for st in self.Brightness.values():
            st["t"] = 0.0

        for gi, g in enumerate(self.Groups):
            displayedCalling = set()
            hasAndRow = False
            for r in (g.BodyRows or []):
                if r.get("type") == "call":
                    displayedCalling.add(str(r.get("text", "") or "").strip().lower())
                if r.get("type") == "and":
                    hasAndRow = True

            for ci in range(int(g.ColCount)):
                rn = g.AssignedRNs[ci]
                if rn is None:
                    continue
                svc = svcByRn.get(str(rn))
                if svc is None:
                    continue

                plat = str(svc.get("plat", "") or "").strip()
                for ti, tok in enumerate(g.PlatformTokens or []):
                    if str(tok).strip().lower() == plat.lower():
                        st = self.Brightness.get(("plat", gi, ti, ci))
                        if st is not None:
                            st["t"] = 1.0
                        break

                stopsSet = svc.get("stopsSet", set())
                if stopsSet is None:
                    stopsSet = set()

                for r in (g.BodyRows or []):
                    rtype = r.get("type", "")
                    norm = str(r.get("text", "") or "").strip().lower()
                    if rtype == "call":
                        if norm in stopsSet:
                            st = self.Brightness.get(("row", gi, "call", norm, ci))
                            if st is not None:
                                st["t"] = 1.0

                if hasAndRow:
                    needAnd = False
                    for s in (stopsSet or set()):
                        if s not in displayedCalling:
                            needAnd = True
                            break
                    if needAnd:
                        st = self.Brightness.get(("row", gi, "and", "and all stations to", ci))
                        if st is not None:
                            st["t"] = 1.0

                destKey = str(svc.get("destKey", "") or "").strip().upper()
                if destKey != "":
                    st = self.Brightness.get(("row", gi, "dest", destKey.lower(), ci))
                    if st is not None:
                        st["t"] = 1.0

        for gi, g in enumerate(self.Groups):
            if not g.IsUngrouped:
                continue
            items = []
            for ci in range(int(g.ColCount)):
                rn = g.AssignedRNs[ci]
                if rn is None:
                    continue
                svc = svcByRn.get(str(rn))
                if svc is None:
                    continue
                items.append((ci, svc))
            items.sort(key=lambda t: t[1].get("effMin", 999999))
            for rankIdx, (ci, svc) in enumerate(items):
                li = int(rankIdx)
                st = self.Brightness.get(("hdr", gi, li, ci))
                if st is not None:
                    st["t"] = 1.0

    def UpdateDisplay(self, event=None):
        oldCols = int(self.NumCols)
        oldLimit = int(self.RowLimit)
        oldHide = bool(self.HideEcs)

        self.ReadSettings()

        needRebuild = False
        if int(self.NumCols) != oldCols or int(self.RowLimit) != oldLimit or bool(self.HideEcs) != oldHide:
            needRebuild = True
        try:
            if event is not None and (event.getSource() == TimetableMem):
                needRebuild = True
        except:
            pass

        if needRebuild:
            self.RebuildStaticLayout()

        rowsAll = CsvRows()
        dayName = str(DayMem.getValue() or "").strip()
        nowMin = CurrentMinutes()
        if nowMin is None:
            try:
                self.Panel.repaint()
            except:
                pass
            return

        servicesAll = CollectUpcomingServicesAll(
            rowsAll,
            dayName,
            nowMin,
            bool(self.RequireAlloc),
            bool(self.HideEcs),
            int(self.LookAheadMin)
        )

        svcByRn = self._AssignServicesToGroups(servicesAll)
        self._UpdateTargets(svcByRn)

        try:
            self.Panel.repaint()
        except:
            pass

    def OnAnimTick(self, event):
        from java.lang import System
        nowMs = System.currentTimeMillis()
        if self._lastAnimMs is None:
            self._lastAnimMs = nowMs
            return
        dtMs = int(nowMs - self._lastAnimMs)
        if dtMs < 1:
            dtMs = 1
        self._lastAnimMs = nowMs
        dt = float(dtMs) / 1000.0

        anyChange = False
        for st in self.Brightness.values():
            b = float(st.get("b", 0.0))
            t = float(st.get("t", 0.0))
            if abs(b - t) < 0.0005:
                st["b"] = t
                continue
            tau = RISE_TAU_S if t > b else FALL_TAU_S
            if tau <= 0.001:
                st["b"] = t
                anyChange = True
                continue
            alpha = 1.0 - math.exp(-dt / float(tau))
            st["b"] = b + (t - b) * alpha
            anyChange = True

        if anyChange:
            try:
                self.Panel.repaint()
            except:
                pass

    def _HeaderBaselineY(self, yTop, hBox, fm):
        adv = (fm.getAscent() + fm.getDescent())
        if adv <= 0:
            adv = fm.getHeight()
        if adv <= 0:
            adv = 1
        return int(yTop + (hBox - adv) // 2 + fm.getAscent())

    def _ScaleColor(self, c, mult):
        r = int(min(255, max(0, int(c.getRed() * mult))))
        g = int(min(255, max(0, int(c.getGreen() * mult))))
        b = int(min(255, max(0, int(c.getBlue() * mult))))
        return Color(r, g, b)

    def PaintCellText(self, g2, x, y, w, h, lines, brightness, fontObj):
        g2.setFont(fontObj)
        fm = g2.getFontMetrics(fontObj)
        frc = g2.getFontRenderContext()

        lineAdvance = self._LineAdvance(fm)
        n = max(1, len(lines))
        blockH = n * lineAdvance
        blockTop = y + (h - blockH) // 2

        boundsX = []
        boundsY = []
        boundsW = []
        boundsH = []
        for i in range(n):
            try:
                s = str(lines[i] or "")
            except:
                s = ""
            if s == "":
                boundsX.append(0.0)
                boundsY.append(-float(fm.getAscent()))
                boundsW.append(0.0)
                boundsH.append(float(lineAdvance))
                continue
            try:
                gv0 = fontObj.createGlyphVector(frc, s)
                b2 = gv0.getOutline(0.0, 0.0).getBounds2D()
                boundsX.append(float(b2.getX()))
                boundsY.append(float(b2.getY()))
                boundsW.append(float(b2.getWidth()))
                boundsH.append(float(b2.getHeight()))
            except:
                boundsX.append(0.0)
                boundsY.append(-float(fm.getAscent()))
                boundsW.append(float(fm.stringWidth(s)))
                boundsH.append(float(lineAdvance))

        def BaselineYForLine(i):
            lineTop = blockTop + (i * lineAdvance)
            gh = boundsH[i]
            if gh <= 0.0:
                gh = float(lineAdvance)
            glyphTopWanted = float(lineTop) + (float(lineAdvance) - gh) / 2.0
            return glyphTopWanted - boundsY[i]

        def BaselineXForLine(i):
            gw = boundsW[i]
            if gw <= 0.0:
                return float(x + CELL_PAD_X)
            centerLeft = float(x) + (float(w) - gw) / 2.0
            bx = centerLeft - boundsX[i]
            lo = float(x + CELL_PAD_X) - boundsX[i]
            hi = float(x + w - CELL_PAD_X) - (boundsX[i] + gw)
            if lo <= hi:
                if bx < lo:
                    bx = lo
                elif bx > hi:
                    bx = hi
            return bx

        if brightness <= 0.0001:
            g2.setColor(UNLIT_TEXT)
            for i in range(n):
                try:
                    s = str(lines[i] or "")
                except:
                    s = ""
                if s == "":
                    continue
                by = BaselineYForLine(i)
                bx = BaselineXForLine(i)
                try:
                    gv = fontObj.createGlyphVector(frc, s)
                    shp = gv.getOutline(float(bx), float(by))
                    g2.fill(shp)
                except:
                    tw = fm.stringWidth(s)
                    tx = x + (w - tw) // 2
                    if tx < (x + CELL_PAD_X):
                        tx = x + CELL_PAD_X
                    g2.drawString(s, int(tx), int(blockTop + (i * lineAdvance)) + fm.getAscent())
            return

        cx = float(x + (w // 2))
        cy = float(y + (h // 2))
        radius = float(max(w, h)) * 0.75
        bval = max(0.0, min(1.0, float(brightness)))

        colors = [self._ScaleColor(LIT_TEXT, 0.25 + 0.75 * bval), self._ScaleColor(LIT_TEXT, 0.05 * bval)]
        fractions = [0.0, 1.0]
        paint = RadialGradientPaint(Point2D.Float(cx, cy), float(radius), fractions, colors)
        try:
            g2.setPaint(paint)
            for i in range(n):
                try:
                    s = str(lines[i] or "")
                except:
                    s = ""
                if s == "":
                    continue
                by = BaselineYForLine(i)
                bx = BaselineXForLine(i)
                gv = fontObj.createGlyphVector(frc, s)
                shp = gv.getOutline(float(bx), float(by))
                g2.fill(shp)
        except:
            try:
                g2.setColor(colors[0])
                for i in range(n):
                    s = str(lines[i] or "")
                    tw = fm.stringWidth(s)
                    tx = x + (w - tw) // 2
                    if tx < (x + CELL_PAD_X):
                        tx = x + CELL_PAD_X
                    g2.drawString(s, int(tx), int(blockTop + (i * lineAdvance)) + fm.getAscent())
            except:
                pass

    def _PaintPlatformTokensInCell(self, g2, x, y, w, h, tokens, gi, ci):
        toks = list(tokens or [])
        if not toks:
            return
        n = len(toks)
        if n <= 0:
            return
        segW = float(w) / float(n)

        for ti, tok in enumerate(toks):
            sx = int(round(float(x) + float(ti) * segW))
            ex = int(round(float(x) + float(ti + 1) * segW))
            cw = int(max(1, ex - sx))
            lines = [str(tok)]
            self.PaintCellText(g2, sx, y, cw, h, lines, 0.0, CELL_FONT)
            st = self.Brightness.get(("plat", gi, ti, ci))
            b = float(st.get("b", 0.0)) if st is not None else 0.0
            if b > 0.001:
                self.PaintCellText(g2, sx, y, cw, h, lines, b, CELL_FONT)

    def _PaintUngroupedHeaderCell(self, g2, x, y, w, h, gi, ci, labelCount):
        if labelCount < 1:
            labelCount = 1
        labels = []
        for i in range(labelCount):
            if i == 0:
                labels.append("FIRST TRAIN")
            elif i == 1:
                labels.append("SECOND TRAIN")
            elif i == 2:
                labels.append("THIRD TRAIN")
            elif i == 3:
                labels.append("FOURTH TRAIN")
            elif i == 4:
                labels.append("FIFTH TRAIN")
            elif i == 5:
                labels.append("SIXTH TRAIN")
            elif i == 6:
                labels.append("SEVENTH TRAIN")
            elif i == 7:
                labels.append("EIGHTH TRAIN")
            elif i == 8:
                labels.append("NINTH TRAIN")
            elif i == 9:
                labels.append("TENTH TRAIN")
            else:
                labels.append(str(i + 1) + "TH TRAIN")

        segH = float(h) / float(labelCount)
        for li, txt in enumerate(labels):
            sy = int(round(float(y) + float(li) * segH))
            ey = int(round(float(y) + float(li + 1) * segH))
            ch = int(max(1, ey - sy))

            lines = [txt]
            self.PaintCellText(g2, x, sy, w, ch, lines, 0.0, HEADER_FONT)
            st = self.Brightness.get(("hdr", gi, li, ci))
            b = float(st.get("b", 0.0)) if st is not None else 0.0
            if b > 0.001:
                self.PaintCellText(g2, x, sy, w, ch, lines, b, HEADER_FONT)

    def PaintContent(self, g2, x, y, w, h):
        g2.setStroke(GRID_STROKE)

        maxGroupH = 0
        for g in self.Groups:
            gh = int(g.HeaderHeight)
            if g.HasPlatformLabelRow:
                gh += int(g.PlatformLabelHeight)
            gh += int(g.PlatformRowHeight)
            for r in (g.BodyRows or []):
                gh += int(r.get("height", 0))
            if gh > maxGroupH:
                maxGroupH = gh
        if maxGroupH < 1:
            maxGroupH = h

        gx = x
        for gi, g in enumerate(self.Groups):
            gw = int(g.ColCount) * int(BASE_COL_W)
            if gw <= 0:
                continue

            g2.setColor(CELL_BG)
            g2.fillRect(gx, y, gw, maxGroupH)

            curY = y

            if g.IsUngrouped:
                headerH = int(g.HeaderHeight)
                for ci in range(int(g.ColCount)):
                    cx = gx + ci * int(BASE_COL_W)
                    g2.setColor(HEADER_BG)
                    g2.fillRect(cx, curY, int(BASE_COL_W), headerH)
                    g2.setColor(BORDER_COLOR)
                    g2.drawRect(cx, curY, int(BASE_COL_W), headerH)
                    self._PaintUngroupedHeaderCell(g2, cx, curY, int(BASE_COL_W), headerH, gi, ci, int(g.ColCount))
                curY += headerH

                plH = int(g.PlatformLabelHeight)
                for ci in range(int(g.ColCount)):
                    cx = gx + ci * int(BASE_COL_W)
                    g2.setColor(HEADER_BG)
                    g2.fillRect(cx, curY, int(BASE_COL_W), plH)
                    g2.setColor(HEADER_TEXT)
                    g2.setFont(HEADER_FONT)
                    fmH = g2.getFontMetrics(HEADER_FONT)
                    txt = "PLATFORM"
                    tw = fmH.stringWidth(txt)
                    tx = cx + (int(BASE_COL_W) - tw) // 2
                    ty = self._HeaderBaselineY(curY, plH, fmH) - 2
                    g2.drawString(txt, tx, ty)
                    g2.setColor(BORDER_COLOR)
                    g2.drawRect(cx, curY, int(BASE_COL_W), plH)
                curY += plH
            else:
                headerH = int(g.HeaderHeight)
                g2.setColor(HEADER_BG)
                g2.fillRect(gx, curY, gw, headerH)
                g2.setColor(HEADER_TEXT)
                g2.setFont(HEADER_FONT)
                fmH = g2.getFontMetrics(HEADER_FONT)
                txt = str(g.TitleText or "")
                tw = fmH.stringWidth(txt)
                tx = gx + (gw - tw) // 2
                ty = self._HeaderBaselineY(curY, headerH, fmH) - 2
                g2.drawString(txt, tx, ty)
                g2.setColor(BORDER_COLOR)
                g2.drawRect(gx, curY, gw, headerH)
                curY += headerH

            prH = int(g.PlatformRowHeight)
            for ci in range(int(g.ColCount)):
                cx = gx + ci * int(BASE_COL_W)
                g2.setColor(CELL_BG)
                g2.fillRect(cx, curY, int(BASE_COL_W), prH)
                g2.setColor(BORDER_COLOR)
                g2.drawRect(cx, curY, int(BASE_COL_W), prH)
                self._PaintPlatformTokensInCell(g2, cx, curY, int(BASE_COL_W), prH, g.PlatformTokens, gi, ci)
            curY += prH

            for row in (g.BodyRows or []):
                rowH = int(row.get("height", 0))
                rtype = str(row.get("type", "") or "")
                keyNorm = str(row.get("text", "") or "").strip().lower()
                lines = row.get("lines", [""])
                fontObj = AND_FONT if rtype == "and" else CELL_FONT

                for ci in range(int(g.ColCount)):
                    cx = gx + ci * int(BASE_COL_W)
                    g2.setColor(CELL_BG)
                    g2.fillRect(cx, curY, int(BASE_COL_W), rowH)
                    g2.setColor(BORDER_COLOR)
                    g2.drawRect(cx, curY, int(BASE_COL_W), rowH)
                    self.PaintCellText(g2, cx, curY, int(BASE_COL_W), rowH, lines, 0.0, fontObj)
                    st = self.Brightness.get(("row", gi, rtype, keyNorm, ci))
                    b = float(st.get("b", 0.0)) if st is not None else 0.0
                    if b > 0.001:
                        self.PaintCellText(g2, cx, curY, int(BASE_COL_W), rowH, lines, b, fontObj)
                curY += rowH

            g2.setColor(BORDER_COLOR)
            g2.drawRect(gx, y, gw, maxGroupH)
            gx += gw

        g2.setColor(CABINET_COLOR)
        g2.setStroke(GRID_STROKE)
        g2.drawRect(x, y, w, maxGroupH)

    def Cleanup(self, event=None):
        if getattr(self, "Cleaned", False):
            return
        self.Cleaned = True
        try:
            self.AnimTimer.stop()
        except:
            pass
        try:
            self.RefreshTimer.stop()
        except:
            pass
        try:
            if self._displayListener is not None:
                try:
                    TimeMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    DayMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    if TimetableMem is not None:
                        TimetableMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    if OverridesMem is not None:
                        OverridesMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    if DepartTPMem is not None:
                        DepartTPMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
        except:
            pass
        try:
            PAR.removePlatformListener(self._displayListener)
        except:
            pass


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------
PID_Lightbox = PIDLightboxConcourseWindow()
