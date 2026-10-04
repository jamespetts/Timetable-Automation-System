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
import java
import jmri
# TAS_SYS_PATH_SNIPPET: make the TAS folder importable even when scripts: still points elsewhere.
try:
    import os as _tas_os_path
    import sys as _tas_sys_path
    _tas_script_dir = None
    try:
        import jmri as _tas_jmri_path
        _tas_script_dir = _tas_jmri_path.util.FileUtil.getExternalFilename('profile:jython/TAS')
    except Exception:
        _tas_script_dir = None
    if _tas_script_dir and _tas_script_dir not in _tas_sys_path.path:
        _tas_sys_path.path.insert(0, _tas_script_dir)
except Exception:
    pass
import TASBeanLookup as TBL

# Keep the time warp disabled for this long after this script starts. Input
# hardware that powers up with the layout can report an input as active while
# it settles, and that must not warp the clock during JMRI start-up.
TIMEWARPCHECKER_STARTUP_GRACE_MS = 10000

# Define the task
class CheckActiveTrains(java.util.TimerTask):
    def __init__(self, startMs, graceMs):
        java.util.TimerTask.__init__(self)
        self.startMs = long(startMs)
        self.graceMs = long(graceMs)

    def run(self):
        try:
            allowMem = TBL.ProvideMemoryBySuffix("ALLOWTIMEWARP", "false")

            # Disable the time warp while JMRI starts up, so an input that
            # reports active as it powers up cannot warp the clock. This is
            # done before the Dispatcher lookup so it works even when the
            # Dispatcher is not ready yet.
            if (java.lang.System.currentTimeMillis() - self.startMs) < self.graceMs:
                allowMem.setValue("False")
                return

            df = jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame)

            allow = False
            if df is not None:
                trains = df.getActiveTrainsList()
                size = trains.size()
                if size == 0:
                    allow = True
                else:
                    # Allow if every train is WAITING for a CLOCK start
                    allWaitingClock = True
                    for i in range(size):
                        at = trains.get(i)
                        if at is None:
                            continue

                        waiting = (at.getStatus() == jmri.jmrit.dispatcher.ActiveTrain.WAITING)

                        # CHANGED: Relaxed - do not require notStarted or zero allocations
                        # notStarted = (not at.getStarted())
                        # allocList = at.getAllocatedSectionList()
                        # noAlloc = (allocList is None) or (allocList.size() == 0)

                        hr = int(at.getDepartureTimeHr())
                        mn = int(at.getDepartureTimeMin())
                        hasClockDepart = (0 <= hr <= 23) and (0 <= mn <= 59)
                        isTimedDelay = (at.getDelayedStart() == jmri.jmrit.dispatcher.ActiveTrain.TIMEDDELAY)

                        # CHANGED: Now only require WAITING and a clock-based hold
                        if not (waiting and (hasClockDepart or isTimedDelay)):
                            allWaitingClock = False
                            break

                    allow = allWaitingClock

            allowMem.setValue("True" if allow else "False")
        except Exception as e:
            print("TimeWarpChecker error: {}".format(e))

# Create and start the timer
timer = java.util.Timer()
timer.schedule(CheckActiveTrains(java.lang.System.currentTimeMillis(),
                                 TIMEWARPCHECKER_STARTUP_GRACE_MS), 0, 1000)  # 0 = initial delay, 1000 = repeat every 1,000ms