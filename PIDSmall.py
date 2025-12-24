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

# Passenger Information Display (per platform) for JMRI 5.12
# - One PID window per platform found in the timetable
# - Each window shows next 3 departures for that platform
# - Disruption inheritance, smooth alternation/scrolling preserved
# - Platform alteration hook via Memory "PID_PLATFORM_OVERRIDES"
#
# * A working is removed ONLY when it is recorded as having DEPARTED at the configured timing point(s).
#   Default timing point = active profile name (base TP). Override via Memory "PID_DEPARTURE_TP"
#   (single TP name or a comma/semicolon separated list). This makes the PID compatible with future
#   use of other physical/virtual timing points.
#
# * csv_rows(): hardened to avoid calling list(reader) to survive global name shadowing.
#
# <<PID-DISP-NAME: Small modern platform display>>
# <<DESCRIPTION: Orange LED scrolling text showing the time, the next train with calling pattern and the two trains after that>>

import javax.swing as swing
import java.awt as awt
from java.awt import Color, Font
from javax.swing import Timer
import jmri
from jmri import InstanceManager
import os, csv
import java.text.SimpleDateFormat as SimpleDateFormat
from DisruptionRegister import getDisruption
import TimingRegister as TR  # read-only access to timing tuples
import TASBeanLookup as TBL
import PlatformAllocationRegister as PAR  # allocation takes precedence over timetable/overrides 

# -------------------- THEME / UI CONFIG --------------------
WINDOW_WIDTH = 800  # width of the content area (panels)
WINDOW_HEIGHT = 300
RIGHT_PADDING = 15  # black gutter on the right (frame is wider by this many px)
FRAME_COLOR = Color.BLACK
PANEL_COLOR = Color(30, 20, 0)
TEXT_COLOR = Color(255, 200, 50)
TOP_FONT_SIZE = 36
MID_FONT_SIZE = 24
CLOCK_FONT_SIZE = 48
SECONDS_FONT_SIZE = 24
SCROLL_SPEED = 30   # ms; marquee speed for "Calling at"
ALT_INTERVAL = 10000  # ms; alternate 2nd/3rd every 10s
VERTICAL_SCROLL_STEPS = 20
VERTICAL_SCROLL_SPEED = 20  # ms per vertical step
STEP_SIZE = 2
TIME_WIDTH = 130    # fixed width for time fields ("HH:mm" or "CANCELLED")
STATUS_WIDTH = 50   # width for "Exp"
STATUS_GAP_PX = 2  # gap between status and time
DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

# Default fonts (so we can restore after scaling)
DEFAULT_TOP_FONT = Font("SansSerif", Font.BOLD, TOP_FONT_SIZE)
DEFAULT_MID_FONT = Font("SansSerif", Font.BOLD, MID_FONT_SIZE)

# ------------------------- MEMORIES / FAST CLOCK -------------------------
# Use TASBeanLookup to obtain Memory beans by suffix (prefix-agnostic across IM/I2M/I3M...).
timeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
dayMem = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
timetableMem = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
# Optional: list of departure timing points (single name or ';' / ',' separated).
departTPMem = TBL.ProvideMemoryBySuffix("PID_DEPARTURE_TP", "")
# Optional override hook: e.g., "2G56=2;1W76=1"
overridesMem = TBL.ProvideMemoryBySuffix("PID_PLATFORM_OVERRIDES", "")

timebase = InstanceManager.getDefault(jmri.Timebase)

# -------------------- TIME PARSING HELPERS --------------------
timeParser = SimpleDateFormat("h:mm a")  # 12-hour like "6:44 AM"
altParser  = SimpleDateFormat("H:mm")    # 24-hour like "06:44"

def parseTimeToMinutes(timeStr):
    for parser in [timeParser, altParser]:
        try:
            parsed = parser.parse(timeStr)
            return parsed.getHours() * 60 + parsed.getMinutes()
        except:
            pass
    return None

def formatTo24Hour(timeStr):
    for parser in [timeParser, altParser]:
        try:
            parsed = parser.parse(timeStr)
            return SimpleDateFormat("HH:mm").format(parsed)
        except:
            pass
    return timeStr

# -------------------- TEXT FIT HELPERS --------------------
def scaleTextToFit(label, text, maxSize, minSize, width):
    """
    Downscale label font size so 'text' fits within 'width' (px).
    Keeps font family/style; only size changes. Stops at minSize.
    """
    family = label.getFont().getFamily()
    style  = label.getFont().getStyle()
    for size in range(maxSize, minSize - 1, -1):
        f  = Font(family, style, size)
        fm = label.getFontMetrics(f)
        if fm.stringWidth(text) <= width:
            label.setFont(f)
            label.setText(text)
            return
    label.setFont(Font(family, style, minSize))
    label.setText(text)

def setTimeLabel(label, text, isTop, isCancelled):
    """
    Set the time label text:
    * For CANCELLED: auto-scale to fit in TIME_WIDTH.
    * Otherwise: restore default font size and set text.
    """
    if isCancelled:
        if isTop:
            scaleTextToFit(label, text, TOP_FONT_SIZE, 18, TIME_WIDTH)
        else:
            scaleTextToFit(label, text, MID_FONT_SIZE, 16, TIME_WIDTH)
    else:
        label.setFont(DEFAULT_TOP_FONT if isTop else DEFAULT_MID_FONT)
        label.setText(text)

def setStatusLabel(label, text, isTop):
    """
    Set the status label (e.g., 'Exp') with auto-scaling to STATUS_WIDTH.
    Empty text clears and restores default font.
    """
    if not text:
        label.setFont(DEFAULT_MID_FONT)
        label.setText("")
        return
    # For now, same scaling both top and mid lines
    scaleTextToFit(label, text, MID_FONT_SIZE, 12, STATUS_WIDTH)

# -------------------- OVERRIDE PROVIDER (future platform alterations) --------------------
def parseOverrides(s):
    """
    Parse strings like: "2G56=2;1W76=1" (semicolon or comma separated)
    -> returns dict { "2G56": "2", "1W76": "1" }
    """
    out = {}
    if not s: return out
    parts = s.replace(",", ";").split(";")
    for p in parts:
        p = p.strip()
        if not p: continue
        if "=" in p:
            k,v = p.split("=",1)
            out[k.strip()] = v.strip()
    return out

def getPlatformOverride(reportingNumber):
    try:
        if overridesMem is None: return None
        mapping = parseOverrides(overridesMem.getValue())
        return mapping.get(reportingNumber)
    except:
        return None

# -------------------- TIMETABLE ACCESS --------------------
def timetable_path():
    name = timetableMem.getValue() or ""
    profilePath = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
    return os.path.join(profilePath, "timetable", name + ".csv")

def csv_rows():
    """Return all rows from the timetable CSV (tab-delimited). Shadowing-safe (no list())."""
    path = timetable_path()
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for r in reader:
                try:
                    rows.append(r)
                except:
                    pass
    except Exception as ex:
        try:
            print("PID csv_rows() failed:", ex)
        except:
            pass
        return []
    return rows

def platform_field(row):
    """Support both 'Plat' and 'Platform' headers."""
    val = row.get("Plat", "")
    if not val:
        val = row.get("Platform", "")
    return (val or "").strip()

def detect_platforms():
    """Find distinct platforms appearing in the timetable (ignore blanks)."""
    plats = set()
    for row in csv_rows():
        p = platform_field(row)
        if p:
            plats.add(p)
    # Sort: numbers before strings, ascending; then reversed slice present originally
    return sorted(plats, key=lambda x: (x.isdigit(), x))[::-1]

# -------------------- Departure TP selection + logged-departure check --------------------
def _ActiveProfileBaseTPName():
    """Default 'Dep' timing point = active profile name (base TP)."""
    try:
        nm = jmri.profile.ProfileManager.getDefault().getActiveProfile().getName()
        return ("" if nm is None else str(nm)).strip()
    except:
        return ""

def _DepartureTPList():
    """
    Read IMPID_DEPARTURE_TP (single or ';' / ',' separated list).
    If absent/blank, fall back to base timing point (active profile name).
    """
    names = []
    try:
        raw = departTPMem.getValue() if departTPMem is not None else None
        if raw:
            parts = str(raw).replace(",", ";").split(";")
            for p in parts:
                p = p.strip()
                if p:
                    names.append(p)
    except:
        names = []
    if not names:
        base = _ActiveProfileBaseTPName()
        if base:
            names = [base]
    return names

def HasDepartedAtConfiguredTP(reportingNumber, dayName, nowMinutes):
    """
    Return True iff any configured departure timing point contains a timing tuple
    for (reportingNumber, dayName) whose logged time <= nowMinutes.

    TimingRegister tuples are (reportingNumber, direction, time, day). 'time' is a string
    (e.g., '5:53' or '06:41 AM'); we parse it to minutes. Only Dep events are logged,
    so any tuple here is a departure record. (Read-only; relies on TimingRegister API.)
    """
    tps = _DepartureTPList()
    if not tps:
        return False
    for tp in tps:
        try:
            entries = TR.getTiming(tp) or []
        except:
            entries = []
        for rec in entries:
            try:
                rn  = rec[0]
                tstr= rec[2]
                d   = rec[3]
            except:
                continue
            if str(rn) != str(reportingNumber):
                continue
            if str(d)  != str(dayName):
                continue
            mm = parseTimeToMinutes(tstr)
            if mm is None:
                continue
            if mm <= int(nowMinutes):
                return True
    return False


def HasAnyTimingToday(reportingNumber, dayName):
    """
    Return True iff ANY timing point has a timing tuple for (reportingNumber, dayName),
    regardless of the logged minute. This treats the train as 'seen on the layout' today.
    """
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
                rn = rec[0]; d = rec[3]
            except:
                continue
            if str(rn) == str(reportingNumber) and str(d) == str(dayName):
                return True
    return False
    
import java.beans as beans

class _PidPropertyChangeListener(beans.PropertyChangeListener):
    def __init__(self, callback):
        self._callback = callback

    def propertyChange(self, event):
        try:
            self._callback(event)
        except Exception as ex:
            try:
                print("PID propertyChange callback failed:", ex)
            except:
                pass

# -------------------- PID WINDOW (per platform) --------------------

class PIDWindow(object):
    def __init__(self, platform, onCloseCallback=None):
        self.platform = str(platform)
        self.onCloseCallback = onCloseCallback
        self.cleaned = False
        self.platform = str(platform)
        # UI
        self.frame = swing.JFrame("Passenger information display: platform " + self.platform)
        # Make the frame slightly wider by RIGHT_PADDING to create a right-hand black gutter
        self.frame.setSize(WINDOW_WIDTH + RIGHT_PADDING, WINDOW_HEIGHT)
        self.frame.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        self.frame.setResizable(False)
        self.frame.getContentPane().setBackground(FRAME_COLOR)
        self.frame.setLayout(None)
        # Panels: keep their widths at the original content width, so the extra frame width
        # becomes a clean black strip on the right.
        self.topPanel = swing.JPanel()
        self.topPanel.setBackground(PANEL_COLOR)
        self.topPanel.setBounds(10, 10, WINDOW_WIDTH - 20, 50)
        self.topPanel.setLayout(None)
        self.frame.add(self.topPanel)

        self.secondPanel = swing.JPanel()
        self.secondPanel.setBackground(PANEL_COLOR)
        self.secondPanel.setBounds(10, 70, WINDOW_WIDTH - 20, 40)
        self.secondPanel.setLayout(None)
        self.frame.add(self.secondPanel)

        self.thirdPanel = swing.JPanel()
        self.thirdPanel.setBackground(PANEL_COLOR)
        self.thirdPanel.setBounds(10, 120, WINDOW_WIDTH - 20, 40)
        self.thirdPanel.setLayout(None)
        self.frame.add(self.thirdPanel)

        clockPanelWidth = 250
        self.clockPanel = swing.JPanel()
        self.clockPanel.setBackground(PANEL_COLOR)
        # Center the clock within the content area (not including the right gutter)
        self.clockPanel.setBounds((WINDOW_WIDTH - clockPanelWidth)//2, 180, clockPanelWidth, 70)
        self.clockPanel.setLayout(None)
        self.frame.add(self.clockPanel)

        # --- Top line labels ---
        self.topLabelDest = swing.JLabel("")
        self.topLabelDest.setForeground(TEXT_COLOR)
        self.topLabelDest.setFont(DEFAULT_TOP_FONT)
        self.topLabelDest.setBounds(10, 5, 500, 40)
        self.topPanel.add(self.topLabelDest)

        self.topLabelTime = swing.JLabel("")
        self.topLabelTime.setForeground(TEXT_COLOR)
        self.topLabelTime.setFont(DEFAULT_TOP_FONT)
        self.topLabelTime.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.topLabelTime.setBounds(self.topPanel.getWidth() - TIME_WIDTH - 10, 5, TIME_WIDTH, 40)
        self.topPanel.add(self.topLabelTime)

        # Status label ("Exp") tight to the left of time
        self.topLabelStatus = swing.JLabel("")
        self.topLabelStatus.setForeground(TEXT_COLOR)
        self.topLabelStatus.setFont(DEFAULT_MID_FONT)  # smaller than time
        self.topLabelStatus.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.topLabelStatus.setBounds(self.topLabelTime.getX() - STATUS_WIDTH - STATUS_GAP_PX, 5, STATUS_WIDTH, 40)
        self.topPanel.add(self.topLabelStatus)

        # --- "Calling at" row ---
        self.staticLabel = swing.JLabel("Calling at:")
        self.staticLabel.setForeground(TEXT_COLOR)
        self.staticLabel.setFont(DEFAULT_MID_FONT)
        self.staticLabel.setBounds(10, 5, 150, 30)
        self.secondPanel.add(self.staticLabel)

        self.scrollPanel = swing.JPanel()
        self.scrollPanel.setLayout(None)
        self.scrollPanel.setOpaque(False)
        self.scrollPanel.setBounds(self.staticLabel.getX() + self.staticLabel.getWidth() + 10,
                                   5, self.secondPanel.getWidth() - self.staticLabel.getWidth() - 30, 30)
        self.secondPanel.add(self.scrollPanel)

        self.scrollLabel = swing.JLabel("")
        self.scrollLabel.setForeground(TEXT_COLOR)
        self.scrollLabel.setFont(DEFAULT_MID_FONT)
        self.scrollLabel.setBounds(self.scrollPanel.getWidth(), 0, 20000, 30)
        self.scrollPanel.add(self.scrollLabel)

        # --- Alternating lines (2nd/3rd) ---
        self.altLabel1 = swing.JLabel("")
        self.altLabel1.setForeground(TEXT_COLOR)
        self.altLabel1.setFont(DEFAULT_MID_FONT)
        self.altLabel1.setBounds(10, 0, 400, 40)
        self.thirdPanel.add(self.altLabel1)

        self.altTime1 = swing.JLabel("")
        self.altTime1.setForeground(TEXT_COLOR)
        self.altTime1.setFont(DEFAULT_MID_FONT)
        self.altTime1.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.altTime1.setBounds(self.thirdPanel.getWidth() - TIME_WIDTH - 10, 0, TIME_WIDTH, 40)
        self.thirdPanel.add(self.altTime1)

        self.altStatus1 = swing.JLabel("")
        self.altStatus1.setForeground(TEXT_COLOR)
        self.altStatus1.setFont(DEFAULT_MID_FONT)
        self.altStatus1.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.altStatus1.setBounds(self.altTime1.getX() - STATUS_WIDTH - STATUS_GAP_PX, 0, STATUS_WIDTH, 40)
        self.thirdPanel.add(self.altStatus1)

        self.altLabel2 = swing.JLabel("")
        self.altLabel2.setForeground(TEXT_COLOR)
        self.altLabel2.setFont(DEFAULT_MID_FONT)
        self.altLabel2.setBounds(10, 40, 400, 40)
        self.thirdPanel.add(self.altLabel2)

        self.altTime2 = swing.JLabel("")
        self.altTime2.setForeground(TEXT_COLOR)
        self.altTime2.setFont(DEFAULT_MID_FONT)
        self.altTime2.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.altTime2.setBounds(self.thirdPanel.getWidth() - TIME_WIDTH - 10, 40, TIME_WIDTH, 40)
        self.thirdPanel.add(self.altTime2)

        self.altStatus2 = swing.JLabel("")
        self.altStatus2.setForeground(TEXT_COLOR)
        self.altStatus2.setFont(DEFAULT_MID_FONT)
        self.altStatus2.setHorizontalAlignment(swing.SwingConstants.RIGHT)
        self.altStatus2.setBounds(self.altTime2.getX() - STATUS_WIDTH - STATUS_GAP_PX, 40, STATUS_WIDTH, 40)
        self.thirdPanel.add(self.altStatus2)

        # --- Clock ---
        self.clockLabel = swing.JLabel()
        self.clockLabel.setForeground(TEXT_COLOR)
        self.clockLabel.setHorizontalAlignment(swing.SwingConstants.CENTER)
        self.clockLabel.setBounds(0, 5, clockPanelWidth, 60)
        self.clockLabel.setFont(Font("SansSerif", Font.BOLD, CLOCK_FONT_SIZE))
        self.clockPanel.add(self.clockLabel)

        # timers + models
        self.clockTimer = Timer(1000, self.updateClock)
        self.scrollTimer = Timer(SCROLL_SPEED, self.scrollText)
        self.altTimer = None
        self.animTimer = None
        self.animStep = 0
        # models for alternation (include status)
        self.altModel1 = {"dest": "", "time": "", "status": ""}
        self.altModel2 = {"dest": "", "time": "", "status": ""}
        # Track last "HH:mm" so we refresh only when minute changes
        self.lastMinuteKey = None

        # listeners (store a real Java listener instance so we can remove it reliably)
        self._displayListener = _PidPropertyChangeListener(self.updateDisplay)

        timeMem.addPropertyChangeListener(self._displayListener)
        dayMem.addPropertyChangeListener(self._displayListener)
        if timetableMem is not None:
            timetableMem.addPropertyChangeListener(self._displayListener)
        if overridesMem is not None:
            overridesMem.addPropertyChangeListener(self._displayListener)
        if departTPMem is not None:
            departTPMem.addPropertyChangeListener(self._displayListener)
        
        # Also refresh immediately on platform allocation register events
        try:
            PAR.addPlatformListener(self._displayListener)
        except Exception as ex:
            try:
                print("[PIDSmall] Failed to add platform allocation listener:", ex)
            except:
                pass

        # close handler
        import java.awt.event as awtevent
        class CloseHandler(awtevent.WindowAdapter):
            def windowClosing(inner_self, e):
                self.cleanup(e)

            def windowClosed(inner_self, e):
                self.cleanup(e)

        self.frame.addWindowListener(CloseHandler())

        # Kick off
        self.clockTimer.start()
        self.scrollTimer.start()
        self.updateDisplay()     
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self.frame, 32)  # 32px icon size
        except Exception as ex:
            print("[PIDCRTSingle] Failed to set PID window icon: " + str(ex))
        
        self.frame.setVisible(True)

    # -------------------- Clock --------------------
    def updateClock(self, event):
        if timebase is not None:
            fast_time = timebase.getTime()
            fmtH = SimpleDateFormat("HH:mm")
            fmtS = SimpleDateFormat("ss")
            hhmm = fmtH.format(fast_time)
            self.clockLabel.setText(
                "<html><span style='font-size:%dpx'>%s</span>"
                "<span style='font-size:%dpx'>:%s</span></html>"
                % (CLOCK_FONT_SIZE, hhmm, SECONDS_FONT_SIZE, fmtS.format(fast_time))
            )
            # Refresh departures when the minute changes (authoritative fast clock)
            if self.lastMinuteKey != hhmm:
                self.lastMinuteKey = hhmm
                try:
                    self.updateDisplay()
                except Exception as ex:
                    print("PID refresh on minute change failed:", ex)
        else:
            self.clockLabel.setText(
                "<html><span style='font-size:%dpx'>--:--</span></html>" % CLOCK_FONT_SIZE
            )

    # -------------------- Scrolling marquee --------------------
    def scrollText(self, event):
        x = self.scrollLabel.getX() - 2
        if x < -self.scrollLabel.getWidth():
            x = self.scrollPanel.getWidth()
        self.scrollLabel.setLocation(x, self.scrollLabel.getY())

    # -------------------- Alternation animation --------------------
    def setVisibleAltLabelsFromModels(self):
        # Destinations
        self.altLabel1.setText(self.altModel1["dest"])
        self.altLabel2.setText(self.altModel2["dest"])
        # Times (with scaling for CANCELLED)
        setTimeLabel(self.altTime1, self.altModel1["time"],
                     isTop=False, isCancelled=(self.altModel1["time"] == "CANCELLED"))
        setTimeLabel(self.altTime2, self.altModel2["time"],
                     isTop=False, isCancelled=(self.altModel2["time"] == "CANCELLED"))
        # Status (auto-scale to avoid "E...")
        setStatusLabel(self.altStatus1, self.altModel1.get("status",""), isTop=False)
        setStatusLabel(self.altStatus2, self.altModel2.get("status",""), isTop=False)

    def prepareAltPositions(self):
        # Keep labels aligned for vertical scroll animation
        self.altLabel1.setLocation(10, 0)
        self.altTime1.setLocation(self.thirdPanel.getWidth() - TIME_WIDTH - 10, 0)
        self.altStatus1.setLocation(self.altTime1.getX() - STATUS_WIDTH - STATUS_GAP_PX, 0)
        self.altLabel2.setLocation(10, 40)
        self.altTime2.setLocation(self.thirdPanel.getWidth() - TIME_WIDTH - 10, 40)
        self.altStatus2.setLocation(self.altTime2.getX() - STATUS_WIDTH - STATUS_GAP_PX, 40)
        self.thirdPanel.repaint()

    def animStepAction(self, event):
        if self.animStep >= VERTICAL_SCROLL_STEPS:
            try:
                self.animTimer.stop()
            except:
                pass
            self.animTimer = None
            self.animStep = 0
            # swap models (dest, time, status)
            m1d, m1t, m1s = self.altModel1["dest"], self.altModel1["time"], self.altModel1["status"]
            m2d, m2t, m2s = self.altModel2["dest"], self.altModel2["time"], self.altModel2["status"]
            self.altModel1["dest"], self.altModel1["time"], self.altModel1["status"] = m2d, m2t, m2s
            self.altModel2["dest"], self.altModel2["time"], self.altModel2["status"] = m1d, m1t, m1s
            self.setVisibleAltLabelsFromModels()
            self.prepareAltPositions()
            return
        dy = -STEP_SIZE
        self.altLabel1.setLocation(self.altLabel1.getX(), self.altLabel1.getY() + dy)
        self.altTime1.setLocation(self.altTime1.getX(), self.altTime1.getY() + dy)
        self.altStatus1.setLocation(self.altStatus1.getX(), self.altStatus1.getY() + dy)
        self.altLabel2.setLocation(self.altLabel2.getX(), self.altLabel2.getY() + dy)
        self.altTime2.setLocation(self.altTime2.getX(), self.altTime2.getY() + dy)
        self.altStatus2.setLocation(self.altStatus2.getX(), self.altStatus2.getY() + dy)
        self.thirdPanel.repaint()
        self.animStep += 1

    def startAnimation(self):
        if self.animTimer is not None:
            return
        self.animStep = 0
        self.animTimer = Timer(VERTICAL_SCROLL_SPEED, self.animStepAction)
        self.animTimer.start()

    def switchAlt(self, event):
        self.prepareAltPositions()
        self.startAnimation()

    def startAltTimer(self):
        if self.altTimer:
            try: self.altTimer.stop()
            except: pass
        self.altTimer = Timer(ALT_INTERVAL, self.switchAlt)
        self.altTimer.start()

    def stopAltTimer(self):
        if self.altTimer:
            try: self.altTimer.stop()
            except: pass
        self.altTimer = None

    # -------------------- Timetable logic (filtered by platform) --------------------
    def getNextTrains(self):
        rows = csv_rows()
        # Day always from memory
        currentDay = dayMem.getValue() or ""

        # Authoritative current minutes from fast clock (fall back to IMCURRENTTIME)
        if timebase is not None:
            ft = timebase.getTime()  # java.util.Date
            currentMinutes = ft.getHours() * 60 + ft.getMinutes()
        else:
            currentTimeStr = timeMem.getValue() or ""
            currentMinutes = parseTimeToMinutes(currentTimeStr)
        if currentMinutes is None:
            return []

        # --- Build per-day index + formation map (for inheritance) ---
        rows_today = []
        for r in rows:
            if (r.get(currentDay, "") or "").strip().lower() == "true":
                rows_today.append(r)

        # Map RN -> list(rows) for today (RN can appear multiple times)
        by_rn = {}
        for r in rows_today:
            rn0 = (r.get("Reporting number", "") or "").strip()
            by_rn.setdefault(rn0, []).append(r)

        # Map child RN -> list(former rows) for today (formation inheritance)
        formers_map = {}
        for r in rows_today:
            child = (r.get("Forms", "") or "").strip()
            if child:
                formers_map.setdefault(child, []).append(r)

        # Minutes -> "HH:mm"
        def mm_to_HHmm(total):
            if total is None:
                return ""
            total %= (24 * 60)
            h = total // 60
            m = total % 60
            return "%02d:%02d" % (h, m)

        # Recursive delay resolver with formation inheritance
        # Returns ('cancel', None) / ('delay', minutes>0) / ('ontime', 0)
        def resolve_delay(rn, sched_dep_min, visited=None):
            if visited is None:
                visited = set()
            if rn in visited:
                return ("ontime", 0)  # loop guard
            visited.add(rn)
            # 1) Direct disruption, if any
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
                # delay == 0 -> try inheritance
            # 2) Inherit from the forming working(s) for today
            formers = formers_map.get(rn, [])
            if not formers:
                return ("ontime", 0)
            # Prefer the former that arrives closest BEFORE the scheduled departure
            chosen = None
            if sched_dep_min is not None:
                before = []
                for fr in formers:
                    arr = (fr.get("Arr", "") or "").strip()
                    arr_min = parseTimeToMinutes(arr) if arr else None
                    if arr_min is not None and arr_min <= sched_dep_min:
                        before.append((arr_min, fr))
                if before:
                    before.sort(key=lambda t: t[0])
                    chosen = before[-1][1]
            if chosen is None:
                chosen = formers[0]
            former_rn = (chosen.get("Reporting number", "") or "").strip()
            return resolve_delay(former_rn, sched_dep_min, visited)

        trains = []
        for row in rows_today:
            depTime = (row.get("Dep", "") or "").strip()
            if not depTime:
                continue
                
            # Platform precedence: allocation register > timetable
            rn = (row.get("Reporting number", "") or "").strip()
            alloc = PAR.getPlatform(rn)
            if alloc is not None and str(alloc).strip():
                plat = str(alloc).strip()
            else:
                plat = getPlatformOverride(rn) or platform_field(row)
            if str(plat) != self.platform:
                continue

            depMinutes = parseTimeToMinutes(depTime)
            if depMinutes is None:
                continue

            destination = (row.get("Destination", "") or "").strip()
            callingPattern = (row.get("Calling pattern", "") or "").strip()

            # --- Delay logic (direct or inherited) ---
            try:
                direct = getDisruption(rn)
            except:
                direct = None

            chosen_kind = "ontime"
            chosen_val = 0

            if direct is not None:
                try:
                    d0 = int(direct)
                except:
                    d0 = 0
                if d0 >= 1440:
                    chosen_kind = "cancel"
                elif d0 > 0:
                    chosen_kind, chosen_val = "delay", d0
                else:
                    chosen_kind, chosen_val = resolve_delay(rn, depMinutes)
            else:
                chosen_kind, chosen_val = resolve_delay(rn, depMinutes)

            # --- Compute display & ordering ---
            status = ""
            adjustedMinutes = depMinutes  # default (on time)
            display_time = formatTo24Hour(depTime)  # scheduled by default ("HH:mm")

            if chosen_kind == "cancel":
                status = "CANCELLED"
                display_time = "CANCELLED"
                adjustedMinutes = 9999  # push to end but still show
                departed = False  # no Dep timing for a cancellation

            elif chosen_kind == "delay" and chosen_val and chosen_val > 0:
                status = "Exp"
                adjustedMinutes = depMinutes + chosen_val
                display_time = mm_to_HHmm(adjustedMinutes)
                departed = HasDepartedAtConfiguredTP(rn, currentDay, currentMinutes)

            else:
                # on time
                departed = HasDepartedAtConfiguredTP(rn, currentDay, currentMinutes)

            if departed:
                continue
    
            # --- Resilience filter ---
            # If there is NO disruption entry for this RN AND no timing anywhere for today,
            # only show the train if the booked Dep is still >= nowMinutes.
            # (Do NOT apply this when chosen_kind != 'ontime' so inherited delays remain shown.)
            if (direct is None) and (chosen_kind == "ontime") and (not HasAnyTimingToday(rn, currentDay)):
                if depMinutes < currentMinutes:
                    continue
          
            trains.append({
                "destination": destination,
                "time_text": display_time,
                "status": status if display_time != "CANCELLED" else "CANCELLED",
                "calling": callingPattern,
                "adjusted_minutes": adjustedMinutes
            })

        trains.sort(key=lambda t: t["adjusted_minutes"])
        return trains[:3]

    def updateDisplay(self, event=None):
        trains = self.getNextTrains()
        anim_running = self.animTimer is not None

        if not trains:
            self.topLabelDest.setText("")
            setTimeLabel(self.topLabelTime, "", isTop=True, isCancelled=False)
            setStatusLabel(self.topLabelStatus, "", isTop=True)
            self.scrollLabel.setText("")
            self.altModel1 = {"dest": "", "time": "", "status": ""}
            self.altModel2 = {"dest": "", "time": "", "status": ""}
            self.setVisibleAltLabelsFromModels()
            self.stopAltTimer()
            return

        # First (next) train
        self.topLabelDest.setText(trains[0]["destination"])
        setTimeLabel(self.topLabelTime, trains[0]["time_text"],
                     isTop=True, isCancelled=(trains[0]["time_text"] == "CANCELLED"))
        # "Exp" when applicable; not alongside CANCELLED
        setStatusLabel(self.topLabelStatus,
                       "" if trains[0]["time_text"] == "CANCELLED" else trains[0]["status"],
                       isTop=True)
        self.scrollLabel.setText(trains[0]["calling"])
        self.scrollLabel.setLocation(self.scrollPanel.getWidth(), self.scrollLabel.getY())

        # Alternating lines
        if len(trains) > 1:
            self.altModel1 = {
                "dest": "2nd " + trains[1]["destination"],
                "time": trains[1]["time_text"],
                "status": "" if trains[1]["time_text"] == "CANCELLED" else trains[1]["status"]
            }
        else:
            self.altModel1 = {"dest": "", "time": "", "status": ""}

        if len(trains) > 2:
            self.altModel2 = {
                "dest": "3rd " + trains[2]["destination"],
                "time": trains[2]["time_text"],
                "status": "" if trains[2]["time_text"] == "CANCELLED" else trains[2]["status"]
            }
        else:
            self.altModel2 = {"dest": "", "time": "", "status": ""}

        if not anim_running:
            self.setVisibleAltLabelsFromModels()
            self.prepareAltPositions()

        # Only alternate if we have both 2nd and 3rd
        if self.altModel1["dest"] and self.altModel2["dest"]:
            self.startAltTimer()
        else:
            self.stopAltTimer()

    def cleanup(self, event=None):
        if getattr(self, "cleaned", False):
            return
        self.cleaned = True

        try:
            self.scrollTimer.stop()
        except:
            pass
        try:
            self.clockTimer.stop()
        except:
            pass
        try:
            if self.altTimer:
                self.altTimer.stop()
        except:
            pass
        try:
            if self.animTimer:
                self.animTimer.stop()
        except:
            pass

        # Remove property listeners using the exact listener instance we added
        try:
            if hasattr(self, "_displayListener") and self._displayListener is not None:
                try:
                    timeMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    dayMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    if timetableMem is not None:
                        timetableMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    if overridesMem is not None:
                        overridesMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
                try:
                    if departTPMem is not None:
                        departTPMem.removePropertyChangeListener(self._displayListener)
                except:
                    pass
        except:
            pass
                      
        # Remove platform allocation listener
        try:
            PAR.removePlatformListener(self._displayListener)
        except:
            pass

        # Inform manager (if any) that this window is gone
        try:
            if self.onCloseCallback is not None:
                self.onCloseCallback(self.platform)
        except:
            pass

# -------------------- MANAGER: spawns one window per platform --------------------
class PlatformPIDManager(object):
    def __init__(self):
        self.windows = {}  # platform -> PIDWindow
        if timetableMem is not None:
            timetableMem.addPropertyChangeListener(self.onTimetableChanged)
        if overridesMem is not None:
            overridesMem.addPropertyChangeListener(self.onOverridesChanged)
        if departTPMem is not None:
            departTPMem.addPropertyChangeListener(self.onOverridesChanged)
                  
        # Manager refresh on platform allocation changes
        try:
            self._parListener = _PidPropertyChangeListener(self.onOverridesChanged)
            PAR.addPlatformListener(self._parListener)
        except Exception as ex:
            try:
                print("[PIDSmall] Failed to add manager PAR listener:", ex)
            except:
                pass

        self.buildWindows()

    def buildWindows(self):
        plats = detect_platforms()
        # create missing
        for p in plats:
            if p not in self.windows:
                self.windows[p] = PIDWindow(p, self.onWindowClosed)
        # remove surplus
        to_remove = [p for p in self.windows.keys() if p not in plats]
        for p in to_remove:
            try:
                self.windows[p].cleanup()
                self.windows[p].frame.dispose()
            except:
                pass
            del self.windows[p]
        # arrange windows: cascade by platform number
        x0, y0 = 50, 50
        dx, dy = 40, 40
        idx = 0
        for p in sorted(self.windows.keys(), key=lambda s: (s.isdigit(), int(s) if s.isdigit() else s)):
            w = self.windows[p]
            w.frame.setLocation(x0 + dx*idx, y0 + dy*idx)
            idx += 1

    def onTimetableChanged(self, event):
        self.buildWindows()
        self.refreshAll()

    def onOverridesChanged(self, event):
        self.refreshAll()

    def refreshAll(self):
        for w in self.windows.values():
            w.updateDisplay()

    def onWindowClosed(self, platform):
        # Called by PIDWindow.cleanup() when the user closes a window
        try:
            if platform in self.windows:
                del self.windows[platform]
        except:
            pass

# -------------------- RUN --------------------
PID_Manager = PlatformPIDManager()