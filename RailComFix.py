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
# RailComFix.py
# Optional startup script. Enabled automatically when at least one roster entry is
# ticked for the fix in TASSetup.py Train detection tab, and removed again when none
# are. Applies the RailCom initialisation fix: for each roster entry marked for the
# fix, a brief function-off command is sent to that entry's DCC address, so the decoder
# is addressed by the command station and then broadcasts on RailCom. The throttle is
# released straight afterwards and no speed setting is touched.
#
# Which entries get the fix, and which function is sent to each, are held in
# profile:jython/config/railcomfix.tsv and edited in TASSetup.py. Entry selection and
# RailCom capability are decided by RailComDetect.py, which also runs the fix.
#
# The script also runs when started manually through Scripting, Run script, so the fix
# can be applied without restarting JMRI.
#
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.
#
# NAMING RULE FOR THIS FILE
# JMRI runs every start-up script through one shared JSR-223 script context, so
# top-level names in this file land in the same map as the names in every other
# start-up script. A name defined here that another start-up script also defines
# is overwritten, and functions in this file resolve that name at call time, so
# the other script's object would be used here. Every top-level name in this
# file therefore starts with RAILCOMFIX_ or _RailComFix, and objects used by
# functions are bound as default arguments so no later script can redirect them.

import jmri
from java.lang import Runnable, Thread
import RailComDetect as RCD


def _RailComFixLog(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


def _RailComFixCollect(_detect=RCD):
    # Roster entries the fix applies to, as (address, longAddress, function, rosterId).
    targets = []
    for rec in _detect.FixEntries(_detect.ScanRoster()):
        try:
            targets.append((int(str(rec.address).strip()), bool(rec.longAddress),
                            int(rec.function), str(rec.rosterId)))
        except Exception:
            continue
    return targets


class _RailComFixWorker(jmri.jmrit.automat.AbstractAutomaton):
    # Sends the function-off command to each address in turn. Kept here so this file
    # reads alone; the same worker lives in RailComDetect for setup's immediate runs.
    def __init__(self, targets):
        jmri.jmrit.automat.AbstractAutomaton.__init__(self)
        self._targets = list(targets)

    def init(self):
        pass

    def handle(self):
        for (address, longAddress, function, rosterId) in list(self._targets):
            throttle = None
            try:
                throttle = self.getThrottle(int(address), bool(longAddress))
            except Exception as ex:
                _RailComFixLog("RailCom fix: no throttle for " + rosterId + " (address " +
                               str(address) + "): " + str(ex))
                continue
            if throttle is None:
                _RailComFixLog("RailCom fix: no throttle acquired for " + rosterId +
                               " (address " + str(address) + ")")
                continue
            try:
                throttle.setFunction(int(function), False)
                _RailComFixLog("RailCom fix: sent F" + str(int(function)) + " off to " +
                               rosterId + " (address " + str(address) + ")")
            except Exception as ex:
                _RailComFixLog("RailCom fix: command failed for " + rosterId + ": " + str(ex))
            try:
                throttle.release(None)
            except Exception as ex:
                _RailComFixLog("RailCom fix: could not release the throttle for " +
                               rosterId + ": " + str(ex))
        return False


def _RailComFixApply(_detect=RCD, _log=_RailComFixLog):
    # Applies the fix now, on a worker thread, and returns the number of entries used.
    targets = []
    try:
        targets = _RailComFixCollect(_detect)
    except Exception as ex:
        _log("RailCom fix: could not read the roster: " + str(ex))
        return 0
    return _detect.ApplyFixTargets(targets)


class _RailComFixTask(Runnable):
    def run(self):
        try:
            _RailComFixApply()
        except Exception as ex:
            _RailComFixLog("RailCom fix could not be applied: " + str(ex))


def _RailComFixStart():
    # Run on a background thread so the JMRI start-up action list is not held up.
    th = Thread(_RailComFixTask())
    th.setDaemon(True)
    th.start()


try:
    _RailComFixStart()
except Exception as ex:
    try:
        print("[TAS] RailCom fix could not start: " + str(ex))
    except Exception:
        pass
