# -*- coding: utf-8 -*-

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
# JMRI 5.12 — 1970s/90s monochrome CRT PID (per-platform)
# Uniformly scaled; disruption inheritance; expected HHMM; keep late service until expected time.
#
# Clears the shown train once a departure is logged at configured timing point(s).
# Only show a train if due within X minutes (IMPID_CRT_WITHIN_MINUTES; default 5).
# NEW: Hide ECS/empty-to-depot workings (class-5 or keyword-matched; keywords configurable via IMPID_ECS_FILTER_TERMS).
# 
# <<PID-DISP-NAME: Monochrome CRT platform display>>
# <<DESCRIPTION: British Rail 1980s monitors showing the next train's time, destination and calling patterm per platform>>

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, GradientPaint, RenderingHints, BasicStroke, Dimension
import jmri
from jmri import InstanceManager
import os, csv
import java.text.SimpleDateFormat as SimpleDateFormat
from DisruptionRegister import getDisruption
import TimingRegister as TR  # read-only access to timing tuples (reportingNumber, direction, time, day)
import TASBeanLookup as TBL

# =============================================================================
# UNIFORM SCALING — keep everything strictly proportional to your current design
# =============================================================================
CRTS_TargetGlassWidth = 640.0  # matches your CRT summary

# ---- BASE (from the original full-size CRT single) ----
CRTS_BaseGlassWidth = 820.0
CRTS_BaseHeaderHeight = 170.0
CRTS_BaseInnerPad = 22.0
CRTS_BaseFramePad = 8.0
CRTS_BaseCrtBezelInset = 5.0
CRTS_BaseSideMargin = 10.0
CRTS_BaseTopMargin = 10.0
CRTS_BaseBottomMargin = 10.0
CRTS_BaseRuleOffset = 14.0
CRTS_BasePlatGap = 12.0
CRTS_BaseStrokeEdge = 6.5
CRTS_BaseCallTopPad = 2.0
CRTS_BaseCallBottomPad = 2.0

# Font search ranges (scaled; still auto-fit to boxes)
CRTS_BaseTimeFontMin = 28
CRTS_BaseTimeFontMax = 148
CRTS_BaseDestFontMin = 28
CRTS_BaseDestFontMax = 160
CRTS_BaseCallFontMin = 18
CRTS_BaseCallFontMax = 26

# Compute scale
CRTS_Scale = CRTS_TargetGlassWidth / CRTS_BaseGlassWidth

def CRTS_S(v, minimum=1):
    # Scale helper -> int px (with a sensible min).
    val = int(round(v * CRTS_Scale))
    return max(minimum, val)

CRTS_CrtGlassWidth = int(round(CRTS_TargetGlassWidth))
CRTS_HeaderHeight = CRTS_S(CRTS_BaseHeaderHeight)
CRTS_InnerPad = CRTS_S(CRTS_BaseInnerPad)
CRTS_FramePad = CRTS_S(CRTS_BaseFramePad)
CRTS_CrtBezelInset = CRTS_S(CRTS_BaseCrtBezelInset)
CRTS_SideMargin = CRTS_S(CRTS_BaseSideMargin)
CRTS_TopMargin = CRTS_S(CRTS_BaseTopMargin)
CRTS_BottomMargin = CRTS_S(CRTS_BaseBottomMargin)
CRTS_RuleOffsetPx = CRTS_S(CRTS_BaseRuleOffset)
CRTS_PlatExtraGap = CRTS_S(CRTS_BasePlatGap)
CRTS_StrokeEdge = max(2, int(round(CRTS_BaseStrokeEdge * CRTS_Scale)))
CRTS_CallTopPad = CRTS_S(CRTS_BaseCallTopPad)
CRTS_CallBottomPad = CRTS_S(CRTS_BaseCallBottomPad)

CRTS_TimeFontMin = max(12, int(round(CRTS_BaseTimeFontMin * CRTS_Scale)))
CRTS_TimeFontMax = max(CRTS_TimeFontMin + 8, int(round(CRTS_BaseTimeFontMax * CRTS_Scale)))
CRTS_DestFontMin = max(12, int(round(CRTS_BaseDestFontMin * CRTS_Scale)))
CRTS_DestFontMax = max(CRTS_DestFontMin + 8, int(round(CRTS_BaseDestFontMax * CRTS_Scale)))
CRTS_CallFontMin = max(10, int(round(CRTS_BaseCallFontMin * CRTS_Scale)))
CRTS_CallFontMax = max(CRTS_CallFontMin + 4, int(round(CRTS_BaseCallFontMax * CRTS_Scale)))

# ---- colours (unchanged) ----
CRTS_CabinetOrange = Color(232, 110, 20)
CRTS_CabinetShade = Color(160, 70, 10)
CRTS_CabinetEdge = Color(60, 30, 0)
CRTS_InnerBlack = Color(10, 10, 10)
CRTS_LegendText = Color(230, 230, 230)
CRTS_RuleGrey = Color(130, 130, 130)
CRTS_CrtBorder = Color(22,22,24)
CRTS_CrtBg = Color(8,10,12)
CRTS_CrtGlow = Color(18,26,32)
CRTS_CrtFore = Color(205,215,235)
CRTS_ScanlineAlpha = 14

# ---- fonts / families (unchanged) ----
CRTS_MonoCands = ["IBM Plex Mono","Consolas","Courier New","Nimbus Mono L","Lucida Console","Monospaced"]
CRTS_RailCands = ["BritishRailLightNormal","British Rail Light Normal","Rail Alphabet","RailAlphabet",
                  "Arial","Helvetica","SansSerif"]

def CRTS_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

CRTS_CrtMonoFamily = CRTS_PickFamily(CRTS_MonoCands)
CRTS_RailAlphaFamily = CRTS_PickFamily(CRTS_RailCands)

# ---- fit margins (unchanged) ----
CRTS_FitMarginW = 0.93
CRTS_FitMarginH = 0.90
CRTS_Days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
CRTS_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
CRTS_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
CRTS_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
CRTS_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")
CRTS_DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
CRTS_WithInMinMem = TBL.ProvideMemoryBySuffix("PID_CRT_WITHIN_MINUTES", "5")
CRTS_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")

# Optional authoritative fast clock
CRTS_Timebase = InstanceManager.getDefault(jmri.Timebase)

# -- Time helpers --
CRTS_TimeParser = SimpleDateFormat("h:mm a")
CRTS_AltParser = SimpleDateFormat("H:mm")
CRTS_FmtHHmm = SimpleDateFormat("HHmm")

def CRTS_ParseMinutes(s):
    for p in [CRTS_TimeParser, CRTS_AltParser]:
        try:
            d = p.parse(s)
            return d.getHours()*60 + d.getMinutes()
        except:
            pass
    return None

def CRTS_FormatHHmm(s):
    for p in [CRTS_TimeParser, CRTS_AltParser]:
        try:
            d = p.parse(s)
            return CRTS_FmtHHmm.format(d)
        except:
            pass
    return s.replace(":", "")

def CRTS_MinutesToHHmm(total):
    if total is None:
        return ""
    total = total % (24*60)
    h = total // 60
    m = total % 60
    return "%02d%02d" % (h, m)

# -- Timetable access --
def CRTS_TimetablePath():
    name = CRTS_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")

def CRTS_CsvRows():
    path = CRTS_TimetablePath()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []

def CRTS_PlatformField(row):
    return (row.get("Plat","") or row.get("Platform","") or "").strip()

def CRTS_ParseOverrides(s):
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

def CRTS_GetOverride(rn):
    try:
        return CRTS_ParseOverrides(CRTS_OverridesMem.getValue()).get(rn)
    except:
        return None

# ---------------------------------------------------------------------------
# Departure TP selection + logged-departure check (mirrors PIDSmall.py logic)
# ---------------------------------------------------------------------------
def CRTS_ActiveProfileBaseTPName():
    # Default 'Dep' timing point = active profile name (base TP).
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""

def CRTS_DepartureTPList():
    """
    Read IMPID_DEPARTURE_TP (single or ';' / ',' separated list).
    If absent/blank, fall back to base timing point (active profile name).
    """
    names = []
    try:
        raw = CRTS_DepartTPMem.getValue() if CRTS_DepartTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        base = CRTS_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names

def CRTS_HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    """
    True iff any configured departure timing point contains a tuple for (reportingNumber, dayName)
    whose logged time <= nowMinutes. TimingRegister tuples are (reportingNumber, direction, time, day).
    Any tuple here is a departure record. (Read-only; uses TR.getTiming(tp).)
    """
    tps = CRTS_DepartureTPList()
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
            mm = CRTS_ParseMinutes(tstr)
            if mm is None:
                continue
            if mm <= int(nowMinutes):
                return True
    return False

# ---- "Due within X minutes" window ----
CRTS_DefaultWithinMinutes = 5  # default when memory not set/invalid

def CRTS_ReadWithinMinutes():
    """Read X from IMPID_CRT_WITHIN_MINUTES; default to 5; clamp to sensible range."""
    try:
        val = CRTS_WithInMinMem.getValue() if CRTS_WithInMinMem is not None else None
        if val is None:
            return CRTS_DefaultWithinMinutes
        s = str(val).strip()
        if not s:
            return CRTS_DefaultWithinMinutes
        x = int(s)
        if x < 0:
            return CRTS_DefaultWithinMinutes
        return x
    except:
        return CRTS_DefaultWithinMinutes

# ---- NEW: ECS detector (class-5 or keyword heuristics) ----
CRTS_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]  # NEW

def CRTS_ReadExtraEcsTerms():
    """Read extra ECS terms from IMPID_ECS_FILTER_TERMS (split on ';' or ',')."""  # NEW
    try:
        raw = CRTS_EcsFilterMem.getValue() if CRTS_EcsFilterMem is not None else None
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

def CRTS_IsEcsWorking(row):
    """
    Return True if the row is an ECS/empty-to-depot working.
    Rules:
      1) Reporting number starts with '5'
      2) Destination or Calling pattern contains an ECS keyword (default + configurable extras)
    """  # NEW
    rn = ((row.get("Reporting number","") or "")).strip().upper()
    if rn.startswith("5"):
        return True
    dest = ((row.get("Destination","") or "")).strip().upper()
    call = ((row.get("Calling pattern","") or "")).strip().upper()
    terms = set([t.upper() for t in CRTS_DefaultEcsTerms])
    for extra in CRTS_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " | " + call
    for t in terms:
        if t and t in hay:
            return True
    return False

# ---- fit helpers ----
def CRTS_FitFontToBox(label, text, fam, minSize, maxSize, maxW, maxH):
    maxW = int(maxW * CRTS_FitMarginW)
    maxH = int(maxH * CRTS_FitMarginH)
    best = minSize
    for size in range(minSize, maxSize+1):
        f = Font(fam, Font.BOLD, size)
        fm = label.getFontMetrics(f)
        if fm.stringWidth(text) <= maxW and (fm.getAscent()+fm.getDescent()) <= maxH:
            best = size
        else:
            break
    label.setFont(Font(fam, Font.BOLD, best))
    label.setText(text)

def CRTS_ToCaps(s):
    return (s or "").upper()

# ---- panels ----
class CRTS_CabinetPanel(swing.JPanel):
    def __init__(self):
        super(CRTS_CabinetPanel, self).__init__()
        self.setOpaque(False)
        self.setLayout(None)
    def paintComponent(self, g):
        super(CRTS_CabinetPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        W = self.getWidth(); H = self.getHeight()
        g2.setColor(Color.BLACK); g2.fillRect(0,0,W,H)
        gp = GradientPaint(0,0,CRTS_CabinetOrange, 0,H,CRTS_CabinetShade)
        g2.setPaint(gp); g2.fillRoundRect(0,0,W,H,20,20)
        g2.setColor(CRTS_CabinetEdge); g2.setStroke(BasicStroke(float(CRTS_StrokeEdge)))
        g2.drawRoundRect(2,2,W-4,H-4,20,20)

class CRTS_InnerCasingPanel(swing.JPanel):
    def __init__(self, platformText, headerH):
        super(CRTS_InnerCasingPanel, self).__init__()
        self.platformText = platformText
        self.headerH = headerH
        self.setOpaque(False)
        self.setLayout(None)
    def setPlatformText(self, txt):
        self.platformText = txt
        self.repaint()
    def paintComponent(self, g):
        super(CRTS_InnerCasingPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth(); H = self.getHeight()
        g2.setColor(CRTS_InnerBlack); g2.fillRoundRect(0,0,W,H,16,16)
        # Header band
        g2.fillRoundRect(8,8, W-16, self.headerH, 12,12)
        padX = 22
        # Next train
        next_str = u"Next train"
        g2.setColor(CRTS_LegendText)
        for size in range(int(round(104*CRTS_Scale)), max(int(round(36*CRTS_Scale)),18), -1):
            f = Font(CRTS_RailAlphaFamily, Font.PLAIN, size)
            fm = g2.getFontMetrics(f)
            if fm.getHeight() <= self.headerH*0.60 and fm.stringWidth(next_str) <= (W-2*padX):
                g2.setFont(f)
                break
        fm = g2.getFontMetrics()
        next_y = 8 + int(self.headerH*0.40)
        g2.drawString(next_str, padX, next_y)
        # Rule
        g2.setColor(CRTS_RuleGrey)
        g2.drawLine(padX, next_y + CRTS_RuleOffsetPx, W - padX, next_y + CRTS_RuleOffsetPx)
        # Platform n
        plat_str = u"Platform " + self.platformText
        g2.setColor(CRTS_LegendText)
        for size in range(int(round(48*CRTS_Scale)), max(int(round(18*CRTS_Scale)),12), -1):
            f2 = Font(CRTS_RailAlphaFamily, Font.PLAIN, size)
            fm2= g2.getFontMetrics(f2)
            if fm2.stringWidth(plat_str) <= (W-2*padX):
                g2.setFont(f2)
                break
        fm2 = g2.getFontMetrics()
        plat_y = min(8 + self.headerH - 16, next_y + CRTS_RuleOffsetPx + CRTS_PlatExtraGap + fm2.getAscent())
        g2.drawString(plat_str, padX, plat_y)

class CRTS_CRTPanel(swing.JPanel):
    def __init__(self, inset):
        super(CRTS_CRTPanel, self).__init__()
        self.inset = inset
        self.setOpaque(False)
    def paintComponent(self, g):
        super(CRTS_CRTPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2 = g
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth(); H = self.getHeight()
        g2.setColor(CRTS_CrtBorder); g2.fillRoundRect(0,0,W,H,18,18)
        inset = self.inset
        x0 = inset; y0 = inset; innerW = W-2*inset; innerH = H-2*inset
        gp = GradientPaint(0,y0,CRTS_CrtBg, 0,y0+innerH, CRTS_CrtGlow)
        g2.setPaint(gp); g2.fillRoundRect(x0,y0,innerW,innerH,16,16)
        g2.setColor(Color(CRTS_CrtFore.getRed(), CRTS_CrtFore.getGreen(), CRTS_CrtFore.getBlue(), CRTS_ScanlineAlpha))
        y = y0 + 1
        while y < y0 + innerH - 1:
            g2.drawLine(x0+8, y, x0+innerW-8, y)
            y += 2

# ---- main window ----
class CRTS_CRTPIDWindow(object):
    def __init__(self, platform):
        self.platform = str(platform)

        # Compute sizes from 4:3 glass
        glassW = CRTS_CrtGlassWidth
        glassH = int(round(glassW * 3.0/4.0))
        crtPanelW = glassW + 2*CRTS_CrtBezelInset
        crtPanelH = glassH + 2*CRTS_CrtBezelInset
        innerW = 2*CRTS_SideMargin + crtPanelW
        innerH = CRTS_HeaderHeight + CRTS_TopMargin + crtPanelH + CRTS_BottomMargin
        cabW = innerW + 2*CRTS_InnerPad
        cabH = innerH + 2*CRTS_InnerPad
        frameW = cabW + 2*CRTS_FramePad
        frameH = cabH + 2*CRTS_FramePad  # window is taller than 4:3

        self.frame = swing.JFrame("Passenger information display: platform " + self.platform)
        cp = self.frame.getContentPane()
        cp.setLayout(None)
        cp.setPreferredSize(Dimension(frameW, frameH))
        cp.setBackground(Color.BLACK)

        # Cabinet
        self.cab = CRTS_CabinetPanel()
        self.cab.setBounds(CRTS_FramePad, CRTS_FramePad, cabW, cabH)
        self.cab.setLayout(None)
        cp.add(self.cab)

        # Inner casing
        self.inner = CRTS_InnerCasingPanel(self.platform, CRTS_HeaderHeight)
        self.inner.setBounds(CRTS_InnerPad, CRTS_InnerPad, innerW, innerH)
        self.inner.setLayout(None)
        self.cab.add(self.inner)

        # CRT panel
        self.crt = CRTS_CRTPanel(CRTS_CrtBezelInset)
        self.crt.setBounds(CRTS_SideMargin, CRTS_HeaderHeight + CRTS_TopMargin, crtPanelW, crtPanelH)
        self.crt.setLayout(None)
        self.inner.add(self.crt)

        # ---- layout inside CRT ----
        crtW, crtH = crtPanelW, crtPanelH
        upperH = int(0.54 * crtH)
        padX = int(0.05 * crtW)
        padY = int(0.05 * upperH)
        timeH = int(upperH * 0.35)
        destH = upperH - timeH

        # TIME (HHMM)
        self.timeLabel = swing.JLabel("")
        self.timeLabel.setForeground(CRTS_CrtFore)
        self.timeLabel.setHorizontalAlignment(swing.SwingConstants.CENTER)
        self.timeLabel.setOpaque(False)
        self.timeLabel.setBounds(padX, padY, crtW - 2*padX, timeH - max(1, padY//4))
        self.crt.add(self.timeLabel)

        # DEST (two lines)
        destBoxY = padY + timeH - 2
        self.dest1 = swing.JLabel("")
        self.dest2 = swing.JLabel("")
        for d in (self.dest1, self.dest2):
            d.setForeground(CRTS_CrtFore)
            d.setHorizontalAlignment(swing.SwingConstants.CENTER)
            d.setOpaque(False)
        self.dest1.setBounds(padX, destBoxY, crtW - 2*padX, destH//2)
        self.dest2.setBounds(padX, destBoxY + destH//2, crtW - 2*padX, destH//2)
        self.crt.add(self.dest1)
        self.crt.add(self.dest2)

        # Calling area (3 columns)
        lowerY = upperH
        lowerH = crtH - upperH
        callTop = lowerY + int(0.08 * lowerH)
        callH = lowerY + lowerH - callTop - int(0.02 * lowerH)
        self.callBaseY = callTop
        CRTS_CallCols = 3
        CRTS_ColGapPct = 0.04
        col_gap = int(CRTS_ColGapPct * crtW)
        availW = (crtW - 2*padX) - (CRTS_CallCols - 1) * col_gap
        colW = availW // CRTS_CallCols
        spill = availW - colW * CRTS_CallCols

        self.callCols = []
        for i in range(CRTS_CallCols):
            extra = 1 if i < spill else 0
            x = padX + i * (colW + col_gap) + min(i, spill)
            w = colW + extra
            lbl = swing.JLabel("")
            lbl.setForeground(CRTS_CrtFore)
            lbl.setHorizontalAlignment(swing.SwingConstants.LEFT)
            lbl.setVerticalAlignment(swing.SwingConstants.TOP)
            lbl.setOpaque(False)
            lbl.setBounds(x, callTop, w, callH)
            self.crt.add(lbl)
            self.callCols.append(lbl)

        # CANCELLED overlay
        self.cancelLabel = swing.JLabel("")
        self.cancelLabel.setForeground(CRTS_CrtFore)
        self.cancelLabel.setHorizontalAlignment(swing.SwingConstants.CENTER)
        self.cancelLabel.setOpaque(False)
        self.cancelLabel.setBounds(padX, callTop, crtW - 2*padX, callH)
        self.cancelLabel.setVisible(False)
        self.crt.add(self.cancelLabel)

        # Listeners
        CRTS_TimeMem.addPropertyChangeListener(self.refresh)
        CRTS_DayMem.addPropertyChangeListener(self.refresh)
        if CRTS_TimetableMem is not None:
            CRTS_TimetableMem.addPropertyChangeListener(self.refresh)
        if CRTS_OverridesMem is not None:
            CRTS_OverridesMem.addPropertyChangeListener(self.refresh)
        if CRTS_DepartTPMem is not None:
            CRTS_DepartTPMem.addPropertyChangeListener(self.refresh)
        if CRTS_WithInMinMem is not None:
            CRTS_WithInMinMem.addPropertyChangeListener(self.refresh)
        if CRTS_EcsFilterMem is not None:  # NEW: react to ECS filter changes
            CRTS_EcsFilterMem.addPropertyChangeListener(self.refresh)

        self.frame.pack()
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[PIDCRTSingle] Failed to set PID window icon: " + str(ex))
        
        self.frame.setResizable(False)
        self.refresh()
        self.frame.setVisible(True)

    # ---- selection (with depart-clearing, due-within-X, and ECS filtering) ----
    def pick_next_train(self):
        rows = CRTS_CsvRows()
        curDay = CRTS_DayMem.getValue() or ""

        # 'Now' minutes
        if CRTS_Timebase is not None:
            ft = CRTS_Timebase.getTime()
            curMin = ft.getHours()*60 + ft.getMinutes()
        else:
            curStr = CRTS_TimeMem.getValue() or ""
            curMin = CRTS_ParseMinutes(curStr)
        if curMin is None:
            return None

        todays = [r for r in rows if ((r.get(curDay,"") or "").strip().lower() == "true")]

        # child RN -> former rows
        formers_map = {}
        for r in todays:
            child = (r.get("Forms","") or "").strip()
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
                    arr = (fr.get("Arr","") or "").strip()
                    arrMin = CRTS_ParseMinutes(arr) if arr else None
                    if arrMin is not None and arrMin <= sched_dep_min:
                        before.append((arrMin, fr))
                if before:
                    before.sort(key=lambda t: t[0])
                    chosen = before[-1][1]
            if chosen is None:
                chosen = formers[0]
            former_rn = (chosen.get("Reporting number","") or "").strip()
            return resolve_delay(former_rn, sched_dep_min, visited)

        within = CRTS_ReadWithinMinutes()
        cands = []
        for row in todays:
            dep = (row.get("Dep","") or "").strip()
            if not dep:
                continue
            rn = (row.get("Reporting number","") or "").strip()

            # NEW: skip ECS/empty-to-depot workings
            if CRTS_IsEcsWorking(row):
                continue

            plat = CRTS_GetOverride(rn) or CRTS_PlatformField(row)
            if str(plat) != self.platform:
                continue
            depMin = CRTS_ParseMinutes(dep)
            if depMin is None:
                continue
            dest = (row.get("Destination","") or "").strip()
            calling = (row.get("Calling pattern","") or "").strip()

            try:
                d = getDisruption(rn)
            except:
                d = None

            kind = "ontime"; val = 0
            if d is not None:
                try:
                    dd = int(d)
                except:
                    dd = 0
                if dd >= 1440:
                    kind = "cancel"
                elif dd > 0:
                    kind = "delay"; val = dd
                else:
                    kind, val = resolve_delay(rn, depMin)
            else:
                kind, val = resolve_delay(rn, depMin)

            cancelled = (kind == "cancel")
            expMin = (depMin + val) % (24*60) if (kind == "delay" and val > 0) else None

            # Clear if logged as departed at configured TP(s)
            if not cancelled and CRTS_HasDepartedAtConfiguredTP(rn, curDay, curMin):
                continue

            # Keep visible until expected time (or scheduled if on time/cancel)
            if cancelled:
                if depMin < curMin:
                    continue
            elif expMin is not None:
                if expMin < curMin:
                    continue
            else:
                if depMin < curMin:
                    continue

            adjusted = expMin if expMin is not None else depMin

            # Due-within-X constraint
            delta = (adjusted - curMin) % (24*60)
            if delta == 0 or (within >= 0 and 0 <= delta <= within):
                cands.append({
                    "rn": rn,
                    "time": dep,
                    "depMin": depMin,
                    "adjMin": adjusted,
                    "expMin": expMin,
                    "dest": dest,
                    "calling": calling,
                    "cancelled": cancelled
                })
            else:
                continue

        if not cands:
            return None
        cands.sort(key=lambda t: t["adjMin"])
        return cands[0]

    # ---- helper: word-wrap ----
    def wrap_into_lines(self, text, fm, maxW):
        words = [w for w in (text or "").split() if w]
        if not words:
            return [""]
        lines = []
        cur = ""
        for w in words:
            tst = (cur + " " + w).strip()
            if fm.stringWidth(tst) <= maxW or cur == "":
                cur = tst
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def refresh(self, e=None):
        nxt = self.pick_next_train()
        if not nxt:
            # Blank only the dynamic train-information area
            self.timeLabel.setText("")
            self.dest1.setText("")
            self.dest2.setText("")
            for c in self.callCols:
                c.setText("")
            self.cancelLabel.setVisible(False)
            self.cancelLabel.setText("")
            return

        # TIME (expected when delayed, else scheduled)
        if nxt.get("expMin") is not None and not nxt.get("cancelled", False):
            hhmm = CRTS_MinutesToHHmm(nxt["expMin"])
        else:
            hhmm = CRTS_FormatHHmm(nxt["time"])

        CRTS_FitFontToBox(self.timeLabel, hhmm, CRTS_CrtMonoFamily,
                          CRTS_TimeFontMin, CRTS_TimeFontMax,
                          self.timeLabel.getWidth(), self.timeLabel.getHeight())

        # DESTINATION (two-line fitter)
        def fit_destination_max(label1, label2, full_text, fam, minSize, maxSize):
            text = (full_text or "").upper().strip()
            w_box = label1.getWidth()
            h1_box = label1.getHeight()
            maxW_ln = int(w_box * CRTS_FitMarginW)
            maxH_ln = int(h1_box * CRTS_FitMarginH)
            tokens = [t for t in text.split() if t]
            best_two = (0, "", "")
            if len(tokens) >= 2:
                for i in range(1, len(tokens)):
                    l1 = " ".join(tokens[:i])
                    l2 = " ".join(tokens[i:])
                    def ok_two(sz):
                        f = Font(fam, Font.BOLD, sz)
                        fm = label1.getFontMetrics(f)
                        lineH = fm.getAscent() + fm.getDescent()
                        return (fm.stringWidth(l1) <= maxW_ln and
                                fm.stringWidth(l2) <= maxW_ln and
                                lineH <= maxH_ln)
                    lo, hi = minSize, maxSize
                    best = minSize
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        if ok_two(mid):
                            best = mid; lo = mid + 1
                        else:
                            hi = mid - 1
                    if best > best_two[0]:
                        best_two = (best, l1, l2)

            def ok_single(sz):
                f = Font(fam, Font.BOLD, sz)
                fm = label1.getFontMetrics(f)
                return (fm.stringWidth(text) <= maxW_ln and
                        (fm.getAscent()+fm.getDescent()) <= maxH_ln)

            lo, hi = minSize, maxSize
            size_single = minSize
            while lo <= hi:
                mid = (lo + hi) // 2
                if ok_single(mid):
                    size_single = mid; lo = mid + 1
                else:
                    hi = mid - 1

            if size_single >= best_two[0]:
                label1.setFont(Font(fam, Font.BOLD, size_single))
                label1.setText(text)
                label2.setText("")
            else:
                label1.setFont(Font(fam, Font.BOLD, best_two[0]))
                label2.setFont(Font(fam, Font.BOLD, best_two[0]))
                label1.setText(best_two[1])
                label2.setText(best_two[2])

        fit_destination_max(self.dest1, self.dest2, nxt["dest"],
                            CRTS_CrtMonoFamily, CRTS_DestFontMin, CRTS_DestFontMax)

        # Calling / CANCELLED
        if nxt.get("cancelled", False):
            for c in self.callCols:
                c.setText("")
            best = CRTS_CallFontMax + 6
            for size in range(best, CRTS_CallFontMin - 1, -1):
                f = Font(CRTS_CrtMonoFamily, Font.BOLD, size)
                fm = self.cancelLabel.getFontMetrics(f)
                w = fm.stringWidth("CANCELLED")
                h = fm.getAscent() + fm.getDescent()
                if (w <= int(self.cancelLabel.getWidth()*CRTS_FitMarginW) and
                    h <= int(self.cancelLabel.getHeight()*CRTS_FitMarginH)):
                    self.cancelLabel.setFont(f)
                    break
            self.cancelLabel.setText("CANCELLED")
            self.cancelLabel.setVisible(True)
            return
        else:
            self.cancelLabel.setVisible(False)
            self.cancelLabel.setText("")

        # ======== WRAP-AWARE PACKING ========
        raw_items = [CRTS_ToCaps(x.strip()) for x in (nxt["calling"] or "").split(",") if x.strip()]

        chosen = CRTS_CallFontMin
        for size in range(CRTS_CallFontMax, CRTS_CallFontMin - 1, -1):
            f = Font(CRTS_CrtMonoFamily, Font.BOLD, size)
            fm = self.callCols[0].getFontMetrics(f)
            lineH = fm.getAscent() + fm.getDescent() + fm.getLeading()
            usable = max(0, self.callCols[0].getHeight() - CRTS_CallTopPad - CRTS_CallBottomPad)
            rows_per_col = 0 if lineH == 0 else (usable // lineH)
            if rows_per_col > 0:
                chosen = size
                break

        mono = Font(CRTS_CrtMonoFamily, Font.BOLD, chosen)
        for lbl in self.callCols:
            lbl.setFont(mono)

        fm0 = self.callCols[0].getFontMetrics(mono)
        lineH = fm0.getAscent() + fm0.getDescent() + fm0.getLeading()
        usable = max(0, self.callCols[0].getHeight() - CRTS_CallTopPad - CRTS_CallBottomPad)
        CRTS_MaxRows = 8
        rows_per_col = max(1, min(CRTS_MaxRows, usable // lineH))

        columns = [[], [], []]
        col_w = [int(self.callCols[i].getWidth() * CRTS_FitMarginW) for i in range(3)]
        col_idx = 0
        used_lines = 0
        for item in raw_items:
            lines = self.wrap_into_lines(item, self.callCols[col_idx].getFontMetrics(mono), col_w[col_idx])
            needed = len(lines)
            if used_lines + needed > rows_per_col:
                col_idx += 1
                if col_idx >= 3:
                    break
                used_lines = 0
                lines = self.wrap_into_lines(item, self.callCols[col_idx].getFontMetrics(mono), col_w[col_idx])
                needed = len(lines)
            if needed > rows_per_col:
                lines = lines[:rows_per_col]
                needed = len(lines)
            for ln in lines:
                if used_lines >= rows_per_col:
                    col_idx += 1
                    if col_idx >= 3:
                        break
                    used_lines = 0
                if col_idx >= 3:
                    break
                columns[col_idx].append(ln)
                used_lines += 1
            if col_idx >= 3:
                break

        for i in range(3):
            while len(columns[i]) < rows_per_col:
                columns[i].append("")

        for i, lbl in enumerate(self.callCols):
            x, y, w, h = lbl.getX(), lbl.getY(), lbl.getWidth(), lbl.getHeight()
            lbl.setBounds(x, self.callBaseY, w, h)
            html = "<html><div style='margin-top:%dpx'>%s</div></html>" % (
                CRTS_CallTopPad, "<br>".join(columns[i])
            )
            lbl.setText(html)

    # ===========================================================================
    def cleanup(self):
        try:
            CRTS_TimeMem.removePropertyChangeListener(self.refresh)
        except:
            pass
        try:
            CRTS_DayMem.removePropertyChangeListener(self.refresh)
        except:
            pass
        try:
            if CRTS_TimetableMem is not None:
                CRTS_TimetableMem.removePropertyChangeListener(self.refresh)
        except:
            pass
        try:
            if CRTS_OverridesMem is not None:
                CRTS_OverridesMem.removePropertyChangeListener(self.refresh)
        except:
            pass
        try:
            if CRTS_DepartTPMem is not None:
                CRTS_DepartTPMem.removePropertyChangeListener(self.refresh)
        except:
            pass
        try:
            if CRTS_WithInMinMem is not None:
                CRTS_WithInMinMem.removePropertyChangeListener(self.refresh)
        except:
            pass
        try:
            if CRTS_EcsFilterMem is not None:  # NEW
                CRTS_EcsFilterMem.removePropertyChangeListener(self.refresh)
        except:
            pass

# ---- manager ----
class CRTS_PlatformCRTManager(object):
    def __init__(self):
        self.windows = {}
        if CRTS_TimetableMem is not None:
            CRTS_TimetableMem.addPropertyChangeListener(self.rebuild)
        if CRTS_OverridesMem is not None:
            CRTS_OverridesMem.addPropertyChangeListener(self.refresh_all)
        if CRTS_DepartTPMem is not None:
            CRTS_DepartTPMem.addPropertyChangeListener(self.refresh_all)
        if CRTS_WithInMinMem is not None:
            CRTS_WithInMinMem.addPropertyChangeListener(self.refresh_all)
        if CRTS_EcsFilterMem is not None:  # NEW: ECS filter changes
            CRTS_EcsFilterMem.addPropertyChangeListener(self.refresh_all)
        self.build()

    def build(self):
        plats = set()
        for r in CRTS_CsvRows():
            p = CRTS_PlatformField(r)
            if p:
                plats.add(p)
        for p in sorted(plats, key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s)):
            if p not in self.windows:
                self.windows[p] = CRTS_CRTPIDWindow(p)
        for p in [x for x in self.windows.keys() if x not in plats]:
            try:
                self.windows[p].cleanup()
                self.windows[p].frame.dispose()
            except:
                pass
            del self.windows[p]
        x0, y0, dx, dy = 40, 40, 16, 16
        for i, p in enumerate(sorted(self.windows.keys(), key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s))):
            self.windows[p].frame.setLocation(x0 + dx*i, y0 + dy*i)

    def rebuild(self, e=None):
        self.build()
        self.refresh_all()

    def refresh_all(self, e=None):
        for w in self.windows.values():
            w.refresh()

# ---- run ----
CRTS_Manager = CRTS_PlatformCRTManager()