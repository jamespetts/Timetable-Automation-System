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
# messages accumulate in the same window; no second window is opened while
# the first window is open.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.

import jmri
import threading
import traceback
from javax.swing import JFrame, JPanel, JLabel, JScrollPane, Box, SwingUtilities, BorderFactory
from java.awt import BorderLayout, Dimension, Color, Font
from java.awt.event import WindowAdapter
from java.lang import Runnable, System
import TASIcon

# Short UNOCCUPIED gap treated as flicker, in milliseconds.
FLICKER_GAP_MS = 3000

_lock = threading.RLock()
_started = False
_listeners = []
_lastInactiveMs = {}
_frame = None
_msgBox = None
_msgScroll = None
_msgCount = [0]


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


class _Runner(Runnable):
    def __init__(self, fn):
        self.fn = fn
    def run(self):
        try:
            self.fn()
        except Exception:
            pass


def _InvokeOnEdt(fn):
    try:
        if SwingUtilities.isEventDispatchThread():
            fn()
        else:
            SwingUtilities.invokeLater(_Runner(fn))
    except Exception:
        try:
            fn()
        except Exception:
            pass


class _WarningIconPanel(JPanel):
    def __init__(self):
        JPanel.__init__(self)
        try:
            self.setPreferredSize(Dimension(280, 150))
            self.setOpaque(False)
        except Exception:
            pass
    def paintComponent(self, g):
        try:
            JPanel.paintComponent(self, g)
        except Exception:
            pass
        try:
            from java.awt import Polygon
            w = self.getWidth()
            h = self.getHeight()
            cx = w // 2
            top = 8
            size = min(w - 24, h - 16)
            half = size // 2
            left = cx - half
            right = cx + half
            bottom = top + size
            poly = Polygon()
            poly.addPoint(cx, top)
            poly.addPoint(right, bottom)
            poly.addPoint(left, bottom)
            g.setColor(Color(255, 193, 7))
            g.fillPolygon(poly)
            g.setColor(Color(0, 0, 0))
            g.drawPolygon(poly)
            g.setFont(Font("SansSerif", Font.BOLD, 64))
            fm = g.getFontMetrics()
            mark = "!"
            tw = fm.stringWidth(mark)
            tx = cx - (tw // 2)
            ty = bottom - 18
            g.drawString(mark, tx, ty)
        except Exception:
            pass


class _CloseReset(WindowAdapter):
    def windowClosed(self, e):
        global _frame, _msgBox, _msgScroll
        try:
            with _lock:
                _frame = None
                _msgBox = None
                _msgScroll = None
        except Exception:
            _frame = None
            _msgBox = None
            _msgScroll = None


def _IsFrameOpen():
    try:
        return _frame is not None and _frame.isDisplayable()
    except Exception:
        return False


def _CreateFrame():
    global _frame, _msgBox, _msgScroll
    frame = JFrame("Occupancy sensor warning")
    frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
    try:
        frame.setMinimumSize(Dimension(300, 320))
        frame.setSize(Dimension(340, 380))
    except Exception:
        pass
    root = JPanel(BorderLayout())
    try:
        root.setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10))
    except Exception:
        pass
    icon = _WarningIconPanel()
    root.add(icon, BorderLayout.NORTH)
    box = Box.createVerticalBox()
    scroll = JScrollPane(box)
    try:
        scroll.setPreferredSize(Dimension(300, 160))
        scroll.setBorder(BorderFactory.createEmptyBorder(4, 0, 0, 0))
    except Exception:
        pass
    root.add(scroll, BorderLayout.CENTER)
    frame.add(root)
    try:
        TASIcon.SetFrameClockIcon(frame)
    except Exception:
        pass
    try:
        frame.addWindowListener(_CloseReset())
    except Exception:
        pass
    _frame = frame
    _msgBox = box
    _msgScroll = scroll
    return frame


def _AddMessageNow(text):
    global _msgCount
    try:
        with _lock:
            if not _IsFrameOpen():
                _CreateFrame()
            box = _msgBox
            frame = _frame
        if box is None or frame is None:
            return
        if _msgCount[0] > 0:
            try:
                box.add(Box.createVerticalStrut(16))
            except Exception:
                pass
        try:
            label = JLabel("<html>" + str(text) + "</html>")
            try:
                label.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8))
            except Exception:
                pass
            box.add(label)
        except Exception:
            pass
        _msgCount[0] += 1
        try:
            box.revalidate()
            box.repaint()
        except Exception:
            pass
        wasVisible = False
        try:
            wasVisible = frame.isVisible()
        except Exception:
            pass
        try:
            frame.pack()
        except Exception:
            pass
        try:
            if not wasVisible:
                frame.setLocationRelativeTo(None)
            frame.setVisible(True)
            frame.toFront()
        except Exception:
            try:
                frame.setVisible(True)
            except Exception:
                pass
    except Exception as ex:
        _Log("Block flicker window update failed: " + str(ex))


def _ReportFlicker(block):
    name = _BlockLabel(block)
    sensor = _SensorLabel(block)
    if sensor is not None and sensor != name:
        consoleName = str(name) + " (sensor " + str(sensor) + ")"
    else:
        consoleName = str(name)
    _Log("Flickering occupancy sensor at " + consoleName)
    text = "flickering occupancy sensor detected at: " + str(name) + ": check for dirty track or loose wiring"
    try:
        _InvokeOnEdt(lambda: _AddMessageNow(text))
    except Exception:
        pass


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
            if newState == jmri.Block.UNOCCUPIED:
                try:
                    with _lock:
                        try:
                            key = str(self.block.getSystemName())
                        except Exception:
                            key = str(self.block)
                        _lastInactiveMs[key] = long(now)
                except Exception:
                    pass
            elif newState == jmri.Block.OCCUPIED:
                gap = None
                try:
                    with _lock:
                        try:
                            key = str(self.block.getSystemName())
                        except Exception:
                            key = str(self.block)
                        prev = _lastInactiveMs.get(key, None)
                        if key in _lastInactiveMs:
                            try:
                                del _lastInactiveMs[key]
                            except Exception:
                                pass
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
        try:
            with _lock:
                openNow = _IsFrameOpen()
                n = int(_msgCount[0])
        except Exception:
            openNow = False
            n = 0
        if openNow:
            try:
                _frame.setVisible(True)
                _frame.toFront()
            except Exception:
                pass
            return
        if n == 0:
            _AddMessageNow("No flickering recorded.")
        else:
            try:
                _frame.setVisible(True)
                _frame.toFront()
            except Exception:
                pass
    _InvokeOnEdt(_ShowNow)


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
        mgr.addShutdownTask(_Runner(Stop))
except Exception:
    pass
