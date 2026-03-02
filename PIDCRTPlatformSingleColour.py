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
# 1990s colour CRT PID (per-platform)
# Selection logic mirrors PIDCRTSingle.py (clear-on-departure; due-within; ECS filter; inherited disruption).
# Render style matches the colour summary PIDs.
#
# Layout:
# - Cabinet: yellow, with "Next train" on the inner header band.
# - Screen: header / main / footer separated by thin white lines.
# - Main section: calling pattern (yellow) + optional special text (white) after a blank line.
# - Footer: page x of y, company (from timetable row if present), and a HH:MM:SS clock.
#
# <<PID-DISP-NAME: Colour CRT platform display>>
# <<DESCRIPTION: British Rail 1990s colour CRT monitor showing the next train per platform>>
#
# User-configurable settings discovered by TASSetup:
# <<SETTING DESCRIPTION NUMBER: Colour CRT platform display: Due window (minutes)>>
# <<SETTING DESCRIPTION STRING: Colour CRT platform display: ECS filter terms>>

# BUILD-ID: CRTPlatformSingleColourV2 2025-12-29
# BUILD-ID: CRTPlatformSingleColourV3 2025-12-29
# BUILD-ID: CRTPlatformSingleColourV3_Final 2025-12-29
# BUILD-ID: CancelCyan 2025-12-29

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, GradientPaint, RenderingHints, BasicStroke, Dimension
from java.awt.event import WindowAdapter
from java.awt.event import ActionListener
from javax.swing import Timer
from java.beans import PropertyChangeListener
from java.lang import System
from java.util import Date
import java.text.SimpleDateFormat as SimpleDateFormat

import jmri
from jmri.util import FileUtil
from jmri import InstanceManager

import os, csv
import TASBeanLookup as TBL
import TimingRegister as TR
import PlatformAllocationRegister as PAR
from DisruptionRegister import getDisruption

# ====== Cabinet / CRT geometry (match colour summary window) ======
CRTSPC_CrtGlassWidth = 640
CRTSPC_HeaderHeight = 108
CRTSPC_InnerPad = 16
CRTSPC_FramePad = 4
CRTSPC_BezelInset = 3
CRTSPC_SideMargin = 6
CRTSPC_TopMargin = 6
CRTSPC_BottomMargin = 6

# Fixed cabinet size to match the colour summary window.
# These values are cabinet panel sizes (excluding the OS window decoration).
CRTSPC_FixedCabinetWidth = 530
CRTSPC_FixedCabinetHeight = 520

# ====== Colours (match colour summary) ======
# Cabinet: yellow
CRTSPC_CabinetYellow = Color(235, 200, 40)
CRTSPC_CabinetShade = Color(170, 140, 25)
CRTSPC_CabinetEdge = Color(60, 50, 0)
CRTSPC_InnerBlack = Color(10, 10, 10)
CRTSPC_CrtBorder = Color(22, 22, 24)

# CRT: deep blue background with subtle glow
CRTSPC_CrtBg = Color(0, 18, 110)
CRTSPC_CrtGlow = Color(0, 36, 160)

# Scanlines
CRTSPC_CrtScan = Color(210, 220, 235)
CRTSPC_ScanlineAlpha = 12

# Text colours
CRTSPC_TextWhite = Color(245, 245, 245)
CRTSPC_TextYellow = Color(255, 220, 0)
CRTSPC_CancelBg = Color(0, 255, 255)
CRTSPC_CancelText = Color(0, 0, 0)

# ====== Fonts / families ======
# Table/body font candidates (match your colour summary preferences).
CRTSPC_MonoCands = ["Liberation Sans Narrow", "Arial Narrow", "Bahnschrift Condensed", "SansSerif"]
CRTSPC_RailCands = [
    "BritishRailLightNormal", "British Rail Light Normal", "Rail Alphabet", "RailAlphabet",
    "Arial", "Helvetica", "SansSerif"
]

def CRTSPC_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

CRTSPC_MonoFamily = CRTSPC_PickFamily(CRTSPC_MonoCands)
CRTSPC_RailAlpha = CRTSPC_PickFamily(CRTSPC_RailCands)

# ====== Sizing ======
# Main text size should match the summary main text.
CRTSPC_MainSzMax = 24
CRTSPC_MainSzMin = 12

# Header text is larger.
CRTSPC_HeaderSzMax = 34
CRTSPC_HeaderSzMin = 14
# Cabinet header text sizing ("Next train").
CRTSPC_CabinetSzMax = CRTSPC_HeaderSzMax * 2
CRTSPC_CabinetSzMin = CRTSPC_HeaderSzMin * 2

# Internal padding in the CRT
CRTSPC_PadX = 8
CRTSPC_PadY = 8

# Section split: middle is about 2/3 of usable height
CRTSPC_MiddleFrac = 2.0 / 3.0

# Extra gap between the mid-section top rule and the "Calling at:" label (in units of row pitch).
CRTSPC_CallAtGapFactor = 0.70
# Message shown when there is no train to display.
CRTSPC_NoTrainMessage = "Please listen for announcements. The next train will be displayed here shortly before it is due."

# Paging cycle (seconds) when more than one page.
CRTSPC_PageSecondsMem = TBL.ProvideMemoryBySuffix("PID_CRT_PAGE_SECONDS", "5")

# Company fallback (if timetable row has no Company column).
CRTSPC_CompanyMem = TBL.ProvideMemoryBySuffix("PID_COMPANY_NAME", "")

# ====== Row pitch normalization (match colour summary approach) ======
CRTSPC_RowPitchRefFamilies = ["Arial Narrow", "Liberation Sans Narrow"]
CRTSPC_RowGapFactor = 0.10
CRTSPC_MinRowGapPx = 2

# ====== JMRI memories / timetable ======
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
CRTSPC_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
CRTSPC_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
CRTSPC_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
CRTSPC_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")
CRTSPC_DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
CRTSPC_WithInMinMem = TBL.ProvideMemoryBySuffix("PID_CRT_WITHIN_MINUTES", "5")
CRTSPC_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")


# TASSetup user-setting memories (friendly labels are unique to this display to avoid clashes).
TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_Mem = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_", "5")
# Legacy TASSetup key: WITHIN_MINUTES (shared across displays; retained for compatibility).
TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_WITHIN_MINUTES_LegacyMem = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_WITHIN_MINUTES", "")
TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS", "ECS;DEPOT;CARRIAGE SIDINGS;CARRIAGE SDGS;SIDING;SIDINGS;C.S.;CS;TMD;TRSMD;UP SIDINGS;DOWN SIDINGS")
try:
    if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem is not None:
        _v = TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem.getValue()
        if _v is None or str(_v).strip() == "":
            TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem.setValue("ECS;DEPOT;CARRIAGE SIDINGS;CARRIAGE SDGS;SIDING;SIDINGS;C.S.;CS;TMD;TRSMD;UP SIDINGS;DOWN SIDINGS")
except:
    pass
# Optional authoritative fast clock
CRTSPC_Timebase = InstanceManager.getDefault(jmri.Timebase)

# Time parsing/formatting
CRTSPC_TimeParser = SimpleDateFormat("h:mm a")
CRTSPC_AltParser = SimpleDateFormat("H:mm")
CRTSPC_FmtHHmm = SimpleDateFormat("HHmm")
CRTSPC_FmtHMS = SimpleDateFormat("HH:mm:ss")


def CRTSPC_ParseMinutes(s):
    for p in [CRTSPC_TimeParser, CRTSPC_AltParser]:
        try:
            d = p.parse(s)
            return d.getHours() * 60 + d.getMinutes()
        except:
            pass
    return None


def CRTSPC_FormatHHmm(s):
    for p in [CRTSPC_TimeParser, CRTSPC_AltParser]:
        try:
            d = p.parse(s)
            return CRTSPC_FmtHHmm.format(d)
        except:
            pass
    return (s or "").replace(":", "")


def CRTSPC_MinutesToHHmm(total):
    if total is None:
        return ""
    total = total % (24 * 60)
    h = total // 60
    m = total % 60
    return "%02d%02d" % (h, m)


def CRTSPC_NowDate():
    try:
        if CRTSPC_Timebase is not None:
            return CRTSPC_Timebase.getTime()
    except:
        pass
    return Date(System.currentTimeMillis())


def CRTSPC_GetFieldCI(row, desiredName):
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

# ---- Timetable access ----

def CRTSPC_TimetablePath():
    name = CRTSPC_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    # Prefer JMRI scheme resolution for portability
    try:
        return FileUtil.getExternalFilename("profile:timetable/" + str(name) + ".csv")
    except Exception:
        return os.path.join(profilePath, "timetable", name + ".csv")


def CRTSPC_CsvRows():
    path = CRTSPC_TimetablePath()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []


def CRTSPC_PlatformField(row):
    return (row.get("Plat", "") or row.get("Platform", "") or "").strip()


def CRTSPC_ParseOverrides(s):
    out = {}
    if not s:
        return out
    for part in str(s).replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def CRTSPC_GetOverride(rn):
    try:
        return CRTSPC_ParseOverrides(CRTSPC_OverridesMem.getValue()).get(rn)
    except:
        return None

# ---- Departure TP selection + logged-departure check ----

def CRTSPC_ActiveProfileBaseTPName():
    # Default 'Dep' timing point = active profile name (base TP).
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""


def CRTSPC_DepartureTPList():
    """Read IMPID_DEPARTURE_TP; if blank, fall back to base timing point (active profile name)."""
    names = []
    try:
        raw = CRTSPC_DepartTPMem.getValue() if CRTSPC_DepartTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        base = CRTSPC_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names


def CRTSPC_HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    tps = CRTSPC_DepartureTPList()
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
            mm = CRTSPC_ParseMinutes(tstr)
            if mm is None:
                continue
            if mm <= int(nowMinutes):
                return True
    return False

# ---- "Due within X minutes" window ----
CRTSPC_DefaultWithinMinutes = 5


def CRTSPC_ReadWithinMinutes():
    """Read due-window minutes. Preference order:
    1) TASSetup friendly setting (unique to this display)
    2) TASSetup legacy setting (WITHIN_MINUTES)
    3) Legacy runtime memory PID_CRT_WITHIN_MINUTES
    4) Default
    0 means infinite (no due-window filtering).
    """
    try:
        for mem in [TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_Mem, TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_WITHIN_MINUTES_LegacyMem, CRTSPC_WithInMinMem]:
            try:
                v = mem.getValue() if mem is not None else None
            except:
                v = None
            s = ("" if v is None else str(v)).strip()
            if s != "":
                try:
                    x = int(float(s))
                except:
                    x = CRTSPC_DefaultWithinMinutes
                if x < 0:
                    x = CRTSPC_DefaultWithinMinutes
                return x
        return CRTSPC_DefaultWithinMinutes
    except:
        return CRTSPC_DefaultWithinMinutes
# ---- On-day timing existence (on-time resilience) ----

def CRTSPC_HasAnyTimingToday(reportingNumber, dayName):
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

# ---- ECS detector ----
CRTSPC_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]


def CRTSPC_ReadExtraEcsTerms():
    """Read extra ECS terms from TASSetup setting or legacy memory (split on ';' or ',')."""
    try:
        raw = None
        try:
            raw = TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem.getValue() if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem is not None else None
        except:
            raw = None
        if not raw:
            raw = CRTSPC_EcsFilterMem.getValue() if CRTSPC_EcsFilterMem is not None else None
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
def CRTSPC_IsEcsWorking(row):
    rn = ((row.get("Reporting number", "") or "")).strip().upper()
    if rn.startswith("5"):
        return True
    dest = ((row.get("Destination", "") or "")).strip().upper()
    call = ((row.get("Calling pattern", "") or "")).strip().upper()
    terms = set([t.upper() for t in CRTSPC_DefaultEcsTerms])
    for extra in CRTSPC_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " " + call
    for t in terms:
        if t and t in hay:
            return True
    return False

# ---- Word packing: fit as many names as possible on each line ----

def CRTSPC_PackNamesIntoLines(names, fm, maxW):
    lines = []
    cur = ""
    for nm in names:
        nm = (nm or "").strip()
        if not nm:
            continue
        if not cur:
            cur = nm
            continue
        cand = cur + ", " + nm
        if fm.stringWidth(cand) <= maxW:
            cur = cand
        else:
            lines.append(cur)
            cur = nm
    if cur:
        lines.append(cur)
    if not lines:
        lines = [""]
    return lines



# Wrap a block of text into lines that fit within maxW, splitting on spaces.
def CRTSPC_WrapTextToLines(text, fm, maxW):
    words = [w for w in str(text or "").split() if w]
    if not words:
        return [""]
    lines = []
    cur = ""
    for w in words:
        cand = w if not cur else (cur + " " + w)
        if not cur:
            cur = w
            continue
        if fm.stringWidth(cand) <= maxW:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
# ====== Panels ======

class CRTSPC_CabinetPanel(swing.JPanel):
    def __init__(self):
        super(CRTSPC_CabinetPanel, self).__init__()
        self.setOpaque(False)
        self.setLayout(None)

    def paintComponent(self, g):
        super(CRTSPC_CabinetPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        W = self.getWidth()
        H = self.getHeight()
        g2.setColor(Color.BLACK)
        g2.fillRect(0, 0, W, H)
        gp = GradientPaint(0, 0, CRTSPC_CabinetYellow, 0, H, CRTSPC_CabinetShade)
        g2.setPaint(gp)
        g2.fillRoundRect(0, 0, W, H, 20, 20)
        g2.setColor(CRTSPC_CabinetEdge)
        g2.setStroke(BasicStroke(5.5))
        g2.drawRoundRect(2, 2, W - 4, H - 4, 20, 20)


class CRTSPC_InnerCasingPanel(swing.JPanel):
    """Inner black casing with a header band saying 'Next train'."""
    def __init__(self):
        super(CRTSPC_InnerCasingPanel, self).__init__()
        self.setOpaque(False)
        self.setLayout(None)

    def paintComponent(self, g):
        super(CRTSPC_InnerCasingPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth()
        H = self.getHeight()
        g2.setColor(CRTSPC_InnerBlack)
        g2.fillRoundRect(0, 0, W, H, 16, 16)

        # Header band
        headerH = int(CRTSPC_HeaderHeight)
        bandY = 8
        bandH = max(1, headerH - 8)
        g2.fillRoundRect(8, bandY, W - 16, bandH, 12, 12)

        textStr = u"Next train"
        padX = 22
        maxW = W - 2 * padX
        maxH = int(bandH * 0.72)
        chosen = None
        for size in range(CRTSPC_CabinetSzMax, CRTSPC_CabinetSzMin - 1, -1):
            f = Font(CRTSPC_RailAlpha, Font.PLAIN, size)
            fm = g2.getFontMetrics(f)
            if fm.stringWidth(textStr) <= maxW and fm.getHeight() <= maxH:
                chosen = (f, fm)
                break
        if chosen is None:
            f = Font(CRTSPC_RailAlpha, Font.PLAIN, CRTSPC_CabinetSzMin)
            fm = g2.getFontMetrics(f)
        else:
            f, fm = chosen
        g2.setFont(f)
        g2.setColor(CRTSPC_TextWhite)
        x = (W - fm.stringWidth(textStr)) // 2
        y = bandY + (bandH - fm.getHeight()) // 2 + fm.getAscent()
        g2.drawString(textStr, x, y)


class CRTSPC_CRTPanel(swing.JPanel):
    def __init__(self, inset):
        super(CRTSPC_CRTPanel, self).__init__()
        self.inset = inset
        self.setOpaque(False)

    def paintComponent(self, g):
        super(CRTSPC_CRTPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth()
        H = self.getHeight()
        g2.setColor(CRTSPC_CrtBorder)
        g2.fillRoundRect(0, 0, W, H, 18, 18)
        inset = self.inset
        x0 = inset
        y0 = inset
        innerW = W - 2 * inset
        innerH = H - 2 * inset
        gp = GradientPaint(0, y0, CRTSPC_CrtBg, 0, y0 + innerH, CRTSPC_CrtGlow)
        g2.setPaint(gp)
        g2.fillRoundRect(x0, y0, innerW, innerH, 16, 16)
        g2.setColor(Color(CRTSPC_CrtScan.getRed(), CRTSPC_CrtScan.getGreen(), CRTSPC_CrtScan.getBlue(), CRTSPC_ScanlineAlpha))
        for y in range(y0 + 1, y0 + innerH - 1, 2):
            g2.drawLine(x0 + 8, y, x0 + innerW - 8, y)


class CRTSPC_ScreenPanel(swing.JPanel):
    def __init__(self, owner):
        super(CRTSPC_ScreenPanel, self).__init__()
        self.owner = owner
        self.setOpaque(False)

    def _fitFont(self, g2, fam, minSz, maxSz, sampleText, maxW, maxH):
        for size in range(maxSz, minSz - 1, -1):
            f = Font(fam, Font.BOLD, size)
            fm = g2.getFontMetrics(f)
            if fm.stringWidth(sampleText) <= maxW and (fm.getAscent() + fm.getDescent()) <= maxH:
                return f, fm
        f = Font(fam, Font.BOLD, minSz)
        return f, g2.getFontMetrics(f)

    def _rowPitch(self, g2, f, fm, availH, rowsToDraw):
        # Normalize row pitch across fonts similarly to the summary PID.
        baseLineH = fm.getAscent() + fm.getDescent()
        refBaseLineH = baseLineH
        try:
            env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
            fams = set(env.getAvailableFontFamilyNames())
            for fam in CRTSPC_RowPitchRefFamilies:
                if fam in fams:
                    tf = Font(fam, Font.BOLD, f.getSize())
                    tfm = g2.getFontMetrics(tf)
                    refBaseLineH = max(refBaseLineH, tfm.getAscent() + tfm.getDescent())
        except:
            pass
        desiredGap = max(int(CRTSPC_MinRowGapPx), int(round(f.getSize() * CRTSPC_RowGapFactor)))
        rowPitch = refBaseLineH + desiredGap
        maxPitch = baseLineH
        if rowsToDraw > 0:
            try:
                maxPitch = max(baseLineH, availH // rowsToDraw)
            except:
                maxPitch = baseLineH
        if rowPitch > maxPitch:
            rowPitch = maxPitch
        return rowPitch

    def paintComponent(self, g):
        super(CRTSPC_ScreenPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)

        W = self.getWidth()
        H = self.getHeight()
        if W <= 0 or H <= 0:
            return

        xL = CRTSPC_PadX
        xR = W - CRTSPC_PadX
        yT = CRTSPC_PadY
        yB = H - CRTSPC_PadY
        usableW = max(0, xR - xL)
        usableH = max(0, yB - yT)

        midH = int(round(usableH * CRTSPC_MiddleFrac))
        rem = max(0, usableH - midH)
        topH = rem // 2
        botH = rem - topH

        yTopEnd = yT + topH
        yMidEnd = yTopEnd + midH

        # Separator lines
        g2.setColor(CRTSPC_TextWhite)
        g2.setStroke(BasicStroke(1.0))
        g2.drawLine(xL, yTopEnd, xR, yTopEnd)
        g2.drawLine(xL, yMidEnd, xR, yMidEnd)

        train = self.owner.currentTrain
        platform = self.owner.platform

        # Main font (middle + footer)
        mainBoxH = int(round(min(topH, botH) * 0.45)) if min(topH, botH) > 0 else 12
        mainFont, mainFm = self._fitFont(g2, CRTSPC_MonoFamily, CRTSPC_MainSzMin, CRTSPC_MainSzMax,
                                         "Expected 2359", usableW, max(12, mainBoxH))
        mainPitch = self._rowPitch(g2, mainFont, mainFm, midH, 12)

        # Header font (larger)
        headerFont, headerFm = self._fitFont(g2, CRTSPC_MonoFamily, CRTSPC_HeaderSzMin, CRTSPC_HeaderSzMax,
                                             "2359", usableW // 2, max(12, topH // 2))

        # ---- Top section: two rows, two columns ----
        # Split into two equal rows.
        # ---- Top section ----
        tRowH = max(1, topH // 2)
        # Row baselines
        y1 = yT + headerFm.getAscent()
        y2 = yT + tRowH + headerFm.getAscent()

        # Left/right split
        halfW = usableW // 2
        leftX = xL
        rightX = xL + halfW
        rightW = usableW - halfW

        # Row 1: due time (left) and status (right)
        g2.setFont(headerFont)

        dueText = ""
        statusText = ""
        statusColor = CRTSPC_TextWhite
        cancelledStatus = False

        if train is not None:
            dueText = CRTSPC_FormatHHmm(train.get("time") or "")
            if train.get("cancelled", False):
                statusText = "CANCELLED"
                statusColor = CRTSPC_CancelText
                cancelledStatus = True
            else:
                expMin = train.get("expMin")
                if expMin is not None:
                    statusText = CRTSPC_MinutesToHHmm(expMin)
                    statusColor = CRTSPC_TextYellow
                else:
                    statusText = "On time"
                    statusColor = CRTSPC_TextWhite

        g2.setColor(CRTSPC_TextWhite)
        g2.drawString(dueText, leftX, y1)
        if cancelledStatus and statusText:
            # Draw a cyan background behind CANCELLED and render the text in black.
            sw = headerFm.stringWidth(statusText)
            pad = 4
            xText = rightX + max(0, rightW - sw)
            yTop = y1 - headerFm.getAscent()
            hBox = headerFm.getAscent() + headerFm.getDescent()
            g2.setColor(CRTSPC_CancelBg)
            g2.fillRect(xText - pad, yTop, sw + (2 * pad), hBox)
            g2.setColor(CRTSPC_CancelText)
            g2.drawString(statusText, xText, y1)
        else:
            g2.setColor(statusColor)
            sw = headerFm.stringWidth(statusText)
            g2.drawString(statusText, rightX + max(0, rightW - sw), y1)

        # Row 2: destination (left) and Plat x (right)
        destText = ""
        platText = ""
        if train is not None:
            destText = (train.get("dest") or "").upper().strip()
            platText = "Plat " + str(platform)

        # Destination in upper row is white (requested).
        g2.setColor(CRTSPC_TextWhite)
        g2.drawString(destText, leftX, y2)

        g2.setColor(CRTSPC_TextWhite)
        pw = headerFm.stringWidth(platText)
        g2.drawString(platText, rightX + max(0, rightW - pw), y2)

        # ---- Middle section ----
        midY0 = yTopEnd + 1
        midY1 = yMidEnd - 1

        g2.setFont(mainFont)
        g2.setColor(CRTSPC_TextWhite)

        callGap = int(round(mainPitch * CRTSPC_CallAtGapFactor))
        if train is None:

            # No train: show an information message in place of the calling list.

            msg = str(CRTSPC_NoTrainMessage or "").strip()

            g2.setColor(CRTSPC_TextWhite)

            maxLineW = int(usableW * 0.98)

            msgLines = CRTSPC_WrapTextToLines(msg, mainFm, maxLineW)

            midUsableH = max(0, midY1 - midY0)

            baseH = mainFm.getAscent() + mainFm.getDescent()

            if mainPitch > 0:

                maxLines = 1 + max(0, (midUsableH - baseH) // mainPitch)

            else:

                maxLines = 1

            if maxLines < 1:

                maxLines = 1

            if len(msgLines) > maxLines:

                msgLines = msgLines[:maxLines]

            blockH = baseH + (max(0, len(msgLines) - 1) * mainPitch)

            y = midY0 + max(0, (midUsableH - blockH) // 2) + mainFm.getAscent()

            for ln in msgLines:

                if y > (midY1 - 1):

                    break

                g2.drawString(ln, xL, y)

                y += mainPitch

            # Set paging defaults for footer.
            totalPages = 1
            pageIndex = 0
        else:
            callLabel = "Calling at:"
            callLabel = "Calling at:"
            callLabelY = midY0 + callGap + mainFm.getAscent()
            if callLabelY > (midY1 - 1):
                callLabelY = midY0 + mainFm.getAscent()
            g2.drawString(callLabel, xL, callLabelY)

            # Available area for calling lines
            callLinesY0 = callLabelY + mainPitch
            callLinesH = max(0, midY1 - callLinesY0)

            # Determine how many lines fit per page (at least 1)
            linesPerPage = 1
            if mainPitch > 0:
                linesPerPage = max(1, callLinesH // mainPitch)

            callingLines = [""]
            totalPages = 1
            pageIndex = 0

            if train is not None:
                callingText = (train.get("calling") or "").strip()
                destUpper = (train.get("dest") or "").strip().upper()
                raw = [x.strip() for x in callingText.split(",") if x.strip()]
                # Ensure destination included
                if destUpper:
                    if (not raw) or (raw[-1].strip().upper() != destUpper):
                        raw.append(destUpper)

                # Preserve case from calling pattern, but force destination uppercase.
                formatted = []
                for nm in raw:
                    nmStr = (nm or "").strip()
                    if destUpper and nmStr.upper() == destUpper:
                        formatted.append(destUpper)
                    else:
                        formatted.append(nmStr)

                maxLineW = int(usableW * 0.98)
                callingLines = CRTSPC_PackNamesIntoLines(formatted, mainFm, maxLineW)

                totalPages = (len(callingLines) + linesPerPage - 1) // linesPerPage if linesPerPage > 0 else 1
                if totalPages < 1:
                    totalPages = 1

                if totalPages > 1:
                    # Page index cycles based on wall-clock milliseconds.
                    try:
                        ps = int(str(CRTSPC_PageSecondsMem.getValue() or "5").strip())
                    except:
                        ps = 5
                    if ps <= 0:
                        ps = 5
                    pageIndex = int((System.currentTimeMillis() // (ps * 1000)) % totalPages)
                else:
                    pageIndex = 0

            # Draw calling lines for the current page
            g2.setColor(CRTSPC_TextYellow)
            startIdx = pageIndex * linesPerPage
            endIdx = min(len(callingLines), startIdx + linesPerPage)
            y = callLinesY0 + mainFm.getAscent()
            for i in range(startIdx, endIdx):
                g2.drawString(callingLines[i], xL, y)
                y += mainPitch

            # Special text (white) after calling pattern with one blank line.
            if train is not None:
                sp = str(train.get("special") or "").strip()
            else:
                sp = ""
            if sp:
                y += mainPitch
                if y <= (midY1 - 1):
                    g2.setColor(CRTSPC_TextWhite)
                    maxW = int(usableW * 0.98)
                    if mainFm.stringWidth(sp) > maxW:
                        ell = "..."
                        t = sp
                        while t and (mainFm.stringWidth(t + ell) > maxW):
                            t = t[:-1]
                        sp = (t + ell) if t else ell
                    g2.drawString(sp, xL, y)

            # ---- Footer ----
        botY0 = yMidEnd + 1
        botY1 = yB
        botUsableH = max(0, botY1 - botY0)

        g2.setFont(mainFont)

        fRowH = max(1, botUsableH // 2)
        fY1 = botY0 + mainFm.getAscent()
        fY2 = botY0 + fRowH + mainFm.getAscent()

        pageText = "Page %d of %d" % (pageIndex + 1, totalPages)
        g2.setColor(CRTSPC_TextWhite)
        pw = mainFm.stringWidth(pageText)
        g2.drawString(pageText, xL + max(0, usableW - pw), fY1)

        company = ""
        if train is not None:
            try:
                company = str(train.get("company") or "").strip()
            except:
                company = ""
            if not company:
                try:
                    company = str(CRTSPC_CompanyMem.getValue() or "").strip()
                except:
                    company = ""

        nowStr = CRTSPC_FmtHMS.format(CRTSPC_NowDate())

        g2.setColor(CRTSPC_TextWhite)
        if company:
            g2.drawString(company, xL, fY2)

        g2.setColor(CRTSPC_TextYellow)
        tw = mainFm.stringWidth(nowStr)
        g2.drawString(nowStr, xL + max(0, usableW - tw), fY2)


# ====== Listeners ======

class CRTSPC_PropertyListener(PropertyChangeListener):
    def __init__(self, owner):
        self.owner = owner

    def propertyChange(self, e):
        # Forward to owner.refresh(e) when available; otherwise to owner.propertyChange(e).
        try:
            fn = getattr(self.owner, 'refresh', None)
            if fn is not None:
                fn(e)
                return
        except:
            pass
        try:
            fn2 = getattr(self.owner, 'propertyChange', None)
            if fn2 is not None:
                fn2(e)
        except:
            pass


class CRTSPC_WindowCloseHandler(WindowAdapter):
    def __init__(self, owner):
        self.owner = owner

    def windowClosing(self, e):
        try:
            self.owner.cleanup()
        finally:
            try:
                self.owner.frame.dispose()
            except:
                pass


class CRTSPC_RepaintTick(ActionListener):
    def __init__(self, owner):
        self.owner = owner

    def actionPerformed(self, e):
        try:
            # Refresh selection on every tick so time warps and fast-clock changes take effect.
            self.owner.refresh()
        except:
            pass


# ====== Main window per platform ======

class CRTSPC_PlatformWindow(object):
    def __init__(self, platform, OnCloseCallback=None):
        self.platform = str(platform)
        self.OnCloseCallback = OnCloseCallback
        self.currentTrain = None

        # Fixed sizes to match the colour summary window.
        cabW = CRTSPC_FixedCabinetWidth
        cabH = CRTSPC_FixedCabinetHeight

        innerW = cabW - 2 * CRTSPC_InnerPad
        innerH = cabH - 2 * CRTSPC_InnerPad

        crtPanelW = innerW - 2 * CRTSPC_SideMargin
        crtPanelH = innerH - CRTSPC_HeaderHeight - CRTSPC_TopMargin - CRTSPC_BottomMargin

        frameW = cabW + 2 * CRTSPC_FramePad
        frameH = cabH + 2 * CRTSPC_FramePad

        self.frame = swing.JFrame("Passenger information display: platform " + self.platform)
        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setPreferredSize(Dimension(frameW, frameH))
        cp.setBackground(Color.BLACK)

        self.cab = CRTSPC_CabinetPanel()
        self.cab.setBounds(CRTSPC_FramePad, CRTSPC_FramePad, cabW, cabH)
        self.cab.setLayout(None)
        cp.add(self.cab)

        self.inner = CRTSPC_InnerCasingPanel()
        self.inner.setBounds(CRTSPC_InnerPad, CRTSPC_InnerPad, innerW, innerH)
        self.inner.setLayout(None)
        self.cab.add(self.inner)

        self.crt = CRTSPC_CRTPanel(CRTSPC_BezelInset)
        self.crt.setBounds(CRTSPC_SideMargin, CRTSPC_HeaderHeight + CRTSPC_TopMargin, crtPanelW, crtPanelH)
        self.crt.setLayout(None)
        self.inner.add(self.crt)

        # Screen content panel fills the glass
        self.screen = CRTSPC_ScreenPanel(self)
        self.screen.setBounds(CRTSPC_BezelInset, CRTSPC_BezelInset, crtPanelW - 2 * CRTSPC_BezelInset, crtPanelH - 2 * CRTSPC_BezelInset)
        self.crt.add(self.screen)

        # Listeners
        self._pcl = CRTSPC_PropertyListener(self)
        CRTSPC_TimeMem.addPropertyChangeListener(self._pcl)
        CRTSPC_DayMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_TimetableMem is not None:
            CRTSPC_TimetableMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_OverridesMem is not None:
            CRTSPC_OverridesMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_DepartTPMem is not None:
            CRTSPC_DepartTPMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_WithInMinMem is not None:
            CRTSPC_WithInMinMem.addPropertyChangeListener(self._pcl)
        if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_Mem is not None:
            TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_Mem.addPropertyChangeListener(self._pcl)
        if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_WITHIN_MINUTES_LegacyMem is not None:
            TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_WITHIN_MINUTES_LegacyMem.addPropertyChangeListener(self._pcl)
        if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem is not None:
            TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem.addPropertyChangeListener(self._pcl)
        if CRTSPC_EcsFilterMem is not None:
            CRTSPC_EcsFilterMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_PageSecondsMem is not None:
            CRTSPC_PageSecondsMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_CompanyMem is not None:
            CRTSPC_CompanyMem.addPropertyChangeListener(self._pcl)

        # Also refresh on platform allocation changes
        try:
            PAR.addPlatformListener(self._pcl)
        except:
            pass

        self._windowCloser = CRTSPC_WindowCloseHandler(self)
        self.frame.setDefaultCloseOperation(swing.JFrame.DO_NOTHING_ON_CLOSE)
        self.frame.addWindowListener(self._windowCloser)

        self.frame.pack()
        self.frame.setResizable(False)

        # Window icon
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)
        except:
            pass

        # Repaint timer for clock/paging
        self._tick = CRTSPC_RepaintTick(self)
        self._timer = Timer(1000, self._tick)
        self._timer.setRepeats(True)
        self._timer.start()

        self.refresh()
        self.frame.setVisible(True)

    def cleanup(self):
        try:
            if self._timer is not None:
                self._timer.stop()
        except:
            pass
        try:
            pcl = getattr(self, "_pcl", None)
        except:
            pcl = None
        if pcl is not None:
            try:
                CRTSPC_TimeMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                CRTSPC_DayMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_TimetableMem is not None:
                    CRTSPC_TimetableMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_OverridesMem is not None:
                    CRTSPC_OverridesMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_DepartTPMem is not None:
                    CRTSPC_DepartTPMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_WithInMinMem is not None:
                    CRTSPC_WithInMinMem.removePropertyChangeListener(pcl)
                if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_Mem is not None:
                    TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_DUE_WINDOW_MINUTES_Mem.removePropertyChangeListener(pcl)
                if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_WITHIN_MINUTES_LegacyMem is not None:
                    TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_WITHIN_MINUTES_LegacyMem.removePropertyChangeListener(pcl)
                if TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem is not None:
                    TAS_USER_SETTING_COLOUR_CRT_PLATFORM_DISPLAY_ECS_FILTER_TERMS_Mem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_EcsFilterMem is not None:
                    CRTSPC_EcsFilterMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_PageSecondsMem is not None:
                    CRTSPC_PageSecondsMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_CompanyMem is not None:
                    CRTSPC_CompanyMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                PAR.removePlatformListener(pcl)
            except:
                pass

        try:
            wc = getattr(self, "_windowCloser", None)
        except:
            wc = None
        if wc is not None:
            try:
                self.frame.removeWindowListener(wc)
            except:
                pass

        try:
            if self.OnCloseCallback is not None:
                self.OnCloseCallback(self.platform, self)
        except:
            pass

    # ---- Selection logic (ported from PIDCRTSingle.py) ----
    def pick_next_train(self):
        rows = CRTSPC_CsvRows()
        curDay = CRTSPC_DayMem.getValue() or ""

        # 'Now' minutes
        if CRTSPC_Timebase is not None:
            ft = CRTSPC_Timebase.getTime()
            curMin = ft.getHours() * 60 + ft.getMinutes()
        else:
            curStr = CRTSPC_TimeMem.getValue() or ""
            curMin = CRTSPC_ParseMinutes(curStr)
        if curMin is None:
            return None

        todays = [r for r in rows if ((r.get(curDay, "") or "").strip().lower() == "true")]

        # child RN -> former rows
        formers_map = {}
        for r in todays:
            child = (r.get("Forms", "") or "").strip()
            if child:
                formers_map.setdefault(child, []).append(r)

        def resolve_delay(rn, sched_dep_min, visited=None):
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
            formers = formers_map.get(rn, [])
            if not formers:
                return ("ontime", 0)
            chosen = None
            if sched_dep_min is not None:
                before = []
                for fr in formers:
                    arr = (fr.get("Arr", "") or "").strip()
                    arrMin = CRTSPC_ParseMinutes(arr) if arr else None
                    if arrMin is not None and arrMin <= sched_dep_min:
                        before.append((arrMin, fr))
                if before:
                    before.sort(key=lambda t: t[0])
                    chosen = before[-1][1]
            if chosen is None:
                chosen = formers[0]
            former_rn = (chosen.get("Reporting number", "") or "").strip()
            return resolve_delay(former_rn, sched_dep_min, visited)

        within = CRTSPC_ReadWithinMinutes()
        cands = []

        for row in todays:
            dep = (row.get("Dep", "") or "").strip()
            if not dep:
                continue
            rn = (row.get("Reporting number", "") or "").strip()

            # Skip ECS/empty-to-depot
            if CRTSPC_IsEcsWorking(row):
                continue

            # Platform precedence: allocation register > overrides > timetable
            alloc = PAR.getPlatform(rn)
            if alloc is not None and str(alloc).strip():
                plat = str(alloc).strip()
            else:
                plat = CRTSPC_GetOverride(rn) or CRTSPC_PlatformField(row)
            if str(plat) != self.platform:
                continue

            depMin = CRTSPC_ParseMinutes(dep)
            if depMin is None:
                continue

            destText = (row.get("Destination", "") or "").strip()
            callingText = (CRTSPC_GetFieldCI(row, "Calling pattern") or "").strip()
            companyText = (CRTSPC_GetFieldCI(row, "Company") or "").strip()
            specialText = (CRTSPC_GetFieldCI(row, "Special") or "").strip()

            # Resolve disruption (direct first, else inherited)
            try:
                d = getDisruption(rn)
            except:
                d = None

            kind = "ontime"
            val = 0
            cancelled = False

            if d is not None:
                try:
                    dd = int(d)
                except:
                    dd = 0
                if dd >= 1440:
                    kind = "cancel"
                    cancelled = True
                elif dd > 0:
                    kind = "delay"
                    val = dd
                else:
                    kind, val = resolve_delay(rn, depMin)
            else:
                kind, val = resolve_delay(rn, depMin)

            if kind == "cancel":
                cancelled = True

            expMin = (depMin + val) % (24 * 60) if (kind == "delay" and val and val > 0) else None

            # Clear if logged departed
            if (not cancelled) and CRTSPC_HasDepartedAtConfiguredTP(rn, curDay, curMin):
                continue

            # Keep visible until expected time (or scheduled if on time/cancel)
            if cancelled:
                if depMin < curMin:
                    continue
            elif expMin is not None:
                if expMin < curMin:
                    continue
            else:
                # On-time resilience: if no disruption and no timing anywhere today for this RN,
                # hide only if booked Dep < now; otherwise keep until actually logged departed.
                try:
                    direct = getDisruption(rn)
                except:
                    direct = None
                if (direct is None) and (not CRTSPC_HasAnyTimingToday(rn, curDay)):
                    if depMin < curMin:
                        continue

            adjusted = expMin if expMin is not None else depMin

            # Due-within-X constraint
            delta = (adjusted - curMin) % (24 * 60)
            if within == 0 or delta == 0 or (within >= 0 and 0 <= delta <= within):
                cands.append({
                    "rn": rn,
                    "time": dep,
                    "depMin": depMin,
                    "adjMin": adjusted,
                    "expMin": expMin,
                    "dest": destText,
                    "calling": callingText,
                    "company": companyText,
                    "special": specialText,
                    "cancelled": cancelled
                })

        if not cands:
            return None
        cands.sort(key=lambda t: t["adjMin"])
        return cands[0]

    def refresh(self, e=None):
        self.currentTrain = self.pick_next_train()
        try:
            self.screen.repaint()
        except:
            pass


# ====== Manager: create one window per platform found in timetable ======

class CRTSPC_PlatformManager(object):
    def __init__(self):
        self.windows = {}

        # Listen for timetable/override/TP changes to rebuild/refresh
        self._pcl = CRTSPC_PropertyListener(self)
        if CRTSPC_TimetableMem is not None:
            CRTSPC_TimetableMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_OverridesMem is not None:
            CRTSPC_OverridesMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_DepartTPMem is not None:
            CRTSPC_DepartTPMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_WithInMinMem is not None:
            CRTSPC_WithInMinMem.addPropertyChangeListener(self._pcl)
        if CRTSPC_EcsFilterMem is not None:
            CRTSPC_EcsFilterMem.addPropertyChangeListener(self._pcl)

        self.build()
        self.refresh_all()

    def propertyChange(self, e):
        # Rebuild if timetable might have changed; always refresh.
        try:
            if getattr(self, '_stopped', False):
                return
        except:
            pass
        self.build()
        self.refresh_all()

    def unregister(self, platform, windowObj):
        try:
            p = str(platform)
        except:
            p = platform
        try:
            if p in self.windows and self.windows.get(p) is windowObj:
                del self.windows[p]
        except:
            pass

    
        # If all windows are closed, stop the manager and remove its listeners.
        try:
            if not self.windows:
                self.cleanup()
        except:
            pass

    def build(self):
        plats = set()
        for r in CRTSPC_CsvRows():
            p = CRTSPC_PlatformField(r)
            if p:
                plats.add(p)

        # Create missing
        for p in sorted(list(plats)):
            if p not in self.windows:
                self.windows[p] = CRTSPC_PlatformWindow(p, self.unregister)

        # Remove stale
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

        # Cascade positions a little
        x0, y0, dx, dy = 40, 40, 16, 16
        for i, p in enumerate(sorted(list(self.windows.keys()))):
            try:
                self.windows[p].frame.setLocation(x0 + dx * i, y0 + dy * i)
            except:
                pass

    def refresh_all(self):
        for w in list(self.windows.values()):
            try:
                w.refresh()
            except:
                pass



    def cleanup(self):
        # Stop the manager once all windows are closed.
        try:
            self._stopped = True
        except:
            pass
        try:
            pcl = getattr(self, '_pcl', None)
        except:
            pcl = None
        if pcl is not None:
            try:
                if CRTSPC_TimetableMem is not None:
                    CRTSPC_TimetableMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_OverridesMem is not None:
                    CRTSPC_OverridesMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_DepartTPMem is not None:
                    CRTSPC_DepartTPMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_WithInMinMem is not None:
                    CRTSPC_WithInMinMem.removePropertyChangeListener(pcl)
            except:
                pass
            try:
                if CRTSPC_EcsFilterMem is not None:
                    CRTSPC_EcsFilterMem.removePropertyChangeListener(pcl)
            except:
                pass
        try:
            self._pcl = None
        except:
            pass
        try:
            global CRTSPC_Manager
            CRTSPC_Manager = None
        except:
            pass
# ----- Run -----
CRTSPC_Manager = CRTSPC_PlatformManager()
