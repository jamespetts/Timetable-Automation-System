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
# <<PID-DISP-NAME: Orange LED multi-platform display>>
# <<DESCRIPTION: A board showing the next departure and calling pattern on multiple platforms using an orange LED matrix as commonly installed by Network Rail in the 2000s at larger stations>>
# <<SETTING DESCRIPTION NUMBER: Number of departures to show>>
# <<SETTING DESCRIPTION NUMBER: Page interval (seconds)>>
# <<SETTING DESCRIPTION NUMBER: Platform/status flip interval (seconds)>>
# <<SETTING DESCRIPTION BOOLEAN: Hide platform until allocated>>

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, BasicStroke
from javax.swing import Timer, BorderFactory
import jmri
from jmri import InstanceManager
import os, csv
import java.text.SimpleDateFormat as SimpleDateFormat
import TASBeanLookup as TBL
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption


# ---------------- Theme and geometry ----------------
FRAME_COLOR = Color.BLACK
PANEL_COLOR = Color(30, 20, 0)
TEXT_COLOR  = Color(255, 200, 50)

# Slightly smaller across the board to avoid clipping
TOP_FONT_SIZE = 22
MID_FONT_SIZE = 14
DEFAULT_TOP_FONT = Font("SansSerif", Font.BOLD, TOP_FONT_SIZE)
DEFAULT_MID_FONT = Font("SansSerif", Font.BOLD, MID_FONT_SIZE)

# Column geometry: sized to the content so there's no big blank tail
COL_WIDTH    = 252     # per column
OUTER_MARGIN = 8
INNER_PAD    = 8
ROW_GAP      = 2

# Row heights (match font sizes closely)
TIME_H     = 28
DEST_H     = 26
VIA_H      = 20
HEADER_H   = 18
CALLING_LINES = 16
CALL_LINE_H   = 18
COMPANY_H  = 20

# Borders (as before)
CALL_BORDER_T = 1
CALL_BORDER_B = 1
LINE_BORDER   = BorderFactory.createMatteBorder(CALL_BORDER_T, 0, CALL_BORDER_B, 0, Color.BLACK)
BOX_BORDER    = BorderFactory.createLineBorder(Color.BLACK, 1)
COL_BORDER    = BorderFactory.createMatteBorder(0, 2, 0, 2, Color.BLACK)  # left/right rules

# ---------------- Memories (prefix-agnostic via TASBeanLookup) ----------------
TimeMem      = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
DayMem       = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
DepartTPMem  = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
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

MEM_Cols = _SettingMemoryName("Number of departures to show")
MEM_PageSecs = _SettingMemoryName("Page interval (seconds)")
MEM_FlipSecs = _SettingMemoryName("Platform/status flip interval (seconds)")
MEM_HidePlat = _SettingMemoryName("Hide platform until allocated")

# ---------------- Fast clock ----------------
Timebase = InstanceManager.getDefault(jmri.Timebase)

# ---------------- Time parsing helpers ----------------
Fmt24     = SimpleDateFormat("HH:mm")
Parser12  = SimpleDateFormat("h:mm a")
Parser24  = SimpleDateFormat("H:mm")

def ParseMinutes(s):
    s = (s or "").strip()
    if s == "": return None
    for p in [Parser12, Parser24]:
        try:
            d = p.parse(s)
            return d.getHours()*60 + d.getMinutes()
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
    if ":" in s and len(s) <= 5: return s
    return s

def MinutesToHHmm(total):
    if total is None: return ""
    total %= (24*60)
    h = total // 60
    m = total % 60
    return ("%02d:%02d" % (h,m))

# ---------------- CSV access ----------------
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
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            for r in rdr: out.append(r)
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
    val = (row.get("Plat","") or "").strip()
    if val == "": val = (row.get("Platform","") or "").strip()
    return val

def ParseOverrides(s):
    out = {}
    s = (s or "")
    for part in s.replace(",", ";").split(";"):
        p = part.strip()
        if p == "" or "=" not in p: continue
        k,v = p.split("=",1)
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
                if t != "": names.append(t)
    except:
        names = []
    if not names:
        base = ActiveProfileBaseTPName()
        if base: names = [base]
    return names

def HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    tps = DepartureTPList()
    if not tps: return False
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
            if str(rn) != str(reportingNumber): continue
            if str(d)  != str(dayName):         continue
            mm = ParseMinutes(tstr)
            if mm is None: continue
            if mm <= int(nowMinutes): return True
    return False

# ---------------- Disruption inheritance ----------------
def ResolveDelayWithInheritance(rowsToday, rn, schedDepMin, visited=None):
    if visited is None: visited = set()
    if rn in visited: return ("ontime", 0)
    visited.add(rn)
    try:
        d = getDisruption(rn)
    except:
        d = None
    if d is not None:
        try: delay = int(d)
        except: delay = 0
        if delay >= 1440: return ("cancel", None)
        if delay > 0:     return ("delay", delay)
    # Else inherit from 'Forms'
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

# ---------------- Fit helper (clone of PIDSmall approach) ----------------
def scaleTextToFit(label, text, maxSize, minSize, widthPx):
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
        self.RN     = CaseInsensitive(row, "Reporting number")
        self.DepStr = CaseInsensitive(row, "Dep")
        self.Dest   = CaseInsensitive(row, "Destination")
        self.Via    = CaseInsensitive(row, "Via")
        self.CoName = CaseInsensitive(row, "Company")
        self.Call   = CaseInsensitive(row, "Calling pattern")
        self.DepMin = ParseMinutes(self.DepStr)
        alloc = PAR.getPlatform(self.RN)
        if alloc is not None and str(alloc).strip() != "":
            self.Plat = str(alloc).strip()
        else:
            self.Plat = (GetOverride(self.RN) or PlatformField(row) or "").strip()
        self.Departed = HasDepartedAtConfiguredTP(self.RN, dayName, nowMinutes)
        self.Status   = ""
        self.ShowTime = FormatHHmm(self.DepStr)
        self.AdjMin   = self.DepMin if self.DepMin is not None else 9999

# ---------------- Column panel ----------------
class ColumnPanel(swing.JPanel):
    def __init__(self):
        super(ColumnPanel, self).__init__()
        self.setBackground(PANEL_COLOR)
        self.setLayout(None)
        self.setBorder(COL_BORDER)  # column edge rules

        y = INNER_PAD

        # Top row: time (left) and platform/status (right), boxed
        self.lblTime = swing.JLabel("")
        self.lblTime.setForeground(TEXT_COLOR)
        self.lblTime.setFont(DEFAULT_TOP_FONT)
        self.lblTime.setBounds(INNER_PAD, y, int(COL_WIDTH*0.46), TIME_H)
        self.lblTime.setBorder(BOX_BORDER)
        self.add(self.lblTime)

        self.lblPlatOrStatus = swing.JLabel("")
        self.lblPlatOrStatus.setForeground(TEXT_COLOR)
        self.lblPlatOrStatus.setFont(DEFAULT_TOP_FONT)
        self.lblPlatOrStatus.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.lblPlatOrStatus.setBounds(COL_WIDTH - INNER_PAD - int(COL_WIDTH*0.46), y, int(COL_WIDTH*0.46), TIME_H)
        self.lblPlatOrStatus.setBorder(BOX_BORDER)
        self.add(self.lblPlatOrStatus)

        y += TIME_H + ROW_GAP

        # Destination (boxed)
        self.lblDest = swing.JLabel("")
        self.lblDest.setForeground(TEXT_COLOR)
        self.lblDest.setFont(DEFAULT_TOP_FONT)
        self.lblDest.setBounds(INNER_PAD, y, COL_WIDTH - 2*INNER_PAD, DEST_H)
        self.lblDest.setBorder(BOX_BORDER)
        self.add(self.lblDest)

        y += DEST_H + ROW_GAP

        # Via (boxed)
        self.lblVia = swing.JLabel("")
        self.lblVia.setForeground(TEXT_COLOR)
        self.lblVia.setFont(DEFAULT_MID_FONT)
        self.lblVia.setBounds(INNER_PAD, y, COL_WIDTH - 2*INNER_PAD, VIA_H)
        self.lblVia.setBorder(BOX_BORDER)
        self.add(self.lblVia)

        y += VIA_H + ROW_GAP

        # "Calling at:" + page indicator (boxed)
        halfW = int((COL_WIDTH - 2*INNER_PAD) * 0.50)
        self.lblCallingTitle = swing.JLabel("Calling at:")
        self.lblCallingTitle.setForeground(TEXT_COLOR)
        self.lblCallingTitle.setFont(DEFAULT_MID_FONT)
        self.lblCallingTitle.setBounds(INNER_PAD, y, halfW, HEADER_H)
        self.lblCallingTitle.setBorder(BOX_BORDER)
        self.add(self.lblCallingTitle)

        self.lblPage = swing.JLabel("")
        self.lblPage.setForeground(TEXT_COLOR)
        self.lblPage.setFont(DEFAULT_MID_FONT)
        self.lblPage.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.lblPage.setBounds(INNER_PAD + halfW, y, (COL_WIDTH - 2*INNER_PAD) - halfW, HEADER_H)
        self.lblPage.setBorder(BOX_BORDER)
        self.add(self.lblPage)

        y += HEADER_H + ROW_GAP

        # 16 fixed calling lines; each has top/bottom black rules
        self.callLabels = []
        for i in range(CALLING_LINES):
            lbl = swing.JLabel("")
            lbl.setForeground(TEXT_COLOR)
            lbl.setFont(DEFAULT_MID_FONT)
            lbl.setBounds(INNER_PAD, y + i*CALL_LINE_H, COL_WIDTH - 2*INNER_PAD, CALL_LINE_H)
            lbl.setBorder(LINE_BORDER)
            self.callLabels.append(lbl)
            self.add(lbl)

        y += CALL_LINE_H * CALLING_LINES + ROW_GAP

        # Company (boxed) just below the grid
        self.lblCompany = swing.JLabel("")
        self.lblCompany.setForeground(TEXT_COLOR)
        self.lblCompany.setFont(DEFAULT_TOP_FONT)
        self.lblCompany.setBounds(INNER_PAD, y, COL_WIDTH - 2*INNER_PAD, COMPANY_H)
        self.lblCompany.setBorder(BOX_BORDER)
        self.add(self.lblCompany)

        # Advance y to the true bottom of the company box, then add a small bottom pad
        y += COMPANY_H
        bottomPad = INNER_PAD  # keep a thin margin under the last box

        # Save computed height (exact content height including company and pad)
        self.computedHeight = y + bottomPad

        # Flip timer state
        self.flipShowPlatform = True

    # Render helpers (scaled to fit width to avoid clipping)
    def setTimeText(self, text):
        scaleTextToFit(self.lblTime, (text or ""), TOP_FONT_SIZE, 16, self.lblTime.getWidth())

    def setPlatOrStatus(self, platText, statusText, hidePlatformUntilAlloc=False, hasAlloc=False):
        shown = platText if (self.flipShowPlatform and not (hidePlatformUntilAlloc and (not hasAlloc))) else statusText
        scaleTextToFit(self.lblPlatOrStatus, (shown or ""), TOP_FONT_SIZE, 14, self.lblPlatOrStatus.getWidth())

    def setDestination(self, dest):
        scaleTextToFit(self.lblDest, (dest or ""), TOP_FONT_SIZE, 16, self.lblDest.getWidth())

    def setVia(self, via):
        txt = ("via " + via) if via else ""
        scaleTextToFit(self.lblVia, txt, MID_FONT_SIZE, 12, self.lblVia.getWidth())

    def setPageIndicator(self, cur, total):
        self.lblPage.setFont(DEFAULT_MID_FONT)
        self.lblPage.setText("Page %d of %d" % (int(cur), int(total)) if total > 1 else "Page 1 of 1")

    def setCallingPage(self, lines16):
        for i in range(CALLING_LINES):
            txt = lines16[i] if i < len(lines16) else ""
            self.callLabels[i].setFont(DEFAULT_MID_FONT)
            self.callLabels[i].setText(txt or "")

    def setCompany(self, co):
        scaleTextToFit(self.lblCompany, (co or ""), TOP_FONT_SIZE, 14, self.lblCompany.getWidth())

# ---------------- Board window ----------------
class StripBoardWindow(object):
    def __init__(self):
        # Settings from TAS
        self.numCols  = self._readInt(MEM_Cols, 5, minVal=1, maxVal=16)
        self.pageSecs = self._readInt(MEM_PageSecs, 10, minVal=2, maxVal=120)
        self.flipSecs = self._readInt(MEM_FlipSecs, 5,  minVal=2, maxVal=60)
        self.hidePlat = self._readBool(MEM_HidePlat, False)
           
        # Flip cache: per-column (platLabel, statusLabel, hasAlloc)
        self._flipCache = [ ( "", "", False ) for _ in range(self.numCols) ]

        # Window: create now; size later once we know exact content height
        self.frame = swing.JFrame("Departure board")
        self.frame.setResizable(False)
        self.frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setBackground(FRAME_COLOR)

        # Build columns (measure and apply exact heights)
        self.columns = []
        x = OUTER_MARGIN
        y = OUTER_MARGIN
        maxH = 0
        for i in range(self.numCols):
            p = ColumnPanel()
            colH = int(p.computedHeight)  # true content height
            if colH > maxH: maxH = colH
            p.setBounds(x, y, COL_WIDTH, colH)
            cp.add(p)
            self.columns.append(p)
            x += COL_WIDTH + OUTER_MARGIN

        # Trim window to the tallest column, accounting for title-bar/border insets
        contentW = OUTER_MARGIN*2 + self.numCols*COL_WIDTH + (self.numCols-1)*OUTER_MARGIN
        contentH = OUTER_MARGIN*2 + int(maxH)

        # Ensure peer exists so insets are valid
        try:
            self.frame.addNotify()  # creates native peer without showing the frame
        except:
            pass

        ins = self.frame.getInsets()
        if ins is None:
            # Fallback: if insets are not yet known, assume zero (rare LAF cases)
            insLeft = insRight = insTop = insBottom = 0
        else:
            insLeft, insRight = ins.left, ins.right
            insTop,  insBottom = ins.top,  ins.bottom

        outerW = int(contentW + insLeft + insRight)
        outerH = int(contentH + insTop  + insBottom)
        self.frame.setSize(outerW, outerH)

        # Timers
        self.pageTimer = Timer(self.pageSecs*1000, self._onPageTick)
        self.flipTimer = Timer(self.flipSecs*1000, self._onFlipTick)
        self.pageTimer.setRepeats(True); self.flipTimer.setRepeats(True)

        # Listeners
        import java.beans as beans
        class PCL(beans.PropertyChangeListener):
            def __init__(innerSelf, cb): innerSelf.cb = cb
            def propertyChange(innerSelf, e):
                try: innerSelf.cb(e)
                except Exception as ex: print("[PIDLarge] listener error:", ex)
        self._pcl = PCL(self.refresh)
        TimeMem.addPropertyChangeListener(self._pcl)
        DayMem.addPropertyChangeListener(self._pcl)
        if TimetableMem is not None: TimetableMem.addPropertyChangeListener(self._pcl)
        if DepartTPMem is not None:  DepartTPMem.addPropertyChangeListener(self._pcl)
        if OverridesMem is not None: OverridesMem.addPropertyChangeListener(self._pcl)
        try: PAR.addPlatformListener(self._pcl)
        except Exception as ex:
            try: print("[PIDLarge] PAR add listener failed:", ex)
            except: pass

        # DO NOT wipe out indices unconditionally: preserve if page count is unchanged
        oldPages   = getattr(self, "pagesByColumn", [ [] for _ in range(self.numCols) ])
        oldIndices = getattr(self, "pageIndex",     [ 0  for _ in range(self.numCols) ])
        self.pagesByColumn = [ [] for _ in range(self.numCols) ]
        self.pageIndex     = [ 0  for _ in range(self.numCols) ]

        # Start
        self.refresh()
        self.pageTimer.start()
        self.flipTimer.start()

        # Close handler
        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(innerSelf, e): self.cleanup()
            def windowClosed(innerSelf, e):  self.cleanup()
        self.frame.addWindowListener(CloseHandler())

        # Icon
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)
        except Exception as ex:
            print("[PIDLarge] Failed to set icon:", str(ex))
        self.frame.setVisible(True)

    def _readInt(self, memName, defaultVal, minVal=None, maxVal=None):
        try:
            raw = TBL.SafeGetOrCreateMemoryValue(memName, str(int(defaultVal)))
            n = int(float(str(raw).strip()))
            if minVal is not None: n = max(minVal, n)
            if maxVal is not None: n = min(maxVal, n)
            return int(n)
        except:
            return int(defaultVal)

    def _readBool(self, memName, defaultVal=False):
        try:
            raw = TBL.SafeGetOrCreateMemoryValue(memName, "true" if defaultVal else "false")
            t = (str(raw).strip().lower())
            if t in ["1","true","yes","y","on","enabled"]: return True
            if t in ["0","false","no","n","off","disabled"]: return False
            return bool(defaultVal)
        except:
            return bool(defaultVal)

    def _currentMinutes(self):
        if Timebase is not None:
            ft = Timebase.getTime()
            return ft.getHours()*60 + ft.getMinutes()
        curStr = TimeMem.getValue() or ""
        return ParseMinutes(curStr)

    def _rowsToday(self):
        rows = CsvRows()
        curDay = DayMem.getValue() or ""
        return [r for r in rows if ((r.get(curDay,"") or "").strip().lower() == "true")]

    def _nextDepartures(self, count):
        rowsToday = self._rowsToday()
        curMin = self._currentMinutes()
        if curMin is None: return []
        curDay = DayMem.getValue() or ""
        models = []
        for r in rowsToday:
            dep = CaseInsensitive(r, "Dep")
            if dep == "": continue
            m = ServiceModel(r, curDay, curMin)
            if m.DepMin is None: continue
            if m.DepMin < curMin: continue
            if m.Departed: continue
            kind, val = ResolveDelayWithInheritance(rowsToday, m.RN, m.DepMin, visited=set())
            if kind == "cancel":
                m.Status   = "Cancelled"
                m.ShowTime = "CANCELLED"
                m.AdjMin   = 9999
            elif kind == "delay" and val and val > 0:
                m.Status   = "Exp " + MinutesToHHmm(m.DepMin + val)
                m.ShowTime = MinutesToHHmm(m.DepMin + val)
                m.AdjMin   = m.DepMin + val
            else:
                m.Status   = "On time"
                m.ShowTime = FormatHHmm(m.DepStr)
                m.AdjMin   = m.DepMin
            models.append(m)
        models.sort(key=lambda t: t.AdjMin)
        return models[:count]

    def _wrapStationsIntoLines(self, text, maxWidthPx, font):
        s = (text or "").strip()
        if s == "": return []
        stations = [t.strip() for t in s.split(",")]
        if len(stations) > 0: stations[-1] = "& " + stations[-1]
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
                                lines.append(chunk); chunk = ch
                        cur = chunk
            if cur != "": lines.append(cur)
        if len(lines) > 0: lines[-1] = (lines[-1].rstrip(".") + ".")
        return lines

    def _paginate16(self, physicalLines):
        pages = []
        if not physicalLines:
            pages.append([""]*CALLING_LINES)
            return pages
        i = 0
        total = len(physicalLines)
        while i < total:
            chunk = physicalLines[i:i+CALLING_LINES]
            if len(chunk) < CALLING_LINES:
                chunk = chunk + [""]*(CALLING_LINES - len(chunk))
            pages.append(chunk)
            i += CALLING_LINES
        return pages

    def refresh(self, e=None):
        services = self._nextDepartures(self.numCols)
        # reset paging state for each refresh
        self.pagesByColumn = [ [] for _ in range(self.numCols) ]
        self.pageIndex     = [ 0 for _ in range(self.numCols) ]

        for idx in range(self.numCols):
            col = self.columns[idx]
            if idx >= len(services):
                col.setTimeText("")
                col.setPlatOrStatus("", "", self.hidePlat, False)
                col.setDestination("")
                col.setVia("")
                col.setPageIndicator(1,1)
                col.setCallingPage([""]*CALLING_LINES)
                col.setCompany("")
                continue
            s = services[idx]
            # Top-left time
            col.setTimeText(FormatHHmm(s.ShowTime))
            # Top-right flip
            platLabel = ("Platform " + s.Plat) if (s.Plat or "") != "" else ""
            statusLabel = s.Status or ""
            hasAlloc = (PAR.getPlatform(s.RN) is not None and str(PAR.getPlatform(s.RN)).strip() != "")
            col.setPlatOrStatus(platLabel, statusLabel, self.hidePlat, hasAlloc)       
            # Cache flip data so flip timer doesn't need a full refresh
            try:
                self._flipCache[idx] = (platLabel, statusLabel, hasAlloc)
            except:
                pass
            # Destination
            col.setDestination(s.Dest)
            # Via
            col.setVia(s.Via)
            # Calling pages
            physical = self._wrapStationsIntoLines(s.Call, COL_WIDTH - 2*INNER_PAD, DEFAULT_MID_FONT)
            pages = self._paginate16(physical)
            self.pagesByColumn[idx] = pages     
            # If page count did not change, keep the current index (modulo new length)
            try:
                oldLen = len(oldPages[idx]) if idx < len(oldPages) and oldPages[idx] else 0
                newLen = len(pages)
                if oldLen > 0 and newLen == oldLen:
                    # preserve current index within bounds
                    keep = oldIndices[idx] if idx < len(oldIndices) else 0
                    self.pageIndex[idx] = max(0, min(newLen - 1, keep))
                else:
                    self.pageIndex[idx] = 0
            except:
                self.pageIndex[idx] = 0

            # Apply whichever page we're on now
            cur = self.pageIndex[idx]
            col.setPageIndicator(cur + 1, len(pages))
            col.setCallingPage(pages[cur])
            col.setPageIndicator(1, len(pages))
            col.setCallingPage(pages[0])
            # Company
            col.setCompany(s.CoName)

    def _onPageTick(self, e=None):
        for i, col in enumerate(self.columns):
            pages = self.pagesByColumn[i] if i < len(self.pagesByColumn) else []
            if not pages: continue
            total = len(pages)
            if total <= 1:
                col.setPageIndicator(1,1)
                continue
            cur = (self.pageIndex[i] + 1) % total
            self.pageIndex[i] = cur
            col.setPageIndicator(cur+1, total)
            col.setCallingPage(pages[cur])

    def _onFlipTick(self, e=None):
        # Toggle the flip flag and re-apply plat/status without touching pages
        for i, col in enumerate(self.columns):
            try:
                col.flipShowPlatform = not bool(col.flipShowPlatform)
                platLabel, statusLabel, hasAlloc = self._flipCache[i] if i < len(self._flipCache) else ("", "", False)
                col.setPlatOrStatus(platLabel, statusLabel, self.hidePlat, hasAlloc)
            except:
                pass

    def cleanup(self):
        try:
            if self.pageTimer: self.pageTimer.stop()
        except: pass
        try:
            if self.flipTimer: self.flipTimer.stop()
        except: pass
        try: PAR.removePlatformListener(self._pcl)
        except: pass
        try:
            TimeMem.removePropertyChangeListener(self._pcl)
            DayMem.removePropertyChangeListener(self._pcl)
        except: pass
        try:
            if TimetableMem is not None: TimetableMem.removePropertyChangeListener(self._pcl)
        except: pass
        try:
            if DepartTPMem is not None: DepartTPMem.removePropertyChangeListener(self._pcl)
        except: pass
        try:
            if OverridesMem is not None: OverridesMem.removePropertyChangeListener(self._pcl)
        except: pass
        # ADD THESE LINES:
        try:
            if self.frame: self.frame.dispose()
        except: pass
        try:
            self.pageTimer = None
            self.flipTimer = None
            self._pcl = None
            self.columns = []
            self.pagesByColumn = []
            self.pageIndex = []
        except: pass

# ---------------- Manager / run ----------------
class StripBoardManager(object):
    def __init__(self):
        self.window = StripBoardWindow()

PIDStrip_Manager = StripBoardManager()
