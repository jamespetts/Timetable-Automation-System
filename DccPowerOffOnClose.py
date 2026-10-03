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
# DccPowerOffOnClose.py
# Optional startup script. Disabled by default; enable in TASSetup.py General tab.
# Turns DCC track power off when JMRI shuts down, so the next start of JMRI
# begins with a real power cycle and occupancy sensors re-report their states.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe.
#
# NAMING RULE FOR THIS FILE
# JMRI runs every start-up script through one shared JSR-223 script context, so
# top-level names in this file land in the same map as the names in every other
# start-up script. Every top-level name in this file therefore starts with
# DCCPOWEROFF_ or _DccPowerOff.

import jmri
from java.lang import Runnable, System, Thread

# How long to wait for a hardware connection to publish a power manager.
DCCPOWEROFF_MANAGER_WAIT_SECONDS = 10
DCCPOWEROFF_POLL_MSEC = 250


def _DccPowerOffLog(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


class _DccPowerOffTask(Runnable):
    def run(self):
        try:
            deadline = System.currentTimeMillis() + long(DCCPOWEROFF_MANAGER_WAIT_SECONDS * 1000)
            pm = None
            while True:
                try:
                    pm = jmri.InstanceManager.getNullableDefault(jmri.PowerManager)
                except Exception:
                    pm = None
                if pm is not None:
                    break
                if System.currentTimeMillis() >= deadline:
                    break
                Thread.sleep(DCCPOWEROFF_POLL_MSEC)
            if pm is None:
                _DccPowerOffLog("No JMRI power manager was found; power left unchanged on close-down")
                return
            try:
                pm.setPower(jmri.PowerManager.OFF)
                _DccPowerOffLog("DCC power turned off at close-down")
            except Exception as ex:
                _DccPowerOffLog("Could not turn DCC power off at close-down: " + str(ex))
        except Exception as ex:
            _DccPowerOffLog("DCC power off at close-down failed: " + str(ex))


class DccPowerOffShutdownTask(jmri.implementation.AbstractShutDownTask):
    def run(self):
        try:
            _DccPowerOffTask().run()
        except Exception as ex:
            _DccPowerOffLog("DCC power off at close-down failed: " + str(ex))
        return True


def _DccPowerOffRegister():
    try:
        sdm = jmri.InstanceManager.getDefault(jmri.ShutDownManager)
        if sdm is None:
            _DccPowerOffLog("Could not register shutdown task: ShutDownManager unavailable")
            return
        sdm.register(DccPowerOffShutdownTask('DccPowerOffOnClose'))
        _DccPowerOffLog("Registered DCC power off shutdown task")
    except Exception as ex:
        _DccPowerOffLog("Could not register shutdown task: " + str(ex))


try:
    _DccPowerOffRegister()
except Exception as ex:
    try:
        print("[TAS] DccPowerOffOnClose failed to run: " + str(ex))
    except Exception:
        pass
