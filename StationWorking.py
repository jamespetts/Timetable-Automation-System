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
# StationWorkingBookDisplay - JMRI 5.14 / Jython 2.7
# A station working display based on station working books, using the TAS timetable CSV.
#
# <<SIG-DISP-NAME: Station working>>
# <<DESCRIPTION: Shows station workings (arrival/departure/platform/remarks) in a station-working-book format, with optional auto-follow of the next expected train (delay-aware).>>
#
import os
import csv
import re
import jmri
from jmri.util import JmriJFrame
from java.text import SimpleDateFormat
from java.awt import BorderLayout, Color, Dimension, Font, FlowLayout, Point
from java.awt.event import KeyEvent, MouseWheelListener
from java.awt.event import ComponentAdapter
from javax.swing import JTable, JLabel, JPanel, JScrollPane, SwingConstants, BorderFactory, JButton, JCheckBox
from javax.swing import KeyStroke, JComponent, AbstractAction
from javax.swing.table import DefaultTableModel, DefaultTableCellRenderer
from javax.swing.table import TableCellRenderer
from javax.swing import JTextArea
from javax.swing import SwingUtilities
from javax.swing.event import TableColumnModelListener
from java.lang import System

import TASBeanLookup as TBL
import TASUtil as TU  # IsDefaultReportingNumber(s), MakeDefaultReportingNumberFromRow(rowNumber)
from DisruptionRegister import getDisruption

# --------------------
# Memory helpers (shared style with WTTDisplay)
# --------------------

def _ReadMemStr(suffix, default=""):
    try:
        val = TBL.SafeGetMemoryValue(suffix, default)
        s = "" if val is None else str(val).strip()
        return s if s else default
    except:
        return default


def _ReadMemBool(suffix, default=False):
    s = _ReadMemStr(suffix, "")
    t = ("" if s is None else str(s)).strip().lower()
    if t in ("1", "true", "yes", "y", "on", "enabled"):
        return True
    if t in ("0", "false", "no", "n", "off", "disabled"):
        return False
    return bool(default)


def _RgbStrToColor(rgbStr, fallback):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) != 3:
            return fallback
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
        return Color(r, g, b)
    except:
        return fallback


# --------------------
# Options (inherit where meaningful from WTTDisplay)
# --------------------
PAGE_MODE = _ReadMemStr("WTT_PAGE_MODE", "WEEKDAYS_SAT_SUN")
TIME_24H = _ReadMemBool("WTT_TIME_24H", True)
TIME_SEPARATOR = _ReadMemStr("WTT_TIME_SEPARATOR", " ")[:1]

# Styles
PAPER = _RgbStrToColor(_ReadMemStr("TASPAPERCOLOUR", "249,246,238"), Color(249, 246, 238))
RULE = Color(60, 60, 60)
HEADER_BG = PAPER
ROW_A = _RgbStrToColor(_ReadMemStr("TASWTTBANDLIGHT", "255,253,247"), Color(255, 253, 247))
ROW_B = _RgbStrToColor(_ReadMemStr("TASWTTBANDDARK", "245,242,235"), Color(245, 242, 235))

MAJOR_RULE_THICK = 2
MINOR_RULE_THICK = 1
LEFT_PAGE_PADDING = 16

SCROLLBAR_RIGHT_PADDING = 10
_fontFam = _ReadMemStr("TAS_FONT_FAMILY", "Gill Sans MT")
try:
    BASE_FONT = Font(_fontFam, Font.PLAIN, 14)
    HEADER_FONT = Font(_fontFam, Font.BOLD, 14)
    TITLE_FONT = Font(_fontFam, Font.BOLD, 18)
except:
    BASE_FONT = Font("Serif", Font.PLAIN, 14)
    HEADER_FONT = Font("Serif", Font.BOLD, 14)
    TITLE_FONT = Font("Serif", Font.BOLD, 18)

DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_TOKEN = {"Monday":"M", "Tuesday":"T", "Wednesday":"W", "Thursday":"Th", "Friday":"F", "Saturday":"S", "Sunday":"Su"}

def ComputeRunCode(daysFlags, groupDays):
    # Copy of WTTDisplay ComputeRunCode: returns codes like FX (Friday excluded) or MTO (Mon/Tue only).
    ordered = [d for d in DAYS_ORDER if d in (groupDays or [])]
    presentDays = [d for d in ordered if (daysFlags or {}).get(d, False)]
    missingDays = [d for d in ordered if not (daysFlags or {}).get(d, False)]
    if len(presentDays) == 0 or len(missingDays) == 0:
        return ""
    presentCore = "".join([DAY_TOKEN[d] for d in presentDays])
    missingCore = "".join([DAY_TOKEN[d] for d in missingDays])
    return (missingCore + "X") if (len(missingCore) < len(presentCore)) else (presentCore + "O")



def GetProfileName():
    name = "PROFILE"
    try:
        from jmri.profile import ProfileManager
        p = ProfileManager.getDefault().getActiveProfile()
        if p is not None and p.getName() is not None:
            name = p.getName()
    except:
        try:
            from apps import Apps
            p = Apps.getProfileManager().getActiveProfile()
            if p is not None and p.getName() is not None:
                name = p.getName()
        except:
            pass
    return name


# --------------------
# Time helpers
# --------------------
_sdf_parse_12 = SimpleDateFormat("h:mm a")
_sdf_parse_24 = SimpleDateFormat("H:mm")
_sdf_out_24 = SimpleDateFormat("HH:mm")
_sdf_out_12 = SimpleDateFormat("h:mm a")


def _ParseMinutes(s):
    if s is None:
        return None
    ss = str(s).strip()
    if ss == "":
        return None
    for parser in (_sdf_parse_12, _sdf_parse_24):
        try:
            dt = parser.parse(ss)
            hhmm = _sdf_out_24.format(dt)
            return int(hhmm[:2]) * 60 + int(hhmm[3:5])
        except:
            pass
    return None


def FormatTime(s):
    if s is None:
        return ""
    ss = str(s).strip()
    if ss == "":
        return ""
    for parser in (_sdf_parse_12, _sdf_parse_24):
        try:
            dt = parser.parse(ss)
            out = _sdf_out_24.format(dt) if TIME_24H else _sdf_out_12.format(dt)
            return out.replace(":", TIME_SEPARATOR) if TIME_SEPARATOR != ":" else out
        except:
            pass
    return ss


# --------------------
# Day grouping (same concept as WTTDisplay)
# --------------------

def DayGroupsFromMode(mode):
    if mode == "SEVEN_DAYS":
        return [("MONDAYS", ["Monday"]), ("TUESDAYS", ["Tuesday"]), ("WEDNESDAYS", ["Wednesday"]),
                ("THURSDAYS", ["Thursday"]), ("FRIDAYS", ["Friday"]), ("SATURDAYS", ["Saturday"]), ("SUNDAYS", ["Sunday"])]
    if mode == "WEEKDAYS_SAT_SUN":
        return [("WEEKDAYS", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
                ("SATURDAYS", ["Saturday"]), ("SUNDAYS", ["Sunday"])]
    if mode == "MONSAT_PLUS_SUN":
        return [("MON-SAT", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]),
                ("SUNDAYS", ["Sunday"])]
    if mode == "ALL_WEEK":
        return [("WEEK", DAYS_ORDER[:])]
    return DayGroupsFromMode("SEVEN_DAYS")


def _ScoreRowForGroup(svc, groupDays):
    inside = 0
    outside = 0
    for d in DAYS_ORDER:
        flag = svc.get("days", {}).get(d, False)
        if d in groupDays:
            if flag:
                inside += 1
        else:
            if flag:
                outside += 1
    return inside * 100 - outside


# --------------------
# CSV import
# --------------------

_TP_HEADER_PAT = re.compile(r"^TP(\d*)(Arr|Dep)\s+(.+)$", re.IGNORECASE)


def ResolveTimetableCsvPath():
    timetableName = _ReadMemStr("CURRENTTIMETABLE", "Default timetable")
    profilePath = None
    try:
        from jmri.profile import ProfileManager
        p = ProfileManager.getDefault().getActiveProfile()
        if p is not None:
            profilePath = p.getPath().toString()
    except:
        try:
            from apps import Apps
            p = Apps.getProfileManager().getActiveProfile()
            if p is not None:
                profilePath = p.getPath().toString()
        except:
            pass
    if profilePath is None:
        profilePath = os.getcwd()
    return os.path.join(profilePath, "timetable", timetableName + ".csv")


def LoadServicesMaster(csvPath):
    services = []
    if not os.path.exists(csvPath):
        return services

    # Detect delimiter
    try:
        with open(csvPath, "r") as fh:
            sniff = fh.read(4096)
            delim = "\t" if ("\t" in sniff) else ","
    except:
        delim = ","

    try:
        with open(csvPath, "r") as f:
            reader = csv.DictReader(f, delimiter=delim)
            try:
                rows = list(reader)
            except:
                rows = []
    except:
        return services

    header = []
    try:
        header = reader.fieldnames or []
    except:
        header = []

    tpNames = set()
    for h in header:
        hs = (h or "").strip()
        if not hs:
            continue
        m = _TP_HEADER_PAT.match(hs)
        if not m:
            continue
        name = (m.group(3) or "").strip()
        if name:
            tpNames.add(name)

    for rowIndex, row in enumerate(rows, start=2):
        if not isinstance(row, dict):
            continue

        def Get(k):
            v = row.get(k, "")
            return ("" if v is None else str(v)).strip()

        rep = Get("Reporting number")
        if rep == "":
            rep = TU.MakeDefaultReportingNumberFromRow(rowIndex)

        days = {}
        for d in DAYS_ORDER:
            v = Get(d)
            days[d] = (v.upper() in ("TRUE", "T", "1", "Y", "YES"))

        tpTimes = {}
        for nm in tpNames:
            a = ""
            d = ""
            for k in row.keys():
                ks = ("" if k is None else str(k)).strip()
                m2 = _TP_HEADER_PAT.match(ks)
                if not m2:
                    continue
                kind = (m2.group(2) or "").strip().lower()
                name2 = (m2.group(3) or "").strip()
                if name2 != nm:
                    continue
                vv = row.get(k)
                vv = ("" if vv is None else str(vv)).strip()
                if kind == "arr":
                    a = vv
                else:
                    d = vv
            tpTimes[nm] = {"arr": a, "dep": d}

        services.append({
            "rep": rep,
            "dir": Get("Direction").upper(),
            "trigger": Get("Trigger"),
            "arr": Get("Arr"),
            "dep": Get("Dep"),
            "origin": Get("Origin"),
            "dest": Get("Destination"),
            "plat": Get("Platform"),
            "notes": Get("Notes"),
            "remarks": Get("Remarks"),
            "forms": Get("Forms"),
            "calling": Get("Calling pattern"),
            "special": Get("Special"),
            "via": Get("Via"),
            "tp": tpTimes,
            "days": days
        })

    return services


# --------------------
# Remarks expansion
# --------------------

def _FindTimingPointTimeForStation(svc, stationName, layoutName):
    if stationName is None:
        return None
    st = str(stationName).strip()
    if st == "":
        return None

    try:
        if layoutName is not None and st.lower() == str(layoutName).strip().lower():
            a = (svc.get("arr", "") or "").strip()
            d = (svc.get("dep", "") or "").strip()
            t = a if a != "" else d
            return FormatTime(t) if t else None
    except:
        pass

    tpmap = svc.get("tp", {}) or {}
    for k in tpmap.keys():
        try:
            if str(k).strip().lower() == st.lower():
                m = tpmap.get(k) or {}
                a = (m.get("arr", "") or "").strip()
                d = (m.get("dep", "") or "").strip()
                t = a if a != "" else d
                return FormatTime(t) if t else None
        except:
            pass
    return None


def _ExpandCallingPattern(svc, layoutName):
    cp = (svc.get("calling", "") or "").strip()
    if cp == "":
        return ""
    parts = [p.strip() for p in cp.split(",")]
    out = []
    for p in parts:
        if p == "":
            continue
        t = _FindTimingPointTimeForStation(svc, p, layoutName)
        out.append("%s (%s)" % (p, t) if t else p)
    return ", ".join(out)


def ExpandRemarks(svc, layoutName):
    raw = (svc.get("remarks", "") or "")
    text = str(raw)
    notes = (svc.get("notes", "") or "")
    forms = (svc.get("forms", "") or "")
    special = (svc.get("special", "") or "")
    via = (svc.get("via", "") or "")

    def _ReplCalling(m):
        return _ExpandCallingPattern(svc, layoutName)

    try:
        text = re.sub(r"\{\s*calling\s*pattern\s*\}", _ReplCalling, text, flags=re.IGNORECASE)
    except:
        pass
    try:
        text = re.sub(r"\{\s*notes\s*\}", notes, text, flags=re.IGNORECASE)
    except:
        pass
    try:
        text = re.sub(r"\{\s*forms\s*\}", forms, text, flags=re.IGNORECASE)
    except:
        pass

    try:
        text = re.sub(r"\{\s*special\s*\}", special, text, flags=re.IGNORECASE)
    except:
        pass

    try:
        text = re.sub(r"\{\s*via\s*\}", via, text, flags=re.IGNORECASE)
    except:
        pass
    # Special marker: {\n} forces a newline in the rendered Remarks.
    # This allows structured, multi-line remarks in the timetable CSV.
    try:
        text = re.sub(r"\{\s*\\n\s*\}", "\n", text, flags=re.IGNORECASE)
    except:
        pass

    # Normalize whitespace but preserve explicit newlines.
    try:
        parts = str(text).split("\n")
        outParts = []
        for p in parts:
            outParts.append(" ".join(str(p).split()))
        return "\n".join(outParts)
    except:
        return " ".join(str(text).split())
# --------------------
# Delay / expected time helpers (including inherited Forms disruptions)
# --------------------

def _BuildFormsFromMap(services):
    formsFrom = {}
    for svc in services:
        rn = (svc.get("rep", "") or "").strip()
        nxt = (svc.get("forms", "") or "").strip()
        if rn and nxt:
            formsFrom.setdefault(nxt, []).append(rn)
    return formsFrom


def _BuildTrainDaysMap(master):
    m = {}
    for svc in master:
        rn = (svc.get("rep", "") or "").strip()
        if rn:
            m[rn] = svc.get("days", {}) or {}
    return m


def _EffectiveDelayMinutesForRn(rn, todayDay, trainDaysByRn, formsFrom):
    if rn in (None, ""):
        return None
    if formsFrom is not None and rn in formsFrom:
        for src in formsFrom.get(rn, []):
            try:
                if trainDaysByRn.get(src, {}).get(todayDay, False):
                    inh = getDisruption(src)
                    if inh is not None:
                        return inh
            except:
                pass
    return getDisruption(rn)


def _ServiceKeyTimeMinutes(svc):
    trig = (svc.get("trigger", "") or "").strip()
    arr = (svc.get("arr", "") or "").strip()
    dep = (svc.get("dep", "") or "").strip()
    return _ParseMinutes(trig) or _ParseMinutes(arr) or _ParseMinutes(dep)


# --------------------
# UI
# --------------------

frame = JmriJFrame("Station working")
frame.setDefaultCloseOperation(JmriJFrame.DISPOSE_ON_CLOSE)

root = JPanel(BorderLayout(0, 0))
root.setBackground(PAPER)
root.setBorder(BorderFactory.createEmptyBorder(0, LEFT_PAGE_PADDING, 0, 0))

headerPanel = JPanel(BorderLayout())
headerPanel.setBackground(PAPER)
leftHeader = JLabel(GetProfileName())
centerHeader = JLabel("")
rightHeader = JLabel("")
for lbl in (leftHeader, centerHeader, rightHeader):
    lbl.setOpaque(True)
    lbl.setBackground(PAPER)
    lbl.setForeground(Color(0, 0, 0))
    lbl.setFont(TITLE_FONT)
    lbl.setBorder(BorderFactory.createEmptyBorder(6, 12, 6, 12))
leftHeader.setHorizontalAlignment(SwingConstants.LEFT)
centerHeader.setHorizontalAlignment(SwingConstants.CENTER)
rightHeader.setHorizontalAlignment(SwingConstants.RIGHT)
headerPanel.add(leftHeader, BorderLayout.WEST)
headerPanel.add(centerHeader, BorderLayout.CENTER)
headerPanel.add(rightHeader, BorderLayout.EAST)
headerPanel.setBorder(BorderFactory.createMatteBorder(MAJOR_RULE_THICK, MAJOR_RULE_THICK, MINOR_RULE_THICK, MAJOR_RULE_THICK, RULE))

# Controls (moved to bottom)
controlsPanel = JPanel(FlowLayout(FlowLayout.LEFT, 6, 0))
controlsPanel.setBackground(PAPER)
btnPrev = JButton("<")
btnNext = JButton(">")
btnSnap = JButton("Snap")
chkFollow = JCheckBox("Auto-follow", False)
for b in (btnPrev, btnNext, btnSnap, chkFollow):
    b.setFont(BASE_FONT)
controlsPanel.add(btnPrev)
controlsPanel.add(btnNext)
controlsPanel.add(btnSnap)
controlsPanel.add(chkFollow)

statusLabel = JLabel("")
statusLabel.setFont(BASE_FONT)
statusLabel.setForeground(Color(0, 0, 0))
statusLabel.setBackground(PAPER)
statusLabel.setOpaque(True)
controlsPanel.add(statusLabel)

# Table and scroll
_tableModel = DefaultTableModel([], [])


class WrapCellRenderer(JTextArea, TableCellRenderer):
    # TableCellRenderer implementation that wraps text and lets us measure preferred height.
    def __init__(self, baseRenderer):
        JTextArea.__init__(self)
        self.Base = baseRenderer
        self.setLineWrap(True)
        self.setWrapStyleWord(True)
        self.setOpaque(True)
        try:
            self.setAlignmentY(0.0)
        except:
            pass

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        # Apply consistent colours and highlight.
        bg = self.Base._ApplyHighlight(self.Base._RowBg(row), row)
        self.setBackground(bg)
        self.setForeground(Color(0, 0, 0))
        self.setFont(BASE_FONT)
        self.setText("" if value is None else str(value))
        try:
            self.setCaretPosition(0)
        except:
            pass
        top = 0
        self.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createMatteBorder(top, MINOR_RULE_THICK, MINOR_RULE_THICK, MINOR_RULE_THICK, RULE), BorderFactory.createEmptyBorder(5, 3, 5, 3)))
        return self


def _Clamp8(v):
    return max(0, min(255, int(v)))


def _AdjustColor(c, delta):
    try:
        r = _Clamp8(c.getRed() + delta)
        g = _Clamp8(c.getGreen() + delta)
        b = _Clamp8(c.getBlue() + delta)
        return Color(r, g, b)
    except:
        return c


class SWBCellRenderer(DefaultTableCellRenderer):
    def __init__(self):
        DefaultTableCellRenderer.__init__(self)
        self.HighlightModelRow = -1
        self.setOpaque(True)

    def _RowBg(self, row):
        return ROW_A if (row % 2 == 0) else ROW_B

    def _ApplyHighlight(self, bg, row):
        if self.HighlightModelRow >= 0 and row == self.HighlightModelRow:
            darker = _AdjustColor(bg, -18)
            if (abs(darker.getRed() - bg.getRed()) + abs(darker.getGreen() - bg.getGreen()) + abs(darker.getBlue() - bg.getBlue())) < 12:
                return _AdjustColor(bg, 22)
            return darker
        return bg

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        comp = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column)
        comp.setFont(BASE_FONT)
        comp.setForeground(Color(0, 0, 0))
        bg = self._ApplyHighlight(self._RowBg(row), row)
        comp.setBackground(bg)
        try:
            name = str(table.getColumnName(column))
        except:
            name = ""
        if name in ("No.", "Pfm"):
            comp.setHorizontalAlignment(SwingConstants.CENTER)
        else:
            comp.setHorizontalAlignment(SwingConstants.LEFT)
        comp.setVerticalAlignment(SwingConstants.TOP)
        top = 0
        comp.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createMatteBorder(top, MINOR_RULE_THICK, MINOR_RULE_THICK, MINOR_RULE_THICK, RULE), BorderFactory.createEmptyBorder(5, 3, 5, 3)))
        return comp




class HeaderCellRenderer(DefaultTableCellRenderer):
    # Header renderer with rule weight matching body grid lines.
    def __init__(self):
        DefaultTableCellRenderer.__init__(self)
        self.setOpaque(True)

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        comp = DefaultTableCellRenderer.getTableCellRendererComponent(self, table, value, False, False, row, column)
        comp.setFont(HEADER_FONT)
        comp.setForeground(Color(0, 0, 0))
        comp.setBackground(HEADER_BG)
        comp.setVerticalAlignment(SwingConstants.TOP)
        try:
            name = str(table.getColumnName(column))
        except:
            name = ""
        if name in ("No.", "Pfm"):
            comp.setHorizontalAlignment(SwingConstants.CENTER)
        else:
            comp.setHorizontalAlignment(SwingConstants.LEFT)
        # Match body line weight/colour; add small horizontal padding.
        try:
            b = BorderFactory.createMatteBorder(MINOR_RULE_THICK, MINOR_RULE_THICK, MINOR_RULE_THICK, MINOR_RULE_THICK, RULE)
            comp.setBorder(BorderFactory.createCompoundBorder(b, BorderFactory.createEmptyBorder(5, 3, 5, 3)))
        except:
            pass
        return comp


_headerRenderer = HeaderCellRenderer()
_swbRenderer = SWBCellRenderer()

class DepCellRenderer(JTextArea, TableCellRenderer):
    # Multi-line renderer for Dep column (time + optional run code on next line).
    def __init__(self, baseRenderer):
        JTextArea.__init__(self)
        self.Base = baseRenderer
        self.setLineWrap(False)
        self.setWrapStyleWord(False)
        self.setOpaque(True)
        try:
            self.setEditable(False)
        except:
            pass
        try:
            self.setAlignmentY(0.0)
        except:
            pass

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        bg = self.Base._ApplyHighlight(self.Base._RowBg(row), row)
        self.setBackground(bg)
        self.setForeground(Color(0, 0, 0))
        self.setFont(BASE_FONT)
        self.setText("" if value is None else str(value))
        try:
            self.setCaretPosition(0)
        except:
            pass
        top = 0
        try:
            self.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createMatteBorder(top, MINOR_RULE_THICK, MINOR_RULE_THICK, MINOR_RULE_THICK, RULE), BorderFactory.createEmptyBorder(5, 3, 5, 3)))
        except:
            pass
        return self

_depRenderer = DepCellRenderer(_swbRenderer)
_wrapRenderer = WrapCellRenderer(_swbRenderer)


class SWBJTable(JTable):
    # Ensure that the row height always matches the wrapped Remarks text.
    # This recalculates during painting, and we also provide explicit recalculation on column resize.
    def __init__(self, model):
        JTable.__init__(self, model)

    def prepareRenderer(self, renderer, row, column):
        comp = JTable.prepareRenderer(self, renderer, row, column)
        try:
            colName = str(self.getColumnName(column))
        except:
            colName = ""
        if colName in ("Remarks", "Dep"):
            try:
                colW = self.getColumnModel().getColumn(column).getWidth()
                comp.setSize(Dimension(colW, 100000))
                prefH = comp.getPreferredSize().height
                if prefH is None:
                    prefH = 36
                prefH = max(36, int(prefH))
                curH = self.getRowHeight(row)
                if curH < prefH:
                    self.setRowHeight(row, prefH)
            except:
                pass
        return comp


_table = SWBJTable(_tableModel)
_table.setFont(BASE_FONT)
_table.setRowHeight(36)
_table.setShowGrid(False)
_table.setIntercellSpacing(Dimension(0, 0))
_table.setAutoResizeMode(JTable.AUTO_RESIZE_LAST_COLUMN)
_table.setRowSelectionAllowed(False)
_table.setColumnSelectionAllowed(False)
_table.setCellSelectionEnabled(False)
_table.setFocusable(False)
_table.setRequestFocusEnabled(False)

scroll = JScrollPane(_table)
scroll.setBackground(PAPER)
scroll.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_NEVER)
try:
    scroll.setViewportBorder(BorderFactory.createMatteBorder(0, 0, 0, SCROLLBAR_RIGHT_PADDING, PAPER))
except:
    pass
try:
    scroll.getColumnHeader().setBorder(BorderFactory.createMatteBorder(0, 0, 0, SCROLLBAR_RIGHT_PADDING, PAPER))
except:
    pass
scroll.getViewport().setBackground(PAPER)
scroll.setBorder(BorderFactory.createMatteBorder(0, MAJOR_RULE_THICK, MAJOR_RULE_THICK, MAJOR_RULE_THICK, RULE))

# Footer: controls + page indicator (moved to bottom)
footerPanel = JPanel(BorderLayout())
footerPanel.setBackground(PAPER)
footerPanel.setBorder(BorderFactory.createEmptyBorder(4, MAJOR_RULE_THICK, 4, MAJOR_RULE_THICK))
pageLabel = JLabel("")
pageLabel.setFont(BASE_FONT)
footerPanel.add(controlsPanel, BorderLayout.CENTER)
footerPanel.add(pageLabel, BorderLayout.EAST)

root.add(headerPanel, BorderLayout.NORTH)
root.add(scroll, BorderLayout.CENTER)
root.add(footerPanel, BorderLayout.SOUTH)

frame.setContentPane(root)

try:
    from TASIcon import SetFrameClockIcon
    SetFrameClockIcon(frame, 32)
except:
    pass


# --------------------
# State
# --------------------

_state = {
    "master": [],
    "pages": [],
    "pageIndex": 0,
    "total": 1,
    "formsFrom": {},
    "trainDays": {},
    "hideNo": False,
    "hideDir": False,
    "hidePfm": False,
    "layoutName": GetProfileName(),
    "currentDay": _ReadMemStr("DAYOFWEEK", ""),
    "currentTime": _ReadMemStr("CURRENTTIME", "")
}


def _BuildPages(master):
    # Build pages for day-groups, skipping any groups that have zero services (as per WTTDisplay).
    groups = DayGroupsFromMode(PAGE_MODE)
    pages = []
    for label, days in groups:
        best = {}
        orderKeys = []
        for idx, svc in enumerate(master):
            hasAny = False
            for d in days:
                if svc.get("days", {}).get(d, False):
                    hasAny = True
                    break
            if not hasAny:
                continue
            rep = (svc.get("rep", "") or "").strip()
            if rep == "":
                continue
            sc = _ScoreRowForGroup(svc, days)
            if rep not in best:
                best[rep] = (sc, idx, svc)
                orderKeys.append(rep)
            else:
                if sc > best[rep][0]:
                    best[rep] = (sc, best[rep][1], svc)
        items = [best[rep][2] for rep in orderKeys]
        if items:
            pages.append({"label": label, "days": days, "items": items})

    if not pages:
        pages = [{"label": "WEEK", "days": DAYS_ORDER[:], "items": []}]
    return pages

def _DecideColumnHiding(master):
    showNo = False
    showDir = False
    showPfm = False
    for svc in master:
        rn = (svc.get("rep", "") or "").strip()
        if rn and (not TU.IsDefaultReportingNumber(rn)):
            showNo = True
        if (svc.get("dir", "") or "").strip() != "":
            showDir = True
        if (svc.get("plat", "") or "").strip() != "":
            showPfm = True
    _state["hideNo"] = (not showNo)
    _state["hideDir"] = (not showDir)
    _state["hidePfm"] = (not showPfm)


def _ColumnsForState():
    cols = []
    if not _state["hideNo"]:
        cols.append("No.")
    cols.append("Time")
    if not _state["hideDir"]:
        cols.append("Dir")
    cols.extend(["From", "To", "Arr", "Dep"])
    if not _state["hidePfm"]:
        cols.append("Pfm")
    cols.append("Remarks")
    return cols


def _PreferredColumnWidths(totalWidth):
    cols = _ColumnsForState()
    weights = []
    for c in cols:
        if c == "Remarks":
            weights.append(40.0)
        elif c in ("From", "To"):
            weights.append(9.0)
        elif c in ("Time", "Arr", "Dep"):
            weights.append(6.0)
        elif c in ("No.", "Dir", "Pfm"):
            weights.append(4.0)
        else:
            weights.append(6.0)
    sw = sum(weights) if weights else 1.0
    out = [int(max(40, (totalWidth * (w / sw)))) for w in weights]
    try:
        ridx = cols.index("Remarks")
        out[ridx] = int(max(out[ridx], totalWidth * 0.40))
    except:
        pass
    return out


def _ServiceRunsOnDay(svc, dayName):
    try:
        return bool(svc.get("days", {}).get(dayName, False))
    except:
        return False


def _ComputeExpectedMinuteForSvc(svc, dayName):
    sched = _ServiceKeyTimeMinutes(svc)
    if sched is None:
        return None
    rn = (svc.get("rep", "") or "").strip()
    d = _EffectiveDelayMinutesForRn(rn, dayName, _state["trainDays"], _state["formsFrom"])
    try:
        if d is None:
            return sched
        di = int(d)
        if di > 1440:
            return None
        return sched + di
    except:
        return sched


def _ChooseCurrentModelRow(pageItems, dayName, nowMinutes):
    bestFuture = None
    bestPast = None
    for i, svc in enumerate(pageItems):
        if not _ServiceRunsOnDay(svc, dayName):
            continue
        exp = _ComputeExpectedMinuteForSvc(svc, dayName)
        if exp is None:
            continue
        if nowMinutes is None:
            return i
        if exp >= nowMinutes:
            if bestFuture is None or exp < bestFuture[0]:
                bestFuture = (exp, i)
        else:
            if bestPast is None or exp > bestPast[0]:
                bestPast = (exp, i)
    if bestFuture is not None:
        return bestFuture[1]
    if bestPast is not None:
        return bestPast[1]
    return -1


def _EnsureRowVisible(modelRow, center=True):
    if modelRow < 0:
        return
    try:
        rect = _table.getCellRect(modelRow, 0, True)
        vp = scroll.getViewport()
        if vp is None:
            _table.scrollRectToVisible(rect)
            return
        if not center:
            _table.scrollRectToVisible(rect)
            return
        extent = vp.getExtentSize()
        targetY = max(0, rect.y - max(0, (extent.height // 2) - (rect.height // 2)))
        vp.setViewPosition(Point(0, targetY))
    except:
        try:
            _table.scrollRectToVisible(_table.getCellRect(modelRow, 0, True))
        except:
            pass


def _SelectPageForDay(dayName):
    try:
        for i, p in enumerate(_state["pages"]):
            if dayName in (p.get("days", []) or []):
                return i
    except:
        pass
    return 0


def _ApplyColumnWidths():
    # Fix all non-Remarks columns to their minimum/optimal width based on current contents.
    # Use AUTO_RESIZE_LAST_COLUMN so only the final (Remarks) column changes with window resizing.
    # Disable horizontal scrolling and prevent the window being resized narrower than needed.
    try:
        _table.setAutoResizeMode(JTable.AUTO_RESIZE_LAST_COLUMN)
    except:
        pass

    try:
        cm = _table.getColumnModel()
    except:
        return

    remarksCol = -1
    try:
        for c in range(cm.getColumnCount()):
            try:
                if str(_table.getColumnName(c)) == 'Remarks':
                    remarksCol = c
                    break
            except:
                pass
    except:
        remarksCol = -1

    try:
        fmBase = _table.getFontMetrics(BASE_FONT)
    except:
        fmBase = None
    try:
        fmHdr = _table.getFontMetrics(HEADER_FONT)
    except:
        fmHdr = fmBase

    def _TextWidth(fm, s):
        try:
            if fm is None:
                return len(str(s)) * 8
            return int(fm.stringWidth(str(s)))
        except:
            return len(str(s)) * 8

    def _PreferredWidthForColumn(colIndex, maxRows):
        try:
            hdrTxt = str(_table.getColumnName(colIndex))
        except:
            hdrTxt = ''
        w = _TextWidth(fmHdr, hdrTxt) + 16

        try:
            rc = _table.getRowCount()
        except:
            rc = 0
        try:
            n = min(int(maxRows), int(rc))
        except:
            n = rc

        r = 0
        while r < n:
            try:
                val = _table.getValueAt(r, colIndex)
            except:
                val = ''
            try:
                rend = _table.getCellRenderer(r, colIndex)
                comp = rend.getTableCellRendererComponent(_table, val, False, False, r, colIndex)
                pw = comp.getPreferredSize().width
                if pw is not None:
                    w = max(w, int(pw) + 10)
            except:
                w = max(w, _TextWidth(fmBase, val) + 16)
            r += 1

        return max(40, int(w))

    fixedSum = 0
    remarksMin = 200
    maxRowsToMeasure = 60

    try:
        for c in range(cm.getColumnCount()):
            col = cm.getColumn(c)
            if c == remarksCol:
                continue
            w = _PreferredWidthForColumn(c, maxRowsToMeasure)
            try:
                col.setMinWidth(w)
                col.setMaxWidth(w)
                col.setPreferredWidth(w)
                col.setResizable(False)
            except:
                pass
            fixedSum += int(w)
    except:
        pass

    if remarksCol >= 0:
        try:
            hdrW = _TextWidth(fmHdr, 'Remarks') + 24
            remarksMin = max(int(remarksMin), int(hdrW))
        except:
            pass
        try:
            rcol = cm.getColumn(remarksCol)
            rcol.setMinWidth(int(remarksMin))
            rcol.setResizable(False)
        except:
            pass

    try:
        scroll.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_NEVER)
    except:
        pass


    try:
        scroll.setViewportBorder(BorderFactory.createMatteBorder(0, 0, 0, SCROLLBAR_RIGHT_PADDING, PAPER))
    except:
        pass
    try:
        scroll.getColumnHeader().setBorder(BorderFactory.createMatteBorder(0, 0, 0, SCROLLBAR_RIGHT_PADDING, PAPER))
    except:
        pass
    try:
        vsbW = 18
        try:
            vsbW = int(scroll.getVerticalScrollBar().getPreferredSize().width)
        except:
            vsbW = 18
        pad = int(LEFT_PAGE_PADDING) + 40
        minViewportW = int(fixedSum + remarksMin + vsbW + pad + SCROLLBAR_RIGHT_PADDING)

        try:
            pref = _table.getPreferredScrollableViewportSize()
            ph = 400
            try:
                ph = int(pref.height)
            except:
                ph = 400
            _table.setPreferredScrollableViewportSize(Dimension(minViewportW, ph))
        except:
            pass

        try:
            mh = int(frame.getSize().height)
        except:
            mh = 300
        try:
            frame.setMinimumSize(Dimension(minViewportW, mh))
        except:
            pass

        try:
            cur = frame.getSize()
            if int(cur.width) < minViewportW:
                frame.setSize(int(minViewportW), int(cur.height))
        except:
            pass

    except:
        pass

def _ApplyRenderers():
    try:
        cm = _table.getColumnModel()
        for c in range(cm.getColumnCount()):
            name = ""
            try:
                name = str(_table.getColumnName(c))
            except:
                name = ""
            if name == "Remarks":
                cm.getColumn(c).setCellRenderer(_wrapRenderer)
            elif name == "Dep":
                cm.getColumn(c).setCellRenderer(_depRenderer)
            else:
                cm.getColumn(c).setCellRenderer(_swbRenderer)
    except Exception as ex:
        try:
            print("[StationWorkingBookDisplay] Renderer apply failed: " + str(ex))
        except:
            pass
def _AdjustAllRowHeights():
    # Force recalculation for all rows based on the Remarks and Dep renderers.
    # Row height is set to the maximum required height across these multi-line columns.
    try:
        rmCol = -1
        depCol = -1
        for c in range(_table.getColumnCount()):
            try:
                nm = str(_table.getColumnName(c))
            except:
                nm = ""
            if nm == "Remarks":
                rmCol = c
            elif nm == "Dep":
                depCol = c
        if rmCol < 0 and depCol < 0:
            return

        baseH = 36
        try:
            baseH = int(_table.getRowHeight())
        except:
            baseH = 36

        rmW = None
        depW = None
        try:
            if rmCol >= 0:
                rmW = _table.getColumnModel().getColumn(rmCol).getWidth()
        except:
            rmW = None
        try:
            if depCol >= 0:
                depW = _table.getColumnModel().getColumn(depCol).getWidth()
        except:
            depW = None

        for r in range(_table.getRowCount()):
            need = baseH
            if rmCol >= 0 and rmW is not None:
                try:
                    comp = _wrapRenderer.getTableCellRendererComponent(_table, _table.getValueAt(r, rmCol), False, False, r, rmCol)
                    comp.setSize(Dimension(int(rmW), 100000))
                    prefH = comp.getPreferredSize().height
                    if prefH is None:
                        prefH = baseH
                    need = max(int(need), int(prefH))
                except:
                    pass
            if depCol >= 0 and depW is not None:
                try:
                    comp2 = _depRenderer.getTableCellRendererComponent(_table, _table.getValueAt(r, depCol), False, False, r, depCol)
                    comp2.setSize(Dimension(int(depW), 100000))
                    prefH2 = comp2.getPreferredSize().height
                    if prefH2 is None:
                        prefH2 = baseH
                    need = max(int(need), int(prefH2))
                except:
                    pass
            try:
                if _table.getRowHeight(r) != int(need):
                    _table.setRowHeight(r, int(need))
            except:
                pass
    except:
        pass

def _AdjustAllRowHeightsLater():
    try:
        SwingUtilities.invokeLater(_AdjustAllRowHeights)
    except:
        pass


def _RebuildTableForCurrentPage():
    pages = _state["pages"]
    if not pages:
        return
    idx = _state["pageIndex"]
    if idx < 0:
        idx = 0
    if idx >= len(pages):
        idx = len(pages) - 1
    _state["pageIndex"] = idx

    page = pages[idx]
    rightHeader.setText(page.get("label", ""))
    pageLabel.setText("Page %d/%d" % (idx + 1, _state["total"]))

    cols = _ColumnsForState()
    data = []
    layoutName = _state["layoutName"]

    for svc in page.get("items", []):
        rn = (svc.get("rep", "") or "").strip()
        displayRn = rn if (rn and (not TU.IsDefaultReportingNumber(rn))) else ""
        trig = (svc.get("trigger", "") or "").strip()
        arr = (svc.get("arr", "") or "").strip()
        dep = (svc.get("dep", "") or "").strip()
        keyTime = trig if trig != "" else (arr if arr != "" else dep)

        row = []
        if not _state["hideNo"]:
            row.append(displayRn)
        row.append(FormatTime(keyTime))
        if not _state["hideDir"]:
            row.append((svc.get("dir", "") or "").strip())
        row.append((svc.get("origin", "") or "").strip())
        row.append((svc.get("dest", "") or "").strip())
        row.append(FormatTime(arr) if arr else "")
        depOut = FormatTime(dep) if dep else ""
        try:
            code = ComputeRunCode((svc.get("days", {}) or {}), (page.get("days", []) or []))
        except:
            code = ""
        if code:
            depOut = (depOut + "\n" if depOut else "") + code
        row.append(depOut)
        if not _state["hidePfm"]:
            row.append((svc.get("plat", "") or "").strip())
        row.append(ExpandRemarks(svc, layoutName))
        data.append(row)

    _tableModel = DefaultTableModel(data, cols)
    _table.setModel(_tableModel)

    try:
        hdr = _table.getTableHeader()
        hdr.setReorderingAllowed(False)
        hdr.setBackground(HEADER_BG)
        hdr.setForeground(Color(0, 0, 0))
        hdr.setFont(HEADER_FONT)
        try:
            hdr.setDefaultRenderer(_headerRenderer)
        except:
            pass
        try:
            hdr.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 0))
        except:
            pass
    except:
        pass

    try:
        _table.setRowHeight(36)
    except:
        pass

    _ApplyRenderers()
    _ApplyColumnWidths()
    _AdjustAllRowHeightsLater()


def _UpdateHighlightAndMaybeFollow(doFollow):
    # Do not highlight services for the wrong day-group: only highlight if the current layout day
    # is included in the currently displayed page's day list.
    try:
        page = _state["pages"][_state["pageIndex"]] if _state["pages"] else None
        pageDays = []
        try:
            pageDays = page.get("days", []) if page else []
        except:
            pageDays = []

        if (not pageDays) or (_state["currentDay"] not in pageDays):
            _swbRenderer.HighlightModelRow = -1
            _wrapRenderer.Base.HighlightModelRow = -1
            try:
                _table.repaint()
            except:
                pass
            return

        dayName = _state["currentDay"]
        nowMin = _ParseMinutes(_state["currentTime"])
        items = page.get("items", []) if page else []
        rowIndex = _ChooseCurrentModelRow(items, dayName, nowMin)
        _swbRenderer.HighlightModelRow = rowIndex
        _wrapRenderer.Base.HighlightModelRow = rowIndex
        try:
            _table.repaint()
        except:
            pass
        if rowIndex >= 0 and doFollow:
            _EnsureRowVisible(rowIndex, center=True)
    except:
        pass


def _SnapToCurrent():
    try:
        target = _SelectPageForDay(_state["currentDay"])
        if target != _state["pageIndex"]:
            _GoToPage(target)
    except:
        pass
    _UpdateHighlightAndMaybeFollow(True)


# --------------------
# Paging and controls
# --------------------

def _RefreshButtons():
    btnPrev.setEnabled(_state["pageIndex"] > 0)
    btnNext.setEnabled(_state["pageIndex"] < (_state["total"] - 1))


def _GoToPage(index):
    _state["pageIndex"] = max(0, min(int(index), _state["total"] - 1))
    _RebuildTableForCurrentPage()
    _RefreshButtons()
    _UpdateHighlightAndMaybeFollow(chkFollow.isSelected())


def NextPage(event=None):
    if _state["pageIndex"] < (_state["total"] - 1):
        _GoToPage(_state["pageIndex"] + 1)


def PrevPage(event=None):
    if _state["pageIndex"] > 0:
        _GoToPage(_state["pageIndex"] - 1)


def _OnSnap(event=None):
    _SnapToCurrent()


btnNext.actionPerformed = NextPage
btnPrev.actionPerformed = PrevPage
btnSnap.actionPerformed = _OnSnap


class _Action(AbstractAction):
    def __init__(self, fn):
        AbstractAction.__init__(self)
        self.Fn = fn

    def actionPerformed(self, e):
        self.Fn()


rootPane = frame.getRootPane()
im = rootPane.getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW)
am = rootPane.getActionMap()
im.put(KeyStroke.getKeyStroke(KeyEvent.VK_RIGHT, 0), "pageNext")
im.put(KeyStroke.getKeyStroke(KeyEvent.VK_LEFT, 0), "pagePrev")
am.put("pageNext", _Action(NextPage))
am.put("pagePrev", _Action(PrevPage))

# --- Mouse wheel paging on the control bar (when mouse is over the lower controls) ---
class WheelPager(MouseWheelListener):
    def __init__(self, nextFn, prevFn, debounceMs):
        self.NextFn = nextFn
        self.PrevFn = prevFn
        try:
            self.DebounceMs = int(debounceMs)
        except:
            self.DebounceMs = 150
        self.LastTs = 0

    def mouseWheelMoved(self, e):
        try:
            now = System.currentTimeMillis()
            if (now - self.LastTs) < self.DebounceMs:
                return
            rot = 0
            try:
                rot = int(e.getWheelRotation())
            except:
                rot = 0
            if rot > 0:
                self.NextFn()
                self.LastTs = now
                try:
                    e.consume()
                except:
                    pass
            elif rot < 0:
                self.PrevFn()
                self.LastTs = now
                try:
                    e.consume()
                except:
                    pass
        except:
            pass

_wheelPager = WheelPager(NextPage, PrevPage, 150)

# Attach wheel listener to the lower control bar AND its child components, so the wheel works when hovering buttons/labels.
try:
    controlsPanel.addMouseWheelListener(_wheelPager)
except:
    pass
for _c in (btnPrev, btnNext, btnSnap, chkFollow, statusLabel):
    try:
        _c.addMouseWheelListener(_wheelPager)
    except:
        pass



# --------------------
# Resize/listen to reflow Remarks rows
# --------------------

class _ColModelListener(TableColumnModelListener):
    def columnAdded(self, e):
        _AdjustAllRowHeightsLater()

    def columnRemoved(self, e):
        _AdjustAllRowHeightsLater()

    def columnMoved(self, e):
        _AdjustAllRowHeightsLater()

    def columnMarginChanged(self, e):
        _AdjustAllRowHeightsLater()

    def columnSelectionChanged(self, e):
        pass


try:
    _table.getColumnModel().addColumnModelListener(_ColModelListener())
except:
    pass


class _FrameResizer(ComponentAdapter):
    def componentResized(self, e):
        _AdjustAllRowHeightsLater()


try:
    frame.addComponentListener(_FrameResizer())
except:
    pass


# --------------------
# Live updates
# --------------------

_IsClosed = [False]

TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")


def _LoadAll():
    csvPath = ResolveTimetableCsvPath()
    master = LoadServicesMaster(csvPath)
    _state["master"] = master
    _state["formsFrom"] = _BuildFormsFromMap(master)
    _state["trainDays"] = _BuildTrainDaysMap(master)
    _DecideColumnHiding(master)
    _state["pages"] = _BuildPages(master)
    _state["total"] = len(_state["pages"])


def _UpdateStatusLine():
    try:
        dayName = _state["currentDay"] or ""
        timeStr = _state["currentTime"] or ""
        statusLabel.setText("%s %s" % (dayName, FormatTime(timeStr)))
    except:
        pass


def _HandleDayOrTimeChange():
    if _IsClosed[0]:
        return
    _UpdateStatusLine()

    if chkFollow.isSelected():
        try:
            target = _SelectPageForDay(_state["currentDay"])
            if target != _state["pageIndex"]:
                _GoToPage(target)
                return
        except:
            pass

    _UpdateHighlightAndMaybeFollow(chkFollow.isSelected())


def _OnTimeChanged(event=None):
    if _IsClosed[0]:
        return
    try:
        _state["currentTime"] = TimeMem.getValue() or ""
    except:
        _state["currentTime"] = ""
    _HandleDayOrTimeChange()


def _OnDayChanged(event=None):
    if _IsClosed[0]:
        return
    try:
        _state["currentDay"] = DayMem.getValue() or ""
    except:
        _state["currentDay"] = ""
    _HandleDayOrTimeChange()


def _OnTimetableChanged(event=None):
    if _IsClosed[0]:
        return
    try:
        _LoadAll()
        _state["pageIndex"] = _SelectPageForDay(_state["currentDay"])
        _RebuildTableForCurrentPage()
        _RefreshButtons()
        _HandleDayOrTimeChange()
    except:
        pass


def _Cleanup():
    if _IsClosed[0]:
        return
    _IsClosed[0] = True
    try:
        TimeMem.removePropertyChangeListener(_TimeListener)
    except:
        pass
    try:
        DayMem.removePropertyChangeListener(_DayListener)
    except:
        pass
    try:
        TimetableMem.removePropertyChangeListener(_TtListener)
    except:
        pass


from java.awt.event import WindowAdapter


class _WindowCloser(WindowAdapter):
    def windowClosing(self, e):
        _Cleanup()

    def windowClosed(self, e):
        _Cleanup()


frame.addWindowListener(_WindowCloser())

_TimeListener = _OnTimeChanged
_DayListener = _OnDayChanged
_TtListener = _OnTimetableChanged
TimeMem.addPropertyChangeListener(_TimeListener)
DayMem.addPropertyChangeListener(_DayListener)
TimetableMem.addPropertyChangeListener(_TtListener)


# Initial build
try:
    _state["currentTime"] = TimeMem.getValue() or ""
except:
    _state["currentTime"] = ""
try:
    _state["currentDay"] = DayMem.getValue() or ""
except:
    _state["currentDay"] = ""

_LoadAll()
_state["pageIndex"] = _SelectPageForDay(_state["currentDay"])
_RebuildTableForCurrentPage()
_RefreshButtons()
_HandleDayOrTimeChange()

frame.pack()
frame.setVisible(True)

# End of file
