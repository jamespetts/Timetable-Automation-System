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
# 1980s colour CRT PID (station-wide summary of arrivals)
# Uniquified global/class names to avoid cross-script shadowing.
# CLEAR-ON-ARRIVAL: remove a working once a departure is logged at the configured timing point(s)
# ECS FILTER: hide ECS/empty-to-depot workings (class-5 or keyword-matched; keywords configurable).
#
# <<PID-DISP-NAME: Colour CRT summary of arrivals>>
# <<DESCRIPTION: British Rail 1990s colour CRT monitor showing a summary of the next ~10 arrivals>>
# BUILD-ID: ArrivalsFix1 2025-12-29
# BUILD-ID: PitchNormalize 2025-12-29
# BUILD-ID: VertPadNoShrink 2025-12-29

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, GradientPaint, RenderingHints, BasicStroke, Dimension
import jmri
from jmri.util import FileUtil
from jmri import InstanceManager
import os, csv
import TASBeanLookup as TBL
import TASPathResolver
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
CRTCLA_CrtGlassWidth = 640
CRTCLA_HeaderHeight = 108
CRTCLA_InnerPad = 16
CRTCLA_FramePad = 4
CRTCLA_BezelInset = 3
CRTCLA_SideMargin = 6
CRTCLA_TopMargin = 6
CRTCLA_BottomMargin = 6
# Fixed cabinet size to match the original monochrome CRT summary window.
# These values are cabinet panel sizes (excluding the OS window decoration).
CRTCLA_FixedCabinetWidth = 530
CRTCLA_FixedCabinetHeight = 520

# Colours
# Cabinet: yellow
CRTCLA_CabinetYellow = Color(235, 200, 40)
CRTCLA_CabinetShade = Color(170, 140, 25)
CRTCLA_CabinetEdge = Color(60, 50, 0)

CRTCLA_InnerBlack = Color(10, 10, 10)
CRTCLA_LegendText = Color(230, 230, 230)
CRTCLA_CrtBorder = Color(22, 22, 24)

# CRT: deep blue background with subtle glow
CRTCLA_CrtBg = Color(0, 18, 110)       # deep blue
CRTCLA_CrtGlow = Color(0, 36, 160)    # slightly lighter blue

# Scanlines
CRTCLA_CrtScan = Color(210, 220, 235)
CRTCLA_ScanlineAlpha = 12

# Text colours
CRTCLA_TextWhite = Color(245, 245, 245)
CRTCLA_DestYellow = Color(255, 220, 0)
CRTCLA_CancelBg = Color(0, 255, 255)
CRTCLA_CancelText = Color(0, 0, 0)

# Fonts / families
CRTCLA_MonoCands = ["Liberation Sans Narrow", "Arial Narrow", "Bahnschrift Condensed", "SansSerif"]
CRTCLA_RailCands = ["BritishRailLightNormal", "British Rail Light Normal", "Rail Alphabet", "RailAlphabet",
                   "Arial", "Helvetica", "SansSerif"]

def CRTCLA_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

CRTCLA_MonoFamily = CRTCLA_PickFamily(CRTCLA_MonoCands)
CRTCLA_RailAlpha = CRTCLA_PickFamily(CRTCLA_RailCands)

# Size bounds
CRTCLA_HeadSzMax = 64
CRTCLA_HeadSzMin = 28
CRTCLA_RowSzMax = 24
CRTCLA_RowSzMin = 12

# Minimum additional vertical leading per font size (applied at paint time; does not affect font fitting).
CRTCLA_MinRowLeadingFactor = 0.24
# Extra fixed pixels between rows (applied at paint time).
CRTCLA_RowExtraPadPx = 0
# Normalize row pitch across fonts by referencing these families (if installed).
CRTCLA_RowPitchRefFamilies = ["Arial Narrow", "Liberation Sans Narrow"]
# Desired inter-row gap (pixels): max(MinRowGapPx, round(pointSize * RowGapFactor)).
CRTCLA_RowGapFactor = 0.10
CRTCLA_MinRowGapPx = 2
# Fixed minimum margins inside the CRT around the text (px)
CRTCLA_TablePadX = 8
CRTCLA_TablePadY = 8

# JMRI memories / timetable
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
CRTCLA_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
CRTCLA_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
CRTCLA_ArrivalTPMem = TBL.ProvideMemoryBySuffix("PID_ARRIVAL_TP", "")
CRTCLA_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")
CRTCLA_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
CRTCLA_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# Optional authoritative fast clock (used for 'now' minutes if available)
CRTCLA_Timebase = InstanceManager.getDefault(jmri.Timebase)

# Time parsing/formatting
CRTCLA_TimeParser = SimpleDateFormat("h:mm a")
CRTCLA_AltParser = SimpleDateFormat("H:mm")
CRTCLA_FmtHHmm = SimpleDateFormat("HHmm")

def CRTCLA_ParseMinutes(s):
    for p in [CRTCLA_TimeParser, CRTCLA_AltParser]:
        try:
            d = p.parse(s)
            return d.getHours() * 60 + d.getMinutes()
        except:
            pass
    return None

def CRTCLA_FormatHHmm(s):
    for p in [CRTCLA_TimeParser, CRTCLA_AltParser]:
        try:
            d = p.parse(s)
            return CRTCLA_FmtHHmm.format(d)
        except:
            pass
    return s.replace(":", "")

def CRTCLA_MinutesToHHmm(total):
    total = total % (24 * 60)
    h = total // 60
    m = total % 60
    return ("%02d%02d" % (h, m))

# CSV access

def CRTCLA_TimetablePath():
    name = (TBL.SafeGetMemoryValue("CURRENTTIMETABLE", "") or "").strip()
    return TASPathResolver.GetTimetableCsvPath(name) or ""
def CRTCLA_CsvRows():
    path = CRTCLA_TimetablePath()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []


def CRTCLA_PlatformField(row):
    return (row.get("Plat", "") or row.get("Platform", "") or "").strip()


def CRTCLA_GetFieldCI(row, desiredName):
    """Return the value from 'row' for the column 'desiredName' case-insensitively."""
    try:
        want = str(desiredName or "").strip().lower()
    except:
        want = ""
    if not want:
        return ""
    try:
        for k in row.keys():
            try:
                if str(k).strip().lower() == want:
                    return row.get(k, "") or ""
            except:
                pass
    except:
        pass
    return ""


def CRTCLA_ParseOverrides(s):
    out = {}
    if not s:
        return out
    for part in s.replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def CRTCLA_GetOverride(rn):
    try:
        return CRTCLA_ParseOverrides(CRTCLA_OverridesMem.getValue()).get(rn)
    except:
        return None


# ---- Departure TP selection + logged-departure check (as per PIDSmall) ----

def CRTCLA_ActiveProfileBaseTPName():
    # Default 'Arr' timing point = active profile name (base TP).
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""


def CRTCLA_ArrivalTPList():
    """
    Read IMPID_ARRIVAL_TP (single or ';' / ',' separated list).
    If absent/blank, fall back to base timing point (active profile name).
    """
    names = []
    try:
        raw = CRTCLA_ArrivalTPMem.getValue() if CRTCLA_ArrivalTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        base = CRTCLA_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names


def CRTCLA_HasArrivedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    """
    True iff any configured departure timing point contains a tuple for (reportingNumber, dayName)
    whose logged time <= nowMinutes. TimingRegister tuples are (reportingNumber, direction, time, day).
    Any tuple here is a departure record.
    """
    tps = CRTCLA_ArrivalTPList()
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
            mm = CRTCLA_ParseMinutes(tstr)
            if mm is None:
                continue
            if mm <= int(nowMinutes):
                return True
    return False


# ---- ECS detector (class-5 or keyword heuristics) ----
CRTCLA_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]


def CRTCLA_ReadExtraEcsTerms():
    """Read extra ECS terms from IMPID_ECS_FILTER_TERMS (split on ';' or ',')."""
    try:
        raw = CRTCLA_EcsFilterMem.getValue() if CRTCLA_EcsFilterMem is not None else None
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


def CRTCLA_IsEcsWorking(row):
    """
    Return True if the row is an ECS/empty-to-depot working.
    Rules:
    1) Reporting number starts with '5'
    2) Destination or Calling pattern contains an ECS keyword (default + configurable extras)
    """
    rn = ((row.get("Reporting number", "") or "")).strip().upper()
    if rn.startswith("5"):
        return True
    dest = ((row.get("Destination", "") or "")).strip().upper()
    call = ((row.get("Calling pattern", "") or "")).strip().upper()
    terms = set([t.upper() for t in CRTCLA_DefaultEcsTerms])
    for extra in CRTCLA_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " " + ( (row.get("Origin", "") or "").strip().upper() ) + " " + call
    for t in terms:
        if t and t in hay:
            return True
    return False


class CRTCLA_PropertyListener(PropertyChangeListener):
    def __init__(self, owner):
        self.owner = owner

    def propertyChange(self, e):
        # Forward the event to the window instance refresh method
        self.owner.refresh(e)


class CRTCLA_WindowCloseHandler(WindowAdapter):
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


class CRTCLA_PlatformChangeListener(PropertyChangeListener):
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
            print("[PIDCRTSummaryColourArrivals] Platform listener error:", str(ex))


class CRTCLA_FlashTick(ActionListener):
    """Toggles visibility of flashing platforms every 500ms and stops at 1 minute."""

    def __init__(self, owner):
        self.owner = owner

    def actionPerformed(self, e):
        try:
            self.owner._onFlashTick()
        except Exception as ex:
            print("[PIDCRTSummaryColourArrivals] FlashTick error:", str(ex))


# ----------------- PANELS -----------------

class CRTCLA_CabinetPanel(swing.JPanel):
    def __init__(self):
        super(CRTCLA_CabinetPanel, self).__init__()
        self.setOpaque(False)
        self.setLayout(None)

    def paintComponent(self, g):
        super(CRTCLA_CabinetPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        W = self.getWidth()
        H = self.getHeight()
        g2.setColor(Color.BLACK)
        g2.fillRect(0, 0, W, H)
        gp = GradientPaint(0, 0, CRTCLA_CabinetYellow, 0, H, CRTCLA_CabinetShade)
        g2.setPaint(gp)
        g2.fillRoundRect(0, 0, W, H, 20, 20)
        g2.setColor(CRTCLA_CabinetEdge)
        g2.setStroke(BasicStroke(5.5))
        g2.drawRoundRect(2, 2, W - 4, H - 4, 20, 20)


class CRTCLA_InnerCasingHeaderPanel(swing.JPanel):
    """Header area with centered 'Departures'."""

    def __init__(self, headerH):
        super(CRTCLA_InnerCasingHeaderPanel, self).__init__()
        self.headerH = headerH
        self.setOpaque(False)
        self.setLayout(None)

    def paintComponent(self, g):
        super(CRTCLA_InnerCasingHeaderPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth()
        H = self.getHeight()
        g2.setColor(CRTCLA_InnerBlack)
        g2.fillRoundRect(0, 0, W, H, 16, 16)
        g2.fillRoundRect(8, 8, W - 16, self.headerH, 12, 12)

        text = u"Arrivals"
        padX = 22
        # Choose the largest font that fits within header box
        maxW = W - 2 * padX
        maxH = int(self.headerH * 0.72)
        chosen = None
        for size in range(CRTCLA_HeadSzMax, CRTCLA_HeadSzMin - 1, -1):
            f = Font(CRTCLA_RailAlpha, Font.PLAIN, size)
            fm = g2.getFontMetrics(f)
            if fm.stringWidth(text) <= maxW and fm.getHeight() <= maxH:
                chosen = (f, fm)
                break
        if chosen is None:
            f = Font(CRTCLA_RailAlpha, Font.PLAIN, CRTCLA_HeadSzMin)
            fm = g2.getFontMetrics(f)
        else:
            f, fm = chosen

        g2.setFont(f)
        g2.setColor(CRTCLA_LegendText)
        x = (W - fm.stringWidth(text)) // 2
        yBoxTop = 8
        yBoxH = self.headerH
        y = yBoxTop + (yBoxH - fm.getHeight()) // 2 + fm.getAscent()
        g2.drawString(text, x, y)


class CRTCLA_CRTPanel(swing.JPanel):
    def __init__(self, inset):
        super(CRTCLA_CRTPanel, self).__init__()
        self.inset = inset
        self.setOpaque(False)

    def paintComponent(self, g):
        super(CRTCLA_CRTPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth()
        H = self.getHeight()
        g2.setColor(CRTCLA_CrtBorder)
        g2.fillRoundRect(0, 0, W, H, 18, 18)
        inset = self.inset
        x0 = inset
        y0 = inset
        innerW = W - 2 * inset
        innerH = H - 2 * inset
        gp = GradientPaint(0, y0, CRTCLA_CrtBg, 0, y0 + innerH, CRTCLA_CrtGlow)
        g2.setPaint(gp)
        g2.fillRoundRect(x0, y0, innerW, innerH, 16, 16)
        g2.setColor(Color(CRTCLA_CrtScan.getRed(), CRTCLA_CrtScan.getGreen(), CRTCLA_CrtScan.getBlue(), CRTCLA_ScanlineAlpha))
        for y in range(y0 + 1, y0 + innerH - 1, 2):
            g2.drawLine(x0 + 8, y, x0 + innerW - 8, y)


# ------ Summary table painter (stores metrics; centers within its bounds) ------

class CRTCLA_SummaryTablePanel(swing.JPanel):
    def __init__(self):
        super(CRTCLA_SummaryTablePanel, self).__init__()
        self.setOpaque(False)
        self.lines = []
        self._last_meas = None  # (lineH, fontSize)
        self._locked_size = None  # when set, freeze font size
        self.flashMap = {}  # rn -> {"show": bool, "until": millisDeadline}

    def setFlashMap(self, flashMap):
        self.flashMap = flashMap or {}

    def lockFontSize(self, size):
        self._locked_size = size
        self.repaint()

    def unlockFont(self):
        self._locked_size = None

    def setLines(self, lines):
        self.lines = lines or []
        self._last_meas = None
        self.unlockFont()
        self.repaint()

    def _truncateToWidth(self, fm, s, maxPx):
        s = s or ""
        if maxPx <= 0:
            return ""
        if fm.stringWidth(s) <= maxPx:
            return s
        ell = "..."
        ellW = fm.stringWidth(ell)
        if ellW >= maxPx:
            while s and fm.stringWidth(s) > maxPx:
                s = s[:-1]
            return s
        t = s
        while t and fm.stringWidth(t) + ellW > maxPx:
            t = t[:-1]
        return t + ell

    def _measureFixedColumnsPx(self, fm):
        # Measure columns that should not expand uncontrollably.
        wDue = fm.stringWidth("Due")
        wPlat = fm.stringWidth("Plat")
        wExp = fm.stringWidth("Expected")
        wDestWant = fm.stringWidth("From")

        for ln in self.lines:
            if ln.get("type") == "main":
                due = CRTCLA_FormatHHmm(ln.get("due") or "")
                plat = str(ln.get("plat") or "")
                exp = ln.get("exp") or ""
                dest = ln.get("dest") or ""
                wDue = max(wDue, fm.stringWidth(due))
                wPlat = max(wPlat, fm.stringWidth(plat))
                wExp = max(wExp, fm.stringWidth(exp))
                wDestWant = max(wDestWant, fm.stringWidth(dest))
            else:
                sub = ln.get("sub") or ""
                wDestWant = max(wDestWant, fm.stringWidth(sub))

        return wDue, wPlat, wExp, wDestWant

    def _fitFont(self, g2, fam, minSz, maxSz, availW, availH):
        # Rows:
        # 0: 'DEPARTURES'
        # 1: headings
        # 2..11: content (10 rows)
        rowsToDraw = 12

        def trySize(size):
            f = Font(fam, Font.BOLD, size)
            fm = g2.getFontMetrics(f)
            lineH = fm.getAscent() + fm.getDescent()

            wDue, wPlat, wExp, wDestWant = self._measureFixedColumnsPx(fm)

            # Column gaps are proportional to line height.
            gap1 = max(8, int(lineH * 0.28))  # Due -> Destination
            gap2 = max(6, int(lineH * 0.28))
            gap3 = max(6, int(lineH * 0.28))

            fixedW = wDue + gap1 + gap2 + gap3 + wPlat + wExp
            remain = availW - fixedW
            minDest = fm.stringWidth("From")

            if remain < minDest:
                return None

            # Destination takes remaining width but cannot steal space from other columns.
            wDest = remain
            wDest = max(minDest, wDest)

            totalW = fixedW + wDest
            totalH = rowsToDraw * lineH

            if totalW <= availW and totalH <= availH:
                return f, fm, lineH, wDue, wDest, wPlat, wExp, gap1, gap2, gap3, totalW
            return None

        if self._locked_size is not None:
            res = trySize(self._locked_size)
            if res is not None:
                return res

        for size in range(maxSz, minSz - 1, -1):
            res = trySize(size)
            if res is not None:
                return res

        # Emergency: allow going below RowSzMin to avoid clipping.
        for size in range(minSz - 1, 7, -1):
            res = trySize(size)
            if res is not None:
                return res

        # Absolute fallback.
        f = Font(fam, Font.BOLD, 8)
        fm = g2.getFontMetrics(f)
        lineH = fm.getAscent() + fm.getDescent()
        wDue, wPlat, wExp, wDestWant = self._measureFixedColumnsPx(fm)
        gap1 = max(8, int(lineH * 0.28))
        gap2 = max(6, int(lineH * 0.28))
        gap3 = max(6, int(lineH * 0.28))
        fixedW = wDue + gap1 + gap2 + gap3 + wPlat + wExp
        remain = max(0, availW - fixedW)
        wDest = remain
        totalW = fixedW + wDest
        totalH = 12 * lineH
        return f, fm, lineH, wDue, wDest, wPlat, wExp, gap1, gap2, gap3, totalW

    def paintComponent(self, g):
        super(CRTCLA_SummaryTablePanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)

        W = self.getWidth()
        H = self.getHeight()
        if W <= 0 or H <= 0:
            return

        availW = max(0, W - 2 * CRTCLA_TablePadX)
        availH = max(0, H - 2 * CRTCLA_TablePadY)

        f, fm, lineH, wDue, wDest, wPlat, wExp, gap1, gap2, gap3, totalW = self._fitFont(
            g2, CRTCLA_MonoFamily, CRTCLA_RowSzMin, CRTCLA_RowSzMax, availW, availH)

        g2.setFont(f)

        # Center horizontally.
        # Normalize row pitch (baseline-to-baseline) across fonts.
        # Use the maximum ascent+descent across key candidate fonts at this size, so tighter fonts
        # (e.g. Liberation Sans Narrow) do not appear vertically compressed compared with Arial Narrow.
        baseLineH = lineH
        refBaseLineH = baseLineH
        try:
            env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
            fams = set(env.getAvailableFontFamilyNames())
            for fam in CRTCLA_RowPitchRefFamilies:
                if fam in fams:
                    tf = Font(fam, Font.BOLD, f.getSize())
                    tfm = g2.getFontMetrics(tf)
                    refBaseLineH = max(refBaseLineH, tfm.getAscent() + tfm.getDescent())
        except:
            pass
        desiredGap = max(int(CRTCLA_MinRowGapPx), int(round(f.getSize() * CRTCLA_RowGapFactor)))
        rowPitch = refBaseLineH + desiredGap + int(CRTCLA_RowExtraPadPx)
        maxPitch = availH // 12
        if maxPitch < baseLineH:
            maxPitch = baseLineH
        if rowPitch > maxPitch:
            rowPitch = maxPitch
        rowPad = max(0, rowPitch - baseLineH)
        # Shift the table up slightly to keep the overall text size unchanged while adding row spacing.
        shiftUp = int(round(((12 - 1) * rowPad) / 2.0))
        padT = max(0, CRTCLA_TablePadY - shiftUp)

        extraX = max(0, (availW - totalW) // 2)
        padL = CRTCLA_TablePadX + extraX
        # padT computed above to compensate for rowPad

        xDue = padL
        xDest = xDue + wDue + gap1
        xPlat = xDest + wDest + gap2
        xExp = xPlat + wPlat + gap3

        # Row 0: 'ARRIVALS' centered over Destination.
        y = padT + fm.getAscent()
        label = "ARRIVALS"
        xLabel = int(xDest + (fm.stringWidth("From") / 2.0) - (fm.stringWidth(label) / 2.0)) + 20
        g2.setColor(CRTCLA_TextWhite)
        g2.drawString(label, xLabel, y)

        # Row 1: headings.
        y += rowPitch
        g2.setColor(CRTCLA_TextWhite)
        g2.drawString("Due", xDue, y)
        g2.drawString("From", xDest, y)
        g2.drawString("Plat", xPlat, y)
        g2.drawString("Expected", xExp, y)

        # Rule.
        g2.setStroke(BasicStroke(1.0))
        uy = y + 2
        g2.drawLine(xDue, uy, xExp + wExp, uy)

        # Content.
        y += rowPitch
        rowIndex = 0
        for ln in self.lines:
            if rowIndex >= 10:
                break

            cancelled = bool(ln.get("cancelled", False))
            if cancelled:
                rowTop = y - fm.getAscent()
                g2.setColor(CRTCLA_CancelBg)
                g2.fillRect(xDue, rowTop, (xExp + wExp) - xDue, rowPitch)
                baseColor = CRTCLA_CancelText
                destColor = CRTCLA_CancelText
            else:
                baseColor = CRTCLA_TextWhite
                destColor = CRTCLA_DestYellow

            if ln.get("type") == "main":
                rn = (ln.get("rn") or "").strip()
                due = CRTCLA_FormatHHmm(ln.get("due") or "")
                dest = ln.get("dest") or ""

                flashEntry = self.flashMap.get(rn) if self.flashMap else None
                platShown = (flashEntry is None) or bool(flashEntry.get("show", True))
                plat = (ln.get("plat") or "") if platShown else ""
                exp = ln.get("exp") or ""

                due = self._truncateToWidth(fm, due, wDue)
                dest = self._truncateToWidth(fm, dest, wDest)
                plat = self._truncateToWidth(fm, str(plat), wPlat)
                exp = self._truncateToWidth(fm, exp, wExp)

                g2.setColor(baseColor)
                g2.drawString(due, xDue, y)

                g2.setColor(destColor)
                g2.drawString(dest, xDest, y)

                g2.setColor(baseColor)
                g2.drawString(plat, xPlat, y)
                g2.drawString(exp, xExp, y)
            else:
                wSub = (xExp + wExp) - xDue
                sub = self._truncateToWidth(fm, ln.get("sub") or "", wSub)
                g2.setColor(baseColor)
                g2.drawString(sub, xDue, y)

            y += rowPitch
            rowIndex += 1

        self._last_meas = (lineH, f.getSize())

    def lastMeasured(self):
        return self._last_meas
class CRTCLA_CRTSummaryWindow(object):
    def __init__(self):
        # Initial sizes (approximate); will be 4:3-corrected & tightened post-paint
        # Fixed sizes to match the original monochrome CRT summary window.
        cabW = CRTCLA_FixedCabinetWidth
        cabH = CRTCLA_FixedCabinetHeight

        innerW = cabW - 2 * CRTCLA_InnerPad
        innerH = cabH - 2 * CRTCLA_InnerPad

        crtPanelW = innerW - 2 * CRTCLA_SideMargin
        crtPanelH = innerH - CRTCLA_HeaderHeight - CRTCLA_TopMargin - CRTCLA_BottomMargin

        glassW = crtPanelW - 2 * CRTCLA_BezelInset
        glassH = crtPanelH - 2 * CRTCLA_BezelInset

        frameW = cabW + 2 * CRTCLA_FramePad
        frameH = cabH + 2 * CRTCLA_FramePad

        self.frame = swing.JFrame("Passenger information display: arrivals")
        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setPreferredSize(Dimension(frameW, frameH))
        cp.setBackground(Color.BLACK)

        # Yellow cabinet
        self.cab = CRTCLA_CabinetPanel()
        self.cab.setBounds(CRTCLA_FramePad, CRTCLA_FramePad, cabW, cabH)
        self.cab.setLayout(None)
        cp.add(self.cab)

        # Inner casing with header
        self.inner = CRTCLA_InnerCasingHeaderPanel(CRTCLA_HeaderHeight)
        self.inner.setBounds(CRTCLA_InnerPad, CRTCLA_InnerPad, innerW, innerH)
        self.inner.setLayout(None)
        self.cab.add(self.inner)

        # CRT panel (bezel+glass)
        self.crt = CRTCLA_CRTPanel(CRTCLA_BezelInset)
        self.crt.setBounds(CRTCLA_SideMargin, CRTCLA_HeaderHeight + CRTCLA_TopMargin, crtPanelW, crtPanelH)
        self.crt.setLayout(None)
        self.inner.add(self.crt)

        # Table area (bounds will be re-set after measurement)
        self.table = CRTCLA_SummaryTablePanel()
        self._tightened_once = False
        self._applyTableBounds(crtPanelW, crtPanelH)
        self.crt.add(self.table)

        # Listeners
        self._pcl = CRTCLA_PropertyListener(self)
        CRTCLA_TimeMem.addPropertyChangeListener(self._pcl)
        CRTCLA_DayMem.addPropertyChangeListener(self._pcl)
        if CRTCLA_TimetableMem is not None:
            CRTCLA_TimetableMem.addPropertyChangeListener(self._pcl)
        if CRTCLA_OverridesMem is not None:
            CRTCLA_OverridesMem.addPropertyChangeListener(self._pcl)
        if CRTCLA_ArrivalTPMem is not None:
            CRTCLA_ArrivalTPMem.addPropertyChangeListener(self._pcl)
        if CRTCLA_EcsFilterMem is not None:
            CRTCLA_EcsFilterMem.addPropertyChangeListener(self._pcl)

        self._windowCloser = CRTCLA_WindowCloseHandler(self)
        self.frame.setDefaultCloseOperation(swing.JFrame.DO_NOTHING_ON_CLOSE)
        self.frame.addWindowListener(self._windowCloser)
        self._rows_cache = None

        self.frame.pack()
        self.frame.setResizable(False)
        self.refresh()
        self.frame.setVisible(True)

        # --- Platform allocation listener + flash timer (500ms on/off for 1 minute) ---
        self._flashMap = {}  # rn -> {"show": True/False, "until": millisDeadline}
        self._flashTick = CRTCLA_FlashTick(self)
        self._flashTimer = None  # javax.swing.Timer
        self.table.setFlashMap(self._flashMap)

        # Subscribe to PlatformAllocationRegister events
        self._parListener = CRTCLA_PlatformChangeListener(self)
        try:
            PAR.addPlatformListener(self._parListener)
        except Exception as ex:
            print("[PIDCRTSummaryColourArrivals] Failed to add platform listener:", str(ex))

    def _applyTableBounds(self, crtPanelW, crtPanelH):
        # Fill glass; the panel itself will center content inside using margins
        self.table.setBounds(CRTCLA_BezelInset, CRTCLA_BezelInset,
                            crtPanelW - 2 * CRTCLA_BezelInset, crtPanelH - 2 * CRTCLA_BezelInset)

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
                print("[PIDCRTSummaryColourArrivals] Failed to start flash timer:", str(ex))
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

    # ------ Data helpers ------

    def _rowsToday(self):
        if self._rows_cache is None:
            self._rows_cache = CRTCLA_CsvRows()
        rows = self._rows_cache
        curDay = CRTCLA_DayMem.getValue() or ""
        return [r for r in rows if (r.get(curDay, "") or "").strip().lower() == "true"]

    def _titleCaseDestination(self, s):
        """Title-case destination strings while attempting to preserve acronyms."""
        s = (s or "").strip()
        if not s:
            return ""
        out = []
        for w in s.split():
            # Preserve short acronyms
            try:
                if w.isupper() and len(w) <= 3:
                    out.append(w)
                    continue
            except:
                pass
            if len(w) == 1:
                out.append(w.upper())
            else:
                out.append(w[:1].upper() + w[1:].lower())
        return " ".join(out)

    def _nextArrivalServices(self):
        """Return a list of candidate services (not lines), sorted by scheduled arrival time."""
        rows = self._rowsToday()

        # 'Now' in minutes: prefer fast clock, else memory string
        if CRTCLA_Timebase is not None:
            ft = CRTCLA_Timebase.getTime()  # java.util.Date
            curMin = ft.getHours() * 60 + ft.getMinutes()
        else:
            curStr = CRTCLA_TimeMem.getValue() or ""
            curMin = CRTCLA_ParseMinutes(curStr)
        if curMin is None:
            return []

        curDay = CRTCLA_DayMem.getValue() or ""
        cands = []
        for row in rows:
            arr = (row.get("Arr", "") or "").strip()
            if not arr:
                continue
            rn = (row.get("Reporting number", "") or "").strip()

            # Skip ECS/empty-to-depot workings
            if CRTCLA_IsEcsWorking(row):
                continue

            # Platform precedence: allocation register > overrides > timetable
            alloc = PAR.getPlatform(rn)
            if alloc is not None and str(alloc).strip():
                plat = str(alloc)
            else:
                plat = CRTCLA_GetOverride(rn) or CRTCLA_PlatformField(row)

            arrMin = CRTCLA_ParseMinutes(arr)
            if arrMin is None or arrMin < curMin:
                continue

            # Drop if this RN is logged as arrived at configured TP(s)
            if CRTCLA_HasArrivedAtConfiguredTP(rn, curDay, curMin):
                continue

            origin = (row.get("Origin", "") or "").strip()
            via = (CRTCLA_GetFieldCI(row, "Via") or "").strip()
            special = (CRTCLA_GetFieldCI(row, "Special") or "").strip()

            cands.append({
                "rn": rn,
                "plat": str(plat or ""),
                "due": arr,
                "tmin": arrMin,
                "dest": origin,
                "via": via,
                "special": special
            })

        cands.sort(key=lambda t: t["tmin"])
        return cands

    # Formation-aware delay lookup (recursive)
    def delayWithInheritance(self, rn, sched_dep_min, visited=None):
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

        rows = self._rowsToday()
        formers = []
        for r in rows:
            if (r.get("Forms", "") or "").strip() == rn:
                arr = (r.get("Arr", "") or "").strip()
                arrMin = CRTCLA_ParseMinutes(arr) if arr else None
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
        former_rn = (chosen[0].get("Reporting number", "") or "").strip()
        return self.delayWithInheritance(former_rn, sched_dep_min, visited)

    def expectedText(self, rn, sched_time):
        smin = CRTCLA_ParseMinutes(sched_time)
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
                return "Cancelled"
            if delay > 0 and smin is not None:
                return CRTCLA_MinutesToHHmm(smin + delay)

        kind, val = self.delayWithInheritance(rn, smin, visited=set())
        if kind == "cancel":
            return "Cancelled"
        if kind == "delay" and val and smin is not None:
            return CRTCLA_MinutesToHHmm(smin + val)
        return "On time"

    def _isCancelledExpected(self, expText):
        try:
            return str(expText or "").strip().lower() == "cancelled"
        except:
            return False

    def buildDisplayLines(self):
        """Build up to 10 physical content rows, including via/special sub-rows."""
        services = self._nextArrivalServices()
        lines = []

        # Keep adding service rows (and via/special sub-rows) until we have 10 physical lines.
        for svc in services:
            if len(lines) >= 10:
                break

            exp = self.expectedText(svc["rn"], svc["due"])
            cancelled = self._isCancelledExpected(exp)
            destTitle = self._titleCaseDestination(svc.get("dest"))

            lines.append({
                "type": "main",
                "rn": svc.get("rn"),
                "due": svc.get("due"),
                "dest": destTitle,
                "plat": (svc.get("plat") or ""),
                "exp": exp,
                "cancelled": cancelled
            })

            via = (svc.get("via") or "").strip()
            if via and len(lines) < 10:
                lines.append({
                    "type": "sub",
                    "rn": svc.get("rn"),
                    "sub": via,
                    "cancelled": cancelled
                })

            special = (svc.get("special") or "").strip()
            if special and len(lines) < 10:
                lines.append({
                    "type": "sub",
                    "rn": svc.get("rn"),
                    "sub": special,
                    "cancelled": cancelled
                })

        return lines

    def refresh(self, e=None):
        lines = self.buildDisplayLines()
        self._tightened_once = False
        self.table.setLines(lines)
        swing.SwingUtilities.invokeLater(self._tighten_if_possible)

    # --- Auto-tighten + enforce 4:3 glass (expand height only if needed) ---
    def _tighten_if_possible(self):
        if self._tightened_once:
            return
        meas = self.table.lastMeasured()
        if not meas:
            return
        lineH, fsize = meas
        # Preserve fixed cabinet/window size; only lock the chosen font size.
        self.table.lockFontSize(fsize)
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)
        except Exception as ex:
            print("[PIDCRTSummaryColourArrivals] Failed to set PID window icon: " + str(ex))
        self._tightened_once = True

    def cleanup(self):
        # Remove property listeners using the same listener object that was added
        try:
            pcl = getattr(self, "_pcl", None)
        except:
            pcl = None
        if pcl is not None:
            try:
                CRTCLA_TimeMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                CRTCLA_DayMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTCLA_TimetableMem is not None:
                    CRTCLA_TimetableMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTCLA_OverridesMem is not None:
                    CRTCLA_OverridesMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTCLA_ArrivalTPMem is not None:
                    CRTCLA_ArrivalTPMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTCLA_EcsFilterMem is not None:
                    CRTCLA_EcsFilterMem.removePropertyChangeListener(pcl)
            except:
                pass

        # Remove window listener
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


# ----------------- Manager -----------------

class CRTCLA_CRTSummaryManager(object):
    def __init__(self):
        self.window = CRTCLA_CRTSummaryWindow()


# ----------------- Run -----------------

CRTCLA_Manager = CRTCLA_CRTSummaryManager(),
