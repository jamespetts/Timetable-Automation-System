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
# Block drops to UNOCCUPIED and returns to OCCUPIED within a short gap.
# The window is shown even when Dispatcher reports no error. All flicker
# messages accumulate in the same window, one per line; no second window is
# opened while the first window is open. A repeated flicker for the same Block
# does not add a second message; the existing message flashes instead.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.

import jmri
import threading
from java.awt import Color
from java.lang import System
import TASWarningWindow

# Short UNOCCUPIED gap treated as flicker, in milliseconds.
FLICKER_GAP_MS = 3000

# Window geometry. Width is fixed so that wrapped text keeps a stable width.
FRAME_WIDTH = 440
FRAME_BASE_HEIGHT = 300
FRAME_GROW_PER_MESSAGE = 46
FRAME_MAX_HEIGHT = 560
TEXT_WIDTH = 400
TEXT_HEIGHT = 170
FLASH_PIXELS = 700
FLIPPER_FONT_SIZE = 12
NAME_FONT_SIZE = 13
TEXT_LIGHT = Color(222, 222, 222)
TEXT_NAME = Color(255, 64, 64)
BACKGROUND = Color(0, 0, 0)
SYMBOL_FILL = Color(198, 40, 40)
SYMBOL_EDGE = Color(122, 0, 0)
SYMBOL_MARK = Color(255, 255, 255)

MESSAGE_LEAD = "Flickering occupancy sensor detected at: "
MESSAGE_TAIL = ": check for dirty track or loose wiring"
NOTICE_TEXT = "No occupancy sensor flickering recorded this session."
NOTICE_KEY = "__notice__"

# One warning window for this feature. See TASWarningWindow.py.
_window = TASWarningWindow.TasWarningWindow({
    "title": "Occupancy sensor warning",
    "textWidth": TEXT_WIDTH,
    "textHeight": TEXT_HEIGHT,
    "frameWidth": FRAME_WIDTH,
    "frameBaseHeight": FRAME_BASE_HEIGHT,
    "frameGrowPerMessage": FRAME_GROW_PER_MESSAGE,
    "frameMaxHeight": FRAME_MAX_HEIGHT,
    "fontSize": FLIPPER_FONT_SIZE,
    "nameFontSize": NAME_FONT_SIZE,
    "background": BACKGROUND,
    "backgroundHex": "000000",
    "textColour": TEXT_LIGHT,
    "textHex": "dedede",
    "nameHex": "ff4040",
    "symbolFill": SYMBOL_FILL,
    "symbolEdge": SYMBOL_EDGE,
    "markColour": SYMBOL_MARK,
    "flashColour": Color(255, 255, 255),
    "flashPixels": FLASH_PIXELS,
})

_lock = threading.RLock()
_started = False
_listeners = []
_lastInactiveMs = {}


def _Log(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


def _BlockLabel(block):
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


def _SensorLabel(block):
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


def _ShowNoticeNow():
    _window.AddNotice(NOTICE_KEY, NOTICE_TEXT)


def _AppendMessage(key, name):
    try:
        _window.AddMessage(key, name, MESSAGE_LEAD, MESSAGE_TAIL)
    except Exception as ex:
        _Log("Block flicker window update failed: " + str(ex))


def _ReportFlicker(block):
    name = _BlockLabel(block)
    sensor = _SensorLabel(block)
    try:
        key = str(block.getSystemName())
    except Exception:
        key = str(name)
    if sensor is not None and sensor != name:
        consoleName = str(name) + " (sensor " + str(sensor) + ")"
    else:
        consoleName = str(name)
    _Log("Flickering occupancy sensor at " + consoleName)
    # AddMessage already marshals to the Event Dispatch Thread.
    _AppendMessage(key, name)


class _BlockListener(java.beans.PropertyChangeListener):
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
            if newState == jmri.Block.UNOCCUPIED:
                try:
                    with _lock:
                        _lastInactiveMs[key] = long(now)
                except Exception:
                    pass
            elif newState == jmri.Block.OCCUPIED:
                gap = None
                try:
                    with _lock:
                        prev = _lastInactiveMs.pop(key, None)
                    if prev is not None:
                        gap = long(now) - long(prev)
                except Exception:
                    gap = None
                if gap is not None and gap >= 0 and gap <= FLICKER_GAP_MS:
                    _ReportFlicker(self.block)
        except Exception:
            pass


def _AllBlocks():
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
        _Log("Block enumeration failed: " + str(ex))
    return items


def Start():
    global _started
    try:
        with _lock:
            if _started:
                return True
            _started = True
    except Exception:
        _started = True
    count = 0
    try:
        for b in _AllBlocks():
            try:
                lst = _BlockListener(b)
                b.addPropertyChangeListener(lst)
                _listeners.append((b, lst))
                count += 1
            except Exception:
                pass
    except Exception as ex:
        _Log("Block flicker start failed: " + str(ex))
        return False
    _Log("Block flicker monitor started on " + str(count) + " blocks")
    return True


def Stop():
    global _started
    try:
        with _lock:
            pairs = list(_listeners)
            del _listeners[:]
            _lastInactiveMs.clear()
            _started = False
    except Exception:
        pairs = []
        _started = False
    for (b, lst) in pairs:
        try:
            b.removePropertyChangeListener(lst)
        except Exception:
            pass
    _Log("Block flicker monitor stopped")


def Show():
    def _ShowNow():
        if _window.IsOpen() or _window.MessageCount() > 0:
            _window.Show()
        else:
            _ShowNoticeNow()
    TASWarningWindow.InvokeOnEdt(_ShowNow)


try:
    Start()
except Exception as ex:
    try:
        print("[TAS] Block flicker monitor auto-start failed: " + str(ex))
    except Exception:
        pass

try:
    mgr = jmri.InstanceManager.getDefault(jmri.ShutDownManager)
    if mgr is not None:
        mgr.addShutdownTask(TASWarningWindow.Runner(Stop))
except Exception:
    pass
