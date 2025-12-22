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
# WTTDisplay.py - JMRI 5.12 / Jython 2.7
# Working Timetable UI with conditional suppression of the "Rep. no." row
# when the timetable has no non-default reporting numbers (i.e., all RNs
# are blank or begin with uppercase 'TAS...').

import os
import csv
import jmri
from jmri import InstanceManager
from jmri.util import JmriJFrame

from javax.swing import JTable
from javax.swing import JLabel
from javax.swing import JPanel
from javax.swing import JScrollPane
from javax.swing import SwingConstants
from javax.swing import BorderFactory
from javax.swing import JButton
from javax.swing import KeyStroke
from javax.swing import JComponent
from javax.swing.table import DefaultTableCellRenderer, DefaultTableModel
from javax.swing import AbstractAction

from java.awt import BorderLayout, Color, Dimension, Font, FlowLayout
from java.awt.event import KeyEvent
from java.awt.event import MouseWheelListener, MouseWheelEvent
from java.lang import String, Math, System
from java.text import SimpleDateFormat
import TASBeanLookup as TBL

# -- TAS default RN rule --
import TASUtil as TU  # IsDefaultReportingNumber(s)

# --- Helpers: read memory and parse "r,g,b" safely 
def _ReadMemStr(suffix, default=""):
    # Read a Memory value using suffix-based (prefix-agnostic) lookup.
    # Returns a stripped string, falling back to default.
    try:
        val = TBL.SafeGetMemoryValue(suffix, default)
        s = "" if val is None else str(val).strip()
        return s if s else default
    except:
        return default


def _ReadMemBool(suffix, default=False):
    # Read boolean-ish Memory values using suffix-based lookup.
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
        if len(parts) != 3: return fallback
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
        return Color(r, g, b)
    except:
        return fallback

# ---------------- Options ----------------
# --- Options via memories set in TASSetup ---
PAGE_MODE = _ReadMemStr("WTT_PAGE_MODE", "WEEKDAYS_SAT_SUN")
TIME_24H = _ReadMemBool("WTT_TIME_24H", True)
TIME_SEPARATOR = _ReadMemStr("WTT_TIME_SEPARATOR", " ")[:1]  # single char
ECS_LABEL = _ReadMemStr("WTT_ECS_LABEL", "ECS")

# Parse comma-separated tokens (lowercased, trimmed) into a set
_ecs_raw = _ReadMemStr("WTT_ECS_DEST_MATCH", "empty to depot,empty,ety.,ecs")
_ECS_DEST_MATCH = set([t.strip().lower() for t in _ecs_raw.split(",") if len(t.strip()) > 0])

DIRECTION_SPLIT = _ReadMemBool("WTT_DIRECTION_SPLIT", True)

# Header orientation for origin/destination columns (default: horizontal)
# Set IMWTT_OD_HEADER_VERTICAL = "true" in TASSetup to enable vertical headers.
OD_HEADER_VERTICAL = _ReadMemBool("WTT_OD_HEADER_VERTICAL", False)

# ---------------- Styles ----------------
# Paper colour from IMTASPAPERCOLOUR (default "249,246,238")
PAPER = _RgbStrToColor(_ReadMemStr("TASPAPERCOLOUR", "249,246,238"), Color(249, 246, 238))
RULE = Color(60, 60, 60)
HEADER_BG = PAPER
# Lighter band = PAPER; darker band from TASWTTBANDDARK (default "245,242,235")
ROW_A = _RgbStrToColor(_ReadMemStr("TASWTTBANDLIGHT", "255,253,247"), Color(255, 253, 247))
ROW_B = _RgbStrToColor(_ReadMemStr("TASWTTBANDDARK", "245,242,235"), Color(245, 242, 235))
MAJOR_RULE_THICK = 2
MINOR_RULE_THICK = 1
DOUBLE_RULE_THICK = MAJOR_RULE_THICK * 2
DOTS_A = ". ."
DOTS_B = ". . . . . . ."

# Font family from TAS_FONT_FAMILY (default "Gill Sans MT")
_fontFam = _ReadMemStr("TAS_FONT_FAMILY", "Gill Sans MT")
try:
    BASE_FONT   = Font(_fontFam, Font.PLAIN, 14)
    HEADER_FONT = Font(_fontFam, Font.BOLD,  14)
    TITLE_FONT  = Font(_fontFam, Font.BOLD,  18)
except:
    # Fallbacks if the requested family isn't available
    BASE_FONT   = Font("Serif", Font.PLAIN, 14)
    HEADER_FONT = Font("Serif", Font.BOLD,  14)
    TITLE_FONT  = Font("Serif", Font.BOLD,  18)

BOLD_FONT = Font(BASE_FONT.getName(), Font.BOLD, BASE_FONT.getSize())
ITALIC_FONT = Font(BASE_FONT.getName(), Font.ITALIC, BASE_FONT.getSize())
BOLD_ITALIC = Font(BASE_FONT.getName(), (Font.BOLD | Font.ITALIC), BASE_FONT.getSize())

LEFT_PAGE_PADDING = 16

# ---------------- Days ----------------
DAYS_ORDER = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
DAY_TOKEN = {"Monday":"M","Tuesday":"T","Wednesday":"W","Thursday":"Th","Friday":"F","Saturday":"S","Sunday":"Su"}

# ---------------- Profile name ----------------
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

LAYOUT_NAME = GetProfileName()

# ---------------- Rotated header ----------------
class VerticalLabel(JLabel):
    def __init__(self, text="", clockwise=False):
        JLabel.__init__(self, text)
        self.clockwise = clockwise
        self.setHorizontalAlignment(SwingConstants.CENTER)
        self.setVerticalAlignment(SwingConstants.CENTER)
        self.setOpaque(True)
    def getPreferredSize(self):
        d = JLabel.getPreferredSize(self)
        return Dimension(int(d.height), int(d.width))
    def paintComponent(self, g):
        g2 = g.create()
        try:
            w = self.getWidth(); h = self.getHeight()
            if self.clockwise:
                g2.rotate(Math.PI / 2.0); g2.translate(0, -w)
            else:
                g2.rotate(-Math.PI / 2.0); g2.translate(-h, 0)
            super(VerticalLabel, self).paintComponent(g2)
        finally:
            g2.dispose()

class VerticalHeaderRenderer(DefaultTableCellRenderer):
    def __init__(self):
        DefaultTableCellRenderer.__init__(self)
        # Choose label type based on OD_HEADER_VERTICAL so we keep one renderer
        if 'OD_HEADER_VERTICAL' in globals() and OD_HEADER_VERTICAL:
            self.proto = VerticalLabel("", clockwise=False)  # rotated
        else:
            self.proto = JLabel("")  # normal horizontal

        self.proto.setBackground(HEADER_BG)
        self.proto.setForeground(Color(0,0,0))
        self.proto.setFont(HEADER_FONT)
        self.proto.setOpaque(True)
        # Preserve the original thick/thin matte border in BOTH orientations
        self.proto.setBorder(BorderFactory.createMatteBorder(
            MAJOR_RULE_THICK, MINOR_RULE_THICK, MAJOR_RULE_THICK, MINOR_RULE_THICK, RULE))

    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        # Create a fresh label each time to avoid cross-cell state
        if 'OD_HEADER_VERTICAL' in globals() and OD_HEADER_VERTICAL:
            lbl = VerticalLabel("" if value is None else String.valueOf(value), clockwise=False)
        else:
            lbl = JLabel("" if value is None else String.valueOf(value))
        # Copy prototype styling (font, colors, border)
        lbl.setBackground(self.proto.getBackground())
        lbl.setForeground(self.proto.getForeground())
        lbl.setFont(self.proto.getFont())
        lbl.setBorder(self.proto.getBorder())
        lbl.setOpaque(True)
        lbl.setHorizontalAlignment(SwingConstants.CENTER)
        lbl.setVerticalAlignment(SwingConstants.CENTER)
        return lbl


# ---------------- Cell renderer ----------------
class WTTCellRenderer(DefaultTableCellRenderer):
    def __init__(self, thickCols=None, boldRows=None, doubleRuleAfterRows=None,
        rowHeaderCol=0, fillDotsRows=None, codesRow=None, dataStartCol=2):
        DefaultTableCellRenderer.__init__(self)
        self.thickCols = set(thickCols or [])
        self.boldRows = set(boldRows or [])
        self.doubleRuleAfterRows = set(doubleRuleAfterRows or [])
        self.rowHeaderCol = rowHeaderCol
        self.fillDotsRows = set(fillDotsRows or [])
        self.codesRow = codesRow
        self.dataStartCol = dataStartCol
        self._dotsRowsOrder = sorted(list(self.fillDotsRows))
        self.styleByCell = {}  # {(row,col): "BOLD"/"ITALIC"}
        self.blockTopRows = set()
        self.blockBottomRows = set()
        self.repRow = -1  # dynamic index; -1 when hidden
        self.setFont(BASE_FONT)
        self.setOpaque(True)
    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        comp = super(WTTCellRenderer, self).getTableCellRendererComponent(
            table, value, isSelected, hasFocus, row, column)
        if column in (0, 1): comp.setHorizontalAlignment(SwingConstants.LEFT)
        else: comp.setHorizontalAlignment(SwingConstants.CENTER)

        if (row in self.fillDotsRows) and (column >= self.dataStartCol):
            txt = "" if value is None else str(value)
            if len(txt.strip()) == 0:
                try: idx = self._dotsRowsOrder.index(row)
                except: idx = 0
                comp.setText(DOTS_A if (idx % 2 == 0) else DOTS_B)
        comp.setFont(BOLD_FONT if (row in self.boldRows) else BASE_FONT)

        if self.codesRow is not None and row == self.codesRow and column >= self.dataStartCol:
            txt = comp.getText()
            if txt is not None and str(txt).strip() and not str(txt).lstrip().lower().startswith("<html"):
                comp.setFont(BOLD_ITALIC)

        try:
            if (row, column) in self.styleByCell:
                style = self.styleByCell[(row, column)]
                if style == "BOLD": comp.setFont(BOLD_FONT)
                elif style == "ITALIC": comp.setFont(ITALIC_FONT)
        except:
            pass

        if not isSelected:
            comp.setBackground(ROW_A if (row % 2 == 0) else ROW_B)
            comp.setForeground(Color(0,0,0))

        left = MAJOR_RULE_THICK if column in self.thickCols else MINOR_RULE_THICK
        right = MAJOR_RULE_THICK if (column+1) in self.thickCols else MINOR_RULE_THICK
        top = 0; bottom = 0
        if self.repRow >= 0 and row == self.repRow:
            bottom = DOUBLE_RULE_THICK
        if row == 0:
            top = MAJOR_RULE_THICK
        if row in self.blockTopRows and (self.repRow < 0 or row - 1 != self.repRow):
            top = MAJOR_RULE_THICK
        if row in self.blockBottomRows:
            bottom = MAJOR_RULE_THICK

        outer = BorderFactory.createMatteBorder(top, left, bottom, right, RULE)
        if column == 1:
            pad = BorderFactory.createEmptyBorder(0, 8, 0, 0)
            comp.setBorder(BorderFactory.createCompoundBorder(outer, pad))
        else:
            comp.setBorder(outer)
        return comp

class ZebraTable(JTable):
    def __init__(self, model):
        JTable.__init__(self, model)
        self.setShowGrid(False)
        self.setRowHeight(28)
        self.setAutoResizeMode(JTable.AUTO_RESIZE_OFF)
        self.setFont(BASE_FONT)
        self.setIntercellSpacing(Dimension(0, 0))
        self.setRowSelectionAllowed(False)
        self.setColumnSelectionAllowed(False)
        self.setCellSelectionEnabled(False)
        self.setFocusable(False)
        self.setRequestFocusEnabled(False)

# ---------------- Columns / base rows ----------------
NUM_DATA_COLS = 12
DATA_START_COL = 2
columns = ["", ""] + ([""] * NUM_DATA_COLS)
ROW_CODES = 0
ROW_TOP_BOLD = 1

def _blank_rows_for_start(showRep):
    emptyData = [""] * NUM_DATA_COLS
    base = [
        ["", ""] + emptyData,  # codes
        ["", ""] + emptyData   # class / load (title set later)
    ]
    if showRep:
        base.append(["Rep. no.", ""] + emptyData)
    return base

model = DefaultTableModel(_blank_rows_for_start(True), columns)  # temp; rebuilt after CSV

# ---------------- CSV path ----------------
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

# ---------------- Time helpers ----------------
_sdf_parse_12 = SimpleDateFormat("h:mm a")
_sdf_parse_24 = SimpleDateFormat("H:mm")
_sdf_out_24  = SimpleDateFormat("HH:mm")
_sdf_out_12 = SimpleDateFormat("h:mm a")

def FormatTime(s):
    if s is None:
        return ""
    s = s.strip()
    if len(s) == 0:
        return ""

    # Try to parse using either 12h or 24h inputs
    for parser in (_sdf_parse_12, _sdf_parse_24):
        try:
            dt = parser.parse(s)
            if TIME_24H:
                # Output 24-hour, respecting TIME_SEPARATOR
                out = _sdf_out_24.format(dt)
                return out.replace(":", TIME_SEPARATOR) if TIME_SEPARATOR != ":" else out
            else:
                # Output 12-hour, respecting TIME_SEPARATOR (before AM/PM)
                out = _sdf_out_12.format(dt)
                return out.replace(":", TIME_SEPARATOR) if TIME_SEPARATOR != ":" else out
        except:
            pass

    # Fallback if parsing fails: return as-is (unchanged)
    return s

def _ParseMinutes(s):
    if s is None: return None
    s = s.strip()
    if len(s) == 0: return None
    for parser in (_sdf_parse_12, _sdf_parse_24):
        try:
            dt = parser.parse(s)
            hhmm = _sdf_out_24.format(dt)
            return int(hhmm[:2]) * 60 + int(hhmm[3:5])
        except:
            pass
    return None

# ---------------- CSV import ----------------
TP_NAMES = []
TP_ORDER_BY_DIR = {}  # direction -> (above_list, below_list)
HAS_TRIGGER_COL = False

def LoadServicesMaster(csv_path):
    """
    Returns list of rows: dict with keys:
    rep, arr, dep, origin, dest, plat, cls, load, trigger, tp{name}->{arr,dep}, days{Mon..Sun}->bool, dir, note
    """
    global HAS_TRIGGER_COL
    services = []
    if not os.path.exists(csv_path):
        print("Timetable file not found: %s" % csv_path); return services
    # Detect delimiter
    try:
        with open(csv_path, "r") as fh:
            sniff = fh.read(4096)
            delim = "\t" if ("\t" in sniff) else ","
    except:
        delim = ","
    with open(csv_path, "r") as f:
        reader = csv.reader(f, delimiter=delim)
        header = None
        idx = {}
        idx_tp_arr = {}
        idx_tp_dep = {}
        trigger_idx = None
        for row in reader:
            if not row or (len(("".join(row)).strip()) == 0): continue
            if header is None:
                header = [h.strip() for h in row]
                def find_col(names):
                    hl = [h.lower() for h in header]
                    for cand in names:
                        cl = cand.lower()
                        if cl in hl: return hl.index(cl)
                    return None
                idx["rep"]  = find_col(("Reporting number","reporting number"))
                idx["dir"]  = find_col(("Direction","direction"))
                idx["note"] = find_col(("Notes","notes","Note","note"))
                idx["arr"]  = find_col(("Arr","arr"))
                idx["dep"]  = find_col(("Dep","dep"))
                trigger_idx = find_col(("Trigger","trigger"))
                HAS_TRIGGER_COL = (trigger_idx is not None)
                idx["origin"] = find_col(("Origin","origin"))
                idx["dest"]   = find_col(("Destination","destination"))
                idx["plat"]   = find_col(("Platform","platform"))
                idx["cls"]    = find_col(("Class","class"))
                idx["load"]   = find_col(("Timing load","Timing Load","timing load","timing Load"))
                # TP columns
                TP_NAMES[:] = []
                seen_tp = set()
                for i, h in enumerate(header):
                    h2 = h.strip().lower()
                    if h2.startswith("tparr "):
                        name = header[i][6:].strip()
                        idx_tp_arr[name] = i
                        if name not in seen_tp: TP_NAMES.append(name); seen_tp.add(name)
                    elif h2.startswith("tpdep "):
                        name = header[i][6:].strip()
                        idx_tp_dep[name] = i
                        if name not in seen_tp: TP_NAMES.append(name); seen_tp.add(name)
                for d in DAYS_ORDER:
                    idx[d] = find_col((d, d.lower()))
                continue

            def safe(idxname):
                i = idx.get(idxname)
                return row[i].strip() if (i is not None and i < len(row)) else ""

            days = {}
            for d in DAYS_ORDER:
                di = idx.get(d)
                flag = row[di].strip().upper() if (di is not None and di < len(row)) else ""
                days[d] = (flag in ("TRUE","T","1","Y","YES"))

            dir_norm  = (safe("dir").strip().upper() if safe("dir") else "")
            note_text = safe("note")
            trig = row[trigger_idx].strip() if (HAS_TRIGGER_COL and trigger_idx < len(row)) else ""

            tp_map = {}
            for name in TP_NAMES:
                a = row[idx_tp_arr[name]].strip() if name in idx_tp_arr and idx_tp_arr[name] < len(row) else ""
                d = row[idx_tp_dep[name]].strip() if name in idx_tp_dep and idx_tp_dep[name] < len(row) else ""
                tp_map[name] = {"arr": a, "dep": d}

            services.append({
                "rep": safe("rep"), "arr": safe("arr"), "dep": safe("dep"),
                "origin": safe("origin"), "dest": safe("dest"),
                "plat": safe("plat"), "cls": safe("cls"), "load": safe("load"),
                "trigger": trig, "tp": tp_map,
                "days": days, "dir": dir_norm, "note": note_text
            })
    return services

# ---------------- Pages & headers ----------------
def DeriveDirectionOrder(services):
    first_index = {}
    has_unspecified = False
    for i, svc in enumerate(services):
        d = (svc.get("dir","") or "").strip().upper()
        if not d:
            has_unspecified = True; continue
        if d not in first_index:
            first_index[d] = i
    dirs = list(first_index.keys())
    def priority(d):
        if d == "DOWN": return 0
        if d == "UP": return 1
        if d in ("EAST","EASTBOUND"): return 10
        if d in ("WEST","WESTBOUND"): return 11
        if d in ("NORTH","NORTHBOUND"): return 20
        if d in ("SOUTH","SOUTHBOUND"): return 21
        return 100
    dirs.sort(key=lambda d: (priority(d), first_index[d]))
    return dirs, has_unspecified

def DayGroupsFromMode(mode):
    if mode == "SEVEN_DAYS":
        return [("MONDAYS", ["Monday"]), ("TUESDAYS", ["Tuesday"]), ("WEDNESDAYS",["Wednesday"]),
                ("THURSDAYS", ["Thursday"]), ("FRIDAYS", ["Friday"]), ("SATURDAYS",["Saturday"]), ("SUNDAYS", ["Sunday"])]
    elif mode == "WEEKDAYS_SAT_SUN":
        return [("WEEKDAYS", ["Monday","Tuesday","Wednesday","Thursday","Friday"]),
                ("SATURDAYS",["Saturday"]), ("SUNDAYS", ["Sunday"])]
    elif mode == "MONSAT_PLUS_SUN":
        return [("MON-SAT", ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]),
                ("SUNDAYS", ["Sunday"])]
    elif mode == "ALL_WEEK":
        return [("WEEK", DAYS_ORDER[:])]
    else:
        return DayGroupsFromMode("SEVEN_DAYS")

def _ScoreRowForGroup(svc, group_days):
    inside = 0; outside = 0
    for d in DAYS_ORDER:
        flag = svc["days"].get(d, False)
        if d in group_days:
            if flag: inside += 1
        else:
            if flag: outside += 1
    return inside * 100 - outside

def BuildPages(services_master, groups, capacity, split_by_direction):
    pages = []
    if split_by_direction:
        order, has_unspecified = DeriveDirectionOrder(services_master)
        dir_passes = order[:]
        if has_unspecified: dir_passes.append("UNSPECIFIED")
    else:
        dir_passes = [None]
    dir_buckets = {}
    for dpass in (dir_passes if dir_passes != [None] else [None]):
        dir_buckets[dpass] = []
    for svc in services_master:
        svcd = (svc.get("dir","") or "").strip().upper()
        placed = False
        for dpass in dir_buckets.keys():
            if dpass is None:
                placed = True
                dir_buckets[dpass].append(svc)
            else:
                if dpass == "UNSPECIFIED":
                    if svcd == "":
                        dir_buckets[dpass].append(svc); placed = True
                else:
                    if svcd == dpass:
                        dir_buckets[dpass].append(svc); placed = True
        if not placed and (dir_passes == [None]):
            dir_buckets[None].append(svc)

    for dpass in dir_passes:
        dir_list = dir_buckets.get(dpass, [])
        for label, days in groups:
            best = {}      # rep -> (score, firstIndex, svc)
            order_keys = []  # first-seen rep order
            for idx, svc in enumerate(dir_list):
                has_any = False
                for d in days:
                    if svc["days"].get(d, False):
                        has_any = True; break
                if not has_any:
                    continue
                rep = svc.get("rep","")
                sc = _ScoreRowForGroup(svc, days)
                if rep not in best:
                    best[rep] = (sc, idx, svc)
                    order_keys.append(rep)
                else:
                    prev_sc, prev_idx, _ = best[rep]
                    if sc > prev_sc:
                        best[rep] = (sc, prev_idx, svc)
            items = [best[rep][2] for rep in order_keys]
            i = 0
            while i < len(items):
                pages.append({"label": label, "days": days, "items": items[i:i+capacity], "direction": dpass})
                i += capacity
    return pages or [{"label":"WEEK","days":DAYS_ORDER[:],"items":[], "direction": None}]

# ---------------- Header helpers ----------------
def HtmlEscape(s):
    if s is None: return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _IsEcsDest(dest): return (dest or "").strip().lower() in _ECS_DEST_MATCH

def _OdPhrase(origin, dest, layout_name):
    o = (origin or "").strip(); d = (dest or "").strip()
    ln = (layout_name or "").strip().lower()
    ol = o.lower(); dl = d.lower()
    if _IsEcsDest(d): return ECS_LABEL
    if o and d:
        if dl == ln and ol != ln: return "From " + o
        if ol == ln and dl != ln: return "To " + d
        if ol == ln and dl == ln: return ""
        return o + " to " + d
    elif o:
        return "" if ol == ln else ("From " + o)
    elif d:
        return "" if dl == ln else ("To " + d)
    else:
        return ""

def MakeWrappedHeaderHtml(origin, dest, px_width, layout_name):
    phrase = _OdPhrase(origin, dest, layout_name)
    if phrase:
        return "<html><div style='width:%dpx; text-align:center;'>%s</div></html>" % (px_width, HtmlEscape(phrase))
    return ""

def AutoAdjustHeaderHeight(header, table):
    max_h = 0
    try:
        if OD_HEADER_VERTICAL:
            # Measure using rotated prototype label
            for i in range(table.getColumnModel().getColumnCount()):
                text = table.getColumnModel().getColumn(i).getHeaderValue()
                v = VerticalLabel("" if text is None else String.valueOf(text))
                v.setFont(HEADER_FONT)
                v.setBackground(HEADER_BG)
                d = v.getPreferredSize()
                if d.height > max_h: max_h = d.height
        else:
            # Measure using a normal JLabel with HTML (horizontal)
            for i in range(table.getColumnModel().getColumnCount()):
                text = table.getColumnModel().getColumn(i).getHeaderValue()
                lbl = JLabel("" if text is None else String.valueOf(text))
                lbl.setFont(HEADER_FONT)
                lbl.setOpaque(True)
                lbl.setBackground(HEADER_BG)
                d = lbl.getPreferredSize()
                if d.height > max_h: max_h = d.height
        max_h = max_h + 6
        ph = header.getPreferredSize()
        header.setPreferredSize(Dimension(int(ph.width), max_h))
        header.revalidate()
        header.repaint()
    except:
        # Fail-safe: do nothing if measuring fails
        pass

# ---------------- Legend helpers ----------------
def ComputeRunCode(days_flags, group_days):
    ordered = [d for d in DAYS_ORDER if d in group_days]
    present_days = [d for d in ordered if days_flags.get(d, False)]
    missing_days = [d for d in ordered if not days_flags.get(d, False)]
    if len(present_days) == 0 or len(missing_days) == 0: return ""
    present_core = "".join([DAY_TOKEN[d] for d in present_days])
    missing_core = "".join([DAY_TOKEN[d] for d in missing_days])
    return (missing_core + "X") if (len(missing_core) < len(present_core)) else (present_core + "O")

def ExplainCode(code):
    if not code: return ""
    suffix = code[-1]; core = code[:-1]; tokens = []; i = 0
    while i < len(core):
        if i + 1 < len(core) and core[i:i+2] in ("Th","Su"):
            tokens.append(core[i:i+2]); i += 2
        else:
            tokens.append(core[i]); i += 1
    token_to_days = { "M":"Mondays","T":"Tuesdays","W":"Wednesdays","Th":"Thursdays",
        "F":"Fridays","S":"Saturdays","Su":"Sundays" }
    days_text = " & ".join(token_to_days.get(t,t) for t in tokens)
    if suffix == "O": return "%s only" % days_text
    if suffix == "X": return "%s excluded" % days_text
    return code

# ---------------- UI construction ----------------
frame = JmriJFrame("Working Timetable")
frame.setDefaultCloseOperation(JmriJFrame.DISPOSE_ON_CLOSE)

root = JPanel(BorderLayout(0, 0))
root.setBackground(PAPER)
root.setBorder(BorderFactory.createEmptyBorder(0, LEFT_PAGE_PADDING, 0, 0))

top = JPanel(BorderLayout()); top.setBackground(PAPER)
leftHeader   = JLabel(GetProfileName())
centerHeader = JLabel("")
rightHeader  = JLabel("WEEKDAYS")
for lbl in (leftHeader, centerHeader, rightHeader):
    lbl.setOpaque(True); lbl.setBackground(PAPER); lbl.setForeground(Color(0,0,0))
    lbl.setFont(TITLE_FONT); lbl.setBorder(BorderFactory.createEmptyBorder(6, 12, 6, 12))
centerHeader.setBorder(BorderFactory.createEmptyBorder(6, 24, 6, 24))
leftHeader.setHorizontalAlignment(SwingConstants.LEFT)
centerHeader.setHorizontalAlignment(SwingConstants.CENTER)
rightHeader.setHorizontalAlignment(SwingConstants.RIGHT)
top.add(leftHeader,   BorderLayout.WEST)
top.add(centerHeader, BorderLayout.CENTER)
top.add(rightHeader,  BorderLayout.EAST)
top.setBorder(BorderFactory.createMatteBorder(MAJOR_RULE_THICK, MAJOR_RULE_THICK, MINOR_RULE_THICK, MAJOR_RULE_THICK, RULE))

table = ZebraTable(model)
thickCols = set([0, 1, DATA_START_COL + 6, len(columns) - 1])
boldRows  = set([ROW_TOP_BOLD])  # (rep row added later if visible)
doubleRuleAfterRows = set()

cellRenderer = WTTCellRenderer(
    thickCols=thickCols,
    boldRows=boldRows,
    doubleRuleAfterRows=doubleRuleAfterRows,
    rowHeaderCol=0,
    fillDotsRows=set(),
    codesRow=ROW_CODES,
    dataStartCol=DATA_START_COL
)

for c in range(model.getColumnCount()):
    table.getColumnModel().getColumn(c).setCellRenderer(cellRenderer)
    if c == 0: table.getColumnModel().getColumn(c).setPreferredWidth(150)
    elif c == 1: table.getColumnModel().getColumn(c).setPreferredWidth(96)
    else: table.getColumnModel().getColumn(c).setPreferredWidth(90)


header = table.getTableHeader()
# Always use our renderer; it decides orientation and applies uniform borders
header.setDefaultRenderer(VerticalHeaderRenderer())
header.setReorderingAllowed(False)
header.setBackground(HEADER_BG)
header.setForeground(Color(0,0,0))
header.setFont(HEADER_FONT)

scroll = JScrollPane(table)
scroll.getViewport().setBackground(PAPER)
scroll.setBorder(BorderFactory.createMatteBorder(0, MAJOR_RULE_THICK, MAJOR_RULE_THICK, MAJOR_RULE_THICK, RULE))

bottom = JPanel(BorderLayout()); bottom.setBackground(PAPER)
bottom.setBorder(BorderFactory.createEmptyBorder(4, MAJOR_RULE_THICK, 4, MAJOR_RULE_THICK))
legendLabel = JLabel("")
legendLabel.setFont(Font(BASE_FONT.getName(), Font.PLAIN, 12))
bottom.add(legendLabel, BorderLayout.WEST)

pagerPanel = JPanel(FlowLayout(FlowLayout.RIGHT, 6, 0))
pagerPanel.setOpaque(True); pagerPanel.setBackground(PAPER)
btnPrev   = JButton("<")
btnNext   = JButton(">")
pageLabel = JLabel("Page 1/1"); pageLabel.setFont(BASE_FONT)
for b in (btnPrev, btnNext): b.setFont(BASE_FONT)
pagerPanel.add(btnPrev); pagerPanel.add(pageLabel); pagerPanel.add(btnNext)
bottom.add(pagerPanel, BorderLayout.EAST)

root.add(top,    BorderLayout.NORTH)
root.add(scroll, BorderLayout.CENTER)
root.add(bottom, BorderLayout.SOUTH)
frame.setContentPane(root)
frame.pack(); frame.setVisible(True)

# Set window icon using TASIcon utility
try:
    from TASIcon import SetFrameClockIcon
    SetFrameClockIcon(frame, 32)  # 32px icon size
except Exception as ex:
    print("[WTTDisplay] Failed to set timetable window icon: " + str(ex))


# ---------------- Data & paging ----------------
_columns_present = {"cls": False, "load": False}
TOP_ROW_TITLE = ""

def SetTopRowHeading():
    global TOP_ROW_TITLE
    if _columns_present.get("cls") and _columns_present.get("load"): TOP_ROW_TITLE = "Class / Timing load"
    elif _columns_present.get("cls"): TOP_ROW_TITLE = "Class"
    elif _columns_present.get("load"): TOP_ROW_TITLE = "Timing load"
    else: TOP_ROW_TITLE = ""
    try: model.setValueAt(TOP_ROW_TITLE, ROW_TOP_BOLD, 0)
    except: pass

def _TypicalTimeForDefault(svc):
    return _ParseMinutes(svc.get("dep","")) or _ParseMinutes(svc.get("arr",""))

def _TypicalTimeForTp(svc, name):
    m = svc.get("tp",{}).get(name, {"arr":"", "dep":""})
    return _ParseMinutes(m.get("dep","")) or _ParseMinutes(m.get("arr",""))

def _ComputeTpOrder(items, names):
    """
    Compute median (tp_time - default_time) per TP across the items,
    then sort:
    - 'above' -> values < 0, ascending (most negative first)
    - 'below' -> values >= 0, ascending (closest to default first)
    """
    diffs = {}
    for nm in names:
        arr = []
        for svc in items:
            td = _TypicalTimeForDefault(svc)
            tt = _TypicalTimeForTp(svc, nm)
            if td is not None and tt is not None:
                arr.append(tt - td)
        if arr:
            arr.sort()
            diffs[nm] = arr[len(arr)//2]
    above = sorted([n for n in names if diffs.get(n, 0) < 0], key=lambda n: diffs.get(n, 0))
    below = sorted([n for n in names if diffs.get(n, 0) >= 0], key=lambda n: diffs.get(n, 0))
    return (above, below)

def _BuildTpOrderIndexByDirection(services_master):
    global TP_ORDER_BY_DIR
    TP_ORDER_BY_DIR = {}
    dirs, has_unspecified = DeriveDirectionOrder(services_master)
    dir_keys = dirs[:] + (["UNSPECIFIED"] if has_unspecified else [])
    for d in dir_keys:
        if d == "UNSPECIFIED":
            items = [s for s in services_master if (s.get("dir","") or "").strip() == ""]
        else:
            items = [s for s in services_master if (s.get("dir","") or "").strip().upper() == d]
        TP_ORDER_BY_DIR[d] = _ComputeTpOrder(items, TP_NAMES)

def _BuildTimingRowsForPage(page, showRep):
    """
    Returns:
    rows, timeRows(set), blockStarts(set), blockEnds(set), nameRows(set), above, below, baseRowsCount
    """
    items = page["items"]
    dkey = page.get("direction")
    dkey = (str(dkey).upper() if dkey else None)

    if dkey and dkey in TP_ORDER_BY_DIR:
        above, below = TP_ORDER_BY_DIR.get(dkey, ([], TP_NAMES[:]))
    else:
        if dkey: above, below = _ComputeTpOrder(items, TP_NAMES)
        else:    above, below = ([], TP_NAMES[:])

    rows = _blank_rows_for_start(showRep)
    timeRows, blockStarts, blockEnds, nameRows = [], set(), set(), set()
    def _AddBlockStart(r): blockStarts.add(r)
    def _AddBlockEnd(r):   blockEnds.add(r)
    baseRowsCount = 2 + (1 if showRep else 0)

    if HAS_TRIGGER_COL:
        rows.append(["", ""]); r_trig = len(rows)-1
        timeRows.append(r_trig); _AddBlockStart(r_trig); _AddBlockEnd(r_trig)

    for nm in above:
        rows.append([nm, "arr."]); r0 = len(rows)-1
        rows.append(["", "dep./pass"]); r1 = len(rows)-1
        timeRows.extend([r0, r1]); _AddBlockStart(r0); _AddBlockEnd(r1)
        nameRows.add(r0)

    rows.append([LAYOUT_NAME, "arr."]); r0 = len(rows)-1
    rows.append(["", "dep./pass"]); r1 = len(rows)-1
    rows.append(["", "plat."]);     r2 = len(rows)-1
    timeRows.extend([r0, r1]); _AddBlockStart(r0); _AddBlockEnd(r2)
    nameRows.add(r0)

    for nm in below:
        rows.append([nm, "arr."]); r0 = len(rows)-1
        rows.append(["", "dep./pass"]); r1 = len(rows)-1
        timeRows.extend([r0, r1]); _AddBlockStart(r0); _AddBlockEnd(r1)
        nameRows.add(r0)

    return rows, set(timeRows), blockStarts, blockEnds, nameRows, above, below, baseRowsCount

def _FitFrameSnug():
    try:
        table_w = table.getPreferredSize().width
        w_cushion = 10
        target_scroll_w = table_w + w_cushion + LEFT_PAGE_PADDING
        header_h = table.getTableHeader().getPreferredSize().height
        rows_h = table.getRowHeight() * model.getRowCount()
        h_cushion = 10
        target_scroll_h = header_h + rows_h + h_cushion

        scroll.setPreferredSize(Dimension(int(target_scroll_w), int(target_scroll_h)))
        top_h    = top.getPreferredSize().height
        bottom_h = bottom.getPreferredSize().height
        needed_w = max(target_scroll_w, top.getPreferredSize().width, bottom.getPreferredSize().width)
        needed_h = top_h + target_scroll_h + bottom_h
        cur  = frame.getSize()
        new_w = int(max(cur.width,  needed_w))
        new_h = int(max(cur.height, needed_h))
        frame.setSize(new_w, new_h); frame.validate()

        try:
            hb = scroll.getHorizontalScrollBar()
            vb = scroll.getVerticalScrollBar()
            bump_w = 0; bump_h = 0
            if hb is not None and hb.isVisible(): bump_w = 16
            if vb is not None and vb.isVisible(): bump_h = 16
            if bump_w or bump_h:
                frame.setSize(new_w + bump_w, new_h + bump_h)
                frame.validate()
        except:
            pass
    except:
        pass

def ApplyPage(page, SHOW_REP_ROW, REP_ROW_INDEX):
    rightHeader.setText(page["label"])
    dir_txt = page.get("direction", None)
    centerHeader.setText("" if not dir_txt else str(dir_txt).upper())

    SetTopRowHeading()
    rows, timeRows, blockStarts, blockEnds, nameRows, above_order, below_order, baseRowsCount = _BuildTimingRowsForPage(page, SHOW_REP_ROW)

    emptyData = [""] * NUM_DATA_COLS
    dataMatrix = [r[:] + emptyData[:] for r in rows]
    model.setDataVector(dataMatrix, columns)

    cellRenderer.fillDotsRows   = timeRows
    cellRenderer._dotsRowsOrder = sorted(list(timeRows))
    cellRenderer.styleByCell    = {}
    cellRenderer.blockTopRows   = set(blockStarts)
    cellRenderer.blockBottomRows= set(blockEnds)
    cellRenderer.repRow         = REP_ROW_INDEX

    if SHOW_REP_ROW and REP_ROW_INDEX >= 0:
        try:
            cellRenderer.boldRows.add(REP_ROW_INDEX)
        except:
            pass

    for c in range(model.getColumnCount()):
        table.getColumnModel().getColumn(c).setCellRenderer(cellRenderer)
        if c == 0: table.getColumnModel().getColumn(c).setPreferredWidth(150)
        elif c == 1: table.getColumnModel().getColumn(c).setPreferredWidth(96)
        else: table.getColumnModel().getColumn(c).setPreferredWidth(90)

    model.setValueAt(TOP_ROW_TITLE, ROW_TOP_BOLD, 0)

    items = page["items"]
    days  = page["days"]
    codes_used, note_index, note_order = [], {}, []

    def _NormNote(s): return " ".join(((s or "").strip()).split()).lower()

    maxCols = model.getColumnCount() - DATA_START_COL
    dkey = page.get("direction"); dkey = (str(dkey).upper() if dkey else None)
    if dkey and dkey in TP_ORDER_BY_DIR:
        above_fixed, below_fixed = TP_ORDER_BY_DIR.get(dkey, ([], TP_NAMES[:]))
    else:
        if dkey: above_fixed, below_fixed = _ComputeTpOrder(page["items"], TP_NAMES)
        else:    above_fixed, below_fixed = ([], TP_NAMES[:])

    for i in range(min(len(items), maxCols)):
        svc = items[i]
        code = ComputeRunCode(svc["days"], days)

        note_text = (svc.get("note","") or "").strip()
        note_num  = None
        if note_text:
            key = _NormNote(note_text)
            if key not in note_index:
                note_index[key] = {"n": len(note_order) + 1, "text": note_text}
                note_order.append(key)
            note_num = note_index[key]["n"]

        if code or (note_num is not None):
            if note_num is None:
                model.setValueAt(code, ROW_CODES, DATA_START_COL + i)
            else:
                parts = []
                if code: parts.append("<b><i>%s</i></b>" % HtmlEscape(code))
                if parts: parts.append(" ")
                parts.append("<b>%d</b>" % note_num)
                model.setValueAt("<html>%s</html>" % "".join(parts), ROW_CODES, DATA_START_COL + i)
        else:
            model.setValueAt("", ROW_CODES, DATA_START_COL + i)

        if code and (code not in codes_used): codes_used.append(code)

        clsStr  = (svc.get("cls","")  or "").strip()
        loadStr = (svc.get("load","") or "").strip()
        model.setValueAt(clsStr + (" - " if (clsStr and loadStr) else "") + loadStr, ROW_TOP_BOLD, DATA_START_COL + i)

        if SHOW_REP_ROW and REP_ROW_INDEX >= 0:
            model.setValueAt(svc.get("rep",""), REP_ROW_INDEX, DATA_START_COL + i)

        r = baseRowsCount
        if HAS_TRIGGER_COL:
            if r < model.getRowCount():
                model.setValueAt(FormatTime(svc.get("trigger","")), r, DATA_START_COL + i)
                cellRenderer.styleByCell[(r, DATA_START_COL + i)] = "ITALIC"
            r += 1

        def _FillTpBlock(tpname, r_in, col_index):
            amap    = svc.get("tp",{}).get(tpname, {"arr":"", "dep":""})
            arr_raw = amap.get("arr",""); dep_raw = amap.get("dep","")
            arr_fmt = FormatTime(arr_raw); dep_fmt = FormatTime(dep_raw)
            model.setValueAt(arr_fmt, r_in,   col_index)
            model.setValueAt(dep_fmt, r_in+1, col_index)
            style = "BOLD" if (arr_raw.strip() != "") else "ITALIC"
            cellRenderer.styleByCell[(r_in,   col_index)] = style
            cellRenderer.styleByCell[(r_in+1, col_index)] = style
            return r_in + 2

        for nm in above_fixed: r = _FillTpBlock(nm, r, DATA_START_COL + i)

        arr_raw  = svc.get("arr","")
        dep_raw  = svc.get("dep","")
        plat_raw = svc.get("plat","")
        arr_fmt  = FormatTime(arr_raw)
        dep_fmt  = FormatTime(dep_raw)

        # Write values
        model.setValueAt(arr_fmt,  r,     DATA_START_COL + i)
        model.setValueAt(dep_fmt,  r + 1, DATA_START_COL + i)
        model.setValueAt(plat_raw, r + 2, DATA_START_COL + i)

        # Style rule:
        # - BOLD if Arr exists OR a platform is specified (stop at main timing point)
        # - ITALIC only if Arr absent AND no platform (pass without stopping)
        isPlatformSpecified = (plat_raw is not None and str(plat_raw).strip() != "")
        style = "BOLD" if ((arr_raw.strip() != "") or isPlatformSpecified) else "ITALIC"

        # Apply to BOTH rows of the main timing point block
        cellRenderer.styleByCell[(r,     DATA_START_COL + i)] = style   # "Arr." row
        cellRenderer.styleByCell[(r + 1, DATA_START_COL + i)] = style   # "Dep./pass" row

        r += 3

        for nm in below_fixed: r = _FillTpBlock(nm, r, DATA_START_COL + i)

    for nameRow in nameRows:
        cellRenderer.styleByCell[(nameRow, 0)] = "BOLD"

    table.getColumnModel().getColumn(0).setHeaderValue("")  # name col
    table.getColumnModel().getColumn(1).setHeaderValue("")  # sublabel

    for i in range(DATA_START_COL, model.getColumnCount()):
        colWidth = table.getColumnModel().getColumn(i).getWidth()
        wrap_px  = max(20, colWidth - 12)
        if i - DATA_START_COL < len(items):
            svc = items[i - DATA_START_COL]
            hdr = MakeWrappedHeaderHtml(svc.get("origin",""), svc.get("dest",""), wrap_px, LAYOUT_NAME)
        else:
            hdr = ""
        table.getColumnModel().getColumn(i).setHeaderValue(hdr)

    AutoAdjustHeaderHeight(header, table)

    parts = []
    for c in codes_used:
        parts.append("<b>%s</b> = %s" % (c, HtmlEscape(ExplainCode(c))))
    for key in note_order:
        info = note_index[key]
        parts.append("<b>%d</b> %s" % (info["n"], HtmlEscape(info["text"])))
    legendLabel.setText("<html>%s</html>" % ("; ".join(parts)) if parts else "")
    pageLabel.setText("Page %d/%d" % (state["index"] + 1, state["total"]))
    _FitFrameSnug()

def RefreshButtons():
    btnPrev.setEnabled(state["index"] > 0)
    btnNext.setEnabled(state["index"] < state["total"] - 1)

def GoTo(index, SHOW_REP_ROW, REP_ROW_INDEX):
    state["index"] = index
    ApplyPage(state["pages"][state["index"]], SHOW_REP_ROW, REP_ROW_INDEX)
    RefreshButtons()

def NextPage(event=None):
    if state["index"] < state["total"] - 1: GoTo(state["index"] + 1, SHOW_REP_ROW, REP_ROW_INDEX)

def PrevPage(event=None):
    if state["index"] > 0: GoTo(state["index"] - 1, SHOW_REP_ROW, REP_ROW_INDEX)

btnNext.actionPerformed = NextPage
btnPrev.actionPerformed = PrevPage

class _Action(AbstractAction):
    def __init__(self, fn): AbstractAction.__init__(self); self.fn = fn
    def actionPerformed(self, e): self.fn()

rootPane = frame.getRootPane()
im = rootPane.getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW)
am = rootPane.getActionMap()
im.put(KeyStroke.getKeyStroke(KeyEvent.VK_RIGHT, 0), "pageNext")
im.put(KeyStroke.getKeyStroke(KeyEvent.VK_LEFT,  0), "pagePrev")
am.put("pageNext", _Action(NextPage))
am.put("pagePrev", _Action(PrevPage))

# --- Mouse wheel paging (debounced) ---
class WheelPager(MouseWheelListener):
    def __init__(self, nextFn, prevFn, debounceMs):
        self.NextFn = nextFn
        self.PrevFn = prevFn
        self.DebounceMs = int(debounceMs)
        self.LastTs = 0  # last dispatch time in ms

    def mouseWheelMoved(self, e):
        try:
            now = System.currentTimeMillis()
            if (now - self.LastTs) < self.DebounceMs:
                return  # debounce: ignore rapid repeats
            rot = 0
            try:
                rot = int(e.getWheelRotation())
            except:
                rot = 0
            if rot > 0:
                self.NextFn()
                self.LastTs = now
                try: e.consume()
                except: pass
            elif rot < 0:
                self.PrevFn()
                self.LastTs = now
                try: e.consume()
                except: pass
        except:
            pass

# Attach the wheel listener to several components to catch events reliably
_wheel = WheelPager(NextPage, PrevPage, 150)  # 150 ms debounce
try:
    root.addMouseWheelListener(_wheel)
except:
    pass
try:
    table.addMouseWheelListener(_wheel)
except:
    pass
try:
    scroll.addMouseWheelListener(_wheel)
    scroll.getViewport().addMouseWheelListener(_wheel)
except:
    pass

# ---------------- Load & init ----------------
csv_path = ResolveTimetableCsvPath()
master   = LoadServicesMaster(csv_path)

_columns_present["cls"]  = any(((svc.get("cls","")  or "").strip()) for svc in master)
_columns_present["load"] = any(((svc.get("load","") or "").strip()) for svc in master)
SetTopRowHeading()

_BuildTpOrderIndexByDirection(master)

# Decide global "Rep. no." visibility
SHOW_REP_ROW = any((((svc.get("rep","") or "").strip()) and not TU.IsDefaultReportingNumber(((svc.get("rep","") or "").strip())))
    for svc in master)

# Prepare base rows and renderer state
model.setDataVector(_blank_rows_for_start(SHOW_REP_ROW), columns)
REP_ROW_INDEX       = (2 if SHOW_REP_ROW else -1)
cellRenderer.repRow = (REP_ROW_INDEX if SHOW_REP_ROW else -1)
if SHOW_REP_ROW and REP_ROW_INDEX >= 0:
    try:
        cellRenderer.boldRows.add(REP_ROW_INDEX)
    except:
        pass

groups = DayGroupsFromMode(PAGE_MODE)
pages  = BuildPages(master, groups, NUM_DATA_COLS, DIRECTION_SPLIT)
state  = {"pages": pages, "index": 0, "total": len(pages)}

GoTo(0, SHOW_REP_ROW, REP_ROW_INDEX)