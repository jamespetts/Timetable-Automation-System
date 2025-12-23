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
# 1980s monochrome CRT PID (station‑wide summary of departures)
# Uniquified global/class names to avoid cross-script shadowing.
# CLEAR-ON-DEPARTURE: remove a working once a departure is logged at the configured timing point(s)
# ECS FILTER: hide ECS/empty-to-depot workings (class-5 or keyword-matched; keywords configurable).
#
# <<PID-DISP-NAME: Monochrome CRT summary of departures>>
# <<DESCRIPTION: British Rail 1980s monitor showing a summary of the next 8 departures>>

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, GradientPaint, RenderingHints, BasicStroke, Dimension
import jmri
from jmri import InstanceManager
import os, csv
import TASBeanLookup as TBL
import java.text.SimpleDateFormat as SimpleDateFormat
from java.beans import PropertyChangeListener
from java.awt.event import WindowAdapter
from DisruptionRegister import getDisruption
import TimingRegister as TR  # read-only timing tuples: (reportingNumber, direction, time, day)

# ====== Cabinet / CRT geometry (compact defaults; auto-tighten will refine) ======
CRTSUM_CrtGlassWidth = 640
CRTSUM_HeaderHeight = 108
CRTSUM_InnerPad = 16
CRTSUM_FramePad = 4
CRTSUM_BezelInset = 3
CRTSUM_SideMargin = 6
CRTSUM_TopMargin = 6
CRTSUM_BottomMargin = 6

# Colours
CRTSUM_CabinetOrange = Color(232, 110, 20)
CRTSUM_CabinetShade  = Color(160, 70, 10)
CRTSUM_CabinetEdge   = Color(60, 30, 0)
CRTSUM_InnerBlack    = Color(10, 10, 10)
CRTSUM_LegendText    = Color(230, 230, 230)
CRTSUM_CrtBorder     = Color(22,22,24)
CRTSUM_CrtBg         = Color(8,10,12)
CRTSUM_CrtGlow       = Color(18,26,32)
CRTSUM_CrtScan       = Color(205,215,235)
CRTSUM_CrtTextAmber  = Color(255,196,64)  # yellower amber (#FFC440)
CRTSUM_ScanlineAlpha = 14

# Fonts / families
CRTSUM_MonoCands = ["IBM Plex Mono","Consolas","Courier New","Nimbus Mono L","Lucida Console","Monospaced"]
CRTSUM_RailCands = ["BritishRailLightNormal","British Rail Light Normal","Rail Alphabet","RailAlphabet",
                    "Arial","Helvetica","SansSerif"]

def CRTSUM_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

CRTSUM_MonoFamily = CRTSUM_PickFamily(CRTSUM_MonoCands)
CRTSUM_RailAlpha  = CRTSUM_PickFamily(CRTSUM_RailCands)

# Size bounds
CRTSUM_HeadSzMax = 64
CRTSUM_HeadSzMin = 28
CRTSUM_RowSzMax  = 22
CRTSUM_RowSzMin  = 12

# Fixed minimum margins inside the CRT around the text (px)
CRTSUM_TablePadX = 8
CRTSUM_TablePadY = 8

# JMRI memories / timetable
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
CRTSUM_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
CRTSUM_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
CRTSUM_DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
CRTSUM_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")
CRTSUM_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
CRTSUM_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# Optional authoritative fast clock (used for 'now' minutes if available)
CRTSUM_Timebase = InstanceManager.getDefault(jmri.Timebase)

# Time parsing/formatting
CRTSUM_TimeParser = SimpleDateFormat("h:mm a")
CRTSUM_AltParser  = SimpleDateFormat("H:mm")
CRTSUM_FmtHHmm    = SimpleDateFormat("HHmm")

def CRTSUM_ParseMinutes(s):
    for p in [CRTSUM_TimeParser, CRTSUM_AltParser]:
        try:
            d = p.parse(s); return d.getHours()*60 + d.getMinutes()
        except:
            pass
    return None

def CRTSUM_FormatHHmm(s):
    for p in [CRTSUM_TimeParser, CRTSUM_AltParser]:
        try:
            d = p.parse(s); return CRTSUM_FmtHHmm.format(d)
        except:
            pass
    return s.replace(":", "")

def CRTSUM_MinutesToHHmm(total):
    total = total % (24*60)
    h = total // 60
    m = total % 60
    return ("%02d%02d" % (h, m))

# CSV access
def CRTSUM_TimetablePath():
    name = CRTSUM_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")

def CRTSUM_CsvRows():
    path = CRTSUM_TimetablePath()
    if not os.path.exists(path): return []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []

def CRTSUM_PlatformField(row):
    return (row.get("Plat","") or row.get("Platform","") or "").strip()

def CRTSUM_ParseOverrides(s):
    out = {}
    if not s: return out
    for part in s.replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part: continue
        k,v = part.split("=",1)
        out[k.strip()] = v.strip()
    return out

def CRTSUM_GetOverride(rn):
    try:
        return CRTSUM_ParseOverrides(CRTSUM_OverridesMem.getValue()).get(rn)
    except:
        return None

# ---- Departure TP selection + logged-departure check (as per PIDSmall) ----
def CRTSUM_ActiveProfileBaseTPName():
    # Default 'Dep' timing point = active profile name (base TP).
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""

def CRTSUM_DepartureTPList():
    """
    Read IMPID_DEPARTURE_TP (single or ';' / ',' separated list).
    If absent/blank, fall back to base timing point (active profile name).
    """
    names = []
    try:
        raw = CRTSUM_DepartTPMem.getValue() if CRTSUM_DepartTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        base = CRTSUM_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names

def CRTSUM_HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    """
    True iff any configured departure timing point contains a tuple for (reportingNumber, dayName)
    whose logged time <= nowMinutes. TimingRegister tuples are (reportingNumber, direction, time, day).
    Any tuple here is a departure record.
    """
    tps = CRTSUM_DepartureTPList()
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
            if str(rn) != str(reportingNumber): continue
            if str(d)  != str(dayName):        continue
            mm = CRTSUM_ParseMinutes(tstr)
            if mm is None: continue
            if mm <= int(nowMinutes):
                return True
    return False

# ---- NEW: ECS detector (class-5 or keyword heuristics) ----
CRTSUM_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]

def CRTSUM_ReadExtraEcsTerms():
    """Read extra ECS terms from IMPID_ECS_FILTER_TERMS (split on ';' or ',')."""
    try:
        raw = CRTSUM_EcsFilterMem.getValue() if CRTSUM_EcsFilterMem is not None else None
        if not raw:
            return []
        parts = str(raw).replace(",", ";").split(";")
        out = []
        for p in parts:
            t = p.strip()
            if t:
                out.append(t.upper())
        return out
    except:
        return []

def CRTSUM_IsEcsWorking(row):
    """
    Return True if the row is an ECS/empty-to-depot working.
    Rules:
      1) Reporting number starts with '5'
      2) Destination or Calling pattern contains an ECS keyword (default + configurable extras)
    """
    rn = ((row.get("Reporting number","") or "")).strip().upper()
    if rn.startswith("5"):
        return True
    dest = ((row.get("Destination","") or "")).strip().upper()
    call = ((row.get("Calling pattern","") or "")).strip().upper()
    terms = set([t.upper() for t in CRTSUM_DefaultEcsTerms])
    for extra in CRTSUM_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " | " + call
    for t in terms:
        if t and t in hay:
            return True
    return False
    
class CRTSUM_PropertyListener(PropertyChangeListener):
    def __init__(self, owner):
        self.owner = owner

    def propertyChange(self, e):
        # Forward the event to the window instance refresh method
        self.owner.refresh(e)


class CRTSUM_WindowCloseHandler(WindowAdapter):
    def __init__(self, owner):
        self.owner = owner

    def windowClosing(self, e):
        # Ensure listeners are removed before disposing the frame
        try:
            self.owner.cleanup()
        finally:
            try:
                self.owner.frame.dispose()
            except:
                pass

    def windowClosed(self, e):
        # Safety net: if dispose happens via other route
        try:
            self.owner.cleanup()
        except:
            pass

# ------------------------- PANELS -------------------------
class CRTSUM_CabinetPanel(swing.JPanel):
    def __init__(self):
        super(CRTSUM_CabinetPanel, self).__init__()
        self.setOpaque(False); self.setLayout(None)
    def paintComponent(self, g):
        super(CRTSUM_CabinetPanel, self).paintComponent(g)
        g2=g
        if isinstance(g, awt.Graphics2D):
            g2=g; g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        W=self.getWidth(); H=self.getHeight()
        g2.setColor(Color.BLACK); g2.fillRect(0,0,W,H)
        gp = GradientPaint(0,0,CRTSUM_CabinetOrange, 0,H,CRTSUM_CabinetShade)
        g2.setPaint(gp); g2.fillRoundRect(0,0,W,H,20,20)
        g2.setColor(CRTSUM_CabinetEdge); g2.setStroke(BasicStroke(5.5))
        g2.drawRoundRect(2,2,W-4,H-4,20,20)

class CRTSUM_InnerCasingSummaryPanel(swing.JPanel):
    """Header area with 'Summary of' and 'Departures'."""
    def __init__(self, headerH):
        super(CRTSUM_InnerCasingSummaryPanel, self).__init__()
        self.headerH = headerH
        self.setOpaque(False); self.setLayout(None)
    def paintComponent(self, g):
        super(CRTSUM_InnerCasingSummaryPanel, self).paintComponent(g)
        g2=g
        if isinstance(g, awt.Graphics2D):
            g2=g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W=self.getWidth(); H=self.getHeight()
        g2.setColor(CRTSUM_InnerBlack); g2.fillRoundRect(0,0,W,H,16,16)
        g2.fillRoundRect(8,8, W-16, self.headerH, 12,12)
        padX = 22
        g2.setColor(CRTSUM_LegendText)
        # "Summary of"
        for size in range(CRTSUM_HeadSzMax, CRTSUM_HeadSzMin-1, -1):
            f = Font(CRTSUM_RailAlpha, Font.PLAIN, size)
            fm = g2.getFontMetrics(f)
            if fm.getHeight() <= self.headerH*0.55 and fm.stringWidth(u"Summary of") <= (W-2*padX):
                g2.setFont(f); break
        fm1 = g2.getFontMetrics()
        y1 = 8 + int(self.headerH*0.45)
        g2.drawString(u"Summary of", padX, y1)
        # "Departures"
        for size in range(max(int(g2.getFont().getSize()*0.9), CRTSUM_HeadSzMin), CRTSUM_HeadSzMin-1, -1):
            f2 = Font(CRTSUM_RailAlpha, Font.PLAIN, size)
            fm2= g2.getFontMetrics(f2)
            if fm2.stringWidth(u"Departures") <= (W-2*padX):
                g2.setFont(f2); break
        fm2 = g2.getFontMetrics()
        y2 = min(8 + self.headerH - 18, y1 + fm2.getAscent() + 8)
        g2.drawString(u"Departures", padX, y2)

class CRTSUM_CRTPanel(swing.JPanel):
    def __init__(self, inset):
        super(CRTSUM_CRTPanel, self).__init__()
        self.inset = inset
        self.setOpaque(False)
    def paintComponent(self, g):
        super(CRTSUM_CRTPanel, self).paintComponent(g)
        g2=g
        if isinstance(g, awt.Graphics2D):
            g2=g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W=self.getWidth(); H=self.getHeight()
        g2.setColor(CRTSUM_CrtBorder); g2.fillRoundRect(0,0,W,H,18,18)
        inset = self.inset
        x0=inset; y0=inset; innerW=W-2*inset; innerH=H-2*inset
        gp=GradientPaint(0,y0,CRTSUM_CrtBg, 0,y0+innerH, CRTSUM_CrtGlow)
        g2.setPaint(gp); g2.fillRoundRect(x0,y0,innerW,innerH,16,16)
        g2.setColor(Color(CRTSUM_CrtScan.getRed(), CRTSUM_CrtScan.getGreen(), CRTSUM_CrtScan.getBlue(), CRTSUM_ScanlineAlpha))
        for y in range(y0+1, y0+innerH-1, 2):
            g2.drawLine(x0+8,y, x0+innerW-8, y)

# -------- Summary table painter (stores metrics; centers within its bounds) --------
class CRTSUM_SummaryTablePanel(swing.JPanel):
    def __init__(self):
        super(CRTSUM_SummaryTablePanel, self).__init__()
        self.setOpaque(False)
        self.items = []
        self.W_TO = 22; self.W_PL = 4; self.W_TI = 4; self.W_EX = 9
        self.color = CRTSUM_CrtTextAmber
        self._last_meas = None  # (cw, lineH, rows, cols, fontSize)
        self._locked_size = None  # when set, freeze font size
    def lockFontSize(self, size):
        self._locked_size = size
        self.repaint()
    def unlockFont(self):
        self._locked_size = None
    def setItemsAndWidths(self, items, w_to, w_pl, w_ti, w_ex):
        self.items = items or []
        self.W_TO, self.W_PL, self.W_TI, self.W_EX = w_to, w_pl, w_ti, w_ex
        self._last_meas = None
        self.unlockFont()
        self.repaint()
    def _fit_font(self, g2, fam, minSz, maxSz, width, height, rows, total_chars):
        # If locked, use that size regardless of available space.
        if self._locked_size is not None:
            f = Font(fam, Font.BOLD, self._locked_size)
            fm = g2.getFontMetrics(f)
            cw = max(fm.charWidth('0'), fm.charWidth('M'))
            lineH = fm.getAscent() + fm.getDescent()
            return f, fm, cw, lineH
        for size in range(maxSz, minSz-1, -1):
            f = Font(fam, Font.BOLD, size)
            fm = g2.getFontMetrics(f)
            cw = max(fm.charWidth('0'), fm.charWidth('M'))
            lineH = fm.getAscent() + fm.getDescent()
            totW = cw * total_chars
            totH = lineH * rows
            if totW <= width and totH <= height:
                return f, fm, cw, lineH
        f = Font(fam, Font.BOLD, minSz)
        fm = g2.getFontMetrics(f)
        return f, fm, max(fm.charWidth('0'), fm.charWidth('M')), (fm.getAscent() + fm.getDescent())
    def paintComponent(self, g):
        super(CRTSUM_SummaryTablePanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2=g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth(); H = self.getHeight()
        if W <= 0 or H <= 0: return
        rows_to_draw = 1 + len(self.items)  # 1 heading + N rows
        total_cols = (self.W_TO + 2 + self.W_PL + 2 + self.W_TI + 2 + self.W_EX)
        # Available area for the grid after minimum margins
        availW = max(0, W - 2*CRTSUM_TablePadX)
        availH = max(0, H - 2*CRTSUM_TablePadY)
        f, fm, cw, lineH = self._fit_font(g2, CRTSUM_MonoFamily, CRTSUM_RowSzMin, CRTSUM_RowSzMax,
                                          availW, availH, rows_to_draw, total_cols)
        g2.setFont(f)
        g2.setColor(self.color)
        # ----- center: compute extra margins so L=R and T=B -----
        gridW = total_cols * cw
        gridH = rows_to_draw * lineH
        extraX = max(0, (availW - gridW) // 2)
        extraY = max(0, (availH - gridH) // 2)
        padL = CRTSUM_TablePadX + extraX
        padT = CRTSUM_TablePadY + extraY
        # Character grid → x positions
        x_to = padL
        x_pl = x_to + cw * (self.W_TO + 2)
        x_tm = x_pl + cw * (self.W_PL + 2)
        x_ex = x_tm + cw * (self.W_TI + 2)
        # Baseline for first line
        y = padT + fm.getAscent()
        # Headings
        head_to = "TO"; head_pl = "PLAT"; head_tm = "TIME"; head_ex = "EXPECTED"
        g2.drawString(head_to, x_to, y)
        g2.drawString(head_pl, x_pl, y)
        g2.drawString(head_tm, x_tm, y)
        g2.drawString(head_ex, x_ex, y)
        # 1px underline under each heading word
        g2.setStroke(BasicStroke(1.0))
        uy = y + 2
        g2.drawLine(x_to, uy, x_to + fm.stringWidth(head_to), uy)
        g2.drawLine(x_pl, uy, x_pl + fm.stringWidth(head_pl), uy)
        g2.drawLine(x_tm, uy, x_tm + fm.stringWidth(head_tm), uy)
        g2.drawLine(x_ex, uy, x_ex + fm.stringWidth(head_ex), uy)
        # Rows
        y += lineH
        for it in self.items:
            to  = (it.get("dest") or "").upper()
            pl  = (str(it.get("plat") or "")).upper()
            tim = CRTSUM_FormatHHmm(it.get("time") or "")
            exp = (it.get("_expected_text") or "")  # sentence-case
            def pad(s, w):
                s = (s or "")
                if len(s) > w: s = s[:w]
                return s + " " * max(0, w - len(s))
            to  = pad(to,  self.W_TO)
            pl  = pad(pl,  self.W_PL)
            tim = pad(tim, self.W_TI)
            exp = pad(exp, self.W_EX)
            g2.drawString(to,  x_to, y)
            g2.drawString(pl,  x_pl, y)
            g2.drawString(tim, x_tm, y)
            g2.drawString(exp, x_ex, y)
            y += lineH
        # Save metrics & chosen font size for the tightener and locking
        self._last_meas = (cw, lineH, rows_to_draw, total_cols, f.getSize())
    def lastMeasured(self):
        return self._last_meas

# ------------------------- MAIN WINDOW (Summary) -------------------------
class CRTSUM_CRTSummaryWindow(object):
    def __init__(self):
        # Initial sizes (approximate); will be 4:3-corrected & tightened post-paint
        glassW = CRTSUM_CrtGlassWidth
        glassH = int(round(glassW * 3.0/4.0))
        crtPanelW = glassW + 2*CRTSUM_BezelInset
        crtPanelH = glassH + 2*CRTSUM_BezelInset
        innerW = 2*CRTSUM_SideMargin + crtPanelW
        innerH = CRTSUM_HeaderHeight + CRTSUM_TopMargin + crtPanelH + CRTSUM_BottomMargin
        cabW = innerW + 2*CRTSUM_InnerPad
        cabH = innerH + 2*CRTSUM_InnerPad
        frameW = cabW + 2*CRTSUM_FramePad
        frameH = cabH + 2*CRTSUM_FramePad

        self.frame = swing.JFrame("Passenger information display: summary of departures")
        cp = self.frame.getContentPane(); cp.setLayout(None)
        cp.setPreferredSize(Dimension(frameW, frameH)); cp.setBackground(Color.BLACK)

        # Orange cabinet
        self.cab = CRTSUM_CabinetPanel()
        self.cab.setBounds(CRTSUM_FramePad, CRTSUM_FramePad, cabW, cabH)
        self.cab.setLayout(None); cp.add(self.cab)

        # Inner casing with summary header
        self.inner = CRTSUM_InnerCasingSummaryPanel(CRTSUM_HeaderHeight)
        self.inner.setBounds(CRTSUM_InnerPad, CRTSUM_InnerPad, innerW, innerH)
        self.inner.setLayout(None); self.cab.add(self.inner)

        # CRT panel (bezel+glass)
        self.crt = CRTSUM_CRTPanel(CRTSUM_BezelInset)
        self.crt.setBounds(CRTSUM_SideMargin, CRTSUM_HeaderHeight + CRTSUM_TopMargin, crtPanelW, crtPanelH)
        self.crt.setLayout(None); self.inner.add(self.crt)

        # Table area (bounds will be re-set after measurement)
        self.table = CRTSUM_SummaryTablePanel()
        self._tightened_once = False
        self._applyTableBounds(crtPanelW, crtPanelH)
        self.crt.add(self.table)

        # Listeners
        self._pcl = CRTSUM_PropertyListener(self)
        CRTSUM_TimeMem.addPropertyChangeListener(self._pcl)
        CRTSUM_DayMem.addPropertyChangeListener(self._pcl)
        if CRTSUM_TimetableMem is not None:
            CRTSUM_TimetableMem.addPropertyChangeListener(self._pcl)
        if CRTSUM_OverridesMem is not None:
            CRTSUM_OverridesMem.addPropertyChangeListener(self._pcl)
        if CRTSUM_DepartTPMem is not None:
            CRTSUM_DepartTPMem.addPropertyChangeListener(self._pcl)
        if CRTSUM_EcsFilterMem is not None:
            CRTSUM_EcsFilterMem.addPropertyChangeListener(self._pcl)

        self._windowCloser = CRTSUM_WindowCloseHandler(self)
        self.frame.setDefaultCloseOperation(swing.JFrame.DO_NOTHING_ON_CLOSE)
        self.frame.addWindowListener(self._windowCloser)

        self._rows_cache = None
        self.frame.pack(); self.frame.setResizable(False)
        self.refresh(); self.frame.setVisible(True)

    def _applyTableBounds(self, crtPanelW, crtPanelH):
        # Fill glass; the panel itself will center content inside using margins
        self.table.setBounds(CRTSUM_BezelInset, CRTSUM_BezelInset,
                             crtPanelW - 2*CRTSUM_BezelInset, crtPanelH - 2*CRTSUM_BezelInset)

    # -------- Data helpers --------
    def _rows_today(self):
        if self._rows_cache is None:
            self._rows_cache = CRTSUM_CsvRows()
        rows = self._rows_cache
        curDay = CRTSUM_DayMem.getValue() or ""
        return [r for r in rows if (r.get(curDay,"") or "").strip().lower() == "true"]

    def next_departures(self, N=8):
        rows = self._rows_today()

        # 'Now' in minutes: prefer fast clock, else memory string
        if CRTSUM_Timebase is not None:
            ft = CRTSUM_Timebase.getTime()  # java.util.Date
            curMin = ft.getHours()*60 + ft.getMinutes()
        else:
            curStr = CRTSUM_TimeMem.getValue() or ""
            curMin = CRTSUM_ParseMinutes(curStr)
        if curMin is None: return []

        curDay = CRTSUM_DayMem.getValue() or ""

        cands = []
        for row in rows:
            dep = (row.get("Dep","") or "").strip()
            if not dep: continue
            rn = (row.get("Reporting number","") or "").strip()
            # ---- NEW: skip ECS/empty-to-depot workings
            if CRTSUM_IsEcsWorking(row):
                continue
            plat = CRTSUM_GetOverride(rn) or CRTSUM_PlatformField(row)
            depMin = CRTSUM_ParseMinutes(dep)
            if depMin is None or depMin < curMin:
                continue

            # ---- existing: drop if this RN is logged as departed at configured TP(s)
            if CRTSUM_HasDepartedAtConfiguredTP(rn, curDay, curMin):
                continue

            dest = (row.get("Destination","") or "").strip()
            cands.append({"rn": rn, "plat": str(plat or ""), "time": dep, "tmin": depMin, "dest": dest})

        cands.sort(key=lambda t: t["tmin"])
        return cands[:N]

    # Formation-aware delay lookup (recursive)
    def delay_with_inheritance(self, rn, sched_dep_min, visited=None):
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
        rows = self._rows_today()
        formers = []
        for r in rows:
            if (r.get("Forms","") or "").strip() == rn:
                arr = (r.get("Arr","") or "").strip()
                arrMin = CRTSUM_ParseMinutes(arr) if arr else None
                formers.append((r, arrMin))
        if not formers:
            return ("ontime", 0)
        chosen = None
        if sched_dep_min is not None:
            before = [t for t in formers if t[1] is not None and t[1] <= sched_dep_min]
            if before:
                chosen = max(before, key=lambda t: t[1])
        if chosen is None:
            chosen = formers[0]
        former_rn = (chosen[0].get("Reporting number","") or "").strip()
        return self.delay_with_inheritance(former_rn, sched_dep_min, visited)

    def expected_text(self, rn, sched_time):
        smin = CRTSUM_ParseMinutes(sched_time)
        try:
            d = getDisruption(rn)
        except:
            d = None
        if d is not None:
            try: delay = int(d)
            except: delay = 0
            if delay >= 1440: return "CANCELLED"
            if delay > 0 and smin is not None:
                return CRTSUM_MinutesToHHmm(smin + delay)
        kind, val = self.delay_with_inheritance(rn, smin, visited=set())
        if kind == "cancel": return "CANCELLED"
        if kind == "delay" and val and smin is not None:
            return CRTSUM_MinutesToHHmm(smin + val)
        return "On time"

    def refresh(self, e=None):
        items = self.next_departures(8)
        w_to = max(2, len("TO"))
        w_pl = max(4, len("PLAT"))
        w_ti = max(4, len("TIME"))
        w_ex = max(8, len("EXPECTED"))
        for it in items:
            it["_expected_text"] = self.expected_text(it["rn"], it["time"])
            w_to = max(w_to, len((it["dest"] or "").upper()))
            w_pl = max(w_pl, len((str(it["plat"] or "")).upper()))
            w_ex = max(w_ex, len(it["_expected_text"] or ""))
        w_to = min(w_to + 1, 26)
        w_ex = min(w_ex + 1, 12)
        # Any data change → unlock font and allow a new tighten
        self._tightened_once = False
        self.table.setItemsAndWidths(items, w_to, w_pl, w_ti, w_ex)
        swing.SwingUtilities.invokeLater(self._tighten_if_possible)

    # ---- Auto-tighten + enforce 4:3 glass (expand height only if needed) ----
    def _tighten_if_possible(self):
        if self._tightened_once:
            return
        meas = self.table.lastMeasured()
        if not meas:
            return
        cw, lineH, rows, cols, fsize = meas
        # Desired inner glass size from measured grid and minimum margins
        innerW = cols * cw + 2*CRTSUM_TablePadX
        innerH = rows * lineH + 2*CRTSUM_TablePadY
        # 4:3: expand height minimally so inner glass becomes 4:3 (W : H = 4 : 3)
        targetH = int(round((innerW * 3.0) / 4.0))  # 4:3 → H = W * 3/4
        if targetH > innerH:
            innerH = targetH  # increase vertical space only (more pad top/bottom)
        # Convert to CRT panel (add bezel)
        crtPanelW = innerW + 2*CRTSUM_BezelInset
        crtPanelH = innerH + 2*CRTSUM_BezelInset
        # Convert to inner casing, cabinet, frame
        innerW_total = 2*CRTSUM_SideMargin + crtPanelW
        innerH_total = CRTSUM_HeaderHeight + CRTSUM_TopMargin + crtPanelH + CRTSUM_BottomMargin
        cabW = innerW_total + 2*CRTSUM_InnerPad
        cabH = innerH_total + 2*CRTSUM_InnerPad
        frameW = cabW + 2*CRTSUM_FramePad
        frameH = cabH + 2*CRTSUM_FramePad
        # Apply new bounds
        self.cab.setBounds(CRTSUM_FramePad, CRTSUM_FramePad, cabW, cabH)
        self.inner.setBounds(CRTSUM_InnerPad, CRTSUM_InnerPad, innerW_total, innerH_total)
        self.crt.setBounds(CRTSUM_SideMargin, CRTSUM_HeaderHeight + CRTSUM_TopMargin, crtPanelW, crtPanelH)
        self._applyTableBounds(crtPanelW, crtPanelH)
        # Lock the font so subsequent paints don't grow it again and disturb 4:3
        self.table.lockFontSize(fsize)
        # Update preferred size and pack
        cp = self.frame.getContentPane()
        cp.setPreferredSize(Dimension(frameW, frameH))  # keep external frame consistent with earlier calc
        self.frame.pack()
            
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[PIDCRTSummary] Failed to set PID window icon: " + str(ex))
        
        self._tightened_once = True

    
    def cleanup(self):
        # Remove property listeners using the same listener object that was added
        try:
            pcl = getattr(self, "_pcl", None)
        except:
            pcl = None

        if pcl is not None:
            try:
                CRTSUM_TimeMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                CRTSUM_DayMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSUM_TimetableMem is not None:
                    CRTSUM_TimetableMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSUM_OverridesMem is not None:
                    CRTSUM_OverridesMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSUM_DepartTPMem is not None:
                    CRTSUM_DepartTPMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSUM_EcsFilterMem is not None:
                    CRTSUM_EcsFilterMem.removePropertyChangeListener(pcl)
            except:
                pass

        # Remove window listener (not strictly required after dispose, but safe)
        try:
            wc = getattr(self, "_windowCloser", None)
        except:
            wc = None

        if wc is not None:
            try:
                self.frame.removeWindowListener(wc)
            except:
                pass

        # Drop references to help GC
        try:
            self._pcl = None
        except:
            pass
        try:
            self._windowCloser = None
        except:
            pass

# ------------------------- Manager -------------------------
class CRTSUM_CRTSummaryManager(object):
    def __init__(self):
        self.window = CRTSUM_CRTSummaryWindow()

# ------------------------- Run -------------------------
CRTSUM_Manager = CRTSUM_CRTSummaryManager()