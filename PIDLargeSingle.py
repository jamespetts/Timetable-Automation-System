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
#
# <<PID-DISP-NAME: Orange LED single-platform display>>
# <<DESCRIPTION: A board showing the next departure and calling pattern per platform using an orange LED matrix as commonly installed by Network Rail in the 2000s>>
# <<SETTING DESCRIPTION NUMBER: Only show trains due within (minutes)>>
# <<SETTING DESCRIPTION NUMBER: Page interval (seconds)>>
# <<SETTING DESCRIPTION NUMBER: Platform/status flip interval (seconds)>>
# <<SETTING DESCRIPTION BOOLEAN: Require platform allocation>>
# <<SETTING DESCRIPTION BOOLEAN: Hide platform until allocated>>
# <<SETTING DESCRIPTION NUMBER: Special text scroll speed \(px per second\)>>
# <<SETTING DESCRIPTION NUMBER: Special text scroll pause \(ms\)>>
#
# Notes:
# - One window per platform (platforms discovered from the current timetable file), mirroring PIDCRTSingle.py.
# - Only services for the relevant platform are shown in that platform's window.
# - Layout is the same as PIDLarge.py except for the requested revisions:
#   (1) Company name uses calling-pattern font size and is left aligned.
#   (2) Current time-of-day is shown on the right of the company row as HH:MM:SS, with seconds 2pt smaller.
#   (3) When nothing is due within the selected window (or when allocation is required but missing), show:
#       (a) '...' in the company position; (b) the time-of-day; (c) a centered welcome message in the calling rows.
#
import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font
from javax.swing import Timer, BorderFactory
import jmri
from jmri import InstanceManager
from java.lang import System
import os, csv
import java.text.SimpleDateFormat as SimpleDateFormat
import java.util.Calendar as Calendar
import TASBeanLookup as TBL
import TASPathResolver
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption

# ---------------- Theme and geometry (copied from PIDLarge.py) ----------------
FRAME_COLOR = Color.BLACK
PANEL_COLOR = Color(30, 20, 0)
TEXT_COLOR = Color(255, 200, 50)

# Slightly smaller across the board to avoid clipping
TOP_FONT_SIZE = 22
MID_FONT_SIZE = 14
DEFAULT_TOP_FONT = Font("SansSerif", Font.BOLD, TOP_FONT_SIZE)
DEFAULT_MID_FONT = Font("SansSerif", Font.BOLD, MID_FONT_SIZE)

# Single-column geometry matches one column of PIDLarge.py
COL_WIDTH = 252
OUTER_MARGIN = 8
INNER_PAD = 8
ROW_GAP = 0

# Row heights
TIME_H = 44
DEST_H = 34
VIA_H = 24
VIA_TO_CALLING_GAP_H = 16
HEADER_H = 22
CALLING_LINES = 16
CALL_LINE_H = 18
COMPANY_H = 36

# Borders
RULE_THICK = 6
CALL_RULE_THICK = 3
TOP_RULE_THICK = 6
ROW_RULE_BORDER = BorderFactory.createMatteBorder(0, 0, RULE_THICK, 0, Color.BLACK)
TOP_ROW_RULE_BORDER = BorderFactory.createMatteBorder(TOP_RULE_THICK, 0, RULE_THICK, 0, Color.BLACK)
CALL_LINE_BORDER = BorderFactory.createMatteBorder(0, 0, CALL_RULE_THICK, 0, Color.BLACK)

# Text padding
V_PAD = 2
PAD_LR = BorderFactory.createEmptyBorder(V_PAD, INNER_PAD, V_PAD, INNER_PAD)
PAD_L = BorderFactory.createEmptyBorder(V_PAD, INNER_PAD, V_PAD, 0)
PAD_R = BorderFactory.createEmptyBorder(V_PAD, 0, V_PAD, INNER_PAD)

# Keep column edge rules (module separators)
COL_BORDER = BorderFactory.createMatteBorder(0, 2, 0, 2, Color.BLACK)

# ---------------- Memories (prefix-agnostic via TASBeanLookup) ----------------
TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# TASSetup "Options" -> memory names
# Derive memory names from the <<SETTING DESCRIPTION ...>> label text using the
# same normalisation rule as TASSetup.py.
def _SettingMemoryName(label):
    try:
        s = str(label).strip()
    except:
        s = ""
    import re as _re
    key = _re.sub(r"[^A-Za-z0-9]+", "_", s).upper()
    return "TAS_USER_SETTING_" + key

MEM_WithinMins = _SettingMemoryName("Only show trains due within (minutes)")
MEM_PageSecs = _SettingMemoryName("Page interval (seconds)")
MEM_FlipSecs = _SettingMemoryName("Platform/status flip interval (seconds)")
MEM_RequireAlloc = _SettingMemoryName("Require platform allocation")
MEM_HidePlat = _SettingMemoryName("Hide platform until allocated")
MEM_MarqueeSpeed = _SettingMemoryName("Special text scroll speed (px per second)")
MEM_MarqueePause = _SettingMemoryName("Special text scroll pause (ms)")

# ---------------- Fast clock ----------------
Timebase = InstanceManager.getDefault(jmri.Timebase)

# ---------------- Time parsing helpers ----------------
Fmt24 = SimpleDateFormat("HH:mm")
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
    return None

def FormatHHmm(schedText):
    for p in [Parser12, Parser24]:
        try:
            d = p.parse(schedText)
            return Fmt24.format(d)
        except:
            pass
    s = (schedText or "").strip()
    if ":" in s and len(s) <= 5:
        return s
    return s

def MinutesToHHmm(total):
    if total is None:
        return ""
    total %= (24 * 60)
    h = total // 60
    m = total % 60
    return ("%02d:%02d" % (h, m))

def DeltaMinutes(nowMin, futureMin):
    # Minutes from now to futureMin, wrapping over midnight.
    if nowMin is None or futureMin is None:
        return None
    return (int(futureMin) - int(nowMin)) % (24 * 60)

# ---------------- CSV access ----------------
def TimetablePath():
    name = TBL.SafeGetOrCreateMemoryValue("CURRENTTIMETABLE", "").strip()
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
        f = open(path, "r")
        try:
            rdr = csv.DictReader(f, delimiter="\t")
            for r in rdr:
                out.append(r)
        finally:
            f.close()
    except:
        return []
    return out

def CaseInsensitive(row, key):
    target = (key or "").strip().lower()
    try:
        keys = row.keys() or []
    except:
        keys = []
    for k in keys:
        if (k or "").strip().lower() == target:
            try:
                return (row.get(k, "") or "").strip()
            except:
                return ""
    return ""

def PlatformField(row):
    val = (row.get("Plat", "") or "").strip()
    if val == "":
        val = (row.get("Platform", "") or "").strip()
    return val

def ParseOverrides(s):
    out = {}
    s = (s or "")
    for part in s.replace(",", ";").split(";"):
        p = part.strip()
        if p == "" or "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[(k or "").strip()] = (v or "").strip()
    return out

def GetOverride(rn):
    try:
        raw = OverridesMem.getValue() if OverridesMem else ""
        return ParseOverrides(raw).get(rn)
    except:
        return None

# ---------------- Departure TP selection & CLEAR-ON-DEPARTURE ----------------
def ActiveProfileBaseTPName():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""

def DepartureTPList():
    names = []
    try:
        raw = DepartTPMem.getValue() if DepartTPMem else None
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

def HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
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


# ---------------- Disruption inheritance ----------------
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
    # Else inherit from 'Forms'
    formers = []
    for r in rowsToday:
        if (CaseInsensitive(r, "Forms") or "") == rn:
            arr = CaseInsensitive(r, "Arr")
            arrMin = ParseMinutes(arr) if arr else None
            formers.append((r, arrMin))
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
    formerRN = CaseInsensitive(chosen, "Reporting number")
    return ResolveDelayWithInheritance(rowsToday, formerRN, schedDepMin, visited)

# ---------------- Fit helper (from PIDLarge.py) ----------------
def ScaleTextToFit(label, text, maxSize, minSize, widthPx):
    fam = label.getFont().getFamily()
    style = label.getFont().getStyle()
    for sz in range(int(maxSize), int(minSize) - 1, -1):
        f = Font(fam, style, sz)
        fm = label.getFontMetrics(f)
        if fm.stringWidth(text) <= int(widthPx):
            label.setFont(f)
            label.setText(text)
            return
    label.setFont(Font(fam, style, int(minSize)))
    label.setText(text)

# ---------------- Service model ----------------
class ServiceModel(object):
    def __init__(self, row, dayName, nowMinutes):
        self.RN = CaseInsensitive(row, "Reporting number")
        self.DepStr = CaseInsensitive(row, "Dep")
        self.Dest = CaseInsensitive(row, "Destination")
        self.Via = CaseInsensitive(row, "Via")
        self.CoName = CaseInsensitive(row, "Company")
        self.Call = CaseInsensitive(row, "Calling pattern")
        self.Special = CaseInsensitive(row, "Special")
        self.DepMin = ParseMinutes(self.DepStr)

        alloc = PAR.getPlatform(self.RN)
        if alloc is not None and str(alloc).strip() != "":
            self.Plat = str(alloc).strip()
            self.HasAlloc = True
        else:
            self.Plat = (GetOverride(self.RN) or PlatformField(row) or "").strip()
            self.HasAlloc = False

        self.Departed = HasDepartedAtConfiguredTP(self.RN, dayName, nowMinutes)
        self.Status = ""
        self.ShowTime = FormatHHmm(self.DepStr)
        self.AdjMin = self.DepMin if self.DepMin is not None else 9999

# ---------------- Column panel ----------------
# ---------------- Special text marquee label (single-pass scroll, blank pause) ----------------
class MarqueeLabel(swing.JLabel):
    def __init__(self):
        swing.JLabel.__init__(self, "")
        self.setOpaque(True)
        self.setBackground(PANEL_COLOR)
        self.setForeground(TEXT_COLOR)
        self.setFont(DEFAULT_MID_FONT)
        self.MarqueeText = ""
        self.MarqueeActive = False
        self.ScrollState = "scroll"
        self.ScrollX = 0.0
        self.LastTickMs = None
        self.PauseUntilMs = None
        self.PauseMs = 2000
        self.SpeedPxPerSec = 60.0
        self._TextWidthPx = None

    def SetTuning(self, speedPxPerSec, pauseMs):
        try:
            self.SpeedPxPerSec = float(speedPxPerSec)
        except:
            pass
        try:
            self.PauseMs = int(pauseMs)
        except:
            pass

    def SetMarqueeText(self, txt):
        try:
            self.MarqueeText = "" if txt is None else str(txt)
        except:
            self.MarqueeText = ""
        self._TextWidthPx = None
        self.LastTickMs = None
        self.PauseUntilMs = None
        if self.MarqueeActive:
            self._ResetStartPosition()

    def _ResetStartPosition(self):
        try:
            ins = self.getInsets()
            avail = int(self.getWidth()) - int(ins.left) - int(ins.right)
        except:
            avail = int(self.getWidth())
        if avail < 0:
            avail = 0
        self.ScrollState = "scroll"
        self.ScrollX = float(avail)

    def SetMarqueeActive(self, active):
        try:
            self.MarqueeActive = bool(active)
        except:
            self.MarqueeActive = False
        self.LastTickMs = None
        self.PauseUntilMs = None
        self._TextWidthPx = None
        if self.MarqueeActive:
            try:
                swing.JLabel.setText(self, "")
            except:
                pass
            self._ResetStartPosition()
        try:
            self.repaint()
        except:
            pass

    def _MeasureTextWidth(self):
        if self._TextWidthPx is not None:
            return int(self._TextWidthPx)
        try:
            fm = self.getFontMetrics(self.getFont())
            w = fm.stringWidth(self.MarqueeText)
            self._TextWidthPx = int(w)
            return int(w)
        except:
            self._TextWidthPx = 0
            return 0

    def Tick(self, nowMs):
        if not self.MarqueeActive:
            return
        if self.MarqueeText is None or str(self.MarqueeText).strip() == "":
            return
        try:
            if self.LastTickMs is None:
                self.LastTickMs = int(nowMs)
                return
            dt = float(int(nowMs) - int(self.LastTickMs)) / 1000.0
            self.LastTickMs = int(nowMs)
        except:
            dt = 0.04
        if dt < 0.0:
            dt = 0.0
        if dt > 0.25:
            dt = 0.25
        tw = self._MeasureTextWidth()
        if self.ScrollState == "scroll":
            try:
                self.ScrollX = float(self.ScrollX) - (float(self.SpeedPxPerSec) * dt)
            except:
                self.ScrollX = float(self.ScrollX) - (60.0 * dt)
            if float(self.ScrollX) < -float(tw):
                self.ScrollState = "pause"
                try:
                    self.PauseUntilMs = int(nowMs) + int(self.PauseMs)
                except:
                    self.PauseUntilMs = None
        else:
            try:
                if self.PauseUntilMs is not None and int(nowMs) >= int(self.PauseUntilMs):
                    self.PauseUntilMs = None
                    self._ResetStartPosition()
            except:
                pass
        try:
            self.repaint()
        except:
            pass

    def paintComponent(self, g):
        # In Jython/JMRI, javax.swing.JLabel.paintComponent is protected and not exposed.
        # Paint background and either delegate normal paint or custom marquee.
        w = self.getWidth()
        h = self.getHeight()
        try:
            if self.isOpaque():
                g.setColor(self.getBackground())
                g.fillRect(0, 0, int(w), int(h))
        except:
            pass
        if not getattr(self, 'MarqueeActive', False):
            try:
                ui = self.getUI()
                if ui is not None:
                    ui.paint(g, self)
            except:
                pass
            return
        if getattr(self, 'ScrollState', 'scroll') != 'scroll':
            return
        msg = ''
        try:
            msg = self.MarqueeText
        except:
            msg = ''
        if msg is None or str(msg).strip() == '':
            return
        try:
            g2 = g.create()
        except:
            g2 = g
        try:
            fnt = self.getFont()
            g2.setFont(fnt)
            g2.setColor(TEXT_COLOR)
            fm = self.getFontMetrics(fnt)
            ins = self.getInsets()
            x = int(ins.left) + int(getattr(self, 'ScrollX', 0.0))
            y = (int(h) + int(fm.getAscent()) - int(fm.getDescent())) // 2
            g2.drawString(str(msg), x, y)
        except:
            pass
        try:
            g2.dispose()
        except:
            pass

class ColumnPanel(swing.JPanel):
    def __init__(self):
        swing.JPanel.__init__(self)
        self.setBackground(Color.BLACK)
        self.setLayout(None)
        self.setBorder(COL_BORDER)

        y = 0
        # Top row: departure time (left) and platform/status (right)
        leftW = int(COL_WIDTH * 0.46)
        rightW = COL_WIDTH - leftW

        self.lblDepTime = swing.JLabel("")
        self.lblDepTime.setForeground(TEXT_COLOR)
        self.lblDepTime.setFont(DEFAULT_TOP_FONT)
        self.lblDepTime.setOpaque(True)
        self.lblDepTime.setBackground(PANEL_COLOR)
        self.lblDepTime.setBounds(0, y, leftW, TIME_H)
        self.lblDepTime.setBorder(BorderFactory.createCompoundBorder(TOP_ROW_RULE_BORDER, PAD_L))
        self.add(self.lblDepTime)

        self.lblPlatOrStatus = swing.JLabel("")
        self.lblPlatOrStatus.setForeground(TEXT_COLOR)
        self.lblPlatOrStatus.setFont(DEFAULT_TOP_FONT)
        self.lblPlatOrStatus.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.lblPlatOrStatus.setOpaque(True)
        self.lblPlatOrStatus.setBackground(PANEL_COLOR)
        self.lblPlatOrStatus.setBounds(leftW, y, rightW, TIME_H)
        self.lblPlatOrStatus.setBorder(BorderFactory.createCompoundBorder(TOP_ROW_RULE_BORDER, PAD_R))
        self.add(self.lblPlatOrStatus)

        y += TIME_H + ROW_GAP

        # Destination
        self.lblDest = swing.JLabel("")
        self.lblDest.setForeground(TEXT_COLOR)
        self.lblDest.setFont(DEFAULT_TOP_FONT)
        self.lblDest.setOpaque(True)
        self.lblDest.setBackground(PANEL_COLOR)
        self.lblDest.setBounds(0, y, COL_WIDTH, DEST_H)
        self.lblDest.setBorder(BorderFactory.createCompoundBorder(ROW_RULE_BORDER, PAD_LR))
        self.add(self.lblDest)

        y += DEST_H + ROW_GAP

        # Via
        self.lblVia = swing.JLabel("")
        self.lblVia.setForeground(TEXT_COLOR)
        self.lblVia.setFont(DEFAULT_MID_FONT)
        self.lblVia.setOpaque(True)
        self.lblVia.setBackground(PANEL_COLOR)
        self.lblVia.setBounds(0, y, COL_WIDTH, VIA_H)
        self.lblVia.setBorder(BorderFactory.createCompoundBorder(ROW_RULE_BORDER, PAD_LR))
        self.add(self.lblVia)

        y += VIA_H + ROW_GAP

        # Gap band
        self.lblViaCallingGap = swing.JLabel("")
        self.lblViaCallingGap.setOpaque(True)
        self.lblViaCallingGap.setBackground(Color.BLACK)
        self.lblViaCallingGap.setBounds(0, y, COL_WIDTH, VIA_TO_CALLING_GAP_H)
        self.lblViaCallingGap.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 0))
        self.add(self.lblViaCallingGap)

        y += VIA_TO_CALLING_GAP_H + ROW_GAP

        # Calling at: + page indicator
        halfW = int(COL_WIDTH * 0.50)
        self.lblCallingTitle = swing.JLabel("Calling at:")
        self.lblCallingTitle.setForeground(TEXT_COLOR)
        self.lblCallingTitle.setFont(DEFAULT_MID_FONT)
        self.lblCallingTitle.setOpaque(True)
        self.lblCallingTitle.setBackground(PANEL_COLOR)
        self.lblCallingTitle.setBounds(0, y, halfW, HEADER_H)
        self.lblCallingTitle.setBorder(BorderFactory.createCompoundBorder(ROW_RULE_BORDER, PAD_L))
        self.add(self.lblCallingTitle)

        self.lblPage = swing.JLabel("")
        self.lblPage.setForeground(TEXT_COLOR)
        self.lblPage.setFont(DEFAULT_MID_FONT)
        self.lblPage.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.lblPage.setOpaque(True)
        self.lblPage.setBackground(PANEL_COLOR)
        self.lblPage.setBounds(halfW, y, COL_WIDTH - halfW, HEADER_H)
        self.lblPage.setBorder(BorderFactory.createCompoundBorder(ROW_RULE_BORDER, PAD_R))
        self.add(self.lblPage)

        y += HEADER_H + ROW_GAP

        # 16 fixed calling lines
        self.callLabels = []
        for i in range(CALLING_LINES):
            if i == (CALLING_LINES - 1):
                lbl = MarqueeLabel()
            else:
                lbl = swing.JLabel("")
            lbl.setForeground(TEXT_COLOR)
            lbl.setFont(DEFAULT_MID_FONT)
            lbl.setOpaque(True)
            lbl.setBackground(PANEL_COLOR)
            lbl.setHorizontalAlignment(swing.SwingConstants.LEFT)
            lbl.setBounds(0, y + i * CALL_LINE_H, COL_WIDTH, CALL_LINE_H)
            lbl.setBorder(BorderFactory.createCompoundBorder(CALL_LINE_BORDER, PAD_LR))
            self.callLabels.append(lbl)
            self.add(lbl)

        y += CALL_LINE_H * CALLING_LINES + ROW_GAP

        # Company row (left) + clock (right)
        # Revision: company uses calling-pattern font size and is left aligned.
        leftCoW = int(COL_WIDTH * 0.66)
        rightClockW = COL_WIDTH - leftCoW

        self.lblCompany = swing.JLabel("")
        self.lblCompany.setForeground(TEXT_COLOR)
        self.lblCompany.setFont(DEFAULT_MID_FONT)
        self.lblCompany.setHorizontalAlignment(swing.SwingConstants.LEFT)
        self.lblCompany.setOpaque(True)
        self.lblCompany.setBackground(PANEL_COLOR)
        self.lblCompany.setBounds(0, y, leftCoW, COMPANY_H)
        self.lblCompany.setBorder(BorderFactory.createCompoundBorder(ROW_RULE_BORDER, PAD_L))
        self.add(self.lblCompany)

        # Clock: two labels so seconds can be 2pt smaller.
        self.clockPanel = swing.JPanel(None)
        self.clockPanel.setOpaque(True)
        self.clockPanel.setBackground(PANEL_COLOR)
        self.clockPanel.setBounds(leftCoW, y, rightClockW, COMPANY_H)
        self.clockPanel.setBorder(BorderFactory.createCompoundBorder(ROW_RULE_BORDER, PAD_R))
        self.add(self.clockPanel)

        self.lblClockHM = swing.JLabel("")
        self.lblClockHM.setForeground(TEXT_COLOR)
        self.lblClockHM.setFont(DEFAULT_MID_FONT)
        self.lblClockHM.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.lblClockHM.setOpaque(False)
        self.clockPanel.add(self.lblClockHM)

        self.lblClockSS = swing.JLabel("")
        self.lblClockSS.setForeground(TEXT_COLOR)
        self.lblClockSS.setFont(Font(DEFAULT_MID_FONT.getFamily(), DEFAULT_MID_FONT.getStyle(), max(8, MID_FONT_SIZE - 2)))
        self.lblClockSS.setHorizontalAlignment(swing.SwingConstants.LEFT)
        self.lblClockSS.setOpaque(False)
        self.clockPanel.add(self.lblClockSS)

        # Size the clock labels within clockPanel on first layout.
        self._LayoutClockLabels()

        y += COMPANY_H
        bottomPad = 2
        self.computedHeight = y + bottomPad

        self.flipShowPlatform = True

    def _LayoutClockLabels(self):
        # Position lblClockHM and lblClockSS so the combined time is right-aligned.
        try:
            W = self.clockPanel.getWidth()
            H = self.clockPanel.getHeight()
            if W <= 0 or H <= 0:
                # If called before bounds set, use expected.
                W = int(COL_WIDTH * 0.34)
                H = COMPANY_H
            hm = self.lblClockHM.getText() or "00:00"
            ss = self.lblClockSS.getText() or ":00"
            fmHm = self.lblClockHM.getFontMetrics(self.lblClockHM.getFont())
            fmSs = self.lblClockSS.getFontMetrics(self.lblClockSS.getFont())
            wHm = fmHm.stringWidth(hm)
            wSs = fmSs.stringWidth(ss)
            total = wHm + wSs
            x0 = max(0, W - total)
            y0 = 0
            self.lblClockHM.setBounds(x0, y0, wHm, H)
            self.lblClockSS.setBounds(x0 + wHm, y0, wSs, H)
        except:
            pass

    # Render helpers
    def SetDepartureTimeText(self, text):
        ScaleTextToFit(self.lblDepTime, (text or ""), TOP_FONT_SIZE, 16, self.lblDepTime.getWidth())

    def SetPlatOrStatus(self, platText, statusText, hidePlatformUntilAlloc=False, hasAlloc=False):
        shown = platText if (self.flipShowPlatform and not (hidePlatformUntilAlloc and (not hasAlloc))) else statusText
        ScaleTextToFit(self.lblPlatOrStatus, (shown or ""), TOP_FONT_SIZE, 14, self.lblPlatOrStatus.getWidth())

    def SetDestination(self, dest):
        ScaleTextToFit(self.lblDest, (dest or ""), TOP_FONT_SIZE, 16, self.lblDest.getWidth())

    def SetVia(self, via):
        txt = ("via " + via) if via else ""
        ScaleTextToFit(self.lblVia, txt, MID_FONT_SIZE, 12, self.lblVia.getWidth())

    def SetPageIndicator(self, cur, total):
        self.lblPage.setFont(DEFAULT_MID_FONT)
        if int(total) > 1:
            self.lblPage.setText("Page %d of %d" % (int(cur), int(total)))
        else:
            self.lblPage.setText("Page 1 of 1")

    def SetPageText(self, txt):
        self.lblPage.setFont(DEFAULT_MID_FONT)
        self.lblPage.setText(txt or "")

    def SetCallingTitleText(self, txt):
        self.lblCallingTitle.setFont(DEFAULT_MID_FONT)
        self.lblCallingTitle.setText(txt or "")

    def SetCallingPage(self, lines16, alignCenter=False):
        for i in range(CALLING_LINES):
            txt = lines16[i] if i < len(lines16) else ""
            self.callLabels[i].setFont(DEFAULT_MID_FONT)
            self.callLabels[i].setText(txt or "")
            self.callLabels[i].setHorizontalAlignment(swing.SwingConstants.CENTER if alignCenter else swing.SwingConstants.LEFT)


    def SetSpecialText(self, text):
        try:
            lbl = self.callLabels[CALLING_LINES - 1]
        except:
            lbl = None
        if lbl is None:
            return
        try:
            if hasattr(lbl, "SetMarqueeText"):
                lbl.SetMarqueeText(text)
        except:
            pass

    def SetSpecialActive(self, active):
        try:
            lbl = self.callLabels[CALLING_LINES - 1]
        except:
            lbl = None
        if lbl is None:
            return
        try:
            if hasattr(lbl, "SetMarqueeActive"):
                lbl.SetMarqueeActive(active)
        except:
            pass

    def SetSpecialTuning(self, speedPxPerSec, pauseMs):
        try:
            lbl = self.callLabels[CALLING_LINES - 1]
        except:
            lbl = None
        if lbl is None:
            return
        try:
            if hasattr(lbl, "SetTuning"):
                lbl.SetTuning(speedPxPerSec, pauseMs)
        except:
            pass

    def AdvanceSpecialScroll(self, nowMs):
        try:
            lbl = self.callLabels[CALLING_LINES - 1]
        except:
            lbl = None
        if lbl is None:
            return
        try:
            if hasattr(lbl, "Tick"):
                lbl.Tick(nowMs)
        except:
            pass

    def SetCompany(self, co):
        # Revision: company font matches calling-pattern font.
        ScaleTextToFit(self.lblCompany, (co or ""), MID_FONT_SIZE, 12, self.lblCompany.getWidth())

    def SetClock(self, hhmm, ss):
        # hhmm should be HH:MM, ss should be :SS
        self.lblClockHM.setText(hhmm or "")
        self.lblClockSS.setText(ss or "")
        self._LayoutClockLabels()

# ---------------- Platform window ----------------
class PlatformStripWindow(object):
    def __init__(self, platform, OnCloseCallback=None):
        self.Platform = str(platform)
        self.OnCloseCallback = OnCloseCallback
        self.CleanedUp = False

        # Settings (shared across all windows)
        self.withinMins = self._ReadInt(MEM_WithinMins, 60, minVal=0, maxVal=1440)
        self.pageSecs = self._ReadInt(MEM_PageSecs, 10, minVal=2, maxVal=120)
        self.flipSecs = self._ReadInt(MEM_FlipSecs, 5, minVal=2, maxVal=60)
        self.requireAlloc = self._ReadBool(MEM_RequireAlloc, False)
        self.hidePlat = self._ReadBool(MEM_HidePlat, False)
        self.marqueeSpeed = self._ReadInt(MEM_MarqueeSpeed, 60, minVal=10, maxVal=300)
        self.marqueePause = self._ReadInt(MEM_MarqueePause, 2000, minVal=0, maxVal=20000)

        # Paging state
        self.pages = []
        self.pageIndex = 0

        # Flip cache
        self._FlipPlatLabel = ""
        self._FlipStatusLabel = ""
        self._FlipHasAlloc = False
        self._SpecialTxt = ""

        # Window
        self.frame = swing.JFrame("Platform " + self.Platform)
        self.frame.setResizable(False)
        self.frame.setDefaultCloseOperation(swing.JFrame.DO_NOTHING_ON_CLOSE)
        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setBackground(FRAME_COLOR)

        self.column = ColumnPanel()
        try:
            self.column.SetSpecialTuning(self.marqueeSpeed, self.marqueePause)
        except:
            pass
        colH = int(self.column.computedHeight)
        self.column.setBounds(OUTER_MARGIN, OUTER_MARGIN, COL_WIDTH, colH)
        cp.add(self.column)

        contentW = OUTER_MARGIN * 2 + COL_WIDTH
        contentH = OUTER_MARGIN * 2 + colH

        try:
            self.frame.addNotify()
        except:
            pass
        ins = self.frame.getInsets()
        if ins is None:
            insLeft = insRight = insTop = insBottom = 0
        else:
            insLeft, insRight = ins.left, ins.right
            insTop, insBottom = ins.top, ins.bottom
        self.frame.setSize(int(contentW + insLeft + insRight), int(contentH + insTop + insBottom))

        # Timers
        self.pageTimer = Timer(self.pageSecs * 1000, self._OnPageTick)
        self.flipTimer = Timer(self.flipSecs * 1000, self._OnFlipTick)
        self.clockTimer = Timer(1000, self._OnClockTick)
        self.specialTimer = Timer(40, self._OnSpecialTick)
        self.pageTimer.setRepeats(True)
        self.flipTimer.setRepeats(True)
        self.clockTimer.setRepeats(True)
        self.specialTimer.setRepeats(True)

        # Listener
        import java.beans as beans
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb):
                innerSelf.cb = cb
            def propertyChange(innerSelf, e):
                try:
                    innerSelf.cb(e)
                except Exception as ex:
                    try:
                        print "[PIDLargeSingle] listener error: %s" % str(ex)
                    except:
                        pass
        self._Pcl = PCL(self.Refresh)

        TimeMem.addPropertyChangeListener(self._Pcl)
        DayMem.addPropertyChangeListener(self._Pcl)
        if TimetableMem is not None:
            TimetableMem.addPropertyChangeListener(self._Pcl)
        if DepartTPMem is not None:
            DepartTPMem.addPropertyChangeListener(self._Pcl)
        if OverridesMem is not None:
            OverridesMem.addPropertyChangeListener(self._Pcl)
        try:
            PAR.addPlatformListener(self._Pcl)
        except Exception as ex:
            try:
                print "[PIDLargeSingle] PAR add listener failed: %s" % str(ex)
            except:
                pass

        # Close handler
        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(innerSelf, e):
                self.HandleUserClose()
        self._CloseHandler = CloseHandler()
        self.frame.addWindowListener(self._CloseHandler)

        # Icon
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)
        except:
            pass

        # Start
        self.Refresh()
        self._OnClockTick()  # set initial clock
        self.pageTimer.start()
        self.flipTimer.start()
        self.clockTimer.start()
        self.specialTimer.start()
        self.frame.setVisible(True)

    def _GetSettingRaw(self, memName, defaultStr):
        # Read a TAS user-setting memory by suffix in a prefix-agnostic way (matches TASSetup.py).
        # Ensure that a newly-created memory is initialised to defaultStr.
        try:
            m = TBL.ProvideMemoryBySuffix(memName, "")
        except:
            m = None
        if m is None:
            return defaultStr
        try:
            v = m.getValue()
        except:
            v = None
        s = "" if v is None else str(v)
        if s.strip() == "":
            try:
                m.setValue(str(defaultStr))
            except:
                pass
            return str(defaultStr)
        return s

    def _ReadInt(self, memName, defaultVal, minVal=None, maxVal=None):
        try:
            raw = self._GetSettingRaw(memName, str(int(defaultVal)))
            n = int(float(str(raw).strip()))
            if minVal is not None:
                n = max(minVal, n)
            if maxVal is not None:
                n = min(maxVal, n)
            return int(n)
        except:
            return int(defaultVal)

    def _ReadBool(self, memName, defaultVal=False):
        try:
            raw = self._GetSettingRaw(memName, "true" if defaultVal else "false")
            t = (str(raw).strip().lower())
            if t in ["1", "true", "yes", "y", "on", "enabled"]:
                return True
            if t in ["0", "false", "no", "n", "off", "disabled"]:
                return False
            return bool(defaultVal)
        except:
            return bool(defaultVal)
    def _CurrentMinutes(self):
        if Timebase is not None:
            ft = Timebase.getTime()
            return ft.getHours() * 60 + ft.getMinutes()
        curStr = TimeMem.getValue() or ""
        return ParseMinutes(curStr)

    def _RowsToday(self):
        rows = CsvRows()
        curDay = DayMem.getValue() or ""
        out = []
        for r in rows:
            try:
                if ((r.get(curDay, "") or "").strip().lower() == "true"):
                    out.append(r)
            except:
                pass
        return out

    def _ClockHHmmSs(self):
        # Return (HH:MM, :SS) for the fast clock if available; else seconds = 00.
        try:
            if Timebase is not None:
                d = Timebase.getTime()
                cal = Calendar.getInstance()
                cal.setTime(d)
                h = cal.get(Calendar.HOUR_OF_DAY)
                m = cal.get(Calendar.MINUTE)
                s = cal.get(Calendar.SECOND)
                return ("%02d:%02d" % (h, m), ":%02d" % s)
        except:
            pass
        # Fallback to memory minutes
        try:
            mm = self._CurrentMinutes()
            if mm is None:
                return ("", "")
            hhmm = MinutesToHHmm(mm)
            return (hhmm, ":00")
        except:
            return ("", "")

    def _WrapStationsIntoLines(self, text, maxWidthPx, font):
        s = (text or "").strip()
        if s == "":
            return []
        stations = [t.strip() for t in s.split(",")]
        if len(stations) > 0:
            stations[-1] = "& " + stations[-1]
        dummy = swing.JLabel("")
        fm = dummy.getFontMetrics(font)
        lines = []
        for st in stations:
            words = st.split(" ")
            cur = ""
            for w in words:
                test = (cur + (" " if cur != "" else "") + w)
                if fm.stringWidth(test) <= int(maxWidthPx):
                    cur = test
                else:
                    if cur != "":
                        lines.append(cur)
                        cur = w
                    else:
                        chunk = ""
                        for ch in w:
                            if fm.stringWidth(chunk + ch) <= int(maxWidthPx):
                                chunk += ch
                            else:
                                lines.append(chunk)
                                chunk = ch
                        cur = chunk
            if cur != "":
                lines.append(cur)
        if len(lines) > 0:
            lines[-1] = (lines[-1].rstrip(".") + ".")
        return lines

    def _Paginate16(self, physicalLines):
        pages = []
        if not physicalLines:
            pages.append([""] * CALLING_LINES)
            return pages
        i = 0
        total = len(physicalLines)
        while i < total:
            chunk = physicalLines[i:i + CALLING_LINES]
            if len(chunk) < CALLING_LINES:
                chunk = chunk + ([""] * (CALLING_LINES - len(chunk)))
            pages.append(chunk)
            i += CALLING_LINES
        return pages

    def _PaginateWithSpecial(self, physicalLines):
        # Page 1: 15 calling lines + special scroller in last line.
        # Page 2+: calling lines pushed down by one (top blank), 15 lines per page.
        pages = []
        lines = physicalLines or []
        if not lines:
            pages.append([""] * CALLING_LINES)
            return pages
        i = 0
        total = len(lines)
        while i < total:
            chunk = lines[i:i + 15]
            if len(chunk) < 15:
                chunk = chunk + ([""] * (15 - len(chunk)))
            if len(pages) == 0:
                page = chunk + [""]
            else:
                page = [""] + chunk
            pages.append(page)
            i += 15
        return pages

    def _NextServiceForPlatform(self):
        rowsToday = self._RowsToday()
        curMin = self._CurrentMinutes()
        if curMin is None:
            return None
        curDay = DayMem.getValue() or ""

        cands = []
        for r in rowsToday:
            dep = CaseInsensitive(r, "Dep")
            if dep == "":
                continue
            m = ServiceModel(r, curDay, curMin)
            if m.DepMin is None:
                continue
            if m.Departed:
                continue

            # Require allocation option: if enabled, ignore timetable/overrides and require PAR allocation.
            if self.requireAlloc:
                alloc = PAR.getPlatform(m.RN)
                if alloc is None or str(alloc).strip() == "":
                    continue
                if str(alloc).strip() != self.Platform:
                    continue
                m.Plat = str(alloc).strip()
                m.HasAlloc = True
            else:
                if (m.Plat or "") == "":
                    continue
                if str(m.Plat) != self.Platform:
                    continue

            kind, val = ResolveDelayWithInheritance(rowsToday, m.RN, m.DepMin, visited=set())           
            # Past-hiding consistent with PIDSmall:
            # - Cancelled: hide only if booked Dep < now.
            # - Delayed: hide only if expected (Dep + delay) < now.
            # - On-time: apply resilience (no disruption AND no timing seen today -> hide only if booked < now).
            if kind == "cancel":
                if m.DepMin < curMin:
                    continue
            elif (kind == "delay") and val and val > 0:
                try:
                    adj = m.DepMin + int(val)
                except:
                    adj = m.DepMin
                if adj < curMin:
                    continue
            else:
                # On-time resilience (inline 'seen today' check to avoid adding helpers here):
                try:
                    direct = getDisruption(m.RN)
                except:
                    direct = None
                seenToday = False
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
                            rn0 = rec[0]; d0 = rec[3]
                        except:
                            continue
                        if str(rn0) == str(m.RN) and str(d0) == str(curDay):
                            seenToday = True
                            break
                    if seenToday:
                        break
                if (direct is None) and (not seenToday):
                    if m.DepMin < curMin:
                        continue

            if kind == "cancel":
                m.Status = "Cancelled"
                m.ShowTime = "CANCELLED"
                m.AdjMin = 9999
            elif kind == "delay" and val and val > 0:
                m.Status = "Exp " + MinutesToHHmm(m.DepMin + val)
                m.ShowTime = MinutesToHHmm(m.DepMin + val)
                m.AdjMin = m.DepMin + val
            else:
                m.Status = "On time"
                m.ShowTime = FormatHHmm(m.DepStr)
                m.AdjMin = m.DepMin

            # Due-within window
            # TASSetup semantics: 0 means no limit.
            within = int(self.withinMins)
            if within > 0:
                delta = DeltaMinutes(curMin, m.AdjMin)
                if delta is None:
                    continue
                if not (0 <= delta <= within):
                    continue

            cands.append(m)

        if not cands:
            return None
        cands.sort(key=lambda t: t.AdjMin)
        return cands[0]

    def _ActiveProfileName(self):
        try:
            nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
            return ("" if nm is None else str(nm)).strip()
        except:
            return ""

    def _ShowWelcomeMode(self):
        # Clear all dynamic service fields and show welcome message.
        self.column.SetDepartureTimeText("")
        self.column.SetPlatOrStatus("", "", self.hidePlat, False)
        self.column.SetDestination("")
        self.column.SetVia("")
        self.column.SetCallingTitleText("")
        self.column.SetPageText("")

        lines = [""] * CALLING_LINES
        mid = CALLING_LINES // 2
        lines[mid - 1] = "Welcome to"
        lines[mid] = self._ActiveProfileName()
        self.column.SetCallingPage(lines, alignCenter=True)

        self._FlipPlatLabel = ""
        self._FlipStatusLabel = ""
        self._FlipHasAlloc = False
        self._SpecialTxt = ""
        try:
            self.column.SetSpecialText("")
            self.column.SetSpecialActive(False)
        except:
            pass
        self.column.SetCompany("...")

    def Refresh(self, e=None):
        # Make UI updates on the EDT.
        def _Do():
            # Re-read live settings that affect selection/display.
            try:
                self.withinMins = self._ReadInt(MEM_WithinMins, self.withinMins, minVal=0, maxVal=1440)
                self.hidePlat = self._ReadBool(MEM_HidePlat, self.hidePlat)
                self.marqueeSpeed = self._ReadInt(MEM_MarqueeSpeed, self.marqueeSpeed, minVal=10, maxVal=300)
                self.marqueePause = self._ReadInt(MEM_MarqueePause, self.marqueePause, minVal=0, maxVal=20000)
                try:
                    self.column.SetSpecialTuning(self.marqueeSpeed, self.marqueePause)
                except:
                    pass
            except:
                pass
            try:
                self.requireAlloc = self._ReadBool(MEM_RequireAlloc, self.requireAlloc)
            except:
                pass

            svc = self._NextServiceForPlatform()
            if svc is None:
                self.pages = []
                self.pageIndex = 0
                self._ShowWelcomeMode()
                return

            # Service display mode
            self.column.SetDepartureTimeText(FormatHHmm(svc.ShowTime))

            platLabel = "Platform " + self.Platform
            statusLabel = svc.Status or ""
            hasAlloc = False
            try:
                alloc = PAR.getPlatform(svc.RN)
                hasAlloc = (alloc is not None and str(alloc).strip() != "")
            except:
                hasAlloc = False
            self.column.SetPlatOrStatus(platLabel, statusLabel, self.hidePlat, hasAlloc)

            self._FlipPlatLabel = platLabel
            self._FlipStatusLabel = statusLabel
            self._FlipHasAlloc = hasAlloc

            self.column.SetDestination(svc.Dest)
            self.column.SetVia(svc.Via)
            physical = self._WrapStationsIntoLines(svc.Call, COL_WIDTH - 2 * INNER_PAD, DEFAULT_MID_FONT)
            specialTxt = (svc.Special or "").strip()
            self._SpecialTxt = specialTxt
            if specialTxt != "":
                self.pages = self._PaginateWithSpecial(physical)
            else:
                self.pages = self._Paginate16(physical)
            try:
                self.column.SetSpecialText(svc.Special)
            except:
                try:
                    self.column.SetSpecialText("")
                except:
                    pass
            if not self.pages:
                self.pages = [[""] * CALLING_LINES]
            self.pageIndex = max(0, min(len(self.pages) - 1, self.pageIndex))

            self.column.SetCallingTitleText("Calling at:")
            self.column.SetPageIndicator(self.pageIndex + 1, len(self.pages))
            self.column.SetCallingPage(self.pages[self.pageIndex], alignCenter=False)
            try:
                self.column.SetSpecialActive((self.pageIndex == 0) and (self._SpecialTxt != ""))
            except:
                pass

            self.column.SetCompany(svc.CoName)

        try:
            swing.SwingUtilities.invokeLater(_Do)
        except:
            try:
                _Do()
            except:
                pass

    def _OnPageTick(self, e=None):
        if not self.pages:
            return
        total = len(self.pages)
        if total <= 1:
            self.column.SetPageIndicator(1, 1)
            return
        self.pageIndex = (self.pageIndex + 1) % total
        self.column.SetPageIndicator(self.pageIndex + 1, total)
        self.column.SetCallingPage(self.pages[self.pageIndex], alignCenter=False)
        try:
            self.column.SetSpecialActive((self.pageIndex == 0) and (self._SpecialTxt != ""))
        except:
            pass

    def _OnFlipTick(self, e=None):
        try:
            self.column.flipShowPlatform = not bool(self.column.flipShowPlatform)
            self.column.SetPlatOrStatus(self._FlipPlatLabel, self._FlipStatusLabel, self.hidePlat, self._FlipHasAlloc)
        except:
            pass

    def _OnClockTick(self, e=None):
        hhmm, ss = self._ClockHHmmSs()
        try:
            self.column.SetClock(hhmm, ss)
        except:
            pass


    def _OnSpecialTick(self, e=None):
        nowMs = 0
        try:
            nowMs = System.currentTimeMillis()
        except:
            nowMs = 0
        if nowMs == 0:
            try:
                import time as _pyTime
                nowMs = int(_pyTime.time() * 1000)
            except:
                nowMs = 0
        try:
            self.column.AdvanceSpecialScroll(nowMs)
        except:
            pass

    def HandleUserClose(self):
        try:
            self.Cleanup()
        except:
            pass
        try:
            if self.OnCloseCallback is not None:
                self.OnCloseCallback(self.Platform, self)
        except:
            pass
        try:
            self.frame.dispose()
        except:
            pass

    def Cleanup(self):
        if self.CleanedUp:
            return
        self.CleanedUp = True
        try:
            if self.pageTimer:
                self.pageTimer.stop()
        except:
            pass
        try:
            if self.flipTimer:
                self.flipTimer.stop()
        except:
            pass
        try:
            if self.clockTimer:
                self.clockTimer.stop()
        except:
            pass
        try:
            if self.specialTimer:
                self.specialTimer.stop()
        except:
            pass

        try:
            PAR.removePlatformListener(self._Pcl)
        except:
            pass

        try:
            TimeMem.removePropertyChangeListener(self._Pcl)
        except:
            pass
        try:
            DayMem.removePropertyChangeListener(self._Pcl)
        except:
            pass
        try:
            if TimetableMem is not None:
                TimetableMem.removePropertyChangeListener(self._Pcl)
        except:
            pass
        try:
            if DepartTPMem is not None:
                DepartTPMem.removePropertyChangeListener(self._Pcl)
        except:
            pass
        try:
            if OverridesMem is not None:
                OverridesMem.removePropertyChangeListener(self._Pcl)
        except:
            pass

        try:
            if self.frame is not None and self._CloseHandler is not None:
                self.frame.removeWindowListener(self._CloseHandler)
        except:
            pass

        self.pageTimer = None
        self.flipTimer = None
        self.clockTimer = None
        self.specialTimer = None
        self._Pcl = None
        self._CloseHandler = None

# ---------------- Manager / run ----------------
class PlatformStripManager(object):
    def __init__(self):
        self.windows = {}

        import java.beans as beans
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb):
                innerSelf.cb = cb
            def propertyChange(innerSelf, e):
                try:
                    innerSelf.cb(e)
                except:
                    pass
        self._TimetableListener = PCL(self.Rebuild)

        if TimetableMem is not None:
            TimetableMem.addPropertyChangeListener(self._TimetableListener)

        # Also rebuild if overrides change (platform discovery may depend on timetable only, but refresh anyway)
        if OverridesMem is not None:
            OverridesMem.addPropertyChangeListener(PCL(self.RefreshAll))

        self.Rebuild()

    def _DiscoverPlatforms(self):
        plats = set()
        for r in CsvRows():
            p = PlatformField(r)
            if p:
                plats.add(str(p).strip())
        return sorted(list(plats), key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s))

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

    def Rebuild(self, e=None):
        plats = self._DiscoverPlatforms()

        # Create missing windows
        for p in plats:
            if p not in self.windows:
                self.windows[p] = PlatformStripWindow(p, self.UnregisterPlatform)

        # Remove obsolete windows
        for p in [x for x in self.windows.keys() if x not in plats]:
            try:
                self.windows[p].Cleanup()
                self.windows[p].frame.dispose()
            except:
                pass
            try:
                del self.windows[p]
            except:
                pass

        # Cascade
        x0, y0, dx, dy = 40, 40, 16, 16
        try:
            keys = sorted(self.windows.keys(), key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s))
        except:
            keys = list(self.windows.keys())
        for i, p in enumerate(keys):
            try:
                self.windows[p].frame.setLocation(x0 + dx * i, y0 + dy * i)
            except:
                pass

        self.RefreshAll()

    def RefreshAll(self, e=None):
        for w in list(self.windows.values()):
            try:
                w.Refresh()
            except:
                pass

PIDLargeSingle_Manager = PlatformStripManager()
