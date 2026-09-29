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
# the first window is open. A repeated flicker for the same Block does not
# add a second message; the existing message flashes instead.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.

import jmri
import threading
from javax.swing import (JFrame, JPanel, JTextPane, JScrollPane, SwingUtilities, Timer,
                        BorderFactory)
from javax.swing.text import SimpleAttributeSet, StyleConstants, DefaultHighlighter
from java.awt import BorderLayout, Dimension, Color, Font, BasicStroke, Polygon, RenderingHints
from java.awt.event import WindowAdapter, ActionListener
from java.lang import Runnable, System
import TASIcon

# Short UNOCCUPIED gap treated as flicker, in milliseconds.
FLICKER_GAP_MS = 3000

# Window geometry. Width is fixed so that wrapped text keeps a stable width.
FRAME_WIDTH = 440
FRAME_BASE_HEIGHT = 300
FRAME_GROW_PER_MESSAGE = 46
FRAME_MAX_HEIGHT = 560
TEXT_WIDTH = 400
TEXT_HEIGHT = 170
MESSAGE_GAP_PIXELS = 16
FLASH_PIXELS = 700
FLIPPER_FONT_SIZE = 12
NAME_FONT_SIZE = 13
TEXT_LIGHT = Color(222, 222, 222)
TEXT_NAME = Color(255, 64, 64)
BACKGROUND = Color(0, 0, 0)
SYMBOL_FILL = Color(198, 40, 40)
SYMBOL_EDGE = Color(122, 0, 0)
SYMBOL_MARK = Color(255, 255, 255)

_lock = threading.RLock()
_started = False
_listeners = []
_lastInactiveMs = {}
_frame = None
_pane = None
_scroll = None
_ranges = {}
_msgCount = [0]
_timers = []


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


class _FlashEnd(ActionListener):
    def __init__(self, pane, tag):
        self.pane = pane
        self.tag = tag
    def actionPerformed(self, e):
        try:
            self.pane.getHighlighter().removeHighlight(self.tag)
        except Exception:
            pass


class _WarningSymbolPanel(JPanel):
    def __init__(self):
        JPanel.__init__(self)
        try:
            self.setPreferredSize(Dimension(TEXT_WIDTH, 150))
            self.setOpaque(False)
        except Exception:
            pass

    def paintComponent(self, g):
        try:
            JPanel.paintComponent(self, g)
        except Exception:
            pass
        try:
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE)
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)
            w = self.getWidth()
            h = self.getHeight()
            cx = w / 2.0
            top = 6.0
            size = min(w - 30.0, h - 14.0)
            if size < 20:
                return
            half = size / 2.0
            bottom = top + size
            poly = Polygon()
            poly.addPoint(int(cx), int(top))
            poly.addPoint(int(cx + half), int(bottom))
            poly.addPoint(int(cx - half), int(bottom))
            g.setColor(SYMBOL_FILL)
            g.fillPolygon(poly)
            g.setColor(SYMBOL_EDGE)
            g.setStroke(BasicStroke(max(4.0, size / 14.0),
                                    BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND))
            g.drawPolygon(poly)
            g.setFont(Font("SansSerif", Font.BOLD, int(size * 0.46)))
            g.setColor(SYMBOL_MARK)
            fm = g.getFontMetrics()
            mark = "!"
            tw = fm.stringWidth(mark)
            tx = int(cx - (tw / 2.0))
            ty = int(bottom - size * 0.22)
            g.drawString(mark, tx, ty)
        except Exception:
            pass


class _CloseReset(WindowAdapter):
    def windowClosed(self, e):
        global _frame, _pane, _scroll
        try:
            with _lock:
                _frame = None
                _pane = None
                _scroll = None
                _ranges.clear()
                _msgCount[0] = 0
                del _timers[:]
        except Exception:
            _frame = None
            _pane = None
            _scroll = None


def _IsFrameOpen():
    try:
        return _frame is not None and _frame.isDisplayable()
    except Exception:
        return False


def _CreateFrame():
    global _frame, _pane, _scroll
    frame = JFrame("Occupancy sensor warning")
    frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
    root = JPanel(BorderLayout())
    root.add(_WarningSymbolPanel(), BorderLayout.NORTH)
    pane = JTextPane()
    try:
        pane.setEditable(False)
        pane.setBackground(BACKGROUND)
        pane.setForeground(TEXT_LIGHT)
        pane.setFont(Font("SansSerif", Font.PLAIN, FLIPPER_FONT_SIZE))
        pane.setBorder(BorderFactory.createEmptyBorder(6, 8, 6, 8))
    except Exception:
        pass
    scroll = JScrollPane(pane)
    try:
        scroll.setPreferredSize(Dimension(TEXT_WIDTH, TEXT_HEIGHT))
        scroll.getViewport().setBackground(BACKGROUND)
        scroll.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_NEVER)
        scroll.setVerticalScrollBarPolicy(JScrollPane.VERTICAL_SCROLLBAR_AS_NEEDED)
    except Exception:
        pass
    root.add(scroll, BorderLayout.CENTER)
    frame.add(root)
    try:
        frame.setSize(Dimension(FRAME_WIDTH, FRAME_BASE_HEIGHT))
    except Exception:
        pass
    try:
        TASIcon.SetFrameClockIcon(frame)
    except Exception:
        pass
    try:
        frame.addWindowListener(_CloseReset())
    except Exception:
        pass
    _frame = frame
    _pane = pane
    _scroll = scroll
    return frame


def _PlainAttrs(color, size, bold):
    attrs = SimpleAttributeSet()
    StyleConstants.setForeground(attrs, color)
    StyleConstants.setFontFamily(attrs, "SansSerif")
    StyleConstants.setFontSize(attrs, size)
    StyleConstants.setBold(attrs, bold)
    return attrs


def _GrowFrame():
    try:
        h = FRAME_BASE_HEIGHT + (int(_msgCount[0]) * FRAME_GROW_PER_MESSAGE)
        if h > FRAME_MAX_HEIGHT:
            h = FRAME_MAX_HEIGHT
        _frame.setSize(Dimension(FRAME_WIDTH, h))
    except Exception:
        pass


def _FlashNow(key):
    try:
        span = _ranges.get(key, None)
        if span is None:
            return
        start, end = span
        painter = DefaultHighlighter.DefaultHighlightPainter(Color(255, 255, 255))
        tag = _pane.getHighlighter().addHighlight(start, end, painter)
        timer = Timer(FLASH_PIXELS, _FlashEnd(_pane, tag))
        timer.setRepeats(False)
        _timers.append(timer)
        timer.start()
    except Exception:
        pass


def _ShowNotice(text):
    try:
        if not _IsFrameOpen():
            _CreateFrame()
        doc = _pane.getStyledDocument()
        pos = doc.getLength()
        if pos > 0:
            gap = SimpleAttributeSet()
            StyleConstants.setFontSize(gap, MESSAGE_GAP_PIXELS)
            doc.insertString(pos, " ", gap)
            pos = doc.getLength()
        start = pos
        doc.insertString(pos, str(text), _PlainAttrs(TEXT_LIGHT, FLIPPER_FONT_SIZE, False))
        _ranges["__notice__"] = (start, doc.getLength())
        _msgCount[0] += 1
        try:
            _pane.setCaretPosition(doc.getLength())
        except Exception:
            pass
        try:
            _pane.revalidate()
            _pane.repaint()
        except Exception:
            pass
        _GrowFrame()
        try:
            if not _frame.isVisible():
                _frame.setLocationRelativeTo(None)
            _frame.setVisible(True)
            _frame.toFront()
        except Exception:
            try:
                _frame.setVisible(True)
            except Exception:
                pass
    except Exception as ex:
        _Log("Block flicker window update failed: " + str(ex))


def _AppendMessage(key, name):
    try:
        if key in _ranges:
            _FlashNow(key)
            return
        if not _IsFrameOpen():
            _CreateFrame()
        doc = _pane.getStyledDocument()
        lead = "Flickering occupancy sensor detected at: "
        tail = ": check for dirty track or loose wiring"
        pos = doc.getLength()
        if pos > 0:
            gap = SimpleAttributeSet()
            StyleConstants.setFontSize(gap, MESSAGE_GAP_PIXELS)
            doc.insertString(pos, " ", gap)
            pos = doc.getLength()
        start = pos
        doc.insertString(pos, lead, _PlainAttrs(TEXT_LIGHT, FLIPPER_FONT_SIZE, False))
        pos = doc.getLength()
        doc.insertString(pos, str(name), _PlainAttrs(TEXT_NAME, NAME_FONT_SIZE, True))
        pos = doc.getLength()
        doc.insertString(pos, tail, _PlainAttrs(TEXT_LIGHT, FLIPPER_FONT_SIZE, False))
        end = doc.getLength()
        _ranges[key] = (start, end)
        _msgCount[0] += 1
        try:
            _pane.setCaretPosition(doc.getLength())
        except Exception:
            pass
        try:
            _pane.revalidate()
            _pane.repaint()
        except Exception:
            pass
        _GrowFrame()
        try:
            if not _frame.isVisible():
                _frame.setLocationRelativeTo(None)
            _frame.setVisible(True)
            _frame.toFront()
        except Exception:
            try:
                _frame.setVisible(True)
            except Exception:
                pass
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
    try:
        _InvokeOnEdt(lambda: _AppendMessage(key, name))
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
            _ShowNotice("No occupancy sensor flickering recorded this session.")
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
