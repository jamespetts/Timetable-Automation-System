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
# Teleprinter-style disruption output (static paper stack) for signallers.
#
# <<SIG-DISP-NAME: Teleprinter disruption messages>>
# <<DESCRIPTION: Simulates a 1960s/1970s teleprinter feed of delays, early running and cancellations, printed as a navigable stack of static pages.>>
#
# <<SETTING DESCRIPTION BOOLEAN: Use 24-hour time>>
#
# IMPORTANT DESIGN NOTE (DO NOT "CLEAN UP" WITHOUT ASKING JAMES):
# This script intentionally keeps a single shared runtime "hub" alive for the entire JMRI runtime session.
# You may open and close the window many times. Closing a window does NOT stop the hub. This is deliberate to
# prevent resource leaks/conflicts caused by creating multiple polling timers/listeners across repeated runs.
# Any future code review that expects all resources to be released on window close must NOT remove this without
# first confirming the requirement with James.
#
# PERFORMANCE NOTE:
# This UI must paint immediately. Therefore, all polling and any timetable file reading is done OFF the Swing EDT
# in a background daemon thread. Only UI updates are posted back to the EDT via SwingUtilities.invokeLater().
#
# JMRI 5.14, Jython (Python 2.7). ASCII-only.

import jmri
import os
import csv
import re
import sys

import javax.swing as swing
import java.awt as awt
import java.awt.event as event

from java.lang import Runnable, Thread, System
from javax.swing import SwingUtilities
from javax.swing import Timer

from java.util.concurrent.locks import ReentrantLock

import TASBeanLookup as TBL
import TASUtil as TU

import DisruptionRegister as DR
from DisruptionRegister import getDisruption

import TimingRegister as TR

from jmri.profile import ProfileManager


# ----------------------------
# UI sizing/appearance
# ----------------------------

# The teleprinter sheets are deliberately small. The window is sized so the page fills most of it.
FRAME_WIDTH = 650
FRAME_HEIGHT = 480

# Maximum paper size in pixels (regardless of window size)
PAPER_MAX_WIDTH = 520
PAPER_MAX_HEIGHT = 360

# Paper size as a fraction of window size (also capped by max values above)
PAPER_FRACTION = 0.80

# Faded ink appearance: blend towards paper and apply alpha.
INK_BLEND_TO_PAPER = 0.35  # 0.0 = raw ink, 1.0 = same as paper
INK_ALPHA = 190            # 255 = opaque, lower = more faded

# Printing animation. These control how quickly the newest page prints.
# Typical teleprinters were about 10 characters per second.
PRINT_TIMER_MS = 100       # tick interval in milliseconds
PRINT_CHARS_PER_TICK = 1   # characters revealed per tick

# Delay between the end of one page printing and the start of the next (milliseconds).
INTER_MESSAGE_DELAY_MS = 5000


# ----------------------------
# Runtime hub (singleton)
# ----------------------------

_HUB_MODULE_KEY = 'TASTeleprinterDisruptionHub'


def _GetOrCreateHub():
    hub = sys.modules.get(_HUB_MODULE_KEY)
    if hub is None:
        class _Hub(object):
            pass
        hub = _Hub()
        sys.modules[_HUB_MODULE_KEY] = hub

        hub.Windows = []
        hub.Messages = []
        hub.PendingMessages = []
        hub.PrintOwnerId = None
        hub.TrainState = {}
        hub.LastSeenDisruptions = {}

        # Timing scan optimization
        hub.LastTimingDay = None
        hub.LastTimingCountByTP = {}

        # Timetable cache
        hub.TimetablePath = None
        hub.TimetableMTime = None
        hub.TimetableByDay = {}

        # Concurrency
        hub.Lock = ReentrantLock()

        # Background poller
        hub.PollThread = None
        hub.PollStop = False

    return hub


# ----------------------------
# Memory helpers (prefix-agnostic)
# ----------------------------

_TimeMem = TBL.ProvideMemoryBySuffix('CURRENTTIME', '')
_DayMem = TBL.ProvideMemoryBySuffix('DAYOFWEEK', '')
_TimetableMem = TBL.ProvideMemoryBySuffix('CURRENTTIMETABLE', '')

# Per-display setting (seeded here so TASSetup can edit it after first run)
_SettingUse24hMem = TBL.ProvideMemoryBySuffix('TAS_USER_SETTING_USE_24_HOUR_TIME', 'true')


def _ReadMemStr(suffix, defaultValue=None):
    try:
        m = TBL.FindMemoryBySuffix(suffix)
        if m is None:
            return defaultValue
        v = m.getValue()
        if v is None:
            return defaultValue
        s = str(v).strip()
        return s if s != '' else defaultValue
    except:
        return defaultValue


def _ReadMemBool(suffix, defaultValue=False):
    v = _ReadMemStr(suffix, None)
    if v is None:
        return bool(defaultValue)
    t = str(v).strip().lower()
    if t in ('1', 'true', 'yes', 'y', 'on', 'enabled'):
        return True
    if t in ('0', 'false', 'no', 'n', 'off', 'disabled'):
        return False
    return bool(defaultValue)


# ----------------------------
# Time helpers
# ----------------------------

_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _DayIndex(dayName):
    try:
        return _DAYS.index(str(dayName))
    except:
        return 0


def _ParseTimeToMinutes(text):
    if text is None:
        return None
    s = str(text).strip()
    if s == '':
        return None

    up = s.upper()
    if (up.endswith('AM') or up.endswith('PM')) and len(s) >= 4 and s[-3] != ' ':
        s = s[:-2] + ' ' + s[-2:]

    m = re.match(r'^\s*(\d{1,2}):(\d{2})\s*$', s)
    if m:
        h = int(m.group(1)); mm = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h * 60 + mm
        return None

    m = re.match(r'^\s*(\d{1,2}):(\d{2})\s*([AP]\s*M)\s*$', s, re.IGNORECASE)
    if m:
        h = int(m.group(1)); mm = int(m.group(2))
        ap = m.group(3).replace(' ', '').upper()
        if h == 12:
            h = 0
        if ap.startswith('P'):
            h += 12
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h * 60 + mm
        return None

    return None


def _FormatMinutes(mins, use24h):
    if mins is None:
        return ''
    mins = int(mins)
    mins = max(0, min(24 * 60 - 1, mins))
    h = mins // 60
    m = mins % 60
    if use24h:
        return '%02d:%02d' % (h, m)
    ap = 'AM'
    hh = h
    if hh >= 12:
        ap = 'PM'
    hh = hh % 12
    if hh == 0:
        hh = 12
    return '%d:%02d %s' % (hh, m, ap)


def _ComputeWeekAbsMinute(dayName, timeMin):
    return _DayIndex(dayName) * 1440 + int(timeMin or 0)


def _AgeMinutes(nowAbsWeek, msgAbsWeek):
    diff = int(nowAbsWeek) - int(msgAbsWeek)
    if diff < 0:
        diff += 7 * 1440
    return diff


# ----------------------------
# Timetable helpers
# ----------------------------


def _ActiveProfilePath():
    try:
        prof = ProfileManager.getDefault().getActiveProfile()
        return prof.getPath().toString()
    except:
        return None


def _TimetablePathFromMemory():
    profilePath = _ActiveProfilePath()
    if not profilePath:
        return None
    name = _ReadMemStr('CURRENTTIMETABLE', '')
    if not name:
        return None
    return os.path.join(profilePath, 'timetable', name + '.csv')


def _LoadTimetableIndex(hub, dayName):
    # Called from background thread.
    path = _TimetablePathFromMemory()
    if not path or not os.path.exists(path):
        hub.TimetablePath = path
        hub.TimetableMTime = None
        hub.TimetableByDay = {}
        return

    try:
        mt = os.path.getmtime(path)
    except:
        mt = None

    if hub.TimetablePath != path or hub.TimetableMTime != mt:
        hub.TimetablePath = path
        hub.TimetableMTime = mt
        hub.TimetableByDay = {}

    dn = str(dayName or '').strip()
    if dn == '' or dn in hub.TimetableByDay:
        return

    byRn = {}
    try:
        with open(path, 'r') as f:
            reader = csv.DictReader(f, delimiter='\t')
            rows = list(reader)
    except:
        hub.TimetableByDay[dn] = byRn
        return

    for rowIndex, row in enumerate(rows, start=2):
        try:
            if not isinstance(row, dict):
                continue
            dayField = row.get(dn, '')
            if str(dayField).strip().upper() != 'TRUE':
                continue
            rn = (row.get('Reporting number', '') or '').strip()
            if rn == '':
                rn = TU.MakeDefaultReportingNumberFromRow(rowIndex)
            byRn[str(rn)] = row
        except:
            continue

    hub.TimetableByDay[dn] = byRn


def _RowForTrain(hub, dayName, rn):
    dn = str(dayName or '').strip()
    _LoadTimetableIndex(hub, dn)
    try:
        return hub.TimetableByDay.get(dn, {}).get(str(rn))
    except:
        return None


def _GetDestinationFromRow(row):
    if not row:
        return ''
    for k in ['Destination', 'Dest', 'To', 'Terminus', 'Terminating at']:
        try:
            v = row.get(k, None)
            if v is None:
                continue
            s = str(v).strip()
            if s != '':
                return s
        except:
            pass
    return ''


def _GetLayoutEtaScheduledMinutes(row):
    # ETA at layout location: Arr else Trigger. Fallback Dep for originating services.
    if not row:
        return None
    arr = (row.get('Arr', '') or '').strip()
    trig = (row.get('Trigger', '') or '').strip()
    dep = (row.get('Dep', '') or '').strip()

    mm = _ParseTimeToMinutes(arr) if arr else None
    if mm is not None:
        return mm
    mm = _ParseTimeToMinutes(trig) if trig else None
    if mm is not None:
        return mm
    mm = _ParseTimeToMinutes(dep) if dep else None
    if mm is not None:
        return mm

    # Fallback: earliest TP
    best = None
    for k, v in row.items():
        if not k or not v:
            continue
        ks = str(k).strip().lower()
        if ks.startswith('tparr ') or ks.startswith('tpdep '):
            t = _ParseTimeToMinutes(v)
            if t is None:
                continue
            if best is None or t < best:
                best = t
    return best


def _MakeTrainIdentifier(hub, dayName, rn, use24h):
    # Suppress TASxxx by identifying as time + destination.
    if not TU.IsDefaultReportingNumber(str(rn)):
        return str(rn)
    row = _RowForTrain(hub, dayName, rn)
    sched = _GetLayoutEtaScheduledMinutes(row)
    dest = _GetDestinationFromRow(row)
    timePart = _FormatMinutes(sched, use24h) if sched is not None else ''
    if timePart and dest:
        return '%s TO %s' % (timePart, dest)
    if timePart:
        return timePart
    if dest:
        return dest
    return 'SERVICE'


# ----------------------------
# Timing helpers
# ----------------------------


def _InferArrDepForTP(row, tpName, actualMin):
    if not row or not tpName:
        return 'DEP'
    keyArr = 'TPArr ' + str(tpName)
    keyDep = 'TPDep ' + str(tpName)
    a = None
    d = None
    try:
        va = (row.get(keyArr, '') or '').strip()
        vd = (row.get(keyDep, '') or '').strip()
        a = _ParseTimeToMinutes(va) if va else None
        d = _ParseTimeToMinutes(vd) if vd else None
    except:
        a = None
        d = None

    if a is None and d is None:
        return 'DEP'
    if a is not None and d is None:
        return 'ARR'
    if d is not None and a is None:
        return 'DEP'

    try:
        da = abs(int(actualMin) - int(a))
        dd = abs(int(actualMin) - int(d))
        return 'ARR' if da <= dd else 'DEP'
    except:
        return 'DEP'


def _GetScheduledMinuteForTP(row, tpName, arrdep):
    if not row or not tpName or not arrdep:
        return None
    key = ('TPArr ' if arrdep == 'ARR' else 'TPDep ') + str(tpName)
    try:
        v = (row.get(key, '') or '').strip()
        return _ParseTimeToMinutes(v) if v else None
    except:
        return None


def _StatusFromDelta(deltaMin):
    if deltaMin is None:
        return ('', 0)
    d = int(deltaMin)
    if d == 0:
        return ('ON TIME', 0)
    if d > 0:
        return ('LATE', d)
    return ('EARLY', -d)


def _IsCancelledValue(valInt):
    try:
        return int(valInt) > 1440
    except:
        return False


# ----------------------------
# Message construction
# ----------------------------


def _BuildMessageText(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    use24h = _ReadMemBool('TAS_USER_SETTING_USE_24_HOUR_TIME', True)

    header = 'TRAIN REPORT'
    if not TU.IsDefaultReportingNumber(str(rn)):
        header = 'TRAIN REPORT FOR ' + str(rn)

    ident = _MakeTrainIdentifier(hub, dayName, rn, use24h)

    if _IsCancelledValue(disruptionInt):
        statusLine = 'STATUS: CANCELLED'
    else:
        delta = None
        if tpName and tpTimeMin is not None:
            row = _RowForTrain(hub, dayName, rn)
            arrdep = _InferArrDepForTP(row, tpName, tpTimeMin)
            sched = _GetScheduledMinuteForTP(row, tpName, arrdep)
            if sched is not None:
                delta = int(tpTimeMin) - int(sched)
        if delta is None:
            try:
                delta = int(disruptionInt)
            except:
                delta = 0
        st, mag = _StatusFromDelta(delta)
        if st == 'ON TIME':
            statusLine = 'STATUS: ON TIME'
        else:
            statusLine = 'STATUS: %s %d MIN' % (st, int(mag))

    stamp = '%s %s' % (str(dayName), _FormatMinutes(nowMin, use24h))

    lines = []
    lines.append(header)
    lines.append(stamp)
    lines.append('')

    if TU.IsDefaultReportingNumber(str(rn)):
        lines.append('SERVICE: ' + ident)
    else:
        lines.append('TRAIN: ' + ident)

    lines.append(statusLine)

    if tpName and tpTimeMin is not None:
        row = _RowForTrain(hub, dayName, rn)
        arrdep = _InferArrDepForTP(row, tpName, tpTimeMin)
        lines.append('LAST REPORTED AT: %s %s %s' % (str(tpName).upper(), str(arrdep), _FormatMinutes(tpTimeMin, use24h)))

    return '\n'.join(lines) + '\n'


# ----------------------------
# Hub logic
# ----------------------------


def _EnsureTrainState(hub, rn):
    st = hub.TrainState.get(str(rn))
    if st is None:
        st = {
            'LastPrintedAbs': None,
            'FirstTpSeen': False,
            'LastTpOnTime': None,
            'LastPrintedWasCancel': False,
        }
        hub.TrainState[str(rn)] = st
    return st


def _RateLimitMinutes(etaMin, nowMin):
    if etaMin is None or nowMin is None:
        return 10
    dist = int(etaMin) - int(nowMin)
    if dist > 60:
        return 10
    if dist > 30:
        return 5
    return 2


def _NotifyWindows(hub):
    for w in list(hub.Windows):
        try:
            w.OnHubMessagesChanged()
        except:
            pass


def _AddMessage(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    txt = _BuildMessageText(hub, dayName, nowMin, rn, disruptionInt, tpName=tpName, tpTimeMin=tpTimeMin)
    rec = {
        'absWeek': _ComputeWeekAbsMinute(dayName, nowMin),
        'day': str(dayName),
        'timeMin': int(nowMin or 0),
        'rn': str(rn),
        'text': txt,
        'printedChars': 0,
        'done': False,
        'doneAtMs': None,
    }

    becameVisible = False
    hub.Lock.lock()
    try:
        if not hasattr(hub, 'PendingMessages'):
            hub.PendingMessages = []
        # Hold back new pages while the newest visible page is still printing.
        if hub.Messages and (not bool(hub.Messages[-1].get('done', False))):
            hub.PendingMessages.append(rec)
        else:
            hub.Messages.append(rec)
            becameVisible = True
    finally:
        hub.Lock.unlock()

    if becameVisible:
        SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))


def _CullOldMessages(hub, dayName, nowMin):
    nowAbs = _ComputeWeekAbsMinute(dayName, nowMin)
    hub.Lock.lock()
    try:
        kept = []
        for m in hub.Messages:
            try:
                age = _AgeMinutes(nowAbs, m.get('absWeek', nowAbs))
                if age < 1440:
                    kept.append(m)
            except:
                kept.append(m)
        hub.Messages = kept

        # Also cull any pending pages
        if hasattr(hub, 'PendingMessages'):
            keptP = []
            for m in hub.PendingMessages:
                try:
                    age = _AgeMinutes(nowAbs, m.get('absWeek', nowAbs))
                    if age < 1440:
                        keptP.append(m)
                except:
                    keptP.append(m)
            hub.PendingMessages = keptP
    finally:
        hub.Lock.unlock()


def _PollOnce(hub):
    # Runs on background thread.
    dayName = _DayMem.getValue() or ''
    timeStr = _TimeMem.getValue() or ''
    nowMin = _ParseTimeToMinutes(timeStr)
    if nowMin is None or str(dayName).strip() == '':
        return

    _LoadTimetableIndex(hub, str(dayName))
    _CullOldMessages(hub, str(dayName), nowMin)

    if hub.LastTimingDay != str(dayName):
        hub.LastTimingDay = str(dayName)
        hub.LastTimingCountByTP = {}

    # Disruption events
    try:
        keys = list(DR.register.keySet().toArray())
    except:
        keys = []

    for rn in keys:
        try:
            cur = getDisruption(rn)
            curInt = int(cur) if cur is not None else 0
        except:
            curInt = 0

        st = _EnsureTrainState(hub, rn)
        wasSeen = str(rn) in hub.LastSeenDisruptions
        lastVal = hub.LastSeenDisruptions.get(str(rn), None)

        # Cancellation immediate (single message)
        if _IsCancelledValue(curInt):
            if (not st.get('LastPrintedWasCancel', False)) or (lastVal is None) or (not _IsCancelledValue(lastVal)):
                _AddMessage(hub, str(dayName), nowMin, rn, curInt)
                st['LastPrintedWasCancel'] = True
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        # First registration
        if not wasSeen:
            _AddMessage(hub, str(dayName), nowMin, rn, curInt)
            st['LastPrintedAbs'] = _ComputeWeekAbsMinute(dayName, nowMin)
            st['LastPrintedWasCancel'] = False
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        # After first TP: ignore churn until TP events
        if st.get('FirstTpSeen', False):
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        # Pre-first-TP rate-limited updates
        if lastVal is not None and int(lastVal) == int(curInt):
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        row = _RowForTrain(hub, str(dayName), rn)
        etaSched = _GetLayoutEtaScheduledMinutes(row)
        etaEst = None
        try:
            etaEst = int(etaSched) + int(curInt) if etaSched is not None else None
        except:
            etaEst = None

        limit = _RateLimitMinutes(etaEst, nowMin)
        nowAbs = _ComputeWeekAbsMinute(dayName, nowMin)
        okByTime = True
        if st.get('LastPrintedAbs', None) is not None:
            age = _AgeMinutes(nowAbs, st.get('LastPrintedAbs'))
            okByTime = (age >= int(limit))

        if okByTime:
            _AddMessage(hub, str(dayName), nowMin, rn, curInt)
            st['LastPrintedAbs'] = nowAbs

        hub.LastSeenDisruptions[str(rn)] = curInt

    # Timing point events (incremental scan)
    try:
        tps = TR.listTimingPoints() or []
    except:
        tps = []

    for tp in tps:
        try:
            entries = TR.getTiming(tp) or []
        except:
            entries = []

        start = 0
        try:
            start = int(hub.LastTimingCountByTP.get(str(tp), 0))
        except:
            start = 0

        if start < 0:
            start = 0
        if start > len(entries):
            start = 0

        if start == len(entries):
            continue

        newEntries = entries[start:]
        hub.LastTimingCountByTP[str(tp)] = len(entries)

        for rec in newEntries:
            try:
                rn = str(rec[0])
                timeStr = str(rec[2])
                dStr = str(rec[3])
            except:
                continue

            if dStr != str(dayName):
                continue

            st = _EnsureTrainState(hub, rn)
            st['FirstTpSeen'] = True

            # If cancelled, do NOT emit a TP-based message
            try:
                cur = getDisruption(rn)
                curInt = int(cur) if cur is not None else 0
            except:
                curInt = 0
            if _IsCancelledValue(curInt):
                continue

            actualMin = _ParseTimeToMinutes(timeStr)
            if actualMin is None:
                continue

            row = _RowForTrain(hub, str(dayName), rn)
            arrdep = _InferArrDepForTP(row, tp, actualMin)
            schedMin = _GetScheduledMinuteForTP(row, tp, arrdep)
            delta = None
            if schedMin is not None:
                delta = int(actualMin) - int(schedMin)

            thisOnTime = (delta == 0) if delta is not None else False
            lastOnTime = st.get('LastTpOnTime', None)

            if lastOnTime is True and thisOnTime is True:
                st['LastTpOnTime'] = True
                continue

            _AddMessage(hub, str(dayName), nowMin, rn, curInt, tpName=str(tp), tpTimeMin=int(actualMin))
            st['LastTpOnTime'] = thisOnTime


# ----------------------------
# UI helpers
# ----------------------------


def _RgbStrToColor(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(',')]
        if len(parts) != 3:
            return defaultColor
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
        return awt.Color(r, g, b)
    except:
        return defaultColor


def _FadeInkColor(ink, paper, blendToPaper, alpha):
    try:
        b = max(0.0, min(1.0, float(blendToPaper)))
        r = int((1.0 - b) * ink.getRed() + b * paper.getRed())
        g = int((1.0 - b) * ink.getGreen() + b * paper.getGreen())
        bl = int((1.0 - b) * ink.getBlue() + b * paper.getBlue())
        a = max(0, min(255, int(alpha)))
        return awt.Color(r, g, bl, a)
    except:
        try:
            return awt.Color(60, 60, 60, max(0, min(255, int(alpha))))
        except:
            return ink


class PaperStackPanel(swing.JPanel):
    def __init__(self, hub, ownerFrame):
        swing.JPanel.__init__(self)
        self.Hub = hub
        # Claim print ownership if there is no current owner.
        try:
            self.Hub.Lock.lock()
            try:
                if not hasattr(self.Hub, 'PrintOwnerId'):
                    self.Hub.PrintOwnerId = None
                if self.Hub.PrintOwnerId is None:
                    self.Hub.PrintOwnerId = id(self)
            finally:
                self.Hub.Lock.unlock()
        except:
            pass
        self.Owner = ownerFrame
        self.setBackground(awt.Color(60, 60, 60))
        self.setFocusable(True)

        self.PaperColor = _RgbStrToColor(_ReadMemStr('TASPAPERCOLOUR', '249,246,238'), awt.Color(249, 246, 238))

        baseInk = _RgbStrToColor(_ReadMemStr('TASINKCOLOUR', '40,40,40'), awt.Color(40, 40, 40))
        self.InkColor = _FadeInkColor(baseInk, self.PaperColor, INK_BLEND_TO_PAPER, INK_ALPHA)

        self.Font = awt.Font('Monospaced', awt.Font.PLAIN, 16)

    def paintComponent(self, g):
        # NOTE: In Jython, javax.swing.JPanel.paintComponent is protected and is not exposed
        # as swing.JPanel.paintComponent on the class object. Do not call super here.

        try:
            g.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        w = self.getWidth()
        h = self.getHeight()

        g.setColor(self.getBackground())
        g.fillRect(0, 0, w, h)

        self.Hub.Lock.lock()
        try:
            msgs = list(self.Hub.Messages)
        finally:
            self.Hub.Lock.unlock()

        n = len(msgs)
        try:
            self.Owner.LastKnownMessageCount = int(n)
        except:
            pass

        pw = min(int(w * PAPER_FRACTION), int(PAPER_MAX_WIDTH))
        ph = min(int(h * PAPER_FRACTION), int(PAPER_MAX_HEIGHT))
        pw = max(260, pw)
        ph = max(200, ph)
        baseX = (w - pw) // 2
        baseY = (h - ph) // 2

        if n == 0:
            g.setColor(self.PaperColor)
            g.fillRoundRect(baseX, baseY, pw, ph, 8, 8)
            g.setColor(self.InkColor)
            g.setFont(self.Font)
            g.drawString('NO MESSAGES', baseX + 30, baseY + 60)
            return

        idx = self.Owner.PageIndex
        idx = max(0, min(n - 1, idx))
        self.Owner.PageIndex = idx

        behind = min(5, n - 1)
        for i in range(behind, 0, -1):
            off = i * 3
            g.setColor(awt.Color(0, 0, 0, 35))
            g.fillRoundRect(baseX + off + 3, baseY + off + 3, pw, ph, 8, 8)
            g.setColor(self.PaperColor)
            g.fillRoundRect(baseX + off, baseY + off, pw, ph, 8, 8)

        g.setColor(awt.Color(0, 0, 0, 55))
        g.fillRoundRect(baseX + 5, baseY + 5, pw, ph, 8, 8)
        g.setColor(self.PaperColor)
        g.fillRoundRect(baseX, baseY, pw, ph, 8, 8)

        cx = baseX + pw - 26
        cy = baseY
        g.setColor(awt.Color(220, 215, 205))
        poly = awt.Polygon()
        poly.addPoint(cx, cy)
        poly.addPoint(cx + 26, cy)
        poly.addPoint(cx + 26, cy + 26)
        g.fillPolygon(poly)
        g.setColor(awt.Color(180, 175, 165))
        g.drawPolygon(poly)

        g.setColor(awt.Color(240, 240, 240))
        g.setFont(awt.Font('SansSerif', awt.Font.PLAIN, 12))
        g.drawString('%d / %d' % (idx + 1, n), baseX + 10, baseY - 8)

        msg = msgs[idx]
        text = msg.get('text', '')
        printed = msg.get('printedChars', 0)
        done = msg.get('done', False)

        if idx == n - 1 and not done:
            shown = text[:max(0, int(printed))]
        else:
            shown = text

        g.setColor(self.InkColor)
        g.setFont(self.Font)

        x0 = baseX + 26
        y0 = baseY + 46
        lineH = 20
        maxW = pw - 52

        fm = g.getFontMetrics(self.Font)
        cw = fm.charWidth('M')
        if cw <= 0:
            cw = 9
        maxChars = max(10, int(maxW // cw))

        y = y0
        for lineIndex, rawLine in enumerate(shown.split('\n')):
            line = rawLine
            if lineIndex in (0, 1):
                if len(line) <= maxChars:
                    try:
                        tw = fm.stringWidth(line)
                        x = baseX + (pw - tw) // 2
                    except:
                        x = x0
                    g.drawString(line, x, y)
                    y += lineH
                    continue
            while len(line) > maxChars:
                part = line[:maxChars]
                g.drawString(part, x0, y)
                y += lineH
                line = line[maxChars:]
            g.drawString(line, x0, y)
            y += lineH
            if y > baseY + ph - 30:
                break


class TeleprinterFrame(swing.JFrame):
    def __init__(self, hub):
        swing.JFrame.__init__(self, 'Teleprinter session')
        self.Hub = hub
        # Claim print ownership if there is no current owner.
        try:
            self.Hub.Lock.lock()
            try:
                if not hasattr(self.Hub, 'PrintOwnerId'):
                    self.Hub.PrintOwnerId = None
                if self.Hub.PrintOwnerId is None:
                    self.Hub.PrintOwnerId = id(self)
            finally:
                self.Hub.Lock.unlock()
        except:
            pass
        self.PageIndex = 0
        self.LastKnownMessageCount = 0
        self.IsClosed = False

        self.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        self.setSize(int(FRAME_WIDTH), int(FRAME_HEIGHT))
        try:
            self.setMinimumSize(awt.Dimension(int(FRAME_WIDTH), int(FRAME_HEIGHT)))
        except:
            pass

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self, 32)
        except:
            pass

        self.StackPanel = PaperStackPanel(hub, self)
        self.getContentPane().setLayout(awt.BorderLayout())
        self.getContentPane().add(self.StackPanel, awt.BorderLayout.CENTER)

        footer = swing.JPanel()
        footer.setLayout(awt.FlowLayout(awt.FlowLayout.CENTER, 12, 6))
        footer.setBackground(awt.Color(60, 60, 60))

        self.LblHelp = swing.JLabel('Arrows/Scroll: navigate   |   Click left/right: navigate   |   Clear: clear stack')
        self.LblHelp.setForeground(awt.Color(230, 230, 230))
        footer.add(self.LblHelp)

        self.BtnClear = swing.JButton('Clear')
        footer.add(self.BtnClear)

        self.getContentPane().add(footer, awt.BorderLayout.SOUTH)

        self.PrintTimer = Timer(int(PRINT_TIMER_MS), self._OnPrintTick)
        self.PrintTimer.setRepeats(True)
        self.PrintTimer.start()

        self.addKeyListener(self._KeyListener())
        self.StackPanel.addMouseWheelListener(self._WheelListener())
        self.StackPanel.addMouseListener(self._ClickListener())
        self.BtnClear.addActionListener(lambda e: self._DoClear())

        self.addWindowListener(self._WindowCloser())

        self.setVisible(True)
        self.StackPanel.requestFocusInWindow()
        self.StackPanel.repaint()

    def _DoClear(self):
        try:
            choice = swing.JOptionPane.showConfirmDialog(
                self,
                'Clear the teleprinter stack for this JMRI runtime session?\nThis does not affect the disruption register.',
                'Confirm clear',
                swing.JOptionPane.OK_CANCEL_OPTION,
                swing.JOptionPane.WARNING_MESSAGE
            )
            if choice != swing.JOptionPane.OK_OPTION:
                return
        except:
            return

        self.Hub.Lock.lock()
        try:
            self.Hub.Messages = []
            if hasattr(self.Hub, 'PendingMessages'):
                self.Hub.PendingMessages = []
        finally:
            self.Hub.Lock.unlock()

        self.PageIndex = 0
        self.LastKnownMessageCount = 0
        self.OnHubMessagesChanged()

    def OnHubMessagesChanged(self):
        if self.IsClosed:
            return
        try:
            self.Hub.Lock.lock()
            try:
                n = len(self.Hub.Messages)
            finally:
                self.Hub.Lock.unlock()
            try:
                self.LastKnownMessageCount = int(n)
            except:
                pass
            self.PageIndex = max(0, n - 1)
        except:
            pass
        self.StackPanel.repaint()
    def _OnPrintTick(self, e=None):

        if self.IsClosed:
            return

        promoted = False

        self.Hub.Lock.lock()
        try:
            # If there is no owner, claim ownership.
            if not hasattr(self.Hub, 'PrintOwnerId'):
                self.Hub.PrintOwnerId = None
            if self.Hub.PrintOwnerId is None:
                self.Hub.PrintOwnerId = id(self)
            # Only the owner advances printing and releases pending pages.
            if self.Hub.PrintOwnerId != id(self):
                return

            if not hasattr(self.Hub, 'PendingMessages'):
                self.Hub.PendingMessages = []

            msgs = self.Hub.Messages
            if not msgs:
                return

            msg = msgs[-1]

            nowMs = 0
            try:
                nowMs = long(System.currentTimeMillis())
            except:
                try:
                    nowMs = int(System.currentTimeMillis())
                except:
                    nowMs = 0

            # If this page is already done, enforce the inter-message delay before promoting the next pending page.
            if msg.get('done', False):
                doneAt = msg.get('doneAtMs', None)
                if doneAt is None:
                    msg['doneAtMs'] = nowMs
                    return
                try:
                    if int(nowMs) - int(doneAt) < int(INTER_MESSAGE_DELAY_MS):
                        return
                except:
                    return
                if self.Hub.PendingMessages:
                    nxt = self.Hub.PendingMessages.pop(0)
                    nxt['printedChars'] = 0
                    nxt['done'] = False
                    nxt['doneAtMs'] = None
                    msgs.append(nxt)
                    promoted = True
                return

            full = msg.get('text', '')
            cur = int(msg.get('printedChars', 0))
            cur += int(PRINT_CHARS_PER_TICK)
            if cur >= len(full):
                cur = len(full)
                msg['done'] = True
                msg['doneAtMs'] = nowMs
            msg['printedChars'] = cur

            # Do NOT promote immediately on the same tick; wait for the inter-message delay.
        except:
            try:
                if msgs:
                    msgs[-1]['done'] = True
            except:
                pass
        finally:
            self.Hub.Lock.unlock()

        if promoted:
            self.OnHubMessagesChanged()
        else:
            self.StackPanel.repaint()


    class _KeyListener(event.KeyAdapter):
        def keyPressed(self, e):
            try:
                frame = e.getComponent()
                code = e.getKeyCode()
            except:
                return
            if code in (event.KeyEvent.VK_RIGHT, event.KeyEvent.VK_DOWN):
                try:
                    frame.Hub.Lock.lock()
                    try:
                        n = len(frame.Hub.Messages)
                    finally:
                        frame.Hub.Lock.unlock()
                    if frame.PageIndex < n - 1:
                        frame.PageIndex += 1
                        frame.StackPanel.repaint()
                except:
                    pass
            elif code in (event.KeyEvent.VK_LEFT, event.KeyEvent.VK_UP):
                try:
                    if frame.PageIndex > 0:
                        frame.PageIndex -= 1
                        frame.StackPanel.repaint()
                except:
                    pass

    class _WheelListener(event.MouseWheelListener):
        def mouseWheelMoved(self, e):
            try:
                frame = e.getComponent().getTopLevelAncestor()
                rot = e.getWheelRotation()
            except:
                return
            if rot > 0:
                try:
                    if frame.PageIndex > 0:
                        frame.PageIndex -= 1
                        frame.StackPanel.repaint()
                except:
                    pass
            elif rot < 0:
                try:
                    frame.Hub.Lock.lock()
                    try:
                        n = len(frame.Hub.Messages)
                    finally:
                        frame.Hub.Lock.unlock()
                    if frame.PageIndex < n - 1:
                        frame.PageIndex += 1
                        frame.StackPanel.repaint()
                except:
                    pass

    class _ClickListener(event.MouseAdapter):
        def mouseClicked(self, e):
            try:
                frame = e.getComponent().getTopLevelAncestor()
                x = e.getX()
                w = e.getComponent().getWidth()
            except:
                return
            if x < w * 0.25:
                try:
                    if frame.PageIndex > 0:
                        frame.PageIndex -= 1
                        frame.StackPanel.repaint()
                except:
                    pass
            elif x > w * 0.75:
                try:
                    frame.Hub.Lock.lock()
                    try:
                        n = len(frame.Hub.Messages)
                    finally:
                        frame.Hub.Lock.unlock()
                    if frame.PageIndex < n - 1:
                        frame.PageIndex += 1
                        frame.StackPanel.repaint()
                except:
                    pass

    class _WindowCloser(event.WindowAdapter):
        def windowClosing(self, e):
            try:
                e.getWindow()._Cleanup()
            except:
                pass
        def windowClosed(self, e):
            try:
                e.getWindow()._Cleanup()
            except:
                pass

    def _Cleanup(self):
        if self.IsClosed:
            return
        self.IsClosed = True
        # Release print ownership if this window owned it.
        try:
            self.Hub.Lock.lock()
            try:
                if hasattr(self.Hub, 'PrintOwnerId') and self.Hub.PrintOwnerId == id(self):
                    self.Hub.PrintOwnerId = None
            finally:
                self.Hub.Lock.unlock()
        except:
            pass
        try:
            if self.PrintTimer is not None:
                self.PrintTimer.stop()
        except:
            pass
        try:
            if self in self.Hub.Windows:
                self.Hub.Windows.remove(self)
        except:
            pass


class RunnableAdapter(Runnable):
    def __init__(self, fn):
        self.Fn = fn
    def run(self):
        try:
            self.Fn()
        except:
            pass


# ----------------------------
# Entry
# ----------------------------


def _StartHubPollingIfNeeded(hub):
    if hub.PollThread is not None:
        try:
            if hub.PollThread.isAlive():
                return
        except:
            pass

    hub.PollStop = False

    class _Poller(Runnable):
        def run(self):
            while not hub.PollStop:
                try:
                    _PollOnce(hub)
                except Exception as ex:
                    try:
                        print('[Teleprinter] Poll error: ' + str(ex))
                    except:
                        pass
                try:
                    Thread.sleep(250)
                except:
                    pass

    try:
        t = Thread(_Poller())
        t.setDaemon(True)
        t.setName('TAS-Teleprinter-Poller')
        hub.PollThread = t
        t.start()
    except:
        hub.PollThread = None


def _OpenWindow():
    hub = _GetOrCreateHub()
    _StartHubPollingIfNeeded(hub)

    win = TeleprinterFrame(hub)
    try:
        hub.Windows.append(win)
    except:
        pass


if SwingUtilities.isEventDispatchThread():
    _OpenWindow()
else:
    SwingUtilities.invokeLater(RunnableAdapter(_OpenWindow))
