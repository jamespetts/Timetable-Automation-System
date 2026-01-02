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
# Teleprinter-style disruption output (printer + stack) for signallers.
#
# <<SIG-DISP-NAME: Teleprinter disruption messages>>
# <<DESCRIPTION: Simulates a 1960s/1970s teleprinter with a live printer on the left and a removable paper stack on the right.>>
#
# <<SETTING DESCRIPTION BOOLEAN: Use 24-hour time>>
#
# IMPORTANT DESIGN NOTE (DO NOT "CLEAN UP" WITHOUT ASKING JAMES):
# This script intentionally keeps a single shared runtime "hub" alive for the entire JMRI runtime session.
# You may open and close the window many times. Closing a window does NOT stop the hub.
#
# PERFORMANCE NOTE:
# All polling and timetable file reading is done OFF the Swing EDT in a background daemon thread.
# Swing painting and event handling must never block; EDT code uses tryLock() only.
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

FRAME_WIDTH = 980
FRAME_HEIGHT = 520

# Left printer viewport and paper
PRINTER_PAPER_WIDTH = 360
PRINTER_PAPER_HEIGHT = 430

# Right stack paper (narrower)
STACK_PAPER_MAX_WIDTH = 300
STACK_PAPER_MAX_HEIGHT = 360
STACK_PAPER_FRACTION = 0.82

# Faded ink appearance: blend towards paper and apply alpha.
INK_BLEND_TO_PAPER = 0.35  # 0.0 = raw ink, 1.0 = same as paper
INK_ALPHA = 190            # 255 = opaque, lower = more faded

# Printing animation.
PRINT_TIMER_MS = 35
PRINT_CHARS_PER_TICK = 1

# Paper movement animation.
SCROLL_PIXELS_PER_TICK = 2
LINE_HEIGHT_PX = 20

# After printing the message body, feed these blank lines to eject the page.
EJECT_BLANK_LINES = 10


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

        # Stack pages (fully printed, removable).
        hub.StackPages = []

        # Current printer job/page, or None.
        hub.Printer = None

        # Pending pages waiting to print.
        hub.PendingPages = []

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

        # Only one window drives printing/promotions.
        hub.PrintOwnerId = None

    return hub


# ----------------------------
# Memory helpers (prefix-agnostic)
# ----------------------------

_TimeMem = TBL.ProvideMemoryBySuffix('CURRENTTIME', '')
_DayMem = TBL.ProvideMemoryBySuffix('DAYOFWEEK', '')
_TimetableMem = TBL.ProvideMemoryBySuffix('CURRENTTIMETABLE', '')

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
# Hub logic and queueing
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
            w.OnHubChanged()
        except:
            try:
                w.repaint()
            except:
                pass


def _NewPrinterState(pageRec):
    # pageRec contains full text.
    return {
        'page': pageRec,
        'pos': 0,
        'lines': [],
        'currentLine': '',
        'scrollAnim': 0,
        'ejectRemaining': 0,
        'done': False,
        'ejected': False,
    }


def _AutoMovePrinterToStackLocked(hub):
    # Caller must hold hub.Lock.
    if hub.Printer is None:
        return False
    pr = hub.Printer
    try:
        if not pr.get('done', False):
            return False
        # Only auto-move once fully ejected.
        if not pr.get('ejected', False):
            return False
    except:
        return False

    try:
        page = pr.get('page', None)
        if page is not None:
            hub.StackPages.append(page)
    except:
        pass

    hub.Printer = None
    return True


def _StartNextPendingIfIdleLocked(hub):
    # Caller must hold hub.Lock.
    if hub.Printer is not None:
        return False
    if not hub.PendingPages:
        return False
    nxt = hub.PendingPages.pop(0)
    hub.Printer = _NewPrinterState(nxt)
    return True


def _AddIncomingPage(hub, pageRec):
    # Returns True if the printer state or stack changed.
    changed = False

    hub.Lock.lock()
    try:
        # If printer is holding a finished page and a new page arrives, auto-move finished page to stack.
        if hub.Printer is not None:
            changed = _AutoMovePrinterToStackLocked(hub) or changed

        if hub.Printer is None:
            hub.Printer = _NewPrinterState(pageRec)
            changed = True
        else:
            hub.PendingPages.append(pageRec)
            changed = True
    finally:
        hub.Lock.unlock()

    if changed:
        SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))

    return changed


def _AddMessage(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    txt = _BuildMessageText(hub, dayName, nowMin, rn, disruptionInt, tpName=tpName, tpTimeMin=tpTimeMin)
    rec = {
        'absWeek': _ComputeWeekAbsMinute(dayName, nowMin),
        'day': str(dayName),
        'timeMin': int(nowMin or 0),
        'rn': str(rn),
        'text': txt,
    }
    _AddIncomingPage(hub, rec)


def _CullOldPages(hub, dayName, nowMin):
    nowAbs = _ComputeWeekAbsMinute(dayName, nowMin)

    hub.Lock.lock()
    try:
        # Stack
        kept = []
        for m in hub.StackPages:
            try:
                age = _AgeMinutes(nowAbs, m.get('absWeek', nowAbs))
                if age < 1440:
                    kept.append(m)
            except:
                kept.append(m)
        hub.StackPages = kept

        # Pending
        keptP = []
        for m in hub.PendingPages:
            try:
                age = _AgeMinutes(nowAbs, m.get('absWeek', nowAbs))
                if age < 1440:
                    keptP.append(m)
            except:
                keptP.append(m)
        hub.PendingPages = keptP

        # Printer page: if older than 1 day, drop it.
        if hub.Printer is not None:
            try:
                page = hub.Printer.get('page', None)
                if page is not None:
                    age = _AgeMinutes(nowAbs, page.get('absWeek', nowAbs))
                    if age >= 1440:
                        hub.Printer = None
            except:
                pass
    finally:
        hub.Lock.unlock()


def _PollOnce(hub):
    dayName = _DayMem.getValue() or ''
    timeStr = _TimeMem.getValue() or ''
    nowMin = _ParseTimeToMinutes(timeStr)
    if nowMin is None or str(dayName).strip() == '':
        return

    _LoadTimetableIndex(hub, str(dayName))
    _CullOldPages(hub, str(dayName), nowMin)

    if hub.LastTimingDay != str(dayName):
        hub.LastTimingDay = str(dayName)
        hub.LastTimingCountByTP = {}

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

        if _IsCancelledValue(curInt):
            if (not st.get('LastPrintedWasCancel', False)) or (lastVal is None) or (not _IsCancelledValue(lastVal)):
                _AddMessage(hub, str(dayName), nowMin, rn, curInt)
                st['LastPrintedWasCancel'] = True
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        if not wasSeen:
            _AddMessage(hub, str(dayName), nowMin, rn, curInt)
            st['LastPrintedAbs'] = _ComputeWeekAbsMinute(dayName, nowMin)
            st['LastPrintedWasCancel'] = False
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        if st.get('FirstTpSeen', False):
            hub.LastSeenDisruptions[str(rn)] = curInt
            continue

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

    # Timing point events
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
        return ink


def _DrawWoodSurface(g, x, y, w, h):
    # Simple table surface.
    base = awt.Color(90, 60, 35)
    g.setColor(base)
    g.fillRect(x, y, w, h)
    # A few plank lines.
    g.setColor(awt.Color(70, 45, 25, 120))
    step = 22
    yy = y
    while yy < y + h:
        g.drawLine(x, yy, x + w, yy)
        yy += step



def _GetInTrayMetrics(x, y, w, h):
    # Keep these in one place so the stack panel can place paper inside the tray.
    pad = 14
    lipH = 18
    ix = x + pad
    iy = y + pad
    iw = max(10, w - pad * 2)
    ih = max(10, h - pad * 2)
    return {
        'pad': pad,
        'lipH': lipH,
        'ix': ix,
        'iy': iy,
        'iw': iw,
        'ih': ih,
    }

def _DrawInTrayBack(g, x, y, w, h):
    # Draw the back/sides/bottom well of a simple grey office in-tray.
    # The front lip is drawn separately so pages can appear inside the tray.
    try:
        g.setColor(awt.Color(35, 35, 35))
        g.fillRoundRect(x + 3, y + 3, w, h, 18, 18)
    except:
        pass

    # Outer tray
    g.setColor(awt.Color(145, 145, 145))
    g.fillRoundRect(x, y, w, h, 18, 18)
    g.setColor(awt.Color(95, 95, 95))
    g.drawRoundRect(x, y, w, h, 18, 18)

    # Inner well
    m = _GetInTrayMetrics(x, y, w, h)
    ix = m.get('ix'); iy = m.get('iy'); iw = m.get('iw'); ih = m.get('ih')
    g.setColor(awt.Color(120, 120, 120))
    g.fillRoundRect(ix, iy, iw, ih, 14, 14)
    g.setColor(awt.Color(80, 80, 80))
    g.drawRoundRect(ix, iy, iw, ih, 14, 14)

def _DrawInTrayFrontLip(g, x, y, w, h):
    # Draw just the front lip so it can overlay paper.
    m = _GetInTrayMetrics(x, y, w, h)
    lipH = int(m.get('lipH', 18))
    ly = y + h - lipH

    # A subtle shadow just above the lip.
    try:
        g.setColor(awt.Color(0, 0, 0, 25))
        g.fillRect(x + 8, ly - 3, w - 16, 3)
    except:
        pass

    g.setColor(awt.Color(160, 160, 160))
    g.fillRect(x + 6, ly, w - 12, lipH - 2)
    g.setColor(awt.Color(105, 105, 105))
    g.drawRect(x + 6, ly, w - 12, lipH - 2)

def _DrawInTray(g, x, y, w, h):
    # Draw a simple grey office in-tray.
    # x,y,w,h define the overall tray outer bounds.
    _DrawInTrayBack(g, x, y, w, h)
    _DrawInTrayFrontLip(g, x, y, w, h)


# ----------------------------
# Printer panel
# ----------------------------


class PrinterPanel(swing.JPanel):
    def __init__(self, hub, ownerFrame):
        swing.JPanel.__init__(self)
        self.Hub = hub
        self.Owner = ownerFrame
        self.setBackground(awt.Color(45, 45, 45))
        self.setFocusable(True)

        self.PaperColor = _RgbStrToColor(_ReadMemStr('TASPAPERCOLOUR', '249,246,238'), awt.Color(249, 246, 238))
        baseInk = _RgbStrToColor(_ReadMemStr('TASINKCOLOUR', '40,40,40'), awt.Color(40, 40, 40))
        self.InkColor = _FadeInkColor(baseInk, self.PaperColor, INK_BLEND_TO_PAPER, INK_ALPHA)

        self.Font = awt.Font('Monospaced', awt.Font.PLAIN, 16)

        # Cache for painting
        self.CachedPrinter = None

    def paintComponent(self, g):
        try:
            g.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        w = self.getWidth()
        h = self.getHeight()
        g.setColor(self.getBackground())
        g.fillRect(0, 0, w, h)

        # Snapshot printer state without blocking EDT.
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False

        if got:
            try:
                pr = self.Hub.Printer
                # Copy minimal fields
                if pr is None:
                    self.CachedPrinter = None
                else:
                    self.CachedPrinter = {
                        'page': pr.get('page', None),
                        'pos': int(pr.get('pos', 0)),
                        'lines': list(pr.get('lines', [])),
                        'currentLine': str(pr.get('currentLine', '')),
                        'scrollAnim': int(pr.get('scrollAnim', 0)),
                        'done': bool(pr.get('done', False)),
                        'ejected': bool(pr.get('ejected', False)),
                    }
            finally:
                try:
                    self.Hub.Lock.unlock()
                except:
                    pass

        pr = self.CachedPrinter

        # Printer viewport
        vpw = min(PRINTER_PAPER_WIDTH + 40, w - 20)
        vph = min(PRINTER_PAPER_HEIGHT + 40, h - 20)
        vx = (w - vpw) // 2
        vy = (h - vph) // 2

        # Surround
        g.setColor(awt.Color(30, 30, 30))
        g.fillRoundRect(vx, vy, vpw, vph, 12, 12)
        g.setColor(awt.Color(15, 15, 15))
        g.drawRoundRect(vx, vy, vpw, vph, 12, 12)

        px = vx + 20
        py = vy + 20
        pw = vpw - 40
        ph = vph - 40

        g.setColor(self.PaperColor)
        g.fillRect(px, py, pw, ph)
        g.setColor(awt.Color(0, 0, 0, 40))
        g.drawRect(px, py, pw, ph)
        if pr is None:
            # No paper in the printer: leave the paper blank and show status in the footer.
            return

        # Draw printed content with page movement.
        g.setColor(self.InkColor)
        g.setFont(self.Font)
        # Determine how many lines fit.
        topMargin = 30
        bottomMargin = 24
        maxLines = max(1, int((ph - topMargin - bottomMargin) // LINE_HEIGHT_PX))

        lines = pr.get('lines', [])
        curLine = pr.get('currentLine', '')

        # Build display list: all completed lines + current line
        displayLines = list(lines)
        displayLines.append(curLine)

        # Show only last maxLines. Older lines have already fed out of view.
        if len(displayLines) > maxLines:
            displayLines = displayLines[-maxLines:]

        # scrollAnim is pixels remaining to feed to the next line.
        remain = int(pr.get('scrollAnim', 0))
        movedThisLine = 0
        try:
            if remain > 0:
                movedThisLine = int(LINE_HEIGHT_PX) - int(remain)
                if movedThisLine < 0:
                    movedThisLine = 0
                if movedThisLine > int(LINE_HEIGHT_PX):
                    movedThisLine = int(LINE_HEIGHT_PX)
        except:
            movedThisLine = 0

        # The print head is fixed near the bottom of the viewport; the paper feeds upward.
        baseLineY = py + ph - bottomMargin - movedThisLine

        # Draw from oldest to newest within displayLines.
        y = int(baseLineY) - int((len(displayLines) - 1) * LINE_HEIGHT_PX)
        for ln in displayLines:
            try:
                g.drawString(str(ln), px + 12, int(y))
            except:
                pass
            y += int(LINE_HEIGHT_PX)


# ----------------------------
# Stack panel
# ----------------------------


class StackPanel(swing.JPanel):
    def __init__(self, hub, ownerFrame):
        swing.JPanel.__init__(self)
        self.Hub = hub
        self.Owner = ownerFrame
        self.setBackground(awt.Color(60, 60, 60))
        self.setFocusable(True)

        self.PaperColor = _RgbStrToColor(_ReadMemStr('TASPAPERCOLOUR', '249,246,238'), awt.Color(249, 246, 238))
        baseInk = _RgbStrToColor(_ReadMemStr('TASINKCOLOUR', '40,40,40'), awt.Color(40, 40, 40))
        self.InkColor = _FadeInkColor(baseInk, self.PaperColor, INK_BLEND_TO_PAPER, INK_ALPHA)

        self.Font = awt.Font('Monospaced', awt.Font.PLAIN, 14)

        self.CachedStack = []

    def paintComponent(self, g):
        try:
            g.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        w = self.getWidth()
        h = self.getHeight()

        # Table surface if empty.
        g.setColor(self.getBackground())
        g.fillRect(0, 0, w, h)

        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False

        if got:
            try:
                self.CachedStack = list(self.Hub.StackPages)
            finally:
                try:
                    self.Hub.Lock.unlock()
                except:
                    pass

        pages = self.CachedStack
        n = len(pages)

        # Keep frame's cached count for navigation.
        try:
            self.Owner.LastKnownStackCount = int(n)
        except:
            pass


        # Always show the in-tray surround; pages sit inside it.
        margin = 18
        tx = margin
        ty = margin
        tw = max(60, int(w) - margin * 2)
        th = max(60, int(h) - margin * 2)

        # Draw the tray back first.
        _DrawInTrayBack(g, int(tx), int(ty), int(tw), int(th))

        # Determine the usable inner area for paper (keep clear of the front lip).
        m = _GetInTrayMetrics(int(tx), int(ty), int(tw), int(th))
        pad = int(m.get('pad', 14))
        lipH = int(m.get('lipH', 18))
        ix = int(m.get('ix', int(tx) + pad))
        iy = int(m.get('iy', int(ty) + pad))
        iw = int(m.get('iw', int(tw) - pad * 2))
        ih = int(m.get('ih', int(th) - pad * 2))

        # Leave a little space at the bottom so the front lip can overlay the paper.
        innerBottomClear = max(6, lipH - 6)
        availX = ix + 6
        availY = iy + 6
        availW = max(60, iw - 12)
        availH = max(60, ih - 12 - innerBottomClear)

        if n == 0:
            # Empty stack: just draw the front lip and return.
            _DrawInTrayFrontLip(g, int(tx), int(ty), int(tw), int(th))
            return

        # Compute paper size constrained to the inner tray well.
        pw = min(int(availW), int(STACK_PAPER_MAX_WIDTH))
        ph = min(int(availH), int(STACK_PAPER_MAX_HEIGHT))
        pw = max(200, pw)
        ph = max(200, ph)
        pw = min(pw, int(availW))
        ph = min(ph, int(availH))

        baseX = int(availX + (availW - pw) // 2)
        baseY = int(availY + (availH - ph) // 2)

        idx = self.Owner.StackIndex
        idx = max(0, min(n - 1, idx))
        self.Owner.StackIndex = idx

        behind = min(5, n - 1)
        for i in range(behind, 0, -1):
            off = i * 3
            g.setColor(awt.Color(0, 0, 0, 30))
            g.fillRoundRect(baseX + off + 3, baseY + off + 3, pw, ph, 8, 8)
            g.setColor(self.PaperColor)
            g.fillRoundRect(baseX + off, baseY + off, pw, ph, 8, 8)

        g.setColor(awt.Color(0, 0, 0, 45))
        g.fillRoundRect(baseX + 4, baseY + 4, pw, ph, 8, 8)
        g.setColor(self.PaperColor)
        g.fillRoundRect(baseX, baseY, pw, ph, 8, 8)

        g.setColor(awt.Color(240, 240, 240))
        g.setFont(awt.Font('SansSerif', awt.Font.PLAIN, 12))
        g.drawString('%d / %d' % (idx + 1, n), baseX + 10, baseY - 8)

        page = pages[idx]
        txt = page.get('text', '') if isinstance(page, dict) else str(page)
        g.setColor(self.InkColor)
        g.setFont(self.Font)
        x0 = baseX + 14
        y0 = baseY + 30
        lineH = 18
        maxW = pw - 28
        fm = g.getFontMetrics(self.Font)
        cw = fm.charWidth('M')
        if cw <= 0:
            cw = 8
        maxChars = max(10, int(maxW // cw))
        y = y0
        for rawLine in str(txt).split('\n'):
            line = rawLine
            while len(line) > maxChars:
                part = line[:maxChars]
                g.drawString(part, x0, y)
                y += lineH
                line = line[maxChars:]
            g.drawString(line, x0, y)
            y += lineH
            if y > baseY + ph - 20:
                break

        # Finally draw the tray front lip over the bottom of the page.
        _DrawInTrayFrontLip(g, int(tx), int(ty), int(tw), int(th))



# ----------------------------
# Main frame
# ----------------------------


class TeleprinterFrame(swing.JFrame):
    def __init__(self, hub):
        swing.JFrame.__init__(self, 'Teleprinter session')
        self.Hub = hub
        self.IsClosed = False

        self.StackIndex = 0
        self.LastKnownStackCount = 0

        # Claim print ownership if none.
        try:
            hub.Lock.lock()
            try:
                if hub.PrintOwnerId is None:
                    hub.PrintOwnerId = id(self)
            finally:
                hub.Lock.unlock()
        except:
            pass

        self.setDefaultCloseOperation(swing.JFrame.DISPOSE_ON_CLOSE)
        self.setSize(int(FRAME_WIDTH), int(FRAME_HEIGHT))

        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self, 32)
        except:
            pass

        # Left container: printer
        self.PrinterPanel = PrinterPanel(hub, self)
        left = swing.JPanel()
        left.setLayout(awt.BorderLayout())
        left.add(self.PrinterPanel, awt.BorderLayout.CENTER)

        # Right container: stack
        self.StackPanel = StackPanel(hub, self)
        right = swing.JPanel()
        right.setLayout(awt.BorderLayout())
        right.add(self.StackPanel, awt.BorderLayout.CENTER)

        split = swing.JSplitPane(swing.JSplitPane.HORIZONTAL_SPLIT, left, right)
        split.setResizeWeight(0.50)
        try:
            split.setDividerLocation(500)
        except:
            pass

        self.getContentPane().setLayout(awt.BorderLayout())
        self.getContentPane().add(split, awt.BorderLayout.CENTER)

        footer = swing.JPanel()
        footer.setLayout(awt.FlowLayout(awt.FlowLayout.CENTER, 10, 6))
        footer.setBackground(awt.Color(55, 55, 55))

        self.BtnTearOff = swing.JButton('Tear off to stack')
        try:
            self.BtnTearOff.setEnabled(False)
        except:
            pass
        footer.add(self.BtnTearOff)

        self.BtnClearStack = swing.JButton('Clear stack')
        footer.add(self.BtnClearStack)

        self.LblStatus = swing.JLabel('')
        self.LblStatus.setForeground(awt.Color(230, 230, 230))
        footer.add(self.LblStatus)

        self.getContentPane().add(footer, awt.BorderLayout.SOUTH)

        self.BtnTearOff.addActionListener(lambda e: self._TearOff())
        self.BtnClearStack.addActionListener(lambda e: self._ClearStack())

        # Stack navigation listeners (no hub lock usage)
        self.addKeyListener(self._KeyListener())
        self.StackPanel.addMouseWheelListener(self._WheelListener())
        self.StackPanel.addMouseListener(self._ClickListener())

        self.addWindowListener(self._WindowCloser())

        self.PrintTimer = Timer(int(PRINT_TIMER_MS), self._OnTick)
        self.PrintTimer.setRepeats(True)
        self.PrintTimer.start()

        self.setVisible(True)
        self._UpdateButtonStates()
        self.PrinterPanel.repaint()
        self.StackPanel.repaint()

    
    def OnHubChanged(self):
        if self.IsClosed:
            return
        self._UpdateButtonStates()
        # Keep stack index on newest
        try:
            n = int(getattr(self, 'LastKnownStackCount', 0))
            if n > 0:
                self.StackIndex = max(0, n - 1)
        except:
            pass
        self.PrinterPanel.repaint()
        self.StackPanel.repaint()

    
    def _UpdateButtonStates(self, pr=None):
        # Enable Tear off only when a page is finished and fully ejected.
        # Enable Clear stack only when there are pages in the stack.
        canTear = False
        stackCount = None

        try:
            if pr is None:
                # Try to read current printer state without blocking.
                got = False
                try:
                    got = self.Hub.Lock.tryLock()
                except:
                    got = False
                if got:
                    try:
                        pr = self.Hub.Printer
                        try:
                            stackCount = len(self.Hub.StackPages)
                        except:
                            stackCount = None
                    finally:
                        try:
                            self.Hub.Lock.unlock()
                        except:
                            pass
            else:
                # Caller provided printer state; still attempt to get stack count.
                got = False
                try:
                    got = self.Hub.Lock.tryLock()
                except:
                    got = False
                if got:
                    try:
                        try:
                            stackCount = len(self.Hub.StackPages)
                        except:
                            stackCount = None
                    finally:
                        try:
                            self.Hub.Lock.unlock()
                        except:
                            pass

            if pr is not None:
                canTear = bool(pr.get('done', False)) and bool(pr.get('ejected', False))
        except:
            canTear = False

        if stackCount is None:
            try:
                stackCount = int(getattr(self, 'LastKnownStackCount', 0))
            except:
                stackCount = 0

        canClear = int(stackCount) > 0

        try:
            self.BtnTearOff.setEnabled(bool(canTear))
        except:
            pass
        try:
            self.BtnClearStack.setEnabled(bool(canClear))
        except:
            pass

    def _ClearStack(self):
        if self.IsClosed:
            return

        # If already empty, do nothing (and keep the button greyed out).
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if got:
            try:
                try:
                    if len(self.Hub.StackPages) <= 0:
                        try:
                            self.LastKnownStackCount = 0
                        except:
                            pass
                        self._UpdateButtonStates()
                        return
                except:
                    pass
            finally:
                try:
                    self.Hub.Lock.unlock()
                except:
                    pass

        try:
            choice = swing.JOptionPane.showConfirmDialog(
                self,
                'Clear the teleprinter stack for this JMRI runtime session?\nThis cannot be undone.',
                'Confirm clear',
                swing.JOptionPane.OK_CANCEL_OPTION,
                swing.JOptionPane.WARNING_MESSAGE
            )
            if choice != swing.JOptionPane.OK_OPTION:
                return
        except:
            return

        # EDT-safe: tryLock only.
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if not got:
            return
        try:
            self.Hub.StackPages = []
            self.StackIndex = 0
        finally:
            try:
                self.Hub.Lock.unlock()
            except:
                pass

        try:
            self.LastKnownStackCount = 0
        except:
            pass

        self.OnHubChanged()
        self._UpdateButtonStates()


    def _TearOff(self):
        if self.IsClosed:
            return
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if not got:
            return
        changed = False
        try:
            if self.Hub.Printer is not None:
                pr = self.Hub.Printer
                if bool(pr.get('done', False)) and bool(pr.get('ejected', False)):
                    page = pr.get('page', None)
                    if page is not None:
                        self.Hub.StackPages.append(page)
                        changed = True
                    self.Hub.Printer = None
                    # Start next pending if any
                    changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
        finally:
            try:
                self.Hub.Lock.unlock()
            except:
                pass
        if changed:
            self.OnHubChanged()

    def _SetStatus(self, statusText):
        # Update the footer status label safely on the EDT.
        try:
            txt = str(statusText)
        except:
            txt = ''

        def _Apply():
            try:
                self.LblStatus.setText(txt)
            except:
                pass

        try:
            if SwingUtilities.isEventDispatchThread():
                _Apply()
            else:
                SwingUtilities.invokeLater(RunnableAdapter(_Apply))
        except:
            try:
                _Apply()
            except:
                pass

    def _OnTick(self, e=None):
        if self.IsClosed:
            return

        # Only the owner window advances printing.
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if not got:
            # Still repaint for smooth UI.
            self.PrinterPanel.repaint()
            return

        changed = False
        try:
            if self.Hub.PrintOwnerId is None:
                self.Hub.PrintOwnerId = id(self)
            if self.Hub.PrintOwnerId != id(self):
                return

            # If printer is empty, start next pending.
            changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
            pr = self.Hub.Printer
            self._UpdateButtonStates(pr)
            if pr is None:
                self._SetStatus('IDLE')
                return

            # If page is done and ejected, enable tear-off.
            if bool(pr.get('done', False)) and bool(pr.get('ejected', False)):
                self._SetStatus('READY')
            else:
                self._SetStatus('PRINTING')

            # If printing finished and there are pending pages, auto tear-off and start next.
            if bool(pr.get('done', False)) and bool(pr.get('ejected', False)) and self.Hub.PendingPages:
                changed = _AutoMovePrinterToStackLocked(self.Hub) or changed
                changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
                return

            # Animate paper movement if needed.
            scroll = int(pr.get('scrollAnim', 0))
            if scroll > 0:
                scroll = max(0, scroll - int(SCROLL_PIXELS_PER_TICK))
                pr['scrollAnim'] = scroll
                return

            # If already done, handle ejection lines.
            if bool(pr.get('done', False)):
                if not bool(pr.get('ejected', False)):
                    rem = int(pr.get('ejectRemaining', 0))
                    if rem <= 0:
                        pr['ejected'] = True
                        return
                    # Feed a blank line: this moves paper.
                    pr['lines'].append('')
                    pr['scrollAnim'] = int(LINE_HEIGHT_PX)
                    pr['ejectRemaining'] = rem - 1
                return

            # Print characters from page text.
            page = pr.get('page', None)
            if page is None:
                pr['done'] = True
                pr['ejectRemaining'] = int(EJECT_BLANK_LINES)
                return

            txt = page.get('text', '')
            pos = int(pr.get('pos', 0))

            # Print one character per tick.
            if pos >= len(txt):
                pr['done'] = True
                pr['ejectRemaining'] = int(EJECT_BLANK_LINES)
                return

            ch = txt[pos]
            pr['pos'] = pos + 1

            if ch == '\n':
                # Carriage return: finalize current line and move paper.
                try:
                    pr['lines'].append(pr.get('currentLine', ''))
                except:
                    pass
                pr['currentLine'] = ''
                pr['scrollAnim'] = int(LINE_HEIGHT_PX)
                return

            # Skip '\r' if any.
            if ch == '\r':
                return

            cur = pr.get('currentLine', '')
            pr['currentLine'] = str(cur) + str(ch)
        finally:
            try:
                self.Hub.Lock.unlock()
            except:
                pass

        if changed:
            self.OnHubChanged()
        else:
            self.PrinterPanel.repaint()
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
                    n = int(getattr(frame, 'LastKnownStackCount', 0))
                    if frame.StackIndex < n - 1:
                        frame.StackIndex += 1
                        frame.StackPanel.repaint()
                except:
                    pass
            elif code in (event.KeyEvent.VK_LEFT, event.KeyEvent.VK_UP):
                try:
                    if frame.StackIndex > 0:
                        frame.StackIndex -= 1
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
                    if frame.StackIndex > 0:
                        frame.StackIndex -= 1
                        frame.StackPanel.repaint()
                except:
                    pass
            elif rot < 0:
                try:
                    n = int(getattr(frame, 'LastKnownStackCount', 0))
                    if frame.StackIndex < n - 1:
                        frame.StackIndex += 1
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
                    if frame.StackIndex > 0:
                        frame.StackIndex -= 1
                        frame.StackPanel.repaint()
                except:
                    pass
            elif x > w * 0.75:
                try:
                    n = int(getattr(frame, 'LastKnownStackCount', 0))
                    if frame.StackIndex < n - 1:
                        frame.StackIndex += 1
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
