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
# Solari-style indicator: multiple boards side-by-side; compact width; unified text size; change-only animation.
# JMRI 5.14 / Jython 2.7 / ASCII only / CamelCase / Thread-safe EDT.

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, BasicStroke, RenderingHints
from javax.swing import Timer
from java.awt.image import BufferedImage
import java.awt.font.TextAttribute as TextAttribute

import jmri
from jmri import InstanceManager
import os, csv, random

# TAS helpers and registers (same contracts as PIDLarge.py)
import TASBeanLookup as TBL
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption

# --------------------------- Scale and simple config -----------------------
def ReadInt(memName, defaultVal, minVal=None, maxVal=None):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(memName, str(int(defaultVal)))
        n = int(float(str(raw).strip()))
        if minVal is not None: n = max(minVal, n)
        if maxVal is not None: n = min(maxVal, n)
        return int(n)
    except:
        return int(defaultVal)

def ReadBool(memName, defaultVal=False):
    try:
        raw = TBL.SafeGetOrCreateMemoryValue(memName, "true" if defaultVal else "false")
        t = (str(raw).strip().lower())
        if t in ["1", "true", "yes", "y", "on", "enabled"]: return True
        if t in ["0", "false", "no", "n", "off", "disabled"]: return False
        return bool(defaultVal)
    except:
        return bool(defaultVal)

# Global scale: default 60% 
SCALE_PCT = ReadInt("TAS_USER_SETTING_SOLARI_SCALE_PERCENT", 70, 35, 120)
S = float(SCALE_PCT) / 100.0
def Sc(x): return int(round(float(x) * S))

# --------------------------- Colours and geometry --------------------------
PANEL_BG = Color(18, 18, 18)  # slightly lighter surround to make flaps stand out
FLAP_BG = Color(11, 11, 11)  # flap face (was former panel background)
PURE_BLK = Color(0, 0, 0)
TEXT_WHT = Color(242, 242, 242)
YELLOW   = Color(255, 211, 0)
RED      = Color(200, 16, 46)

HingeRatio  = 0.50

OUTER_PAD   = Sc(12)           # slightly tighter side pad
BOARD_GAP   = Sc(10)           # between boards
LINE_GAP    = Sc(6)

FLAP_H      = Sc(48)           # single-line flap height (used for time/platform too)
DOUBLE_H    = Sc(72)           # two-line calling flap height

TOP_LINE_H  = Sc(58)
PLAT_LINE_H = Sc(50)


def PaintFlapFrame(g2, w, h, bgColor, frameColor, hingeY=None):
    # Paint a pixel-aligned flap with a plain black frame and hinge.
    # The frame is outside the flap face area to avoid edge artefacts on light backgrounds.
    try:
        ww = int(w)
        hh = int(h)
    except:
        ww = w
        hh = h

    t = Sc(2)
    if t < 1:
        t = 1
    if ww < 2 or hh < 2:
        return

    # Fill full component with the frame color first.
    g2.setColor(frameColor)
    g2.fillRect(0, 0, ww, hh)

    # Fill the flap face inside the frame.
    innerW = ww - (2 * t)
    innerH = hh - (2 * t)
    if innerW > 0 and innerH > 0:
        g2.setColor(bgColor)
        g2.fillRect(t, t, innerW, innerH)

    # Hinge line across the face.
    if hingeY is not None:
        try:
            hy = int(hingeY)
        except:
            hy = 0
        y = hy - (t // 2)
        if y < 0:
            y = 0
        if y > hh - t:
            y = hh - t
        g2.setColor(frameColor)
        g2.fillRect(0, y, ww, t)


def DrawHingeOver(g2, w, h, frameColor):
    # Draw the hinge line over any text so it remains visible through unified text flaps.
    try:
        ww = int(w)
        hh = int(h)
    except:
        ww = w
        hh = h

    t = Sc(2)
    if t < 1:
        t = 1

    try:
        hy = int(float(h) * float(HingeRatio))
    except:
        try:
            hy = int(hh * 0.5)
        except:
            hy = 0

    y = hy - (t // 2)
    if y < 0:
        y = 0
    if y > hh - t:
        y = hh - t

    g2.setColor(frameColor)
    g2.fillRect(0, y, ww, t)

def AvailableFamilies():
    try:
        ge = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
        return [str(f) for f in ge.getAvailableFontFamilyNames()]
    except:
        return []

def PickFamily():
    # Fallback order per your instruction
    prefs = ["BritishRailLightNormal", "Helvetica", "Liberation Sans", "Arial", "SansSerif"]
    fams = set([f.lower() for f in AvailableFamilies()])
    for p in prefs:
        if p.lower() in fams: return p
    return "SansSerif"

FONT_FAM  = PickFamily()
# Single-line font for Destination, Time digits, Platform digits (exactly the same)
FONT_BIG  = Sc(28)
FONT_MID  = Sc(24)
FONT_CALL = Sc(22)  # per half of calling flap
FONT_DIGIT = Sc(24)

def MakeFont(sz, bold=False):
    style = Font.BOLD if bold else Font.PLAIN
    return Font(FONT_FAM, style, int(sz))
    
def FitTextForFlap(text, flapWidth, twoLine=False):
    # Match SolariFlap.DrawTextLine truncation strategy so animation frames do not "jump"
    s = str(text or "")

    margin = Sc(12)
    maxWidth = int(flapWidth) - 2 * margin
    if maxWidth < 4:
        maxWidth = 4

    # Choose the same font as SolariFlap.DrawTextLine would choose
    f = MakeFont(FONT_BIG if not twoLine else FONT_CALL, bold=False)

    # Offscreen metrics (safe and deterministic)
    img = BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB)
    g2 = img.createGraphics()
    try:
        fm = g2.getFontMetrics(f)
        if fm.stringWidth(s) <= maxWidth:
            return s

        # Try the same tracking reduction as SolariFlap.DrawTextLine
        try:
            attrs = {TextAttribute.TRACKING: -0.04}
            f2 = f.deriveFont(attrs)
            fm2 = g2.getFontMetrics(f2)

            if fm2.stringWidth(s) > maxWidth:
                t = s
                while len(t) > 1 and fm2.stringWidth(t + "...") > maxWidth:
                    t = t[:-1]
                if len(t) > 1:
                    t = t + "..."
                return t

            # Tracking alone was enough; keep the original string
            # (paint-time may apply tracking if needed)
            return s
        except:
            # Fallback truncation without tracking
            t = s
            while len(t) > 1 and fm.stringWidth(t + "...") > maxWidth:
                t = t[:-1]
            if len(t) > 1:
                t = t + "..."
            return t
    finally:
        try:
            g2.dispose()
        except:
            pass


# --------------------------- Time parsing (PIDLarge) -----------------------
import java.text.SimpleDateFormat as SimpleDateFormat
Fmt24    = SimpleDateFormat("HH:mm")
Parser12 = SimpleDateFormat("h:mm a")
Parser24 = SimpleDateFormat("H:mm")

def ParseMinutes(s):
    s = (s or "").strip()
    if s == "": return None
    for p in [Parser12, Parser24]:
        try:
            d = p.parse(s)
            return d.getHours()*60 + d.getMinutes()
        except:
            pass
    try:
        if ":" in s and len(s) <= 5:
            h, m = s.split(":")
            return int(h)*60 + int(m)
    except:
        pass
    return None

def MinutesToHHmm(total):
    if total is None: return ""
    total %= (24*60)
    h = total // 60
    m = total % 60
    return ("%02d:%02d" % (h, m))

def FormatHHmm(schedText):
    for p in [Parser12, Parser24]:
        try:
            d = p.parse(schedText)
            return Fmt24.format(d)
        except:
            pass
    s = (schedText or "").strip()
    return s if (":" in s and len(s) <= 5) else s

# ------------------------------- CSV access --------------------------------
def TimetablePath():
    name = TBL.SafeGetOrCreateMemoryValue("CURRENTTIMETABLE", "").strip()
    if name == "": return None
    try:
        prof = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    except:
        return None
    return os.path.join(prof, "timetable", name + ".csv")

def CsvRows():
    path = TimetablePath()
    if not (path and os.path.exists(path)): return []
    out = []
    try:
        import csv as _csv
        with open(path, "r") as f:
            rdr = _csv.DictReader(f, delimiter="\t")  # like PIDLarge
            for r in rdr: out.append(r)
    except:
        return []
    return out

def CaseInsensitive(row, key):
    target = (key or "").strip().lower()
    for k in (row.keys() or []):
        if (k or "").strip().lower() == target:
            v = row.get(k, "")
            return (v or "").strip()
    return ""

def PlatformField(row):
    val = (row.get("Plat","") or "").strip()
    if val == "": val = (row.get("Platform","") or "").strip()
    return val

# ---------------------------- TAS user settings ----------------------------

DELAY_THRESHOLD_MIN = ReadInt("TAS_USER_SETTING_DELAY_THRESHOLD_MINUTES", 2, 0, 60)
CHATTER_STEPS       = ReadInt("TAS_USER_SETTING_SOLARI_CHATTER_STEPS", 2, 0, 4)
ANIM_MS_PER_HALF    = ReadInt("TAS_USER_SETTING_SOLARI_ANIM_MS_PER_HALF", 70, 35, 400)
DIGIT_FPS           = ReadInt("TAS_USER_SETTING_SOLARI_DIGIT_FPS", 60, 30, 75)

# Transition timing: blank stage hold and board cascade
BLANK_HOLD_MS        = ReadInt("TAS_USER_SETTING_SOLARI_BLANK_HOLD_MS", 300, 0, 2000)
BLANK_CHATTER_STEPS  = ReadInt("TAS_USER_SETTING_SOLARI_BLANK_CHATTER_STEPS", CHATTER_STEPS, 0, 12)
BOARD_CASCADE_MS     = ReadInt("TAS_USER_SETTING_SOLARI_BOARD_CASCADE_MS", 4500, 0, 30000)
HIDE_PLAT_UNTIL_ALLOC = ReadBool("TAS_USER_SETTING_HIDE_PLATFORM_UNTIL_ALLOCATED", False)

# Start stagger and extra running time
STAGGER_ROW_MS = ReadInt("TAS_USER_SETTING_SOLARI_STAGGER_ROW_MS", 350, 0, 3000)
STAGGER_JITTER_MS = ReadInt("TAS_USER_SETTING_SOLARI_STAGGER_JITTER_MS", 250, 0, 3000)

# Extra "running" steps to randomise stop times (0 disables)
EXTRA_WORD_STEPS_MAX = ReadInt("TAS_USER_SETTING_SOLARI_EXTRA_WORD_STEPS_MAX", 3, 0, 12)
EXTRA_DIGIT_CYCLES_MAX = ReadInt("TAS_USER_SETTING_SOLARI_EXTRA_DIGIT_CYCLES_MAX", 1, 0, 6)

# ECS message (shown when the service is already being displayed as ECS)
ECS_MESSAGE = TBL.SafeGetOrCreateMemoryValue("TAS_USER_SETTING_ECS_MESSAGE", "Not for public use")

MEM_Cols            = "TAS_USER_SETTING_STRIP_COLUMNS"  # sam

# Compact board width expansion: increase compact width by this percent 
WIDTH_EXPAND_PCT    = ReadInt("TAS_USER_SETTING_SOLARI_WIDTH_EXPAND_PERCENT", 25, 0, 100)
WIDTH_EXPAND_FACTOR = 1.0 + (float(WIDTH_EXPAND_PCT) / 100.0)

# Calling pattern mechanical gaps (computed from timetable on each refresh)
CALL_GAP_MAPS_BY_DEST = {}

def _ParseStopsFromCallPattern(callText):
    out = []
    for t in str(callText or "").split(","):
        s = (t or "").strip()
        if s != "":
            out.append(s)
    return out

def _BuildGapMaps(rowsToday):
    byDestSeqs = {}
    for r in (rowsToday or []):
        try:
            destKey = (CaseInsensitive(r, "Destination") or "").strip().upper()
        except:
            destKey = ""
        if destKey == "":
            continue
        seq = _ParseStopsFromCallPattern(CaseInsensitive(r, "Calling pattern"))
        if not seq:
            continue
        byDestSeqs.setdefault(destKey, []).append(seq)

    gapMaps = {}
    for destKey, seqs in byDestSeqs.items():
        gm = {}
        try:
            for seq in seqs:
                n = len(seq)
                for i in range(n):
                    a = seq[i]
                    for j in range(i + 1, n):
                        b = seq[j]
                        gap = j - i - 1
                        key = (a, b)
                        old = gm.get(key, 0)
                        if gap > old:
                            gm[key] = gap
        except:
            gm = {}

        ok = True
        try:
            for seq in seqs:
                newLen = len(seq)
                for i in range(len(seq) - 1):
                    newLen += int(gm.get((seq[i], seq[i+1]), 0))
                if newLen > 20:
                    ok = False
                    break
        except:
            ok = False
        if ok and gm:
            gapMaps[destKey] = gm

    return gapMaps

def _ApplyGapsToStops(stops, destKey):
    gm = CALL_GAP_MAPS_BY_DEST.get(destKey) if destKey else None
    if not gm:
        return stops
    out = []
    try:
        for i in range(len(stops)):
            out.append(stops[i])
            if i < len(stops) - 1:
                gap = int(gm.get((stops[i], stops[i+1]), 0))
                for k in range(gap):
                    out.append("")
    except:
        return stops
    return out

def ActiveProfileNameUpper():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        s = ("" if nm is None else str(nm)).strip()
        return s.upper()
    except:
        return ""

# ------------------------------ Fast clock ---------------------------------
Timebase = InstanceManager.getDefault(jmri.Timebase)
DayMem   = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimeMem  = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
TTMem    = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")

def CurrentMinutes():
    try:
        if Timebase is not None:
            ft = Timebase.getTime()
            return ft.getHours()*60 + ft.getMinutes()
    except:
        pass
    curStr = TBL.SafeGetOrCreateMemoryValue("CURRENTTIME", "")
    return ParseMinutes(curStr)

# ------------------------------ Service model ------------------------------
def HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    try:
        tps = []
        raw = TBL.SafeGetOrCreateMemoryValue("PID_DEPARTURE_TP", "")
        if raw:
            for p in str(raw).replace(",", ";").split(";"):
                t = (p or "").strip()
                if t != "": tps.append(t)
        if not tps:
            try:
                nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
                base = ("" if nm is None else str(nm)).strip()
                if base != "": tps = [base]
            except:
                pass
        for tp in (tps or []):
            try: entries = TR.getTiming(tp) or []
            except: entries = []
            for rec in entries:
                try: rn = rec[0]; tstr = rec[2]; d = rec[3]
                except: continue
                if str(rn) != str(reportingNumber): continue
                if str(d) != str(dayName): continue
                mm = ParseMinutes(tstr)
                if mm is None: continue
                if mm <= int(nowMinutes): return True
    except:
        pass
    return False

def ResolveDelayWithInheritance(rowsToday, rn, schedDepMin, visited=None):
    if visited is None: visited = set()
    if rn in visited: return ("ontime", 0)
    visited.add(rn)
    try: d = getDisruption(rn)
    except: d = None
    if d is not None:
        try: delay = int(d)
        except: delay = 0
        if delay >= 1440: return ("cancel", None)
        if delay > 0: return ("delay", delay)
    formers = []
    for r in rowsToday:
        if (CaseInsensitive(r, "Forms") or "") == rn:
            arr = CaseInsensitive(r, "Arr")
            arrMin = ParseMinutes(arr) if arr else None
            formers.append((r, arrMin))
    if not formers: return ("ontime", 0)
    chosen = None
    if schedDepMin is not None:
        before = [t for t in formers if t[1] is not None and t[1] <= schedDepMin]
        if before:
            before.sort(key=lambda t: t[1])
            chosen = before[-1][0]
    if chosen is None: chosen = formers[0][0]
    formerRN = CaseInsensitive(chosen, "Reporting number")
    return ResolveDelayWithInheritance(rowsToday, formerRN, schedDepMin, visited)

class Service(object):
    def __init__(self, row, dayName, nowMinutes):
        self.RN   = CaseInsensitive(row, "Reporting number")
        self.Dep  = CaseInsensitive(row, "Dep")
        self.DepMin = ParseMinutes(self.Dep)
        self.Dest = CaseInsensitive(row, "Destination")
        self.Via  = CaseInsensitive(row, "Via")
        self.Co   = CaseInsensitive(row, "Company")
        self.Call = CaseInsensitive(row, "Calling pattern")
        alloc = PAR.getPlatform(self.RN)
        self.HasAlloc = (alloc is not None and str(alloc).strip() != "")
        if self.HasAlloc:
            platVal = str(alloc).strip()
        else:
            platVal = (PlatformField(row) or "").strip()
        if HIDE_PLAT_UNTIL_ALLOC and (not self.HasAlloc):
            platVal = ""
        self.Plat = platVal
        self.Departed = HasDepartedAtConfiguredTP(self.RN, dayName, nowMinutes)
        self.Status = ""
        self.ShowTime = FormatHHmm(self.Dep)
        self.AdjMin = self.DepMin if self.DepMin is not None else 9999

def NextServices(count):
    rows = CsvRows()
    day = TBL.SafeGetOrCreateMemoryValue("DAYOFWEEK", "")
    now = CurrentMinutes()
    if now is None: return [], [], [], set()
    rowsToday = [r for r in rows if ((r.get(day,"") or "").strip().lower() == "true")]
    models = []
    for r in rowsToday:
        dep = CaseInsensitive(r, "Dep")
        if dep == "": continue
        m = Service(r, day, now)
        if m.DepMin is None: continue
        if m.DepMin < now: continue
        if m.Departed: continue
        kind, val = ResolveDelayWithInheritance(rowsToday, m.RN, m.DepMin, visited=set())
        if kind == "cancel":
            m.Status = "CANCELLED"; m.ShowTime = "CANCELLED"; m.AdjMin = 9999
        elif kind == "delay" and val and val > 0:
            m.Status = "Delayed" if val >= DELAY_THRESHOLD_MIN else "On time"
            m.ShowTime = MinutesToHHmm(m.DepMin + val)
            m.AdjMin = m.DepMin + val
        else:
            m.Status = "On time"; m.ShowTime = FormatHHmm(m.Dep); m.AdjMin = m.DepMin
        models.append(m)
    models.sort(key=lambda t: t.AdjMin)

    destPool, viaPool, platCharsSet = [], [], set()
    maxPlatNum = 0
    for r in rowsToday:
        d = CaseInsensitive(r, "Destination")
        v = CaseInsensitive(r, "Via")
        if d:
            try:
                if (d or "").strip().upper() != ActiveProfileNameUpper():
                    destPool.append(d)
            except:
                destPool.append(d)
        if v: viaPool.append(v)
        pf = PlatformField(r)
        try:
            if (pf or "").isdigit():
                nPlat = int(pf)
                if nPlat > maxPlatNum: maxPlatNum = nPlat
        except:
            pass
        for ch in (pf or ""): platCharsSet.add(ch)
    global CALL_GAP_MAPS_BY_DEST
    CALL_GAP_MAPS_BY_DEST = _BuildGapMaps(rowsToday)
    return models[:count], destPool, viaPool, platCharsSet, maxPlatNum


# ------------------ Flap base ------------------
from java.lang import System

class SolariAnimClock(object):
    # Single shared Swing Timer for all active flaps.
    TimerObj = None
    Active = {}
    LastMs = None
    Interval = None

    @classmethod
    def _GetInterval(cls):
        try:
            fps = int(ReadInt("TAS_USER_SETTING_SOLARI_DIGIT_FPS", 60, 30, 75))
        except:
            fps = 60
        if fps <= 0:
            fps = 60
        iv = int(max(1000 // fps, 15))
        return iv

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
        if flap is None:
            return
        try:
            cls.Active.pop(id(flap), None)
        except:
            pass
        if not cls.Active:
            cls._Stop()

    @classmethod
    def StopAll(cls):
        try:
            cls.Active = {}
        except:
            pass
        cls._Stop()

    @classmethod
    def _EnsureRunning(cls):
        iv = cls._GetInterval()
        if cls.TimerObj is None:
            cls.Interval = iv
            cls.LastMs = System.currentTimeMillis()
            cls.TimerObj = Timer(iv, cls._OnTick)
            cls.TimerObj.setRepeats(True)
            cls.TimerObj.start()
        else:
            try:
                if int(cls.Interval) != int(iv):
                    cls.Interval = iv
                    cls.TimerObj.setDelay(iv)
            except:
                pass
            try:
                if not cls.TimerObj.isRunning():
                    cls.LastMs = System.currentTimeMillis()
                    cls.TimerObj.start()
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
        cls.Interval = None

    @classmethod
    def _OnTick(cls, e):
        now = System.currentTimeMillis()
        try:
            last = cls.LastMs
            if last is None:
                dt = cls.Interval if cls.Interval is not None else 16
            else:
                dt = int(now - last)
                if dt < 1:
                    dt = 1
        except:
            dt = 16
        cls.LastMs = now

        try:
            activeList = list(cls.Active.values())
        except:
            try:
                activeList = cls.Active.values()
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
        super(SolariFlap, self).__init__()
        self.setOpaque(False)
        self.w = int(w)
        self.h = int(h)
        self.twoLine = bool(twoLine)
        self.curTop = ""
        self.curBot = ""
        self.targetTop = ""
        self.targetBot = ""
        self.phase = "idle"
        self.t = 0.0
        self.queue = []
        self.pendingTimer = None

        # Base timing (per half). Kept compatible with your existing setting.
        self.msPerHalf = int(ReadInt("TAS_USER_SETTING_SOLARI_ANIM_MS_PER_HALF", 70, 33, 400))

        self.setSize(self.w, self.h)

    def TextColor(self):
        return TEXT_WHT

    def EaseInOut(self, x):
        # Smoothstep: 3x^2 - 2x^3 (slow start/end, fast in middle).
        try:
            t = float(x)
        except:
            t = 0.0
        if t < 0.0:
            t = 0.0
        if t > 1.0:
            t = 1.0
        t2 = t * t
        t3 = t2 * t
        return (3.0 * t2) - (2.0 * t3)

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, FLAP_BG, PURE_BLK, hingeY=hingeY)

            if self.phase == "idle":
                self.DrawTopText(g2, self.curTop)
                self.DrawBottomText(g2, self.curBot)

            elif self.phase == "fullFlip":
                # One physical flap: reveal new content from top->bottom across the entire flap.
                oldTop = getattr(self, "prevFullTop", self.curTop)
                oldBot = getattr(self, "prevFullBot", self.curBot)
                newTop = getattr(self, "nextTop", self.curTop)
                newBot = getattr(self, "nextBot", self.curBot)

                frac = self.EaseInOut(self.t)
                reveal = int(round(frac * float(self.h)))
                if reveal < 0:
                    reveal = 0
                if reveal > self.h:
                    reveal = self.h

                # New region (top of flap)
                if reveal > 0:
                    g2.setClip(awt.Rectangle(0, 0, self.w, reveal))
                    self.DrawTopText(g2, newTop)
                    self.DrawBottomText(g2, newBot)

                # Old region (bottom of flap)
                if reveal < self.h:
                    g2.setClip(awt.Rectangle(0, reveal, self.w, self.h - reveal))
                    self.DrawTopText(g2, oldTop)
                    self.DrawBottomText(g2, oldBot)

                try:
                    g2.setClip(None)
                except:
                    pass

            elif self.phase == "topFlip":
                # Legacy half-flip behaviour (used by single-line flaps where top/bottom are the same text).
                self.DrawFlipHalf(g2, half="top")
                self.DrawBottomText(g2, self.curBot)

            elif self.phase == "bottomFlip":
                self.DrawTopText(g2, self.curTop)
                self.DrawFlipHalf(g2, half="bottom")

            else:
                self.DrawTopText(g2, self.curTop)
                self.DrawBottomText(g2, self.curBot)

        finally:
            try:
                g2.setClip(None)
            except:
                pass
            g2.dispose()

    def DrawTopText(self, g2, text):
        self.DrawTextLine(g2, text, top=True, colorOverride=None)

    def DrawBottomText(self, g2, text, colorOverride=None):
        self.DrawTextLine(g2, text, top=False, colorOverride=colorOverride)

    def DrawTextLine(self, g2, text, top, colorOverride=None):
        g2.setColor(colorOverride if colorOverride is not None else self.TextColor())
        margin = Sc(12)

        halfH = int(self.h * HingeRatio) if top else (self.h - int(self.h * HingeRatio))
        y0 = 0 if top else int(self.h * HingeRatio)

        f = MakeFont(FONT_BIG if not self.twoLine else FONT_CALL, bold=False)
        s = str(text or "")
        fm = g2.getFontMetrics(f)
        maxWidth = self.w - 2 * margin

        if fm.stringWidth(s) > maxWidth:
            try:
                attrs = {TextAttribute.TRACKING: -0.04}
                f2 = f.deriveFont(attrs)
                fm2 = g2.getFontMetrics(f2)
                if fm2.stringWidth(s) > maxWidth:
                    while len(s) > 1 and fm2.stringWidth(s + "...") > maxWidth:
                        s = s[:-1]
                    if len(s) > 1:
                        s = s + "..."
                g2.setFont(f2)
            except:
                while len(s) > 1 and fm.stringWidth(s + "...") > maxWidth:
                    s = s[:-1]
                if len(s) > 1:
                    s = s + "..."
                g2.setFont(f)
        else:
            g2.setFont(f)

        fm = g2.getFontMetrics()
        baseline = y0 + (halfH + fm.getAscent()) // 2 - 2
        g2.drawString(s, margin, baseline)

    def _DrawReveal(self, g2, y0, hh, oldTxt, newTxt, drawFuncOld, drawFuncNew, revealPx):
        # Reveal new from top->bottom within this half; old remains below reveal line.
        if hh <= 0:
            return

        r = int(revealPx)
        if r < 0:
            r = 0
        if r > hh:
            r = hh

        # New region (top of half)
        if r > 0:
            g2.setClip(awt.Rectangle(0, y0, self.w, r))
            drawFuncNew(g2, newTxt)

        # Old region (bottom of half)
        if r < hh:
            g2.setClip(awt.Rectangle(0, y0 + r, self.w, hh - r))
            drawFuncOld(g2, oldTxt)

        try:
            g2.setClip(None)
        except:
            pass

    def DrawFlipHalf(self, g2, half):
        # Head-on split-flap: progressively reveal what is behind from top->bottom,
        # with ease-in-out speed profile.
        hingeY = int(self.h * HingeRatio)
        frac = self.EaseInOut(self.t)

        if half == "top":
            y0 = 0
            hh = hingeY

            oldTxt = self.curTop
            newTxt = getattr(self, "nextTop", self.curTop)

            reveal = int(round(frac * hh))

            self._DrawReveal(
                g2, y0, hh,
                oldTxt, newTxt,
                lambda gg, s: self.DrawTopText(gg, s),
                lambda gg, s: self.DrawTopText(gg, s),
                reveal
            )
        else:
            y0 = hingeY
            hh = self.h - hingeY

            oldTxt = self.curBot
            newTxt = getattr(self, "nextBot", self.curBot)

            reveal = int(round(frac * hh))

            self._DrawReveal(
                g2, y0, hh,
                oldTxt, newTxt,
                lambda gg, s: self.DrawBottomText(gg, s),
                lambda gg, s: self.DrawBottomText(gg, s),
                reveal
            )

    def AnimateTo(self, targetTop, targetBot, chatterPairs, startDelayMs=0):
        # Cancel any pending start
        try:
            if self.pendingTimer is not None:
                self.pendingTimer.stop()
        except:
            pass
        self.pendingTimer = None

        # Stop any active clock participation
        try:
            SolariAnimClock.Unregister(self)
        except:
            pass

        self.phase = "idle"
        self.t = 0.0

        self.targetTop = str(targetTop or "")
        self.targetBot = str(targetBot or "")

        if (self.curTop == self.targetTop) and (self.curBot == self.targetBot):
            return

        seq = []
        for p in (chatterPairs or []):
            try:
                a = p[0]
            except:
                a = ""
            try:
                b = p[1]
            except:
                b = ""
            seq.append((a, b))
        seq.append((self.targetTop, self.targetBot))
        self.queue = seq

        if self.queue:
            first = self.queue.pop(0)
        else:
            first = None

        dly = 0
        try:
            dly = int(startDelayMs)
        except:
            dly = 0

        if dly > 0:
            self.phase = "pending"
            self._pendingFirst = first

            def _StartLater(e):
                try:
                    if self.pendingTimer is not None:
                        self.pendingTimer.stop()
                except:
                    pass
                self.pendingTimer = None
                self.phase = "idle"
                self.StartTopHalf(self._pendingFirst)
                try:
                    del self._pendingFirst
                except:
                    pass

            self.pendingTimer = Timer(dly, _StartLater)
            self.pendingTimer.setRepeats(False)
            self.pendingTimer.start()
        else:
            self.StartTopHalf(first)

    def StartTopHalf(self, nextPair):
        if nextPair is None:
            try:
                self.prevTopForBottom = self.curTop
            except:
                pass
            self.phase = "idle"
            self.repaint()
            try:
                SolariAnimClock.Unregister(self)
            except:
                pass
            return

        try:
            self.prevTopForBottom = self.curTop
        except:
            pass

        self.nextTop = nextPair[0]
        self.nextBot = nextPair[1]

        # Snapshot the current full flap content for a full-height reveal.
        try:
            self.prevFullTop = self.curTop
            self.prevFullBot = self.curBot
        except:
            pass

        # If this represents one physical flap with two printed lines, use fullFlip.
        useFull = False
        try:
            if self.twoLine:
                useFull = True
        except:
            pass
        try:
            if str(self.curBot or "").strip() != "":
                useFull = True
        except:
            pass
        try:
            if str(self.nextBot or "").strip() != "":
                useFull = True
        except:
            pass

        self.phase = "fullFlip" if useFull else "topFlip"
        self.t = 0.0

        try:
            SolariAnimClock.Register(self)
        except:
            pass
        self.repaint()

    def StartBottomHalf(self):
        self.phase = "bottomFlip"
        self.t = 0.0
        try:
            SolariAnimClock.Register(self)
        except:
            pass
        self.repaint()

    def OnClockTick(self, dtMs):
        # Return True while active; False when idle so the clock can unregister us.
        try:
            if self.phase not in ["topFlip", "bottomFlip", "fullFlip"]:
                return False

            try:
                if self.phase == "fullFlip":
                    # fullFlip replaces top+bottom halves, so keep overall duration comparable
                    step = float(dtMs) / float(self.msPerHalf * 2.0)
                else:
                    step = float(dtMs) / float(self.msPerHalf)
            except:
                step = 0.25

            self.t += step

            if self.t >= 1.0:
                if self.phase == "fullFlip":
                    self.curTop = getattr(self, "nextTop", self.curTop)
                    self.curBot = getattr(self, "nextBot", self.curBot)
                    if self.queue:
                        nxt = self.queue.pop(0)
                        self.StartTopHalf(nxt)
                        return True
                    else:
                        self.phase = "idle"
                        self.t = 0.0
                        self.repaint()
                        return False

                elif self.phase == "topFlip":
                    self.curTop = getattr(self, "nextTop", self.curTop)
                    self.phase = "bottomFlip"
                    self.t = 0.0

                elif self.phase == "bottomFlip":
                    self.curBot = getattr(self, "nextBot", self.curBot)
                    if self.queue:
                        nxt = self.queue.pop(0)
                        self.StartTopHalf(nxt)
                        return True
                    else:
                        self.phase = "idle"
                        self.t = 0.0
                        self.repaint()
                        return False

            self.repaint()
            return True

        except:
            self.phase = "idle"
            self.t = 0.0
            try:
                self.repaint()
            except:
                pass
            return False

# ---------------------- Specialised flaps and helpers ----------------------
class LabelFixed(swing.JComponent):
    def __init__(self, text, size, bold=False, color=TEXT_WHT):
        super(LabelFixed, self).__init__()
        self.text = str(text or "")
        self.font = MakeFont(size, bold=bold)
        self.color = color
        self.setOpaque(False)
        # Ensure the component's font property reflects the constructor font
        try:
            self.setFont(self.font)
        except:
            pass

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setColor(self.color)
            # Use the component font if present; fall back to constructor font
            try:
                compFont = self.getFont()
            except:
                compFont = None
            useFont = compFont if compFont is not None else self.font
            g2.setFont(useFont)
            fm = g2.getFontMetrics()
            y = (self.getHeight() + fm.getAscent())//2 - 2
            # DEBUG (one-time): report colon metrics
            try:
                if getattr(self, "text", "") == ":" and not getattr(self, "_colon_debugged", False):
                    print("[PIDSolari] Colon paint: font=%s bounds=%s ascent=%d height=%d"
                          % (str(useFont), str(self.getBounds()), fm.getAscent(), self.getHeight()))
                    self._colon_debugged = True
            except:
                pass
            g2.drawString(self.text, 0, y)
        finally:
            g2.dispose()
            
        
class ColonFlapFixed(swing.JComponent):
    def __init__(self, w, h):
        super(ColonFlapFixed, self).__init__()
        self.setOpaque(False)
        self.w = int(w)
        self.h = int(h)
        self.setSize(self.w, self.h)

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

            # Match the digit flap styling           
            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, FLAP_BG, PURE_BLK, hingeY=hingeY)

            # Draw two dots (font-independent), tuned to match the visual baseline of the digits
            g2.setColor(TEXT_WHT)

            # Smaller dots than before; clamp so they never get oversized at large SCALE_PCT
            dotD = int(round(self.h * 0.07))
            dotD = max(2, dotD)
            dotD = min(dotD, Sc(4))

            r = dotD // 2

            # Center horizontally with a small border clearance
            cx = (self.w - dotD) // 2
            if cx < 2:
             cx = 2
            if cx > (self.w - dotD - 2):
             cx = max(2, self.w - dotD - 2)

            # Place the dots nearer the midline (not at 1/4 and 3/4), and raise slightly
            shiftUp = max(0, Sc(2))
            topCenterY = int(round(self.h * 0.44)) - shiftUp
            botCenterY = int(round(self.h * 0.60)) - shiftUp

            topCy = topCenterY - r
            botCy = botCenterY - r

            # Clamp within drawable area
            if topCy < 2:
             topCy = 2
            if topCy > (self.h - dotD - 2):
             topCy = max(2, self.h - dotD - 2)

            if botCy < 2:
             botCy = 2
            if botCy > (self.h - dotD - 2):
             botCy = max(2, self.h - dotD - 2)

            g2.fillOval(cx, topCy, dotD, dotD)
            g2.fillOval(cx, botCy, dotD, dotD)
            
        finally:
            DrawHingeOver(g2, self.w, self.h, PURE_BLK)
            g2.dispose()

class DigitFlap(SolariFlap):
    def __init__(self, w, h):
        SolariFlap.__init__(self, w, h, twoLine=False)
        
    def DrawTextLine(self, g2, text, top, colorOverride=None):
        g2.setColor(colorOverride if colorOverride is not None else self.TextColor())
        halfH = int(self.h * HingeRatio) if top else (self.h - int(self.h * HingeRatio))
        y0 = 0 if top else int(self.h * HingeRatio)

        s = str(text or "")

        f = MakeFont(FONT_DIGIT, bold=False)
        g2.setFont(f)
        fm = g2.getFontMetrics(f)

        # Center the single character horizontally; clamp away from the border
        wtxt = fm.stringWidth(s)
        x = (self.w - wtxt) // 2
        if x < 2:
            x = 2
        if x > (self.w - wtxt - 2):
            x = max(2, self.w - wtxt - 2)
    
        adjustDown = max(1, Sc(15))
        baseline = y0 + (halfH + fm.getAscent()) // 2 - 2 + adjustDown
        g2.drawString(s, x, baseline)
  
    def AnimateDigit(self, curCh, targetCh, ascending=True, allowed=None):
        current = (curCh if curCh is not None and curCh != "" else " ")
        target  = (targetCh if targetCh is not None and targetCh != "" else " ")
        if current == target: return []
        steps = []
        if allowed is None: allowed = [str(i) for i in range(10)]
        if (current not in allowed) or (target not in allowed): return [target]
        digits = allowed[:]
        try: ci = digits.index(current)
        except: ci = 0
        try: ti = digits.index(target)
        except: ti = 0
        i = ci
        while i != ti:
            i = (i + 1) % len(digits)
            steps.append(digits[i])
        return steps
        
    def DrawUnifiedDigit(self, g2, text):
        s = str(text or "")
        f = MakeFont(FONT_DIGIT, bold=False)
        g2.setFont(f)
        fm = g2.getFontMetrics(f)

        wtxt = fm.stringWidth(s)
        x = (self.w - wtxt) // 2
        if x < 2:
            x = 2
        if x > (self.w - wtxt - 2):
            x = max(2, self.w - wtxt - 2)

        # Use the same vertical reference as the original DigitFlap.DrawTextLine top-half placement:
        # baseline computed from hinge (half height) rather than full height.
        hingeY = int(self.h * HingeRatio)
        adjustDown = max(1, Sc(15))
        baseline = (hingeY + fm.getAscent()) // 2 - 2 + adjustDown

        g2.drawString(s, x, baseline)

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, FLAP_BG, PURE_BLK, hingeY=hingeY)

            g2.setColor(self.TextColor())

            oldText = getattr(self, "prevTopForBottom", self.curTop)
            frac = self.EaseInOut(self.t)

            if self.phase == "idle":
                g2.setClip(None)
                self.DrawUnifiedDigit(g2, self.curTop)

            elif self.phase == "topFlip":
                # Reveal new digit from top->hinge, bottom stays old
                newText = getattr(self, "nextTop", self.curTop)
                reveal = int(round(frac * hingeY))

                if reveal > 0:
                    g2.setClip(awt.Rectangle(0, 0, self.w, reveal))
                    self.DrawUnifiedDigit(g2, newText)

                if reveal < hingeY:
                    g2.setClip(awt.Rectangle(0, reveal, self.w, hingeY - reveal))
                    self.DrawUnifiedDigit(g2, oldText)

                g2.setClip(awt.Rectangle(0, hingeY, self.w, self.h - hingeY))
                self.DrawUnifiedDigit(g2, oldText)

            elif self.phase == "bottomFlip":
                # Top already new; reveal new on bottom half from hinge->bottom
                newText = self.curTop
                botH = self.h - hingeY
                reveal = int(round(frac * botH))

                # Top half: new, fixed
                g2.setClip(awt.Rectangle(0, 0, self.w, hingeY))
                self.DrawUnifiedDigit(g2, newText)

                # Bottom half: reveal new from hinge down, old below reveal
                if reveal > 0:
                    g2.setClip(awt.Rectangle(0, hingeY, self.w, reveal))
                    self.DrawUnifiedDigit(g2, newText)

                if reveal < botH:
                    g2.setClip(awt.Rectangle(0, hingeY + reveal, self.w, botH - reveal))
                    self.DrawUnifiedDigit(g2, oldText)

            else:
                g2.setClip(None)
                self.DrawUnifiedDigit(g2, self.curTop)

        finally:
            try:
                g2.setClip(None)
            except:
                pass
            DrawHingeOver(g2, self.w, self.h, PURE_BLK)
            g2.dispose()

class WordFlap(SolariFlap):
    def __init__(self, w, h):
        SolariFlap.__init__(self, w, h, twoLine=False)
        
    def DrawUnifiedText(self, g2, text):
        # Draw one line of text centered over the full flap height (not separately per half)
        margin = Sc(12)
        s = str(text or "")
        f = MakeFont(FONT_BIG, bold=False)
        g2.setFont(f)
        fm = g2.getFontMetrics(f)
        maxWidth = self.w - 2 * margin

        # Apply the same truncation strategy as SolariFlap.DrawTextLine, but for full-height text
        if fm.stringWidth(s) > maxWidth:
            try:
                attrs = {TextAttribute.TRACKING: -0.04}
                f2 = f.deriveFont(attrs)
                fm2 = g2.getFontMetrics(f2)
                if fm2.stringWidth(s) > maxWidth:
                    t = s
                    while len(t) > 1 and fm2.stringWidth(t + "...") > maxWidth:
                        t = t[:-1]
                    if len(t) > 1:
                        t = t + "..."
                    s = t
                    g2.setFont(f2)
                else:
                    g2.setFont(f)
            except:
                t = s
                while len(t) > 1 and fm.stringWidth(t + "...") > maxWidth:
                    t = t[:-1]
                if len(t) > 1:
                    t = t + "..."
                s = t
                g2.setFont(f)

        fm = g2.getFontMetrics()
        baseline = (self.h + fm.getAscent()) // 2 - 2
        g2.drawString(s, margin, baseline)

    def paintComponent(self, g):
        g2 = g.create()
        try:
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

            hingeY = int(self.h * HingeRatio)
            PaintFlapFrame(g2, self.w, self.h, FLAP_BG, PURE_BLK, hingeY=hingeY)

            g2.setColor(TEXT_WHT)

            oldText = getattr(self, "prevTopForBottom", self.curTop)
            frac = self.EaseInOut(self.t)

            if self.phase == "idle":
                g2.setClip(None)
                self.DrawUnifiedText(g2, self.curTop)

            elif self.phase == "topFlip":
                newText = getattr(self, "nextTop", self.curTop)
                reveal = int(round(frac * hingeY))

                if reveal > 0:
                    g2.setClip(awt.Rectangle(0, 0, self.w, reveal))
                    self.DrawUnifiedText(g2, newText)

                if reveal < hingeY:
                    g2.setClip(awt.Rectangle(0, reveal, self.w, hingeY - reveal))
                    self.DrawUnifiedText(g2, oldText)

                g2.setClip(awt.Rectangle(0, hingeY, self.w, self.h - hingeY))
                self.DrawUnifiedText(g2, oldText)

            elif self.phase == "bottomFlip":
                newText = self.curTop
                botH = self.h - hingeY
                reveal = int(round(frac * botH))

                # Top half: new, fixed
                g2.setClip(awt.Rectangle(0, 0, self.w, hingeY))
                self.DrawUnifiedText(g2, newText)

                # Bottom half: reveal new from hinge down, old below reveal
                if reveal > 0:
                    g2.setClip(awt.Rectangle(0, hingeY, self.w, reveal))
                    self.DrawUnifiedText(g2, newText)

                if reveal < botH:
                    g2.setClip(awt.Rectangle(0, hingeY + reveal, self.w, botH - reveal))
                    self.DrawUnifiedText(g2, oldText)

            else:
                g2.setClip(None)
                self.DrawUnifiedText(g2, self.curTop)

        finally:
            try:
                g2.setClip(None)
            except:
                pass
            DrawHingeOver(g2, self.w, self.h, PURE_BLK)
            g2.dispose()
    
class DoubleLineFlap(SolariFlap):
    def __init__(self, w, h):
        SolariFlap.__init__(self, w, h, twoLine=True)

# ------------------------------ Board panel --------------------------------
class SolariBoard(swing.JPanel):
    def __init__(self):
        super(SolariBoard, self).__init__()
        self.setLayout(None)
        self.setBackground(PANEL_BG)

        # --- Compact width planning (computed board width) ---
        # Time label width and desired gap
        LABEL_TIME_W  = Sc(70)
        TIME_GAP      = Sc(8)

        # Digit block metrics (use single-line flap height to unify sizes)
        DIGIT_W = Sc(34)
        DIGIT_H = FLAP_H
        DIGIT_GAP = Sc(4)

        # Reserve proper space for the colon so it cannot overlap digits
        COLON_W = Sc(14)
        COLON_PAD = Sc(4)

        DIGIT_TRAIL = Sc(6) # small trailing margin to the right edge

        # H1 gap H2 pad colon pad M1 gap M2 trail
        totalDigitsW = (DIGIT_W * 4) + (DIGIT_GAP * 2) + (COLON_PAD * 2 + COLON_W) + DIGIT_TRAIL
       
        # Final compact board width, expanded by configured percentage
        baseW = OUTER_PAD + LABEL_TIME_W + TIME_GAP + totalDigitsW + OUTER_PAD
        self.boardW = int(round(baseW * WIDTH_EXPAND_FACTOR))
        self.boardH = Sc(1000)  # content height; will be respected by window

        x = OUTER_PAD
        y = OUTER_PAD

        # Top: "Time" fixed label + colon + 4 digit flaps (right-aligned)
        self.lblTime = LabelFixed("Time", FONT_MID, bold=False, color=TEXT_WHT)
        self.lblTime.setBounds(x, y, LABEL_TIME_W, TOP_LINE_H)
        self.add(self.lblTime)

        # Right alignment anchor
        rightEdge = self.boardW - OUTER_PAD
        startX = rightEdge - totalDigitsW + DIGIT_TRAIL

        self.dH1 = DigitFlap(DIGIT_W, DIGIT_H)
        self.dH2 = DigitFlap(DIGIT_W, DIGIT_H)
        self.dM1 = DigitFlap(DIGIT_W, DIGIT_H)
        self.dM2 = DigitFlap(DIGIT_W, DIGIT_H)

        topY = y + (TOP_LINE_H - DIGIT_H) // 2
        cx = startX

        self.dH1.setBounds(cx, topY, DIGIT_W, DIGIT_H)
        self.add(self.dH1)
        cx += DIGIT_W + DIGIT_GAP

        self.dH2.setBounds(cx, topY, DIGIT_W, DIGIT_H)
        self.add(self.dH2)
        cx += DIGIT_W

        # Colon (fixed flap), with padding either side
        cx += COLON_PAD
        self.colonFlap = ColonFlapFixed(COLON_W, DIGIT_H)
        self.colonFlap.setBounds(cx, topY, COLON_W, DIGIT_H)
        self.add(self.colonFlap)
        cx += COLON_W + COLON_PAD

        self.dM1.setBounds(cx, topY, DIGIT_W, DIGIT_H)
        self.add(self.dM1)
        cx += DIGIT_W + DIGIT_GAP

        self.dM2.setBounds(cx, topY, DIGIT_W, DIGIT_H)
        self.add(self.dM2)


        y += TOP_LINE_H + LINE_GAP

        # Platform: "Platform" fixed + 3 digit flaps (same DIGIT_H, same font size) right-aligned
        self.lblPlat = LabelFixed("Platform", FONT_MID, bold=False, color=TEXT_WHT)
        self.lblPlat.setBounds(x, y, Sc(150), PLAT_LINE_H); self.add(self.lblPlat)

        self.platFlaps = [DigitFlap(DIGIT_W, DIGIT_H),
                          DigitFlap(DIGIT_W, DIGIT_H),
                          DigitFlap(DIGIT_W, DIGIT_H)]
        totalPlatW = DIGIT_W*3 + DIGIT_GAP*2
        sx = self.boardW - OUTER_PAD - totalPlatW
        py = y + (PLAT_LINE_H - DIGIT_H)//2
        for i, df in enumerate(self.platFlaps):
            df.setBounds(sx + i*(DIGIT_W + DIGIT_GAP), py, DIGIT_W, DIGIT_H)
            self.add(df)

        y += PLAT_LINE_H + LINE_GAP

        # Destination flap (full width of compact board)
        self.flapDest = WordFlap(self.boardW - 2*OUTER_PAD, FLAP_H)
        self.flapDest.setBounds(OUTER_PAD, y, self.flapDest.w, self.flapDest.h); self.add(self.flapDest)
        y += FLAP_H + LINE_GAP

        # Via flap
        self.flapVia = WordFlap(self.boardW - 2*OUTER_PAD, FLAP_H)
        self.flapVia.setBounds(OUTER_PAD, y, self.flapVia.w, self.flapVia.h); self.add(self.flapVia)
        y += FLAP_H + LINE_GAP

        # Special flap
        self.flapSpecial = WordFlap(self.boardW - 2*OUTER_PAD, FLAP_H)
        self.flapSpecial.setBounds(OUTER_PAD, y, self.flapSpecial.w, self.flapSpecial.h); self.add(self.flapSpecial)
        y += FLAP_H + (LINE_GAP*2)

        # "Calling at" fixed header
        self.lblCalling = LabelFixed("Calling at", FONT_MID, bold=False, color=TEXT_WHT)
        self.lblCalling.setBounds(OUTER_PAD, y, Sc(180), Sc(28)); self.add(self.lblCalling)
        y += Sc(32)

        # Ten two-line flaps
        self.callFlaps = []
        for i in range(10):
            fp = DoubleLineFlap(self.boardW - 2*OUTER_PAD, DOUBLE_H)
            fp.setBounds(OUTER_PAD, y, fp.w, fp.h); self.add(fp)
            self.callFlaps.append(fp)
            y += DOUBLE_H + Sc(6)

        self.boardH = y + OUTER_PAD
        self.setPreferredSize(awt.Dimension(self.boardW, self.boardH))

        # Data for chatter / constraints
        self.destPool = []; self.viaPool = []; self.platCharSet = set()
        self.lastPlatCharsAllowed = ["0","1","2","3","4","5","6","7","8","9"]
        self.lastStateKey = None  # used to suppress unnecessary animations
        self._blankSerial = 0
        self._blankTimer = None
        self._skipBlankOnce = False
          
    def CalcStartDelayMs(self, rowIndex, multiChange):
        if not multiChange:
            return 0

        base = 0
        try:
            base = int(rowIndex) * int(STAGGER_ROW_MS)
        except:
            base = 0

        jitter = 0
        try:
            if int(STAGGER_JITTER_MS) > 0:
                jitter = random.randint(0, int(STAGGER_JITTER_MS))
        except:
            jitter = 0

        return base + jitter

    # -------------------- Two-stage transition helper -----------------------
    def BeginBlankTransition(self, svc, destPool, viaPool, platCharSet, maxPlatNum):
        # Stage 1: chatter/flap to blank. Stage 2: after hold, animate to final.
        self._blankSerial += 1
        serial = int(self._blankSerial)

        # Cancel any previous blank-to-final timer.
        try:
            if self._blankTimer is not None:
                self._blankTimer.stop()
        except:
            pass
        self._blankTimer = None

        # Ensure the special flap uses the normal painter during the blank stage.
        try:
            self.flapSpecial.paintComponent = lambda g: SolariFlap.paintComponent(self.flapSpecial, g)
            self.flapSpecial.TextColor = lambda: TEXT_WHT
        except:
            pass

        # Pools for blank chatter
        wordPool = []
        try:
            for w in (destPool or []):
                s = str(w or "").strip()
                if s != "":
                    wordPool.append(s.upper())
        except:
            pass
        try:
            for w in (viaPool or []):
                s = str(w or "").strip()
                if s != "":
                    wordPool.append(s)
        except:
            pass

        # Blank chatter count
        try:
            nSteps = int(BLANK_CHATTER_STEPS)
        except:
            nSteps = 0
        if nSteps < 0:
            nSteps = 0

        def _RandPairsChars(pool):
            pairs = []
            if nSteps <= 0:
                return pairs
            p = list(pool or [])
            if not p:
                return pairs
            for k in range(nSteps):
                try:
                    pairs.append((random.choice(p), ""))
                except:
                    pairs.append((" ", ""))
            return pairs

        def _RandPairsWords():
            pairs = []
            if nSteps <= 0:
                return pairs
            p = list(wordPool or [])
            if not p:
                return pairs
            for k in range(nSteps):
                try:
                    pairs.append((random.choice(p), ""))
                except:
                    pairs.append(("", ""))
            return pairs

        def _RandPairsDouble():
            pairs = []
            if nSteps <= 0:
                return pairs
            p = list(wordPool or [])
            if not p:
                return pairs
            for k in range(nSteps):
                try:
                    a = random.choice(p)
                except:
                    a = ""
                try:
                    b = random.choice(p)
                except:
                    b = ""
                pairs.append((a, b))
            return pairs

        # Use the same within-board cascade delays for the blank stage.
        multiChange = True

        dlyTime = self.CalcStartDelayMs(0, multiChange)
        for df in (self.dH1, self.dH2, self.dM1, self.dM2):
            df.AnimateTo(" ", "", _RandPairsChars([str(i) for i in range(10)]), startDelayMs=dlyTime)

        dlyPlat = self.CalcStartDelayMs(1, multiChange)
        allowedPlat = list(getattr(self, "lastPlatCharsAllowed", [])) or [str(i) for i in range(10)]

        platHide = False
        try:
            platHide = bool(HIDE_PLAT_UNTIL_ALLOC) and (not getattr(svc, "HasAlloc", False))
        except:
            platHide = False

        platAlreadyBlank = True
        if platHide:
            try:
                for _pf in self.platFlaps:
                    if (_pf.curTop or " ") != " ":
                        platAlreadyBlank = False
                        break
            except:
                platAlreadyBlank = False

        # Platform blank chatter: constrain transient values to the highest numeric platform in the timetable.
        platPairsByDigit = None
        try:
            mp = int(maxPlatNum)
        except:
            mp = 0
        if mp > 0 and nSteps > 0:
            try:
                seq = []
                for k in range(nSteps):
                    try:
                        num = random.randint(1, mp)
                    except:
                        num = 1
                    s = str(num)
                    if len(s) > 3:
                        s = s[-3:]
                    s = (" " * (3 - len(s))) + s
                    seq.append(s)
                platPairsByDigit = [[], [], []]
                for s in seq:
                    platPairsByDigit[0].append((s[0], ""))
                    platPairsByDigit[1].append((s[1], ""))
                    platPairsByDigit[2].append((s[2], ""))
            except:
                platPairsByDigit = None

        if platHide and platAlreadyBlank:
            for pf in self.platFlaps:
                pf.AnimateTo(" ", "", [], startDelayMs=dlyPlat)
        else:
            for i, pf in enumerate(self.platFlaps):
                if platPairsByDigit is not None and i < 3:
                    pf.AnimateTo(" ", "", platPairsByDigit[i], startDelayMs=dlyPlat)
                else:
                    pf.AnimateTo(" ", "", _RandPairsChars(allowedPlat), startDelayMs=dlyPlat)

        dlyDest = self.CalcStartDelayMs(2, multiChange)
        self.flapDest.AnimateTo("", "", _RandPairsWords(), startDelayMs=dlyDest)

        dlyVia = self.CalcStartDelayMs(3, multiChange)
        self.flapVia.AnimateTo("", "", _RandPairsWords(), startDelayMs=dlyVia)

        dlySpecial = self.CalcStartDelayMs(4, multiChange)
        self.flapSpecial.AnimateTo("", "", _RandPairsWords(), startDelayMs=dlySpecial)

        # Calling flaps cascade top-to-bottom
        try:
            callBase = int(STAGGER_ROW_MS) * 4
        except:
            callBase = 0
        for idx, fp in enumerate(self.callFlaps):
            callDelay = callBase + (idx * int(STAGGER_ROW_MS))
            fp.AnimateTo("", "", _RandPairsDouble(), startDelayMs=callDelay)

        # Estimate time for blank stage to complete, then hold, then run final stage.
        try:
            msPerHalf = int(ANIM_MS_PER_HALF)
        except:
            msPerHalf = 50
        blankMs = ((nSteps + 1) * 2 * msPerHalf) + 75
        try:
            holdMs = int(BLANK_HOLD_MS)
        except:
            holdMs = 300
        if holdMs < 0:
            holdMs = 0

        delayFinal = blankMs + holdMs

        def _RunFinal(ev):
            if int(self._blankSerial) != serial:
                return
            # Prevent recursion: next ApplyService run should skip the blank stage.
            self._skipBlankOnce = True
            try:
                self.ApplyService(svc, destPool, viaPool, platCharSet, maxPlatNum)
            except Exception as ex:
                try:
                    print("[PIDSolari] blank->final error:", ex)
                except:
                    pass

        self._blankTimer = Timer(delayFinal, _RunFinal)
        self._blankTimer.setRepeats(False)
        self._blankTimer.start()

    def BeginClearTransition(self, destPool, viaPool, platCharSet, maxPlatNum):
        # Clear the board with chatter to blank, then remain blank.
        self._blankSerial += 1

        # Cancel any previous blank-to-final timer.
        try:
            if self._blankTimer is not None:
                self._blankTimer.stop()
        except:
            pass
        self._blankTimer = None

        # Mark state unknown so a later service will always trigger a full update.
        self.lastStateKey = None
        self._skipBlankOnce = False

        # Use the same blanking animation as stage 1, but do not schedule a final stage.
        self.BeginBlankTransition(Service({"Reporting number":"","Dep":"","Destination":"","Via":"","Calling pattern":""}, "", 0), destPool, viaPool, platCharSet, maxPlatNum)
        try:
            if self._blankTimer is not None:
                self._blankTimer.stop()
        except:
            pass
        self._blankTimer = None

    # -------------------- Update & animation orchestration -----------------
    def ApplyService(self, svc, destPool, viaPool, platCharSet, maxPlatNum):
        # Build state key so a minute tick that does not change the visible data does nothing.
        hhmm = FormatHHmm(svc.ShowTime or "")
        plat = (svc.Plat or "").strip() 
        destTarget = (svc.Dest or "").upper()
        viaName = (svc.Via or "").strip()
        viaTarget = ("via " + viaName) if viaName != "" else ""

        # Pre-fit targets so animation frames do not "jump" in/out of ellipsis
        destTargetFit = FitTextForFlap(destTarget, self.flapDest.w, twoLine=False)
        viaTargetFit = FitTextForFlap(viaTarget, self.flapVia.w, twoLine=False)
               
        # ECS is considered "already detected" if the destination being displayed starts with "EMPTY"
        isEcsDisplay = False
        try:
            dt = str(destTargetFit or "").strip().lower()
            if dt.startswith("empty"):
                isEcsDisplay = True
        except:
            pass
        # Delay banner (Solari style): use Via and Special lines in white on red, split by hinge.
        showDelayBanner = False
        try:
            if (svc.Status == "Delayed") and (not isEcsDisplay) and (svc.Status.upper() != "CANCELLED"):
                if not HIDE_PLAT_UNTIL_ALLOC:
                    showDelayBanner = True
                else:
                    showDelayBanner = (not getattr(svc, "HasAlloc", False))
        except:
            showDelayBanner = False

        def _SetBannerPainter(flap):
            def _PaintBanner(g):
                g2 = g.create()
                try:
                    hingeY = int(flap.h * HingeRatio)
                    PaintFlapFrame(g2, flap.w, flap.h, RED, PURE_BLK, hingeY=hingeY)
                    f = MakeFont(FONT_CALL, bold=False)
                    g2.setFont(f)
                    g2.setColor(TEXT_WHT)
                    fm = g2.getFontMetrics(f)
                    margin = Sc(12)
                    topH = hingeY
                    botH = flap.h - hingeY
                    def _DrawHalf(txt, top):
                        s = str(txt or "")
                        if top:
                            y0 = 0
                            hh = topH
                        else:
                            y0 = hingeY
                            hh = botH
                        try:
                            maxWidth = flap.w - (2 * margin)
                            if fm.stringWidth(s) > maxWidth:
                                while len(s) > 1 and fm.stringWidth(s + "...") > maxWidth:
                                    s = s[:-1]
                                if len(s) > 1:
                                    s = s + "..."
                        except:
                            pass
                        baseline = y0 + ((hh + fm.getAscent()) // 2) - 2
                        g2.drawString(s, margin, baseline)
                    oldTop = getattr(flap, "prevTopForBottom", flap.curTop)

                    oldTop = getattr(flap, "prevFullTop", getattr(flap, "prevTopForBottom", flap.curTop))
                    oldBot = getattr(flap, "prevFullBot", flap.curBot)

                    if flap.phase == "idle":
                        _DrawHalf(flap.curTop, True)
                        _DrawHalf(flap.curBot, False)

                    elif flap.phase == "fullFlip":
                        newTop = getattr(flap, "nextTop", flap.curTop)
                        newBot = getattr(flap, "nextBot", flap.curBot)

                        try:
                            frac = flap.EaseInOut(flap.t)
                        except:
                            frac = 0.0
                        reveal = int(round(frac * float(flap.h)))
                        if reveal < 0:
                            reveal = 0
                        if reveal > flap.h:
                            reveal = flap.h

                        if reveal > 0:
                            g2.setClip(awt.Rectangle(0, 0, flap.w, reveal))
                            _DrawHalf(newTop, True)
                            _DrawHalf(newBot, False)

                        if reveal < flap.h:
                            g2.setClip(awt.Rectangle(0, reveal, flap.w, flap.h - reveal))
                            _DrawHalf(oldTop, True)
                            _DrawHalf(oldBot, False)

                        try:
                            g2.setClip(None)
                        except:
                            pass

                    elif flap.phase == "topFlip":
                        topTxt = flap.nextTop if flap.t > 0.5 else oldTop
                        _DrawHalf(topTxt, True)
                        _DrawHalf(flap.curBot, False)

                    elif flap.phase == "bottomFlip":
                        _DrawHalf(flap.curTop, True)
                        botTxt = flap.nextBot if flap.t > 0.5 else flap.curBot
                        _DrawHalf(botTxt, False)

                    else:
                        _DrawHalf(flap.curTop, True)
                        _DrawHalf(flap.curBot, False)

                    DrawHingeOver(g2, flap.w, flap.h, PURE_BLK)
                finally:
                    g2.dispose()
            flap.paintComponent = _PaintBanner

        def _SetViaDefaultPainter():
            self.flapVia.paintComponent = lambda g: WordFlap.paintComponent(self.flapVia, g)

        def _SetSpecialDefaultPainter():
            self.flapSpecial.paintComponent = lambda g: WordFlap.paintComponent(self.flapSpecial, g)
            self.flapSpecial.TextColor = lambda: TEXT_WHT

            

        stops = [t.strip() for t in (svc.Call or "").split(",") if (t or "").strip() != ""]
        destKeyForGaps = (svc.Dest or "").strip().upper()
        stops = _ApplyGapsToStops(stops, destKeyForGaps)
        key = "\n".join([hhmm, plat, destTargetFit, viaTargetFit, svc.Status, ",".join(stops)])
        if key == self.lastStateKey and not self._skipBlankOnce:
            return  # nothing changed -> no animation
        self.lastStateKey = key
        if not self._skipBlankOnce:
            self.BeginBlankTransition(svc, destPool, viaPool, platCharSet, maxPlatNum)
            return
        self._skipBlankOnce = False
        

        # Pools/constraints
        self.destPool = list(destPool or [])
        self.viaPool = list(viaPool or [])
        self.platCharSet = set(platCharSet or [])
        
        # Pre-fit chatter pools so flip frames use the same truncation strategy as the final target
        # Destination must always appear in capitals, including during chatter
        destPoolUpperFit = []
        for _d in (self.destPool or []):
            _s = str(_d or "").strip()
            if _s == "":
                continue
            _u = _s.upper()
            _f = FitTextForFlap(_u, self.flapDest.w, twoLine=False)
            if _f != "":
                destPoolUpperFit.append(_f)

        # Via pool also pre-fitted (keeps chatter consistent if "via ..." strings vary in length)
        viaPoolFit = []
        for _v in (self.viaPool or []):
            _s = str(_v or "").strip()
            if _s == "":
                continue
            _f = FitTextForFlap(_s, self.flapVia.w, twoLine=False)
            if _f != "":
                viaPoolFit.append(_f)

        # Destination should always appear in capitals, including during chatter frames
        destPoolUpper = []
        for _d in (self.destPool or []):
            _s = str(_d or "").strip()
            if _s != "":
                destPoolUpper.append(_s.upper())
        allowedDigits = sorted([c for c in self.platCharSet if c.isdigit()])
        if allowedDigits: self.lastPlatCharsAllowed = allowedDigits

        # Determine whether multiple flaps are changing; used to enable top-down stagger and stop-time variability
        changedCount = 0

        try:
            if len(hhmm) >= 5 and hhmm[2] == ":":
                if (self.dH1.curTop or " ") != hhmm[0]:
                    changedCount += 1
                if (self.dH2.curTop or " ") != hhmm[1]:
                    changedCount += 1
                if (self.dM1.curTop or " ") != hhmm[3]:
                    changedCount += 1
                if (self.dM2.curTop or " ") != hhmm[4]:
                    changedCount += 1
        except:
            pass

        try:
            if (self.flapDest.curTop or "") != destTargetFit:
                changedCount += 1
        except:
            pass

        try:
            if (self.flapVia.curTop or "") != viaTargetFit:
                changedCount += 1
        except:
            pass

        multiChange = (changedCount >= 2)

        # TIME digits
        if len(hhmm) >= 5 and hhmm[2] == ":":
            h1, h2, m1, m2 = hhmm[0], hhmm[1], hhmm[3], hhmm[4]
        else:
            h1=h2=m1=m2=" "     
        dlyTime = self.CalcStartDelayMs(0, multiChange)
        self.AnimateDigitTo(self.dH1, h1, startDelayMs=dlyTime, multiChange=multiChange)
        self.AnimateDigitTo(self.dH2, h2, startDelayMs=dlyTime, multiChange=multiChange)
        self.AnimateDigitTo(self.dM1, m1, startDelayMs=dlyTime, multiChange=multiChange)
        self.AnimateDigitTo(self.dM2, m2, startDelayMs=dlyTime, multiChange=multiChange)

        # PLATFORM digits (right-aligned to 3 flaps)
        chars = list(plat)[-3:]; chars = ([" "]*(3-len(chars))) + chars       
        dlyPlat = self.CalcStartDelayMs(1, multiChange)
        for i, ch in enumerate(chars):
            self.AnimatePlatCharTo(self.platFlaps[i], ch, startDelayMs=dlyPlat, multiChange=multiChange)

        # DEST and VIA (whole-word chatter only when content changes)          
        dlyDest = self.CalcStartDelayMs(2, multiChange)
        dlyVia = self.CalcStartDelayMs(3, multiChange)
        self.AnimateWordFlap(self.flapDest, destTargetFit, pool=destPoolUpperFit, startDelayMs=dlyDest, multiChange=multiChange)
        if showDelayBanner:
            _SetBannerPainter(self.flapVia)
            self.flapVia.AnimateTo("Incoming Service", "Delayed", [], startDelayMs=dlyVia)
        else:
            _SetViaDefaultPainter()
            self.AnimateWordFlap(self.flapVia, viaTargetFit, pool=viaPoolFit, startDelayMs=dlyVia, multiChange=multiChange)

        # If showing Solari-style delay banner, also use the Special line.
        if showDelayBanner:
            _SetBannerPainter(self.flapSpecial)
            dlySpecial = self.CalcStartDelayMs(4, multiChange)
            self.flapSpecial.AnimateTo("Please listen", "for Announcements", [], startDelayMs=dlySpecial)
        else:
            _SetSpecialDefaultPainter()

        # SPECIAL
        if showDelayBanner:
            pass
        elif svc.Status.upper() == "CANCELLED":
            def PaintSpecial(g):
                g2 = g.create()
                try:
                    hingeY = int(self.flapSpecial.h * HingeRatio)
                    PaintFlapFrame(g2, self.flapSpecial.w, self.flapSpecial.h, RED, PURE_BLK, hingeY=hingeY)
                    SolariFlap.DrawTopText(self.flapSpecial, g2, "CANCELLED")
                    SolariFlap.DrawBottomText(self.flapSpecial, g2, "")
                finally: g2.dispose()
            self.flapSpecial.paintComponent = PaintSpecial
            self.flapSpecial.AnimateTo("CANCELLED", "", [])      
        elif isEcsDisplay:
            ecsMsg = str(ECS_MESSAGE or "Not for public use")

            def PaintSpecialEcs(g):
                g2 = g.create()
                try:
                    # White background, black border, black hinge
                    hingeY = int(self.flapSpecial.h * HingeRatio)
                    PaintFlapFrame(g2, self.flapSpecial.w, self.flapSpecial.h, Color.WHITE, PURE_BLK, hingeY=hingeY)

                    # Red text, using the WordFlap unified renderer so it looks like one line split by hinge
                    g2.setColor(RED)

                    oldText = getattr(self.flapSpecial, "prevTopForBottom", self.flapSpecial.curTop)

                    if self.flapSpecial.phase == "idle":
                        g2.setClip(None)
                        self.flapSpecial.DrawUnifiedText(g2, self.flapSpecial.curTop)

                    elif self.flapSpecial.phase == "topFlip":
                        g2.setClip(awt.Rectangle(0, 0, self.flapSpecial.w, hingeY))
                        topTxt = self.flapSpecial.nextTop if self.flapSpecial.t > 0.5 else oldText
                        self.flapSpecial.DrawUnifiedText(g2, topTxt)

                        g2.setClip(awt.Rectangle(0, hingeY, self.flapSpecial.w, self.flapSpecial.h - hingeY))
                        self.flapSpecial.DrawUnifiedText(g2, oldText)

                    elif self.flapSpecial.phase == "bottomFlip":
                        g2.setClip(awt.Rectangle(0, 0, self.flapSpecial.w, hingeY))
                        self.flapSpecial.DrawUnifiedText(g2, self.flapSpecial.curTop)

                        g2.setClip(awt.Rectangle(0, hingeY, self.flapSpecial.w, self.flapSpecial.h - hingeY))
                        botTxt = self.flapSpecial.curTop if self.flapSpecial.t > 0.5 else oldText
                        self.flapSpecial.DrawUnifiedText(g2, botTxt)
                    else:
                        g2.setClip(None)
                        self.flapSpecial.DrawUnifiedText(g2, self.flapSpecial.curTop)

                finally:
                    try:
                        g2.setClip(None)
                    except:
                        pass
                    DrawHingeOver(g2, self.flapSpecial.w, self.flapSpecial.h, PURE_BLK)
                    g2.dispose()

            self.flapSpecial.paintComponent = PaintSpecialEcs
            self.flapSpecial.AnimateTo(ecsMsg, "", [])
        else:
            self.flapSpecial.paintComponent = lambda g: SolariFlap.paintComponent(self.flapSpecial, g)
            self.flapSpecial.TextColor = lambda: TEXT_WHT
            self.flapSpecial.AnimateTo("", "", [])

        # CALLING AT: no paging; >20 stops -> last flap shows yellow "and stations to:" / DEST
        pairs = []
        i = 0
        while i < len(stops):
            top = stops[i]
            bot = stops[i+1] if (i+1) < len(stops) else ""
            pairs.append((top, bot)); i += 2
        if len(stops) > 20:
            pairs = pairs[:9]
            pairs.append(("and stations to:", destTarget))

        while len(pairs) < 10: pairs.append(("", ""))
        wordPool = set([t for t in (self.destPool or [])] + [t for t in (self.viaPool or [])])

        # Calling-flap chatter should use actual station names from the calling pattern.
        # Build an ordered unique list from stops (which may include blanks from mechanical gaps).
        callStationsPool = []
        seenStations = set()
        for s in (stops or []):
            ss = (s or "").strip()
            if ss == "":
                continue
            if ss in seenStations:
                continue
            seenStations.add(ss)
            callStationsPool.append(ss)

        # Cascade calling flaps from top to bottom (always), with optional jitter
        try:
            callBase = int(STAGGER_ROW_MS) * 4
        except:
            callBase = 0
        try:
            callJitterMax = int(STAGGER_JITTER_MS)
        except:
            callJitterMax = 0

        for idx, fp in enumerate(self.callFlaps):
            topT, botT = pairs[idx]

            # Delay increases as idx increases (top flap starts first)
            callDelay = callBase + (idx * int(STAGGER_ROW_MS))
            if callJitterMax > 0:
                try:
                    callDelay = callDelay + random.randint(0, callJitterMax)
                except:
                    pass

            if topT.lower() == "and stations to:":
                fp.DrawTopText = lambda g2, s: SolariFlap.DrawTextLine(fp, g2, (s or ""), top=True, colorOverride=YELLOW)
                fp.AnimateTo(topT, botT, [], startDelayMs=callDelay)
                continue
            else:
                fp.DrawTopText = lambda g2, s: SolariFlap.DrawTextLine(fp, g2, (s or ""), top=True, colorOverride=None)

            chatter = []

            # Prefer real station names for calling-flap chatter; fall back to wordPool if needed.
            pool = callStationsPool if (callStationsPool and len(callStationsPool) > 0) else list(wordPool)

            if CHATTER_STEPS > 0 and pool and ((fp.curTop != topT) or (fp.curBot != botT)):
                for k in range(CHATTER_STEPS):
                    try:
                        aTop = random.choice(pool)
                    except:
                        aTop = ""
                    try:
                        aBot = random.choice(pool)
                    except:
                        aBot = ""
                    chatter.append((aTop, aBot))

            fp.AnimateTo(topT, botT, chatter, startDelayMs=callDelay)

    def AnimateWordFlap(self, flap, target, pool, startDelayMs=0, multiChange=False):
        targetTop = (target or "")
        targetBot = ""  # SolariFlap.AnimateTo will duplicate for single-line flaps

        if (flap.curTop == targetTop) and (flap.curBot == targetBot or not flap.twoLine):
            # If an earlier stage left a pending/active animation on this flap (e.g. blank-stage),
            # we must still assert the target so that the pending animation cannot overwrite it later.
            try:
                pending = getattr(flap, "pendingTimer", None)
                phase = getattr(flap, "phase", "idle")
                if pending is not None or phase != "idle":
                    flap.AnimateTo(targetTop, targetBot, [], startDelayMs=startDelayMs)
            except:
                pass
            return

        # Build a stable cycle list (unique, preserves pool order)
        cycle = []
        seen = set()
        for w in (pool or []):
            s = str(w or "")
            if s == "":
                continue
            if s in seen:
                continue
            seen.add(s)
            cycle.append(s)

        if targetTop not in seen:
            cycle.append(targetTop)
            seen.add(targetTop)

        if not cycle:
            flap.AnimateTo(targetTop, targetBot, [], startDelayMs=startDelayMs)
            return

        # Determine current position in the cycle
        cur = str(flap.curTop or "")
        try:
            ci = cycle.index(cur)
        except:
            # If current is not in the cycle, start from a random point for realism
            try:
                ci = random.randint(0, len(cycle) - 1)
            except:
                ci = 0

        ti = 0
        try:
            ti = cycle.index(targetTop)
        except:
            ti = 0

        n = len(cycle)
        dist = (ti - ci) % n

        extra = 0
        if multiChange:
            try:
                if int(EXTRA_WORD_STEPS_MAX) > 0:
                    extra = random.randint(0, int(EXTRA_WORD_STEPS_MAX))
            except:
                extra = 0

        total = dist + extra
        if total <= 0:
            # If already at target, do a small random run then return to target (only when multi-change)
            if multiChange and n > 1:
                total = 1 + extra
            else:
                flap.AnimateTo(targetTop, targetBot, [], startDelayMs=startDelayMs)
                return

        # Build the forward sequence of intermediate frames
        seq = []
        i = ci
        for k in range(total):
            i = (i + 1) % n
            seq.append(cycle[i])

        # Ensure we end on the target; if not, continue cycling until we do
        if not seq or seq[-1] != targetTop:
            i = ci
            while True:
                i = (i + 1) % n
                seq.append(cycle[i])
                if cycle[i] == targetTop:
                    break

        chatter = []
        for s in seq[:-1]:
            chatter.append((s, ""))

        flap.AnimateTo(targetTop, targetBot, chatter, startDelayMs=startDelayMs)
    
    def AnimateDigitTo(self, flap, charTarget, startDelayMs=0, multiChange=False):
        cur = (flap.curTop or " ")
        tgt = (charTarget or " ")

        if cur == tgt:
            # If an earlier stage left a pending/active animation on this flap (e.g. blank-stage),
            # we must still assert the target so that the pending animation cannot overwrite it later.
            try:
                pending = getattr(flap, "pendingTimer", None)
                phase = getattr(flap, "phase", "idle")
                if pending is not None or phase != "idle":
                    flap.AnimateTo(tgt, "", [], startDelayMs=startDelayMs)
            except:
                pass
            return

        steps = flap.AnimateDigit(cur, tgt, ascending=True, allowed=[str(i) for i in range(10)])
        if not steps:
            return

        chatter = []
        for s in steps[:-1]:
            chatter.append((s, ""))

        flap.AnimateTo(steps[-1], "", chatter, startDelayMs=startDelayMs)


    
    def AnimatePlatCharTo(self, flap, charTarget, startDelayMs=0, multiChange=False):
        cur = (flap.curTop or " ")
        tgt = (charTarget or " ")

        if cur == tgt:
            # If an earlier stage left a pending/active animation on this flap (e.g. blank-stage),
            # we must still assert the target so that the pending animation cannot overwrite it later.
            try:
                pending = getattr(flap, "pendingTimer", None)
                phase = getattr(flap, "phase", "idle")
                if pending is not None or phase != "idle":
                    flap.AnimateTo(tgt, "", [], startDelayMs=startDelayMs)
            except:
                pass
            return

        allowed = list(getattr(self, "lastPlatCharsAllowed", [])) or [str(i) for i in range(10)]
        if tgt not in allowed:
            flap.AnimateTo(tgt, "", [], startDelayMs=startDelayMs)
            return

        steps = flap.AnimateDigit(cur, tgt, ascending=True, allowed=allowed)
        if not steps:
            return

        chatter = []
        for s in steps[:-1]:
            chatter.append((s, ""))

        flap.AnimateTo(steps[-1], "", chatter, startDelayMs=startDelayMs)

# --------------------------- Window/controller -----------------------------
class SolariWindow(object):
    def __init__(self):
        self.numCols = ReadInt("TAS_USER_SETTING_STRIP_COLUMNS", 5, 1, 16)

        self.frame = swing.JFrame("Departures")
        self.frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        cp = self.frame.getContentPane()
        cp.setBackground(PANEL_BG); cp.setLayout(None)

        # Build boards; use each board's computed width/height consistently
        self.boards = []
        self._boardTimers = []
        self._refreshSerial = 0
        x = OUTER_PAD; y = OUTER_PAD
        # Create one board to learn width/height
        probe = SolariBoard()
        bw = probe.boardW; bh = probe.boardH
        probe.setBounds(x, y, bw, bh); cp.add(probe); self.boards.append(probe)
        x += bw + BOARD_GAP
        for i in range(1, self.numCols):
            b = SolariBoard()
            b.setBounds(x, y, bw, bh); cp.add(b); self.boards.append(b)
            x += bw + BOARD_GAP

        # Frame size (content + insets)
        try:
            self.frame.addNotify()
            ins = self.frame.getInsets()
            iw, ih = (ins.left + ins.right), (ins.top + ins.bottom)
        except:
            iw = ih = 0
        contentW = OUTER_PAD*2 + self.numCols*bw + (self.numCols-1)*BOARD_GAP
        contentH = OUTER_PAD*2 + bh
        self.frame.setSize(int(contentW + iw), int(contentH + ih))

        # Listeners (change-driven only)
        import java.beans as beans
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb): innerSelf.cb = cb
            def propertyChange(innerSelf, e):
                try: innerSelf.cb(e)
                except Exception as ex: print("[PIDSolari] listener error:", ex)
        self._pcl = PCL(self.Refresh)
        if TimeMem is not None: TimeMem.addPropertyChangeListener(self._pcl)
        if DayMem  is not None: DayMem.addPropertyChangeListener(self._pcl)
        if TTMem   is not None: TTMem.addPropertyChangeListener(self._pcl)
        try:
            PAR.addPlatformListener(self._pcl)
        except Exception as ex:
            try: print("[PIDSolari] PAR add listener failed:", ex)
            except: pass

        self.Refresh(None)
        self.frame.setVisible(True)

        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(innerSelf, e): self.Cleanup()
            def windowClosed(innerSelf, e): self.Cleanup()
        self.frame.addWindowListener(CloseHandler())

    def Refresh(self, e):
        # Update boards left-to-right, one at a time, by staggering board start times.
        self._refreshSerial += 1
        serial = int(self._refreshSerial)

        # Cancel any pending board start timers.
        try:
            for t in list(self._boardTimers or []):
                try:
                    t.stop()
                except:
                    pass
        except:
            pass
        self._boardTimers = []

        try:
            services, destPool, viaPool, platCharSet, maxPlatNum = NextServices(self.numCols)

            for idx in range(self.numCols):
                board = self.boards[idx]
                try:
                    startDelay = int(idx) * int(BOARD_CASCADE_MS)
                except:
                    startDelay = 0
                if startDelay < 0:
                    startDelay = 0

                def _MakeRun(i, b, delayMs):
                    def _Run(ev):
                        # Ignore stale refresh sequences.
                        if int(self._refreshSerial) != serial:
                            return
                        try:
                            if i >= len(services):
                                # Clear board i with chatter to blank.
                                b.BeginClearTransition(destPool, viaPool, platCharSet, maxPlatNum)
                                return

                            svc = services[i]
                            b.ApplyService(svc, destPool, viaPool, platCharSet, maxPlatNum)
                        except Exception as ex:
                            try:
                                print("[PIDSolari] Refresh board error:", ex)
                            except:
                                pass

                    tm = Timer(delayMs, _Run)
                    tm.setRepeats(False)
                    tm.start()
                    try:
                        self._boardTimers.append(tm)
                    except:
                        pass

                _MakeRun(idx, board, startDelay)

        except Exception as ex:
            print("[PIDSolari] Refresh error:", ex)

    def Cleanup(self):
        try:
            if TimeMem is not None: TimeMem.removePropertyChangeListener(self._pcl)
            if DayMem  is not None: DayMem.removePropertyChangeListener(self._pcl)
            if TTMem   is not None: TTMem.removePropertyChangeListener(self._pcl)
        except: pass
        try:
            PAR.removePlatformListener(self._pcl)
        except: pass
        try:
            if self.frame: self.frame.dispose()
        except: pass
        self._pcl = None

# Entry point
PIDSolari_Manager = SolariWindow()
