
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
# Lightbox-style platform Passenger Information Display for JMRI 5.14
#
# <<PID-DISP-NAME: Lightbox platform destination indicator>>
# <<DESCRIPTION: A London Underground style destination indicator lightbox that shows the next (and optionally later) trains' destinations and vias>>
#
# User-configurable settings discovered by TASSetup.py (do not modify TASSetup.py):
# <<SETTING DESCRIPTION NUMBER: Number of forthcoming trains to show>>
# <<SETTING DESCRIPTION NUMBER: Show trains scheduled less than this many minutes in the future>>
# <<SETTING DESCRIPTION BOOLEAN: Only show trains whose platform has been allocated (requires platform allocation setup)>>
# <<SETTING DESCRIPTION BOOLEAN: Hide empty stock workings>>
#
# Notes on behaviour:
# - Destinations and vias are always faintly visible (unlit apertures), with brighter illumination when lit.
# - When 'Require platform allocation' is true, a train is shown only once it has an allocation in PlatformAllocationRegister.
#   In that case, lookahead minutes is ignored (allocation governs visibility).
# - When 'Require platform allocation' is false, lookahead minutes governs visibility (0 => always show the next N trains).
# - Row positions are fixed per timetable and sorted alphabetically for consistency.
# - For long destination/via text, wrap to multiple lines and expand the cell height (no mid-border line).
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

# ---------------------------
# EDT helper
# ---------------------------

def InvokeLater(fn):
    class _R(Runnable):
        def run(self):
            try:
                fn()
            except Exception as ex:
                try:
                    print("[PIDLightboxSingle] EDT invoke failed:", ex)
                except:
                    pass
    try:
        SwingUtilities.invokeLater(_R())
    except:
        try:
            fn()
        except:
            pass

# ---------------------------
# TAS user settings (via TASSetup.py)
# ---------------------------

def _SettingMemoryName(label):
    # Must match TASSetup.py memory naming so options affect this script.
    # key = re.sub(r"[^A-Za-z0-9]+", "_", label).upper()
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

# Defaults
DEFAULT_TRAINS_SHOWN = 2
DEFAULT_LOOKAHEAD_MIN = 10
DEFAULT_REQUIRE_ALLOC = False
DEFAULT_HIDE_ECS = False

# ---------------------------
# Theme / geometry
# ---------------------------

CABINET_COLOR = Color(0, 0, 0)
BORDER_COLOR = Color(0, 0, 0)

# Your chosen colours
HEADER_BG = Color(20, 20, 20)
HEADER_TEXT = Color(245, 245, 245)
CELL_BG = Color(34, 34, 34)
UNLIT_TEXT = Color(28, 28, 28)

# Warm white lit text
LIT_TEXT = Color(255, 230, 190)

CABINET_PAD = 10
CELL_PAD_X = 18
# Separate header and cell vertical padding so we can increase cell padding without making headers too tall.
HEADER_PAD_Y = 10
CELL_PAD_Y = 18
GRID_STROKE = BasicStroke(4.0)

HEADER_FONT_SIZE = 34
CELL_FONT_SIZE = 30

# Animation
ANIM_FPS_MS = 40
RISE_TAU_S = 0.06
FALL_TAU_S = 0.08

PERIODIC_REFRESH_MS = 60000

# ---------------------------
# Memories / fast clock
# ---------------------------

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

# ---------------------------
# Timetable access
# ---------------------------

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
            print("[PIDLightboxSingle] Failed to read timetable:", ex)
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

def DetectPlatforms():
    plats = set()
    for r in CsvRows():
        p = PlatformField(r)
        if p:
            plats.add(p)
    try:
        return sorted(plats, key=lambda x: (x.isdigit(), x))[::-1]
    except:
        try:
            return sorted(list(plats))
        except:
            return []

# ---------------------------
# Departure timing point logic
# ---------------------------

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
    # Return True iff ANY timing point has a timing tuple for (reportingNumber, dayName),
    # regardless of the logged minute. Treats the train as 'seen on the layout' today.
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
                rn = rec[0]; d = rec[3]
            except:
                continue
            if str(rn) == str(reportingNumber) and str(d) == str(dayName):
                return True
    return False

# ---------------------------
# Platform override helper
# ---------------------------

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

# ---------------------------
# Disruption-aware ordering
# ---------------------------

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

# ---------------------------
# Font selection
# ---------------------------

def AvailableFamilies():
    try:
        ge = GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []

def PickFamily():
    # Prefer Railway (Railway Sans) if present
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

def OrdinalWord(n):
    mapping = {1: "FIRST", 2: "SECOND", 3: "THIRD", 4: "FOURTH", 5: "FIFTH", 6: "SIXTH", 7: "SEVENTH", 8: "EIGHTH", 9: "NINTH", 10: "TENTH"}
    try:
        return mapping.get(int(n), str(int(n)) + "TH")
    except:
        return str(n) + "TH"

def IsEcsDestination(destUpper):
    try:
        s = str(destUpper or "").strip().upper()
        return s.startswith("EMPTY") or s.startswith("ECS")
    except:
        return False

# ---------------------------
# Painting panel
# ---------------------------

class LightboxPanel(swing.JPanel):
    def __init__(self, window):
        swing.JPanel.__init__(self)
        self.Window = window
        self.setOpaque(True)
        self.setBackground(CABINET_COLOR)

    def paintComponent(self, g):
        # Clear background explicitly (avoid calling JPanel.paintComponent)
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

# ---------------------------
# Property change listener (EDT safe)
# ---------------------------

class _PidPropertyChangeListener(beans.PropertyChangeListener):
    def __init__(self, callback):
        self._callback = callback

    def propertyChange(self, event):
        def _do():
            try:
                self._callback(event)
            except Exception as ex:
                try:
                    print("[PIDLightboxSingle] propertyChange callback failed:", ex)
                except:
                    pass
        InvokeLater(_do)

# ---------------------------
# Main per-platform window
# ---------------------------

class PIDWindow(object):
    def __init__(self, platform, onCloseCallback=None):
        self.Platform = str(platform)
        self.OnCloseCallback = onCloseCallback
        self.Cleaned = False

        self.NumTrains = DEFAULT_TRAINS_SHOWN
        self.LookAheadMin = DEFAULT_LOOKAHEAD_MIN
        self.RequireAlloc = DEFAULT_REQUIRE_ALLOC
        self.HideEcs = DEFAULT_HIDE_ECS

        self.Destinations = []
        self.Vias = []
        self.HasViaSection = False

        self.ModeSingleTrain = False
        self.ColCount = 2
        self.ColumnHeaders = []

        self.Brightness = {}
        self.RowLayouts = []
        self._lastAnimMs = None

        self.Frame = swing.JFrame("Destination indicator: platform " + self.Platform)
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
        # Labels must exactly match the <<SETTING DESCRIPTION ...>> lines in the header comments.
        self.NumTrains = ReadIntSetting("Number of forthcoming trains to show", DEFAULT_TRAINS_SHOWN, 1, 12)
        self.LookAheadMin = ReadIntSetting("Show trains scheduled less than this many minutes in the future", DEFAULT_LOOKAHEAD_MIN, 0, 240)
        self.RequireAlloc = ReadBoolSetting("Only show trains whose platform has been allocated (requires platform allocation setup)", DEFAULT_REQUIRE_ALLOC)
        self.HideEcs = ReadBoolSetting("Hide empty stock workings", DEFAULT_HIDE_ECS)

    def RebuildStaticLayout(self):
        self.ReadSettings()
        rows = CsvRows()
        profUpper = ActiveProfileNameUpper()

        destSet = set()
        viaSet = set()

        for r in rows:
            try:
                d = (r.get("Destination", "") or "").strip()
            except:
                d = ""
            if d:
                du = d.strip().upper()
                if bool(self.HideEcs) and IsEcsDestination(du):
                    du = ""
                if du:
                    if du == profUpper:
                        du = "THIS STATION"
                    destSet.add(du)

            try:
                v = (r.get("Via", "") or "").strip()
            except:
                v = ""
            if v and v.strip():
                viaSet.add(("VIA " + v.strip()).upper())

        self.Destinations = sorted(list(destSet), key=lambda s: str(s).upper())
        self.Vias = sorted(list(viaSet), key=lambda s: str(s).upper())
        self.HasViaSection = (len(self.Vias) > 0)

        self.ModeSingleTrain = (int(self.NumTrains) == 1)
        if self.ModeSingleTrain:
            self.ColCount = 2
            self.ColumnHeaders = ["NEXT TRAIN"]
        else:
            self.ColCount = int(self.NumTrains)
            self.ColumnHeaders = [OrdinalWord(i).upper() for i in range(self.ColCount, 0, -1)]

        self.ComputeGeometryAndResize()
        self.Brightness = {}
        self.InitBrightnessState()

    def _LineAdvance(self, fm):
        adv = fm.getAscent() + fm.getDescent()
        if adv <= 0:
            adv = fm.getHeight()
        if adv <= 0:
            adv = 1
        return int(adv)

    def ComputeGeometryAndResize(self):
        baseColW = 320
        if self.ModeSingleTrain:
            baseColW = 340

        contentW = self.ColCount * baseColW

        img = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
        g2 = img.createGraphics()
        try:
            g2.setFont(HEADER_FONT)
            fmH = g2.getFontMetrics(HEADER_FONT)
            headerH = fmH.getHeight() + (2 * HEADER_PAD_Y)

            g2.setFont(CELL_FONT)
            fmC = g2.getFontMetrics(CELL_FONT)
            lineAdvance = self._LineAdvance(fmC)

            # IMPORTANT:
            # The single-train display paints in two columns (left/right) with paired rows.
            # Height must be computed the same way, otherwise the window will be too tall.
            self.RowLayouts = []

            if self.ModeSingleTrain:
                colW = int(baseColW)
                maxTextW = colW - (2 * CELL_PAD_X)

                def RowHeightForPair(leftKey, rightKey):
                    maxLines = 1
                    if leftKey:
                        try:
                            leftLines = WrapTextLines(leftKey, fmC, maxTextW)
                            maxLines = max(maxLines, len(leftLines))
                        except:
                            pass
                    if rightKey:
                        try:
                            rightLines = WrapTextLines(rightKey, fmC, maxTextW)
                            maxLines = max(maxLines, len(rightLines))
                        except:
                            pass
                    return (2 * CELL_PAD_Y) + (maxLines * lineAdvance)

                bodyH = 0

                # Destinations: two columns, paired per row
                destLeft = self.Destinations[0::2]
                destRight = self.Destinations[1::2]
                rowsN = max(len(destLeft), len(destRight))
                for i in range(rowsN):
                    leftKey = destLeft[i] if i < len(destLeft) else ""
                    rightKey = destRight[i] if i < len(destRight) else ""
                    bodyH += RowHeightForPair(leftKey, rightKey)

                # Via section (optional): same pairing logic, plus spacer
                if self.HasViaSection and self.Vias:
                    bodyH += int(lineAdvance * 0.8)
                    viaLeft = self.Vias[0::2]
                    viaRight = self.Vias[1::2]
                    rowsN = max(len(viaLeft), len(viaRight))
                    for i in range(rowsN):
                        leftKey = viaLeft[i] if i < len(viaLeft) else ""
                        rightKey = viaRight[i] if i < len(viaRight) else ""
                        bodyH += RowHeightForPair(leftKey, rightKey)

            else:
                # Multi-train mode: one row per key, used directly by PaintContent()
                def addRowsForKeys(kind, keys):
                    for k in keys:
                        maxTextW = baseColW - (2 * CELL_PAD_X)
                        lines = WrapTextLines(k, fmC, maxTextW)
                        height = (2 * CELL_PAD_Y) + (len(lines) * lineAdvance)
                        self.RowLayouts.append({"type": kind, "key": k, "lines": lines, "height": height})

                addRowsForKeys("dest", self.Destinations)
                if self.HasViaSection:
                    self.RowLayouts.append({"type": "spacer", "key": "", "lines": [""], "height": int(lineAdvance * 0.8)})
                    addRowsForKeys("via", self.Vias)

                bodyH = sum([int(r["height"]) for r in self.RowLayouts])

            contentH = headerH + bodyH

        finally:
            try:
                g2.dispose()
            except:
                pass

        totalW = contentW + (2 * CABINET_PAD)
        totalH = contentH + (2 * CABINET_PAD)

        totalW = max(totalW, 520)
        totalH = max(totalH, 240)

        try:
            self.Panel.setPreferredSize(Dimension(int(totalW), int(totalH)))
            self.Frame.pack()
        except:
            try:
                self.Frame.setSize(int(totalW) + 40, int(totalH) + 60)
            except:
                pass

    def InitBrightnessState(self):
        if self.ModeSingleTrain:
            destLeft = self.Destinations[0::2]
            destRight = self.Destinations[1::2]
            for i, k in enumerate(destLeft):
                self.Brightness[("dest", 0, i)] = {"b": 0.0, "t": 0.0, "key": k}
            for i, k in enumerate(destRight):
                self.Brightness[("dest", 1, i)] = {"b": 0.0, "t": 0.0, "key": k}

            if self.HasViaSection and self.Vias:
                viaLeft = self.Vias[0::2]
                viaRight = self.Vias[1::2]
                for i, k in enumerate(viaLeft):
                    self.Brightness[("via", 0, i)] = {"b": 0.0, "t": 0.0, "key": k}
                for i, k in enumerate(viaRight):
                    self.Brightness[("via", 1, i)] = {"b": 0.0, "t": 0.0, "key": k}
        else:
            for k in self.Destinations:
                for c in range(self.ColCount):
                    self.Brightness[("dest", k, c)] = {"b": 0.0, "t": 0.0}
            for k in self.Vias:
                for c in range(self.ColCount):
                    self.Brightness[("via", k, c)] = {"b": 0.0, "t": 0.0}

    def _RowsToday(self, rows, dayName):
        out = []
        for r in rows:
            try:
                if (r.get(dayName, "") or "").strip().lower() == "true":
                    out.append(r)
            except:
                pass
        return out

    def _DisplayDestinationKey(self, destRawUpper, profUpper):
        if destRawUpper == profUpper:
            return "THIS STATION"
        return destRawUpper


    def GetNextTrains(self):
        rows = CsvRows()
        dayName = str(DayMem.getValue() or "").strip()
        nowMin = CurrentMinutes()
        if nowMin is None:
            return []
        rowsToday = self._RowsToday(rows, dayName)

        profUpper = ActiveProfileNameUpper()
        lookAhead = int(self.LookAheadMin)
        requireAlloc = bool(self.RequireAlloc)

        candidates = []

        for r in rowsToday:
            dep = (r.get("Dep", "") or "").strip()
            if dep == "":
                continue
            depMin = ParseTimeToMinutes(dep)
            if depMin is None:
                continue

            rn = (r.get("Reporting number", "") or "").strip()
            if rn == "":
                continue

            # Platform precedence: allocation > overrides > timetable column
            alloc = PAR.getPlatform(rn)
            hasAlloc = (alloc is not None and str(alloc).strip() != "")
            if hasAlloc:
                plat = str(alloc).strip()
            else:
                plat = GetPlatformOverride(rn) or PlatformField(r)
            if str(plat) != self.Platform:
                continue

            # If user requires allocation, skip non-allocated workings
            if requireAlloc and not hasAlloc:
                continue

            # Resolve delay with inheritance (PIDSmall rule)
            try:
                kind, val = ResolveDelayWithInheritance(rowsToday, rn, depMin, visited=set())
            except:
                kind, val = ("ontime", 0)

            # Skip cancellations in Lightbox (PIDSmall shows them with "CANCELLED" time;
            # Lightbox has no time field, so we keep cancellations hidden).
            if kind == "cancel":
                continue

            # Remove ONLY when logged as departed at configured timing points
            try:
                if HasDepartedAtConfiguredTP(rn, dayName, nowMin):
                    continue
            except:
                pass

            # Resilience filter copied from PIDSmall:
            # If no disruption AND no timing anywhere today for this RN,
            # do not show if booked departure is already in the past.
            if kind == "ontime":
                try:
                    direct = getDisruption(rn)
                except:
                    direct = None
                if (direct is None) and (not HasAnyTimingToday(rn, dayName)):
                    if depMin < nowMin:
                        continue

            # Effective minutes for ordering (disruption-aware)
            effMin = depMin
            if kind == "delay" and val and val > 0:
                try:
                    effMin = depMin + int(val)
                except:
                    effMin = depMin

            # Destination / Via keys (Lightbox display)
            dest = (r.get("Destination", "") or "").strip()
            destKey = (dest.upper() if dest else "")
            if destKey != "":
                if bool(self.HideEcs) and IsEcsDestination(destKey):
                    continue
                destKey = self._DisplayDestinationKey(destKey, profUpper)

            via = (r.get("Via", "") or "").strip()
            viaKey = ("VIA " + via).upper() if via else ""

            candidates.append({"effMin": effMin, "destKey": destKey, "viaKey": viaKey})

        # Apply lookahead ONLY as an upper bound when allocation is not required,
        # matching the Lightbox header semantics ("0 => show next N trains regardless of distance").
        if (not requireAlloc) and (lookAhead > 0):
            candidates = [c for c in candidates if c.get("effMin", 999999) <= (nowMin + lookAhead)]

        # Sort by effective minutes and emit the top N for the Lightbox columns
        candidates.sort(key=lambda t: t.get("effMin", 999999))
        out = []
        for c in candidates:
            out.append({"destKey": c.get("destKey", ""), "viaKey": c.get("viaKey", "")})
            if len(out) >= int(self.NumTrains):
                break
        return out


    def UpdateDisplay(self, event=None):
        oldNum = self.NumTrains
        oldHide = self.HideEcs
        self.ReadSettings()
        if int(self.NumTrains) != int(oldNum) or bool(self.HideEcs) != bool(oldHide):
            self.RebuildStaticLayout()

        try:
            if event is not None and (event.getSource() == TimetableMem):
                self.RebuildStaticLayout()
        except:
            pass

        trains = self.GetNextTrains()

        for st in self.Brightness.values():
            st["t"] = 0.0

        if self.ModeSingleTrain:
            t0 = trains[0] if trains else None
            destKey = t0.get("destKey", "") if t0 else ""
            viaKey = t0.get("viaKey", "") if t0 else ""
            for pos, st in self.Brightness.items():
                try:
                    secType, col, rowIdx = pos
                except:
                    continue
                if secType == "dest" and st.get("key") == destKey and destKey != "":
                    st["t"] = 1.0
                if secType == "via" and st.get("key") == viaKey and viaKey != "":
                    st["t"] = 1.0
        else:
            for i, t in enumerate(trains):
                col = (self.ColCount - 1 - i)
                if col < 0 or col >= self.ColCount:
                    continue
                destKey = t.get("destKey", "")
                viaKey = t.get("viaKey", "")
                if destKey:
                    st = self.Brightness.get(("dest", destKey, col))
                    if st is not None:
                        st["t"] = 1.0
                if viaKey:
                    st = self.Brightness.get(("via", viaKey, col))
                    if st is not None:
                        st["t"] = 1.0

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

    def PaintContent(self, g2, x, y, w, h):
        colW = int(w // self.ColCount)

        g2.setFont(HEADER_FONT)
        fmH = g2.getFontMetrics(HEADER_FONT)
        headerH = fmH.getHeight() + (2 * HEADER_PAD_Y)

        g2.setFont(CELL_FONT)
        fmC = g2.getFontMetrics(CELL_FONT)
        lineAdvance = self._LineAdvance(fmC)

        if self.ModeSingleTrain:
            g2.setColor(HEADER_BG)
            g2.fillRect(x, y, w, headerH)
            g2.setColor(HEADER_TEXT)
            g2.setFont(HEADER_FONT)
            txt = "NEXT TRAIN"
            tw = fmH.stringWidth(txt)
            tx = x + (w - tw) // 2
            ty = self._HeaderBaselineY(y, headerH, fmH) - 2
            g2.drawString(txt, tx, ty)

            g2.setColor(BORDER_COLOR)
            g2.setStroke(GRID_STROKE)
            g2.drawRect(x, y, w, headerH)

            CurYBox = [y + headerH]
            destLeft = self.Destinations[0::2]
            destRight = self.Destinations[1::2]

            def PaintTwoColSection(keysLeft, keysRight, kind):
                rowsN = max(len(keysLeft), len(keysRight))
                for i in range(rowsN):
                    leftKey = keysLeft[i] if i < len(keysLeft) else ""
                    rightKey = keysRight[i] if i < len(keysRight) else ""   

                    maxLines = 1
                    leftLines = [""]
                    rightLines = [""]
                    maxTextW = colW - (2 * CELL_PAD_X)
                    if leftKey:
                        leftLines = WrapTextLines(leftKey, fmC, maxTextW)
                        maxLines = max(maxLines, len(leftLines))
                    if rightKey:
                        rightLines = WrapTextLines(rightKey, fmC, maxTextW)
                        maxLines = max(maxLines, len(rightLines))

                    rowH = (2 * CELL_PAD_Y) + (maxLines * lineAdvance)

                    for colIdx, (cellKey, lines) in enumerate([(leftKey, leftLines), (rightKey, rightLines)]):
                        cx = x + (colIdx * colW)
                        g2.setColor(CELL_BG)
                        g2.fillRect(cx, CurYBox[0], colW, rowH)
                        g2.setColor(BORDER_COLOR)
                        g2.setStroke(GRID_STROKE)
                        g2.drawRect(cx, CurYBox[0], colW, rowH)

                        if cellKey:
                            self.PaintCellText(g2, cx, CurYBox[0], colW, rowH, lines, 0.0)
                            st = self.Brightness.get((kind, colIdx, i))
                            b = float(st.get("b", 0.0)) if st is not None else 0.0
                            if b > 0.001:
                                self.PaintCellText(g2, cx, CurYBox[0], colW, rowH, lines, b)

                    CurYBox[0] += rowH

            PaintTwoColSection(destLeft, destRight, "dest")

            if self.HasViaSection and self.Vias:
                CurYBox[0] += int(lineAdvance * 0.8)
                viaLeft = self.Vias[0::2]
                viaRight = self.Vias[1::2]
                PaintTwoColSection(viaLeft, viaRight, "via")

        else:
            g2.setFont(HEADER_FONT)
            for c in range(self.ColCount):
                cx = x + (c * colW)
                g2.setColor(HEADER_BG)
                g2.fillRect(cx, y, colW, headerH)
                g2.setColor(HEADER_TEXT)
                txt = self.ColumnHeaders[c]
                tw = fmH.stringWidth(txt)
                tx = cx + (colW - tw) // 2
                ty = self._HeaderBaselineY(y, headerH, fmH) - 2
                g2.drawString(txt, tx, ty)

                g2.setColor(BORDER_COLOR)
                g2.setStroke(GRID_STROKE)
                g2.drawRect(cx, y, colW, headerH)

            curY = y + headerH
            for row in self.RowLayouts:
                rtype = row["type"]
                if rtype == "spacer":
                    curY += int(row["height"])
                    continue

                key = row["key"]
                lines = row["lines"]
                rowH = int(row["height"])

                for c in range(self.ColCount):
                    cx = x + (c * colW)
                    g2.setColor(CELL_BG)
                    g2.fillRect(cx, curY, colW, rowH)
                    g2.setColor(BORDER_COLOR)
                    g2.setStroke(GRID_STROKE)
                    g2.drawRect(cx, curY, colW, rowH)

                    self.PaintCellText(g2, cx, curY, colW, rowH, lines, 0.0)
                    st = self.Brightness.get((rtype, key, c))
                    b = float(st.get("b", 0.0)) if st is not None else 0.0
                    if b > 0.001:
                        self.PaintCellText(g2, cx, curY, colW, rowH, lines, b)

                curY += rowH

        g2.setColor(CABINET_COLOR)
        g2.setStroke(GRID_STROKE)
        g2.drawRect(x, y, w, h)

    def PaintCellText(self, g2, x, y, w, h, lines, brightness):
        # Robust centering:
        # - Vertically: center each line's glyph bounds inside a line box, then center the block.
        # - Horizontally: center each line inside the cell using glyph bounds (with padding clamp).
        g2.setFont(CELL_FONT)
        fm = g2.getFontMetrics(CELL_FONT)
        frc = g2.getFontRenderContext()

        lineAdvance = self._LineAdvance(fm)
        n = max(1, len(lines))
        blockH = n * lineAdvance
        blockTop = y + (h - blockH) // 2

        # Precompute glyph bounds at (0,0) for each line.
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
                gv0 = CELL_FONT.createGlyphVector(frc, s)
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
                    gv = CELL_FONT.createGlyphVector(frc, s)
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

        def ScaleColor(c, mult):
            r = int(min(255, max(0, int(c.getRed() * mult))))
            g = int(min(255, max(0, int(c.getGreen() * mult))))
            bl = int(min(255, max(0, int(c.getBlue() * mult))))
            return Color(r, g, bl)

        colors = [ScaleColor(LIT_TEXT, 0.25 + 0.75 * bval), ScaleColor(LIT_TEXT, 0.05 * bval)]
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
                gv = CELL_FONT.createGlyphVector(frc, s)
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
        try:
            if self.OnCloseCallback is not None:
                self.OnCloseCallback(self.Platform)
        except:
            pass

# ---------------------------
# Manager: one window per platform
# ---------------------------

class PlatformPIDManager(object):
    def __init__(self):
        self.Windows = {}
        if TimetableMem is not None:
            try:
                TimetableMem.addPropertyChangeListener(self.OnTimetableChanged)
            except:
                pass
        try:
            PAR.addPlatformListener(_PidPropertyChangeListener(self.OnTimetableChanged))
        except:
            pass
        self.BuildWindows()

    def BuildWindows(self):
        plats = DetectPlatforms()
        for p in plats:
            if p not in self.Windows:
                self.Windows[p] = PIDWindow(p, self.OnWindowClosed)

        toRemove = [p for p in self.Windows.keys() if p not in plats]
        for p in toRemove:
            try:
                self.Windows[p].Cleanup()
                self.Windows[p].Frame.dispose()
            except:
                pass
            try:
                del self.Windows[p]
            except:
                pass

        x0, y0 = 50, 50
        dx, dy = 40, 40
        idx = 0
        try:
            sortedKeys = sorted(self.Windows.keys(), key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s))
        except:
            sortedKeys = list(self.Windows.keys())
        for p in sortedKeys:
            try:
                self.Windows[p].Frame.setLocation(x0 + dx * idx, y0 + dy * idx)
            except:
                pass
            idx += 1

    def OnTimetableChanged(self, event=None):
        self.BuildWindows()
        self.RefreshAll()

    def RefreshAll(self):
        for w in self.Windows.values():
            try:
                w.UpdateDisplay()
            except:
                pass

    def OnWindowClosed(self, platform):
        try:
            if platform in self.Windows:
                del self.Windows[platform]
        except:
            pass

# ---------------------------
# Run
# ---------------------------

PID_Manager = PlatformPIDManager()
