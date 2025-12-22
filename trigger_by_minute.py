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
# This needs to be a STARTUP SCRIPT
#
# Trigger an external script whenever the simulated clock minute changes.
# Better design: use a Memory property-change listener (no polling loop).
#
# Configuration (optional):
# - Memory MINUTETRIGGERSCRIPT: script name or relative path under profile:jython
#   Default: adjust_lighting_by_time.py
#
# Notes:
# - Uses TASBeanLookup ProvideMemoryBySuffix so internal prefixes are handled.
# - Avoids absolute paths by using FileUtil.getExternalFilename("profile:jython/<script>").
# - Parses both 12h and 24h formats and normalises to minutes since midnight.

import jmri
import os
import traceback
import TASBeanLookup as TBL

from java.text import SimpleDateFormat
from java.util.concurrent.locks import ReentrantLock
from java.lang import Thread, Exception as JavaException
from java.beans import PropertyChangeListener


# ---------------- Time parsing helpers ----------------

_TimeParsers = [
    SimpleDateFormat("h:mm a"),
    SimpleDateFormat("h:mm:ss a"),
    SimpleDateFormat("H:mm"),
    SimpleDateFormat("H:mm:ss"),
]

def _NormaliseTimeString(s):
    # Returns a cleaned string suitable for parsing, ASCII only.
    if s is None:
        return ""
    try:
        t = str(s)
    except Exception:
        return ""
    t = t.strip()
    if t == "":
        return ""

    # Collapse whitespace
    t = " ".join(t.split())

    # Handle missing space before AM/PM, e.g. "9:19PM"
    up = t.upper()
    if (up.endswith("AM") or up.endswith("PM")) and len(t) >= 4:
        if len(t) >= 3 and t[-3] != " ":
            t = t[:-2] + " " + t[-2:]

    return t

def _ParseTimeToMinutes(s):
    # Returns minutes since midnight, or None on parse failure.
    t = _NormaliseTimeString(s)
    if t == "":
        return None

    for p in _TimeParsers:
        try:
            d = p.parse(t)
            # java.util.Date.getHours/getMinutes exist and are used elsewhere in TAS
            return int(d.getHours()) * 60 + int(d.getMinutes())
        except:
            # Any parse failure (Java or Python): try the next format
            pass

    # Last-resort manual parse for "HH:MM" or "H:MM"
    try:
        parts = t.split(" ")
        hm = parts[0]
        fields = hm.split(":")
        if len(fields) >= 2:
            hh = int(fields[0])
            mm = int(fields[1])
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return hh * 60 + mm
    except Exception:
        pass

    return None


# ---------------- Script path resolution ----------------

def _ResolveProfileJythonScriptPath(scriptRel):
    # scriptRel is a filename or relative path under profile:jython
    if scriptRel is None:
        return None
    s = str(scriptRel).strip()
    if s == "":
        return None

    # Reject absolute paths (drive letters or leading slash/backslash)
    # This keeps the script portable and profile-relative.
    if ":" in s:
        # Covers "C:\..." and also other URI-like forms
        return None
    if s.startswith("/") or s.startswith("\\"):
        return None

    # Normalise separators
    s = s.replace("\\", "/")

    # Ensure .py suffix
    if not s.lower().endswith(".py"):
        s = s + ".py"

    # Resolve to external filename under the active profile
    try:
        fullPath = jmri.util.FileUtil.getExternalFilename("profile:jython/" + s)
        return fullPath
    except Exception:
        return None


# ---------------- Core trigger class ----------------

class MinuteTrigger(object):
    def __init__(self):
        self._Lock = ReentrantLock()

        self._TimeMem = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
        self._ScriptMem = TBL.ProvideMemoryBySuffix("MINUTETRIGGERSCRIPT", "adjust_lighting_by_time.py")

        self._LastMinute = None
        self._PendingMinute = None
        self._RunnerActive = False

        self._Listener = None

    def _GetScriptPath(self):
        try:
            v = self._ScriptMem.getValue() if self._ScriptMem is not None else None
        except Exception:
            v = None
        if v is None or str(v).strip() == "":
            v = "adjust_lighting_by_time.py"

        path = _ResolveProfileJythonScriptPath(v)
        return path

    def _RunTargetScript(self):
        # Run the configured script once (best effort).
        path = self._GetScriptPath()
        if path is None:
            print("[FastClockTrigger] ERROR: Script path invalid. Set MINUTETRIGGERSCRIPT to a profile-relative .py name.")
            return
        if not os.path.isfile(path):
            print("[FastClockTrigger] ERROR: Script not found: " + str(path))
            return

        try:
            # Use fresh globals to avoid leaking names.
            g = {"__name__": "__main__", "jmri": jmri}
            execfile(path, g)
        except Exception:
            print("[FastClockTrigger] ERROR running script: " + str(path))
            traceback.print_exc()

    def _RunnerLoop(self):
        # Coalesce multiple minute changes: always run the latest pending minute once.
        while True:
            minuteToRun = None

            self._Lock.lock()
            try:
                if self._PendingMinute is None:
                    self._RunnerActive = False
                    return
                minuteToRun = self._PendingMinute
                self._PendingMinute = None
            finally:
                self._Lock.unlock()

            # Execute outside the lock
            print("[FastClockTrigger] Minute changed to %d. Running script..." % int(minuteToRun))
            self._RunTargetScript()

    def _EnsureRunner(self):
        # Start runner thread if not already running
        start = False
        self._Lock.lock()
        try:
            if not self._RunnerActive:
                self._RunnerActive = True
                start = True
        finally:
            self._Lock.unlock()

        if start:
            try:
                t = Thread(self._RunnerLoop)
                t.setDaemon(True)
                t.start()
            except Exception:
                # If we cannot start a thread, fail safe by clearing runner flag
                self._Lock.lock()
                try:
                    self._RunnerActive = False
                finally:
                    self._Lock.unlock()

    def _MaybeTrigger(self):
        # Read time, parse to minutes, trigger if changed.
        if self._TimeMem is None:
            return
        try:
            cur = self._TimeMem.getValue()
        except Exception:
            cur = None

        m = _ParseTimeToMinutes(cur)
        if m is None:
            return

        self._Lock.lock()
        try:
            if self._LastMinute is None:
                # Baseline on first observed value; do not trigger immediately at startup.
                self._LastMinute = m
                return

            if m != self._LastMinute:
                self._LastMinute = m
                self._PendingMinute = m
        finally:
            self._Lock.unlock()

        # If we set a pending minute, ensure runner is active
        self._EnsureRunner()

    def Start(self):
        if self._TimeMem is None:
            print("[FastClockTrigger] ERROR: CURRENTTIME memory not available.")
            return

        outer = self

        class _MemListener(PropertyChangeListener):
            def propertyChange(self, ev):
                # Any change to the memory value can be treated as a potential minute tick.
                try:
                    outer._MaybeTrigger()
                except Exception:
                    # Listener must never crash JMRI
                    pass

        self._Listener = _MemListener()
        try:
            self._TimeMem.addPropertyChangeListener(self._Listener)
        except Exception:
            print("[FastClockTrigger] ERROR: Could not attach property change listener to CURRENTTIME.")
            return

        # Establish baseline immediately
        try:
            self._MaybeTrigger()
        except Exception:
            pass

        print("[FastClockTrigger] Listener attached. Monitoring CURRENTTIME for minute changes.")


# ---------------- Start (startup script) ----------------

# Prevent accidental double-install if the script is run twice
try:
    if "_MinuteTriggerInstance" in globals() and globals()["_MinuteTriggerInstance"] is not None:
        print("[FastClockTrigger] Already running (instance exists).")
    else:
        _MinuteTriggerInstance = MinuteTrigger()
        _MinuteTriggerInstance.Start()
except Exception:
    traceback.print_exc()

