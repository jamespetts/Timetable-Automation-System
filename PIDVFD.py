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
#
# <<PID-DISP-NAME: Early 1980s VFD multi-service departure board>>
# <<DESCRIPTION: A multi-service departure board styled like early 1980s vacuum fluorescent displays, with 18x19 character boxes per service and paging for >12 calling points>>
# <<SETTING DESCRIPTION NUMBER: Number of departures to show>>
# <<SETTING DESCRIPTION NUMBER: Page interval (seconds)>>
# <<SETTING DESCRIPTION BOOLEAN: Hide platform until allocated>>
#
# NOTE: Logic is derived from PIDLarge.py, but rendering/layout is changed to match the VFD board described.

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, RenderingHints
from java.awt import AlphaComposite
from javax.swing import Timer
import java.text.SimpleDateFormat as SimpleDateFormat
import jmri
from jmri import InstanceManager
import os, csv
import TASBeanLookup as TBL
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption

# -------------------- Theme and geometry (VFD) --------------------
# Match per-column size of PIDLarge.py: 252px wide, ~466px tall content area.
GRID_COLS = 18
GRID_ROWS = 19

# Cell geometry
BOX_W = 13
BOX_H = int(round(float(BOX_W) * 1.5))  # 20
BORDER_THICK = 1

# Per-column margins (chosen so each column panel is exactly 252x466)
H_MARGIN = 9
V_MARGIN = 9

# Window outer margin and inter-column gap (aligned with PIDLarge feel)
OUTER_MARGIN = 8
COL_GAP = 18

# VFD colors: white has a very slight greenish tinge, and neutral grey similarly.
VFD_WHITE = Color(230, 255, 242)
VFD_AMBER = Color(255, 210, 90)

# Backgrounds (both dark grey; white background slightly greenish; amber background slightly amber-tinted).
BG_WHITE = Color(42, 52, 46)
BG_AMBER = Color(52, 48, 36)

SURROUND_BLACK = Color.BLACK

# Font: logical monospaced for portability.
FONT_MAIN = Font("Monospaced", Font.BOLD, 14)

# Glow tuning (subtle, slightly increased)
GLOW_ALPHA = 0.26
GLOW_OFFSETS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
GLOW_DIAGONALS = [(-1, -1), (1, -1), (-1, 1), (1, 1)]

# -------------------- Memories (prefix-agnostic via TASBeanLookup) --------------------
TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# TASSetup "Options" -> memory names
def _SettingMemoryName(label):
    try:
        s = str(label).strip()
    except:
        s = ""
    import re as _re
    key = _re.sub(r"[^A-Za-z0-9]+", "_", s).upper()
    return "TAS_USER_SETTING_" + key

MEM_Cols = _SettingMemoryName("Number of departures to show")
MEM_PageSecs = _SettingMemoryName("Page interval (seconds)")
MEM_HidePlat = _SettingMemoryName("Hide platform until allocated")

# -------------------- Fast clock --------------------
Timebase = InstanceManager.getDefault(jmri.Timebase)

# -------------------- Time parsing helpers --------------------
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

def MinutesToHHmmDigits(total):
    if total is None:
        return ""
    total %= (24 * 60)
    h = total // 60
    m = total % 60
    return ("%02d%02d" % (h, m))

# -------------------- CSV access --------------------
def TimetablePath():
    name = TBL.SafeGetOrCreateMemoryValue("CURRENTTIMETABLE", "").strip()
    if name == "":
        return None
    try:
        prof = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    except:
        return None
    return os.path.join(prof, "timetable", name + ".csv")

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

def CaseInsensitive(row, key):
    target = (key or "").strip().lower()
    for k in (row.keys() or []):
        if (k or "").strip().lower() == target:
            return (row.get(k, "") or "").strip()
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

# -------------------- Departure TP selection & CLEAR-ON-DEPARTURE --------------------
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
                rn = rec[0]; tstr = rec[2]; d = rec[3]
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

# -------------------- Disruption inheritance --------------------
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

# -------------------- Text helpers --------------------
def _ToAsciiUpper(s):
    try:
        return str(s or "").upper()
    except:
        return ""

def TruncateWithDot(s, width):
    try:
        t = str(s or "")
    except:
        t = ""
    if width <= 0:
        return ""
    if len(t) <= width:
        return t
    if width == 1:
        return "."
    return t[:width - 1] + "."

def TruncateSilent(s, width):
    try:
        t = str(s or "")
    except:
        t = ""
    if width <= 0:
        return ""
    return t[:width]

def WrapSpecialText(text, width):
    t = (text or "").strip()
    if t == "":
        return []
    words = [w for w in t.split() if w != ""]
    lines = []
    cur = ""
    for w in words:
        if cur == "":
            if len(w) <= width:
                cur = w
            else:
                lines.append(TruncateSilent(w, width))
                cur = ""
        else:
            test = cur + " " + w
            if len(test) <= width:
                cur = test
            else:
                lines.append(TruncateSilent(cur, width))
                if len(w) <= width:
                    cur = w
                else:
                    lines.append(TruncateSilent(w, width))
                    cur = ""
    if cur != "":
        lines.append(TruncateSilent(cur, width))
    return lines

# -------------------- Service model --------------------
class ServiceModel(object):
    def __init__(self, row, dayName, nowMinutes):
        self.RN = CaseInsensitive(row, "Reporting number")
        self.DepStr = CaseInsensitive(row, "Dep")
        self.Dest = CaseInsensitive(row, "Destination")
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

        self.Kind = "ontime"  # 'ontime' | 'delay' | 'cancel'
        self.DelayMin = 0
        self.ExpectedMin = None

        self.AdjMin = self.DepMin if self.DepMin is not None else 999999

# -------------------- VFD panel (one column / one service) --------------------
class VfdPanel(swing.JPanel):
    def __init__(self):
        swing.JPanel.__init__(self)
        self.setOpaque(True)
        self.setBackground(SURROUND_BLACK)

        self.BoxPresent = [[True for _ in range(GRID_COLS)] for __ in range(GRID_ROWS)]
        self.FgScheme = [["W" for _ in range(GRID_COLS)] for __ in range(GRID_ROWS)]
        self.BgScheme = [["W" for _ in range(GRID_COLS)] for __ in range(GRID_ROWS)]
        self.Chars = [[" " for _ in range(GRID_COLS)] for __ in range(GRID_ROWS)]

        self._InitMasksAndSchemes()

        w = H_MARGIN * 2 + GRID_COLS * BOX_W
        h = V_MARGIN * 2 + GRID_ROWS * BOX_H
        self.setPreferredSize(awt.Dimension(w, h))

    def _InitMasksAndSchemes(self):
        # Row 0: TIME row with gaps
        for c in range(GRID_COLS):
            self.BoxPresent[0][c] = True
            self.FgScheme[0][c] = "W"
            self.BgScheme[0][c] = "W"

        for c in range(0, 4):
            self.FgScheme[0][c] = "A"
            self.BgScheme[0][c] = "A"

        self.BoxPresent[0][4] = False

        for c in range(5, 9):
            self.FgScheme[0][c] = "W"
            self.BgScheme[0][c] = "W"

        self.BoxPresent[0][9] = False
        self.BoxPresent[0][10] = False

        for c in range(11, 15):
            self.FgScheme[0][c] = "A"
            self.BgScheme[0][c] = "A"

        for c in range(15, 18):
            self.FgScheme[0][c] = "W"
            self.BgScheme[0][c] = "W"

        # Row 1: Destination row: first two boxes missing, rest present.
        for c in range(GRID_COLS):
            self.BoxPresent[1][c] = True
            self.FgScheme[1][c] = "W"
            self.BgScheme[1][c] = "W"
        self.BoxPresent[1][0] = False
        self.BoxPresent[1][1] = False

        # Row 2: CALLING AT row: only boxes where letters are, amber.
        for c in range(GRID_COLS):
            self.BoxPresent[2][c] = False
            self.FgScheme[2][c] = "A"
            self.BgScheme[2][c] = "A"

        word = "CALLING AT"
        col = 0
        for ch in word:
            if ch == " ":
                col += 1
                continue
            if col >= GRID_COLS:
                break
            self.BoxPresent[2][col] = True
            self.FgScheme[2][col] = "A"
            self.BgScheme[2][col] = "A"
            col += 1

        # Rows 3-14: 12 calling pattern rows, full width, white.
        for r in range(3, 15):
            for c in range(GRID_COLS):
                self.BoxPresent[r][c] = True
                self.FgScheme[r][c] = "W"
                self.BgScheme[r][c] = "W"

        # Rows 15-18: specials, amber text and amber-tinted background.
        for r in range(15, 19):
            for c in range(GRID_COLS):
                self.BoxPresent[r][c] = True
                self.FgScheme[r][c] = "A"
                self.BgScheme[r][c] = "A"

    def ClearAll(self):
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                self.Chars[r][c] = " "

    def SetRowText(self, row, text, startCol=0):
        if row < 0 or row >= GRID_ROWS:
            return
        for c in range(GRID_COLS):
            if self.BoxPresent[row][c]:
                self.Chars[row][c] = " "
        try:
            t = str(text or "")
        except:
            t = ""
        col = int(startCol)
        for ch in t:
            if col >= GRID_COLS:
                break
            if self.BoxPresent[row][col]:
                self.Chars[row][col] = ch
            col += 1

    def SetCellChar(self, row, col, ch):
        if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
            return
        if not self.BoxPresent[row][col]:
            return
        try:
            s = str(ch or " ")
            if s == "":
                s = " "
            self.Chars[row][col] = s[0]
        except:
            self.Chars[row][col] = " "

    def _ColorFromScheme(self, scheme, isForeground):
        if isForeground:
            return VFD_WHITE if scheme == "W" else VFD_AMBER
        else:
            return BG_WHITE if scheme == "W" else BG_AMBER

    def _DrawGlowChar(self, g2, ch, x, y, fg):
        try:
            oldComp = g2.getComposite()
        except:
            oldComp = None

        try:
            g2.setColor(fg)
            g2.setComposite(AlphaComposite.getInstance(AlphaComposite.SRC_OVER, float(GLOW_ALPHA)))
            for dx, dy in GLOW_OFFSETS:
                g2.drawString(ch, int(x + dx), int(y + dy))

            g2.setComposite(AlphaComposite.getInstance(AlphaComposite.SRC_OVER, float(GLOW_ALPHA) * 0.65))
            for dx, dy in GLOW_DIAGONALS:
                g2.drawString(ch, int(x + dx), int(y + dy))

            g2.setComposite(AlphaComposite.getInstance(AlphaComposite.SRC_OVER, 1.0))
            g2.drawString(ch, int(x), int(y))
        except:
            try:
                g2.setColor(fg)
                g2.drawString(ch, int(x), int(y))
            except:
                pass

        try:
            if oldComp is not None:
                g2.setComposite(oldComp)
        except:
            pass

    def paintComponent(self, g):
        w = self.getWidth()
        h = self.getHeight()
        try:
            g.setColor(SURROUND_BLACK)
            g.fillRect(0, 0, int(w), int(h))
        except:
            pass

        try:
            g2 = g.create()
        except:
            g2 = g

        try:
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_FRACTIONALMETRICS, RenderingHints.VALUE_FRACTIONALMETRICS_ON)
        except:
            pass

        try:
            g2.setFont(FONT_MAIN)
        except:
            pass

        try:
            fm = g2.getFontMetrics(FONT_MAIN)
        except:
            fm = None

        for r in range(GRID_ROWS):
            y0 = V_MARGIN + r * BOX_H
            for c in range(GRID_COLS):
                x0 = H_MARGIN + c * BOX_W

                if not self.BoxPresent[r][c]:
                    try:
                        g2.setColor(SURROUND_BLACK)
                        g2.fillRect(int(x0), int(y0), int(BOX_W), int(BOX_H))
                    except:
                        pass
                    continue

                bg = self._ColorFromScheme(self.BgScheme[r][c], False)
                fg = self._ColorFromScheme(self.FgScheme[r][c], True)

                try:
                    g2.setColor(bg)
                    g2.fillRect(int(x0), int(y0), int(BOX_W), int(BOX_H))
                except:
                    pass

                try:
                    g2.setColor(SURROUND_BLACK)
                    for t in range(BORDER_THICK):
                        g2.drawRect(int(x0 + t), int(y0 + t), int(BOX_W - 1 - 2 * t), int(BOX_H - 1 - 2 * t))
                except:
                    pass

                ch = self.Chars[r][c]
                if ch is None or ch == " ":
                    continue

                try:
                    if fm is not None:
                        ascent = fm.getAscent()
                        descent = fm.getDescent()
                        cw = fm.charWidth(ch)
                        tx = int(x0 + (BOX_W - cw) // 2)
                        ty = int(y0 + (BOX_H + ascent - descent) // 2)
                        self._DrawGlowChar(g2, str(ch), tx, ty, fg)
                    else:
                        self._DrawGlowChar(g2, str(ch), int(x0 + 1), int(y0 + BOX_H - 2), fg)
                except:
                    pass

        try:
            g2.dispose()
        except:
            pass

# -------------------- Board window --------------------
class VfdBoardWindow(object):
    def __init__(self):
        self.numCols = self._readInt(MEM_Cols, 5, minVal=1, maxVal=16)
        self.pageSecs = self._readInt(MEM_PageSecs, 10, minVal=2, maxVal=120)
        self.hidePlat = self._readBool(MEM_HidePlat, False)

        self.pagesByColumn = [[] for _ in range(self.numCols)]
        self.pageIndex = [0 for _ in range(self.numCols)]

        self.frame = swing.JFrame("Departure board")
        self.frame.setResizable(False)
        self.frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)

        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setBackground(SURROUND_BLACK)

        self.columns = []
        colW = H_MARGIN * 2 + GRID_COLS * BOX_W
        colH = V_MARGIN * 2 + GRID_ROWS * BOX_H

        x = OUTER_MARGIN
        y = OUTER_MARGIN
        for i in range(self.numCols):
            p = VfdPanel()
            p.setBounds(x, y, colW, colH)
            cp.add(p)
            self.columns.append(p)
            x += colW + COL_GAP

        contentW = OUTER_MARGIN * 2 + self.numCols * colW + (self.numCols - 1) * COL_GAP
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

        self.pageTimer = Timer(self.pageSecs * 1000, self._onPageTick)
        self.pageTimer.setRepeats(True)

        import java.beans as beans
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb):
                innerSelf.cb = cb
            def propertyChange(innerSelf, e):
                try:
                    innerSelf.cb(e)
                except Exception as ex:
                    try:
                        print("[PIDVFD1980] listener error:", ex)
                    except:
                        pass

        self._pcl = PCL(self.refresh)
        TimeMem.addPropertyChangeListener(self._pcl)
        DayMem.addPropertyChangeListener(self._pcl)
        if TimetableMem is not None:
            TimetableMem.addPropertyChangeListener(self._pcl)
        if DepartTPMem is not None:
            DepartTPMem.addPropertyChangeListener(self._pcl)
        if OverridesMem is not None:
            OverridesMem.addPropertyChangeListener(self._pcl)
        try:
            PAR.addPlatformListener(self._pcl)
        except Exception as ex:
            try:
                print("[PIDVFD1980] PAR add listener failed:", ex)
            except:
                pass

        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(innerSelf, e):
                self.cleanup()
            def windowClosed(innerSelf, e):
                self.cleanup()

        self.frame.addWindowListener(CloseHandler())

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)
        except Exception as ex:
            try:
                print("[PIDVFD1980] Failed to set icon:", str(ex))
            except:
                pass

        self.refresh()
        self.pageTimer.start()
        self.frame.setVisible(True)

    def _readInt(self, memName, defaultVal, minVal=None, maxVal=None):
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

    def _readBool(self, memName, defaultVal=False):
        try:
            raw = TBL.SafeGetOrCreateMemoryValue(memName, "true" if defaultVal else "false")
            t = (str(raw).strip().lower())
            if t in ["1", "true", "yes", "y", "on", "enabled"]:
                return True
            if t in ["0", "false", "no", "n", "off", "disabled"]:
                return False
            return bool(defaultVal)
        except:
            return bool(defaultVal)

    def _currentMinutes(self):
        if Timebase is not None:
            ft = Timebase.getTime()
            return ft.getHours() * 60 + ft.getMinutes()
        curStr = TimeMem.getValue() or ""
        return ParseMinutes(curStr)

    def _rowsToday(self):
        rows = CsvRows()
        curDay = DayMem.getValue() or ""
        return [r for r in rows if ((r.get(curDay, "") or "").strip().lower() == "true")]

    def _nextDepartures(self, count):
        rowsToday = self._rowsToday()
        curMin = self._currentMinutes()
        if curMin is None:
            return []
        curDay = DayMem.getValue() or ""

        models = []
        for r in rowsToday:
            dep = CaseInsensitive(r, "Dep")
            if dep == "":
                continue
            m = ServiceModel(r, curDay, curMin)
            if m.DepMin is None:
                continue
            if m.DepMin < curMin:
                continue
            if m.Departed:
                continue

            kind, val = ResolveDelayWithInheritance(rowsToday, m.RN, m.DepMin, visited=set())
            if kind == "cancel":
                m.Kind = "cancel"
                m.AdjMin = 999999
            elif kind == "delay" and val and val > 0:
                m.Kind = "delay"
                m.DelayMin = int(val)
                m.ExpectedMin = m.DepMin + int(val)
                m.AdjMin = m.ExpectedMin
            else:
                m.Kind = "ontime"
                m.AdjMin = m.DepMin
            models.append(m)

        models.sort(key=lambda t: t.AdjMin)
        return models[:count]

    def _CallingStations(self, callText):
        s = (callText or "").strip()
        if s == "":
            return []
        parts = [p.strip() for p in s.split(",")]
        out = []
        for p in parts:
            if p == "":
                continue
            out.append(_ToAsciiUpper(p))
        return out

    def _PaginateStations(self, stations):
        pages = []
        i = 0
        total = len(stations)
        if total == 0:
            pages.append(["" for _ in range(12)])
            return pages
        while i < total:
            chunk = stations[i:i + 12]
            if len(chunk) < 12:
                chunk = chunk + ["" for _ in range(12 - len(chunk))]
            pages.append(chunk)
            i += 12
        return pages

    def _ApplyToPanel(self, panel, svc, pageIndex):
        p = panel
        p.ClearAll()

        for i, ch in enumerate("TIME"):
            p.SetCellChar(0, i, ch)
        for i, ch in enumerate("PLAT"):
            p.SetCellChar(0, 11 + i, ch)

        word = "CALLING AT"
        col = 0
        for ch in word:
            if ch == " ":
                col += 1
                continue
            if col >= GRID_COLS:
                break
            p.SetCellChar(2, col, ch)
            col += 1

        if svc is None:
            p.repaint()
            return

        depDigits = MinutesToHHmmDigits(svc.DepMin)
        depDigits = TruncateSilent(depDigits, 4)
        for i in range(4):
            ch = depDigits[i] if i < len(depDigits) else " "
            p.SetCellChar(0, 5 + i, ch)

        platDigits = ""
        if svc.Kind != "cancel":
            if (not self.hidePlat) or svc.HasAlloc:
                platDigits = (svc.Plat or "")
        platDigits = TruncateSilent(platDigits, 3)
        for i in range(3):
            ch = platDigits[i] if i < len(platDigits) else " "
            p.SetCellChar(0, 15 + i, ch)

        dest = _ToAsciiUpper(svc.Dest)
        dest = TruncateWithDot(dest, 16)
        p.SetRowText(1, dest, startCol=2)

        stations = self._CallingStations(svc.Call)
        pages = self._PaginateStations(stations)
        total = len(pages) if pages else 1
        if total < 1:
            total = 1
        if pageIndex < 0 or pageIndex >= total:
            pageIndex = 0

        pageStations = pages[pageIndex] if pages else ["" for _ in range(12)]
        for i in range(12):
            st = pageStations[i] if i < len(pageStations) else ""
            st = TruncateWithDot(st, GRID_COLS)
            p.SetRowText(3 + i, st, startCol=0)

        statusLine1 = ""
        statusLine2 = ""
        if svc.Kind == "cancel":
            statusLine1 = "**CANCELLED**"
        elif svc.Kind == "delay":
            statusLine1 = "Delayed."
            exp = MinutesToHHmmDigits(svc.ExpectedMin)
            statusLine2 = "Expected: " + exp

        if statusLine1 != "":
            p.SetRowText(15, TruncateSilent(statusLine1, GRID_COLS), startCol=0)
        else:
            if total > 1:
                pageTxt = "Page %d of %d" % (int(pageIndex) + 1, int(total))
                p.SetRowText(15, TruncateSilent(pageTxt, GRID_COLS), startCol=0)

        if statusLine2 != "":
            p.SetRowText(16, TruncateSilent(statusLine2, GRID_COLS), startCol=0)

        specialTxt = (svc.Special or "").strip()
        if specialTxt != "":
            lines = WrapSpecialText(specialTxt, GRID_COLS)
            if lines:
                if svc.Kind == "delay":
                    availRows = [17, 18]
                else:
                    availRows = [16, 17, 18]

                use = lines[:len(availRows)]
                startAt = len(availRows) - len(use)
                for i, line in enumerate(use):
                    rr = availRows[startAt + i]
                    if rr == 16 and statusLine2 != "":
                        continue
                    p.SetRowText(rr, TruncateSilent(line, GRID_COLS), startCol=0)

        p.repaint()

    def refresh(self, e=None):
        def _do():
            services = self._nextDepartures(self.numCols)
            for idx in range(self.numCols):
                panel = self.columns[idx]
                if idx >= len(services):
                    self.pagesByColumn[idx] = []
                    self.pageIndex[idx] = 0
                    self._ApplyToPanel(panel, None, 0)
                    continue

                svc = services[idx]
                stations = self._CallingStations(svc.Call)
                pages = self._PaginateStations(stations)
                self.pagesByColumn[idx] = pages
                total = len(pages) if pages else 1
                if total < 1:
                    total = 1
                if self.pageIndex[idx] >= total:
                    self.pageIndex[idx] = 0
                self._ApplyToPanel(panel, svc, self.pageIndex[idx])

        try:
            swing.SwingUtilities.invokeLater(_do)
        except:
            try:
                _do()
            except:
                pass

    def _onPageTick(self, e=None):
        def _do():
            services = self._nextDepartures(self.numCols)
            for idx in range(self.numCols):
                pages = self.pagesByColumn[idx] if idx < len(self.pagesByColumn) else []
                total = len(pages) if pages else 1
                if total <= 1:
                    self.pageIndex[idx] = 0
                    continue
                self.pageIndex[idx] = (self.pageIndex[idx] + 1) % total

            for idx in range(self.numCols):
                panel = self.columns[idx]
                if idx >= len(services):
                    self._ApplyToPanel(panel, None, 0)
                    continue
                svc = services[idx]
                stations = self._CallingStations(svc.Call)
                pages = self._PaginateStations(stations)
                self.pagesByColumn[idx] = pages
                total = len(pages) if pages else 1
                if total < 1:
                    total = 1
                cur = self.pageIndex[idx]
                if cur >= total:
                    cur = 0
                    self.pageIndex[idx] = 0
                self._ApplyToPanel(panel, svc, cur)

        try:
            _do()
        except:
            pass

    def cleanup(self):
        try:
            if self.pageTimer:
                self.pageTimer.stop()
        except:
            pass
        try:
            PAR.removePlatformListener(self._pcl)
        except:
            pass
        try:
            TimeMem.removePropertyChangeListener(self._pcl)
            DayMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if TimetableMem is not None:
                TimetableMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if DepartTPMem is not None:
                DepartTPMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if OverridesMem is not None:
                OverridesMem.removePropertyChangeListener(self._pcl)
        except:
            pass
        try:
            if self.frame:
                self.frame.dispose()
        except:
            pass
        try:
            self.pageTimer = None
            self._pcl = None
            self.columns = []
            self.pagesByColumn = []
            self.pageIndex = []
        except:
            pass

# -------------------- Manager / run --------------------
class VfdBoardManager(object):
    def __init__(self):
        self.window = VfdBoardWindow()

PIDVFD1980_Manager = VfdBoardManager()
