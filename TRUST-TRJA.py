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
# TRUST-TRJA Enquiry Output — hides TAS-default reporting numbers in the "Train" column.

import javax.swing as swing
import java.awt as awt
import java.awt.event as event
import jmri
import os
import csv
import TASBeanLookup as TBL
from java.text import SimpleDateFormat
from jmri.profile import ProfileManager
from DisruptionRegister import getDisruption
from TimingRegister import listTimingPoints, getTiming
from javax.swing import SwingUtilities
from javax.swing.event import TableColumnModelListener
from java.awt.event import ComponentAdapter

# --- TAS default RN rule ---
import TASUtil as TU  # IsDefaultReportingNumber(s)

# ------ Script option ------
TRJA_KEEP_AFTER_DEPART_UNTIL_LAST_TP = False

# ----- Memory and profile -----
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
TRJA_TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
TRJA_DayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
TRJA_TimetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")

TRJA_CurrentTimeStr = TRJA_TimeMem.getValue() or ""
TRJA_CurrentDay = TRJA_DayMem.getValue() or ""
TRJA_TimetableName = TRJA_TimetableMem.getValue() or ""
TRJA_Profile = ProfileManager.getDefault().getActiveProfile()
TRJA_ProfilePath = TRJA_Profile.getPath().toString()
TRJA_TimetableFile = os.path.join(TRJA_ProfilePath, "timetable", TRJA_TimetableName + ".csv")
TRJA_BaseTPName = (TRJA_Profile.getName() or "").strip()

# ------ Day/Time helpers ------
TRJA_DaysOfWeek = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
def TRJA_GetNextDay(day):
    try:
        idx = TRJA_DaysOfWeek.index(day)
        return TRJA_DaysOfWeek[(idx + 1) % 7]
    except:
        return ""
def TRJA_GetPrevDay(day):
    try:
        i = TRJA_DaysOfWeek.index(day)
        return TRJA_DaysOfWeek[(i - 1) % 7]
    except:
        return ""
TRJA_TimeParser = SimpleDateFormat("h:mm a")
TRJA_AltParser = SimpleDateFormat("H:mm")
TRJA_Out24 = SimpleDateFormat("HH:mm")
def TRJA_ParseTimeToMinutes(timeStr):
    for parser in [TRJA_TimeParser, TRJA_AltParser]:
        try:
            parsed = parser.parse(timeStr)
            return parsed.getHours() * 60 + parsed.getMinutes()
        except:
            continue
    return None
def TRJA_FormatTo24Hour(timeStr):
    for parser in [TRJA_TimeParser, TRJA_AltParser]:
        try:
            parsed = parser.parse(timeStr)
            return TRJA_Out24.format(parsed)
        except:
            continue
    return timeStr
def TRJA_IsCrossMidnightWindow(now_minutes):
    return now_minutes is not None and now_minutes < 300
def TRJA_IsLateEvening(minutes_val):
    return minutes_val is not None and minutes_val >= 1320
def TRJA_MinutesNow():
    s = TRJA_TimeMem.getValue() or ""
    for parser in [TRJA_TimeParser, TRJA_AltParser]:
        try:
            dt = parser.parse(s)
            return dt.getHours() * 60 + dt.getMinutes()
        except:
            pass
    return None

# ------ Timing register helpers (unchanged) ------
def TRJA_FindLatestTimingForRNAtTP(tpName, rn, dayToday):
    try:
        entries = getTiming(tpName) or []
    except:
        return None
    best = None
    for rec in entries:
        try:
            rnr = rec[0]; t_str = rec[2]; d_str = rec[3]
        except:
            continue
        if rnr != rn: continue
        if d_str != dayToday: continue
        mm = TRJA_ParseTimeToMinutes(t_str)
        if mm is None: continue
        if (best is None) or (mm > best):
            best = mm
    return best

def TRJA_GetLastScheduledTP(row):
    latestMin = None; latestName = None
    arr = (row.get("Arr","") or "").strip()
    dep = (row.get("Dep","") or "").strip()
    mmArr = TRJA_ParseTimeToMinutes(arr) if arr else None
    mmDep = TRJA_ParseTimeToMinutes(dep) if dep else None
    if mmArr is not None: latestMin = mmArr; latestName = TRJA_BaseTPName
    if mmDep is not None and (latestMin is None or mmDep > latestMin):
        latestMin = mmDep; latestName = TRJA_BaseTPName
    for key, val in row.items():
        if not key or not val: continue
        kl = key.strip().lower()
        if kl.startswith("tparr ") or kl.startswith("tpdep "):
            tpName = key[6:].strip()
            mm = TRJA_ParseTimeToMinutes(val)
            if mm is not None and (latestMin is None or mm > latestMin):
                latestMin = mm; latestName = tpName
    return latestName, latestMin

def TRJA_GetLastReportForTrain_Display(reportingNumber, nowDay, nowMinutes):
    best_tp = ""; best_time_minutes = -1; best_day = ""
    try:
        tps = listTimingPoints() or []
    except:
        tps = []
    prevDay = TRJA_GetPrevDay(nowDay)
    for tp in tps:
        try:
            entries = getTiming(tp) or []
        except:
            entries = []
        for rec in entries:
            try:
                rn = rec[0]; t_str = rec[2]; d_str = rec[3]
            except:
                continue
            if rn != reportingNumber: continue
            t_min = TRJA_ParseTimeToMinutes(t_str)
            if t_min is None: continue
            if d_str == nowDay:
                if t_min <= nowMinutes:
                    if (best_day == nowDay and t_min > best_time_minutes) or (best_day != nowDay):
                        best_tp = (tp or "").upper()
                        best_time_minutes = t_min
                        best_day = d_str
            elif d_str == prevDay:
                if TRJA_IsCrossMidnightWindow(nowMinutes) and TRJA_IsLateEvening(t_min):
                    abs_min = t_min - 1440
                    if best_day == nowDay:
                        best_abs = best_time_minutes
                    elif best_time_minutes >= 0:
                        best_abs = best_time_minutes - 1440
                    else:
                        best_abs = -10**9
                    if abs_min <= 0 and abs_min > best_abs:
                        best_tp = (tp or "").upper()
                        best_time_minutes = t_min
                        best_day = d_str
    if best_tp and best_time_minutes >= 0:
        hhmm = "%02d:%02d" % (best_time_minutes // 60, best_time_minutes % 60)
        return best_tp, hhmm
    return "", ""


def TRJA_ComputeOverdueReport(row, reportingNumber, nowDay, nowMinutes):
    # Build a list of scheduled TP events (both Arr and Dep) from row
    # We treat the base timing point (profile name) as a TP too, using Arr/Dep.
    # Return the first overdue (closest past) TP as "<mins> <TPNAME>", else "".

    try:
        tps_all = listTimingPoints() or []
    except:
        tps_all = []

    # Helper: parse time from any cell text to minutes
    def _p(val):
        return TRJA_ParseTimeToMinutes((val or "").strip()) if val else None

    events = []

    # Base TP: Arr/Dep
    baseTP = (TRJA_BaseTPName or "").strip()
    if baseTP:
        arr = (row.get("Arr", "") or "").strip()
        dep = (row.get("Dep", "") or "").strip()
        mmArr = _p(arr)
        mmDep = _p(dep)
        if mmArr is not None:
            events.append((baseTP, "Arr", mmArr))
        if mmDep is not None:
            events.append((baseTP, "Dep", mmDep))

    # Other TP columns: "TPArr X" / "TPDep Y"
    for k, v in row.items():
        if not k or not v:
            continue
        ks = (str(k).strip()).lower()
        if ks.startswith("tparr ") or ks.startswith("tpdep "):
            tpName = k[6:].strip()
            mm = _p(v)
            if mm is not None and tpName:
                kind = "Arr" if ks.startswith("tparr ") else "Dep"
                events.append((tpName, kind, mm))

    # Consider only scheduled times already past "now"
    past = [e for e in events if (e[2] is not None and nowMinutes is not None and e[2] <= nowMinutes)]
    if not past:
        return ""

    # For each past event, check TimingRegister for any record (RN, day) at that TP.
    # First, find the latest scheduled minute that DOES have a timing record: lastPassedSchedMin.
    lastPassedSchedMin = None

    # Build a quick map from TP name -> list of scheduled minutes (Arr/Dep) for the row
    tpSchedMap = {}
    for tpName, kind, schedMin in events:
        if tpName and schedMin is not None:
            tpSchedMap.setdefault(tpName, []).append(schedMin)

    try:
        # Scan all timing points to find any actual reports for this RN/day
        allTPs = listTimingPoints() or []
    except:
        allTPs = []

    for tp in allTPs:
        try:
            entries = getTiming(tp) or []
        except:
            entries = []
        # If a timing exists for RN/day at this TP, consider its scheduled minutes
        hasThisRNDay = False
        for rec in entries:
            try:
                rn = rec[0]; d_str = rec[3]
            except:
                continue
            if rn == reportingNumber and d_str == nowDay:
                hasThisRNDay = True
                break
        if hasThisRNDay:
            # Use the scheduled minute(s) for this TP from the row
            for sm in tpSchedMap.get(tp, []):
                if sm is not None:
                    if (lastPassedSchedMin is None) or (sm > lastPassedSchedMin):
                        lastPassedSchedMin = sm

    # Now collect overdue candidates among "past" events that have NO timing yet,
    # but ONLY those strictly later than the latest passed scheduled minute.
    overdue_candidates = []
    for tpName, kind, schedMin in past:
        # Skip any TPs at/before the last passed scheduled minute
        if (lastPassedSchedMin is not None) and (schedMin <= lastPassedSchedMin):
            continue

        try:
            entries = getTiming(tpName) or []
        except:
            entries = []

        found = False
        for rec in entries:
            try:
                rn = rec[0]; d_str = rec[3]
            except:
                continue
            if rn == reportingNumber and d_str == nowDay:
                found = True
                break

        if not found:
            overdue_candidates.append((tpName, schedMin))

    if not overdue_candidates:
        return ""

    # Pick the earliest overdue (minimum scheduled minute strictly after the last actual)
    tpName, schedMin = sorted(overdue_candidates, key=lambda x: x[1])[0]
    minutesLate = (nowMinutes or 0) - (schedMin or 0)
    if minutesLate > 0:
        return ("%d %s" % (minutesLate, (tpName or "").upper()))
    return ""


    # Pick the nearest past (highest schedMin <= nowMinutes)
    tpName, schedMin = sorted(overdue_candidates, key=lambda x: x[1], reverse=True)[0]
    minutesLate = max(0, (nowMinutes or 0) - (schedMin or 0))
    # Display in upper-case to match style used in "Last reported" - but only display if there's a non-zero number to show
    if minutesLate > 0:
        return ("%d %s" % (minutesLate, (tpName or "").upper()))
    return ""



# ------ Paging state/data -> unchanged layout ------
TRJA_PageSize = 12
TRJA_CurrentPage = [0]
TRJA_FilteredData = []
TRJA_TodayTrains = []
TRJA_TomorrowTrains = []
TRJA_NextDay = TRJA_GetNextDay(TRJA_CurrentDay)

def TRJA_TotalPages():
    return max(1, (len(TRJA_FilteredData) + TRJA_PageSize - 1) // TRJA_PageSize)

def TRJA_UpdatePageIndicator():
    pages = TRJA_TotalPages()
    curr = TRJA_CurrentPage[0] + 1
    TRJA_PageLabel.setText(
        "<html>"
        "<font color=#00FF00>Page </font>"
        + ("<font color=#FF3333>%d... </font>" % curr)
        + "<font color=#00FF00>of </font>"
        + ("<font color=white>%d</font>" % pages)
        + "</html>"
    )

def TRJA_ClampPageAndRefreshIndicator():
    pages = TRJA_TotalPages()
    if TRJA_CurrentPage[0] >= pages:
        TRJA_CurrentPage[0] = pages - 1
    if TRJA_CurrentPage[0] < 0:
        TRJA_CurrentPage[0] = 0
    TRJA_UpdatePageIndicator()

# ------ UI (unchanged widgets/formatting) ------
TRJA_Columns = ["", "Train", "arr", "dep", "--------- Last", "reported", "---------", "Overdue reports"]
TRJA_TableModel = swing.table.DefaultTableModel([], TRJA_Columns)
TRJA_Table = swing.JTable(TRJA_TableModel)
TRJA_Table.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_Table.setForeground(awt.Color.GREEN)
TRJA_Table.setBackground(awt.Color.BLACK)
TRJA_Table.setGridColor(awt.Color.BLACK)
TRJA_Table.setShowGrid(False)
TRJA_Table.setRowHeight(24)
TRJA_Table.setRowSelectionAllowed(False)
TRJA_Table.setColumnSelectionAllowed(False)
TRJA_Table.setCellSelectionEnabled(False)
TRJA_Table.setFocusable(False)
TRJA_Table.setEnabled(False)


class TRJA_BulletRendererClass(swing.table.DefaultTableCellRenderer):
    def getTableCellRendererComponent(self, tbl, value, isSelected, hasFocus, row, col):
        comp = swing.table.DefaultTableCellRenderer.getTableCellRendererComponent(self, tbl, value, isSelected, hasFocus, row, col)
        comp.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
        comp.setForeground(awt.Color.RED)
        comp.setBackground(awt.Color.BLACK)
        comp.setHorizontalAlignment(swing.SwingConstants.LEFT)
        return comp
TRJA_BulletRenderer = TRJA_BulletRendererClass()
def TRJA_ApplyBulletFormatting():
    def _run():
        cm = TRJA_Table.getColumnModel()
        if cm and cm.getColumnCount() >= 1:
            col0 = cm.getColumn(0)
            col0.setCellRenderer(TRJA_BulletRenderer)
            col0.setPreferredWidth(6)
    SwingUtilities.invokeLater(_run)

class TRJA_HeaderCellRenderer(swing.table.DefaultTableCellRenderer):
    def __init__(self, align=swing.SwingConstants.LEFT):
        swing.table.DefaultTableCellRenderer.__init__(self)
        self._align = align
    def getTableCellRendererComponent(self, tbl, value, isSelected, hasFocus, row, col):
        comp = swing.table.DefaultTableCellRenderer.getTableCellRendererComponent(self, tbl, value, isSelected, hasFocus, row, col)
        comp.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
        comp.setForeground(awt.Color.WHITE)
        comp.setBackground(awt.Color.BLACK)
        comp.setHorizontalAlignment(self._align)
        return comp

def TRJA_ApplyColumnFormatting():
    def _run():
        cm = TRJA_Table.getColumnModel()
        if cm is None or cm.getColumnCount() < 8:
            return

        cm.getColumn(0).setPreferredWidth(6)    # bullet
        cm.getColumn(1).setPreferredWidth(82)   # Train
        cm.getColumn(2).setPreferredWidth(72)   # arr
        cm.getColumn(3).setPreferredWidth(72)   # dep
        cm.getColumn(4).setPreferredWidth(190)  # booked TP
        cm.getColumn(5).setPreferredWidth(100)  # Last reported
        cm.getColumn(6).setPreferredWidth(140)  # status
        cm.getColumn(7).setPreferredWidth(180)  # Overdue reports

        hdr = TRJA_Table.getTableHeader()
        cm.getColumn(4).setHeaderRenderer(TRJA_HeaderCellRenderer(swing.SwingConstants.LEFT))
        cm.getColumn(5).setHeaderRenderer(TRJA_HeaderCellRenderer(swing.SwingConstants.LEFT))
        cm.getColumn(6).setHeaderRenderer(TRJA_HeaderCellRenderer(swing.SwingConstants.LEFT))
        cm.getColumn(7).setHeaderRenderer(TRJA_HeaderCellRenderer(swing.SwingConstants.LEFT))

        defaultHdr = TRJA_HeaderCellRenderer(swing.SwingConstants.LEFT)
        cm.getColumn(1).setHeaderRenderer(defaultHdr)
        cm.getColumn(2).setHeaderRenderer(defaultHdr)
        cm.getColumn(3).setHeaderRenderer(defaultHdr)

        TRJA_Table.getTableHeader().revalidate()
        TRJA_Table.getTableHeader().repaint()

    SwingUtilities.invokeLater(_run)

def TRJA_UpdateTable():
    pages = TRJA_TotalPages()
    if TRJA_CurrentPage[0] >= pages:
        TRJA_CurrentPage[0] = pages - 1
    start = TRJA_CurrentPage[0] * TRJA_PageSize
    end = start + TRJA_PageSize
    pageData = TRJA_FilteredData[start:end]
    TRJA_Table.setModel(swing.table.DefaultTableModel(pageData, TRJA_Columns))
    TRJA_ApplyBulletFormatting()
    TRJA_ApplyColumnFormatting()
    TRJA_UpdatePageIndicator()
    TRJA_PositionBookedHeaderLater()

class TRJA_HeaderRenderer(swing.table.DefaultTableCellRenderer):
    def getTableCellRendererComponent(self, tbl, value, isSelected, hasFocus, row, col):
        comp = swing.table.DefaultTableCellRenderer.getTableCellRendererComponent(self, tbl, value, isSelected, hasFocus, row, col)
        comp.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
        comp.setForeground(awt.Color.WHITE)
        comp.setBackground(awt.Color.BLACK)
        comp.setHorizontalAlignment(swing.SwingConstants.LEFT)
        return comp

TRJA_Header = TRJA_Table.getTableHeader()
TRJA_Header.setDefaultRenderer(TRJA_HeaderRenderer())
TRJA_ScrollPane = swing.JScrollPane(TRJA_Table)
TRJA_ScrollPane.setBorder(swing.BorderFactory.createEmptyBorder(0, 20, 0, 20))
TRJA_ScrollPane.setBackground(awt.Color.BLACK)
TRJA_ScrollPane.getViewport().setBackground(awt.Color.BLACK)

# ------ Footer (unchanged) ------
TRJA_FooterPanel = swing.JPanel()
TRJA_FooterPanel.setLayout(swing.BoxLayout(TRJA_FooterPanel, swing.BoxLayout.Y_AXIS))
TRJA_FooterPanel.setBackground(awt.Color.BLACK)
TRJA_FooterPanel.setBorder(swing.BorderFactory.createEmptyBorder(0, 20, 10, 20))
TRJA_InfoPanel = swing.JPanel()
TRJA_InfoPanel.setLayout(swing.BoxLayout(TRJA_InfoPanel, swing.BoxLayout.X_AXIS))
TRJA_InfoPanel.setBackground(awt.Color.BLACK)
TRJA_ClockStatusLabel = swing.JLabel("Clock status")
TRJA_ClockStatusLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_ClockStatusLabel.setForeground(awt.Color.WHITE)
TRJA_ClockStatusLabel.setBackground(awt.Color.BLACK)
TRJA_ClockStatusLabel.setOpaque(True)
TRJA_ClockRateLabel = swing.JLabel("Clock rate")
TRJA_ClockRateLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_ClockRateLabel.setForeground(awt.Color.WHITE)
TRJA_ClockRateLabel.setBackground(awt.Color.BLACK)
TRJA_ClockRateLabel.setOpaque(True)
TRJA_InfoPanel.add(TRJA_ClockStatusLabel)
TRJA_InfoPanel.add(swing.Box.createHorizontalStrut(20))
TRJA_InfoPanel.add(TRJA_ClockRateLabel)
TRJA_TimetableLabel = swing.JLabel("Timetable: ")
TRJA_TimetableLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_TimetableLabel.setForeground(awt.Color.GREEN)
TRJA_TimetableLabel.setBackground(awt.Color.BLACK)
TRJA_TimetableLabel.setOpaque(True)
TRJA_InfoPanel.add(swing.Box.createHorizontalGlue())
TRJA_InfoPanel.add(TRJA_TimetableLabel)
TRJA_KeyHelpPanel = swing.JPanel()
TRJA_KeyHelpPanel.setLayout(swing.BoxLayout(TRJA_KeyHelpPanel, swing.BoxLayout.X_AXIS))
TRJA_KeyHelpPanel.setBackground(awt.Color.BLACK)
TRJA_KeyHelpPanel.setBorder(swing.BorderFactory.createEmptyBorder(0, 20, 0, 20))
def TRJA_MakeKeyLabel(key, function):
    label = swing.JLabel("<html><font color=white>%s</font>: <font color=#00FF00>%s</font></html>" % (key, function))
    label.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
    label.setBackground(awt.Color.BLACK)
    label.setOpaque(True)
    return label
TRJA_KeyHelpPanel.add(TRJA_MakeKeyLabel("&lt;-", "Previous page"))
TRJA_KeyHelpPanel.add(swing.Box.createHorizontalStrut(20))
TRJA_KeyHelpPanel.add(swing.Box.createHorizontalGlue())
TRJA_KeyHelpPanel.add(TRJA_MakeKeyLabel("->", "Next page"))
TRJA_FooterPanel.add(TRJA_KeyHelpPanel)
TRJA_FooterPanel.add(TRJA_InfoPanel)

# ------ FastClock integration ------
TRJA_FastClock = jmri.InstanceManager.getDefault(jmri.Timebase)
def TRJA_UpdateClock(event=None):
    running = TRJA_FastClock.getRun()
    rate = TRJA_FastClock.getRate()
    if running:
        TRJA_ClockStatusLabel.setForeground(awt.Color.WHITE)
        TRJA_ClockStatusLabel.setText("Clock running")
    else:
        TRJA_ClockStatusLabel.setForeground(awt.Color.RED)
        TRJA_ClockStatusLabel.setText("Clock paused")
    TRJA_ClockRateLabel.setText("<html>Clock rate: <font color=#00FF00>%.1f</font></html>" % rate)
TRJA_FastClock.addPropertyChangeListener(TRJA_UpdateClock)
TRJA_UpdateClock()

# ------ Header rows ------
TRJA_HeaderPanel = swing.JPanel()
TRJA_HeaderPanel.setLayout(swing.BoxLayout(TRJA_HeaderPanel, swing.BoxLayout.X_AXIS))
TRJA_HeaderPanel.setBackground(awt.Color.BLACK)
TRJA_HeaderPanel.setBorder(swing.BorderFactory.createEmptyBorder(6, 30, 6, 30))
TRJA_LeftLabel = swing.JLabel("TCTRW87  T R U S T   TRJA Enquiry Output")
TRJA_LeftLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_LeftLabel.setForeground(awt.Color.GREEN)
TRJA_LeftLabel.setBackground(awt.Color.BLACK)
TRJA_LeftLabel.setOpaque(True)
TRJA_RightLabel = swing.JLabel(" %s %s" % (TRJA_CurrentDay, TRJA_CurrentTimeStr))
TRJA_RightLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_RightLabel.setForeground(awt.Color.WHITE)
TRJA_RightLabel.setBackground(awt.Color.BLACK)
TRJA_RightLabel.setOpaque(True)
TRJA_PageLabel = swing.JLabel("Page 1... of 1")
TRJA_PageLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_PageLabel.setForeground(awt.Color.WHITE)
TRJA_PageLabel.setBackground(awt.Color.BLACK)
TRJA_PageLabel.setOpaque(True)
TRJA_HeaderPanel.add(TRJA_LeftLabel)
TRJA_HeaderPanel.add(swing.Box.createHorizontalGlue())
TRJA_HeaderPanel.add(TRJA_RightLabel)
TRJA_HeaderPanel.add(swing.Box.createHorizontalStrut(36))
TRJA_HeaderPanel.add(TRJA_PageLabel)

TRJA_LineupPanel = swing.JPanel()
TRJA_LineupPanel.setLayout(awt.FlowLayout(awt.FlowLayout.LEFT, 0, 0))
TRJA_LineupPanel.setBackground(awt.Color.BLACK)
TRJA_LineupPanel.setBorder(swing.BorderFactory.createEmptyBorder(0, 30, 12, 30))
TRJA_LineupLabel = swing.JLabel("TRUST LineUp for %s at %s %s + trains not departed" % (TRJA_Profile.getName(), TRJA_CurrentDay, TRJA_CurrentTimeStr))
TRJA_LineupLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_LineupLabel.setForeground(awt.Color.WHITE)
TRJA_LineupLabel.setBackground(awt.Color.BLACK)
TRJA_LineupLabel.setOpaque(True)
TRJA_LineupPanel.add(TRJA_LineupLabel)

TRJA_BookedPanel = swing.JPanel()
TRJA_BookedPanel.setLayout(swing.BoxLayout(TRJA_BookedPanel, swing.BoxLayout.X_AXIS))
TRJA_BookedPanel.setBackground(awt.Color.BLACK)
TRJA_BookedPanel.setBorder(swing.BorderFactory.createEmptyBorder(0, 20, 4, 20))
TRJA_BookedLabel = swing.JLabel("Booked", swing.SwingConstants.CENTER)
TRJA_BookedLabel.setFont(awt.Font("Monospaced", awt.Font.PLAIN, 16))
TRJA_BookedLabel.setForeground(awt.Color.WHITE)
TRJA_BookedLabel.setBackground(awt.Color.BLACK)
TRJA_BookedLabel.setOpaque(True)
TRJA_BookedLeftStrut = swing.Box.createHorizontalStrut(0)
TRJA_BookedPanel.add(TRJA_BookedLeftStrut)
TRJA_BookedContainer = swing.JPanel(awt.FlowLayout(awt.FlowLayout.LEFT, 0, 0))
TRJA_BookedContainer.setBackground(awt.Color.BLACK)
TRJA_BookedContainer.add(TRJA_BookedLabel)
TRJA_BookedPanel.add(TRJA_BookedContainer)
TRJA_BookedPanel.add(swing.Box.createHorizontalGlue())

def TRJA_PositionBookedHeader():
    try:
        hdr = TRJA_Table.getTableHeader()
        cm = TRJA_Table.getColumnModel()
        if cm is None or cm.getColumnCount() < 7:
            return
        r_arr = hdr.getHeaderRect(2)
        r_dep = hdr.getHeaderRect(3)
        leftMargin = 20
        start_x = r_arr.x
        span_w = (r_dep.x + r_dep.width) - r_arr.x
        TRJA_BookedLeftStrut.setPreferredSize(awt.Dimension(leftMargin + start_x, 1))
        TRJA_BookedContainer.setPreferredSize(awt.Dimension(span_w, TRJA_BookedLabel.getPreferredSize().height))
        TRJA_BookedPanel.revalidate()
        TRJA_BookedPanel.repaint()
    except:
        pass

def TRJA_PositionBookedHeaderLater():
    SwingUtilities.invokeLater(TRJA_PositionBookedHeader)

class TRJA_HeaderResizer(ComponentAdapter):
    def componentResized(self, e): TRJA_PositionBookedHeaderLater()
TRJA_Table.getTableHeader().addComponentListener(TRJA_HeaderResizer())

class TRJA_ColModelListener(TableColumnModelListener):
    def columnAdded(self, e): TRJA_PositionBookedHeaderLater()
    def columnRemoved(self, e): TRJA_PositionBookedHeaderLater()
    def columnMoved(self, e): TRJA_PositionBookedHeaderLater()
    def columnMarginChanged(self, e): TRJA_PositionBookedHeaderLater()
    def columnSelectionChanged(self, e): pass
TRJA_Table.getColumnModel().addColumnModelListener(TRJA_ColModelListener())

TRJA_Frame = swing.JFrame("WinVV Session 1")
TRJA_Frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
TRJA_Frame.setSize(800, 600)

# Set window icon using TASIcon utility
try:
    from TASIcon import SetFrameClockIcon
    SetFrameClockIcon(TRJA_Frame, 32)  # 32px icon size
except Exception as ex:
    print("[TRUST-TRJA] Failed to set window icon: " + str(ex))

TRJA_Frame.getContentPane().setBackground(awt.Color.BLACK)
TRJA_Frame.setLayout(swing.BoxLayout(TRJA_Frame.getContentPane(), swing.BoxLayout.Y_AXIS))
TRJA_Frame.getContentPane().add(TRJA_HeaderPanel)
TRJA_Frame.getContentPane().add(TRJA_LineupPanel)
TRJA_Frame.getContentPane().add(TRJA_BookedPanel)
TRJA_Frame.getContentPane().add(TRJA_ScrollPane)
TRJA_Frame.getContentPane().add(TRJA_FooterPanel)

# ------ Core: Rebuild + timing-aware culling (unchanged logic except "Train" display) ------
def TRJA_RebuildFilteredData():
    global TRJA_FilteredData, TRJA_TodayTrains, TRJA_TomorrowTrains, TRJA_NextDay
    TRJA_FilteredData = []
    TRJA_TodayTrains = []
    TRJA_TomorrowTrains = []
    currentTimeStr_local = TRJA_TimeMem.getValue() or ""
    currentDay_local = TRJA_DayMem.getValue() or ""
    currentMinutes = TRJA_MinutesNow()
    TRJA_NextDay = TRJA_GetNextDay(currentDay_local)

    if not os.path.exists(TRJA_TimetableFile):
        TRJA_UpdatePageIndicator()
        return

    with open(TRJA_TimetableFile, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    # Next day that has trains
    nd = TRJA_NextDay
    while nd and not any(row.get(nd, "").strip().lower() == "true" for row in rows):
        nd = TRJA_GetNextDay(nd)
    TRJA_NextDay = nd

    # forms inheritance map (unchanged)
    formsFrom = {}
    for row in rows:
        reportingNumber = (row.get("Reporting number", "") or "").strip()
        formsNext = (row.get("Forms", "") or "").strip()
        if formsNext:
            formsFrom.setdefault(formsNext, []).append(reportingNumber)

    # Day flags per train (unchanged)
    trainDays = {}
    for row in rows:
        reportingNumber = (row.get("Reporting number", "") or "").strip()
        trainDays[reportingNumber] = {
            day: (row.get(day, "") or "").strip().lower() == "true"
            for day in TRJA_DaysOfWeek
        }

    for row in rows:
        rn = (row.get("Reporting number", "") or "").strip()
        if not rn:
            continue

        arrTime = (row.get("Arr", "") or "").strip()
        depTime = (row.get("Dep", "") or "").strip()
        arrMinutes = TRJA_ParseTimeToMinutes(arrTime) if arrTime else None
        depMinutes = TRJA_ParseTimeToMinutes(depTime) if depTime else None

        # Disruption -> status (unchanged)
        disruption = None
        if rn in formsFrom:
            for sourceTrain in formsFrom[rn]:
                if trainDays.get(sourceTrain, {}).get(currentDay_local, False):
                    inherited = getDisruption(sourceTrain)
                    if inherited is not None:
                        disruption = inherited
                        break
        if disruption is None:
            disruption = getDisruption(rn)
        try:
            delay = int(disruption) if disruption is not None else 0
        except:
            delay = 0
        status = ""
        if disruption is not None:
            if delay == 0: status = "RT TIME"
            elif delay < 0: status = "%d EARLY" % delay
            elif 0 < delay <= 1440: status = "%d LATE" % delay
            elif delay > 1440: status = "CANCELLED"
        else:
            if arrMinutes == currentMinutes or depMinutes == currentMinutes:
                status = "RT TIME"
            elif not arrTime and not depTime:
                status = "CANCELLED"

        platformValue = (row.get("Platform", "") or "").strip()
        arrDisplay = TRJA_FormatTo24Hour(arrTime) if arrTime else "-"
        depDisplay = TRJA_FormatTo24Hour(depTime) if depTime else "-"
        if (platformValue == "") and (not arrTime):
            arrDisplay = "PASS"

        dispTP, dispTime = TRJA_GetLastReportForTrain_Display(rn, currentDay_local, currentMinutes)

        baseReportMin = TRJA_FindLatestTimingForRNAtTP(TRJA_BaseTPName, rn, currentDay_local)
        lastTPName, lastSchedMin = TRJA_GetLastScheduledTP(row)
        lastTPReportMin = TRJA_FindLatestTimingForRNAtTP(lastTPName, rn, currentDay_local) if lastTPName else None       
        # Time-warp & timing-based RT: if we saw a timing at base or last scheduled TP within ±1 minute of now, treat as RT TIME
        if status == "":
            if (baseReportMin is not None and currentMinutes is not None and abs(currentMinutes - baseReportMin) <= 1) \
               or (lastTPReportMin is not None and currentMinutes is not None and abs(currentMinutes - lastTPReportMin) <= 1):
                status = "RT TIME"      
        isArrOnly = (arrTime and not depTime)
        runsToday = ((row.get(currentDay_local, "") or "").strip().lower() == "true")
        runsNext = (TRJA_NextDay and (row.get(TRJA_NextDay, "") or "").strip().lower() == "true")
        include = False

        if runsToday:
            if isArrOnly:
                if (arrMinutes is not None and currentMinutes is not None and arrMinutes >= currentMinutes):
                    include = True
                elif (baseReportMin is not None and currentMinutes is not None and currentMinutes <= baseReportMin + 1):
                    include = True
            else:
                if depMinutes is not None and currentMinutes is not None and depMinutes >= currentMinutes:
                    include = True
                else:
                    if TRJA_KEEP_AFTER_DEPART_UNTIL_LAST_TP:
                        if lastTPName:
                            if lastTPReportMin is None:
                                include = True
                            else:
                                if currentMinutes is not None and currentMinutes <= lastTPReportMin:
                                    include = True
                        else:
                            if baseReportMin is not None and currentMinutes is not None and currentMinutes <= baseReportMin + 1:
                                include = True
                    else:
                        if baseReportMin is not None and currentMinutes is not None and currentMinutes <= baseReportMin + 1:
                            include = True

        if runsNext and not include and currentMinutes is not None:
            minsList = [m for m in (arrMinutes, depMinutes) if m is not None]
            if minsList:
                firstDef = min(minsList)
                if firstDef <= currentMinutes + 1440:
                    keyTime = firstDef + 1440
                    TRJA_TomorrowTrains.append((keyTime, None))
 
        if include:
            displayTrain = rn if not TU.IsDefaultReportingNumber(rn) else ""
            overdueDisplay = TRJA_ComputeOverdueReport(row, rn, currentDay_local, currentMinutes)
            trainEntry = [
                ".", displayTrain, arrDisplay, depDisplay,
                dispTP, dispTime, status, overdueDisplay
            ]
            keyTime = min([m for m in (arrMinutes, depMinutes) if m is not None]) if (arrMinutes is not None or depMinutes is not None) else 10**9
            TRJA_TodayTrains.append((keyTime, trainEntry))

    TRJA_TodayTrains.sort(key=lambda x: x[0])
    TRJA_FilteredData[:] = [entry for _, entry in TRJA_TodayTrains]
    TRJA_ClampPageAndRefreshIndicator()

def TRJA_UpdateTimetable(event=None):
    value = TRJA_TimetableMem.getValue() or ""
    TRJA_TimetableLabel.setText("Timetable: " + value)
    TRJA_RebuildFilteredData()
    TRJA_UpdateTable()

def TRJA_UpdateHeader(event=None):
    currentTime_local = TRJA_TimeMem.getValue() or ""
    currentDay_local = TRJA_DayMem.getValue() or ""
    try:
        parsed = TRJA_TimeParser.parse(currentTime_local)
        formattedTime = TRJA_Out24.format(parsed)
    except:
        formattedTime = currentTime_local
    TRJA_RightLabel.setText(" %s %s" % (currentDay_local, formattedTime))
    TRJA_RebuildFilteredData()
    TRJA_LineupLabel.setText("TRUST LineUp for %s at %s %s + trains not departed" % (TRJA_Profile.getName(), currentDay_local, formattedTime))
    TRJA_UpdateTable()

TRJA_TimetableMem.addPropertyChangeListener(TRJA_UpdateTimetable)
TRJA_TimeMem.addPropertyChangeListener(TRJA_UpdateHeader)
TRJA_DayMem.addPropertyChangeListener(TRJA_UpdateHeader)

# ------ Build initial content ------
TRJA_RebuildFilteredData()
TRJA_UpdateTable()
TRJA_UpdateTimetable()
TRJA_UpdateHeader()

class TRJA_PageKeyListener(event.KeyAdapter):
    def keyPressed(self, e):
        code = e.getKeyCode()
        if code == event.KeyEvent.VK_RIGHT:
            if (TRJA_CurrentPage[0] + 1) * TRJA_PageSize < len(TRJA_FilteredData):
                TRJA_CurrentPage[0] += 1
                TRJA_UpdateTable()
        elif code == event.KeyEvent.VK_LEFT:
            if TRJA_CurrentPage[0] > 0:
                TRJA_CurrentPage[0] -= 1
                TRJA_UpdateTable()

TRJA_Frame.addKeyListener(TRJA_PageKeyListener())
TRJA_Frame.setFocusable(True)
TRJA_Frame.requestFocusInWindow()
TRJA_Frame.setVisible(True)
TRJA_PositionBookedHeaderLater()