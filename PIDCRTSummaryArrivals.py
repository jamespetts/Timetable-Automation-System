
# This file is part of the Timetable Automation System by James E. Petts
#
# GNU GPLv3 or later. See <https://www.gnu.org/licenses/>.
#
# 1980s monochrome CRT PID (station‑wide summary of arrivals)
# Uniquified global/class names to avoid cross‑script shadowing.
# CLEAR-ON-ARRIVAL: remove a working once an arrival is logged at the configured timing point(s)
# ECS FILTER: hide ECS/empty‑to‑depot workings (class‑5 or keyword‑matched; keywords configurable).
#
# <<PID-DISP-NAME: Monochrome CRT summary of arrivals>>
# <<DESCRIPTION: British Rail 1980s monitor showing a summary of the next 8 arrivals>>

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
from java.awt.event import ActionListener  # for Timer tick
from javax.swing import Timer  # 500ms flash timer
from java.lang import System  # currentTimeMillis for 1-minute flash window
import PlatformAllocationRegister as PAR  # precedence + event listener
from DisruptionRegister import getDisruption
import TimingRegister as TR  # read-only timing tuples: (reportingNumber, direction, time, day)

# ====== Cabinet / CRT geometry (compact defaults; auto-tighten will refine) ======
CRTARR_CrtGlassWidth = 640
CRTARR_HeaderHeight = 108
CRTARR_InnerPad = 16
CRTARR_FramePad = 4
CRTARR_BezelInset = 3
CRTARR_SideMargin = 6
CRTARR_TopMargin = 6
CRTARR_BottomMargin = 6

# Colours
CRTARR_CabinetOrange = Color(232, 110, 20)
CRTARR_CabinetShade = Color(160, 70, 10)
CRTARR_CabinetEdge = Color(60, 30, 0)
CRTARR_InnerBlack = Color(10, 10, 10)
CRTARR_LegendText = Color(230, 230, 230)

CRTARR_CrtBorder = Color(22,22,24)
CRTARR_CrtBg = Color(8,10,12)
CRTARR_CrtGlow = Color(18,26,32)
CRTARR_CrtScan = Color(205,215,235)
CRTARR_CrtTextAmber = Color(255,196,64)  # yellower amber (#FFC440)
CRTARR_ScanlineAlpha = 14

# Fonts / families
CRTARR_MonoCands = ["IBM Plex Mono","Consolas","Courier New","Nimbus Mono L","Lucida Console","Monospaced"]
CRTARR_RailCands = ["BritishRailLightNormal","British Rail Light Normal","Rail Alphabet","RailAlphabet",
                    "Arial","Helvetica","SansSerif"]
def CRTARR_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"
CRTARR_MonoFamily = CRTARR_PickFamily(CRTARR_MonoCands)
CRTARR_RailAlpha = CRTARR_PickFamily(CRTARR_RailCands)

# Size bounds
CRTARR_HeadSzMax = 64
CRTARR_HeadSzMin = 28
CRTARR_RowSzMax = 22
CRTARR_RowSzMin = 12

# Fixed minimum margins inside the CRT around the text (px)
CRTARR_TablePadX = 8
CRTARR_TablePadY = 8

# JMRI memories / timetable
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
CRTARR_TimeMem      = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
CRTARR_DayMem       = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
CRTARR_ArrivalTPMem = TBL.ProvideMemoryBySuffix("PID_ARRIVAL_TP", "")     # NEW: arrivals timing point(s)
CRTARR_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")
CRTARR_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
CRTARR_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# Optional authoritative fast clock (used for 'now' minutes if available)
CRTARR_Timebase = InstanceManager.getDefault(jmri.Timebase)

# Time parsing/formatting
CRTARR_TimeParser = SimpleDateFormat("h:mm a")
CRTARR_AltParser  = SimpleDateFormat("H:mm")
CRTARR_FmtHHmm    = SimpleDateFormat("HHmm")
def CRTARR_ParseMinutes(s):
    for p in [CRTARR_TimeParser, CRTARR_AltParser]:
        try:
            d = p.parse(s); return d.getHours()*60 + d.getMinutes()
        except:
            pass
    return None
def CRTARR_FormatHHmm(s):
    for p in [CRTARR_TimeParser, CRTARR_AltParser]:
        try:
            d = p.parse(s); return CRTARR_FmtHHmm.format(d)
        except:
            pass
    return s.replace(":", "")
def CRTARR_MinutesToHHmm(total):
    total = total % (24*60)
    h = total // 60
    m = total % 60
    return ("%02d%02d" % (h, m))

# CSV access
def CRTARR_TimetablePath():
    name = CRTARR_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")
def CRTARR_CsvRows():
    path = CRTARR_TimetablePath()
    if not os.path.exists(path): return []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []

def CRTARR_PlatformField(row):
    return (row.get("Plat","") or row.get("Platform","") or "").strip()

def CRTARR_ParseOverrides(s):
    out = {}
    if not s: return out
    for part in s.replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part: continue
        k,v = part.split("=",1)
        out[k.strip()] = v.strip()
    return out
def CRTARR_GetOverride(rn):
    try:
        return CRTARR_ParseOverrides(CRTARR_OverridesMem.getValue()).get(rn)
    except:
        return None

# ---- Arrival TP selection + logged-arrival check (mirrors departures) ----
def CRTARR_ActiveProfileBaseTPName():
    # Default 'Arr' timing point = active profile name (base TP).
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""
def CRTARR_ArrivalTPList():
    """
    Read IMPID_ARRIVAL_TP (single or ';' / ',' separated list).
    If absent/blank, fall back to base timing point (active profile name).
    """
    names = []
    try:
        raw = CRTARR_ArrivalTPMem.getValue() if CRTARR_ArrivalTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        base = CRTARR_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names

def CRTARR_HasArrivedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    """
    True iff any configured arrival timing point contains a tuple for (reportingNumber, dayName)
    whose logged time <= nowMinutes. TimingRegister tuples are (reportingNumber, direction, time, day).
    Any tuple here is an arrival record.
    """
    tps = CRTARR_ArrivalTPList()
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
            if str(d)  != str(dayName):         continue
            mm = CRTARR_ParseMinutes(tstr)
            if mm is None: continue
            if mm <= int(nowMinutes):
                return True
    return False

# ---- ECS detector (class-5 or keyword heuristics) ----
CRTARR_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]
def CRTARR_ReadExtraEcsTerms():
    """Read extra ECS terms from IMPID_ECS_FILTER_TERMS (split on ';' or ',')."""
    try:
        raw = CRTARR_EcsFilterMem.getValue() if CRTARR_EcsFilterMem is not None else None
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
def CRTARR_IsEcsWorking(row):
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
    terms = set([t.upper() for t in CRTARR_DefaultEcsTerms])
    for extra in CRTARR_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " \n " + call
    for t in terms:
        if t and t in hay:
            return True
    return False

class CRTARR_PropertyListener(PropertyChangeListener):
    def __init__(self, owner):
        self.owner = owner
    def propertyChange(self, e):
        # Forward the event to the window instance refresh method
        self.owner.refresh(e)

class CRTARR_WindowCloseHandler(WindowAdapter):
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

class CRTARR_PlatformChangeListener(PropertyChangeListener):
    """Listens to PlatformAllocationRegister events and triggers refresh + flashing."""
    def __init__(self, owner):
        self.owner = owner
    def propertyChange(self, e):
        try:
            if str(e.getPropertyName()) != "platformAllocationChanged":
                return
            payload = e.getNewValue()
            if not isinstance(payload, dict):
                return
            rn = str(payload.get("rn") or "")
            # Start a 1-minute visual flash on PLAT for this RN, then refresh
            self.owner._startPlatformFlash(rn)
            self.owner.refresh()
        except Exception as ex:
            print("[PIDCRTSummaryArrivals] Platform listener error:", str(ex))

class CRTARR_FlashTick(ActionListener):
    """Toggles visibility of flashing platforms every 500ms and stops at 1 minute."""
    def __init__(self, owner):
        self.owner = owner
    def actionPerformed(self, e):
        try:
            self.owner._onFlashTick()
        except Exception as ex:
            print("[PIDCRTSummaryArrivals] FlashTick error:", str(ex))

# --------------------- PANELS ---------------------
class CRTARR_CabinetPanel(swing.JPanel):
    def __init__(self):
        super(CRTARR_CabinetPanel, self).__init__()
        self.setOpaque(False); self.setLayout(None)
    def paintComponent(self, g):
        super(CRTARR_CabinetPanel, self).paintComponent(g)
        g2=g
        if isinstance(g, awt.Graphics2D):
            g2=g; g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        W=self.getWidth(); H=self.getHeight()
        g2.setColor(Color.BLACK); g2.fillRect(0,0,W,H)
        gp = GradientPaint(0,0,CRTARR_CabinetOrange, 0,H,CRTARR_CabinetShade)
        g2.setPaint(gp); g2.fillRoundRect(0,0,W,H,20,20)
        g2.setColor(CRTARR_CabinetEdge); g2.setStroke(BasicStroke(5.5))
        g2.drawRoundRect(2,2,W-4,H-4,20,20)

class CRTARR_InnerCasingSummaryPanel(swing.JPanel):
    """Header area with 'Summary of' and 'Arrivals'."""
    def __init__(self, headerH):
        super(CRTARR_InnerCasingSummaryPanel, self).__init__()
        self.headerH = headerH
        self.setOpaque(False); self.setLayout(None)
    def paintComponent(self, g):
        super(CRTARR_InnerCasingSummaryPanel, self).paintComponent(g)
        g2=g
        if isinstance(g, awt.Graphics2D):
            g2=g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W=self.getWidth(); H=self.getHeight()
        g2.setColor(CRTARR_InnerBlack); g2.fillRoundRect(0,0,W,H,16,16)
        g2.fillRoundRect(8,8, W-16, self.headerH, 12,12)
        padX = 22
        g2.setColor(CRTARR_LegendText)
        # "Summary of"
        for size in range(CRTARR_HeadSzMax, CRTARR_HeadSzMin-1, -1):
            f = Font(CRTARR_RailAlpha, Font.PLAIN, size)
            fm = g2.getFontMetrics(f)
            if fm.getHeight() <= self.headerH*0.55 and fm.stringWidth(u"Summary of") <= (W-2*padX):
                g2.setFont(f); break
        fm1 = g2.getFontMetrics()
        y1 = 8 + int(self.headerH*0.45)
        g2.drawString(u"Summary of", padX, y1)
        # "Arrivals"
        for size in range(max(int(g2.getFont().getSize()*0.9), CRTARR_HeadSzMin), CRTARR_HeadSzMin-1, -1):
            f2 = Font(CRTARR_RailAlpha, Font.PLAIN, size)
            fm2= g2.getFontMetrics(f2)
            if fm2.stringWidth(u"Arrivals") <= (W-2*padX):
                g2.setFont(f2); break
        fm2 = g2.getFontMetrics()
        y2 = min(8 + self.headerH - 18, y1 + fm2.getAscent() + 8)
        g2.drawString(u"Arrivals", padX, y2)

class CRTARR_CRTPanel(swing.JPanel):
    def __init__(self, inset):
        super(CRTARR_CRTPanel, self).__init__()
        self.inset = inset
        self.setOpaque(False)
    def paintComponent(self, g):
        super(CRTARR_CRTPanel, self).paintComponent(g)
        g2=g
        if isinstance(g, awt.Graphics2D):
            g2=g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W=self.getWidth(); H=self.getHeight()
        g2.setColor(CRTARR_CrtBorder); g2.fillRoundRect(0,0,W,H,18,18)
        inset = self.inset
        x0=inset; y0=inset; innerW=W-2*inset; innerH=H-2*inset
        gp=GradientPaint(0,y0,CRTARR_CrtBg, 0,y0+innerH, CRTARR_CrtGlow)
        g2.setPaint(gp); g2.fillRoundRect(x0,y0,innerW,innerH,16,16)
        g2.setColor(Color(CRTARR_CrtScan.getRed(), CRTARR_CrtScan.getGreen(), CRTARR_CrtScan.getBlue(), CRTARR_ScanlineAlpha))
        for y in range(y0+1, y0+innerH-1, 2):
            g2.drawLine(x0+8,y, x0+innerW-8, y)

# -------- Summary table painter (stores metrics; centers within its bounds) --------
class CRTARR_SummaryTablePanel(swing.JPanel):
    def __init__(self):
        super(CRTARR_SummaryTablePanel, self).__init__()
        self.setOpaque(False)
        self.items = []
        self.W_FR = 22; self.W_PL = 4; self.W_TI = 4; self.W_EX = 9
        self.color = CRTARR_CrtTextAmber
        self._last_meas = None  # (cw, lineH, rows, cols, fontSize)
        self._locked_size = None  # when set, freeze font size
        self.flashMap = {}  # rn -> {"show": bool, "until": millisDeadline}
    def setFlashMap(self, flashMap):
        # Called by window to update current flash states per RN
        self.flashMap = flashMap or {}
    def lockFontSize(self, size):
        self._locked_size = size
        self.repaint()
    def unlockFont(self):
        self._locked_size = None
    def setItemsAndWidths(self, items, w_fr, w_pl, w_ti, w_ex):
        self.items = items or []
        self.W_FR, self.W_PL, self.W_TI, self.W_EX = w_fr, w_pl, w_ti, w_ex
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
        super(CRTARR_SummaryTablePanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2=g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth(); H = self.getHeight()
        if W <= 0 or H <= 0: return
        rows_to_draw = 1 + len(self.items)  # 1 heading + N rows
        total_cols = (self.W_FR + 2 + self.W_PL + 2 + self.W_TI + 2 + self.W_EX)
        # Available area for the grid after minimum margins
        availW = max(0, W - 2*CRTARR_TablePadX)
        availH = max(0, H - 2*CRTARR_TablePadY)
        f, fm, cw, lineH = self._fit_font(g2, CRTARR_MonoFamily, CRTARR_RowSzMin, CRTARR_RowSzMax,
                                          availW, availH, rows_to_draw, total_cols)
        g2.setFont(f)
        g2.setColor(self.color)
        # --- center: compute extra margins so L=R and T=B ---
        gridW = total_cols * cw
        gridH = rows_to_draw * lineH
        extraX = max(0, (availW - gridW) // 2)
        extraY = max(0, (availH - gridH) // 2)
        padL = CRTARR_TablePadX + extraX
        padT = CRTARR_TablePadY + extraY
        # Character grid → x positions
        x_fr = padL
        x_pl = x_fr + cw * (self.W_FR + 2)
        x_tm = x_pl + cw * (self.W_PL + 2)
        x_ex = x_tm + cw * (self.W_TI + 2)
        # Baseline for first line
        y = padT + fm.getAscent()
        # Headings
        head_fr = "FROM"; head_pl = "PLAT"; head_tm = "TIME"; head_ex = "EXPECTED"
        g2.drawString(head_fr, x_fr, y)
        g2.drawString(head_pl, x_pl, y)
        g2.drawString(head_tm, x_tm, y)
        g2.drawString(head_ex, x_ex, y)
        # 1px underline under each heading word
        g2.setStroke(BasicStroke(1.0))
        uy = y + 2
        g2.drawLine(x_fr, uy, x_fr + fm.stringWidth(head_fr), uy)
        g2.drawLine(x_pl, uy, x_pl + fm.stringWidth(head_pl), uy)
        g2.drawLine(x_tm, uy, x_tm + fm.stringWidth(head_tm), uy)
        g2.drawLine(x_ex, uy, x_ex + fm.stringWidth(head_ex), uy)
        # Rows
        y += lineH
        for it in self.items:
            rn = (it.get("rn") or "").strip()
            fr = (it.get("origin") or "").upper()
            pl_val = (str(it.get("plat") or "")).upper()
            tim = CRTARR_FormatHHmm(it.get("time") or "")
            exp = (it.get("_expected_text") or "")
            def pad(s, w):
                s = (s or "")
                if len(s) > w: s = s[:w]
                return s + " " * max(0, w - len(s))
            # Flash logic: if rn has a flash entry and 'show' is False, draw blanks in PLAT
            flashEntry = self.flashMap.get(rn) if self.flashMap else None
            platShown = (flashEntry is None) or bool(flashEntry.get("show", True))
            pl = pad(pl_val if platShown else "", self.W_PL)
            fr = pad(fr, self.W_FR)
            tim = pad(tim, self.W_TI)
            exp = pad(exp, self.W_EX)
            g2.drawString(fr, x_fr, y)
            g2.drawString(pl, x_pl, y)
            g2.drawString(tim, x_tm, y)
            g2.drawString(exp, x_ex, y)
            y += lineH
        # Save metrics & chosen font size for the tightener and locking
        self._last_meas = (cw, lineH, rows_to_draw, total_cols, f.getSize())
    def lastMeasured(self):
        return self._last_meas

# --------------------- MAIN WINDOW (Summary) ---------------------
class CRTARR_CRTSummaryArrivalsWindow(object):
    def __init__(self):
        # Initial sizes (approximate); will be 4:3-corrected & tightened post-paint
        glassW = CRTARR_CrtGlassWidth
        glassH = int(round(glassW * 3.0/4.0))
        crtPanelW = glassW + 2*CRTARR_BezelInset
        crtPanelH = glassH + 2*CRTARR_BezelInset
        innerW = 2*CRTARR_SideMargin + crtPanelW
        innerH = CRTARR_HeaderHeight + CRTARR_TopMargin + crtPanelH + CRTARR_BottomMargin
        cabW = innerW + 2*CRTARR_InnerPad
        cabH = innerH + 2*CRTARR_InnerPad
        frameW = cabW + 2*CRTARR_FramePad
        frameH = cabH + 2*CRTARR_FramePad

        self.frame = swing.JFrame("Passenger information display: summary of arrivals")
        cp = self.frame.getContentPane(); cp.setLayout(None)
        cp.setPreferredSize(Dimension(frameW, frameH)); cp.setBackground(Color.BLACK)

        # Orange cabinet
        self.cab = CRTARR_CabinetPanel()
        self.cab.setBounds(CRTARR_FramePad, CRTARR_FramePad, cabW, cabH)
        self.cab.setLayout(None); cp.add(self.cab)

        # Inner casing with summary header
        self.inner = CRTARR_InnerCasingSummaryPanel(CRTARR_HeaderHeight)
        self.inner.setBounds(CRTARR_InnerPad, CRTARR_InnerPad, innerW, innerH)
        self.inner.setLayout(None); self.cab.add(self.inner)

        # CRT panel (bezel+glass)
        self.crt = CRTARR_CRTPanel(CRTARR_BezelInset)
        self.crt.setBounds(CRTARR_SideMargin, CRTARR_HeaderHeight + CRTARR_TopMargin, crtPanelW, crtPanelH)
        self.crt.setLayout(None); self.inner.add(self.crt)

        # Table area (bounds will be re-set after measurement)
        self.table = CRTARR_SummaryTablePanel()
        self._tightened_once = False
        self._applyTableBounds(crtPanelW, crtPanelH)
        self.crt.add(self.table)

        # Listeners
        self._pcl = CRTARR_PropertyListener(self)
        CRTARR_TimeMem.addPropertyChangeListener(self._pcl)
        CRTARR_DayMem.addPropertyChangeListener(self._pcl)
        if CRTARR_TimetableMem is not None:
            CRTARR_TimetableMem.addPropertyChangeListener(self._pcl)
        if CRTARR_OverridesMem is not None:
            CRTARR_OverridesMem.addPropertyChangeListener(self._pcl)
        if CRTARR_ArrivalTPMem is not None:
            CRTARR_ArrivalTPMem.addPropertyChangeListener(self._pcl)
        if CRTARR_EcsFilterMem is not None:
            CRTARR_EcsFilterMem.addPropertyChangeListener(self._pcl)

        self._windowCloser = CRTARR_WindowCloseHandler(self)
        self.frame.setDefaultCloseOperation(swing.JFrame.DO_NOTHING_ON_CLOSE)
        self.frame.addWindowListener(self._windowCloser)

        self._rows_cache = None

        self.frame.pack(); self.frame.setResizable(False)
        self.refresh(); self.frame.setVisible(True)

        # --- Platform allocation listener + flash timer (500ms on/off for 1 minute) ---
        self._flashMap = {}  # rn -> {"show": True/False, "until": millisDeadline}
        self._flashTick = CRTARR_FlashTick(self)
        self._flashTimer = None  # javax.swing.Timer
        self.table.setFlashMap(self._flashMap)

        # Subscribe to PlatformAllocationRegister events
        self._parListener = CRTARR_PlatformChangeListener(self)
        try:
            PAR.addPlatformListener(self._parListener)
        except Exception as ex:
            print("[PIDCRTSummaryArrivals] Failed to add platform listener:", str(ex))

    def _applyTableBounds(self, crtPanelW, crtPanelH):
        # Fill glass; the panel itself will center content inside using margins
        self.table.setBounds(CRTARR_BezelInset, CRTARR_BezelInset,
                             crtPanelW - 2*CRTARR_BezelInset, crtPanelH - 2*CRTARR_BezelInset)

    def _startPlatformFlash(self, rn):
        """Begin a 1-minute flash for this RN; 500ms cadence."""
        if not rn:
            return
        # Set deadline and initial visible-state
        self._flashMap[rn] = {"show": True, "until": System.currentTimeMillis() + 60 * 1000}
        self.table.setFlashMap(self._flashMap)
        # Start timer if needed
        if self._flashTimer is None:
            try:
                self._flashTimer = Timer(500, self._flashTick)  # 500ms
                self._flashTimer.setRepeats(True)
                self._flashTimer.start()
            except Exception as ex:
                print("[PIDCRTSummaryArrivals] Failed to start flash timer:", str(ex))
        # Ensure a repaint now so first 'on' state is visible immediately
        try:
            self.table.repaint()
        except:
            pass

    def _onFlashTick(self):
        """Timer tick: flip visibility; end flash when deadline passes."""
        now = System.currentTimeMillis()
        stale = []
        for rn, st in self._flashMap.items():
            if st.get("until", now) <= now:
                stale.append(rn)
            else:
                st["show"] = not bool(st.get("show", True))
        # Drop expired RN entries
        for rn in stale:
            try:
                del self._flashMap[rn]
            except:
                pass
        # Stop timer if no active flashes
        if not self._flashMap and self._flashTimer is not None:
            try:
                self._flashTimer.stop()
            except:
                pass
            self._flashTimer = None
        # Repaint table to reflect new visibility state
        try:
            self.table.repaint()
        except:
            pass

    # -------- Data helpers --------
    def _rows_today(self):
        if self._rows_cache is None:
            self._rows_cache = CRTARR_CsvRows()
        rows = self._rows_cache
        curDay = CRTARR_DayMem.getValue() or ""
        return [r for r in rows if (r.get(curDay,"") or "").strip().lower() == "true"]

    def next_arrivals(self, N=8):
        rows = self._rows_today()
        # 'Now' in minutes: prefer fast clock, else memory string
        if CRTARR_Timebase is not None:
            ft = CRTARR_Timebase.getTime()  # java.util.Date
            curMin = ft.getHours()*60 + ft.getMinutes()
        else:
            curStr = CRTARR_TimeMem.getValue() or ""
            curMin = CRTARR_ParseMinutes(curStr)
        if curMin is None: return []
        curDay = CRTARR_DayMem.getValue() or ""
        cands = []
        for row in rows:
            arr = (row.get("Arr","") or "").strip()
            if not arr: continue
            rn = (row.get("Reporting number","") or "").strip()
            # --- skip ECS/empty-to-depot workings
            if CRTARR_IsEcsWorking(row):
                continue
            # Platform precedence: allocation register > timetable > override (same as departures)
            alloc = PAR.getPlatform(rn)
            if alloc is not None and str(alloc).strip():
                plat = str(alloc)
            else:
                plat = CRTARR_GetOverride(rn) or CRTARR_PlatformField(row)
            arrMin = CRTARR_ParseMinutes(arr)
            if arrMin is None or arrMin < curMin:
                continue
            # --- drop if this RN is logged as arrived at configured TP(s)
            if CRTARR_HasArrivedAtConfiguredTP(rn, curDay, curMin):
                continue
            origin = (row.get("Origin","") or "").strip()
            cands.append({"rn": rn, "plat": str(plat or ""), "time": arr, "tmin": arrMin, "origin": origin})
        cands.sort(key=lambda t: t["tmin"])
        return cands[:N]

    # Formation-aware delay lookup (recursive)
    def delay_with_inheritance(self, rn, sched_arr_min, visited=None):
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
            if delay > 0: return ("delay", delay)
        rows = self._rows_today()
        formers = []
        for r in rows:
            if (r.get("Forms","") or "").strip() == rn:
                arr = (r.get("Arr","") or "").strip()
                arrMin = CRTARR_ParseMinutes(arr) if arr else None
                formers.append((r, arrMin))
        if not formers:
            return ("ontime", 0)
        chosen = None
        if sched_arr_min is not None:
            before = [t for t in formers if t[1] is not None and t[1] <= sched_arr_min]
            if before:
                chosen = max(before, key=lambda t: t[1])
        if chosen is None:
            chosen = formers[0]
        former_rn = (chosen[0].get("Reporting number","") or "").strip()
        return self.delay_with_inheritance(former_rn, sched_arr_min, visited)

    def expected_text(self, rn, sched_time):
        smin = CRTARR_ParseMinutes(sched_time)
        try:
            d = getDisruption(rn)
        except:
            d = None
        if d is not None:
            try: delay = int(d)
            except: delay = 0
            if delay >= 1440: return "CANCELLED"
            if delay > 0 and smin is not None:
                return CRTARR_MinutesToHHmm(smin + delay)
        kind, val = self.delay_with_inheritance(rn, smin, visited=set())
        if kind == "cancel": return "CANCELLED"
        if kind == "delay" and val and smin is not None:
            return CRTARR_MinutesToHHmm(smin + val)
        return "On time"

    def refresh(self, e=None):
        items = self.next_arrivals(8)
        w_fr = max(4, len("FROM"))
        w_pl = max(4, len("PLAT"))
        w_ti = max(4, len("TIME"))
        w_ex = max(8, len("EXPECTED"))
        for it in items:
            it["_expected_text"] = self.expected_text(it["rn"], it["time"])
            w_fr = max(w_fr, len((it["origin"] or "").upper()))
            w_pl = max(w_pl, len((str(it["plat"] or "")).upper()))
            w_ex = max(w_ex, len(it["_expected_text"] or ""))
        w_fr = min(w_fr + 1, 26)
        w_ex = min(w_ex + 1, 12)
        # Any data change → unlock font and allow a new tighten
        self._tightened_once = False
        self.table.setItemsAndWidths(items, w_fr, w_pl, w_ti, w_ex)
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
        innerW = cols * cw + 2*CRTARR_TablePadX
        innerH = rows * lineH + 2*CRTARR_TablePadY
        # 4:3: expand height minimally so inner glass becomes 4:3 (W : H = 4 : 3)
        targetH = int(round((innerW * 3.0) / 4.0))  # 4:3 → H = W * 3/4
        if targetH > innerH:
            innerH = targetH  # increase vertical space only (more pad top/bottom)
        # Convert to CRT panel (add bezel)
        crtPanelW = innerW + 2*CRTARR_BezelInset
        crtPanelH = innerH + 2*CRTARR_BezelInset
        # Convert to inner casing, cabinet, frame
        innerW_total = 2*CRTARR_SideMargin + crtPanelW
        innerH_total = CRTARR_HeaderHeight + CRTARR_TopMargin + crtPanelH + CRTARR_BottomMargin
        cabW = innerW_total + 2*CRTARR_InnerPad
        cabH = innerH_total + 2*CRTARR_InnerPad
        frameW = cabW + 2*CRTARR_FramePad
        frameH = cabH + 2*CRTARR_FramePad
        # Apply new bounds
        self.cab.setBounds(CRTARR_FramePad, CRTARR_FramePad, cabW, cabH)
        self.inner.setBounds(CRTARR_InnerPad, CRTARR_InnerPad, innerW_total, innerH_total)
        self.crt.setBounds(CRTARR_SideMargin, CRTARR_HeaderHeight + CRTARR_TopMargin, crtPanelW, crtPanelH)
        self._applyTableBounds(crtPanelW, crtPanelH)
        # Lock the font so subsequent paints don't grow it again and disturb 4:3
        self.table.lockFontSize(fsize)
        # Update preferred size and pack
        cp = self.frame.getContentPane()
        cp.setPreferredSize(Dimension(frameW, frameH))
        self.frame.pack()
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[PIDCRTSummaryArrivals] Failed to set PID window icon: " + str(ex))
        self._tightened_once = True

    def cleanup(self):
        # Remove property listeners using the same listener object that was added
        try:
            pcl = getattr(self, "_pcl", None)
        except:
            pcl = None
        if pcl is not None:
            try:
                CRTARR_TimeMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                CRTARR_DayMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTARR_TimetableMem is not None:
                    CRTARR_TimetableMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTARR_OverridesMem is not None:
                    CRTARR_OverridesMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTARR_ArrivalTPMem is not None:
                    CRTARR_ArrivalTPMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTARR_EcsFilterMem is not None:
                    CRTARR_EcsFilterMem.removePropertyChangeListener(pcl)
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
        # Unsubscribe from PlatformAllocationRegister and stop flash timer
        try:
            parL = getattr(self, "_parListener", None)
        except:
            parL = None
        if parL is not None:
            try:
                PAR.removePlatformListener(parL)
            except:
                pass
        try:
            if self._flashTimer is not None:
                self._flashTimer.stop()
        except:
            pass
        try:
            self._flashTimer = None
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

# --------------------- Manager ---------------------
class CRTARR_CRTSummaryArrivalsManager(object):
    def __init__(self):
        self.window = CRTARR_CRTSummaryArrivalsWindow()

# --------------------- Run ---------------------
CRTARR_Manager = CRTARR_CRTSummaryArrivalsManager()
