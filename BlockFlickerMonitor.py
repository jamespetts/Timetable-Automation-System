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
# BlockFlickerMonitor.py
# Optional startup script. Disabled by default; enable in TASSetup.py General tab.
# Monitors Block occupancy state and shows one non-modal warning window when a
# Block shows a double flicker: occupied-unoccupied-occupied, or
# unoccupied-occupied-unoccupied, within a short time span.
# The window is shown even when Dispatcher reports no error. All flicker
# messages accumulate in the same window, one per line; no second window is
# opened while the first window is open. A repeated flicker for the same Block
# does not add a second message; the existing message flashes instead.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.
#
# NAMING RULE FOR THIS FILE
# JMRI runs every start-up script through one shared JSR-223 script context, so
# top-level names in this file land in the same map as the names in every other
# start-up script. A name defined here that another start-up script also defines
# is overwritten, and functions in this file resolve that name at call time, so
# the other script's object would be used here. Every top-level name in this
# file therefore starts with FLICKER_ or _Flicker, and the warning window is
# also bound as a default argument so no later script can redirect it.

import jmri
import threading
from java.awt import Color
from java.lang import System
import TASWarningWindow

# Maximum time from the first to the third state of a double flicker,
# in milliseconds.
FLICKER_GAP_MS = 3000

# Window geometry. Width is fixed so that wrapped text keeps a stable width.
FLICKER_FRAME_WIDTH = 440
FLICKER_FRAME_BASE_HEIGHT = 300
FLICKER_FRAME_GROW_PER_MESSAGE = 46
FLICKER_FRAME_MAX_HEIGHT = 560
FLICKER_TEXT_WIDTH = 400
FLICKER_TEXT_HEIGHT = 170
FLICKER_FLASH_PIXELS = 700
FLICKER_FONT_SIZE = 12
FLICKER_NAME_FONT_SIZE = 13
FLICKER_TEXT_LIGHT = Color(222, 222, 222)
FLICKER_BACKGROUND = Color(0, 0, 0)
FLICKER_SYMBOL_FILL = Color(198, 40, 40)
FLICKER_SYMBOL_EDGE = Color(122, 0, 0)
FLICKER_SYMBOL_MARK = Color(255, 255, 255)

FLICKER_MESSAGE_LEAD = "Flickering occupancy sensor detected at: "
FLICKER_MESSAGE_TAIL = ": check for dirty track or loose wiring"
FLICKER_NOTICE_TEXT = "No occupancy sensor flickering recorded this session."
FLICKER_NOTICE_KEY = "flicker-notice"

# One warning window for this feature. Red triangle. See TASWarningWindow.py.
_FlickerWindow = TASWarningWindow.TasWarningWindow({
    "title": "Occupancy sensor warning",
    "textWidth": FLICKER_TEXT_WIDTH,
    "textHeight": FLICKER_TEXT_HEIGHT,
    "frameWidth": FLICKER_FRAME_WIDTH,
    "frameBaseHeight": FLICKER_FRAME_BASE_HEIGHT,
    "frameGrowPerMessage": FLICKER_FRAME_GROW_PER_MESSAGE,
    "frameMaxHeight": FLICKER_FRAME_MAX_HEIGHT,
    "fontSize": FLICKER_FONT_SIZE,
    "nameFontSize": FLICKER_NAME_FONT_SIZE,
    "background": FLICKER_BACKGROUND,
    "backgroundHex": "000000",
    "textColour": FLICKER_TEXT_LIGHT,
    "textHex": "dedede",
    "nameHex": "ff4040",
    "symbolFill": FLICKER_SYMBOL_FILL,
    "symbolEdge": FLICKER_SYMBOL_EDGE,
    "markColour": FLICKER_SYMBOL_MARK,
    "flashColour": Color(255, 255, 255),
    "flashPixels": FLICKER_FLASH_PIXELS,
})

_FlickerLock = threading.RLock()
_FlickerStarted = False
_FlickerListeners = []
_FlickerStateChanges = {}


def _FlickerLog(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


def _FlickerBlockLabel(block):
    try:
        usr = block.getUserName()
        if usr is not None and str(usr).strip() != "":
            return str(usr).strip()
    except Exception:
        pass
    try:
        return str(block.getSystemName())
    except Exception:
        pass
    try:
        return str(block)
    except Exception:
        return "unknown block"


def _FlickerSensorLabel(block):
    try:
        s = block.getSensor()
        if s is None:
            return None
        try:
            return str(s.getSystemName())
        except Exception:
            pass
        try:
            return str(s.getDisplayName())
        except Exception:
            pass
        return str(s)
    except Exception:
        return None


def _FlickerShowNotice(_window=_FlickerWindow):
    _window.AddNotice(FLICKER_NOTICE_KEY, FLICKER_NOTICE_TEXT)


def _FlickerAppendMessage(key, name, _window=_FlickerWindow):
    try:
        _window.AddMessage(key, name, FLICKER_MESSAGE_LEAD, FLICKER_MESSAGE_TAIL)
    except Exception as ex:
        _FlickerLog("Block flicker window update failed: " + str(ex))


def _FlickerReport(block):
    name = _FlickerBlockLabel(block)
    sensor = _FlickerSensorLabel(block)
    try:
        key = str(block.getSystemName())
    except Exception:
        key = str(name)
    if sensor is not None and sensor != name:
        consoleName = str(name) + " (sensor " + str(sensor) + ")"
    else:
        consoleName = str(name)
    _FlickerLog("Flickering occupancy sensor at " + consoleName)
    # AddMessage already marshals to the Event Dispatch Thread.
    _FlickerAppendMessage(key, name)


class _FlickerBlockListener(java.beans.PropertyChangeListener):
    def __init__(self, block):
        self.block = block

    def propertyChange(self, ev):
        try:
            try:
                pname = ev.getPropertyName()
            except Exception:
                return
            if pname != "state":
                try:
                    if pname != jmri.Block.PROPERTY_STATE:
                        return
                except Exception:
                    return
            try:
                newState = int(ev.getNewValue())
            except Exception:
                return
            now = System.currentTimeMillis()
            try:
                key = str(self.block.getSystemName())
            except Exception:
                key = str(self.block)
            report = False
            try:
                with _FlickerLock:
                    hist = _FlickerStateChanges.setdefault(key, [])
                    if newState == jmri.Block.UNOCCUPIED or newState == jmri.Block.OCCUPIED:
                        if len(hist) == 0 or hist[-1][0] != newState:
                            hist.append((newState, long(now)))
                        else:
                            hist[-1] = (newState, long(now))
                        if len(hist) > 3:
                            del hist[:-3]
                        if len(hist) == 3:
                            a0 = hist[0][0]
                            a1 = hist[1][0]
                            a2 = hist[2][0]
                            if a0 == a2 and a0 != a1 and (long(hist[2][1]) - long(hist[0][1])) <= FLICKER_GAP_MS:
                                report = True
                                del _FlickerStateChanges[key]
                    else:
                        if key in _FlickerStateChanges:
                            del _FlickerStateChanges[key]
            except Exception:
                report = False
            if report:
                _FlickerReport(self.block)
        except Exception:
            pass


def _FlickerAllBlocks():
    items = []
    try:
        bm = jmri.InstanceManager.getDefault(jmri.BlockManager)
        if bm is None:
            return items
        try:
            beans = bm.getNamedBeanSet()
            seq = beans.toArray() if hasattr(beans, "toArray") else list(beans)
        except Exception:
            seq = []
            try:
                names = bm.getSystemNameList()
                seq = [bm.getBlock(str(n)) for n in list(names)]
            except Exception:
                seq = []
        for b in seq:
            if b is not None:
                items.append(b)
    except Exception as ex:
        _FlickerLog("Block enumeration failed: " + str(ex))
    return items


def _FlickerStart():
    global _FlickerStarted
    try:
        with _FlickerLock:
            if _FlickerStarted:
                return True
            _FlickerStarted = True
    except Exception:
        _FlickerStarted = True
    count = 0
    try:
        for b in _FlickerAllBlocks():
            try:
                lst = _FlickerBlockListener(b)
                b.addPropertyChangeListener(lst)
                _FlickerListeners.append((b, lst))
                count += 1
            except Exception:
                pass
    except Exception as ex:
        _FlickerLog("Block flicker start failed: " + str(ex))
        return False
    _FlickerLog("Block flicker monitor started on " + str(count) + " blocks")
    return True


def _FlickerStop():
    global _FlickerStarted
    try:
        with _FlickerLock:
            pairs = list(_FlickerListeners)
            del _FlickerListeners[:]
            _FlickerStateChanges.clear()
            _FlickerStarted = False
    except Exception:
        pairs = []
        _FlickerStarted = False
    for (b, lst) in pairs:
        try:
            b.removePropertyChangeListener(lst)
        except Exception:
            pass
    _FlickerLog("Block flicker monitor stopped")


def _FlickerShow(_window=_FlickerWindow):
    def _ShowNow():
        if _window.IsOpen() or _window.MessageCount() > 0:
            _window.Show()
        else:
            _FlickerShowNotice()
    TASWarningWindow.InvokeOnEdt(_ShowNow)


try:
    _FlickerStart()
except Exception as ex:
    try:
        print("[TAS] Block flicker monitor auto-start failed: " + str(ex))
    except Exception:
        pass

try:
    mgr = jmri.InstanceManager.getDefault(jmri.ShutDownManager)
    if mgr is not None:
        mgr.addShutdownTask(TASWarningWindow.Runner(_FlickerStop))
except Exception:
    pass
