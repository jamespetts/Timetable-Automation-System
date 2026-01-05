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
# <<SIG-DISP-NAME: Message notebook>>
# <<DESCRIPTION: A notebook where status messages about trains (delays, cancellations, etc.) are written down by hand by the signaller.>>
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

# Adapter to allow passing Python callables to SwingUtilities.invokeLater
class RunnableAdapter(Runnable):
    def __init__(self, fn):
        self.Fn = fn

    def run(self):
        try:
            self.Fn()
        except:
            pass

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

# Last seen BookPanel size (used for off-EDT wrap estimation to match actual rendering).
_LAST_PANEL_W = int(FRAME_WIDTH)
_LAST_PANEL_H = int(FRAME_HEIGHT)


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
        # Book pages (ordered).
        hub.Pages = []
        hub.ViewLeftPageIndex = -1
        hub.LastBookDayName = None

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

def _GetOriginFromRow(row):
    if not row:
        return ''
    for k in ['Origin', 'From', 'Start', 'Starting at', 'Start station', 'From station', 'Origin station']:
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

def _GetDueTimeScheduledMinutes(row):
    # Prefer the scheduled departure time for 'due' time.
    if not row:
        return None
    try:
        dep = (row.get('Dep', '') or '').strip()
    except:
        dep = ''
    mm = _ParseTimeToMinutes(dep) if dep else None
    if mm is not None:
        return mm
    # Fallbacks for older/alternative timetable conventions.
    try:
        trig = (row.get('Trigger', '') or '').strip()
    except:
        trig = ''
    mm = _ParseTimeToMinutes(trig) if trig else None
    if mm is not None:
        return mm
    try:
        arr = (row.get('Arr', '') or '').strip()
    except:
        arr = ''
    mm = _ParseTimeToMinutes(arr) if arr else None
    if mm is not None:
        return mm
    # Last resort: earliest known time on the layout for the service.
    return _GetLayoutEtaScheduledMinutes(row)
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
    # If the reporting number is not a TAS default/hidden value, show it.
    if not TU.IsDefaultReportingNumber(str(rn)):
        return str(rn)

    # Default/hidden reporting numbers (e.g. TASxx): identify the service by timetable details.
    row = _RowForTrain(hub, dayName, rn)
    if row is not None:
        dueMin = _GetDueTimeScheduledMinutes(row)
        dueStr = _FormatTimeForEntry(dueMin, use24h) if dueMin is not None else ''
        origin = _ToDisplayCase(_GetOriginFromRow(row))
        dest = _ToDisplayCase(_GetDestinationFromRow(row))

        if dueStr and origin and dest:
            return '%s %s to %s' % (dueStr, origin, dest)
        if origin and dest:
            return '%s to %s' % (origin, dest)
        if dueStr and dest:
            return '%s to %s' % (dueStr, dest)
        if dueStr and origin:
            return '%s %s' % (dueStr, origin)
        if dest:
            return dest

    # Fallback: should not happen in normal operation because disruption generation depends on timetable data,
    # but keep a safe generic label for test harnesses and misconfiguration.
    return 'train'
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

def _FormatTimeForEntry(mins, use24h):
    try:
        mins = int(mins)
    except:
        return ''
    mins = max(0, min(24 * 60 - 1, mins))
    h = mins // 60
    m = mins % 60
    if use24h:
        return '%d.%02d' % (h, m)
    ap = 'a.m.'
    hh = h
    if hh >= 12:
        ap = 'p.m.'
        hh = hh % 12
    if hh == 0:
        hh = 12
    if m == 0:
        ms = '00'
    elif m < 10:
        ms = str(m)
    else:
        ms = '%02d' % m
    return '%d.%s %s' % (hh, ms, ap)

def _BuildMessageText(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    # Book-style entry: day header once per day, then time-only entries.
    use24h = _ReadMemBool('TAS_USER_SETTING_USE_24_HOUR_TIME', True)
    timeStr = _FormatTimeForEntry(nowMin, use24h)

    ident = _MakeTrainIdentifier(hub, dayName, rn, use24h)

    if _IsCancelledValue(disruptionInt):
        statusText = 'cancelled'
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
            statusText = 'on time'
        else:
            mins = int(mag)
            unit = 'min' if mins == 1 else 'mins'
            statusText = '%d %s %s' % (mins, unit, stLower)

    locText = ''
    if tpName and str(tpName).strip() != '':
        locText = ' at ' + _ToDisplayCase(tpName)

    entry = '%s - %s %s%s' % (timeStr, str(ident), statusText, locText)

    lines = []
    try:
        lastDay = getattr(hub, 'LastBookDayName', None) if hub is not None else None
    except:
        lastDay = None
    dn = _ToDisplayCase(dayName)
    if lastDay is None or str(lastDay).strip().lower() != str(dayName).strip().lower():
        lines.append(dn)
        lines.append('-' * max(3, len(dn)))
        if hub is not None:
            try:
                hub.LastBookDayName = str(dayName)
            except:
                pass
    lines.append(entry)
    return '\n'.join(lines) + '\n'


# Build a single entry line (no day header). This is used when multiple entries share a page.
def _BuildEntryLine(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    use24h = _ReadMemBool('TAS_USER_SETTING_USE_24_HOUR_TIME', True)
    timeStr = _FormatTimeForEntry(nowMin, use24h)
    ident = _MakeTrainIdentifier(hub, dayName, rn, use24h)

    if _IsCancelledValue(disruptionInt):
        statusText = 'cancelled'
    else:
        delta = None
        if tpName and tpTimeMin is not None:
            row = _RowForTrain(hub, dayName, rn)
            arrdep = _InferArrDepForTP(row, tpName, tpTimeMin)
            sched = _GetScheduledMinuteForTP(row, tpName, arrdep)
            if sched is not None:
                try:
                    delta = int(tpTimeMin) - int(sched)
                except:
                    delta = None
        if delta is None:
            try:
                delta = int(disruptionInt)
            except:
                delta = 0
        st, mag = _StatusFromDelta(delta)
        stLower = str(st).strip().lower()
        if stLower == 'on time' or int(mag) == 0:
            statusText = 'on time'
        else:
            mins = int(mag)
            unit = 'min' if mins == 1 else 'mins'
            statusText = '%d %s %s' % (mins, unit, stLower)

    locText = ''
    if tpName and str(tpName).strip() != '':
        locText = ' at ' + _ToDisplayCase(tpName)

    return '%s - %s %s%s' % (timeStr, str(ident), statusText, locText)


def _BuildDayHeaderText(dayName):
    dn = _ToDisplayCase(dayName)
    ul = '-' * max(3, len(dn))
    return dn + '\n' + ul + '\n'


# Estimate wrapped line count for a given page text using a fixed default page geometry.
# This is used OFF the EDT to decide whether a new entry will fit on the current page.
def _EstimateWrappedLineCountForPageText(text, font):
    try:
        from java.awt.image import BufferedImage
        img = BufferedImage(2, 2, BufferedImage.TYPE_INT_ARGB)
        g = img.getGraphics()
    except:
        return None

    # Default geometry matches the default frame size.
    spineW = 28
    gutter = 10
    outerPad = 6
    inner = 26
    outer = 30

    try:
        pageW = (int(_LAST_PANEL_W) - spineW - gutter * 2) // 2
    except:
        pageW = 400
    try:
        pageH = int(_LAST_PANEL_H) - outerPad * 2
    except:
        pageH = 500

    try:
        textW = int(pageW) - int(MARGIN_LINE_X_PX) - int(inner) - int(outer)
    except:
        textW = 280

    try:
        textH = int(pageH) - int(TOP_MARGIN_PX) - int(BOTTOM_MARGIN_PX)
    except:
        textH = 300

    try:
        maxLines = max(1, int(textH // int(LINE_HEIGHT_PX)))
    except:
        maxLines = 10

    try:
        g.setFont(font)
    except:
        pass

    total = 0
    try:
        lines = str(text or '').split('\n')
    except:
        lines = []

    for ln in lines:
        # Preserve empty lines
        try:
            parts = _WrapTextToLines(g, font, ln, textW)
            total += len(parts)
        except:
            total += 1

    try:
        g.dispose()
    except:
        pass

    return (total, maxLines)


def _WouldEntryFitOnPage(pageRec, addText, font):
    try:
        curText = str(pageRec.get('text', ''))
    except:
        curText = ''

    # Ensure entries start two lines down from the previous entry: one blank ruled line.
    sep = ''
    if curText != '':
        if curText.endswith('\n'):
            sep = '\n'
        else:
            sep = '\n\n'

    cand = curText + sep + str(addText) + '\n'

    res = _EstimateWrappedLineCountForPageText(cand, font)
    if res is None:
        return False
    used, maxLines = res
    return used <= maxLines


def _AppendEntryToExistingPageLocked(hub, pageRec, addText):
    # Append addText (a single entry line) to an existing physical page and ensure writing resumes if needed.
    # IMPORTANT: If the page is currently being written, do NOT change the writer position; just extend the text.
    try:
        curText = str(pageRec.get('text', ''))
    except:
        curText = ''
    sep = ''
    if curText != '':
        if curText.endswith('\n'):
            sep = '\n'
        else:
            sep = '\n\n'
    oldText = curText
    oldLen = len(oldText)
    newText = oldText + sep + str(addText) + '\n'
    pageRec['text'] = newText

    # If this page is the active writer, keep its pos/lines/currentLine intact.
    try:
        wr = getattr(hub, 'Writer', None)
    except:
        wr = None
    if wr is pageRec:
        try:
            pageRec['done'] = False
        except:
            pass
        return

    # Otherwise, if the old text was already fully written, resume at the append point and preserve display lines.
    wasDone = False
    try:
        wasDone = bool(pageRec.get('done', False))
    except:
        wasDone = False
    if wasDone:
        # Preserve any existing handwritten line breaks for the already-written portion.
        # Fall back to raw text splitlines() only if no recorded lines exist.
        keep = None
        try:
            keep = pageRec.get('lines', None)
        except:
            keep = None
        if keep is None or len(keep) == 0:
            try:
                pageRec['lines'] = str(oldText).splitlines()
            except:
                pageRec['lines'] = []
        else:
            try:
                pageRec['lines'] = list(keep)
            except:
                try:
                    pageRec['lines'] = str(oldText).splitlines()
                except:
                    pageRec['lines'] = []
        pageRec['currentLine'] = ''
        pageRec['pos'] = int(oldLen)

    # Ensure these exist (do not clear them if already present).
    if 'lines' not in pageRec:
        pageRec['lines'] = []
    if 'currentLine' not in pageRec:
        pageRec['currentLine'] = ''
    try:
        pageRec['done'] = False
    except:
        pass

    # If no active writer, resume on this page.
    if getattr(hub, 'Writer', None) is None:
        hub.Writer = pageRec

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
    pageRec['pos'] = 0
    pageRec['lines'] = []
    pageRec['currentLine'] = ''
    pageRec['done'] = False
    return pageRec

def _StartNextPendingIfIdleLocked(hub):
    if hub.Writer is not None:
        return False
    if not hub.PendingPages:
        return False
    nxt = hub.PendingPages.pop(0)
    hub.Writer = _NewWriterState(nxt)
    try:
        pi = int(nxt.get('pageIndex', 0))
        hub.ViewLeftPageIndex = _SpreadForPageIndex(pi)
    except:
        pass
    return True

def _AddIncomingPage(hub, pageRec):
    changed = False
    hub.Lock.lock()
    try:
        if not hasattr(hub, 'Pages'):
            hub.Pages = []
        if not hasattr(hub, 'ViewLeftPageIndex'):
            hub.ViewLeftPageIndex = -1
        if not hasattr(hub, 'LastBookDayName'):
            hub.LastBookDayName = None

        try:
            pageIndex = len(hub.Pages)
        except:
            pageIndex = 0
        try:
            pageRec['pageIndex'] = int(pageIndex)
        except:
            pass

        hub.Pages.append(pageRec)
        changed = True

        if hub.Writer is None:
            hub.Writer = _NewWriterState(pageRec)
            try:
                hub.ViewLeftPageIndex = _SpreadForPageIndex(pageIndex)
            except:
                hub.ViewLeftPageIndex = 0
        else:
            hub.PendingPages.append(pageRec)

    finally:
        hub.Lock.unlock()

    if changed:
        SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))
    return changed

def _AddMessage(hub, dayName, nowMin, rn, disruptionInt, tpName=None, tpTimeMin=None):
    # Add a new entry to the book.
    # Entries are separated by one blank ruled line (i.e. start two lines down).
    # A new day always starts on a new page, with the day header at the top.

    entryLine = _BuildEntryLine(hub, dayName, nowMin, rn, disruptionInt, tpName=tpName, tpTimeMin=tpTimeMin)

    # Use the handwriting font for wrap estimation.
    try:
        font = _PickHandwritingFont(18)
    except:
        font = awt.Font('SansSerif', awt.Font.PLAIN, 18)

    dn = str(dayName or '').strip()

    hub.Lock.lock()
    try:
        # Determine whether this is a new day.
        forceNewPage = False
        try:
            lastDay = getattr(hub, 'LastBookDayName', None)
        except:
            lastDay = None

        if lastDay is None:
            forceNewPage = True
        else:
            try:
                if str(lastDay).strip().lower() != dn.lower():
                    forceNewPage = True
            except:
                forceNewPage = True

        # Ensure hub.LastBookDayName tracks the current day when we first write for that day.
        if forceNewPage:
            try:
                hub.LastBookDayName = dn
            except:
                pass

        # If no pages yet, or new day, start a new page with header.
        try:
            hasPages = len(getattr(hub, 'Pages', [])) > 0
        except:
            hasPages = False

        if (not hasPages) or forceNewPage:
            pageText = _BuildDayHeaderText(dn) + entryLine + '\n'
            rec = {
                'absWeek': _ComputeWeekAbsMinute(dn, nowMin),
                'day': dn,
                'timeMin': int(nowMin or 0),
                'rn': str(rn),
                'text': pageText,
            }
            _AddIncomingPage(hub, rec)
            return

        # Same day: try to append to the last page if it will fit without spilling.
        try:
            pages = hub.Pages
        except:
            pages = []

        if not pages:
            pageText = _BuildDayHeaderText(dn) + entryLine + '\n'
            rec = {
                'absWeek': _ComputeWeekAbsMinute(dn, nowMin),
                'day': dn,
                'timeMin': int(nowMin or 0),
                'rn': str(rn),
                'text': pageText,
            }
            _AddIncomingPage(hub, rec)
            return

        lastPage = pages[-1]

        # Only append to the last page if it is for the same day.
        try:
            lastPageDay = str(lastPage.get('day', '')).strip()
        except:
            lastPageDay = ''

        if lastPageDay.lower() != dn.lower():
            pageText = _BuildDayHeaderText(dn) + entryLine + '\n'
            rec = {
                'absWeek': _ComputeWeekAbsMinute(dn, nowMin),
                'day': dn,
                'timeMin': int(nowMin or 0),
                'rn': str(rn),
                'text': pageText,
            }
            _AddIncomingPage(hub, rec)
            return

        if _WouldEntryFitOnPage(lastPage, entryLine, font):
            _AppendEntryToExistingPageLocked(hub, lastPage, entryLine)
            return

        # Does not fit: start a new page (same day, no day header).
        pageText = entryLine + '\n'
        rec = {
            'absWeek': _ComputeWeekAbsMinute(dn, nowMin),
            'day': dn,
            'timeMin': int(nowMin or 0),
            'rn': str(rn),
            'text': pageText,
        }
        _AddIncomingPage(hub, rec)
        return

    finally:
        hub.Lock.unlock()

    # Ensure the UI updates (safe fallback; _AddIncomingPage already notifies).
    try:
        SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))
    except:
        pass

def _CullOldPages(hub, dayName, nowMin):
    # Unlimited book length: do not discard pages.
    return

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



def _PeekNextWord(text, startIndex):
    # Return the next word starting at startIndex (up to space or newline).
    # Used by the handwriting writer to decide word wrapping BEFORE writing the word.
    try:
        s = str(text)
    except:
        return ''
    try:
        i = int(startIndex)
    except:
        i = 0
    if i < 0:
        i = 0
    if i >= len(s):
        return ''
    out = []
    while i < len(s):
        ch = s[i]
        if ch == ' ' or ch == '\n' or ch == '\r' or ch == '\t':
            break
        out.append(ch)
        i += 1
    try:
        return ''.join(out)
    except:
        return ''

def _ComputeTextWFromPanel(panelW, panelH):
    # Compute the available text width in pixels for a page, matching BookPanel._DrawPage.
    try:
        w = int(panelW)
        h = int(panelH)
    except:
        w = int(FRAME_WIDTH)
        h = int(FRAME_HEIGHT)
    spineW = 28
    gutter = 10
    outerPad = 6
    inner = 26
    outer = 30
    try:
        pageW = (w - spineW - gutter * 2) // 2
    except:
        pageW = 400
    try:
        pageH = h - outerPad * 2
    except:
        pageH = 500
    try:
        textW = int(pageW) - int(MARGIN_LINE_X_PX) - int(inner) - int(outer)
    except:
        textW = 280
    try:
        textH = int(pageH) - int(TOP_MARGIN_PX) - int(BOTTOM_MARGIN_PX)
    except:
        textH = 300
    try:
        maxLines = max(1, int(textH // int(LINE_HEIGHT_PX)))
    except:
        maxLines = 10
    return (int(textW), int(maxLines))
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
# ------------------------------------------------------------------------------
# Book UI (cover + ruled pages, two-page spreads)
# ------------------------------------------------------------------------------

BOOK_COVER_COLOR = awt.Color(28, 44, 62)
BOOK_COVER_EDGE = awt.Color(15, 24, 36)
BOOK_SPINE_COLOR = awt.Color(18, 30, 44)
FOLD_PX = 26

# ViewLeftPageIndex is treated as a spread index:
# 0 = inside front cover (left) + page 0 (right)
# 1 = pages 1 (left) and 2 (right)
# 2 = pages 3 (left) and 4 (right), etc.

def _GetMaxSpreadIndex(pages):
    try:
        n = len(pages)
    except:
        n = 0
    if n <= 0:
        return -1
    # Spread 0 uses page 0; each additional spread consumes 2 pages.
    return int(n) // 2

def _SpreadForPageIndex(pageIndex):
    try:
        i = int(pageIndex)
    except:
        i = 0
    if i <= 0:
        return 0
    return (i + 1) // 2

def _GetCoverNewBookButtonRect(panelW, panelH):
    try:
        w = int(panelW)
        h = int(panelH)
    except:
        w = FRAME_WIDTH
        h = FRAME_HEIGHT
    spineW = 28
    outerPad = 6
    gutter = 10
    centerX = w // 2
    pageW = (w - spineW - gutter * 2) // 2
    pageH = h - outerPad * 2
    leftX = centerX - gutter - spineW // 2 - pageW
    pageY = outerPad
    bw = 140
    bh = 30
    bx = int(leftX + (pageW - bw) // 2)
    by = int(pageY + pageH - bh - 18)
    return (bx, by, bw, bh)

def _HitRect(x, y, rect):
    try:
        rx, ry, rw, rh = rect
        return x >= rx and x <= (rx + rw) and y >= ry and y <= (ry + rh)
    except:
        return False

def _GetLastLeftIndex(pages):
    # Backwards-compatible name: returns the max spread index.
    return _GetMaxSpreadIndex(pages)

def _ClampViewLeftIndex(hub):
    try:
        pages = hub.Pages
    except:
        pages = []
    maxSpread = _GetMaxSpreadIndex(pages)
    if maxSpread < 0:
        hub.ViewLeftPageIndex = -1
        return
    try:
        v = int(getattr(hub, 'ViewLeftPageIndex', 0))
    except:
        v = 0
    if v < 0:
        v = 0
    if v > maxSpread:
        v = maxSpread
    hub.ViewLeftPageIndex = v

def _GoPrev(hub):
    hub.Lock.lock()
    try:
        try:
            v = int(getattr(hub, 'ViewLeftPageIndex', -1))
        except:
            v = -1
        if v >= 1:
            hub.ViewLeftPageIndex = v - 1
            _ClampViewLeftIndex(hub)
    finally:
        hub.Lock.unlock()
    SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))

def _GoNext(hub):
    hub.Lock.lock()
    try:
        try:
            pages = hub.Pages
        except:
            pages = []
        maxSpread = _GetMaxSpreadIndex(pages)
        try:
            v = int(getattr(hub, 'ViewLeftPageIndex', -1))
        except:
            v = -1
        if v >= 0 and v < maxSpread:
            hub.ViewLeftPageIndex = v + 1
            _ClampViewLeftIndex(hub)
    finally:
        hub.Lock.unlock()
    SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))

def _NewBook(hub):
    hub.Lock.lock()
    try:
        hub.Pages = []
        hub.PendingPages = []
        hub.Writer = None
        hub.TrainState = {}
        hub.LastSeenDisruptions = {}
        hub.LastTimingDay = None
        hub.LastTimingCountByTP = {}
        hub.ViewLeftPageIndex = -1
        hub.LastBookDayName = None
    finally:
        hub.Lock.unlock()
    SwingUtilities.invokeLater(RunnableAdapter(lambda: _NotifyWindows(hub)))

def _DrawFold(g, x, y, size, isRight):
    try:
        g.setColor(awt.Color(255, 255, 255, 160))
    except:
        return
    if isRight:
        xs = [int(x + size), int(x + size), int(x)]
        ys = [int(y), int(y + size), int(y + size)]
    else:
        xs = [int(x), int(x), int(x + size)]
        ys = [int(y), int(y + size), int(y + size)]
    try:
        g.fillPolygon(xs, ys, 3)
        g.setColor(awt.Color(0, 0, 0, 60))
        g.drawPolygon(xs, ys, 3)
    except:
        pass

def _PageTextLinesForDisplay(pageRec):
    if pageRec is None:
        return []
    try:
        done = bool(pageRec.get('done', False))
    except:
        done = False
    if done:
        # Prefer the recorded handwritten lines if present so finished pages do not snap
        # back to an unwrapped layout. Fall back to raw text for backwards compatibility.
        try:
            ln = pageRec.get('lines', None)
            if ln is not None:
                return list(ln)
        except:
            pass
        try:
            return str(pageRec.get('text', '')).splitlines()
        except:
            return []
    try:
        lines = list(pageRec.get('lines', []))
    except:
        lines = []
    try:
        cur = str(pageRec.get('currentLine', ''))
    except:
        cur = ''

    # Only show the in-progress line if we are actually mid-line.
    # If the last written character was a newline and currentLine is empty,
    # appending an extra '' here consumes a ruled line and can make the last
    # real entry appear one line higher than it should.
    showCur = False
    if cur != '':
        showCur = True
    else:
        try:
            pos = int(pageRec.get('pos', 0))
        except:
            pos = 0
        try:
            txt = str(pageRec.get('text', ''))
        except:
            txt = ''
        if pos > 0 and pos <= len(txt):
            try:
                lastCh = txt[pos - 1]
            except:
                lastCh = ''
            if lastCh != '\n':
                showCur = True

    if showCur:
        lines.append(cur)
    return lines

class BookPanel(swing.JPanel):

    def __init__(self, hub, ownerFrame):
        swing.JPanel.__init__(self)
        self.Hub = hub
        self.Owner = ownerFrame
        self.setFocusable(True)
        self.PaperColor = _RgbStrToColor(_ReadMemStr('TASPAPERCOLOUR', '249,246,238'), awt.Color(249, 246, 238))
        baseInk = _RgbStrToColor(_ReadMemStr('TASINKCOLOUR', '40,40,40'), awt.Color(40, 40, 40))
        self.InkColor = _FadeInkColor(baseInk, self.PaperColor, INK_BLEND_TO_PAPER, INK_ALPHA)
        self.RuleLineColor = _RgbStrToColor(_ReadMemStr('TASRULELINECOLOUR', '173,205,235'), awt.Color(173, 205, 235))
        self.MarginColor = _RgbStrToColor(_ReadMemStr('TASMARGINCOLOUR', '220,80,80'), awt.Color(220, 80, 80))
        self.Font = _PickHandwritingFont(18)
        self.CachedPages = []
        self.CachedViewLeft = -1
        self.addMouseWheelListener(self._Wheel())
        self.addMouseListener(self._Click())
        self.addKeyListener(self._Keys())

    def paintComponent(self, g):
        try:
            g.setRenderingHint(awt.RenderingHints.KEY_TEXT_ANTIALIASING, awt.RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            g.setRenderingHint(awt.RenderingHints.KEY_ANTIALIASING, awt.RenderingHints.VALUE_ANTIALIAS_ON)
        except:
            pass
        w = self.getWidth()
        h = self.getHeight()


        # Update shared panel size for wrap estimation (read off the EDT).
        try:
            global _LAST_PANEL_W
            global _LAST_PANEL_H
            _LAST_PANEL_W = int(w)
            _LAST_PANEL_H = int(h)
        except:
            pass
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        pages = []
        viewLeft = -1
        if got:
            try:
                pages = list(getattr(self.Hub, 'Pages', []))
                viewLeft = int(getattr(self.Hub, 'ViewLeftPageIndex', -1))
            finally:
                try:
                    self.Hub.Lock.unlock()
                except:
                    pass
            # Cache snapshot to avoid flicker when tryLock fails
            try:
                self.CachedPages = pages
                self.CachedViewLeft = viewLeft
            except:
                pass
        else:
            # Use last known snapshot
            try:
                pages = list(getattr(self, 'CachedPages', []))
                viewLeft = int(getattr(self, 'CachedViewLeft', -1))
            except:
                pages = []
                viewLeft = -1

        try:
            g.setColor(BOOK_COVER_COLOR)
            g.fillRect(0, 0, w, h)
            g.setColor(BOOK_COVER_EDGE)
            g.drawRect(2, 2, w - 4, h - 4)
        except:
            pass

        if len(pages) <= 0:

            # Empty book: show the inside front cover (left) and a blank first page (right).

            viewLeft = 0


            spineW = 28

            outerPad = 6

            gutter = 10

            centerX = w // 2

            pageW = (w - spineW - gutter * 2) // 2

            pageH = h - outerPad * 2

            leftX = centerX - gutter - spineW // 2 - pageW

            rightX = centerX + gutter + spineW // 2

            pageY = outerPad


            try:

                g.setColor(BOOK_SPINE_COLOR)

                g.fillRect(centerX - spineW // 2, pageY, spineW, pageH)

            except:

                pass


            # Inside cover

            self._DrawCoverPage(g, leftX, pageY, pageW, pageH)


            # Blank first page

            try:

                _DrawPaperWithRules(g, rightX, pageY, pageW, pageH, self.PaperColor, self.RuleLineColor, self.MarginColor)

            except:

                pass

            return

        if viewLeft < 0:
            viewLeft = 0

        spineW = 28
        outerPad = 6
        gutter = 10
        centerX = w // 2
        pageW = (w - spineW - gutter * 2) // 2
        pageH = h - outerPad * 2
        leftX = centerX - gutter - spineW // 2 - pageW
        rightX = centerX + gutter + spineW // 2
        pageY = outerPad

        try:
            g.setColor(BOOK_SPINE_COLOR)
            g.fillRect(centerX - spineW // 2, pageY, spineW, pageH)
        except:
            pass

        # Spread mapping:
        # viewLeft == 0: inside front cover (left) + page 0 (right)
        # viewLeft >= 1: left page = 2*viewLeft - 1, right page = 2*viewLeft
        if int(viewLeft) <= 0:
            self._DrawCoverPage(g, leftX, pageY, pageW, pageH)
            self._DrawPage(g, pages, 0, rightX, pageY, pageW, pageH, isRight=True)
        else:
            li = int(viewLeft) * 2 - 1
            ri = int(viewLeft) * 2
            self._DrawPage(g, pages, li, leftX, pageY, pageW, pageH, isRight=False)
            self._DrawPage(g, pages, ri, rightX, pageY, pageW, pageH, isRight=True)
        if int(viewLeft) >= 1:
            _DrawFold(g, leftX, pageY + pageH - FOLD_PX, FOLD_PX, isRight=False)
        maxSpread = _GetMaxSpreadIndex(pages)
        if int(viewLeft) < int(maxSpread):
            _DrawFold(g, rightX + pageW - FOLD_PX, pageY + pageH - FOLD_PX, FOLD_PX, isRight=True)

    def _DrawCoverPage(self, g, x, y, w, h):
        try:
            g.setColor(BOOK_COVER_COLOR)
            g.fillRoundRect(int(x), int(y), int(w), int(h), 10, 10)
            g.setColor(BOOK_COVER_EDGE)
            g.drawRoundRect(int(x), int(y), int(w), int(h), 10, 10)
        except:
            pass

        try:
            bw = 140
            bh = 30
            bx = int(x + (int(w) - bw) // 2)
            by = int(y + int(h) - bh - 18)
            g.setColor(awt.Color(45, 64, 90))
            g.fillRoundRect(bx, by, bw, bh, 10, 10)
            g.setColor(awt.Color(230, 230, 230, 200))
            g.drawRoundRect(bx, by, bw, bh, 10, 10)
            g.setFont(awt.Font('SansSerif', awt.Font.BOLD, 12))
            s = 'New book'
            fm = g.getFontMetrics()
            g.drawString(s, bx + (bw - fm.stringWidth(s)) // 2, by + (bh + fm.getAscent()) // 2 - 2)
        except:
            pass



    def _DrawPage(self, g, pages, pageIndex, x, y, w, h, isRight):
        _DrawPaperWithRules(g, x, y, w, h, self.PaperColor, self.RuleLineColor, self.MarginColor)
        inner = 26
        outer = 30
        textX = int(x + (inner if isRight else outer) + MARGIN_LINE_X_PX)
        textX2 = int(x + w - (outer if isRight else inner))
        textW = max(10, textX2 - textX)
        textY = int(y + TOP_MARGIN_PX)
        textH = int(h - TOP_MARGIN_PX - BOTTOM_MARGIN_PX)
        pageRec = None
        if pageIndex >= 0 and pageIndex < len(pages):
            pageRec = pages[pageIndex]
        g.setFont(self.Font)
        g.setColor(self.InkColor)
        lines = _PageTextLinesForDisplay(pageRec)
        # Do not re-wrap dynamically during handwriting; the writer pre-wraps at word boundaries.
        wrapped = []
        for ln in lines:
            try:
                wrapped.append(str(ln))
            except:
                wrapped.append('')
        maxLines = max(1, int(textH // LINE_HEIGHT_PX))
        if len(wrapped) > maxLines:
            wrapped = wrapped[:maxLines]
        yy = int(textY + LINE_HEIGHT_PX - 6)
        prev = None
        for s in wrapped:
            st = str(s)
            if prev is None:
                # Day header line: keep a fixed centred starting point based on the FULL day name.
                isDay = False
                dayFull = None
                if st in _DAYS:
                    isDay = True
                    dayFull = st
                elif st != '':
                    try:
                        for d in _DAYS:
                            if d.startswith(st):
                                isDay = True
                                dayFull = d
                                break
                    except:
                        isDay = False
                        dayFull = None
                if isDay:
                    try:
                        fm = g.getFontMetrics(self.Font)
                        wday = fm.stringWidth(dayFull if dayFull is not None else st)
                        sx = int(textX + (textW - wday) // 2)
                        g.drawString(st, sx, yy)
                    except:
                        g.drawString(st, textX, yy)
                    prev = dayFull if dayFull is not None else st
                    yy += int(LINE_HEIGHT_PX)
                    continue
            if (prev in _DAYS or (prev is not None and prev != '' and any([d.startswith(prev) for d in _DAYS]))) and len(st) > 0 and set(st) == set('-'):
                try:
                    fm = g.getFontMetrics(self.Font)
                    wday = fm.stringWidth(prev)
                    sx = int(textX + (textW - wday) // 2)
                    g.drawLine(sx, yy - 6, sx + wday, yy - 6)
                except:
                    pass
                prev = None
                yy += int(LINE_HEIGHT_PX)
                continue
            try:
                g.drawString(st, textX, yy)
            except:
                pass
            prev = st
            yy += int(LINE_HEIGHT_PX)

    class _Wheel(event.MouseWheelListener):
        def mouseWheelMoved(self, e):
            try:
                hub = e.getComponent().Hub
                rot = e.getWheelRotation()
            except:
                return
            if rot < 0:
                _GoPrev(hub)
            elif rot > 0:
                _GoNext(hub)

    class _Click(event.MouseAdapter):
        def mouseClicked(self, e):
            try:
                hub = e.getComponent().Hub
                x = e.getX()
                y = e.getY()
                w = e.getComponent().getWidth()
                h = e.getComponent().getHeight()
                # New book button hit on inside front cover
                try:
                    viewSp = int(getattr(hub, 'ViewLeftPageIndex', -1))
                except:
                    viewSp = -1
                if viewSp < 0:
                    viewSp = 0
                if viewSp == 0:
                    rect = _GetCoverNewBookButtonRect(w, h)
                    if _HitRect(int(x), int(y), rect):
                        _NewBook(hub)
                        return
            except:
                return
            if x < FOLD_PX * 2 and y > h - FOLD_PX * 2:
                _GoPrev(hub)
            elif x > w - FOLD_PX * 2 and y > h - FOLD_PX * 2:
                _GoNext(hub)

    class _Keys(event.KeyAdapter):
        def keyPressed(self, e):
            try:
                hub = e.getComponent().Hub
                code = e.getKeyCode()
                if e.isControlDown() and code == event.KeyEvent.VK_N:
                    _NewBook(hub)
                    return

            except:
                return
            if code in (event.KeyEvent.VK_LEFT, event.KeyEvent.VK_UP, event.KeyEvent.VK_PAGE_UP):
                _GoPrev(hub)
            elif code in (event.KeyEvent.VK_RIGHT, event.KeyEvent.VK_DOWN, event.KeyEvent.VK_PAGE_DOWN):
                _GoNext(hub)

class BookFrame(swing.JFrame):
    def __init__(self, hub):
        swing.JFrame.__init__(self, 'Train status messages')
        self.Hub = hub
        self.IsClosed = False
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
        self.Layer = swing.JLayeredPane()
        self.Layer.setLayout(None)
        self.setContentPane(self.Layer)
        self.Panel = BookPanel(hub, self)
        self.Layer.add(self.Panel, swing.JLayeredPane.DEFAULT_LAYER)
        self.BtnNewBook = swing.JButton('New book')
        try:
            self.BtnNewBook.setVisible(False)
        except:
            pass
        try:
            self.BtnNewBook.setFocusPainted(False)
            self.BtnNewBook.setContentAreaFilled(False)
            self.BtnNewBook.setOpaque(False)
            self.BtnNewBook.setForeground(awt.Color(230, 230, 230))
            self.BtnNewBook.setBorder(swing.BorderFactory.createLineBorder(awt.Color(230, 230, 230, 160), 1))
            self.BtnNewBook.setContentAreaFilled(True)
            self.BtnNewBook.setOpaque(True)
            self.BtnNewBook.setBackground(awt.Color(45, 64, 90))

        except:
            pass
        self.Layer.add(self.BtnNewBook, swing.JLayeredPane.PALETTE_LAYER)
        self.BtnNewBook.addActionListener(lambda e: _NewBook(hub))
        self.addComponentListener(self._ResizeListener())
        self.addWindowListener(self._WindowCloser())
        self.WriteTimer = Timer(int(WRITE_TIMER_MS), self._OnTick)
        self.WriteTimer.setRepeats(True)
        self.WriteTimer.start()
        self.setVisible(True)
        self._LayoutChildren()
        try:
            self.Panel.requestFocusInWindow()
        except:
            pass

    def _LayoutChildren(self):
        try:
            w = self.getContentPane().getWidth()
            h = self.getContentPane().getHeight()
        except:
            try:
                w = self.Layer.getWidth()
                h = self.Layer.getHeight()
            except:
                w = FRAME_WIDTH
                h = FRAME_HEIGHT
        try:
            self.Panel.setBounds(0, 0, w, h)
        except:
            pass
        bw = 120
        bh = 26
        try:
            self.BtnNewBook.setBounds((w - bw) // 2, h - bh - 14, bw, bh)
        except:
            pass

    def OnHubChanged(self):
        if self.IsClosed:
            return
        try:
            self.Panel.repaint()
        except:
            pass

    def _OnTick(self, e=None):
        if self.IsClosed:
            return
        got = False
        try:
            got = self.Hub.Lock.tryLock()
        except:
            got = False
        if not got:
            try:
                self.Panel.repaint()
            except:
                pass
            return
        changed = False
        try:
            if self.Hub.WriteOwnerId is None:
                self.Hub.WriteOwnerId = id(self)
            if self.Hub.WriteOwnerId != id(self):
                return
            changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
            wr = self.Hub.Writer
            if wr is None:
                return
            text = wr.get('text', '')
            try:
                pos = int(wr.get('pos', 0))
            except:
                pos = 0
            if pos >= len(text):
                # Finalise the last in-progress line so the finished page uses the same wrapped layout.
                try:
                    curFinal = str(wr.get('currentLine', ''))
                except:
                    curFinal = ''
                if curFinal != '':
                    try:
                        wr['lines'].append(curFinal.rstrip())
                    except:
                        pass
                    wr['currentLine'] = ''
                wr['done'] = True
                self.Hub.Writer = None
                changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
                return
            # Handwriting word-wrapping: decide line breaks BEFORE starting a word so existing letters never move.
            # Also avoid writing a trailing space at the end of a line; use a newline instead.
            try:
                tw, _ml = _ComputeTextWFromPanel(self.Panel.getWidth(), self.Panel.getHeight())
            except:
                tw, _ml = _ComputeTextWFromPanel(FRAME_WIDTH, FRAME_HEIGHT)
            try:
                fm = self.Panel.getFontMetrics(self.Panel.Font)
            except:
                fm = None
            
            def _Width(s):
                try:
                    return fm.stringWidth(s)
                except:
                    try:
                        return len(s) * 8
                    except:
                        return 0
            
            for _i in range(int(WRITE_CHARS_PER_TICK)):
                if pos >= len(text):
                    break
                ch = text[pos]
                if ch == '\r':
                    pos += 1
                    wr['pos'] = pos
                    continue
                if ch == '\n':
                    pos += 1
                    wr['pos'] = pos
                    try:
                        wr['lines'].append(str(wr.get('currentLine', '')).rstrip())
                    except:
                        pass
                    wr['currentLine'] = ''
                    continue
                cur = str(wr.get('currentLine', ''))
                if ch == ' ':
                    nxt = _PeekNextWord(text, pos + 1)
                    if cur != '' and nxt != '' and _Width(cur + ' ' + nxt) > int(tw):
                        try:
                            wr['lines'].append(cur.rstrip())
                        except:
                            pass
                        wr['currentLine'] = ''
                        pos += 1
                        wr['pos'] = pos
                        continue
                    if cur == '':
                        pos += 1
                        wr['pos'] = pos
                        continue
                    if _Width(cur + ' ') > int(tw):
                        try:
                            wr['lines'].append(cur.rstrip())
                        except:
                            pass
                        wr['currentLine'] = ''
                        pos += 1
                        wr['pos'] = pos
                        continue
                    wr['currentLine'] = cur + ' '
                    pos += 1
                    wr['pos'] = pos
                    continue
                if cur != '' and cur.endswith(' '):
                    w = _PeekNextWord(text, pos)
                    if w != '' and _Width(cur + w) > int(tw):
                        try:
                            wr['lines'].append(cur.rstrip())
                        except:
                            pass
                        wr['currentLine'] = ''
                        continue
                if cur != '' and _Width(cur + str(ch)) > int(tw):
                    try:
                        wr['lines'].append(cur.rstrip())
                    except:
                        pass
                    wr['currentLine'] = ''
                    continue
                wr['currentLine'] = cur + str(ch)
                pos += 1
                wr['pos'] = pos
            if pos >= len(text):
                # Finalise the last in-progress line so the finished page uses the same wrapped layout.
                try:
                    curFinal = str(wr.get('currentLine', ''))
                except:
                    curFinal = ''
                if curFinal != '':
                    try:
                        wr['lines'].append(curFinal.rstrip())
                    except:
                        pass
                    wr['currentLine'] = ''
                wr['done'] = True
                self.Hub.Writer = None
                changed = _StartNextPendingIfIdleLocked(self.Hub) or changed
            _ClampViewLeftIndex(self.Hub)
        finally:
            try:
                self.Hub.Lock.unlock()
            except:
                pass
        if changed:
            self.OnHubChanged()
        else:
            try:
                self.Panel.repaint()
            except:
                pass

    class _ResizeListener(event.ComponentAdapter):
        def componentResized(self, e):
            try:
                e.getComponent()._LayoutChildren()
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
            self.Hub.Lock.lock()
            try:
                if self.Hub.WriteOwnerId == id(self):
                    self.Hub.WriteOwnerId = None
            finally:
                self.Hub.Lock.unlock()
        except:
            pass
        try:
            if self in self.Hub.Windows:
                self.Hub.Windows.remove(self)
        except:
            pass
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
    win = BookFrame(hub)
    try:
        hub.Windows.append(win)
    except:
        pass


if SwingUtilities.isEventDispatchThread():
    _OpenWindow()
else:
    SwingUtilities.invokeLater(RunnableAdapter(_OpenWindow))
