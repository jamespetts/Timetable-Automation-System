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
# Solari-style single platform indicator
# Black background, fixed white header bars, one destination flap, four two-line calling flaps.
# JMRI 5.14 / Jython 2.7 / ASCII only / CamelCase.
#
# <<PID-DISP-NAME: Single platform Solari/split flap indicator>>
# <<DESCRIPTION: A Solari/split flap display for showing the destination and calling pattern of the next train on an individual platform>>

# <<SETTING DESCRIPTION NUMBER: Heading font size>>
# <<SETTING DESCRIPTION NUMBER: Fixed text font size>>
# <<SETTING DESCRIPTION NUMBER: Calling pattern font size>>
# <<SETTING DESCRIPTION NUMBER: Header horizontal padding>>
# <<SETTING DESCRIPTION NUMBER: Destination extra padding>>
# <<SETTING DESCRIPTION COLOR: Solari special default fg>>
# <<SETTING DESCRIPTION COLOR: Solari special default bg>>
# <<SETTING DESCRIPTION COLOR: Solari special alt fg>>
# <<SETTING DESCRIPTION COLOR: Solari special alt bg>>
# <<SETTING DESCRIPTION STRING: Solari special keywords>>
import javax.swing as swing
import javax.swing.SwingUtilities as SwingUtilities
import java.awt as awt
from java.awt import Color, Font, RenderingHints
from javax.swing import Timer
from java.awt.image import BufferedImage
import java.awt.font.TextAttribute as TextAttribute
import java.beans as beans
import java.awt.event as awtevent

import jmri
from jmri import InstanceManager
from java.lang import System, Runnable

import os, csv, random

import TASBeanLookup as TBL
import TASPathResolver
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def ReadInt(memName, defaultVal, minVal=None, maxVal=None):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(memName, str(int(defaultVal)))
        n = int(float(str(raw).strip()))
        if minVal is not None:
            n = max(minVal, n)
        if maxVal is not None:
            n = min(maxVal, n)
        return int(n)
    except:
        return int(defaultVal)

def _SettingMemoryName(label):
    # Must match TASSetup.py memory naming:
    # key = re.sub(r"[^A-Za-z0-9]+", "_", label).upper()
    try:
        s = str(label).strip()
    except:
        s = ""
    import re as _re
    key = _re.sub(r"[^A-Za-z0-9]+", "_", s).upper()
    return "TAS_USER_SETTING_" + key

def ReadIntSetting(label, defaultVal, minVal=None, maxVal=None):
    return ReadInt(_SettingMemoryName(label), defaultVal, minVal, maxVal)

def RunOnEDT(func):
    try:
        if SwingUtilities.isEventDispatchThread():
            func()
            return
    except:
        pass

    class _R(Runnable):
        def run(self):
            try:
                func()
            except:
                pass

    try:
        SwingUtilities.invokeLater(_R())
    except:
        try:
            func()
        except:
            pass

# -----------------------------------------------------------------------------
# Scale / styling
# -----------------------------------------------------------------------------

SCALE_PCT = ReadInt("TAS_USER_SETTING_SOLARI_SCALE_PERCENT", 70, 35, 120)
S = float(SCALE_PCT) / 100.0

def Sc(x):
    return int(round(float(x) * S))

PANEL_BG = Color(0, 0, 0)
FLAP_BG = Color(11, 11, 11)
PURE_BLK = Color(0, 0, 0)
TEXT_WHT = Color(242, 242, 242)
YELLOW = Color(255, 211, 0)
RED = Color(200, 16, 46)
WHITE = Color(255, 255, 255)

# ---- Solari special message style (as per PIDSolari.py) ----

def ColorToRgbText(c):
    try:
        return "%d,%d,%d" % (int(c.getRed()), int(c.getGreen()), int(c.getBlue()))
    except:
        return "255,255,255"

def ParseColorSpec(raw, defaultColor):
    # Accept: "r,g,b", "r g b", "r;g;b", "#RRGGBB", "RRGGBB", and a few names.
    try:
        s = str(raw if raw is not None else "").strip()
    except:
        s = ""
    if s == "":
        return defaultColor
    sl = s.lower()
    if sl == "black":
        return Color(0, 0, 0)
    if sl == "white":
        return Color(255, 255, 255)
    if sl == "red":
        return RED
    if sl == "yellow":
        return YELLOW
    hx = sl
    if hx.startswith("#"):
        hx = hx[1:]
    if len(hx) == 6:
        try:
            r = int(hx[0:2], 16)
            g = int(hx[2:4], 16)
            b = int(hx[4:6], 16)
            return Color(r, g, b)
        except:
            pass
    t = s.replace(";", ",").replace(" ", ",")
    parts = [p for p in t.split(",") if p.strip() != ""]
    if len(parts) >= 3:
        try:
            r = int(float(parts[0].strip()))
            g = int(float(parts[1].strip()))
            b = int(float(parts[2].strip()))
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return Color(r, g, b)
        except:
            pass
    return defaultColor

def ReadColor(memName, defaultColor):
    # Store as "r,g,b" or "#RRGGBB". Default written in "r,g,b" form.
    try:
        defaultText = ColorToRgbText(defaultColor)
    except:
        defaultText = "255,255,255"
    raw = TBL.SafeGetOrCreateMemoryValue(memName, defaultText)
    return ParseColorSpec(raw, defaultColor)

def SplitKeywords(raw):
    out = []
    try:
        s = str(raw if raw is not None else "")
        s = s.replace(";", ",")
        for k in s.split(","):
            kk = (k or "").strip().lower()
            if kk != "":
                out.append(kk)
    except:
        pass
    return out

def GetSpecialStyleForMessage(msg):
    # Defaults: red on white; alternate: yellow on red when keywords match.
    defaultFg = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_DEFAULT_FG", RED)
    defaultBg = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_DEFAULT_BG", Color(255, 255, 255))
    altFg = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_ALT_FG", YELLOW)
    altBg = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_ALT_BG", RED)
    keysRaw = TBL.SafeGetOrCreateMemoryValue(
        "TAS_USER_SETTING_SOLARI_SPECIAL_KEYWORDS",
        "buffet,restaurant,trolley,dining"
    )
    keys = SplitKeywords(keysRaw)
    try:
        ml = str(msg if msg is not None else "").lower()
    except:
        ml = ""
    useAlt = False
    for k in keys:
        try:
            if k in ml:
                useAlt = True
                break
        except:
            pass
    if useAlt:
        return (altBg, altFg)
    return (defaultBg, defaultFg)

def SeedSpecialSettings():
    # Create default values so TASSetup can discover these memories.
    try:
        _ = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_DEFAULT_FG", RED)
        _ = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_DEFAULT_BG", Color(255, 255, 255))
        _ = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_ALT_FG", YELLOW)
        _ = ReadColor("TAS_USER_SETTING_SOLARI_SPECIAL_ALT_BG", RED)
    except:
        pass
    try:
        TBL.SafeGetOrCreateMemoryValue(
            "TAS_USER_SETTING_SOLARI_SPECIAL_KEYWORDS",
            "buffet,restaurant,trolley,dining"
        )
    except:
        pass

try:
    SeedSpecialSettings()
except:
    pass
HingeRatio = 0.50

BASE_FLAP_W = ReadInt("TAS_USER_SETTING_SOLARI_SINGLE_BASE_WIDTH", 780, 400, 1400)
FLAP_W = Sc(BASE_FLAP_W)

# Taller geometry than the original script; width unchanged.
FLAP_H = Sc(60)
DOUBLE_H = Sc(90)
BAR_H = Sc(34)
OUTER_PAD = Sc(14)
LINE_GAP = Sc(10)
BASE_DEST_EXTRA_GAP = ReadIntSetting("Destination extra padding", 5, 0, 50)
DEST_EXTRA_GAP = Sc(BASE_DEST_EXTRA_GAP)

# About one tab of padding for header text.
BASE_HEADER_PAD_X = ReadIntSetting("Header horizontal padding", 60, 0, 240)
HEADER_PAD_X = Sc(BASE_HEADER_PAD_X)

# Larger fonts than the original.

def AvailableFamilies():
    try:
        ge = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []


def PickFamily():
    prefs = ["BritishRailLightNormal", "Helvetica", "Liberation Sans", "Arial", "SansSerif"]
    fams = set([f.lower() for f in AvailableFamilies()])
    for p in prefs:
        if p.lower() in fams:
            return p
    return "SansSerif"

FONT_FAM = PickFamily()
BASE_FONT_BIG = ReadIntSetting("Heading font size", 40, 10, 80)
BASE_FONT_MID = ReadIntSetting("Fixed text font size", 28, 10, 80)
BASE_FONT_CALL = ReadIntSetting("Calling pattern font size", 28, 10, 80)
FONT_BIG = Sc(BASE_FONT_BIG)
FONT_MID = Sc(BASE_FONT_MID)
FONT_CALL = Sc(BASE_FONT_CALL)
def MakeFont(sz, bold=False):
    style = Font.BOLD if bold else Font.PLAIN
    return Font(FONT_FAM, style, int(sz))

DELAY_THRESHOLD_MIN = ReadInt("TAS_USER_SETTING_DELAY_THRESHOLD_MINUTES", 2, 0, 60)
CHATTER_STEPS = ReadInt("TAS_USER_SETTING_SOLARI_CHATTER_STEPS", 2, 0, 4)
ANIM_MS_PER_HALF = ReadInt("TAS_USER_SETTING_SOLARI_ANIM_MS_PER_HALF", 70, 35, 400)
DIGIT_FPS = ReadInt("TAS_USER_SETTING_SOLARI_DIGIT_FPS", 60, 30, 75)
STAGGER_ROW_MS = ReadInt("TAS_USER_SETTING_SOLARI_STAGGER_ROW_MS", 350, 0, 3000)
STAGGER_JITTER_MS = ReadInt("TAS_USER_SETTING_SOLARI_STAGGER_JITTER_MS", 250, 0, 3000)

# -----------------------------------------------------------------------------
# Drawing helpers
# -----------------------------------------------------------------------------

def PaintFlapFrame(g2, w, h, bgColor, frameColor, hingeY=None):
    ww = int(w)
    hh = int(h)
    t = Sc(2)
    if t < 1:
        t = 1
    if ww < 2 or hh < 2:
        return
    g2.setColor(frameColor)
    g2.fillRect(0, 0, ww, hh)
    innerW = ww - (2 * t)
    innerH = hh - (2 * t)
    if innerW > 0 and innerH > 0:
        g2.setColor(bgColor)
        g2.fillRect(t, t, innerW, innerH)
    if hingeY is not None:
        y = int(hingeY) - (t // 2)
        if y < 0:
            y = 0
        if y > hh - t:
            y = hh - t
        g2.setColor(frameColor)
        g2.fillRect(0, y, ww, t)


def DrawHingeOver(g2, w, h, frameColor):
    ww = int(w)
    hh = int(h)
    t = Sc(2)
    if t < 1:
        t = 1
    hy = int(float(h) * float(HingeRatio))
    y = hy - (t // 2)
    if y < 0:
        y = 0
    if y > hh - t:
        y = hh - t
    g2.setColor(frameColor)
    g2.fillRect(0, y, ww, t)


def _StringWidthWithTracking(f, g2, s):
    try:
        attrs = {TextAttribute.TRACKING: -0.04}
        f2 = f.deriveFont(attrs)
        fm2 = g2.getFontMetrics(f2)
        return f2, fm2.stringWidth(s)
    except:
        fm = g2.getFontMetrics(f)
        return f, fm.stringWidth(s)


def FitFontToWidth(g2, baseFont, s, maxWidth, minSize):
    fm = g2.getFontMetrics(baseFont)
    if fm.stringWidth(s) <= maxWidth:
        return baseFont, s

    fT, wT = _StringWidthWithTracking(baseFont, g2, s)
    if wT <= maxWidth:
        return fT, s

    try:
        sz = int(baseFont.getSize())
    except:
        sz = 12

    cur = sz
    while cur > int(minSize):
        cur -= 1
        try:
            fTry = baseFont.deriveFont(float(cur))
        except:
            fTry = MakeFont(cur, bold=False)
        fTry2, wTry = _StringWidthWithTracking(fTry, g2, s)
        if wTry <= maxWidth:
            return fTry2, s

    # Last resort: ellipsis
    fm = g2.getFontMetrics(fT)
    t = s
    while len(t) > 1 and fm.stringWidth(t + "...") > maxWidth:
        t = t[:-1]
    if len(t) > 1:
        t = t + "..."
    return fT, t

# -----------------------------------------------------------------------------
# Time helpers
# -----------------------------------------------------------------------------

import java.text.SimpleDateFormat as SimpleDateFormat
Parser12 = SimpleDateFormat("h:mm a")
Parser24 = SimpleDateFormat("H:mm")

def ParseMinutes(s):
    s = (s or "").strip()
    if s == "":
        return None
    for p in [Parser12, Parser24]:
        try:
            d = p.parse(s)
            return d.getHours() * 60 + d.getMinutes()
        except:
            pass
    try:
        if ":" in s and len(s) <= 5:
            h, m = s.split(":")
            return int(h) * 60 + int(m)
    except:
        pass
    return None

def CurrentMinutes():
    Timebase = InstanceManager.getDefault(jmri.Timebase)
    try:
        if Timebase is not None:
            ft = Timebase.getTime()
            return ft.getHours() * 60 + ft.getMinutes()
    except:
        pass
    try:
        curStr = TBL.SafeGetOrCreateMemoryValue("CURRENTTIME", "")
        return ParseMinutes(curStr)
    except:
        return None

# -----------------------------------------------------------------------------
# Timetable and registers
# -----------------------------------------------------------------------------

DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
TTMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")
DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")


def TimetablePath():
    name = (TTMem.getValue() or "").strip()
    if name == "":
        return None
    try:
        prof = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    except:
        return None
    return TASPathResolver.GetTimetableCsvPath(name)
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
    except:
        return []
    return out


def PlatformField(row):
    val = (row.get("Plat", "") or "").strip()
    if val == "":
        val = (row.get("Platform", "") or "").strip()
    return val

def CaseInsensitive(row, key):
    # Case-insensitive lookup for CSV column names.
    target = (key or "").strip().lower()
    try:
        for k in (row.keys() or []):
            if (k or "").strip().lower() == target:
                v = row.get(k, "")
                return (v or "").strip()
    except:
        pass
    return ""


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


def GetOverride(rn):
    try:
        return ParseOverrides(OverridesMem.getValue()).get(rn)
    except:
        return None

# Departure TP clearing (PIDCRTSingle.py pattern)

def ActiveProfileBaseTPName():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""


def DepartureTPList():
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
        base = ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names

def HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    for tp in DepartureTPList():
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
            mm = ParseMinutes(tstr)
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
                rn = rec[0]; d = rec[3]
            except:
                continue
            if str(rn) == str(reportingNumber) and str(d) == str(dayName):
                return True
    return False

# ECS detection and inherited disruption

DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]

def ReadExtraEcsTerms():
    try:
        raw = EcsFilterMem.getValue() if EcsFilterMem is not None else None
        if not raw:
            return []
        out = []
        for p in str(raw).replace(",", ";").split(";"):
            p = p.strip()
            if p:
                out.append(p.upper())
        return out
    except:
        return []


def IsEcsWorking(row):
    rn = ((row.get("Reporting number", "") or "")).strip().upper()
    if rn.startswith("5"):
        return True
    dest = ((row.get("Destination", "") or "")).strip().upper()
    call = ((row.get("Calling pattern", "") or "")).strip().upper()
    terms = set([t.upper() for t in DefaultEcsTerms])
    for extra in ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " " + call
    for t in terms:
        if t and t in hay:
            return True
    return False


def ResolveDelayWithInheritance(rowsToday, formersMap, rn, schedDepMin, visited=None):
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
            dd = int(d)
        except:
            dd = 0
        if dd >= 1440:
            return ("cancel", None)
        if dd > 0:
            return ("delay", dd)

    formers = formersMap.get(rn, [])
    if not formers:
        return ("ontime", 0)

    chosen = None
    if schedDepMin is not None:
        before = []
        for fr in formers:
            arr = (fr.get("Arr", "") or "").strip()
            arrMin = ParseMinutes(arr) if arr else None
            if arrMin is not None and arrMin <= schedDepMin:
                before.append((arrMin, fr))
        if before:
            before.sort(key=lambda t: t[0])
            chosen = before[-1][1]

    if chosen is None:
        chosen = formers[0]

    formerRn = (chosen.get("Reporting number", "") or "").strip()
    return ResolveDelayWithInheritance(rowsToday, formersMap, formerRn, schedDepMin, visited)

# -----------------------------------------------------------------------------
# Solari animation classes
# -----------------------------------------------------------------------------

class SolariAnimClock(object):
    TimerObj = None
    Active = {}
    LastMs = None

    @classmethod
    def _GetInterval(cls):
        try:
            fps = int(DIGIT_FPS)
        except:
            fps = 60
        if fps <= 0:
            fps = 60
        return int(max(1000 // fps, 15))

    @classmethod
    def Register(cls, flap):
        if flap is None:
            return
        try:
            cls.Active[id(flap)] = flap
        except:
            return
        cls._EnsureRunning()

    @classmethod
    def Unregister(cls, flap):
        try:
            cls.Active.pop(id(flap), None)
        except:
            pass
        if not cls.Active:
            cls._Stop()

    @classmethod
    def _EnsureRunning(cls):
        iv = cls._GetInterval()
        if cls.TimerObj is None:
            cls.LastMs = System.currentTimeMillis()
            cls.TimerObj = Timer(iv, cls._OnTick)
            cls.TimerObj.setRepeats(True)
            cls.TimerObj.start()
        else:
            try:
                cls.TimerObj.setDelay(iv)
            except:
                pass

    @classmethod
    def _Stop(cls):
        try:
            if cls.TimerObj is not None:
                cls.TimerObj.stop()
        except:
            pass
        cls.TimerObj = None
        cls.LastMs = None

    @classmethod
    def _OnTick(cls, e):
        now = System.currentTimeMillis()
        dt = 16
        try:
            if cls.LastMs is not None:
                dt = int(now - cls.LastMs)
                if dt < 1:
                    dt = 1
        except:
            dt = 16
        cls.LastMs = now

        activeList = []
        try:
            activeList = list(cls.Active.values())
        except:
            activeList = []

        toRemove = []
        for f in activeList:
            try:
                keep = f.OnClockTick(dt)
                if not keep:
                    toRemove.append(f)
            except:
                toRemove.append(f)

        for f in toRemove:
            try:
                cls.Active.pop(id(f), None)
            except:
                pass

        if not cls.Active:
            cls._Stop()


class SolariFlap(swing.JComponent):
    def __init__(self, w, h, twoLine=False):
        swing.JComponent.__init__(self)
        self.setOpaque(False)
        self.w = int(w)
        self.h = int(h)
        self.twoLine = bool(twoLine)
        self.curTop = ""
        self.curBot = ""
        self.phase = "idle"
        self.t = 0.0
        self.queue = []
        self.pendingTimer = None
        self.AnimSerial = 0
        self.ActiveSerial = 0
        self.msPerHalf = int(ANIM_MS_PER_HALF)
        self.setSize(self.w, self.h)

    def EaseInOut(self, x):
        try:
            t = float(x)
        except:
            t = 0.0
        if t < 0.0:
            t = 0.0
        if t > 1.0:
            t = 1.0
        return (3.0 * t * t) - (2.0 * t * t * t)

    def DrawTextLine(self, g2, text, top, colorOverride=None):
        g2.setColor(colorOverride if colorOverride is not None else TEXT_WHT)
        margin = Sc(12)
        halfH = int(self.h * HingeRatio) if top else (self.h - int(self.h * HingeRatio))
        y0 = 0 if top else int(self.h * HingeRatio)

        baseSize = FONT_BIG if not self.twoLine else FONT_CALL
        f = MakeFont(baseSize, bold=False)
        s = str(text or "")
        maxW = self.w - 2 * margin
        minSz = max(10, int(int(baseSize) * 0.60))
        fFit, sFit = FitFontToWidth(g2, f, s, maxW, minSz)

        g2.setFont(fFit)
        fm = g2.getFontMetrics(fFit)
        baseline = y0 + (halfH + fm.getAscent()) // 2 - 2
        g2.drawString(sFit, margin, baseline)

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, FLAP_BG, PURE_BLK, hingeY=hingeY)

            if self.phase == "idle":
                self.DrawTextLine(g2, self.curTop, True)
                self.DrawTextLine(g2, self.curBot, False)
                return

            oldTop = getattr(self, "prevTop", self.curTop)
            oldBot = getattr(self, "prevBot", self.curBot)
            newTop = getattr(self, "nextTop", self.curTop)
            newBot = getattr(self, "nextBot", self.curBot)

            frac = self.EaseInOut(self.t)
            reveal = int(round(frac * float(self.h)))
            if reveal < 0:
                reveal = 0
            if reveal > self.h:
                reveal = self.h

            if reveal > 0:
                g2.setClip(awt.Rectangle(0, 0, self.w, reveal))
                self.DrawTextLine(g2, newTop, True)
                self.DrawTextLine(g2, newBot, False)
            if reveal < self.h:
                g2.setClip(awt.Rectangle(0, reveal, self.w, self.h - reveal))
                self.DrawTextLine(g2, oldTop, True)
                self.DrawTextLine(g2, oldBot, False)
        finally:
            try:
                g2.setClip(None)
            except:
                pass
            DrawHingeOver(g2, self.w, self.h, PURE_BLK)
            g2.dispose()

    def AnimateTo(self, targetTop, targetBot, chatterPairs, startDelayMs=0):
        try:
            if self.pendingTimer is not None:
                self.pendingTimer.stop()
        except:
            pass
        self.pendingTimer = None

        try:
            self.AnimSerial = int(self.AnimSerial) + 1
        except:
            self.AnimSerial = 1
        localSerial = self.AnimSerial

        tgtTop = str(targetTop or "")
        tgtBot = str(targetBot or "")
        if self.curTop == tgtTop and self.curBot == tgtBot:
            # cancel in-flight animation for this flap
            try:
                self.queue = []
            except:
                pass
            self.phase = "idle"
            self.t = 0.0
            try:
                self.repaint()
            except:
                pass
            return

        seq = []
        for p in (chatterPairs or []):
            try:
                seq.append((p[0], p[1]))
            except:
                seq.append(("", ""))
        seq.append((tgtTop, tgtBot))
        self.queue = seq

        first = self.queue.pop(0) if self.queue else None

        def _Start(pair, serial):
            try:
                if int(serial) != int(self.AnimSerial):
                    return
            except:
                return
            if pair is None:
                self.phase = "idle"
                self.repaint()
                return
            self.ActiveSerial = serial
            self.prevTop = self.curTop
            self.prevBot = self.curBot
            self.nextTop = pair[0]
            self.nextBot = pair[1]
            self.phase = "flip"
            self.t = 0.0
            SolariAnimClock.Register(self)
            self.repaint()

        try:
            dly = int(startDelayMs)
        except:
            dly = 0

        if dly > 0:
            def _Later(e):
                _Start(first, localSerial)
            self.pendingTimer = Timer(dly, _Later)
            self.pendingTimer.setRepeats(False)
            self.pendingTimer.start()
        else:
            _Start(first, localSerial)

    def OnClockTick(self, dtMs):
        try:
            if int(getattr(self, "ActiveSerial", 0)) != int(getattr(self, "AnimSerial", 0)):
                self.phase = "idle"
                self.t = 0.0
                return False
        except:
            pass
        if self.phase != "flip":
            return False
        try:
            self.t += float(dtMs) / float(self.msPerHalf * 2.0)
        except:
            self.t += 0.2
        if self.t >= 1.0:
            self.curTop = getattr(self, "nextTop", self.curTop)
            self.curBot = getattr(self, "nextBot", self.curBot)
            if self.queue:
                nxt = self.queue.pop(0)
                self.prevTop = self.curTop
                self.prevBot = self.curBot
                self.nextTop = nxt[0]
                self.nextBot = nxt[1]
                self.t = 0.0
                return True
            self.phase = "idle"
            self.t = 0.0
            self.repaint()
            return False
        self.repaint()
        return True


class WordFlap(SolariFlap):
    def __init__(self, w, h):
        SolariFlap.__init__(self, w, h, twoLine=False)

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, FLAP_BG, PURE_BLK, hingeY=hingeY)

            def _DrawCentered(txt):
                margin = Sc(12)
                s = str(txt or "")
                f = MakeFont(FONT_BIG, bold=False)
                minSz = max(10, int(int(FONT_BIG) * 0.60))
                fFit, sFit = FitFontToWidth(g2, f, s, self.w - 2 * margin, minSz)
                g2.setFont(fFit)
                fm = g2.getFontMetrics(fFit)
                wTxt = fm.stringWidth(sFit)
                x = (self.w - wTxt) // 2
                if x < margin:
                    x = margin
                baseline = (self.h + fm.getAscent()) // 2 - 2
                g2.setColor(TEXT_WHT)
                g2.drawString(sFit, x, baseline)

            if self.phase == "idle":
                _DrawCentered(self.curTop)
                return

            oldText = getattr(self, "prevTop", self.curTop)
            newText = getattr(self, "nextTop", self.curTop)
            frac = self.EaseInOut(self.t)
            reveal = int(round(frac * float(self.h)))
            if reveal < 0:
                reveal = 0
            if reveal > self.h:
                reveal = self.h
            if reveal > 0:
                g2.setClip(awt.Rectangle(0, 0, self.w, reveal))
                _DrawCentered(newText)
            if reveal < self.h:
                g2.setClip(awt.Rectangle(0, reveal, self.w, self.h - reveal))
                _DrawCentered(oldText)
        finally:
            try:
                g2.setClip(None)
            except:
                pass
            DrawHingeOver(g2, self.w, self.h, PURE_BLK)
            g2.dispose()


class ColoredDoubleLineFlap(SolariFlap):
    def __init__(self, w, h):
        SolariFlap.__init__(self, w, h, twoLine=True)
        self.SpecialBg = None
        self.SpecialFg = None

    def SetSpecialColors(self, bg, fg):
        self.SpecialBg = bg
        self.SpecialFg = fg

    def ClearSpecialColors(self):
        self.SpecialBg = None
        self.SpecialFg = None

    def paintComponent(self, g):
        if self.SpecialBg is None or self.SpecialFg is None:
            SolariFlap.paintComponent(self, g)
            return
        # If there is no text to show yet, always render as a normal (black) flap.
        # A real Solari flap would not show a special background with no text.
        try:
            if self.phase == "idle":
                if (str(self.curTop or "").strip() == "") and (str(self.curBot or "").strip() == ""):
                    SolariFlap.paintComponent(self, g)
                    return
        except:
            pass          
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, self.SpecialBg, PURE_BLK, hingeY=hingeY)
            if self.phase == "idle":
                self.DrawTextLine(g2, self.curTop, True, colorOverride=self.SpecialFg)
                self.DrawTextLine(g2, self.curBot, False, colorOverride=self.SpecialFg)
            else:
                SolariFlap.paintComponent(self, g)
        finally:
            DrawHingeOver(g2, self.w, self.h, PURE_BLK)
            g2.dispose()

# -----------------------------------------------------------------------------
# White header bar
# -----------------------------------------------------------------------------

class WhiteBar(swing.JComponent):
    def __init__(self, text):
        swing.JComponent.__init__(self)
        self.setOpaque(True)
        self.setBackground(WHITE)
        self.text = str(text or "")

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            w = self.getWidth()
            h = self.getHeight()
            g2.setColor(WHITE)
            g2.fillRect(0, 0, w, h)

            txt = self.text
            size = int(FONT_MID)
            if size < 10:
                size = 10
            f = MakeFont(size, bold=False)
            g2.setFont(f)
            fm = g2.getFontMetrics(f)
            maxW = max(10, w - HEADER_PAD_X - Sc(12))
            while size > 10 and fm.stringWidth(txt) > maxW:
                size -= 1
                f = MakeFont(size, bold=False)
                g2.setFont(f)
                fm = g2.getFontMetrics(f)

            g2.setColor(PURE_BLK)
            x = int(HEADER_PAD_X)
            y = (h + fm.getAscent()) // 2 - 2
            g2.drawString(txt, x, y)
        finally:
            g2.dispose()

# -----------------------------------------------------------------------------
# Calling pattern packing and special message wrapping
# -----------------------------------------------------------------------------

def PackCallingLines(stops, flapWidth, maxLines):
    lines = []
    cur = ""
    for st in (stops or []):
        s = (st or "").strip()
        if s == "":
            continue
        if cur == "":
            cand = s
        else:
            cand = cur + ", " + s

        img = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
        g2 = img.createGraphics()
        try:
            margin = Sc(12)
            maxW = int(flapWidth) - 2 * margin
            f = MakeFont(FONT_CALL, bold=False)
            f2, w = _StringWidthWithTracking(f, g2, cand)
            if w <= maxW:
                cur = cand
            else:
                if cur != "":
                    lines.append(cur)
                cur = s
        finally:
            g2.dispose()

        if len(lines) >= maxLines:
            break

    if cur != "" and len(lines) < maxLines:
        lines.append(cur)

    return lines


def WrapMessageTwoLines(text, flapWidth):
    # Split message text into two lines for the bottom flap.
    # Honour explicit newlines; otherwise, greedy word wrap across two lines.
    try:
        raw = str(text or "").replace("\r", "\n")
        if "\n" in raw:
            parts = [p.strip() for p in raw.split("\n") if p.strip() != ""]
            if parts:
                if len(parts) == 1:
                    return (parts[0], "")
                return (parts[0], " ".join(parts[1:]))
    except:
        pass

    words = [w for w in str(text or "").split() if w]
    if not words:
        return ("", "")

    img = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
    g2 = img.createGraphics()
    try:
        margin = Sc(12)
        maxW = int(flapWidth) - 2 * margin
        f = MakeFont(FONT_CALL, bold=False)
        minSz = max(10, int(int(FONT_CALL) * 0.60))

        line1 = ""
        i = 0
        while i < len(words):
            cand = words[i] if line1 == "" else (line1 + " " + words[i])
            fFit, sFit = FitFontToWidth(g2, f, cand, maxW, minSz)
            fm = g2.getFontMetrics(fFit)
            if fm.stringWidth(sFit) <= maxW and (not sFit.endswith("...") or sFit == cand):
                line1 = cand
                i += 1
            else:
                break

        line2 = " ".join(words[i:]) if i < len(words) else ""
        if line2:
            fFit2, sFit2 = FitFontToWidth(g2, f, line2, maxW, minSz)
            line2 = sFit2

        return (line1, line2)
    finally:
        g2.dispose()


# -----------------------------------------------------------------------------
# Calling pattern chatter pools (only values that can appear at each flap position)
# -----------------------------------------------------------------------------

try:
    from java.util.concurrent.locks import ReentrantLock
    _CallPoolsLock = ReentrantLock()
except:
    _CallPoolsLock = None

_CallLinePoolsCache = {}

def _CallingLinePoolsCacheKey(maxLines):
    try:
        path = TimetablePath()
    except:
        path = None
    try:
        tt = (TTMem.getValue() or "").strip()
    except:
        tt = ""
    try:
        mt = os.path.getmtime(path) if (path and os.path.exists(path)) else 0
    except:
        mt = 0
    return (tt, int(FLAP_W), int(maxLines), int(mt))

def CallingLinePoolsAll(flapWidth, maxLines):
    pools = []
    for _i in range(int(maxLines)):
        pools.append([])
    seenByPos = []
    for _i in range(int(maxLines)):
        seenByPos.append(set())
    rowsAll = CsvRows()
    for r in (rowsAll or []):
        try:
            callText = CaseInsensitive(r, "Calling pattern")
        except:
            callText = ""
        callText = (callText or "").strip()
        stops = []
        if callText:
            try:
                stops = [t.strip() for t in str(callText).split(",") if t.strip()]
            except:
                stops = []
        if not stops:
            stops = ["NON-STOP"]

        try:
            packed = PackCallingLines(stops, flapWidth, int(maxLines))
        except:
            packed = []
        while len(packed) < int(maxLines):
            packed.append("")
        for pos in range(int(maxLines)):
            txt = (packed[pos] or "").strip()
            if txt == "":
                continue
            key = txt.lower()
            if key in seenByPos[pos]:
                continue
            seenByPos[pos].add(key)
            pools[pos].append(txt)
    return pools

def GetCallingLinePoolsCached(maxLines):
    key = _CallingLinePoolsCacheKey(maxLines)
    locked = False
    if _CallPoolsLock is not None:
        try:
            _CallPoolsLock.lock()
            locked = True
        except:
            locked = False
    try:
        if key in _CallLinePoolsCache:
            pools = _CallLinePoolsCache.get(key)
            if pools is not None:
                return pools
        pools = CallingLinePoolsAll(FLAP_W, int(maxLines))
        try:
            _CallLinePoolsCache.clear()
            _CallLinePoolsCache[key] = pools
        except:
            pass
        return pools
    finally:
        if locked and _CallPoolsLock is not None:
            try:
                _CallPoolsLock.unlock()
            except:
                pass

def BuildCallingChatterPairs(flapIndex, curTop, curBot, targetTop, targetBot, pools, steps):
    pairs = []
    try:
        n = int(steps)
    except:
        n = 0
    if n <= 0 or pools is None:
        return pairs
    if (str(curTop or "") == str(targetTop or "")) and (str(curBot or "") == str(targetBot or "")):
        return pairs
    try:
        fi = int(flapIndex)
    except:
        fi = 0
    topPos = fi * 2
    botPos = topPos + 1
    topPool = []
    botPool = []
    try:
        if topPos < len(pools):
            topPool = list(pools[topPos] or [])
    except:
        topPool = []
    try:
        if botPos < len(pools):
            botPool = list(pools[botPos] or [])
    except:
        botPool = []
    if not topPool and not botPool:
        return pairs
    lastPick = None
    for _k in range(n):
        a = ""
        b = ""
        if topPool:
            try:
                a = random.choice(topPool)
            except:
                a = ""
        if botPool:
            try:
                b = random.choice(botPool)
            except:
                b = ""
        pick = (a, b)
        if lastPick is not None and pick == lastPick and (len(topPool) > 1 or len(botPool) > 1):
            tries = 0
            while pick == lastPick and tries < 4:
                if topPool:
                    try:
                        a = random.choice(topPool)
                    except:
                        a = ""
                if botPool:
                    try:
                        b = random.choice(botPool)
                    except:
                        b = ""
                pick = (a, b)
                tries += 1
        lastPick = pick
        pairs.append(pick)
    return pairs

# -----------------------------------------------------------------------------
# Selection: next service per platform
# -----------------------------------------------------------------------------

def _RowsToday(rows, dayName):
    out = []
    for r in (rows or []):
        try:
            v = (r.get(dayName, "") or "").strip().lower()
        except:
            v = ""
        if v == "true":
            out.append(r)
    return out


def _PlatformForRow(row, rn):
    try:
        alloc = PAR.getPlatform(rn)
    except:
        alloc = None
    if alloc is not None and str(alloc).strip():
        return str(alloc).strip()
    ov = GetOverride(rn)
    if ov is not None and str(ov).strip():
        return str(ov).strip()
    return PlatformField(row)


def PickNextTrainForPlatform(platformText):
    rows = CsvRows()
    day = DayMem.getValue() or ""
    now = CurrentMinutes()
    if now is None:
        return None

    todays = _RowsToday(rows, day)

    formersMap = {}
    for r in todays:
        child = (r.get("Forms", "") or "").strip()
        if child:
            formersMap.setdefault(child, []).append(r)

    cands = []
    for row in todays:
        dep = (row.get("Dep", "") or "").strip()
        if not dep:
            continue
        rn = (row.get("Reporting number", "") or "").strip()
        depMin = ParseMinutes(dep)
        if depMin is None:
            continue

        plat = _PlatformForRow(row, rn)
        if str(plat) != str(platformText):
            continue

        kind, val = ResolveDelayWithInheritance(todays, formersMap, rn, depMin, visited=set())
        cancelled = (kind == "cancel")
        delayMin = int(val) if (kind == "delay" and val is not None) else 0
        expectedMin = ((depMin + delayMin) % (24 * 60)) if delayMin > 0 else None

        if (not cancelled) and HasDepartedAtConfiguredTP(rn, day, now):
            continue

        if cancelled:
            if depMin < now:
                continue
        elif expectedMin is not None:
            if expectedMin < now:
                continue
        else:
            # On-time resilience (PIDSmall behaviour):
            # If there is NO disruption AND no timing anywhere today for this RN,
            # hide only if booked Dep < now; otherwise keep it until actually logged departed.
            try:
                direct = getDisruption(rn)
            except:
                direct = None
            if (direct is None) and (not HasAnyTimingToday(rn, day)):
                if depMin < now:
                    continue
        adjusted = expectedMin if expectedMin is not None else depMin

        destText = (row.get("Destination", "") or "").strip()
        callText = (row.get("Calling pattern", "") or "").strip()
        specialText = (CaseInsensitive(row, "Special") or "").strip()

        ecs = IsEcsWorking(row)
        delayed = (delayMin >= int(DELAY_THRESHOLD_MIN)) if expectedMin is not None else False

        cands.append({
            "rn": rn,
            "adjMin": adjusted,
            "dest": destText,
            "call": callText,
            "special": specialText,
            "ecs": ecs,
            "cancelled": cancelled,
            "delayed": delayed
        })

    if not cands:
        return None

    cands.sort(key=lambda t: t["adjMin"])
    return cands[0]

# -----------------------------------------------------------------------------
# Window/controller
# -----------------------------------------------------------------------------

class SolariSinglePIDWindow(object):
    def __init__(self, platform, OnCloseCallback=None):
        self.platform = str(platform)
        self.OnCloseCallback = OnCloseCallback
        self.CleanedUp = False
        self.RefreshListener = None
        self.CloseAdapter = None

        self.frame = swing.JFrame("Passenger information display: platform " + self.platform)
        self.frame.setDefaultCloseOperation(swing.JFrame.DO_NOTHING_ON_CLOSE)
        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setBackground(PANEL_BG)

        x = OUTER_PAD
        y = OUTER_PAD

        self.barTop = WhiteBar("NEXT TRAIN FROM THIS PLATFORM")
        self.barTop.setBounds(x, y, FLAP_W, BAR_H)
        cp.add(self.barTop)
        y += BAR_H + LINE_GAP + DEST_EXTRA_GAP

        self.flapDest = WordFlap(FLAP_W, FLAP_H)
        self.flapDest.setBounds(x, y, FLAP_W, FLAP_H)
        cp.add(self.flapDest)
        y += FLAP_H + LINE_GAP + DEST_EXTRA_GAP

        self.barCall = WhiteBar("CALLING AT")
        self.barCall.setBounds(x, y, FLAP_W, BAR_H)
        cp.add(self.barCall)
        y += BAR_H + LINE_GAP

        self.callFlaps = []
        for i in range(4):
            fp = ColoredDoubleLineFlap(FLAP_W, DOUBLE_H)
            fp.setBounds(x, y, FLAP_W, DOUBLE_H)
            cp.add(fp)
            self.callFlaps.append(fp)
            y += DOUBLE_H + LINE_GAP

        contentW = FLAP_W + 2 * OUTER_PAD
        contentH = y + OUTER_PAD

        try:
            self.frame.addNotify()
            ins = self.frame.getInsets()
            iw, ih = (ins.left + ins.right), (ins.top + ins.bottom)
        except:
            iw = ih = 0

        self.frame.setSize(int(contentW + iw), int(contentH + ih))
        self.frame.setResizable(False)

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)
        except:
            pass

        class RefreshPCL(beans.PropertyChangeListener):
            def __init__(innerSelf, Window):
                innerSelf.Window = Window
            def propertyChange(innerSelf, Event):
                try:
                    innerSelf.Window.RequestRefresh(Event)
                except:
                    pass

        class WindowCloseAdapter(awtevent.WindowAdapter):
            def __init__(innerSelf, Window):
                innerSelf.Window = Window
            def windowClosing(innerSelf, Event):
                try:
                    innerSelf.Window.HandleUserClose()
                except:
                    pass

        self.RefreshListener = RefreshPCL(self)
        self.CloseAdapter = WindowCloseAdapter(self)
        self.frame.addWindowListener(self.CloseAdapter)

        try:
            TTMem.addPropertyChangeListener(self.RefreshListener)
        except:
            pass
        try:
            DayMem.addPropertyChangeListener(self.RefreshListener)
        except:
            pass
        try:
            TimeMem.addPropertyChangeListener(self.RefreshListener)
        except:
            pass
        try:
            OverridesMem.addPropertyChangeListener(self.RefreshListener)
        except:
            pass
        try:
            DepartTPMem.addPropertyChangeListener(self.RefreshListener)
        except:
            pass
        try:
            EcsFilterMem.addPropertyChangeListener(self.RefreshListener)
        except:
            pass
        try:
            PAR.addPlatformListener(self.RefreshListener)
        except:
            pass


        # Refresh on fast clock changes even if no Memory event is fired.
        self.LastNowMinutes = None
        self.TimeTickTimer = None
        try:
            self.LastNowMinutes = CurrentMinutes()
        except:
            self.LastNowMinutes = None
        try:
            def _OnTimeTick(ev):
                try:
                    nowM = CurrentMinutes()
                except:
                    nowM = None
                if nowM is None:
                    return
                try:
                    if self.LastNowMinutes is None or int(nowM) != int(self.LastNowMinutes):
                        self.LastNowMinutes = int(nowM)
                        self.RequestRefresh(None)
                except:
                    self.LastNowMinutes = nowM
                    self.RequestRefresh(None)
            self.TimeTickTimer = Timer(1000, _OnTimeTick)
            self.TimeTickTimer.setRepeats(True)
            self.TimeTickTimer.start()
        except:
            self.TimeTickTimer = None
        self.RequestRefresh(None)
        self.frame.setVisible(True)

    def RequestRefresh(self, e=None):
        def _Do():
            try:
                self.refresh(e)
            except:
                pass
        RunOnEDT(_Do)

    def _CallDelay(self, idx):
        d = 0
        try:
            d = idx * int(STAGGER_ROW_MS)
        except:
            d = 0
        try:
            jm = int(STAGGER_JITTER_MS)
        except:
            jm = 0
        if jm > 0:
            try:
                d += random.randint(0, jm)
            except:
                pass
        return d

    def _AnimateDestination(self, text):
        dest = str(text or "").upper()
        chatter = []
        if CHATTER_STEPS > 0 and self.flapDest.curTop != dest:
            pool = []
            try:
                for r in CsvRows():
                    d = (r.get("Destination", "") or "").strip()
                    if d:
                        pool.append(d.upper())
            except:
                pool = []
            pool = [p for p in pool if p]
            for k in range(int(CHATTER_STEPS)):
                try:
                    chatter.append((random.choice(pool), ""))
                except:
                    chatter.append(("", ""))
        self.flapDest.AnimateTo(dest, "", chatter, 0)

    def refresh(self, e=None):
        svc = PickNextTrainForPlatform(self.platform)
        if not svc:
            self._AnimateDestination("")
            for fp in self.callFlaps:
                fp.ClearSpecialColors()
                fp.AnimateTo("", "", [], 0)
            return

        self._AnimateDestination(svc.get("dest", ""))

        msg = None
        specialText = (svc.get("special", "") or "").strip()
        if svc.get("ecs", False):
            msg = "ecs"
        elif svc.get("cancelled", False):
            msg = "cancel"
        elif svc.get("delayed", False):
            msg = "delay"
        elif specialText != "":
            msg = "special"

        stops = [t.strip() for t in str(svc.get("call", "") or "").split(",") if t.strip()]
        if not stops:
            if msg == "ecs":
                stops = []
            else:
                stops = ["NON-STOP"]

        maxLines = 8 if msg is None else 6
        packed = PackCallingLines(stops, FLAP_W, maxLines)
        callPools = GetCallingLinePoolsCached(8)
        while len(packed) < maxLines:
            packed.append("")

        callFlapCount = 4 if msg is None else 3
        li = 0
        for i in range(callFlapCount):
            top = packed[li] if li < len(packed) else ""
            bot = packed[li + 1] if (li + 1) < len(packed) else ""
            li += 2
            self.callFlaps[i].ClearSpecialColors()
            chatterPairs = BuildCallingChatterPairs(i, self.callFlaps[i].curTop, self.callFlaps[i].curBot, top, bot, callPools, CHATTER_STEPS)
            self.callFlaps[i].AnimateTo(top, bot, chatterPairs, self._CallDelay(i))

        if msg is None:
            return
        bottom = self.callFlaps[3]
        if msg == "ecs":
            bottom.SetSpecialColors(WHITE, RED)
            t1, t2 = WrapMessageTwoLines("Train not for public use", FLAP_W)
            bottom.AnimateTo(t1, t2, [], self._CallDelay(3))
        elif msg == "cancel":
            bottom.SetSpecialColors(RED, WHITE)
            bottom.AnimateTo("Cancelled", "Cancelled", [], self._CallDelay(3))
        elif msg == "delay":
            bottom.SetSpecialColors(YELLOW, PURE_BLK)
            t1, t2 = WrapMessageTwoLines("Train delayed. Listen for announcements", FLAP_W)
            bottom.AnimateTo(t1, t2, [], self._CallDelay(3))
        else:
            # Special text from timetable (PIDSolari special style/keywords)
            sbg, sfg = GetSpecialStyleForMessage(specialText)
            bottom.SetSpecialColors(sbg, sfg)
            t1, t2 = WrapMessageTwoLines(specialText, FLAP_W)
            bottom.AnimateTo(t1, t2, [], self._CallDelay(3))

    def HandleUserClose(self):
        try:
            self.cleanup()
        except:
            pass
        try:
            if self.OnCloseCallback is not None:
                self.OnCloseCallback(self.platform, self)
        except:
            pass
        try:
            self.frame.dispose()
        except:
            pass

    def cleanup(self):
        if self.CleanedUp:
            return
        self.CleanedUp = True

        try:
            if self.TimeTickTimer is not None:
                self.TimeTickTimer.stop()
        except:
            pass
        self.TimeTickTimer = None

        try:
            if self.CloseAdapter is not None:
                self.frame.removeWindowListener(self.CloseAdapter)
        except:
            pass

        L = self.RefreshListener
        try:
            if L is not None:
                TTMem.removePropertyChangeListener(L)
        except:
            pass
        try:
            if L is not None:
                DayMem.removePropertyChangeListener(L)
        except:
            pass
        try:
            if L is not None:
                TimeMem.removePropertyChangeListener(L)
        except:
            pass
        try:
            if L is not None:
                OverridesMem.removePropertyChangeListener(L)
        except:
            pass
        try:
            if L is not None:
                DepartTPMem.removePropertyChangeListener(L)
        except:
            pass
        try:
            if L is not None:
                EcsFilterMem.removePropertyChangeListener(L)
        except:
            pass
        try:
            PAR.removePlatformListener(L)
        except:
            pass

        self.RefreshListener = None
        self.CloseAdapter = None

# -----------------------------------------------------------------------------
# Manager
# -----------------------------------------------------------------------------

class SolariSinglePlatformManager(object):
    def __init__(self):
        self.windows = {}
        self.build()
        try:
            TTMem.addPropertyChangeListener(self.rebuild)
        except:
            pass

    def UnregisterPlatform(self, Platform, WindowObj):
        try:
            p = str(Platform)
        except:
            p = Platform
        try:
            if p in self.windows and self.windows.get(p) is WindowObj:
                del self.windows[p]
        except:
            pass

    def build(self):
        plats = set()
        for r in CsvRows():
            p = PlatformField(r)
            if p:
                plats.add(p)

        for p in sorted(plats, key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s)):
            if p not in self.windows:
                self.windows[p] = SolariSinglePIDWindow(p, self.UnregisterPlatform)

        for p in [x for x in list(self.windows.keys()) if x not in plats]:
            try:
                self.windows[p].cleanup()
                self.windows[p].frame.dispose()
            except:
                pass
            try:
                del self.windows[p]
            except:
                pass

        x0, y0, dx, dy = 40, 40, 16, 16
        for i, p in enumerate(sorted(self.windows.keys(), key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s))):
            try:
                self.windows[p].frame.setLocation(x0 + dx * i, y0 + dy * i)
            except:
                pass

    def rebuild(self, e=None):
        self.build()


PIDSolariSingle_Manager = SolariSinglePlatformManager()
