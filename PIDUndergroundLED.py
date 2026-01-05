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
# Underground-style small electronic board PID (per platform) for JMRI 5.14
#
# <<PID-DISP-NAME: Underground LED 2-line platform display>>
# <<DESCRIPTION: Two-line LED destination indicator of the type introduced by the London Underground in the 1980s>>
#
# User-configurable settings discovered by TASSetup.py (do not modify TASSetup.py):
# <<SETTING DESCRIPTION NUMBER: Show trains scheduled less than this many minutes in the future>>
# <<SETTING DESCRIPTION NUMBER: Lower line cycle seconds>>
# <<SETTING DESCRIPTION BOOLEAN: Enable special message>>
# <<SETTING DESCRIPTION NUMBER: Special message every N minutes>>
# <<SETTING DESCRIPTION NUMBER: Special message blank min seconds>>
# <<SETTING DESCRIPTION NUMBER: Special message blank max seconds>>
# <<SETTING DESCRIPTION NUMBER: Special message wipe duration ms>>
# <<SETTING DESCRIPTION NUMBER: Board width pixels>>
# <<SETTING DESCRIPTION NUMBER: Board height pixels>>
#
# Notes:
# - Per platform: one window per platform found in the timetable
# - Time window: shows next 3 trains where expected departure <= now + lookAhead
# - Expected times: uses same delay + formation inheritance + depart-at-TP logic as PIDSmall.py
# - Lower line alternates between 2nd and 3rd trains using a slide-up clipped transition
# - Periodic special message replaces lower line, with blank pause + wipe in/out + 2 Hz flashing
# - No calling patterns shown
# - Vias are read from "Via" column (case-insensitive); if blank/missing, omit
# - Unlit LEDs are not shown (background always plain black)
#
# Jython 2.7 / ASCII only / CamelCase / Thread-safe EDT

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, RenderingHints, BasicStroke, Dimension, GradientPaint, GraphicsEnvironment
from java.awt.geom import RoundRectangle2D
from java.awt.image import BufferedImage
from javax.swing import Timer
from javax.swing import SwingUtilities
from java.lang import Runnable, System
import java.beans as beans
import java.text.SimpleDateFormat as SimpleDateFormat
import jmri
from jmri import InstanceManager
import os, csv, math

from DisruptionRegister import getDisruption
import TimingRegister as TR
import TASBeanLookup as TBL
import PlatformAllocationRegister as PAR


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
                    print("[PIDUndergroundLED] EDT invoke failed:", ex)
                except:
                    pass
    try:
        SwingUtilities.invokeLater(_R())
    except:
        try:
            fn()
        except:
            pass


class _PidPropertyChangeListener(beans.PropertyChangeListener):
    def __init__(self, callback):
        self._callback = callback

    def propertyChange(self, event):
        def _do():
            try:
                self._callback(event)
            except Exception as ex:
                try:
                    print("[PIDUndergroundLED] propertyChange callback failed:", ex)
                except:
                    pass
        InvokeLater(_do)


# ------------------------------------------------------------
# TAS user settings (via TASSetup.py)
# ------------------------------------------------------------
def _SettingMemoryName(label):
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
# Memories / fast clock
# ------------------------------------------------------------
TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")
SpecialMsgMem = TBL.ProvideMemoryBySuffix("PID_SPECIAL_MESSAGE", "** NO SMOKING **")

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
                try:
                    rows.append(r)
                except:
                    pass
    except Exception as ex:
        try:
            print("[PIDUndergroundLED] Failed to read timetable:", ex)
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


def DetectPlatforms(rowsAll):
    plats = []
    seen = set()
    for r in (rowsAll or []):
        p = PlatformField(r)
        if not p:
            continue
        if p in seen:
            continue
        seen.add(p)
        plats.append(p)

    def _SortKey(s):
        try:
            if str(s).isdigit():
                return (0, int(s))
        except:
            pass
        return (1, str(s))

    try:
        plats.sort(key=_SortKey)
    except:
        pass
    return plats


# ------------------------------------------------------------
# Platform overrides
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
# Departure timing point logic
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
# Delay resolution with inheritance (Forms)
# Returns ("cancel", None) / ("delay", minutes>0) / ("ontime", 0)
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
    for r in (rowsToday or []):
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
# Collect next 3 trains for a platform within look-ahead
# ------------------------------------------------------------
def _RowsToday(rowsAll, dayName):
    out = []
    for r in (rowsAll or []):
        try:
            if (r.get(dayName, "") or "").strip().lower() == "true":
                out.append(r)
        except:
            pass
    return out


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


def _NormalizeSpaces(s):
    try:
        import re as _re
        return _re.sub(r"\s+", " ", str(s or "")).strip()
    except:
        return (s or "").strip()


def CollectUpcomingForPlatform(rowsAll, platformStr, dayName, nowMin, lookAheadMin):
    if nowMin is None:
        return []

    rowsToday = _RowsToday(rowsAll, dayName)
    profUpper = ActiveProfileNameUpper()

    try:
        la = int(lookAheadMin)
    except:
        la = 0
    upper = int(nowMin) + int(la) if la > 0 else None

    out = []
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
        if str(plat) != str(platformStr):
            continue

        try:
            kind, val = ResolveDelayWithInheritance(rowsToday, rn, depMin, visited=set())
        except:
            kind, val = ("ontime", 0)

        if kind == "cancel":
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

        try:
            if HasDepartedAtConfiguredTP(rn, dayName, nowMin):
                continue
        except:
            pass

        try:
            direct = getDisruption(rn)
        except:
            direct = None
        if (direct is None) and (kind == "ontime") and (not HasAnyTimingToday(rn, dayName)):
            if depMin < nowMin:
                continue

        destRaw = (r.get("Destination", "") or "").strip()
        destUpper = destRaw.upper() if destRaw else ""
        destKey = "THIS STATION" if destUpper == profUpper else destUpper

        viaRaw = _NormalizeSpaces(CaseInsensitive(r, "Via"))
        if viaRaw:
            leftText = "%s via %s" % (destKey, viaRaw)
        else:
            leftText = "%s" % (destKey,)

        out.append({
            "rn": rn,
            "depMin": depMin,
            "effMin": effMin,
            "destVia": leftText
        })

    out.sort(key=lambda t: t.get("effMin", 999999))
    return out[:3]


# ------------------------------------------------------------
# Rendering constants
# ------------------------------------------------------------
ORANGE = Color(255, 165, 40)
FACE_BLACK = Color(0, 0, 0)
CASE_DARK = Color(28, 28, 28)
CASE_DARK2 = Color(18, 18, 18)
RED_LINE = Color(180, 20, 20)

# Font
# Use the same font selection hierarchy as PIDLightboxSingle.py.
def AvailableFamilies():
    try:
        ge = GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []

def PickFamily():
    # Prefer Johnston/Railway style if present; otherwise fall back safely.
    prefs = ["LED Dot-Matrix", "SansSerif"]
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
FONT_MAIN = Font(FONT_FAM, Font.PLAIN, 44)
FONT_MINS = Font(FONT_FAM, Font.PLAIN, 26)
FONT_SPECIAL = Font(FONT_FAM, Font.PLAIN, 44)
PAD_X = 26

# Animation speed adjustment: requested ~60% of previous speed => duration / 0.6
ANIM_SLOW_FACTOR = 1.0 / 0.6
SLIDE_MS = int(round(400.0 * ANIM_SLOW_FACTOR))


def _RowCenterBaseline(y, h, fm):
    # Standard vertical centering for a single-line text block
    return int(y + (h - fm.getHeight()) // 2 + fm.getAscent())

# Font metrics helpers
# Different fonts (especially dot-matrix bitmap-style fonts) can have very different
# ascent/descent/leading, so fm.getHeight() centering can look wrong.
# These helpers center based on the actual glyph outline bounds for the specific text.
def _GlyphBounds2D(fontObj, frc, text):
    try:
        s = str(text or '')
    except:
        s = ''
    try:
        gv = fontObj.createGlyphVector(frc, s)
        return gv.getOutline(0.0, 0.0).getBounds2D()
    except:
        return None

def _CenteredBaselineY(g2, y, h, fontObj, text):
    # Return a baseline Y such that the *glyph outline* is vertically centered inside (y,h).
    # Falls back to FontMetrics centering if glyph bounds are unavailable.
    try:
        frc = g2.getFontRenderContext()
    except:
        frc = None
    if frc is not None:
        b = _GlyphBounds2D(fontObj, frc, text)
        if b is not None:
            try:
                gh = float(b.getHeight())
                by = float(b.getY())
                if gh > 0.0:
                    # Want top of glyph at y + (h-gh)/2
                    return float(y) + (float(h) - gh) / 2.0 - by
            except:
                pass
    try:
        fm = g2.getFontMetrics(fontObj)
        return float(_RowCenterBaseline(int(y), int(h), fm))
    except:
        return float(y) + float(h) * 0.75

def _CenteredXForBounds(x, w, bounds2d):
    # Return an x origin for drawing a glyph outline so that its bounds are centered in (x,w).
    try:
        if bounds2d is None:
            return float(x)
        bw = float(bounds2d.getWidth())
        bx = float(bounds2d.getX())
        return float(x) + (float(w) - bw) / 2.0 - bx
    except:
        return float(x)

# ------------------------------------------------------------
# Panel
# ------------------------------------------------------------
class LedBoardPanel(swing.JPanel):
    def __init__(self, window):
        swing.JPanel.__init__(self)
        self.Window = window
        self.setOpaque(True)
        self.setBackground(Color(0, 0, 0))

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            self.Window.Paint(g2, self.getWidth(), self.getHeight())
        finally:
            try:
                g2.dispose()
            except:
                pass


# ------------------------------------------------------------
# Per-platform PID window/controller
# ------------------------------------------------------------
class PIDUndergroundLedWindow(object):
    def __init__(self, platformStr, onCloseCallback=None):
        self.Platform = str(platformStr)
        self.OnCloseCallback = onCloseCallback
        self.Cleaned = False

        # Settings
        self.LookAheadMin = 10
        self.CycleSeconds = 5
        self.SpecialEnabled = True
        self.SpecialEveryNMinutes = 1
        self.SpecialBlankMinS = 1
        self.SpecialBlankMaxS = 2
        self.SpecialWipeMs = 800
        self.BoardW = 1200
        self.BoardH = 200

        # State
        self.Services = []
        self.LastNowMin = None
        self.LastDayName = None

        # Bottom cycling: 1 means show train #2; 2 means show train #3
        self.BottomShowingIndex = 1
        self.BottomNextIndex = 2

        # Cycle timing
        self.LastCycleMs = 0

        # Special scheduling
        self.SpecialPending = False
        self.LastSpecialShownMinute = None

        # Animation state machine
        self.Mode = "NORMAL"  # NORMAL, SLIDE, BLANK, WIPE_IN, SPECIAL, WIPE_OUT
        self.SlidePhase = 0.0
        self.ModeStartMs = 0
        self.BlankDurationMs = 0
        self.WipeFrac = 0.0

        # Flash
        self.FlashOn = True
        self.LastFlashToggleMs = 0

        # UI
        self.Frame = swing.JFrame("Underground PID: platform " + self.Platform)
        self.Frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        self.Frame.setResizable(False)

        self.Panel = LedBoardPanel(self)
        self.Frame.setContentPane(self.Panel)

        self.ReadSettings()
        self.Panel.setPreferredSize(Dimension(int(self.BoardW), int(self.BoardH)))
        self.Frame.pack()

        # Listener
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

        # Ensure updates on fast clock minute changes
        self._timebaseMinuteListenerAdded = False
        try:
            if Timebase is not None:
                Timebase.addMinuteChangeListener(self._displayListener)
                self._timebaseMinuteListenerAdded = True
        except:
            pass

        # Timers
        self.AnimTimer = Timer(40, self.OnAnimTick)
        self.AnimTimer.start()

        self.UpdateDisplay()

        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(inner_self, e):
                self.Cleanup(e)
            def windowClosed(inner_self, e):
                self.Cleanup(e)
        self.Frame.addWindowListener(CloseHandler())

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.Frame, 32)
        except:
            pass

        self.Frame.setVisible(True)

    def ReadSettings(self):
        self.LookAheadMin = ReadIntSetting("Show trains scheduled less than this many minutes in the future", 10, 0, 240)
        self.CycleSeconds = ReadIntSetting("Lower line cycle seconds", 5, 2, 60)
        self.SpecialEnabled = ReadBoolSetting("Enable special message", True)
        self.SpecialEveryNMinutes = ReadIntSetting("Special message every N minutes", 1, 1, 60)
        self.SpecialBlankMinS = ReadIntSetting("Special message blank min seconds", 1, 0, 10)
        self.SpecialBlankMaxS = ReadIntSetting("Special message blank max seconds", 2, 0, 10)
        self.SpecialWipeMs = ReadIntSetting("Special message wipe duration ms", 800, 100, 5000)

        self.BoardW = ReadIntSetting("Board width pixels", 1200, 400, 4000)
        self.BoardH = ReadIntSetting("Board height pixels", 180, 120, 1200)

        try:
            self.Panel.setPreferredSize(Dimension(int(self.BoardW), int(self.BoardH)))
            self.Frame.pack()
        except:
            pass

    def _ResetCycleState(self):
        self.Mode = "NORMAL"
        self.SlidePhase = 0.0
        self.WipeFrac = 0.0
        self.FlashOn = True
        self.LastFlashToggleMs = 0
        self.ModeStartMs = 0
        self.BlankDurationMs = 0
        self.LastCycleMs = 0
        self.BottomShowingIndex = 1
        self.BottomNextIndex = 2
        self.SpecialPending = False

    def UpdateDisplay(self, event=None):
        self.ReadSettings()

        rowsAll = CsvRows()
        dayName = str(DayMem.getValue() or "").strip()
        nowMin = CurrentMinutes()
        if nowMin is None:
            try:
                self.Panel.repaint()
            except:
                pass
            return

        # Detect time warps backwards and reset animation state
        try:
            if self.LastDayName is not None and str(dayName) != str(self.LastDayName):
                self._ResetCycleState()
            elif self.LastNowMin is not None:
                lastMin = int(self.LastNowMin)
                thisMin = int(nowMin)
                wrapForward = (lastMin >= 1380 and thisMin <= 60)
                if (thisMin < lastMin) and (not wrapForward):
                    self._ResetCycleState()
        except:
            pass

        self.LastNowMin = nowMin
        self.LastDayName = dayName

        self.Services = CollectUpcomingForPlatform(rowsAll, self.Platform, dayName, nowMin, int(self.LookAheadMin))

        # Schedule special message (pending) once per N minutes
        if self.SpecialEnabled:
            try:
                curMinute = int(nowMin)
                if (curMinute % int(self.SpecialEveryNMinutes)) == 0:
                    if self.LastSpecialShownMinute is None or int(self.LastSpecialShownMinute) != curMinute:
                        self.SpecialPending = True
            except:
                pass

        try:
            self.Panel.repaint()
        except:
            pass

    def _TopRowText(self):
        if not self.Services or len(self.Services) < 1:
            return ("", None)
        s = self.Services[0]
        left = "1 " + str(s.get("destVia", "") or "")
        mins = None
        try:
            nowMin = int(self.LastNowMin) if self.LastNowMin is not None else None
            effMin = int(s.get("effMin", 0))
            if nowMin is not None:
                dm = effMin - nowMin
                if dm > 0:
                    mins = int(dm)
        except:
            mins = None
        return (left, mins)

    def _BottomCandidate(self, whichIdx):
        if not self.Services:
            return ("", None)
        idx = 1 if whichIdx == 1 else 2
        if len(self.Services) <= idx:
            return ("", None)
        s = self.Services[idx]
        prefix = "2 " if idx == 1 else "3 "
        left = prefix + str(s.get("destVia", "") or "")
        mins = None
        try:
            nowMin = int(self.LastNowMin) if self.LastNowMin is not None else None
            effMin = int(s.get("effMin", 0))
            if nowMin is not None:
                dm = effMin - nowMin
                if dm > 0:
                    mins = int(dm)
        except:
            mins = None
        return (left, mins)

    def _SpecialText(self):
        try:
            t = SpecialMsgMem.getValue()
        except:
            t = None
        msg = str(t if t is not None else "** NO SMOKING **")
        msg = _NormalizeSpaces(msg)
        if msg == "":
            msg = "** NO SMOKING **"
        return msg

    def OnAnimTick(self, event):
        nowMs = System.currentTimeMillis()

        # Flash at 2 Hz when special is displayed (toggle every 250ms)
        if self.Mode in ["WIPE_IN", "SPECIAL", "WIPE_OUT"]:
            if self.LastFlashToggleMs == 0:
                self.LastFlashToggleMs = nowMs
            if (nowMs - self.LastFlashToggleMs) >= 250:
                self.FlashOn = (not self.FlashOn)
                self.LastFlashToggleMs = nowMs

        # Initialize cycle timer
        if self.LastCycleMs == 0:
            self.LastCycleMs = nowMs

        cycleDue = (nowMs - self.LastCycleMs) >= int(self.CycleSeconds) * 1000

        if self.Mode == "NORMAL":
            if cycleDue:
                if self.SpecialPending:
                    try:
                        self.LastSpecialShownMinute = int(self.LastNowMin) if self.LastNowMin is not None else None
                    except:
                        self.LastSpecialShownMinute = None
                    self.SpecialPending = False

                    self.Mode = "SLIDE"
                    self.ModeStartMs = nowMs
                    self.SlidePhase = 0.0
                    self.SlideFromText = self._BottomCandidate(self.BottomShowingIndex)
                    self.SlideToText = ("", None)
                else:
                    if len(self.Services) >= 3:
                        self.BottomNextIndex = 2 if self.BottomShowingIndex == 1 else 1
                    else:
                        self.BottomNextIndex = self.BottomShowingIndex

                    self.Mode = "SLIDE"
                    self.ModeStartMs = nowMs
                    self.SlidePhase = 0.0
                    self.SlideFromText = self._BottomCandidate(self.BottomShowingIndex)
                    self.SlideToText = self._BottomCandidate(self.BottomNextIndex)

        elif self.Mode == "SLIDE":
            dur = float(SLIDE_MS)
            t = float(nowMs - self.ModeStartMs)
            self.SlidePhase = max(0.0, min(1.0, t / dur))
            if self.SlidePhase >= 1.0:
                if self.SlideToText[0] == "" and self.SlideFromText[0] != "":
                    self.Mode = "BLANK"
                    self.ModeStartMs = nowMs
                    bmin = int(self.SpecialBlankMinS) * 1000
                    bmax = int(self.SpecialBlankMaxS) * 1000
                    if bmax < bmin:
                        bmax = bmin
                    if bmax == bmin:
                        self.BlankDurationMs = bmin
                    else:
                        self.BlankDurationMs = bmin + int((nowMs % 997) * (bmax - bmin) / 996)
                else:
                    self.BottomShowingIndex = self.BottomNextIndex
                    self.Mode = "NORMAL"
                    self.LastCycleMs = nowMs

        elif self.Mode == "BLANK":
            if (nowMs - self.ModeStartMs) >= int(self.BlankDurationMs):
                self.Mode = "WIPE_IN"
                self.ModeStartMs = nowMs
                self.WipeFrac = 0.0
                self.FlashOn = True
                self.LastFlashToggleMs = nowMs

        elif self.Mode == "WIPE_IN":
            dur = max(100.0, float(self.SpecialWipeMs) * ANIM_SLOW_FACTOR)
            t = float(nowMs - self.ModeStartMs)
            self.WipeFrac = max(0.0, min(1.0, t / dur))
            if self.WipeFrac >= 1.0:
                self.Mode = "SPECIAL"
                self.ModeStartMs = nowMs
                self.LastCycleMs = nowMs

        elif self.Mode == "SPECIAL":
            if (nowMs - self.ModeStartMs) >= int(self.CycleSeconds) * 1000:
                self.Mode = "WIPE_OUT"
                self.ModeStartMs = nowMs
                self.WipeFrac = 1.0
                self.LastFlashToggleMs = nowMs

        elif self.Mode == "WIPE_OUT":
            dur = max(100.0, float(self.SpecialWipeMs) * ANIM_SLOW_FACTOR)
            t = float(nowMs - self.ModeStartMs)
            self.WipeFrac = max(0.0, min(1.0, 1.0 - (t / dur)))
            if self.WipeFrac <= 0.0:
                self.Mode = "SLIDE"
                self.ModeStartMs = nowMs
                self.SlidePhase = 0.0
                self.SlideFromText = ("", None)
                self.SlideToText = self._BottomCandidate(self.BottomShowingIndex)
                self.LastCycleMs = nowMs

        try:
            self.Panel.repaint()
        except:
            pass

    def _DrawRow(self, g2, x, y, w, h, leftText, minsVal):

        # Draw one row: left text + right minutes (number big + MINS. small aligned to row bottom)

        if leftText is None:

            leftText = ''

        leftText = str(leftText)

        minsNumText = ''

        minsSuffixText = ''

        if minsVal is not None:

            try:

                mv = int(minsVal)

            except:

                mv = None

            if mv is not None and mv > 0:

                minsNumText = str(mv)

                minsSuffixText = 'MINS.'

        g2.setColor(ORANGE)


        # Left text - center using glyph bounds to handle fonts with unusual ascent/leading.

        g2.setFont(FONT_MAIN)

        baseLeft = _CenteredBaselineY(g2, float(y), float(h), FONT_MAIN, leftText)

        g2.drawString(leftText, int(x + PAD_X), int(round(baseLeft)))


        # Right minutes: align number vertically with the left text, then align suffix

        # so that its glyph bottom matches the number glyph bottom.

        if minsNumText:

            rightPad = 18

            fmNum = g2.getFontMetrics(FONT_MAIN)

            fmSuf = g2.getFontMetrics(FONT_MINS)

            numW = fmNum.stringWidth(minsNumText)

            sufW = fmSuf.stringWidth(minsSuffixText)

            gap = 10

            blockRight = int(x + w - rightPad)

            sufX = int(blockRight - sufW)

            numX = int(sufX - gap - numW)


            g2.setFont(FONT_MAIN)

            baseNum = _CenteredBaselineY(g2, float(y), float(h), FONT_MAIN, minsNumText)

            try:

                frc = g2.getFontRenderContext()

                bNum = _GlyphBounds2D(FONT_MAIN, frc, minsNumText)

                bSuf = _GlyphBounds2D(FONT_MINS, frc, minsSuffixText)

                if bNum is not None and bSuf is not None:

                    bottomOffNum = float(bNum.getY()) + float(bNum.getHeight())

                    bottomOffSuf = float(bSuf.getY()) + float(bSuf.getHeight())

                    bottomY = float(baseNum) + bottomOffNum

                    baseSuf = bottomY - bottomOffSuf

                else:

                    baseSuf = float(baseNum) + float(fmNum.getDescent()) - float(fmSuf.getDescent())

            except:

                baseSuf = float(baseNum) + float(fmNum.getDescent()) - float(fmSuf.getDescent())


            g2.setFont(FONT_MAIN)

            g2.drawString(minsNumText, int(numX), int(round(baseNum)))

            g2.setFont(FONT_MINS)

            g2.drawString(minsSuffixText, int(sufX), int(round(baseSuf)))

    def Paint(self, g2, w, h):
        # Plain black background
        g2.setColor(FACE_BLACK)
        g2.fillRect(0, 0, w, h)
        inset = 8
        caseX = inset
        caseY = inset
        caseW = w - 2 * inset
        caseH = h - 2 * inset

        # Squarer ends
        arcOuter = int(min(caseH * 0.45, 70))

        rr = RoundRectangle2D.Float(float(caseX), float(caseY), float(caseW), float(caseH), float(arcOuter), float(arcOuter))
        g2.setColor(CASE_DARK2)
        g2.fill(rr)

        rr2 = RoundRectangle2D.Float(float(caseX + 4), float(caseY + 4), float(caseW - 8), float(caseH - 8), float(arcOuter), float(arcOuter))
        g2.setColor(CASE_DARK)
        g2.fill(rr2)

        # Face (outer frame)
        faceX = caseX + 12
        faceY = caseY + 12
        faceW = caseW - 24
        faceH = caseH - 24
        arcFace = int(min(faceH * 0.35, 55))

        rrFace = RoundRectangle2D.Float(float(faceX), float(faceY), float(faceW), float(faceH), float(arcFace), float(arcFace))
        g2.setColor(FACE_BLACK)
        g2.fill(rrFace)

        # Red border matches the outer face frame
        g2.setColor(RED_LINE)
        g2.setStroke(BasicStroke(2.0))
        rrRed = RoundRectangle2D.Float(float(faceX + 2), float(faceY + 2), float(faceW - 4), float(faceH - 4), float(arcFace), float(arcFace))
        g2.draw(rrRed)

        # Bevel between the red border and the inner text box (subtle chamfer effect)
        # The previous implementation used a single GradientPaint across the whole area, which
        # makes the bevel appear to fade out toward one side. The prototype bevel is uniform.
        # Here we render a constant-tone bevel ring with two subtle outline strokes.
        bevelT = 6  # bevel thickness in pixels
        bevelOuterX = faceX + 4
        bevelOuterY = faceY + 4
        bevelOuterW = faceW - 8
        bevelOuterH = faceH - 8
        bevelArc = int(max(0, arcFace - 2))
        rrBevelOuter = RoundRectangle2D.Float(float(bevelOuterX), float(bevelOuterY), float(bevelOuterW), float(bevelOuterH), float(bevelArc), float(bevelArc))

        # Solid bevel tone (no directional fade)
        g2.setColor(Color(18, 18, 18))
        g2.fill(rrBevelOuter)

        # Outer highlight line (subtle)
        g2.setColor(Color(38, 38, 38))
        g2.setStroke(BasicStroke(1.5))
        g2.draw(rrBevelOuter)
        # Inner text box (actual black display area)
        textX = bevelOuterX + bevelT
        textY = bevelOuterY + bevelT
        textW = bevelOuterW - 2 * bevelT
        textH = bevelOuterH - 2 * bevelT
        textArc = int(max(0, bevelArc - 6))
        rrText = RoundRectangle2D.Float(float(textX), float(textY), float(textW), float(textH), float(textArc), float(textArc))
        g2.setColor(FACE_BLACK)
        g2.fill(rrText)

        # Inner edge line to suggest bevel depth (subtle)
        g2.setColor(Color(8, 8, 8))
        g2.setStroke(BasicStroke(1.0))
        g2.draw(rrText)
        # Two text rows
        # Forensic note: the large visible gap is mainly from each row being half the face height
        # (rowH ~= (faceH-rowGap)/2) combined with vertical centering of the text within that tall row.
        # So changing rowGap alone cannot fix the observed spacing.
        # We instead size rows from the font metrics and center the two-row block within the face.
        # Row spacing: choose a larger gap for dot-matrix fonts, and a tighter gap for outline fonts.
        # This is font-dependent: dot-matrix fonts often report small/odd leading and tall glyph bounds.
        fmMain = g2.getFontMetrics(FONT_MAIN)
        try:
            adv = int(fmMain.getAscent() + fmMain.getDescent())
        except:
            adv = int(fmMain.getHeight())
        try:
            lead = int(fmMain.getHeight()) - int(adv)
        except:
            lead = 0
        if lead < 0:
            lead = 0
        rowH = int(adv)
        if rowH < 12:
            rowH = 12
        
        # Identify dot-matrix style fonts by family name.
        isMatrixFont = False
        try:
            famLower = str(FONT_FAM or '').lower()
            if ('dot' in famLower) or ('matrix' in famLower) or ('led' in famLower):
                isMatrixFont = True
        except:
            isMatrixFont = False
        
        # Parameter sets: increased differential between dot-matrix and outline fonts.
        if isMatrixFont:
            leadMult = 0.85
            targetSlack = 12.0
            extraMult = 0.90
            minGap = 7
            maxGap = 20
        else:
            leadMult = 0.18
            targetSlack = 3.0
            extraMult = 0.20
            minGap = 1
            maxGap = 8
        
        extraGap = 0
        try:
            frc = g2.getFontRenderContext()
            sample = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            b = _GlyphBounds2D(FONT_MAIN, frc, sample)
            if b is not None:
                glyphH = float(b.getHeight())
                slack = float(rowH) - float(glyphH)
                if slack < 0.0:
                    slack = 0.0
                if slack < float(targetSlack):
                    extraGap = int(round((float(targetSlack) - slack) * float(extraMult)))
        except:
            extraGap = 0
        
        rowGap = int(round(float(lead) * float(leadMult))) + int(extraGap)
        if rowGap < int(minGap):
            rowGap = int(minGap)
        if rowGap > int(maxGap):
            rowGap = int(maxGap)
        blockH = (2 * rowH) + rowGap
        blockTop = int(textY + (textH - blockH) // 2)
        topY = blockTop
        botY = blockTop + rowH + rowGap

        # Top row fixed
        topLeft, topMins = self._TopRowText()
        self._DrawRow(g2, int(textX), int(topY), int(textW), int(rowH), topLeft, topMins)

        # Bottom row clipped for slide-up
        clip = g2.getClip()
        g2.clipRect(int(textX), int(botY), int(textW), int(rowH))

        if self.Mode == "NORMAL":
            bLeft, bMins = self._BottomCandidate(self.BottomShowingIndex)
            self._DrawRow(g2, int(textX), int(botY), int(textW), int(rowH), bLeft, bMins)

        elif self.Mode == "SLIDE":
            phase = float(self.SlidePhase)
            dy = int(round(-phase * float(rowH)))
            fromLeft, fromMins = self.SlideFromText
            toLeft, toMins = self.SlideToText

            if fromLeft or fromMins is not None:
                self._DrawRow(g2, int(textX), int(botY + dy), int(textW), int(rowH), fromLeft, fromMins)

            if toLeft or toMins is not None:
                self._DrawRow(g2, int(textX), int(botY + dy + rowH), int(textW), int(rowH), toLeft, toMins)

        elif self.Mode == "BLANK":
            pass

        elif self.Mode in ["WIPE_IN", "SPECIAL", "WIPE_OUT"]:
            # Flash off => draw nothing
            if self.FlashOn:
                msg = self._SpecialText()
                frac = float(self.WipeFrac)
                if self.Mode == "SPECIAL":
                    frac = 1.0
                if frac < 0.0:
                    frac = 0.0
                if frac > 1.0:
                    frac = 1.0

                wipeW = int(round(float(textW) * frac))
                oldClip = g2.getClip()
                g2.clipRect(int(textX), int(botY), int(wipeW), int(rowH))

                g2.setColor(ORANGE)
                g2.setFont(FONT_SPECIAL)
                # Center special message using glyph bounds (better for dot-matrix fonts)
                try:
                    frc = g2.getFontRenderContext()
                    b = _GlyphBounds2D(FONT_SPECIAL, frc, msg)
                    tx = int(round(_CenteredXForBounds(float(textX), float(textW), b)))
                    ty = _CenteredBaselineY(g2, float(botY), float(rowH), FONT_SPECIAL, msg)
                    g2.drawString(msg, tx, int(round(ty)))
                except:
                    fm = g2.getFontMetrics(FONT_SPECIAL)
                    tw = fm.stringWidth(msg)
                    tx = int(textX + (textW - tw) // 2)
                    ty = _RowCenterBaseline(int(botY), int(rowH), fm)
                    g2.drawString(msg, tx, int(ty))
                g2.setClip(oldClip)

        g2.setClip(clip)

    def Cleanup(self, event=None):
        if getattr(self, "Cleaned", False):
            return
        self.Cleaned = True

        try:
            self.AnimTimer.stop()
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
            if getattr(self, "_timebaseMinuteListenerAdded", False) and Timebase is not None and self._displayListener is not None:
                Timebase.removeMinuteChangeListener(self._displayListener)
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


# ------------------------------------------------------------
# Manager: spawns one window per platform
# ------------------------------------------------------------
class PlatformPidManager(object):
    def __init__(self):
        self.Windows = {}
        self._listener = _PidPropertyChangeListener(self.RebuildAndRefresh)

        try:
            if TimetableMem is not None:
                TimetableMem.addPropertyChangeListener(self._listener)
        except:
            pass
        try:
            if OverridesMem is not None:
                OverridesMem.addPropertyChangeListener(self._listener)
        except:
            pass
        try:
            if DepartTPMem is not None:
                DepartTPMem.addPropertyChangeListener(self._listener)
        except:
            pass

        try:
            PAR.addPlatformListener(self._listener)
        except:
            pass

        self.RebuildAndRefresh()

    def RebuildAndRefresh(self, event=None):
        rowsAll = CsvRows()
        plats = DetectPlatforms(rowsAll)

        for p in plats:
            if p not in self.Windows:
                self.Windows[p] = PIDUndergroundLedWindow(p, self.OnWindowClosed)

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

        def _SortKey(s):
            try:
                if str(s).isdigit():
                    return (0, int(s))
            except:
                pass
            return (1, str(s))

        for p in sorted(self.Windows.keys(), key=_SortKey):
            try:
                self.Windows[p].Frame.setLocation(int(x0 + dx * idx), int(y0 + dy * idx))
            except:
                pass
            idx += 1

        for w in self.Windows.values():
            try:
                w.UpdateDisplay()
            except:
                pass

    def OnWindowClosed(self, platformStr):
        try:
            if platformStr in self.Windows:
                del self.Windows[platformStr]
        except:
            pass


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------
PID_UndergroundLed_Manager = PlatformPidManager()
