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
# DccPowerOnStart.py
# Optional startup script. Disabled by default; enable in TASSetup.py General tab.
# Makes sure DCC track power is on when the layout starts.
# Power that is already on is left alone, so there is no interruption to power.
# An unknown power state is never changed. The script waits for the state to
# become known and then acts. If the state is still unknown it shows a warning
# window and leaves the power alone.
# The script also disables any enabled JMRI Start-Up entry that runs PowerOn.py,
# which turns track power on unconditionally, so that track power is turned on in
# one place only. That change takes effect at the next start of JMRI.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe. No Swing work off the EDT.
#
# NAMING RULE FOR THIS FILE
# JMRI runs every start-up script through one shared JSR-223 script context, so
# top-level names in this file land in the same map as the names in every other
# start-up script. A name defined here that another start-up script also defines
# is overwritten, and functions in this file resolve that name at call time, so
# the other script's object would be used here. Every top-level name in this
# file therefore starts with DCCPOWER_ or _DccPower, and the warning window is
# also bound as a default argument so no later script can redirect it.

import jmri
from java.io import File
from java.lang import Runnable, System, Thread
from java.awt import Color
import TASWarningWindow

# How long to wait for a hardware connection to publish a power manager.
DCCPOWER_MANAGER_WAIT_SECONDS = 30
# How long to wait for the power state to stop being unknown.
DCCPOWER_STATE_WAIT_SECONDS = 15
# Gap between state readings.
DCCPOWER_POLL_MSEC = 500

# Name of the script JMRI ships for turning track power on.
DCCPOWER_BUILTIN_SCRIPT = "PowerOn.py"

DCCPOWER_UNKNOWN_KEY = "dccpower-state-unknown"
DCCPOWER_NO_MANAGER_KEY = "dccpower-no-manager"
DCCPOWER_SET_FAILED_KEY = "dccpower-set-failed"

DCCPOWER_UNKNOWN_TEXT = ("The DCC power state is not known, so the power was left unchanged. "
                         "Check the command station connection and the track power control.")
DCCPOWER_NO_MANAGER_TEXT = ("No JMRI power manager was found. Check that a hardware connection "
                            "is configured in Preferences.")
DCCPOWER_SET_FAILED_TEXT = "Could not turn DCC power on: "

# One warning window for this feature. Orange triangle, black message area.
# See TASWarningWindow.py.
_DccPowerWindow = TASWarningWindow.TasWarningWindow({
    "title": "DCC power warning",
    "textWidth": 400,
    "textHeight": 170,
    "frameWidth": 440,
    "frameBaseHeight": 300,
    "frameGrowPerMessage": 46,
    "frameMaxHeight": 560,
    "fontSize": 12,
    "nameFontSize": 13,
    "background": Color(0, 0, 0),
    "backgroundHex": "000000",
    "textColour": Color(222, 222, 222),
    "textHex": "dedede",
    "nameHex": "ffa64d",
    "symbolFill": Color(230, 126, 34),
    "symbolEdge": Color(140, 74, 0),
    "markColour": Color(255, 255, 255),
    "flashColour": Color(255, 255, 255),
    "flashPixels": 700,
})


def _DccPowerLog(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


def _DccPowerStateName(state):
    try:
        if state == jmri.PowerManager.UNKNOWN:
            return "unknown"
        if state == jmri.PowerManager.ON:
            return "on"
        if state == jmri.PowerManager.OFF:
            return "off"
        if state == jmri.PowerManager.IDLE:
            return "idle"
    except Exception:
        pass
    return str(state)


def _DccPowerGetManager():
    # getDefault throws NullPointerException when no connection has published a
    # power manager, so use the nullable form.
    try:
        return jmri.InstanceManager.getNullableDefault(jmri.PowerManager)
    except Exception as ex:
        _DccPowerLog("Power manager lookup failed: " + str(ex))
        return None


def _DccPowerReadState(pm):
    try:
        return int(pm.getPower())
    except Exception as ex:
        _DccPowerLog("Could not read the DCC power state: " + str(ex))
        return jmri.PowerManager.UNKNOWN


def _DccPowerWaitForManager():
    deadline = System.currentTimeMillis() + long(DCCPOWER_MANAGER_WAIT_SECONDS * 1000)
    while True:
        pm = _DccPowerGetManager()
        if pm is not None:
            return pm
        if System.currentTimeMillis() >= deadline:
            return None
        Thread.sleep(DCCPOWER_POLL_MSEC)


def _DccPowerWaitForKnownState(pm):
    deadline = System.currentTimeMillis() + long(DCCPOWER_STATE_WAIT_SECONDS * 1000)
    state = _DccPowerReadState(pm)
    while state == jmri.PowerManager.UNKNOWN:
        if System.currentTimeMillis() >= deadline:
            return state
        Thread.sleep(DCCPOWER_POLL_MSEC)
        state = _DccPowerReadState(pm)
    return state


def _DccPowerApply(_window=_DccPowerWindow):
    pm = _DccPowerWaitForManager()
    if pm is None:
        _DccPowerLog("No JMRI power manager was found within " + str(DCCPOWER_MANAGER_WAIT_SECONDS) + " seconds")
        _window.AddNotice(DCCPOWER_NO_MANAGER_KEY, DCCPOWER_NO_MANAGER_TEXT)
        return
    if _DccPowerReadState(pm) == jmri.PowerManager.UNKNOWN:
        _DccPowerLog("DCC power state is not known yet; waiting up to " +
                     str(DCCPOWER_STATE_WAIT_SECONDS) + " seconds")
    state = _DccPowerWaitForKnownState(pm)
    if state == jmri.PowerManager.UNKNOWN:
        _DccPowerLog("DCC power state is still not known; the power was left unchanged")
        _window.AddNotice(DCCPOWER_UNKNOWN_KEY, DCCPOWER_UNKNOWN_TEXT)
        return
    if state == jmri.PowerManager.ON:
        _DccPowerLog("DCC power is already on; left unchanged")
        return
    _DccPowerLog("DCC power is " + _DccPowerStateName(state) + "; turning it on")
    try:
        pm.setPower(jmri.PowerManager.ON)
        _DccPowerLog("DCC power turned on")
    except Exception as ex:
        _DccPowerLog(DCCPOWER_SET_FAILED_TEXT + str(ex))
        _window.AddNotice(DCCPOWER_SET_FAILED_KEY, DCCPOWER_SET_FAILED_TEXT + str(ex))


# ------------------ JMRI built-in PowerOn.py Start-Up entry ------------------

def _DccPowerActiveProfile():
    try:
        profMgr = jmri.profile.ProfileManager.getDefault()
        if profMgr is None:
            return None
        return profMgr.getActiveProfile()
    except Exception:
        return None


def _DccPowerDisableBuiltinScript():
    # Disable any enabled Start-Up entry that runs JMRI's PowerOn.py, which turns
    # power on unconditionally. Start-Up actions belong to the active profile, so
    # this affects the current layout only. Every path disabled is logged so that
    # the change can be reversed in Edit, Preferences, Start Up.
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
        if mgr is None:
            return
        actions = mgr.getActions()
    except Exception as ex:
        _DccPowerLog("Could not read the Start-Up actions: " + str(ex))
        return
    disabled = []
    for m in actions:
        try:
            if not isinstance(m, jmri.util.startup.PerformScriptModel):
                continue
            if not m.isEnabled():
                continue
            path = m.getFileName()
            if path is None:
                continue
            if File(str(path)).getName().lower() != DCCPOWER_BUILTIN_SCRIPT.lower():
                continue
            m.setEnabled(False)
            disabled.append(str(path))
        except Exception:
            continue
    if not disabled:
        return
    try:
        prof = _DccPowerActiveProfile()
        if prof is not None:
            mgr.savePreferences(prof)
    except Exception as ex:
        _DccPowerLog("Could not save the Start-Up preferences: " + str(ex))
        return
    _DccPowerLog("Disabled " + str(len(disabled)) + " unconditional " + DCCPOWER_BUILTIN_SCRIPT +
                 " Start-Up entry/entries: " + ", ".join(disabled))
    _DccPowerLog("Track power will be turned on by DccPowerOnStart.py from the next start of JMRI")


# ------------------ Entry point ------------------

class _DccPowerTask(Runnable):
    def run(self):
        try:
            _DccPowerApply()
        except Exception as ex:
            _DccPowerLog("Could not set DCC power at start-up: " + str(ex))
        try:
            _DccPowerDisableBuiltinScript()
        except Exception as ex:
            _DccPowerLog("Could not disable the built-in " + DCCPOWER_BUILTIN_SCRIPT +
                         " Start-Up entry: " + str(ex))


def _DccPowerStart():
    # Run on a background thread so the JMRI start-up action list is not held up.
    th = Thread(_DccPowerTask())
    th.setDaemon(True)
    th.start()


try:
    _DccPowerStart()
except Exception as ex:
    try:
        print("[TAS] DCC power on start failed to run: " + str(ex))
    except Exception:
        pass
