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
# <<PID-DISP-NAME: Platform fingerboard (British Rail)>>
# <<DESCRIPTION: A simplified BR-style fingerboard: white on black calling pattern with a white 'Next train' box>>
#
# User-configurable setting discovered by TASSetup:
# <<SETTING DESCRIPTION NUMBER: Due window (minutes)>>
#
# Requirements implemented:
# - No clocks, labels or wooden pole.
# - Black board with white title-case calling pattern text.
# - Destination is always appended as the final item in the calling pattern.
# - Right-hand end is rectangular with slightly rounded corners.
# - White rectangle (twice as tall as wide) with centered "Next\nTrain".
# - White rectangle is to the LEFT of the black board with NO GAP.
# - Board height adapts to text, up to the white rectangle height.
# - British Rail Light Normal (white-on-black) and British Rail Dark Normal (black-on-white) with sensible fallbacks.
# - Windowless (undecorated) with transparent background.
# - Double-click on the "Next train" box closes the window.
# - Drag anywhere to move the window.
#
# JMRI 5.14, Jython 2.7.

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, RenderingHints, BasicStroke, Dimension
from java.awt.geom import RoundRectangle2D, Area
from javax.swing import Timer
import jmri
from jmri import InstanceManager
import os
import csv as BR_csv
import java.text.SimpleDateFormat as SimpleDateFormat

import TimingRegister as TR  # read-only tuples (reportingNumber, direction, time, day)
import TASBeanLookup as TBL
import PlatformAllocationRegister as PAR  # allocation takes precedence over timetable/overrides
from DisruptionRegister import getDisruption

# -------------------- TYPEFACES (NO USER SETTINGS) --------------------

def BR_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

# White on black
BR_TypefaceLight = BR_PickFamily([
    "BritishRailLightNormal",
    "Helvetica",
    "Liberation Sans",
    "Arial",
    "SansSerif"
])

# Black on white
BR_TypefaceDark = BR_PickFamily([
    "BritishRailDarkNormal",
    "Helvetica",
    "Liberation Sans",
    "Arial",
    "SansSerif"
])

# -------------------- COLOURS (FIXED) --------------------

BR_Black = Color(0, 0, 0)
BR_White = Color(255, 255, 255)

# -------------------- LAYOUT CONSTANTS --------------------

BR_Margin = 10
BR_BoardW = 900
BR_BoardMinH = 60
BR_BoardCorner = 10
BR_BoardPadX = 16
BR_BoardPadY = 12

BR_BoxW = 120
BR_BoxH = 240  # 2x tall
BR_BoxCorner = 12

BR_BoardTextMaxPt = 34
BR_BoardTextMinPt = 14

BR_BoxTextMaxPt = 44
BR_BoxTextMinPt = 18

BR_OutlineStroke = BasicStroke(3.0)

# -------------------- JMRI MEMORIES / TIMETABLE --------------------

# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
BR_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
BR_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
BR_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
BR_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# Legacy behaviour memory.
BR_WithinMinLegacyMem = TBL.ProvideMemoryBySuffix("PID_FINGERBOARD_WITHIN_MINUTES", "10")
BR_DefaultWithinMinutes = 10

# TASSetup user-setting memories (friendly label and legacy key).
# Friendly label: "Due window (minutes)" -> TAS_USER_SETTING_DUE_WINDOW_MINUTES_
BR_WithinMinFriendlyMem = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_DUE_WINDOW_MINUTES_", "10")
# Legacy TASSetup key: WITHIN_MINUTES
BR_WithinMinLegacyTASMem = TBL.ProvideMemoryBySuffix("TAS_USER_SETTING_WITHIN_MINUTES", "")

# Optional behaviour memories kept for compatibility.
BR_DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
BR_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")

# Optional authoritative fast clock for "now".
BR_Timebase = InstanceManager.getDefault(jmri.Timebase)

# -------------------- TIME HELPERS --------------------

BR_TimeParser24 = SimpleDateFormat("H:mm")
BR_TimeParser12 = SimpleDateFormat("h:mm a")


def BR_ParseMinutes(s):
    for p in [BR_TimeParser12, BR_TimeParser24]:
        try:
            d = p.parse(s)
            return d.getHours() * 60 + d.getMinutes()
        except:
            pass
    return None


def BR_ReadWithinMinutes():
    # Preference order:
    # 1) TASSetup friendly setting (Due window minutes)
    # 2) TASSetup legacy setting (WITHIN_MINUTES)
    # 3) Legacy runtime memory PID_FINGERBOARD_WITHIN_MINUTES
    # 4) Default
    try:
        for mem in [BR_WithinMinFriendlyMem, BR_WithinMinLegacyTASMem, BR_WithinMinLegacyMem]:
            try:
                v = mem.getValue() if mem is not None else None
            except:
                v = None
            s = ("" if v is None else str(v)).strip()
            if s != "":
                try:
                    x = int(float(s))
                except:
                    x = BR_DefaultWithinMinutes
                if x < 0:
                    x = BR_DefaultWithinMinutes
                return x
        return BR_DefaultWithinMinutes
    except:
        return BR_DefaultWithinMinutes

# -------------------- CSV ACCESS --------------------


def BR_TimetablePath():
    name = BR_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")


def BR_CsvRows():
    path = BR_TimetablePath()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            rdr = BR_csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []


def BR_PlatformField(row):
    return (row.get("Plat", "") or row.get("Platform", "") or "").strip()


def BR_ParseOverrides(s):
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


def BR_GetOverride(rn):
    try:
        return BR_ParseOverrides(BR_OverridesMem.getValue()).get(rn)
    except:
        return None

# -------------------- DEPARTURE-LOGGING SUPPORT --------------------


def BR_ActiveProfileBaseTPName():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""


def BR_DepartureTPList():
    # If nothing configured, default to the active profile name (one TP).
    names = []
    try:
        raw = BR_DepartTPMem.getValue() if BR_DepartTPMem is not None else None
        if raw:
            for p in str(raw).replace(",", ";").split(";"):
                t = (p or "").strip()
                if t and t not in names:
                    names.append(t)
    except:
        pass
    if not names:
        base = BR_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names


def BR_HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    tps = BR_DepartureTPList()
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
            mm = BR_ParseMinutes(tstr)
            if mm is None:
                continue
            if mm <= int(nowMinutes):
                return True
    return False


def BR_HasAnyTimingToday(reportingNumber, dayName):
    # Return True iff ANY timing point has a timing tuple for (reportingNumber, dayName).
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

# -------------------- ECS FILTER (KEYWORDS ONLY) --------------------

BR_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]


def BR_ReadExtraEcsTerms():
    out = []
    try:
        raw = BR_EcsFilterMem.getValue() if BR_EcsFilterMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                t = p.strip()
                if t:
                    out.append(t.upper())
    except:
        pass
    return out


def BR_IsEcsWorking(row):
    dest = ((row.get("Destination", "") or "")).strip().upper()
    call = ((row.get("Calling pattern", "") or "")).strip().upper()
    terms = set([t.upper() for t in BR_DefaultEcsTerms])
    for extra in BR_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " " + call
    for t in terms:
        if t and t in hay:
            return True
    return False

# -------------------- DELAY INHERITANCE --------------------


def BR_ResolveDelayWithInheritance(rowsToday, formersMap, rn, schedDepMin, visited=None):
    # Returns ("cancel", None) / ("delay", minutes>0) / ("ontime", 0)
    if visited is None:
        visited = set()
    if rn in visited:
        return ("ontime", 0)
    visited.add(rn)

    # Direct disruption
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

    # Inherit from 'Forms' today
    formers = formersMap.get(rn, [])
    if not formers:
        return ("ontime", 0)

    chosen = None
    if schedDepMin is not None:
        before = []
        for fr in formers:
            arr = (fr.get("Arr", "") or "").strip()
            arrMin = BR_ParseMinutes(arr) if arr else None
            if arrMin is not None and arrMin <= schedDepMin:
                before.append((arrMin, fr))
        if before:
            before.sort(key=lambda t: t[0])
            chosen = before[-1][1]

    if chosen is None:
        chosen = formers[0]

    formerRN = ((chosen.get("Reporting number", "") or "")).strip()
    return BR_ResolveDelayWithInheritance(rowsToday, formersMap, formerRN, schedDepMin, visited)

# -------------------- NEXT TRAIN FOR A PLATFORM --------------------


def BR_PickNextTrainForPlatform(platform):
    rows = BR_CsvRows()

    # "Now" minutes: prefer fast clock, else IMCURRENTTIME
    if BR_Timebase is not None:
        ft = BR_Timebase.getTime()
        curMin = ft.getHours() * 60 + ft.getMinutes()
    else:
        curStr = BR_TimeMem.getValue() or ""
        curMin = BR_ParseMinutes(curStr)
    if curMin is None:
        return None

    curDay = BR_DayMem.getValue() or ""
    within = BR_ReadWithinMinutes()

    # Build today's rows and the formation map for delay inheritance
    todays = []
    for _r in rows:
        try:
            if (((_r.get(curDay, "") or "").strip().lower()) == "true"):
                todays.append(_r)
        except:
            pass

    formersMap = {}
    for _r in todays:
        try:
            ch = (_r.get("Forms", "") or "").strip()
            if ch:
                formersMap.setdefault(ch, []).append(_r)
        except:
            pass

    cands = []
    for row in rows:
        dep = (row.get("Dep", "") or "").strip()
        if not dep:
            continue
        if ((row.get(curDay, "") or "").strip().lower() != "true"):
            continue

        # Platform precedence: allocation register > overrides > timetable
        rn = (row.get("Reporting number", "") or "").strip()
        alloc = PAR.getPlatform(rn)
        if alloc is not None and str(alloc).strip():
            plat = str(alloc).strip()
        else:
            plat = BR_GetOverride(rn) or BR_PlatformField(row)
        if str(plat) != str(platform):
            continue

        # ECS filter (keywords only)
        if BR_IsEcsWorking(row):
            continue

        depMin = BR_ParseMinutes(dep)
        if depMin is None:
            continue

        # Determine disruption (direct or inherited) and adjusted minutes
        cancelled = False
        expectedMin = None

        try:
            direct = getDisruption(rn)
        except:
            direct = None

        kind = "ontime"
        val = 0

        if direct is not None:
            try:
                dd = int(direct)
            except:
                dd = 0
            if dd >= 1440:
                cancelled = True
            elif dd > 0:
                kind = "delay"
                val = dd

        if (direct is None) or (kind == "ontime"):
            try:
                kind, val = BR_ResolveDelayWithInheritance(todays, formersMap, rn, depMin, visited=set())
            except:
                kind, val = ("ontime", 0)

        if kind == "cancel":
            cancelled = True
        elif kind == "delay" and val and val > 0:
            try:
                expectedMin = depMin + int(val)
            except:
                expectedMin = depMin

        # Clear on departure (remove only when logged as departed)
        if BR_HasDepartedAtConfiguredTP(rn, curDay, curMin):
            continue

        # Past-hiding rules (resilient)
        if cancelled:
            if depMin < curMin:
                continue
        else:
            if expectedMin is not None:
                if expectedMin < curMin:
                    continue
            else:
                # On-time resilience: only hide booked-past if no disruption AND no timing seen today.
                if (direct is None) and (not BR_HasAnyTimingToday(rn, curDay)):
                    if depMin < curMin:
                        continue

        # Due-within window uses adjusted minutes when delayed, else booked
        adjMin = expectedMin if expectedMin is not None else depMin
        delta = (adjMin - curMin) % (24 * 60)
        if within != 0:
            if not (delta == 0 or (0 <= delta <= within)):
                continue

        calling = (row.get("Calling pattern", "") or "").strip()
        dest = (row.get("Destination", "") or "").strip()

        cands.append({
            "rn": rn,
            "calling": calling,
            "dest": dest,
            "adjMin": adjMin
        })

    if not cands:
        return None

    cands.sort(key=lambda t: t["adjMin"])
    return cands[0]

# -------------------- TEXT HELPERS --------------------


def BR_TitleCase(s):
    # Keep it simple and ASCII-safe.
    try:
        return str(s).strip().lower().title()
    except:
        return ""


def BR_ComposeCallingPattern(model):
    if not model:
        return ""
    callingRaw = (model.get("calling") or "").strip()
    destRaw = (model.get("dest") or "").strip()
    items = []
    lastCallingRaw = None
    if callingRaw:
        for part in callingRaw.split(","):
            t = part.strip()
            if t:
                items.append(BR_TitleCase(t))
                lastCallingRaw = t
    dest = BR_TitleCase(destRaw)
    if dest:
        # Avoid printing the destination twice if it is already the last item in the calling pattern.
        try:
            def _Norm(s):
                return " ".join(str(s).strip().split()).lower()
            if lastCallingRaw is None or _Norm(lastCallingRaw) != _Norm(destRaw):
                items.append(dest)
        except:
            items.append(dest)
    return ", ".join(items)
# -------------------- DRAWING PANEL --------------------

class BR_FingerBoardPanel(swing.JPanel):
    def __init__(self, platform, ownerWindow):
        swing.JPanel.__init__(self)
        self.setOpaque(False)
        self.platform = str(platform)
        self.ownerWindow = ownerWindow
        self.model = None
        self.cachedLines = []
        self.cachedFont = None
        self.cachedBoardH = BR_BoardMinH

        self.dragAnchorScreenX = None
        self.dragAnchorScreenY = None
        self.dragAnchorWinX = None
        self.dragAnchorWinY = None

        # Repaint timer
        def _doRepaint(e):
            try:
                self.repaint()
            except:
                pass
        self.repaintTimer = Timer(800, _doRepaint)
        self.repaintTimer.start()

        from java.awt.event import MouseAdapter
        class MouseHandler(MouseAdapter):
            def __init__(self, panel):
                self.panel = panel

            def mousePressed(self, e):
                try:
                    self.panel.dragAnchorScreenX = e.getXOnScreen()
                    self.panel.dragAnchorScreenY = e.getYOnScreen()
                    if self.panel.ownerWindow is not None:
                        loc = self.panel.ownerWindow.getLocation()
                        self.panel.dragAnchorWinX = loc.x
                        self.panel.dragAnchorWinY = loc.y
                except:
                    pass

            def mouseDragged(self, e):
                try:
                    if self.panel.ownerWindow is None:
                        return
                    if self.panel.dragAnchorScreenX is None or self.panel.dragAnchorScreenY is None:
                        return
                    dx = e.getXOnScreen() - self.panel.dragAnchorScreenX
                    dy = e.getYOnScreen() - self.panel.dragAnchorScreenY
                    self.panel.ownerWindow.setLocation(self.panel.dragAnchorWinX + dx, self.panel.dragAnchorWinY + dy)
                except:
                    pass

            def mouseClicked(self, e):
                # Double-click on Next Train box closes
                try:
                    if e.getClickCount() != 2:
                        return
                    x = e.getX()
                    y = e.getY()
                    bx, by, bw, bh = self.panel.getNextBoxBounds()
                    if x >= bx and x <= bx + bw and y >= by and y <= by + bh:
                        try:
                            self.panel.closeOwner()
                        except:
                            pass
                except:
                    pass

        handler = MouseHandler(self)
        self.addMouseListener(handler)
        self.addMouseMotionListener(handler)

    def stopRepaintTimer(self):
        try:
            if hasattr(self, "repaintTimer") and self.repaintTimer is not None:
                self.repaintTimer.stop()
                self.repaintTimer = None
        except:
            pass

    def removeNotify(self):
        try:
            self.stopRepaintTimer()
        finally:
            swing.JPanel.removeNotify(self)

    def setModel(self, m):
        self.model = m
        self.recomputeLayout()
        try:
            self.revalidate()
        except:
            pass
        try:
            self.repaint()
        except:
            pass

    def closeOwner(self):
        # Called on double-click in the Next Train box.
        # Ensure cleanup and manager bookkeeping happen.
        try:
            if self.ownerWindow is not None and hasattr(self.ownerWindow, "_BrOwner"):
                owner = getattr(self.ownerWindow, "_BrOwner")
                if owner is not None:
                    owner.onWindowClosed()
                    return
        except:
            pass

        # Fallback
        try:
            self.stopRepaintTimer()
        except:
            pass
        try:
            if self.ownerWindow is not None:
                self.ownerWindow.dispose()
        except:
            pass

    def getNextBoxBounds(self):
        # White box is at the left, flush to the black board.
        bx = BR_Margin
        by = BR_Margin
        return (bx, by, BR_BoxW, BR_BoxH)

    def computePreferred(self):
        width = BR_Margin + BR_BoxW + BR_BoardW + BR_Margin
        height = BR_Margin + BR_BoxH + BR_Margin
        return Dimension(width, height)

    def recomputeLayout(self):
        # Determine best wrap and font for the calling pattern within max board height.
        try:
            img = awt.image.BufferedImage(10, 10, awt.image.BufferedImage.TYPE_INT_ARGB)
            g2 = img.createGraphics()
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        except:
            self.cachedLines = []
            self.cachedFont = Font(BR_TypefaceLight, Font.PLAIN, BR_BoardTextMinPt)
            self.cachedBoardH = BR_BoardMinH
            self.setPreferredSize(self.computePreferred())
            return

        text = BR_ComposeCallingPattern(self.model)
        maxW = BR_BoardW - 2 * BR_BoardPadX
        maxH = BR_BoxH - 2 * BR_BoardPadY

        bestFont = Font(BR_TypefaceLight, Font.PLAIN, BR_BoardTextMinPt)
        bestLines = [""]
        bestNeeded = BR_BoardMinH

        def wrapWithFont(fontObj):
            fm = g2.getFontMetrics(fontObj)
            perH = fm.getAscent() + fm.getDescent()
            lines = []
            words = [w for w in (text or "").split() if w]
            if not words:
                return ([""], 0, perH)
            cur = ""
            for w in words:
                t = (cur + " " + w).strip()
                if fm.stringWidth(t) <= maxW or not cur:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            neededH = len(lines) * perH
            return (lines, neededH, perH)

        chosen = False
        for size in range(BR_BoardTextMaxPt, BR_BoardTextMinPt - 1, -1):
            f = Font(BR_TypefaceLight, Font.PLAIN, size)
            lines, neededH, perH = wrapWithFont(f)
            if neededH <= maxH:
                bestFont = f
                bestLines = lines
                bestNeeded = neededH
                chosen = True
                break

        if not chosen:
            f = Font(BR_TypefaceLight, Font.PLAIN, BR_BoardTextMinPt)
            lines, neededH, perH = wrapWithFont(f)
            maxLines = max(1, int(maxH // perH))
            bestFont = f
            bestLines = lines[:maxLines]
            bestNeeded = maxLines * perH

        boardH = int(min(BR_BoxH, max(BR_BoardMinH, bestNeeded + 2 * BR_BoardPadY)))

        self.cachedLines = bestLines
        self.cachedFont = bestFont
        self.cachedBoardH = boardH

        self.setPreferredSize(self.computePreferred())

        try:
            g2.dispose()
        except:
            pass

    def paintComponent(self, g):
        # Transparent background: do not fill.
        try:
            g2 = g
            if isinstance(g, awt.Graphics2D):
                g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
                g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)

            boxX = BR_Margin
            boxY = BR_Margin
            boxW = BR_BoxW
            boxH = BR_BoxH

            boardX = boxX + boxW  # flush, no gap
            boardY = BR_Margin
            boardW = BR_BoardW
            boardH = self.cachedBoardH

            # White "Next train" box
            boxShape = RoundRectangle2D.Float(boxX, boxY, boxW, boxH, BR_BoxCorner, BR_BoxCorner)
            boardShape = RoundRectangle2D.Float(boardX, boardY, boardW, boardH, BR_BoardCorner, BR_BoardCorner)
            # Directional drop shadow for the entire sign (no internal shadows).
            try:
                signArea = Area(boxShape)
                signArea.add(Area(boardShape))
                baseTx = None
                try:
                    baseTx = g2.getTransform()
                    steps = 10
                    maxAlpha = 55
                    # Shadow falls down and right, fading with distance.
                    for s in range(1, steps + 1):
                        frac = float(steps + 1 - s) / float(steps + 1)
                        alpha = int(maxAlpha * (frac * frac))
                        if alpha <= 0:
                            continue
                        ox = s
                        oy = s
                        g2.setColor(Color(0, 0, 0, alpha))
                        # A little softening: a couple of near-by offsets, still down/right.
                        offs = [(ox, oy), (ox + 1, oy), (ox, oy + 1)]
                        for dx, dy in offs:
                            g2.setTransform(baseTx)
                            g2.translate(dx, dy)
                            g2.fill(signArea)
                except:
                    pass
                try:
                    if baseTx is not None:
                        g2.setTransform(baseTx)
                except:
                    pass
            except:
                pass

            g2.setColor(BR_White)
            g2.fill(boxShape)
            # Small platform label at the top of the Next Train box.
            try:
                headerText = "Platform " + str(self.platform)
                headerPadTop = 10
                headerGap = 6
                headerMaxW = int(boxW * 0.90)
                headerBest = Font(BR_TypefaceDark, Font.PLAIN, 12)
                for size in range(20, 9, -1):
                    f = Font(BR_TypefaceDark, Font.PLAIN, size)
                    hfm = g2.getFontMetrics(f)
                    if hfm.stringWidth(headerText) <= headerMaxW:
                        headerBest = f
                        break
                g2.setFont(headerBest)
                g2.setColor(BR_Black)
                hfm = g2.getFontMetrics(headerBest)
                hx = boxX + int((boxW - hfm.stringWidth(headerText)) / 2)
                hy = boxY + headerPadTop + hfm.getAscent()
                g2.drawString(headerText, hx, hy)
                headerAreaH = headerPadTop + hfm.getAscent() + hfm.getDescent() + headerGap
                if headerAreaH < boxH - 20:
                    self.drawCenteredMultiline(g2, "Next\nTrain", boxX, boxY + headerAreaH, boxW, boxH - headerAreaH)
                else:
                    self.drawCenteredMultiline(g2, "Next\nTrain", boxX, boxY, boxW, boxH)
            except:
                self.drawCenteredMultiline(g2, "Next\nTrain", boxX, boxY, boxW, boxH)

            # Black board
            g2.setColor(BR_Black)
            g2.fill(boardShape)

            # Calling pattern text (white on black), left aligned
            g2.setFont(self.cachedFont if self.cachedFont is not None else Font(BR_TypefaceLight, Font.PLAIN, BR_BoardTextMinPt))
            g2.setColor(BR_White)
            fm = g2.getFontMetrics()
            lineH = fm.getAscent() + fm.getDescent()
            x = boardX + BR_BoardPadX
            y = boardY + BR_BoardPadY + fm.getAscent()
            for ln in (self.cachedLines or []):
                g2.drawString(ln, x, y)
                y += lineH

        except:
            pass

    def drawCenteredMultiline(self, g2, text, x, y, w, h):
        lines = (text or "").split("\n")
        maxW = int(w * 0.88)
        maxH = int(h * 0.85)

        best = Font(BR_TypefaceDark, Font.PLAIN, BR_BoxTextMinPt)
        for size in range(BR_BoxTextMaxPt, BR_BoxTextMinPt - 1, -1):
            f = Font(BR_TypefaceDark, Font.PLAIN, size)
            fm = g2.getFontMetrics(f)
            perH = fm.getAscent() + fm.getDescent()
            totalH = perH * len(lines)
            widest = 0
            for ln in lines:
                widest = max(widest, fm.stringWidth(ln))
            if widest <= maxW and totalH <= maxH:
                best = f
                break

        g2.setFont(best)
        g2.setColor(BR_Black)
        fm = g2.getFontMetrics(best)
        perH = fm.getAscent() + fm.getDescent()
        totalH = perH * len(lines)
        startY = y + int((h - totalH) / 2) + fm.getAscent()
        for i, ln in enumerate(lines):
            tx = x + int((w - fm.stringWidth(ln)) / 2)
            ty = startY + i * perH
            g2.drawString(ln, tx, ty)

# -------------------- WINDOW PER PLATFORM --------------------

class BR_FingerBoardWindow(object):
    def __init__(self, platform):
        self.platform = str(platform)
        self.window = swing.JWindow()

        # Back-reference used by the panel to close cleanly.
        try:
            setattr(self.window, "_BrOwner", self)
        except:
            pass

        try:
            self.window.setBackground(Color(0, 0, 0, 0))
        except:
            pass

        self.panel = BR_FingerBoardPanel(self.platform, self.window)
        preferred = self.panel.computePreferred()

        cp = self.window.getContentPane()
        cp.setLayout(None)
        try:
            cp.setOpaque(False)
        except:
            pass

        self.panel.setBounds(0, 0, preferred.width, preferred.height)
        cp.add(self.panel)

        self.window.setSize(preferred)
        self.window.setVisible(True)

        # Listeners
        for m in [
            BR_TimeMem, BR_DayMem, BR_TimetableMem, BR_OverridesMem,
            BR_DepartTPMem, BR_EcsFilterMem,
            BR_WithinMinLegacyMem, BR_WithinMinFriendlyMem, BR_WithinMinLegacyTASMem
        ]:
            try:
                if m is not None:
                    m.addPropertyChangeListener(self.refresh)
            except:
                pass

        try:
            PAR.addPlatformListener(self.refresh)
        except:
            pass

        self.refresh()

    def refresh(self, e=None):
        m = BR_PickNextTrainForPlatform(self.platform)
        self.panel.setModel(m)

    def cleanup(self):
        try:
            self.panel.stopRepaintTimer()
        except:
            pass

        for m in [
            BR_TimeMem, BR_DayMem, BR_TimetableMem, BR_OverridesMem,
            BR_DepartTPMem, BR_EcsFilterMem,
            BR_WithinMinLegacyMem, BR_WithinMinFriendlyMem, BR_WithinMinLegacyTASMem
        ]:
            try:
                if m is not None:
                    m.removePropertyChangeListener(self.refresh)
            except:
                pass

        try:
            PAR.removePlatformListener(self.refresh)
        except:
            pass

        try:
            if self.window is not None:
                self.window.dispose()
        except:
            pass

    def onWindowClosed(self):
        # Idempotent cleanup and manager bookkeeping.
        try:
            self.cleanup()
        except:
            pass
        try:
            if 'BR_Manager' in globals() and BR_Manager is not None:
                BR_Manager.handleWindowClosed(self.platform)
        except:
            pass

# -------------------- MANAGER: WINDOWS PER PLATFORM --------------------


def BR_DetectPlatforms():
    plats = set()
    for r in BR_CsvRows():
        p = BR_PlatformField(r)
        if p:
            plats.add(str(p))
    return sorted(plats, key=lambda x: (x.isdigit(), int(x) if x.isdigit() else x))


class BR_PlatformFingerBoards(object):
    def __init__(self):
        self.windows = {}

        try:
            if BR_TimetableMem is not None:
                BR_TimetableMem.addPropertyChangeListener(self.rebuild)
        except:
            pass

        self.build()

    def build(self):
        plats = BR_DetectPlatforms()

        for p in plats:
            if p not in self.windows:
                self.windows[p] = BR_FingerBoardWindow(p)

        for p in [x for x in list(self.windows.keys()) if x not in plats]:
            try:
                self.windows[p].cleanup()
            except:
                pass
            try:
                del self.windows[p]
            except:
                pass

        x0, y0, dx, dy = 40, 40, 26, 26
        i = 0
        for p in self.windows.keys():
            try:
                self.windows[p].window.setLocation(x0 + dx * i, y0 + dy * i)
            except:
                pass
            i += 1

    def rebuild(self, e=None):
        self.build()

    def handleWindowClosed(self, platform):
        try:
            key = str(platform)
            if key in self.windows:
                try:
                    del self.windows[key]
                except:
                    pass
        except:
            pass

# -------------------- RUN --------------------

BR_Manager = BR_PlatformFingerBoards()
