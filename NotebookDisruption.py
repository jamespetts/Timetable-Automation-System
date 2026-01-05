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
# Handwriting-on-ruled-paper disruption output (live writing + filed pages) for signallers.
#
# <<SIG-DISP-NAME: Notebook disruption messages>>
# <<DESCRIPTION: Simulates handwritten disruption reports on ruled paper with a margin. Live writing on the left; filed pages on the right.>>
#
# <<SETTING DESCRIPTION BOOLEAN: Use 24-hour time>>
#
# OPTIONAL APPEARANCE MEMORIES (all are prefix-agnostic via TASBeanLookup):
# - TASPAPERCOLOUR         e.g. "249,246,238" (default)
# - TASINKCOLOUR           e.g. "40,40,40" (default)
# - TASRULELINECOLOUR      e.g. "173,205,235" (light blue)
# - TASMARGINCOLOUR        e.g. "220,80,80" (soft red)
# - TASHANDWRITINGFONT     e.g. "Segoe Script" (optional; script will pick a suitable font if missing)
#
# IMPORTANT DESIGN NOTE (DO NOT "CLEAN UP" WITHOUT CHECKING):
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
from java.lang import Runnable, Thread
from javax.swing import SwingUtilities
from javax.swing import Timer
from java.util.concurrent.locks import ReentrantLock

import TASBeanLookup as TBL
import TASUtil as TU
import DisruptionRegister as DR
from DisruptionRegister import getDisruption
import TimingRegister as TR
from jmri.profile import ProfileManager

# --------------------------------------------------
# UI sizing/appearance
# --------------------------------------------------
FRAME_WIDTH = 980
FRAME_HEIGHT = 520

# Left notebook viewport and paper
NOTEBOOK_PAPER_WIDTH = 420
NOTEBOOK_PAPER_HEIGHT = 450

# Right filed page preview
STACK_PAPER_MAX_WIDTH = 320
STACK_PAPER_MAX_HEIGHT = 380

# Handwriting animation
WRITE_TIMER_MS = 70
WRITE_CHARS_PER_TICK = 1

# Ruled paper geometry
LINE_HEIGHT_PX = 22
TOP_MARGIN_PX = 34
BOTTOM_MARGIN_PX = 28
LEFT_PADDING_PX = 14
RIGHT_PADDING_PX = 14
MARGIN_LINE_X_PX = 64

# Ink appearance
INK_ALPHA = 210
INK_BLEND_TO_PAPER = 0.18

# After completing a page, pause briefly before it becomes "fileable".
DONE_HOLD_TICKS = 18

# --------------------------------------------------
# Runtime hub (singleton)
# --------------------------------------------------
_HUB_MODULE_KEY = 'TASHandwritingDisruptionHub'

def _GetOrCreateHub():
    hub = sys.modules.get(_HUB_MODULE_KEY)
    if hub is None:
        class _Hub(object):
            pass
        hub = _Hub()
        sys.modules[_HUB_MODULE_KEY] = hub
        hub.Windows = []
        # Filed pages (fully written).
        hub.StackPages = []
        # Current writing job/page, or None.
        hub.Writer = None
        # Pending pages waiting to be written.
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
        # Only one window drives writing/promotions.
        hub.WriteOwnerId = None
    return hub

# --------------------------------------------------
# Memory helpers (prefix-agnostic)
# --------------------------------------------------
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

# --------------------------------------------------
# Time helpers
# --------------------------------------------------
_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Timing point header support: accept TPArr/TPDep and TP<digits>Arr/TP<digits>Dep.
_TP_KEY_PAT = re.compile(r'^TP(\d*)(Arr|Dep)\s+(.+)$', re.IGNORECASE)


def _FindTpCellValue(row, tpName, arrdep):
    # Return the raw timetable cell value for a TP name and ARR/DEP selector.
    # Supports both legacy headers (TPArr X / TPDep X) and grouped headers (TP1Arr X / TP1Dep X, etc).
    if not row or not tpName or not arrdep:
        return ''
    wantName = str(tpName).strip()
    if wantName == '':
        return ''
    wantKind = str(arrdep).strip().upper()
    if wantKind not in ('ARR', 'DEP'):
        return ''
    # Fast path: legacy exact key.
    try:
        key = ('TPArr ' if wantKind == 'ARR' else 'TPDep ') + wantName
        v = row.get(key, None)
        if v is not None and str(v).strip() != '':
            return str(v)
    except:
        pass
    # Scan headers for grouped form.
    try:
        for k, v in row.items():
            if not k:
                continue
            ks = str(k).strip()
            m = _TP_KEY_PAT.match(ks)
            if not m:
                continue
            kind = (m.group(2) or '').strip().upper()
            name = (m.group(3) or '').strip()
            if kind == wantKind and name.lower() == wantName.lower():
                return '' if v is None else str(v)
    except:
        pass
    return ''


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
        h = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h * 60 + mm
        return None
    m = re.match(r'^\s*(\d{1,2}):(\d{2})\s*([AP]\s*M)\s*$', s, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2))
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

# --------------------------------------------------
# Timetable helpers
# --------------------------------------------------

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
        f = open(path, 'r')
        try:
            reader = csv.DictReader(f, delimiter='\t')
            rows = list(reader)
        finally:
            try:
                f.close()
            except:
                pass
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
        ks = str(k).strip()
        m = _TP_KEY_PAT.match(ks)
        if not m:
            continue
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
    dest = _ToDisplayCase(dest)
    timePart = _FormatMinutes(sched, use24h) if sched is not None else ''
    if timePart and dest:
        return '%s to %s' % (timePart, dest)
    if timePart:
        return timePart
    if dest:
        return dest
    return 'Service'

# --------------------------------------------------
# Timing helpers
# --------------------------------------------------

def _InferArrDepForTP(row, tpName, actualMin):
    if not row or not tpName:
        return 'DEP'
    va = _FindTpCellValue(row, tpName, 'ARR')
    vd = _FindTpCellValue(row, tpName, 'DEP')
    a = _ParseTimeToMinutes(va) if va else None
    d = _ParseTimeToMinutes(vd) if vd else None
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
    kind = str(arrdep).strip().upper()
    if kind == 'ARR':
        raw = _FindTpCellValue(row, tpName, 'ARR')
    else:
        raw = _FindTpCellValue(row, tpName, 'DEP')
    try:
        v = (raw or '').strip()
        return _ParseTimeToMinutes(v) if v else None
    except:
        return None


def _StatusFromDelta(deltaMin):
    if deltaMin is None:
        return ('', 0)
    d = int(deltaMin)
    if d == 0:
        return ('On time', 0)
    if d > 0:
        return ('Late', d)
    return ('Early', -d)


def _IsCancelledValue(valInt):
    try:
        return int(valInt) > 1440
    except:
        return False

# --------------------------------------------------
def _ToDisplayCase(s):
    try:
        t = str(s)
    except:
        return ''
    t = t.strip()
    if t == '':
        return ''
    # Sentence-case each word (keeps digits intact, avoids all-caps look).
    out = []
    for w in t.split(' '):
        if w == '':
            continue
        try:
            out.append(w[:1].upper() + w[1:].lower())
        except:
            out.append(w)
    return ' '.join(out)

# Message construction
# --------------------------------------------------

def _BuildMessageText(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    # Handwritten-style narrative, not teleprinter structure.
    use24h = _ReadMemBool('TAS_USER_SETTING_USE_24_HOUR_TIME', True)

    ident = _MakeTrainIdentifier(hub, dayName, rn, use24h)

    # Status phrase
    if _IsCancelledValue(disruptionInt):
        statusPhrase = 'cancelled'
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
        stLower = str(st).strip().lower()
        if stLower == 'on time' or int(mag) == 0:
            statusPhrase = 'on time'
        else:
            mins = int(mag)
            unit = 'min' if mins == 1 else 'mins'
            statusPhrase = '%s %d %s' % (stLower, mins, unit)

    # Subject phrase
    if TU.IsDefaultReportingNumber(str(rn)):
        subj = 'Service ' + str(ident)
    else:
        subj = 'Train ' + str(ident)

    stamp = '%s %s' % (_ToDisplayCase(dayName), _FormatMinutes(nowMin, use24h))
    lines = []
    lines.append('%s - %s %s' % (stamp, subj, statusPhrase))

    # Optional last reported line
    if tpName and tpTimeMin is not None:
        row = _RowForTrain(hub, dayName, rn)
        arrdep = _InferArrDepForTP(row, tpName, tpTimeMin)
        ad = str(arrdep).strip().lower()
        lines.append('')
        lines.append('Last at %s %s %s' % (_ToDisplayCase(tpName), ad, _FormatMinutes(tpTimeMin, use24h)))

    return '\n'.join(lines) + '\n'
def _EnsureTrainState(hub, rn):
    st = hub.TrainState.get(str(rn))
    if st is None:
        st = {
            'LastWrittenAbs': None,
            'FirstTpSeen': False,
            'LastTpOnTime': None,
            'LastWrittenWasCancel': False,
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


def _NewWriterState(pageRec):
    # pageRec contains full text.
    return {
        'page': pageRec,
        'pos': 0,
        'lines': [],
        'currentLine': '',
        'done': False,
        'fileable': False,
        'holdRemaining': int(DONE_HOLD_TICKS),
    }


def _AutoMoveWriterToStackLocked(hub):
    # Caller must hold hub.Lock.
    if hub.Writer is None:
        return False
    wr = hub.Writer
    try:
        if not wr.get('done', False):
            return False
        if not wr.get('fileable', False):
            return False
    except:
        return False
    try:
        page = wr.get('page', None)
        if page is not None:
            hub.StackPages.append(page)
    except:
        pass
    hub.Writer = None
    return True


def _StartNextPendingIfIdleLocked(hub):
    # Caller must hold hub.Lock.
    if hub.Writer is not None:
        return False
    if not hub.PendingPages:
        return False
    nxt = hub.PendingPages.pop(0)
    hub.Writer = _NewWriterState(nxt)
    return True


def _AddIncomingPage(hub, pageRec):
    # Returns True if the writer state or stack changed.
    changed = False
    hub.Lock.lock()
    try:
        # If the writer is holding a finished page and a new page arrives, auto-file it.
        if hub.Writer is not None:
            changed = _AutoMoveWriterToStackLocked(hub) or changed
        if hub.Writer is None:
            hub.Writer = _NewWriterState(pageRec)
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

        # Writer page: if older than 1 day, drop it.
        if hub.Writer is not None:
            try:
                page = hub.Writer.get('page', None)
                if page is not None:
                    age = _AgeMinutes(nowAbs, page.get('absWeek', nowAbs))
                    if age >= 1440:
                        hub.Writer = None
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
            if (not st.get('LastWrittenWasCancel', False)) or (lastVal is None) or (not _IsCancelledValue(lastVal)):
                _AddMessage(hub, str(dayName), nowMin, rn, curInt)
                st['LastWrittenWasCancel'] = True
                hub.LastSeenDisruptions[str(rn)] = curInt
            continue

        if not wasSeen:
            _AddMessage(hub, str(dayName), nowMin, rn, curInt)
            st['LastWrittenAbs'] = _ComputeWeekAbsMinute(dayName, nowMin)
            st['LastWrittenWasCancel'] = False
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
        if st.get('LastWrittenAbs', None) is not None:
            age = _AgeMinutes(nowAbs, st.get('LastWrittenAbs'))
            okByTime = (age >= int(limit))

        if okByTime:
            _AddMessage(hub, str(dayName), nowMin, rn, curInt)
            st['LastWrittenAbs'] = nowAbs
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

# --------------------------------------------------
# UI helpers
# --------------------------------------------------

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



# Draw a simple wood background (desk surface).
def _DrawWoodSurface(g, x, y, w, h):
    try:
        base = awt.Color(110, 78, 45)
        g.setColor(base)
        g.fillRect(int(x), int(y), int(w), int(h))
        g.setColor(awt.Color(90, 62, 36, 110))
        step = 22
        yy = int(y)
        while yy < int(y) + int(h):
            g.drawLine(int(x), yy, int(x) + int(w), yy)
            yy += step
    except:
        try:
            g.setColor(awt.Color(110, 78, 45))
            g.fillRect(int(x), int(y), int(w), int(h))
        except:
            pass
def _PickHandwritingFont(sizePx):
    # Choose a handwriting-like font if available.
    # Order: explicit memory request, then a conservative list of commonly-available script fonts.
    want = _ReadMemStr('TASHANDWRITINGFONT', None)
    families = []
    if want:
        families.append(str(want))
    families.extend([
        'Segoe Script',
        'Bradley Hand',
        'Lucida Handwriting',
        'Comic Sans MS',
        'URW Chancery L',
        'Apple Chancery',
        'SansSerif',
    ])
    try:
        env = awt.GraphicsEnvironment.getLocalGraphicsEnvironment()
        avail = list(env.getAvailableFontFamilyNames())
        availLower = {}
        for nm in avail:
            try:
                availLower[str(nm).lower()] = str(nm)
            except:
                pass
        for nm in families:
            try:
                real = availLower.get(str(nm).lower(), None)
                if real is not None:
                    return awt.Font(real, awt.Font.PLAIN, int(sizePx))
            except:
                continue
    except:
        pass
    return awt.Font('SansSerif', awt.Font.PLAIN, int(sizePx))


def _Jitter(seedInt, idx, amp):
    # Deterministic small jitter for a more handwritten feel.
    try:
        x = int(seedInt) ^ (int(idx) * 1103515245 + 12345)
        x = (x ^ (x >> 16)) & 0x7fffffff
        # Map to [-amp, +amp]
        if amp <= 0:
            return 0
        return int((x % (amp * 2 + 1)) - amp)
    except:
        return 0


def _WrapTextToLines(g, font, text, maxWidthPx):
    # Wrap the given text into lines that fit within maxWidthPx.
    # Preserves existing newlines.
    out = []
    try:
        g.setFont(font)
        fm = g.getFontMetrics(font)
    except:
        fm = None

    def _Width(s):
        try:
            return fm.stringWidth(s)
        except:
            return len(s) * 8

    for raw in str(text).split('\n'):
        s = str(raw)
        if s == '':
            out.append('')
            continue
        words = s.split(' ')
        cur = ''
        for w in words:
            if cur == '':
                test = w
            else:
                test = cur + ' ' + w
            if _Width(test) <= int(maxWidthPx):
                cur = test
            else:
                if cur != '':
                    out.append(cur)
                # If a single word is too long, hard-split.
                if _Width(w) <= int(maxWidthPx):
                    cur = w
                else:
                    chunk = ''
                    for ch in w:
                        if chunk == '':
                            t2 = ch
                        else:
                            t2 = chunk + ch
                        if _Width(t2) <= int(maxWidthPx):
                            chunk = t2
                        else:
                            if chunk != '':
                                out.append(chunk)
                            chunk = ch
                    cur = chunk
        if cur != '':
            out.append(cur)
    return out


def _DrawPaperWithRules(g, x, y, w, h, paperColor, ruleColor, marginColor):
    # Paper with soft shadow
    try:
        g.setColor(awt.Color(0, 0, 0, 35))
        g.fillRoundRect(int(x) + 4, int(y) + 5, int(w), int(h), 10, 10)
    except:
        pass

    g.setColor(paperColor)
    g.fillRoundRect(int(x), int(y), int(w), int(h), 10, 10)

    try:
        g.setColor(awt.Color(0, 0, 0, 45))
        g.drawRoundRect(int(x), int(y), int(w), int(h), 10, 10)
    except:
        pass

    # Rules
    try:
        g.setColor(awt.Color(ruleColor.getRed(), ruleColor.getGreen(), ruleColor.getBlue(), 120))
    except:
        g.setColor(ruleColor)

    top = int(y) + int(TOP_MARGIN_PX)
    bottom = int(y) + int(h) - int(BOTTOM_MARGIN_PX)
    yy = top
    while yy <= bottom:
        try:
            g.drawLine(int(x) + 10, int(yy), int(x) + int(w) - 10, int(yy))
        except:
            pass
        yy += int(LINE_HEIGHT_PX)

    # Margin line
    mx = int(x) + int(MARGIN_LINE_X_PX)
    try:
        g.setColor(awt.Color(marginColor.getRed(), marginColor.getGreen(), marginColor.getBlue(), 170))
    except:
        g.setColor(marginColor)
    try:
        g.drawLine(int(mx), int(y) + 10, int(mx), int(y) + int(h) - 10)
    except:
        pass

# --------------------------------------------------
# Notebook (live writing) panel
# --------------------------------------------------
class NotebookPanel(swing.JPanel):
    def __init__(self, hub, ownerFrame):
        swing.JPanel.__init__(self)
        self.Hub = hub
        self.Owner = ownerFrame
        self.setBackground(awt.Color(40, 40, 40))
        self.setFocusable(True)

        self.PaperColor = _RgbStrToColor(_ReadMemStr('TASPAPERCOLOUR', '249,246,238'), awt.Color(249, 246, 238))
        baseInk = _RgbStrToColor(_ReadMemStr('TASINKCOLOUR', '40,40,40'), awt.Color(40, 40, 40))
        self.InkColor = _FadeInkColor(baseInk, self.PaperColor, INK_BLEND_TO_PAPER, INK_ALPHA)
        self.RuleLineColor = _RgbStrToColor(_ReadMemStr('TASRULELINECOLOUR', '173,205,235'), awt.Color(173, 205, 235))
        self.MarginColor = _RgbStrToColor(_ReadMemStr('TASMARGINCOLOUR', '220,80,80'), awt.Color(220, 80, 80))
        self.Font = _PickHandwritingFont(18)

        # Cache for painting
        self.CachedWriter = None

    def paintComponent(self, g):
        try:
            g.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        w = self.getWidth()
        h = self.getHeight()
        _DrawWoodSurface(g, 0, 0, w, h)

        # Snapshot writer state without blocking EDT.
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if got:
            try:
                wr = self.Hub.Writer
                if wr is None:
                    self.CachedWriter = None
                else:
                    self.CachedWriter = {
                        'page': wr.get('page', None),
                        'pos': int(wr.get('pos', 0)),
                        'lines': list(wr.get('lines', [])),
                        'currentLine': str(wr.get('currentLine', '')),
                        'done': bool(wr.get('done', False)),
                        'fileable': bool(wr.get('fileable', False)),
                    }
            finally:
                try:
                    self.Hub.Lock.unlock()
                except:
                    pass

        # Viewport
        vpw = min(NOTEBOOK_PAPER_WIDTH + 60, w - 20)
        vph = min(NOTEBOOK_PAPER_HEIGHT + 60, h - 20)
        vx = (w - vpw) // 2
        vy = (h - vph) // 2

        # Paper area inside viewport
        px = vx + 30
        py = vy + 30
        pw = vpw - 60
        ph = vph - 60

        # Draw paper even if idle
        _DrawPaperWithRules(g, px, py, pw, ph, self.PaperColor, self.RuleLineColor, self.MarginColor)

        wr = self.CachedWriter
        if wr is None:
            return

        # Determine seed from page absWeek if possible
        seed = 0
        try:
            page = wr.get('page', None)
            if page is not None:
                seed = int(page.get('absWeek', 0))
        except:
            seed = 0

        # Compute writing bounds
        textX = int(px) + int(MARGIN_LINE_X_PX) + int(LEFT_PADDING_PX)
        textY = int(py) + int(TOP_MARGIN_PX)
        textW = int(pw) - int(MARGIN_LINE_X_PX) - int(LEFT_PADDING_PX) - int(RIGHT_PADDING_PX)
        textH = int(ph) - int(TOP_MARGIN_PX) - int(BOTTOM_MARGIN_PX)

        # Prepare display lines: completed + current
        try:
            doneLines = list(wr.get('lines', []))
        except:
            doneLines = []
        try:
            curLine = str(wr.get('currentLine', ''))
        except:
            curLine = ''

        display = list(doneLines)
        display.append(curLine)

        g.setColor(self.InkColor)
        g.setFont(self.Font)

        # Wrap each logical line to fit width.
        wrapped = []
        for ln in display:
            try:
                parts = _WrapTextToLines(g, self.Font, ln, textW)
            except:
                parts = [str(ln)]
            for p in parts:
                wrapped.append(p)

        maxLines = 1
        try:
            maxLines = max(1, int(textH // int(LINE_HEIGHT_PX)))
        except:
            maxLines = 1

        # If too many, show the last maxLines (messages are short, but keep safe).
        if len(wrapped) > maxLines:
            wrapped = wrapped[-maxLines:]

        y = int(textY) + int(LINE_HEIGHT_PX) - 6
        lineIndexBase = max(0, len(doneLines) - len(wrapped) + 1)

        for i, ln in enumerate(wrapped):
            # Slight per-line jitter for handwriting.
            dx = _Jitter(seed, i + lineIndexBase, 2)
            dy = _Jitter(seed, i + lineIndexBase + 77, 1)
            try:
                g.drawString(str(ln), int(textX) + int(dx), int(y) + int(dy))
            except:
                pass
            y += int(LINE_HEIGHT_PX)

# --------------------------------------------------
# Filed pages (stack) panel
# --------------------------------------------------
class FiledPagesPanel(swing.JPanel):
    def __init__(self, hub, ownerFrame):
        swing.JPanel.__init__(self)
        self.Hub = hub
        self.Owner = ownerFrame
        self.setBackground(awt.Color(55, 55, 55))
        self.setFocusable(True)

        self.PaperColor = _RgbStrToColor(_ReadMemStr('TASPAPERCOLOUR', '249,246,238'), awt.Color(249, 246, 238))
        baseInk = _RgbStrToColor(_ReadMemStr('TASINKCOLOUR', '40,40,40'), awt.Color(40, 40, 40))
        self.InkColor = _FadeInkColor(baseInk, self.PaperColor, INK_BLEND_TO_PAPER, INK_ALPHA)
        self.RuleLineColor = _RgbStrToColor(_ReadMemStr('TASRULELINECOLOUR', '173,205,235'), awt.Color(173, 205, 235))
        self.MarginColor = _RgbStrToColor(_ReadMemStr('TASMARGINCOLOUR', '220,80,80'), awt.Color(220, 80, 80))
        self.Font = _PickHandwritingFont(14)

        self.CachedStack = []

    def paintComponent(self, g):
        try:
            g.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass

        w = self.getWidth()
        h = self.getHeight()
        _DrawWoodSurface(g, 0, 0, w, h)

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

        try:
            self.Owner.LastKnownStackCount = int(n)
        except:
            pass

        margin = 18
        px = margin
        py = margin
        pw = max(60, int(w) - margin * 2)
        ph = max(60, int(h) - margin * 2)


        if n == 0:
            g.setColor(awt.Color(230, 230, 230))
            g.setFont(awt.Font('SansSerif', awt.Font.PLAIN, 12))
            try:
                g.drawString('No filed pages', int(px) + 18, int(py) + 28)
            except:
                pass
            return

        # Compute paper size
        paperW = min(int(pw) - 40, int(STACK_PAPER_MAX_WIDTH))
        paperH = min(int(ph) - 60, int(STACK_PAPER_MAX_HEIGHT))
        paperW = max(220, paperW)
        paperH = max(240, paperH)
        paperW = min(paperW, int(pw) - 40)
        paperH = min(paperH, int(ph) - 60)

        baseX = int(px) + (int(pw) - paperW) // 2
        baseY = int(py) + (int(ph) - paperH) // 2 + 8

        idx = self.Owner.StackIndex
        idx = max(0, min(n - 1, idx))
        self.Owner.StackIndex = idx

        # Simple stack shadow behind
        behind = min(4, n - 1)
        for i in range(behind, 0, -1):
            off = i * 3
            try:
                _DrawPaperWithRules(g, baseX + off, baseY + off, paperW, paperH, self.PaperColor, self.RuleLineColor, self.MarginColor)
            except:
                pass

        # Foremost page
        _DrawPaperWithRules(g, baseX, baseY, paperW, paperH, self.PaperColor, self.RuleLineColor, self.MarginColor)

        g.setColor(awt.Color(240, 240, 240))
        g.setFont(awt.Font('SansSerif', awt.Font.PLAIN, 12))
        try:
            g.drawString('%d / %d' % (idx + 1, n), int(baseX) + 10, int(baseY) - 8)
        except:
            pass

        page = pages[idx]
        txt = page.get('text', '') if isinstance(page, dict) else str(page)

        # Text bounds
        textX = int(baseX) + int(MARGIN_LINE_X_PX) + 10
        textY = int(baseY) + int(TOP_MARGIN_PX)
        textW = int(paperW) - int(MARGIN_LINE_X_PX) - 20
        textH = int(paperH) - int(TOP_MARGIN_PX) - int(BOTTOM_MARGIN_PX)

        g.setColor(self.InkColor)
        g.setFont(self.Font)

        wrapped = _WrapTextToLines(g, self.Font, txt, textW)

        maxLines = 1
        try:
            maxLines = max(1, int(textH // int(LINE_HEIGHT_PX)))
        except:
            maxLines = 1

        y = int(textY) + int(LINE_HEIGHT_PX) - 6
        for ln in wrapped[:maxLines]:
            try:
                g.drawString(str(ln), int(textX), int(y))
            except:
                pass
            y += int(LINE_HEIGHT_PX)

# --------------------------------------------------
# Main frame
# --------------------------------------------------
class NotebookFrame(swing.JFrame):
    def __init__(self, hub):
        swing.JFrame.__init__(self, 'Notebook session')
        self.Hub = hub
        self.IsClosed = False
        self.StackIndex = 0
        self.LastKnownStackCount = 0

        # Claim write ownership if none.
        try:
            hub.Lock.lock()
            try:
                if hub.WriteOwnerId is None:
                    hub.WriteOwnerId = id(self)
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

        # Left: live notebook
        self.NotebookPanel = NotebookPanel(hub, self)
        left = swing.JPanel()
        left.setLayout(awt.BorderLayout())
        left.add(self.NotebookPanel, awt.BorderLayout.CENTER)

        # Right: filed pages
        self.FiledPanel = FiledPagesPanel(hub, self)
        right = swing.JPanel()
        right.setLayout(awt.BorderLayout())
        right.add(self.FiledPanel, awt.BorderLayout.CENTER)

        split = swing.JSplitPane(swing.JSplitPane.HORIZONTAL_SPLIT, left, right)
        split.setResizeWeight(0.50)
        try:
            split.setDividerLocation(520)
        except:
            pass

        self.getContentPane().setLayout(awt.BorderLayout())
        self.getContentPane().add(split, awt.BorderLayout.CENTER)

        footer = swing.JPanel()
        footer.setLayout(awt.FlowLayout(awt.FlowLayout.CENTER, 10, 6))
        footer.setBackground(awt.Color(55, 55, 55))

        self.BtnFilePage = swing.JButton('File page')
        try:
            self.BtnFilePage.setEnabled(False)
        except:
            pass
        footer.add(self.BtnFilePage)

        self.BtnClearStack = swing.JButton('Clear filed')
        footer.add(self.BtnClearStack)


        self.getContentPane().add(footer, awt.BorderLayout.SOUTH)

        self.BtnFilePage.addActionListener(lambda e: self._FilePage())
        self.BtnClearStack.addActionListener(lambda e: self._ClearStack())

        # Stack navigation listeners
        self.addKeyListener(self._KeyListener())
        self.FiledPanel.addMouseWheelListener(self._WheelListener())
        self.FiledPanel.addMouseListener(self._ClickListener())
        self.addWindowListener(self._WindowCloser())

        self.WriteTimer = Timer(int(WRITE_TIMER_MS), self._OnTick)
        self.WriteTimer.setRepeats(True)
        self.WriteTimer.start()

        self.setVisible(True)
        self._UpdateButtonStates()
        self.NotebookPanel.repaint()
        self.FiledPanel.repaint()

    def OnHubChanged(self):
        if self.IsClosed:
            return
        self._UpdateButtonStates()

        # Keep stack index on newest
        n = None
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if got:
            try:
                try:
                    n = len(self.Hub.StackPages)
                except:
                    n = None
            finally:
                try:
                    self.Hub.Lock.unlock()
                except:
                    pass
        if n is None:
            try:
                n = int(getattr(self, 'LastKnownStackCount', 0))
            except:
                n = 0
        try:
            self.LastKnownStackCount = int(n)
        except:
            pass
        try:
            if int(n) > 0:
                self.StackIndex = max(0, int(n) - 1)
        except:
            pass

        self.NotebookPanel.repaint()
        self.FiledPanel.repaint()

    def _UpdateButtonStates(self, wr=None):
        # Enable File page only when a page is finished and fileable.
        # Enable Clear filed only when there are pages in the stack.
        canFile = False
        stackCount = None
        try:
            if wr is None:
                got = False
                try:
                    got = self.Hub.Lock.tryLock()
                except:
                    got = False
                if got:
                    try:
                        wr = self.Hub.Writer
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
            if wr is not None:
                canFile = bool(wr.get('done', False)) and bool(wr.get('fileable', False))
        except:
            canFile = False

        if stackCount is None:
            try:
                stackCount = int(getattr(self, 'LastKnownStackCount', 0))
            except:
                stackCount = 0

        canClear = int(stackCount) > 0

        try:
            self.BtnFilePage.setEnabled(bool(canFile))
        except:
            pass
        try:
            self.BtnClearStack.setEnabled(bool(canClear))
        except:
            pass

    def _ClearStack(self):
        if self.IsClosed:
            return

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
                'Clear the filed pages for this JMRI runtime session?\nThis cannot be undone.',
                'Confirm clear',
                swing.JOptionPane.OK_CANCEL_OPTION,
                swing.JOptionPane.WARNING_MESSAGE
            )
            if choice != swing.JOptionPane.OK_OPTION:
                return
        except:
            return

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

    def _FilePage(self):
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
            if self.Hub.Writer is not None:
                wr = self.Hub.Writer
                if bool(wr.get('done', False)) and bool(wr.get('fileable', False)):
                    page = wr.get('page', None)
                    if page is not None:
                        self.Hub.StackPages.append(page)
                        changed = True
                    self.Hub.Writer = None
                    changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
        finally:
            try:
                self.Hub.Lock.unlock()
            except:
                pass

        if changed:
            self.OnHubChanged()

    def _OnTick(self, e=None):
        if self.IsClosed:
            return

        # Only the owner window advances writing.
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False

        if not got:
            self.NotebookPanel.repaint()
            return

        changed = False
        try:
            if self.Hub.WriteOwnerId is None:
                self.Hub.WriteOwnerId = id(self)
            if self.Hub.WriteOwnerId != id(self):
                return

            changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
            wr = self.Hub.Writer

            # Update render caches while holding the hub lock.
            try:
                if wr is None:
                    self.NotebookPanel.CachedWriter = None
                else:
                    self.NotebookPanel.CachedWriter = {
                        'page': wr.get('page', None),
                        'pos': int(wr.get('pos', 0)),
                        'lines': list(wr.get('lines', [])),
                        'currentLine': str(wr.get('currentLine', '')),
                        'done': bool(wr.get('done', False)),
                        'fileable': bool(wr.get('fileable', False)),
                    }
            except:
                pass

            try:
                self.FiledPanel.CachedStack = list(self.Hub.StackPages)
            except:
                pass

            self._UpdateButtonStates(wr)

            if wr is None:
                pass
                return

            if bool(wr.get('done', False)) and bool(wr.get('fileable', False)):
                pass
            else:
                pass

            # If finished and pending pages exist, auto-file and start next.
            if bool(wr.get('done', False)) and bool(wr.get('fileable', False)) and self.Hub.PendingPages:
                changed = _AutoMoveWriterToStackLocked(self.Hub) or changed
                changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
                return

            # If done, count down hold time.
            if bool(wr.get('done', False)) and not bool(wr.get('fileable', False)):
                rem = int(wr.get('holdRemaining', 0))
                rem = max(0, rem - 1)
                wr['holdRemaining'] = rem
                if rem <= 0:
                    wr['fileable'] = True
                return

            # Write characters from page text.
            page = wr.get('page', None)
            if page is None:
                wr['done'] = True
                wr['holdRemaining'] = int(DONE_HOLD_TICKS)
                return

            txt = page.get('text', '')
            pos = int(wr.get('pos', 0))
            if pos >= len(txt):
                wr['done'] = True
                wr['holdRemaining'] = int(DONE_HOLD_TICKS)
                return

            # Write a few characters per tick.
            for _i in range(int(WRITE_CHARS_PER_TICK)):
                if pos >= len(txt):
                    break
                ch = txt[pos]
                pos += 1
                wr['pos'] = pos

                if ch == '\n':
                    try:
                        wr['lines'].append(wr.get('currentLine', ''))
                    except:
                        pass
                    wr['currentLine'] = ''
                    continue

                if ch == '\r':
                    continue

                cur = wr.get('currentLine', '')
                wr['currentLine'] = str(cur) + str(ch)

        finally:
            try:
                self.Hub.Lock.unlock()
            except:
                pass

        if changed:
            self.OnHubChanged()
        else:
            self.NotebookPanel.repaint()
            self.FiledPanel.repaint()

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
                        frame.FiledPanel.repaint()
                except:
                    pass
            elif code in (event.KeyEvent.VK_LEFT, event.KeyEvent.VK_UP):
                try:
                    if frame.StackIndex > 0:
                        frame.StackIndex -= 1
                        frame.FiledPanel.repaint()
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
                        frame.FiledPanel.repaint()
                except:
                    pass
            elif rot < 0:
                try:
                    n = int(getattr(frame, 'LastKnownStackCount', 0))
                    if frame.StackIndex < n - 1:
                        frame.StackIndex += 1
                        frame.FiledPanel.repaint()
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
                        frame.FiledPanel.repaint()
                except:
                    pass
            elif x > w * 0.75:
                try:
                    n = int(getattr(frame, 'LastKnownStackCount', 0))
                    if frame.StackIndex < n - 1:
                        frame.StackIndex += 1
                        frame.FiledPanel.repaint()
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
            if self.WriteTimer is not None:
                self.WriteTimer.stop()
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

# --------------------------------------------------
# Entry
# --------------------------------------------------

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
                        print('[Notebook] Poll error: ' + str(ex))
                    except:
                        pass
                try:
                    Thread.sleep(250)
                except:
                    pass

    try:
        t = Thread(_Poller())
        t.setDaemon(True)
        t.setName('TAS-Notebook-Poller')
        hub.PollThread = t
        t.start()
    except:
        hub.PollThread = None


def _OpenWindow():
    hub = _GetOrCreateHub()
    _StartHubPollingIfNeeded(hub)
    win = NotebookFrame(hub)
    try:
        hub.Windows.append(win)
    except:
        pass


if SwingUtilities.isEventDispatchThread():
    _OpenWindow()
else:
    SwingUtilities.invokeLater(RunnableAdapter(_OpenWindow))
