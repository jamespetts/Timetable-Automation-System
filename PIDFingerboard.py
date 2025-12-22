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
#
# Text composition remains configurable:
#   FBP_TEXT_MODE = "CALLING_ONLY" or "DEST_THEN_CALLING"
#   FBP_CALLING_SEPARATOR, FBP_DEST_CALL_JOINER, FBP_UPPERCASE_ALL
#
# <<PID-DISP-NAME: Platform fingerboard>>
# <<DESCRIPTION: A wooden board with the destination and calling pattern of the next train painted on it>>

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font, GradientPaint, RenderingHints, BasicStroke, Dimension
from javax.swing import Timer
import jmri
from jmri import InstanceManager
import os
import csv as FBP_csv
import java.text.SimpleDateFormat as SimpleDateFormat
from java.awt.geom import Area, RoundRectangle2D, Ellipse2D
import TimingRegister as TR  # read-only tuples (reportingNumber, direction, time, day)
import TASBeanLookup as TBL

# -------------------- TYPEFACE & COLOURS --------------------
def FBP_PickFamily(cands):
    env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
    fams = set(env.getAvailableFontFamilyNames())
    for name in cands:
        if name in fams:
            return name
    return "SansSerif"

# Primary face (board & labels)
FBP_TYPEFACE_PRIMARY  = FBP_PickFamily(["Gill Sans MT", "Gill Sans", "SansSerif"])
# Numerals face (Roman around the dial)
FBP_TYPEFACE_NUMERALS = FBP_PickFamily(["Serif", "Times New Roman", "DejaVu Serif", "Serif"])

# -------------------- TEXT COMPOSITION --------------------
FBP_TEXT_MODE          = "CALLING_ONLY"   # "CALLING_ONLY" or "DEST_THEN_CALLING"
FBP_CALLING_SEPARATOR  = " - "
FBP_DEST_CALL_JOINER   = " "
FBP_UPPERCASE_ALL      = True

# -------------------- COLOURS --------------------
FBP_BG_COLOR      = Color(20, 20, 30)
FBP_POST_COLOR    = Color(96, 70, 38)
FBP_POST_SHADE    = Color(68, 48, 26)
FBP_BOARD_FILL    = Color(252, 252, 252)
FBP_BOARD_EDGE    = Color(35, 35, 35)
FBP_TEXT_COLOR    = Color(0, 0, 0)
FBP_CLOCK_FACE    = Color(250, 250, 250)
FBP_CLOCK_EDGE    = Color(35, 35, 35)
FBP_CLOCK_TICK    = Color(65, 65, 65)
FBP_CLOCK_HAND    = Color(20, 20, 20)
FBP_LABEL_BOX_FILL= Color(255, 255, 255)
FBP_LABEL_BOX_EDGE= Color(20, 20, 20)

# -------------------- GEOMETRY / LAYOUT --------------------
FBP_MARGIN            = 10
FBP_POST_W            = 36
FBP_POST_RADIUS       = 14
FBP_BOARD_H           = 120
FBP_BOARD_LEFT_GAP    = -1   # slight overlap onto post
FBP_BOARD_TOP         = 14
FBP_CAP_RADIUS        = FBP_BOARD_H // 2
FBP_OUTLINE_STROKE    = BasicStroke(3.0)
FBP_LEFT_PAD          = 14
FBP_RIGHT_PAD         = 18
FBP_CLOCK_D           = 120
FBP_CLOCK_PAIR_GAP    = 30
FBP_CLOCK_BLOCK_TOP_G = 18

# ARR/DEP label boxes beside clocks
FBP_LABEL_BOX_MAX_W   = 180
FBP_LABEL_BOX_H       = 40
FBP_LABEL_BOX_PAD_TXT = 6
FBP_LABEL_BOX_INSET   = 4
FBP_LABEL_FONT_MAX    = 28
FBP_LABEL_FONT_MIN    = 12

# Board text sizing
FBP_LINE_FONT_MAX     = 42
FBP_LINE_FONT_MIN     = 18

# ------------------------- JMRI MEMORIES / TIMETABLE -------------------------
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
FBP_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
FBP_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
FBP_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
FBP_OverridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

# Optional: departure TP list, ECS keywords, due-window, hide-clocks toggle
FBP_DepartTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
FBP_EcsFilterMem = TBL.ProvideMemoryBySuffix("PID_ECS_FILTER_TERMS", "")
FBP_WithInMinMem = TBL.ProvideMemoryBySuffix("PID_FINGERBOARD_WITHIN_MINUTES", "10")
FBP_HideClocksEmptyMem = TBL.ProvideMemoryBySuffix("PID_FINGERBOARD_HIDE_CLOCKS_WHEN_EMPTY", "false")

FBP_DefaultWithinMinutes = 10

# Optional authoritative fast clock for "now"
FBP_Timebase      = InstanceManager.getDefault(jmri.Timebase)

# -------------------- TIME HELPERS --------------------
FBP_TimeParser24 = SimpleDateFormat("H:mm")
FBP_TimeParser12 = SimpleDateFormat("h:mm a")
FBP_FmtHHmm = SimpleDateFormat("HH:mm")

def FBP_ParseMinutes(s):
    for p in [FBP_TimeParser24, FBP_TimeParser12]:
        try:
            d = p.parse(s); return d.getHours()*60 + d.getMinutes()
        except:
            pass
    return None

def FBP_NormTime(s):
    for p in [FBP_TimeParser24, FBP_TimeParser12]:
        try:
            d = p.parse(s); return FBP_FmtHHmm.format(d)
        except:
            pass
    return None

def FBP_ReadWithinMinutes():
    try:
        v = FBP_WithInMinMem.getValue() if FBP_WithInMinMem is not None else None
        if v is None: return FBP_DefaultWithinMinutes
        s = str(v).strip()
        if not s: return FBP_DefaultWithinMinutes
        x = int(s)
        if x < 0: return FBP_DefaultWithinMinutes
        return x
    except:
        return FBP_DefaultWithinMinutes

def FBP_ReadHideClocksWhenEmpty():
    try:
        v = FBP_HideClocksEmptyMem.getValue() if FBP_HideClocksEmptyMem is not None else None
        if v is None: return False
        s = str(v).strip().lower()
        return s in ("true","yes","1","on","y","t")
    except:
        return False

# -------------------- CSV ACCESS --------------------
def FBP_TimetablePath():
    name = FBP_TimetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")

def FBP_CsvRows():
    path = FBP_TimetablePath()
    if not os.path.exists(path): return []
    try:
        with open(path, "r") as f:
            rdr = FBP_csv.DictReader(f, delimiter="\t")
            return list(rdr)
    except:
        return []

def FBP_PlatformField(row):
    return (row.get("Plat","") or row.get("Platform","") or "").strip()

def FBP_ParseOverrides(s):
    out = {}
    if not s: return out
    for part in s.replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part: continue
        k, v = part.split("=",1)
        out[k.strip()] = v.strip()
    return out

def FBP_GetOverride(rn):
    try:
        return FBP_ParseOverrides(FBP_OverridesMem.getValue()).get(rn)
    except:
        return None

# -------------------- DEPARTURE-LOGGING SUPPORT --------------------
def FBP_ActiveProfileBaseTPName():
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""

def FBP_DepartureTPList():
    names = []
    try:
        raw = FBP_DepartTPMem.getValue() if FBP_DepartTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                t = p.strip()
                if t:
                    names.append(t)
    except:
        names = []
    if not names:
        base = FBP_ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names

def FBP_HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    tps = FBP_DepartureTPList()
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
            mm = FBP_ParseMinutes(tstr)
            if mm is None: continue
            if mm <= int(nowMinutes):
                return True
    return False

# -------------------- ECS FILTER (KEYWORDS ONLY) --------------------
FBP_DefaultEcsTerms = [
    "ECS", "DEPOT", "CARRIAGE SIDINGS", "CARRIAGE SDGS",
    "SIDING", "SIDINGS", "C.S.", "CS", "TMD", "TRSMD",
    "UP SIDINGS", "DOWN SIDINGS"
]

def FBP_ReadExtraEcsTerms():
    try:
        raw = FBP_EcsFilterMem.getValue() if FBP_EcsFilterMem is not None else None
        if not raw: return []
        parts = str(raw).replace(",", ";").split(";")
        out = []
        for p in parts:
            t = p.strip()
            if t:
                out.append(t.upper())
        return out
    except:
        return []

def FBP_IsEcsWorking(row):
    dest = ((row.get("Destination","") or "")).strip().upper()
    call = ((row.get("Calling pattern","") or "")).strip().upper()
    terms = set([t.upper() for t in FBP_DefaultEcsTerms])
    for extra in FBP_ReadExtraEcsTerms():
        terms.add(extra)
    hay = dest + " | " + call
    for t in terms:
        if t and t in hay:
            return True
    return False

# -------------------- NEXT TRAIN FOR A PLATFORM --------------------
def FBP_PickNextTrainForPlatform(platform):
    rows = FBP_CsvRows()

    # "Now" minutes: prefer fast clock, else IMCURRENTTIME
    if FBP_Timebase is not None:
        ft = FBP_Timebase.getTime()
        curMin = ft.getHours()*60 + ft.getMinutes()
    else:
        curStr = FBP_TimeMem.getValue() or ""
        curMin = FBP_ParseMinutes(curStr)
    if curMin is None: return None

    curDay = FBP_DayMem.getValue() or ""
    within = FBP_ReadWithinMinutes()
    cands = []

    for row in rows:
        dep = (row.get("Dep","") or "").strip()
        if not dep:
            continue
        if ((row.get(curDay,"") or "").strip().lower() != "true"):
            continue

        rn   = (row.get("Reporting number","") or "").strip()
        plat = FBP_GetOverride(rn) or FBP_PlatformField(row)
        if str(plat) != str(platform):
            continue

        # ECS filter (keywords only)
        if FBP_IsEcsWorking(row):
            continue

        depMin = FBP_ParseMinutes(dep)
        if depMin is None:
            continue

        # Skip past departures
        if depMin < curMin:
            continue

        # Clear-on-departure (skip if already logged as departed)
        if FBP_HasDepartedAtConfiguredTP(rn, curDay, curMin):
            continue

        # Due within X minutes (wrap-safe)
        delta = (depMin - curMin) % (24*60)
        if not (delta == 0 or (0 <= delta <= within)):
            continue

        arr     = (row.get("Arr","") or "").strip()
        calling = (row.get("Calling pattern","") or "").strip()
        dest    = (row.get("Destination","") or "").strip()

        cands.append({
            "rn": rn,
            "arr": FBP_NormTime(arr),
            "dep": FBP_NormTime(dep),
            "calling": calling,
            "dest": dest
        })

    if not cands: return None
    cands.sort(key=lambda t: FBP_ParseMinutes(t["dep"]))
    return cands[0]

# -------------------- DRAWING PANEL --------------------
class FBP_FingerBoardPanel(swing.JPanel):
    def __init__(self, platform):
        super(FBP_FingerBoardPanel, self).__init__()
        self.setOpaque(True); self.setBackground(FBP_BG_COLOR)
        self.platform = str(platform)
        self.model = None   # None => no board to paint (as if not hoisted)
        self.setLayout(None)
        self.setPreferredSize(self.computePreferred())
        # repaint timer
        def _doRepaint(e):
            self.repaint()
        self.repaintTimer = Timer(800, _doRepaint)
        self.repaintTimer.start()

    def computePreferred(self):
        boardW = 980
        clocksH = FBP_CLOCK_D + FBP_CLOCK_BLOCK_TOP_G + FBP_MARGIN
        height = FBP_MARGIN + max(FBP_BOARD_TOP + FBP_BOARD_H, FBP_CLOCK_D) + clocksH + FBP_MARGIN
        width  = FBP_MARGIN + FBP_POST_W + FBP_BOARD_LEFT_GAP + boardW + FBP_MARGIN
        return Dimension(width, height)

    def setModel(self, m):
        self.model = m; self.repaint()

    # helpers (fit and wrap)
    def fit_font_to_box(self, g2, family, text, maxW, maxH, maxSize, minSize, bold=True):
        style = Font.BOLD if bold else Font.PLAIN
        best = minSize
        for size in range(minSize, maxSize+1):
            f = Font(family, style, size)
            fm = g2.getFontMetrics(f)
            if fm.stringWidth(text) <= maxW and (fm.getAscent()+fm.getDescent()) <= maxH:
                best = size
            else:
                break
        return Font(family, style, best)

    def wrap_text_to_fit(self, g2, family, maxW, maxH, maxSize, minSize, text):
        paragraphs = (text or "").split("\n")
        def wrap_with_font(font):
            fm = g2.getFontMetrics(font)
            perH = fm.getAscent() + fm.getDescent()
            all_lines = []
            for para in paragraphs:
                words = [w for w in para.split() if w]
                if not words:
                    all_lines.append("")
                    continue
                cur = ""
                for w in words:
                    t = (cur + " " + w).strip()
                    if fm.stringWidth(t) <= maxW or not cur:
                        cur = t
                    else:
                        all_lines.append(cur)
                        cur = w
                if cur:
                    all_lines.append(cur)
            neededH = len(all_lines) * perH
            return all_lines, neededH, perH
        for size in range(maxSize, minSize-1, -1):
            f = Font(family, Font.BOLD, size)
            lines, neededH, perH = wrap_with_font(f)
            if neededH <= maxH:
                return f, lines
        f = Font(family, Font.BOLD, minSize)
        lines, neededH, perH = wrap_with_font(f)
        maxLines = max(1, maxH // perH)
        return f, lines[:maxLines]

    def compose_board_text(self):
        if not self.model: return ""
        items = [s.strip() for s in (self.model.get("calling") or "").split(",") if s.strip()]
        calling_text = FBP_CALLING_SEPARATOR.join(items)
        dest_text = (self.model.get("dest") or "").strip()
        if FBP_UPPERCASE_ALL:
            calling_text = calling_text.upper()
            dest_text = dest_text.upper()
        mode = (FBP_TEXT_MODE or "").upper()
        if mode == "DEST_THEN_CALLING":
            if dest_text and calling_text:
                return dest_text + "\n" + calling_text
            elif dest_text:
                return dest_text
            else:
                return calling_text
        return calling_text

    # clock drawing
    def draw_hand_arrow(self, g2, x1, y1, x2, y2, head_len=8):
        g2.drawLine(x1, y1, x2, y2)
        import math
        ang = math.atan2(y2-y1, x2-x1)
        left  = (int(x2 - head_len*math.cos(ang) + (head_len/2)*math.sin(ang)),
                 int(y2 - head_len*math.sin(ang) - (head_len/2)*math.cos(ang)))
        right = (int(x2 - head_len*math.cos(ang) - (head_len/2)*math.sin(ang)),
                 int(y2 - head_len*math.sin(ang) + (head_len/2)*math.cos(ang)))
        poly = awt.Polygon()
        poly.addPoint(x2, y2); poly.addPoint(left[0], left[1]); poly.addPoint(right[0], right[1])
        g2.fillPolygon(poly)

    def draw_roman_clock(self, g2, cx, cy, d, label, timeText, label_side):
        r = d//2
        g2.setColor(FBP_CLOCK_FACE); g2.fillOval(cx - r, cy - r, d, d)
        g2.setColor(FBP_CLOCK_EDGE); g2.setStroke(BasicStroke(3.0)); g2.drawOval(cx - r, cy - r, d, d)
        romans = ["XII","I","II","III","IV","V","VI","VII","VIII","IX","X","XI"]
        inner = r - 26
        maxArcW = int(2*3.14159*(inner)/12 * 0.85)
        size = 16
        while size > 10:
            ftest = Font(FBP_TYPEFACE_NUMERALS, Font.BOLD, size)
            w = max([g2.getFontMetrics(ftest).stringWidth(s) for s in romans])
            if w <= maxArcW: break
            size -= 1
        g2.setFont(Font(FBP_TYPEFACE_NUMERALS, Font.BOLD, size))
        fm = g2.getFontMetrics()
        import math
        for i in range(12):
            a = math.radians(i*30)
            rx = int(cx + inner*math.sin(a))
            ry = int(cy - inner*math.cos(a))
            s = romans[i]
            g2.setColor(FBP_CLOCK_EDGE)
            g2.drawString(s, rx - g2.getFontMetrics().stringWidth(s)//2, ry + fm.getAscent()//2 - 2)
        for i in range(60):
            a = math.radians(i*6)
            if i % 5 == 0:
                x1 = int(cx + (r-12)*math.sin(a)); y1 = int(cy - (r-12)*math.cos(a))
                x2 = int(cx + (r-6)*math.sin(a));  y2 = int(cy - (r-6)*math.cos(a))
                g2.setColor(FBP_CLOCK_TICK); g2.setStroke(BasicStroke(2.2))
                g2.drawLine(x1,y1,x2,y2)
            else:
                x = int(cx + (r-8)*math.sin(a)); y = int(cy - (r-8)*math.cos(a))
                g2.setColor(Color(150,150,150)); g2.fillOval(x-1,y-1,2,2)
        if timeText:
            try:
                t = FBP_TimeParser24.parse(timeText)
                h = t.getHours() % 12
                m = t.getMinutes()
                min_a = __import__("math").radians(m*6.0)
                hr_a  = __import__("math").radians(h*30.0 + m*0.5)
                g2.setColor(FBP_CLOCK_HAND)
                g2.setStroke(BasicStroke(3.0))
                mx = int(cx + (r-20)*__import__("math").sin(min_a))
                my = int(cy - (r-20)*__import__("math").cos(min_a))
                self.draw_hand_arrow(g2, cx, cy, mx, my, head_len=7)
                g2.setStroke(BasicStroke(4.8))
                hx = int(cx + (r-34)*__import__("math").sin(hr_a))
                hy = int(cy - (r-34)*__import__("math").cos(hr_a))
                self.draw_hand_arrow(g2, cx, cy, hx, hy, head_len=8)
                g2.fillOval(cx-3, cy-3, 6, 6)
            except:
                pass
        # label box
        boxH = FBP_LABEL_BOX_H
        if label_side == "left":
            maxW = (cx - r) - (FBP_MARGIN + FBP_POST_W) - 2*FBP_LABEL_BOX_PAD_TXT
            boxW = min(FBP_LABEL_BOX_MAX_W, max(60, maxW))
            bx = (FBP_MARGIN + FBP_POST_W) + FBP_LABEL_BOX_PAD_TXT
            by = cy - boxH//2
        else:
            maxW = (self.getWidth() - FBP_MARGIN) - (cx + r) - 2*FBP_LABEL_BOX_PAD_TXT
            boxW = min(FBP_LABEL_BOX_MAX_W, max(60, maxW))
            bx = self.getWidth() - FBP_MARGIN - FBP_LABEL_BOX_PAD_TXT - boxW
            by = cy - boxH//2
        g2.setColor(FBP_LABEL_BOX_FILL); g2.fillRoundRect(bx, by, boxW, boxH, 8,8)
        g2.setColor(FBP_LABEL_BOX_EDGE); g2.setStroke(BasicStroke(2.0))
        inset = FBP_LABEL_BOX_INSET
        g2.drawRoundRect(bx+inset, by+inset, boxW-2*inset, boxH-2*inset, 6,6)
        label_txt = label.upper()
        f = self.fit_font_to_box(g2, FBP_TYPEFACE_PRIMARY, label_txt,
                                 boxW-2*FBP_LABEL_BOX_PAD_TXT, boxH-2*FBP_LABEL_BOX_PAD_TXT,
                                 FBP_LABEL_FONT_MAX, FBP_LABEL_FONT_MIN, bold=True)
        g2.setFont(f); g2.setColor(FBP_TEXT_COLOR)
        fmL = g2.getFontMetrics()
        tx = bx + (boxW - fmL.stringWidth(label_txt))//2
        ty = by + (boxH + fmL.getAscent() - fmL.getDescent())//2
        g2.drawString(label_txt, tx, ty)

    def paintComponent(self, g):
        super(FBP_FingerBoardPanel, self).paintComponent(g)
        g2 = g
        if isinstance(g, awt.Graphics2D):
            g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g2.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_LCD_HRGB)
        W = self.getWidth(); H = self.getHeight()

        # Post (always present)
        postX = FBP_MARGIN; postY = FBP_MARGIN; postH = H - 2*FBP_MARGIN
        g2.setPaint(GradientPaint(postX, postY, FBP_POST_COLOR, postX+FBP_POST_W, postY, FBP_POST_SHADE))
        g2.fillRoundRect(postX, postY, FBP_POST_W, postH, FBP_POST_RADIUS, FBP_POST_RADIUS)

        # Board/clock layout refs
        boardX = postX + FBP_POST_W + FBP_BOARD_LEFT_GAP
        boardY = FBP_MARGIN + FBP_BOARD_TOP
        boardW = W - boardX - FBP_MARGIN

        # Draw plank + text only if a model exists
        if self.model is not None:
            rectW  = max(100, boardW - FBP_CAP_RADIUS)
            plank  = Area(RoundRectangle2D.Float(boardX, boardY, rectW, FBP_BOARD_H, 6, 6))
            cap    = Area(Ellipse2D.Float(boardX + rectW - FBP_CAP_RADIUS, boardY, 2*FBP_CAP_RADIUS, FBP_BOARD_H))
            plank.add(cap)
            g2.setColor(FBP_BOARD_FILL); g2.fill(plank)
            g2.setColor(FBP_BOARD_EDGE); g2.setStroke(FBP_OUTLINE_STROKE); g2.draw(plank)
            textL = boardX + FBP_LEFT_PAD
            textR = boardX + boardW - FBP_RIGHT_PAD
            textW = max(50, textR - textL)
            textT = boardY + 10
            textH = FBP_BOARD_H - 20
            board_text = self.compose_board_text()
            f, lines = self.wrap_text_to_fit(g2, FBP_TYPEFACE_PRIMARY, textW, textH,
                                             FBP_LINE_FONT_MAX, FBP_LINE_FONT_MIN, board_text)
            g2.setColor(FBP_TEXT_COLOR); g2.setFont(f)
            fm = g2.getFontMetrics()
            y = textT + fm.getAscent()
            for ln in lines:
                g2.drawString(ln, textL, y)
                y += (fm.getAscent()+fm.getDescent())

        # Clocks + labels (optionally hidden when empty)
        hideClocksWhenEmpty = FBP_ReadHideClocksWhenEmpty()
        clocksW = 2*FBP_CLOCK_D + FBP_CLOCK_PAIR_GAP
        cx1 = boardX + (boardW - clocksW)//2 + FBP_CLOCK_D//2
        cx2 = cx1 + FBP_CLOCK_D + FBP_CLOCK_PAIR_GAP
        cy  = boardY + FBP_BOARD_H + FBP_CLOCK_BLOCK_TOP_G + FBP_CLOCK_D//2

        if (self.model is None) and hideClocksWhenEmpty:
            # When empty and toggle is on: draw no clocks at all
            return

        arrTxt = self.model["arr"] if (self.model and self.model["arr"]) else None
        depTxt = self.model["dep"] if (self.model and self.model["dep"]) else None
        self.draw_roman_clock(g2, cx1, cy, FBP_CLOCK_D, "ARR", arrTxt, label_side="left")
        self.draw_roman_clock(g2, cx2, cy, FBP_CLOCK_D, "DEP", depTxt, label_side="right")

# -------------------- WINDOW PER PLATFORM --------------------
class FBP_FingerBoardWindow(object):
    def __init__(self, platform):
        self.platform = str(platform)
        self.panel = FBP_FingerBoardPanel(self.platform)
        preferred = self.panel.getPreferredSize()
        self.frame = swing.JFrame("Finger board - Platform " + self.platform)
        cp = self.frame.getContentPane()
        cp.setLayout(None); cp.setBackground(FBP_BG_COLOR)
        cp.setPreferredSize(preferred)
        self.panel.setBounds(0,0, preferred.width, preferred.height)
        cp.add(self.panel)
        self.frame.pack()     
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[PIDCRTFingerboard] Failed to set PID window icon: " + str(ex))
       
        self.frame.setResizable(False)
        self.frame.setVisible(True)

        # listeners
        FBP_TimeMem.addPropertyChangeListener(self.refresh)
        FBP_DayMem.addPropertyChangeListener(self.refresh)
        if FBP_TimetableMem is not None: FBP_TimetableMem.addPropertyChangeListener(self.refresh)
        if FBP_OverridesMem is not None: FBP_OverridesMem.addPropertyChangeListener(self.refresh)
        if FBP_DepartTPMem is not None: FBP_DepartTPMem.addPropertyChangeListener(self.refresh)
        if FBP_EcsFilterMem is not None: FBP_EcsFilterMem.addPropertyChangeListener(self.refresh)
        if FBP_WithInMinMem is not None: FBP_WithInMinMem.addPropertyChangeListener(self.refresh)
        if FBP_HideClocksEmptyMem is not None: FBP_HideClocksEmptyMem.addPropertyChangeListener(self.refresh)

        self.refresh()

    def refresh(self, e=None):
        m = FBP_PickNextTrainForPlatform(self.platform)
        self.panel.setModel(m)

    def cleanup(self):
        try: FBP_TimeMem.removePropertyChangeListener(self.refresh)
        except: pass
        try: FBP_DayMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_TimetableMem is not None: FBP_TimetableMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_OverridesMem is not None: FBP_OverridesMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_DepartTPMem is not None: FBP_DepartTPMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_EcsFilterMem is not None: FBP_EcsFilterMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_WithInMinMem is not None: FBP_WithInMinMem.removePropertyChangeListener(self.refresh)
        except: pass
        try:
            if FBP_HideClocksEmptyMem is not None: FBP_HideClocksEmptyMem.removePropertyChangeListener(self.refresh)
        except: pass

# -------------------- MANAGER — windows per platform --------------------
def FBP_DetectPlatforms():
    plats = set()
    for r in FBP_CsvRows():
        p = FBP_PlatformField(r)
        if p: plats.add(str(p))
    return sorted(plats, key=lambda x:(x.isdigit(), int(x) if x.isdigit() else x))

class FBP_PlatformFingerBoards(object):
    def __init__(self):
        self.windows = {}
        if FBP_TimetableMem is not None: FBP_TimetableMem.addPropertyChangeListener(self.rebuild)
        if FBP_OverridesMem is not None: FBP_OverridesMem.addPropertyChangeListener(self.refresh_all)
        if FBP_DepartTPMem is not None:  FBP_DepartTPMem.addPropertyChangeListener(self.refresh_all)
        if FBP_EcsFilterMem is not None: FBP_EcsFilterMem.addPropertyChangeListener(self.refresh_all)
        if FBP_WithInMinMem is not None: FBP_WithInMinMem.addPropertyChangeListener(self.refresh_all)
        if FBP_HideClocksEmptyMem is not None: FBP_HideClocksEmptyMem.addPropertyChangeListener(self.refresh_all)
        self.build()

    def build(self):
        plats = FBP_DetectPlatforms()
        for p in plats:
            if p not in self.windows:
                self.windows[p] = FBP_FingerBoardWindow(p)
        for p in [x for x in list(self.windows.keys()) if x not in plats]:
            try:
                self.windows[p].cleanup(); self.windows[p].frame.dispose()
            except:
                pass
            del self.windows[p]
        # cascade
        x0,y0,dx,dy = 40,40, 22,22
        for i,p in enumerate(self.windows.keys()):
            self.windows[p].frame.setLocation(x0 + dx*i, y0 + dy*i)

    def rebuild(self, e=None):
        self.build(); self.refresh_all()

    def refresh_all(self, e=None):
        for w in self.windows.values():
            w.refresh()

# -------------------- RUN --------------------
FBP_Manager = FBP_PlatformFingerBoards()