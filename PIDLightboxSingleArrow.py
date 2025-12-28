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
# Arrow lightbox-style platform Passenger Information Display for JMRI 5.14
#
# <<PID-DISP-NAME: Lightbox arrow destination indicator (single platform)>>
# <<DESCRIPTION: A London Underground style arrow-and-enamel destination indicator showing the next train's destination by illuminating an arrow pointing at a fixed list of destinations>>
#
# User-configurable settings discovered by TASSetup.py (do not modify TASSetup.py):
# <<SETTING DESCRIPTION NUMBER: Show trains scheduled less than this many minutes in the future>>
# <<SETTING DESCRIPTION BOOLEAN: Only show trains whose platform has been allocated (requires platform allocation setup)>>
# <<SETTING DESCRIPTION BOOLEAN: Hide empty stock workings>>
#
# Notes on behaviour:
# - One window per platform present in the timetable (like PIDLightboxSingle.py).
# - Fixed enamel destination labels (white on blue) are derived from the whole timetable and do not change at runtime.
# - For the next train from the platform, the arrow next to the destination is illuminated.
# - Destination labels are fixed width; font size is reduced per-label so each label fits horizontally.
# - Destinations are shown in two columns; each label has an arrow to its left pointing right.
#
# Jython 2.7 / ASCII only / CamelCase / Thread-safe EDT

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, RenderingHints, Dimension
from java.awt import BasicStroke
from java.awt import GraphicsEnvironment
from java.awt import RadialGradientPaint
from java.awt.geom import Point2D
from java.awt.image import BufferedImage
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
                    print("[PIDLightboxSingleArrow] EDT invoke failed:", ex)
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
# Theme / geometry
# ------------------------------------------------------------
CABINET_COLOR = Color(0, 0, 0)
BORDER_COLOR = Color(0, 0, 0)
GRID_STROKE = BasicStroke(4.0)

# Enamel label colors (mid blue background, white text)
ENAMEL_BG = Color(8, 54, 138)
ENAMEL_TEXT = Color(245, 245, 245)


# Enamel ridge shading (computed relative to ENAMEL_BG so changes to base blue propagate)
def _BlendTowardEnamel(baseColor, targetR, targetG, targetB, frac):
    try:
        br = int(baseColor.getRed())
        bg = int(baseColor.getGreen())
        bb = int(baseColor.getBlue())
    except:
        br, bg, bb = 0, 0, 0
    try:
        rr = int(round(float(br) + (float(targetR) - float(br)) * float(frac)))
        gg = int(round(float(bg) + (float(targetG) - float(bg)) * float(frac)))
        bb2 = int(round(float(bb) + (float(targetB) - float(bb)) * float(frac)))
    except:
        rr, gg, bb2 = br, bg, bb
    if rr < 0: rr = 0
    if rr > 255: rr = 255
    if gg < 0: gg = 0
    if gg > 255: gg = 255
    if bb2 < 0: bb2 = 0
    if bb2 > 255: bb2 = 255
    return Color(int(rr), int(gg), int(bb2))

# Raised enamel effect: highlight line, base line, shadow line
ENAMEL_RIDGE_LIGHT = _BlendTowardEnamel(ENAMEL_BG, 255, 255, 255, 0.35)
ENAMEL_RIDGE_DARK = _BlendTowardEnamel(ENAMEL_BG, 0, 0, 0, 0.35)

def DrawEnamelRidgeHorizontal(g2, x, y, w):
    # Draw a 3px ridge: light, base, dark (top to bottom).
    try:
        x0 = int(x)
        y0 = int(y)
        ww = int(w)
        if ww <= 0:
            return
        g2.setColor(ENAMEL_RIDGE_LIGHT)
        g2.drawLine(x0, y0, x0 + ww - 1, y0)
        g2.setColor(ENAMEL_BG)
        g2.drawLine(x0, y0 + 1, x0 + ww - 1, y0 + 1)
        g2.setColor(ENAMEL_RIDGE_DARK)
        g2.drawLine(x0, y0 + 2, x0 + ww - 1, y0 + 2)
    except:
        pass

# Cabinet bevel and bolt shading (computed relative to CABINET_COLOR).
# Uses the same blend formula as enamel so any change to CABINET_COLOR propagates.
CABINET_EDGE_LIGHT = _BlendTowardEnamel(CABINET_COLOR, 255, 255, 255, 0.22)
CABINET_EDGE_DARK = _BlendTowardEnamel(CABINET_COLOR, 0, 0, 0, 0.85)
BOLT_FACE = _BlendTowardEnamel(CABINET_COLOR, 255, 255, 255, 0.16)
BOLT_SHADOW = _BlendTowardEnamel(CABINET_COLOR, 0, 0, 0, 0.90)
BOLT_HILITE = _BlendTowardEnamel(CABINET_COLOR, 255, 255, 255, 0.38)

def DrawCabinetSideBevel(g2, x, y, w, h, thickness=3):
    # Draw shaded black borders on left and right sides.
    try:
        x0 = int(x); y0 = int(y); ww = int(w); hh = int(h); t = int(thickness)
        if ww <= 0 or hh <= 0 or t <= 0:
            return
        for i in range(t):
            if i == 0:
                col = CABINET_EDGE_DARK
            elif i == 1:
                col = CABINET_COLOR
            else:
                col = CABINET_EDGE_LIGHT
            g2.setColor(col)
            g2.drawLine(x0 + i, y0, x0 + i, y0 + hh - 1)
        for i in range(t):
            if i == 0:
                col = CABINET_EDGE_DARK
            elif i == 1:
                col = CABINET_COLOR
            else:
                col = CABINET_EDGE_LIGHT
            g2.setColor(col)
            g2.drawLine(x0 + ww - 1 - i, y0, x0 + ww - 1 - i, y0 + hh - 1)
    except:
        pass

def DrawBolt(g2, cx, cy, r):
    # Small bolt head with subtle highlight/shadow and a slot.
    try:
        x0 = int(cx); y0 = int(cy); rr = int(r)
        if rr < 2:
            rr = 2
        g2.setColor(BOLT_SHADOW)
        g2.fillOval(x0 - rr, y0 - rr, 2 * rr, 2 * rr)
        g2.setColor(BOLT_FACE)
        g2.fillOval(x0 - rr + 1, y0 - rr + 1, 2 * rr - 2, 2 * rr - 2)
        g2.setColor(BOLT_HILITE)
        g2.fillOval(x0 - rr // 2, y0 - rr // 2, max(1, rr // 2), max(1, rr // 2))
        g2.setColor(CABINET_EDGE_DARK)
        g2.drawLine(x0 - rr // 2, y0, x0 + rr // 2, y0)
    except:
        pass

# Arrow panel colors
ARROW_BG = Color(14, 14, 14)
# Arrow column surround (very dark grey) computed relative to ARROW_BG
ARROW_FRAME_COLOR = _BlendTowardEnamel(ARROW_BG, 255, 255, 255, 0.10)
ARROW_FRAME_STROKE = BasicStroke(4.0)
ARROW_UNLIT = Color(24, 24, 24)
ARROW_LIT = Color(255, 235, 205)

CABINET_PAD = 10
CELL_PAD_X = 4
CELL_PAD_Y = 4
# Sizes
ARROW_W = 90
LABEL_W = 320
ROW_H = 54
COL_GAP = 18

# Font sizes
BASE_FONT_SIZE = 34
MIN_FONT_SIZE = 14

# Animation
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
    out = []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            for r in rdr:
                out.append(r)
    except Exception as ex:
        try:
            print("[PIDLightboxSingleArrow] Failed to read timetable:", ex)
        except:
            pass
        return []
    return out


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
            plats.add(str(p))
    try:
        return sorted(list(plats), key=lambda s: (not str(s).isdigit(), int(s) if str(s).isdigit() else str(s)))
    except:
        try:
            return sorted(list(plats))
        except:
            return []


def ParseOverrides(s):
    out = {}
    if not s:
        return out
    for part in str(s).replace(",", ";").split(";"):
        part = part.strip()
        if (not part) or ("=" not in part):
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def GetPlatformOverride(rn):
    try:
        if OverridesMem is None:
            return None
        return ParseOverrides(OverridesMem.getValue()).get(rn)
    except:
        return None


def _DepartureTPList():
    names = []
    try:
        raw = DepartTPMem.getValue() if DepartTPMem is not None else None
        if raw:
            for p in str(raw).replace(",", ";").split(";"):
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
    for tp in _DepartureTPList():
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


def IsEcsDestination(destUpper):
    try:
        s = str(destUpper or "").strip().upper()
        return s.startswith("EMPTY") or s.startswith("ECS")
    except:
        return False

# ------------------------------------------------------------
# Font helpers
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


def MakeFont(sz):
    return Font(FONT_FAM, Font.BOLD, int(sz))


def FitFontToWidth(g2, text, maxWidth, baseSize, minSize):
    # Reduce font size until the text fits the maxWidth and fits the row height.
    s = str(text or "")
    size = int(baseSize)
    if size < int(minSize):
        size = int(minSize)
    maxH = int(ROW_H) - (2 * int(CELL_PAD_Y))
    if maxH < 1:
        maxH = 1
    frc = g2.getFontRenderContext()
    while size > int(minSize):
        f = MakeFont(size)
        fm = g2.getFontMetrics(f)
        okW = (fm.stringWidth(s) <= int(maxWidth))
        try:
            gv = f.createGlyphVector(frc, s)
            b2 = gv.getOutline(0.0, 0.0).getBounds2D()
            h = float(b2.getHeight())
        except:
            h = float(fm.getHeight())
        okH = (h <= float(maxH))
        if okW and okH:
            return f
        size -= 1
    return MakeFont(int(minSize))


# ------------------------------------------------------------
# Arrow drawing
# ------------------------------------------------------------
def ScaleColor(c, mult):
    r = int(min(255, max(0, int(c.getRed() * mult))))
    g = int(min(255, max(0, int(c.getGreen() * mult))))
    b = int(min(255, max(0, int(c.getBlue() * mult))))
    return Color(r, g, b)


def MakeArrowShape(x, y, w, h):
    # Create a right-pointing arrow polygon closer to the London Underground style.
    # Features: slimmer shaft, pointier head, chamfered head-back, and a shaped tail (flat back, no reverse arrowhead).
    x0 = float(x)
    y0 = float(y)
    ww = float(w)
    hh = float(h)

    # Margins within the arrow cell
    mx = ww * 0.10
    my = hh * 0.18

    cy = y0 + (hh / 2.0)

    # Slimmer shaft
    shaftH = hh * 0.16
    shaftTop = cy - (shaftH / 2.0)
    shaftBot = cy + (shaftH / 2.0)

    # Head geometry (pointier, with chamfered head-back)
    tipX = x0 + ww - mx
    headW = ww * 0.38
    headBackX = tipX - headW
    chamfer = ww * 0.06
    headBackChamferX = headBackX + chamfer

    headTop = y0 + my
    headBot = y0 + hh - my

    # Tail geometry: flat back with small chamfers (matches photo better than a pointed reverse arrowhead)
    tailBackX = x0 + mx
    tailInX = tailBackX + (ww * 0.14)
    tailBackTop = cy - (shaftH * 0.95)
    tailBackBot = cy + (shaftH * 0.95)
    tailChamferX = ww * 0.05
    tailChamferY = shaftH * 0.45

    # Polygon points (clockwise)
    pts = [
        (tailBackX, tailBackTop),
        (tailInX, shaftTop),
        (headBackChamferX, shaftTop),
        (headBackX, headTop),
        (tipX, cy),
        (headBackX, headBot),
        (headBackChamferX, shaftBot),
        (tailInX, shaftBot),
        (tailBackX, tailBackBot),
    ]

    poly = awt.Polygon()
    for px, py in pts:
        poly.addPoint(int(round(px)), int(round(py)))
    return poly
def PaintArrow(g2, x, y, w, h, brightness):
    # Unlit: dark; lit: warm gradient.
    poly = MakeArrowShape(x, y, w, h)
    if brightness <= 0.0001:
        g2.setColor(ARROW_UNLIT)
        g2.fill(poly)
        return

    bval = max(0.0, min(1.0, float(brightness)))
    cx = float(x + w // 2)
    cy = float(y + h // 2)
    radius = float(max(w, h)) * 0.9
    colors = [ScaleColor(ARROW_LIT, 0.3 + 0.7 * bval), ScaleColor(ARROW_LIT, 0.06 * bval)]
    fractions = [0.0, 1.0]
    paint = RadialGradientPaint(Point2D.Float(cx, cy), float(radius), fractions, colors)
    try:
        g2.setPaint(paint)
        g2.fill(poly)
    except:
        g2.setColor(colors[0])
        g2.fill(poly)


# ------------------------------------------------------------
# Painting panel
# ------------------------------------------------------------
class ArrowPanel(swing.JPanel):
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
                    print("[PIDLightboxSingleArrow] propertyChange callback failed:", ex)
                except:
                    pass
        InvokeLater(_do)


# ------------------------------------------------------------
# Main per-platform window
# ------------------------------------------------------------
class PIDWindow(object):
    def __init__(self, platform, onCloseCallback=None):
        self.Platform = str(platform)
        self.OnCloseCallback = onCloseCallback
        self.Cleaned = False

        # Settings
        self.LookAheadMin = 10
        self.RequireAlloc = False
        self.HideEcs = False

        # Static destinations and per-destination fonts
        self.Destinations = []
        self.FontByDest = {}

        # Brightness for each arrow (keyed by destination index)
        self.ArrowBrightness = []

        self._lastAnimMs = None

        self.Frame = swing.JFrame("Destination indicator: platform " + self.Platform)
        self.Frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        self.Frame.setResizable(False)
        self.Panel = ArrowPanel(self)
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
        self.LookAheadMin = ReadIntSetting("Show trains scheduled less than this many minutes in the future", 10, 0, 240)
        self.RequireAlloc = ReadBoolSetting("Only show trains whose platform has been allocated (requires platform allocation setup)", False)
        self.HideEcs = ReadBoolSetting("Hide empty stock workings", False)

    def _RowsToday(self, rows, dayName):
        out = []
        for r in (rows or []):
            try:
                if (r.get(dayName, "") or "").strip().lower() == "true":
                    out.append(r)
            except:
                pass
        return out

    def _DisplayDestinationKey(self, destUpper, profUpper):
        if destUpper == profUpper:
            return "TERMINATES HERE"
        return destUpper

    def _BuildDestinations(self):
        self.ReadSettings()
        rows = CsvRows()
        profUpper = ActiveProfileNameUpper()
        destSet = {}
        for r in (rows or []):
            d = (r.get("Destination", "") or "").strip()
            if not d:
                continue
            du = d.upper()
            if bool(self.HideEcs) and IsEcsDestination(du):
                continue
            dk = self._DisplayDestinationKey(du, profUpper)
            destSet[dk] = True

        # Stable alphabetical ordering
        self.Destinations = sorted(list(destSet.keys()), key=lambda s: str(s).upper())

        # Prepare per-destination fonts so each fits LABEL_W
        img = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
        g2 = img.createGraphics()
        try:
            maxW = int(LABEL_W) - (2 * int(CELL_PAD_X))
            self.FontByDest = {}
            for d in (self.Destinations or []):
                self.FontByDest[d] = FitFontToWidth(g2, d, maxW, BASE_FONT_SIZE, MIN_FONT_SIZE)
        finally:
            try:
                g2.dispose()
            except:
                pass

        # Init brightness state
        self.ArrowBrightness = []
        for _i in range(len(self.Destinations)):
            self.ArrowBrightness.append({"b": 0.0, "t": 0.0})

    def RebuildStaticLayout(self):
        self._BuildDestinations()

        # Compute window size
        rows = int((len(self.Destinations) + 1) // 2)
        if rows < 1:
            rows = 1
        contentW = (2 * (ARROW_W + LABEL_W)) + COL_GAP
        contentH = rows * ROW_H
        totalW = contentW + (2 * CABINET_PAD)
        totalH = contentH + (2 * CABINET_PAD)

        try:
            self.Panel.setPreferredSize(Dimension(int(totalW), int(totalH)))
            self.Frame.pack()
        except:
            try:
                self.Frame.setSize(int(totalW) + 40, int(totalH) + 60)
            except:
                pass

    def GetNextTrainDestination(self):
        self.ReadSettings()
        rowsAll = CsvRows()
        dayName = str(DayMem.getValue() or "").strip()
        nowMin = CurrentMinutes()
        if nowMin is None:
            return ""

        rowsToday = self._RowsToday(rowsAll, dayName)
        profUpper = ActiveProfileNameUpper()

        lookAhead = int(self.LookAheadMin)
        requireAlloc = bool(self.RequireAlloc)

        candidates = []
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

            # Platform precedence: allocation > overrides > timetable
            alloc = PAR.getPlatform(rn)
            hasAlloc = (alloc is not None and str(alloc).strip() != "")
            if hasAlloc:
                plat = str(alloc).strip()
            else:
                ov = GetPlatformOverride(rn)
                plat = (str(ov).strip() if ov is not None else "")
                if plat == "":
                    plat = PlatformField(r)

            if str(plat) != str(self.Platform):
                continue

            if requireAlloc and (not hasAlloc):
                continue

            # Resolve delay with inheritance
            try:
                kind, val = ResolveDelayWithInheritance(rowsToday, rn, depMin, visited=set())
            except:
                kind, val = ("ontime", 0)

            # Skip cancellations
            if kind == "cancel":
                continue

            # Remove only when logged departed
            try:
                if HasDepartedAtConfiguredTP(rn, dayName, nowMin):
                    continue
            except:
                pass

            # Resilience filter: if no disruption and no timing anywhere today, hide if dep is in the past
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

            # Apply lookahead upper bound only when allocation is not required
            if (not requireAlloc) and (lookAhead > 0):
                if int(effMin) > int(nowMin + lookAhead):
                    continue

            dest = (r.get("Destination", "") or "").strip()
            destKey = dest.upper() if dest else ""
            if destKey != "":
                if bool(self.HideEcs) and IsEcsDestination(destKey):
                    continue
                destKey = self._DisplayDestinationKey(destKey, profUpper)

            candidates.append({"effMin": effMin, "destKey": destKey})

        candidates.sort(key=lambda t: t.get("effMin", 999999))
        if not candidates:
            return ""
        return str(candidates[0].get("destKey", "") or "")

    def UpdateDisplay(self, event=None):
        # Rebuild on timetable change
        try:
            if event is not None and (event.getSource() == TimetableMem):
                self.RebuildStaticLayout()
        except:
            pass

        destKey = self.GetNextTrainDestination()

        # Set targets
        for st in self.ArrowBrightness:
            st["t"] = 0.0

        if destKey:
            for i, d in enumerate(self.Destinations):
                if str(d) == str(destKey):
                    self.ArrowBrightness[i]["t"] = 1.0
                    break

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
        for st in self.ArrowBrightness:
            b = float(st.get("b", 0.0))
            t = float(st.get("t", 0.0))
            if abs(b - t) < 0.0005:
                st["b"] = t
                continue
            tau = RISE_TAU_S if t > b else FALL_TAU_S
            alpha = 1.0 - math.exp(-dt / float(tau))
            st["b"] = b + (t - b) * alpha
            anyChange = True

        if anyChange:
            try:
                self.Panel.repaint()
            except:
                pass

    def PaintContent(self, g2, x, y, w, h):
        # Layout destinations into two columns.
        total = len(self.Destinations)
        rows = int((total + 1) // 2)
        if rows < 1:
            rows = 1

        # Column origins
        leftX = x
        rightX = x + (ARROW_W + LABEL_W) + COL_GAP

        # Background
        g2.setColor(CABINET_COLOR)
        g2.fillRect(x, y, w, h)

        # Continuous arrow column background (no dividers between arrow cells)
        colH = int(rows * ROW_H)
        g2.setColor(ARROW_BG)
        g2.fillRect(leftX, y, ARROW_W, colH)
        g2.fillRect(rightX, y, ARROW_W, colH)
        # Subtle surround for arrow columns (very dark grey), as per photo
        try:
            oldStroke = g2.getStroke()
        except:
            oldStroke = None
        try:
            g2.setStroke(ARROW_FRAME_STROKE)
            g2.setColor(ARROW_FRAME_COLOR)
            g2.drawRect(leftX, y, ARROW_W, colH)
            g2.drawRect(rightX, y, ARROW_W, colH)
        finally:
            try:
                if oldStroke is not None:
                    g2.setStroke(oldStroke)
            except:
                pass

        # Draw cells
        for r in range(rows):
            # Left index
            li = r
            ri = r + rows

            cy = y + r * ROW_H

            # Draw left cell
            if li < total:
                self._PaintRowCell(g2, leftX, cy, li)

            # Draw right cell
            if ri < total:
                self._PaintRowCell(g2, rightX, cy, ri)

        # Bottom enamel ridge after the last cell (matches the photo).
        try:
            totalCells = len(self.Destinations)
            rCount = int((totalCells + 1) // 2)
            if rCount < 1: rCount = 1
            yBottom = y + (rCount * ROW_H)
            DrawEnamelRidgeHorizontal(g2, x + ARROW_W, yBottom, LABEL_W)
            DrawEnamelRidgeHorizontal(g2, x + (ARROW_W + LABEL_W) + COL_GAP + ARROW_W, yBottom, LABEL_W)
        except:
            pass

        # Cabinet borders: shaded sides + bolts (apply to enamel panels, not arrow columns)
        panelH = int(rows * ROW_H)
        leftEnX = int(x + ARROW_W)
        rightEnX = int(rightX + ARROW_W)
        # Side bevel for each enamel panel
        DrawCabinetSideBevel(g2, leftEnX, y, LABEL_W, panelH, thickness=3)
        DrawCabinetSideBevel(g2, rightEnX, y, LABEL_W, panelH, thickness=3)
        # Bolts at corners of each enamel panel
        DrawBolt(g2, leftEnX + 8, y + 8, 4)
        DrawBolt(g2, leftEnX + LABEL_W - 9, y + 8, 4)
        DrawBolt(g2, leftEnX + 8, y + panelH - 9, 4)
        DrawBolt(g2, leftEnX + LABEL_W - 9, y + panelH - 9, 4)
        DrawBolt(g2, rightEnX + 8, y + 8, 4)
        DrawBolt(g2, rightEnX + LABEL_W - 9, y + 8, 4)
        DrawBolt(g2, rightEnX + 8, y + panelH - 9, 4)
        DrawBolt(g2, rightEnX + LABEL_W - 9, y + panelH - 9, 4)
        # Mid-sides
        DrawBolt(g2, leftEnX + 8, y + (panelH // 2), 4)
        DrawBolt(g2, leftEnX + LABEL_W - 9, y + (panelH // 2), 4)
        DrawBolt(g2, rightEnX + 8, y + (panelH // 2), 4)
        DrawBolt(g2, rightEnX + LABEL_W - 9, y + (panelH // 2), 4)
    def _PaintRowCell(self, g2, x, y, idx):
        # Arrow column background drawn once in PaintContent (continuous column)

        # Label box
        lx = x + ARROW_W
        g2.setColor(ENAMEL_BG)
        g2.fillRect(lx, y, LABEL_W, ROW_H)
        # Raised enamel separator (no black grid lines between cells)
        DrawEnamelRidgeHorizontal(g2, lx, y, LABEL_W)
        g2.setColor(BORDER_COLOR)
        g2.setStroke(GRID_STROKE)
        # No black border for enamel labels (use enamel ridge shading instead)
        # Arrow (faint + lit overlay)
        st = self.ArrowBrightness[idx] if idx < len(self.ArrowBrightness) else None
        b = float(st.get("b", 0.0)) if st is not None else 0.0
        # Always draw faint arrow
        PaintArrow(g2, x + 6, y + 6, ARROW_W - 12, ROW_H - 12, 0.0)
        if b > 0.001:
            PaintArrow(g2, x + 6, y + 6, ARROW_W - 12, ROW_H - 12, b)

        # Text
        dest = self.Destinations[idx]
        f = self.FontByDest.get(dest, MakeFont(BASE_FONT_SIZE))
        g2.setFont(f)
        fm = g2.getFontMetrics(f)
        txt = str(dest)
        tw = fm.stringWidth(txt)
        tx = lx + (LABEL_W - tw) // 2
        if tx < (lx + CELL_PAD_X):
            tx = lx + CELL_PAD_X
        # Compute baseline Y using glyph bounds so the text looks visually centred.
        availH = int(ROW_H) - (2 * int(CELL_PAD_Y))
        if availH < 1:
            availH = 1
        frc = g2.getFontRenderContext()
        try:
            gv = f.createGlyphVector(frc, txt)
            b2 = gv.getOutline(0.0, 0.0).getBounds2D()
            bh = float(b2.getHeight())
            by = float(b2.getY())
            topY = float(y + CELL_PAD_Y) + (float(availH) - bh) / 2.0
            ty = int(round(topY - by))
        except:
            # Fallback: centre using font height.
            ty = y + CELL_PAD_Y + ((availH - fm.getHeight()) // 2) + fm.getAscent()
        g2.setColor(ENAMEL_TEXT)
        g2.drawString(txt, int(tx), int(ty))

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


# ------------------------------------------------------------
# Manager: one window per platform
# ------------------------------------------------------------
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
        # Cascade window placement
        x0, y0 = 50, 50
        dx, dy = 40, 40
        idx = 0
        try:
            sortedKeys = sorted(self.Windows.keys(), key=lambda s: (not str(s).isdigit(), int(s) if str(s).isdigit() else str(s)))
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


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------
PID_Manager = PlatformPIDManager()
