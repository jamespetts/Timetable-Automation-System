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
# TASWarningWindow.py
# Shared non-modal warning window used by TAS warning features.
# A warning triangle is drawn above a black message area. Message lines accumulate in
# one window, one per line. A repeated message for the same key flashes the existing
# line instead of adding a second line. The window grows as lines are added, up to a
# maximum height, and the text wraps to the width of the window.
# All window work is performed on the Event Dispatch Thread.
# JMRI 5.16 / Jython 2.7. ASCII only.

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
import threading
from javax.swing import (JFrame, JPanel, JTextPane, JScrollPane, SwingUtilities, Timer)
from javax.swing.text import DefaultHighlighter
from java.awt import BorderLayout, Dimension, Color, Font, BasicStroke, Polygon, RenderingHints
from java.awt.event import WindowAdapter, ActionListener
from java.lang import Runnable, System
import TASIcon

# Defaults. A caller overrides any of these through the config dictionary.
DEFAULTS = {
    "title": "TAS warning",
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
    "nameHex": "ff4040",
    "symbolFill": Color(198, 40, 40),
    "symbolEdge": Color(122, 0, 0),
    "markColour": Color(255, 255, 255),
    "flashColour": Color(255, 255, 255),
    "flashPixels": 700,
}


class Runner(Runnable):
    def __init__(self, fn):
        self.fn = fn

    def run(self):
        try:
            self.fn()
        except Exception:
            pass


def InvokeOnEdt(fn):
    try:
        if SwingUtilities.isEventDispatchThread():
            fn()
        else:
            SwingUtilities.invokeLater(Runner(fn))
    except Exception:
        try:
            fn()
        except Exception:
            pass


def Escape(text):
    s = str(text)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    return s


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
    def __init__(self, fill, edge, mark, textWidth):
        JPanel.__init__(self)
        self.Fill = fill
        self.Edge = edge
        self.Mark = mark
        try:
            self.setPreferredSize(Dimension(int(textWidth), 150))
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
            g.setColor(self.Fill)
            g.fillPolygon(poly)
            g.setColor(self.Edge)
            g.setStroke(BasicStroke(max(4.0, size / 14.0),
                                    BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND))
            g.drawPolygon(poly)
            g.setFont(Font("SansSerif", Font.BOLD, int(size * 0.46)))
            g.setColor(self.Mark)
            fm = g.getFontMetrics()
            mark = "!"
            tw = fm.stringWidth(mark)
            tx = int(cx - (tw / 2.0))
            ty = int(bottom - size * 0.22)
            g.drawString(mark, tx, ty)
        except Exception:
            pass


class _CloseReset(WindowAdapter):
    def __init__(self, window):
        self.window = window

    def windowClosed(self, e):
        self.window._ResetOnClose()


class TasWarningWindow(object):
    # One independent warning window. Create one instance per warning feature so
    # that unrelated warnings do not share a window.
    def __init__(self, config=None):
        cfg = {}
        cfg.update(DEFAULTS)
        try:
            if config is not None:
                cfg.update(config)
        except Exception:
            pass
        self.cfg = cfg
        self._lock = threading.RLock()
        self._frame = None
        self._pane = None
        self._scroll = None
        self._messages = []
        self._ranges = {}
        self._timers = []

    # ---------------- state ----------------

    def IsOpen(self):
        try:
            return self._frame is not None and self._frame.isDisplayable()
        except Exception:
            return False

    def MessageCount(self):
        try:
            with self._lock:
                return len(self._messages)
        except Exception:
            return 0

    def _ResetOnClose(self):
        try:
            with self._lock:
                self._frame = None
                self._pane = None
                self._scroll = None
                self._messages = []
                self._ranges = {}
                del self._timers[:]
        except Exception:
            self._frame = None
            self._pane = None
            self._scroll = None

    def Clear(self):
        InvokeOnEdt(lambda: self._ClearNow())

    def _ClearNow(self):
        try:
            with self._lock:
                self._messages = []
                self._ranges = {}
                del self._timers[:]
            self._RenderNow()
        except Exception:
            pass

    # ---------------- content ----------------

    def _AddRecord(self, key, name, text, lead, tail):
        if not self.IsOpen():
            self._CreateFrame()
        with self._lock:
            self._messages.append({"key": key, "name": name, "text": text,
                                   "lead": lead, "tail": tail,
                                   "start": None, "end": None})
        self._RenderNow()
        self._ShowFrame()

    def AddNotice(self, key, text):
        # A plain message with no highlighted name.
        InvokeOnEdt(lambda: self._AddRecord(key, None, str(text), "", ""))

    def AddMessage(self, key, name, lead, tail):
        # A message with a highlighted name. A repeat of the same key flashes the
        # existing line rather than adding a second line.
        def _Do():
            try:
                with self._lock:
                    known = (key in self._ranges) or any(m.get("key") == key for m in self._messages)
                if known:
                    self._FlashNow(key)
                    return
                text = str(lead) + str(name) + str(tail)
                self._AddRecord(key, str(name), text, str(lead), str(tail))
            except Exception:
                pass
        InvokeOnEdt(_Do)

    # ---------------- frame ----------------

    def _CreateFrame(self):
        cfg = self.cfg
        frame = JFrame(str(cfg.get("title", "TAS warning")))
        frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
        root = JPanel(BorderLayout())
        root.add(_WarningSymbolPanel(cfg.get("symbolFill"), cfg.get("symbolEdge"),
                                     cfg.get("markColour"), cfg.get("textWidth")),
                 BorderLayout.NORTH)
        pane = JTextPane()
        try:
            pane.setEditable(False)
            pane.setBackground(cfg.get("background"))
            pane.setForeground(cfg.get("textColour"))
            pane.setFont(Font("SansSerif", Font.PLAIN, int(cfg.get("fontSize"))))
            pane.setContentType("text/html")
        except Exception:
            pass
        scroll = JScrollPane(pane)
        try:
            scroll.setPreferredSize(Dimension(int(cfg.get("textWidth")), int(cfg.get("textHeight"))))
            scroll.getViewport().setBackground(cfg.get("background"))
            scroll.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_NEVER)
            scroll.setVerticalScrollBarPolicy(JScrollPane.VERTICAL_SCROLLBAR_AS_NEEDED)
        except Exception:
            pass
        root.add(scroll, BorderLayout.CENTER)
        frame.add(root)
        try:
            frame.setSize(Dimension(int(cfg.get("frameWidth")), int(cfg.get("frameBaseHeight"))))
        except Exception:
            pass
        try:
            TASIcon.SetFrameClockIcon(frame)
        except Exception:
            pass
        try:
            frame.addWindowListener(_CloseReset(self))
        except Exception:
            pass
        with self._lock:
            self._frame = frame
            self._pane = pane
            self._scroll = scroll

    def _BuildHtml(self):
        cfg = self.cfg
        body = "background-color:#" + str(cfg.get("backgroundHex")) + ";"
        grow = int(int(cfg.get("frameGrowPerMessage")) / 2)
        parts = ["<html><head><style type=\"text/css\">",
                 "body { " + body + " color:#" + str(cfg.get("textHex")) +
                 "; font-family: SansSerif; font-size: " + str(int(cfg.get("fontSize"))) +
                 "px; margin: 6px 8px 6px 8px; }",
                 "p { margin: 0px 0px " + str(grow) + "px 0px; }",
                 "</style></head><body>"]
        with self._lock:
            snapshot = list(self._messages)
        for m in snapshot:
            if m.get("name") is None:
                parts.append("<p>" + Escape(m.get("text")) + "</p>")
            else:
                parts.append("<p>" + Escape(m.get("lead")) +
                             "<span style=\"color:#" + str(cfg.get("nameHex")) +
                             "; font-size:" + str(int(cfg.get("nameFontSize"))) +
                             "px; font-weight:bold;\">" + Escape(m.get("name")) + "</span>" +
                             Escape(m.get("tail")) + "</p>")
        parts.append("</body></html>")
        return "".join(parts)

    def _RecomputeRanges(self):
        with self._lock:
            pane = self._pane
        if pane is None:
            return
        try:
            doc = pane.getDocument()
            txt = doc.getText(0, doc.getLength())
        except Exception:
            return
        pos = 0
        with self._lock:
            for m in self._messages:
                needle = m.get("text")
                if needle is None:
                    continue
                idx = txt.find(needle, pos)
                if idx < 0:
                    continue
                m["start"] = idx
                m["end"] = idx + len(needle)
                pos = idx + len(needle)
            self._ranges.clear()
            for m in self._messages:
                k = m.get("key")
                if k is None:
                    continue
                if m.get("start") is not None:
                    self._ranges[k] = (m.get("start"), m.get("end"))

    def _RenderNow(self):
        with self._lock:
            pane = self._pane
            frame = self._frame
        if pane is None:
            return
        try:
            pane.setText(self._BuildHtml())
        except Exception:
            return
        try:
            pane.setCaretPosition(0)
        except Exception:
            pass
        self._RecomputeRanges()
        try:
            pane.revalidate()
            pane.repaint()
        except Exception:
            pass
        try:
            base = int(self.cfg.get("frameBaseHeight"))
            grow = int(self.cfg.get("frameGrowPerMessage"))
            h = base + (self.MessageCount() * grow)
            if h > int(self.cfg.get("frameMaxHeight")):
                h = int(self.cfg.get("frameMaxHeight"))
            if frame is not None:
                frame.setSize(Dimension(int(self.cfg.get("frameWidth")), h))
        except Exception:
            pass

    def _FlashNow(self, key):
        with self._lock:
            span = self._ranges.get(key, None)
            pane = self._pane
        if span is None or pane is None:
            return
        try:
            start, end = span
            painter = DefaultHighlighter.DefaultHighlightPainter(self.cfg.get("flashColour"))
            tag = pane.getHighlighter().addHighlight(start, end, painter)
            timer = Timer(int(self.cfg.get("flashPixels")), _FlashEnd(pane, tag))
            timer.setRepeats(False)
            with self._lock:
                self._timers.append(timer)
            timer.start()
        except Exception:
            pass

    def _ShowFrame(self):
        with self._lock:
            frame = self._frame
        if frame is None:
            return
        try:
            if not frame.isVisible():
                frame.setLocationRelativeTo(None)
            frame.setVisible(True)
            frame.toFront()
        except Exception:
            try:
                frame.setVisible(True)
            except Exception:
                pass

    def Show(self):
        # Bring the window forward. With no messages yet, show a supplied notice.
        def _ShowNow():
            if self.IsOpen():
                self._ShowFrame()
                return
        InvokeOnEdt(_ShowNow)
