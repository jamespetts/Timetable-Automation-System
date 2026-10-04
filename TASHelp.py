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
# Help window for TAS with searchable topic index and greyed placeholder
# Renders tashelp/*.md (Markdown) as HTML. Plain tashelp/*.txt still loads as fallback.
# Uses theme Memories TAS_FONT_FAMILY, TASPAPERCOLOUR and TASINKCOLOUR.

from javax.swing import JFrame, JPanel, JSplitPane, JScrollPane, JList, JLabel
from javax.swing import ListSelectionModel, JOptionPane, JTextField, DefaultListModel, SwingUtilities
from javax.swing import JEditorPane
from javax.swing.event import DocumentListener, HyperlinkEvent
from java.awt import BorderLayout, Dimension, Color, Desktop, Font
from java.io import File
from java.lang import System
from java.net import URI
from java.awt.event import FocusAdapter, WindowAdapter
import jmri
import re
import traceback
import TASIcon
try:
    import TASBeanLookup as TBL
except:
    TBL = None

def _ThemeFontFamily():
    try:
        if TBL is not None:
            v = TBL.SafeGetOrCreateMemoryValue("TAS_FONT_FAMILY", "Gill Sans MT")
            if v is not None and len(str(v).strip()) > 0:
                return str(v).strip()
    except:
        pass
    return "Gill Sans MT"

def _ThemeRgbStr(name, default):
    try:
        if TBL is not None:
            v = TBL.SafeGetOrCreateMemoryValue(name, default)
            if v is not None and len(str(v).strip()) > 0:
                return str(v).strip()
    except:
        pass
    return default

def _RgbStrToHex(rgbStr, defaultHex):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) == 3:
            r = max(0, min(255, int(float(parts[0]))))
            g = max(0, min(255, int(float(parts[1]))))
            b = max(0, min(255, int(float(parts[2]))))
            return "#%02x%02x%02x" % (r, g, b)
    except:
        pass
    return defaultHex

def _RgbStrToColor(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) == 3:
            r = max(0, min(255, int(float(parts[0]))))
            g = max(0, min(255, int(float(parts[1]))))
            b = max(0, min(255, int(float(parts[2]))))
            return Color(r, g, b)
    except:
        pass
    return defaultColor

def _CssFontFamily():
    try:
        fam = _ThemeFontFamily()
    except:
        fam = "Gill Sans MT"
    try:
        fam = str(fam).replace("'", "").replace('"', "").replace(";", "").strip()
    except:
        fam = "Gill Sans MT"
    if len(fam) == 0:
        fam = "Gill Sans MT"
    return fam

def _BodyStyle():
    try:
        fam = _CssFontFamily()
        inkHex = _RgbStrToHex(_ThemeRgbStr("TASINKCOLOUR", "0,0,0"), "#000000")
        paperHex = _RgbStrToHex(_ThemeRgbStr("TASPAPERCOLOUR", "249,246,238"), "#f9f6ee")
        return "font-family:'" + fam + "',sans-serif; font-size:14px; color:" + inkHex + "; background-color:" + paperHex + ";"
    except:
        return "font-family:sans-serif; font-size:14px;"

def _EscapeHtml(s):
    try:
        t = str(s)
    except:
        t = ""
    t = t.replace("&", "&amp;")
    t = t.replace("<", "&lt;")
    t = t.replace(">", "&gt;")
    t = t.replace('"', "&quot;")
    return t

def _RenderInline(s):
    try:
        t = _EscapeHtml(s)
    except:
        t = ""
    try:
        t = re.sub(r'`([^`]+?)`', r'<code>\1</code>', t)
    except:
        pass
    try:
        t = re.sub(r'\[([^\]]+?)\]\(([^)]+?)\)', r'<a href="\2">\1</a>', t)
    except:
        pass
    try:
        t = re.sub(r'\*\*([^*]+?)\*\*', r'<b>\1</b>', t)
    except:
        pass
    try:
        t = re.sub(r'\*([^*]+?)\*', r'<i>\1</i>', t)
    except:
        pass
    try:
        t = re.sub(r'_([^_]+?)_', r'<i>\1</i>', t)
    except:
        pass
    return t

def _IsTableSeparator(line):
    try:
        t = str(line).strip()
        if "|" not in t:
            return False
        if t.startswith("|"):
            t = t[1:]
        if t.endswith("|"):
            t = t[:-1]
        cells = t.split("|")
        if len(cells) == 0:
            return False
        for c in cells:
            cc = c.strip()
            if len(cc) < 3:
                return False
            k = 0
            while k < len(cc) and cc[k] == ":":
                k += 1
            j = len(cc)
            while j > k and cc[j - 1] == ":":
                j -= 1
            mid = cc[k:j]
            if len(mid) < 3:
                return False
            ok = True
            for ch in mid:
                if ch != "-":
                    ok = False
                    break
            if not ok:
                return False
        return True
    except:
        return False

def _SplitTableRow(line):
    try:
        t = str(line).strip()
        if t.startswith("|"):
            t = t[1:]
        if t.endswith("|"):
            t = t[:-1]
        parts = t.split("|")
        out = []
        for p in parts:
            out.append(p.strip())
        return out
    except:
        return []

def _WrapHtml(body):
    try:
        return "<html><body style=\"" + _BodyStyle() + "\">" + str(body) + "</body></html>"
    except:
        return "<html><body></body></html>"

def _TextToHtml(txt):
    try:
        return _WrapHtml("<pre>" + _EscapeHtml(txt) + "</pre>")
    except Exception as ex:
        _LogExc("_TextToHtml failed", ex)
        return _WrapHtml("<pre></pre>")

def _MarkdownToHtml(md):
    try:
        text = str(md).replace("\r\n", "\n").replace("\r", "\n")
    except:
        text = ""
    lines = text.split("\n")
    out = []
    para = []
    inUl = [False]
    inOl = [False]
    inCode = [False]
    codeBuf = []
    def _FlushPara():
        try:
            if len(para) > 0:
                joined = " ".join(para)
                joined = joined.strip()
                if len(joined) > 0:
                    out.append("<p>" + _RenderInline(joined) + "</p>")
                del para[:]
        except:
            try:
                del para[:]
            except:
                pass
    def _CloseLists():
        try:
            if inOl[0]:
                out.append("</ol>")
                inOl[0] = False
            if inUl[0]:
                out.append("</ul>")
                inUl[0] = False
        except:
            pass
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        try:
            s = raw.strip()
        except:
            s = ""
        if inCode[0]:
            if s.startswith("```"):
                try:
                    out.append("<pre>" + _EscapeHtml("\n".join(codeBuf)) + "</pre>")
                except:
                    out.append("<pre></pre>")
                del codeBuf[:]
                inCode[0] = False
            else:
                codeBuf.append(raw.rstrip("\n"))
            i += 1
            continue
        if s.startswith("```"):
            _FlushPara()
            _CloseLists()
            inCode[0] = True
            del codeBuf[:]
            i += 1
            continue
        if len(s) == 0:
            _FlushPara()
            _CloseLists()
            i += 1
            continue
        if s in ("---", "***", "___"):
            _FlushPara()
            _CloseLists()
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("#"):
            h = 0
            while h < len(s) and s[h] == "#":
                h += 1
            if h >= 1 and h <= 4 and len(s) > h and s[h] == " ":
                _FlushPara()
                _CloseLists()
                title = s[h + 1:].strip()
                out.append("<h" + str(h) + ">" + _RenderInline(title) + "</h" + str(h) + ">")
                i += 1
                continue
        if s.startswith(">"):
            _FlushPara()
            _CloseLists()
            quotes = []
            while i < n:
                q = lines[i].strip()
                if q.startswith(">"):
                    quotes.append(q[1:].strip())
                    i += 1
                elif len(q) == 0:
                    break
                else:
                    break
            try:
                qtext = " ".join(quotes).strip()
                if len(qtext) > 0:
                    out.append("<blockquote>" + _RenderInline(qtext) + "</blockquote>")
            except:
                pass
            continue
        if "|" in s and (i + 1) < n and _IsTableSeparator(lines[i + 1]):
            _FlushPara()
            _CloseLists()
            try:
                header = _SplitTableRow(s)
                out.append('<table border="1" cellpadding="4" cellspacing="0">')
                hcells = []
                for hc in header:
                    hcells.append("<th>" + _RenderInline(hc) + "</th>")
                out.append("<tr>" + "".join(hcells) + "</tr>")
            except:
                pass
            i += 2
            while i < n:
                try:
                    row = lines[i].strip()
                except:
                    row = ""
                if len(row) == 0 or "|" not in row:
                    break
                if _IsTableSeparator(row):
                    i += 1
                    continue
                try:
                    cells = _SplitTableRow(row)
                    parts = []
                    for cc in cells:
                        parts.append("<td>" + _RenderInline(cc) + "</td>")
                    out.append("<tr>" + "".join(parts) + "</tr>")
                except:
                    pass
                i += 1
            try:
                out.append("</table>")
            except:
                pass
            continue
        bullet = None
        try:
            if re.match(r'^\s*[-*+]\s+.+', raw):
                m = re.match(r'^\s*[-*+]\s+(.*)', raw)
                if m:
                    bullet = m.group(1)
        except:
            bullet = None
        if bullet is not None:
            _FlushPara()
            if inOl[0]:
                out.append("</ol>")
                inOl[0] = False
            if not inUl[0]:
                out.append("<ul>")
                inUl[0] = True
            try:
                out.append("<li>" + _RenderInline(bullet.strip()) + "</li>")
            except:
                pass
            i += 1
            continue
        ordered = None
        try:
            if re.match(r'^\s*\d+[.)]\s+.+', raw):
                m2 = re.match(r'^\s*\d+[.)]\s+(.*)', raw)
                if m2:
                    ordered = m2.group(1)
        except:
            ordered = None
        if ordered is not None:
            _FlushPara()
            if inUl[0]:
                out.append("</ul>")
                inUl[0] = False
            if not inOl[0]:
                out.append("<ol>")
                inOl[0] = True
            try:
                out.append("<li>" + _RenderInline(ordered.strip()) + "</li>")
            except:
                pass
            i += 1
            continue
        para.append(s)
        i += 1
    _FlushPara()
    _CloseLists()
    if inCode[0]:
        try:
            out.append("<pre>" + _EscapeHtml("\n".join(codeBuf)) + "</pre>")
        except:
            pass
    return _WrapHtml("".join(out))

def _OpenLink(url):
    try:
        u = str(url).strip()
        if len(u) == 0:
            return
        if u.lower().startswith("http://") or u.lower().startswith("https://"):
            try:
                if Desktop.isDesktopSupported():
                    d = Desktop.getDesktop()
                    try:
                        supported = d.isSupported(Desktop.Action.BROWSE)
                    except:
                        supported = True
                    if supported:
                        d.browse(URI(u))
                        _Log("Opened link: " + u)
                        return
            except Exception as exDesk:
                _LogExc("Desktop browse failed", exDesk)
        _Log("Link ignored: " + u)
        try:
            JOptionPane.showMessageDialog(None, "Link:\n" + u, "TAS Help", JOptionPane.INFORMATION_MESSAGE)
        except:
            pass
    except Exception as exLink:
        _LogExc("_OpenLink failed", exLink)

def _Log(msg):
    try:
        System.err.println("[TASHelp] " + str(msg))
    except:
        pass
    try:
        print("[TASHelp] " + str(msg))
    except:
        pass

def _LogExc(prefix, ex):
    try:
        System.err.println("[TASHelp] " + prefix + ": " + str(ex))
    except:
        pass
    try:
        print("[TASHelp] " + prefix + ": " + str(ex))
        print(traceback.format_exc())
    except:
        pass

def Show(initialTopic="General"):
    """
    Entry point. Builds and shows the TAS Help window.
    initialTopic: name of topic WITHOUT extension (case-insensitive), default "General".
    """
    _Log("Show(initialTopic=" + str(initialTopic) + ") called")
    try:
        # Resolve help directory relative to the active profile
        tashelpDir = jmri.util.FileUtil.getProfilePath() + "/jython/tashelp"
        helpDir = File(tashelpDir)
        _Log("Help dir: " + tashelpDir)

        # Gather topics safely (strip .md or .txt, prefer .md, preserve original case, sort)
        originalTopics = []
        topicExt = {}
        try:
            if helpDir.exists() and helpDir.isDirectory():
                fileArray = helpDir.listFiles()
                if fileArray:
                    lowerMap = {}
                    for f in fileArray:
                        name = f.getName()
                        base = None
                        ext = None
                        if name.endswith(".md"):
                            base = name[:-3]
                            ext = ".md"
                        elif name.endswith(".txt"):
                            base = name[:-4]
                            ext = ".txt"
                        else:
                            continue
                        key = base.lower()
                        if key not in lowerMap:
                            lowerMap[key] = [base, ext]
                        else:
                            if ext == ".md":
                                lowerMap[key] = [base, ext]
                    for key in lowerMap:
                        base, ext = lowerMap[key]
                        originalTopics.append(base)
                        topicExt[base.lower()] = ext
        except Exception as scanEx:
            _LogExc("Directory scan failed", scanEx)
        originalTopics.sort()
        _Log("Topics found: " + str(originalTopics))

        # ---- Frame & status banner ----
        frame = JFrame("Timetable Automation System - Help")
        frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)
        frame.setSize(Dimension(900, 600))
        frame.setLocationRelativeTo(None)   

        statusLabel = JLabel("Select a topic from the list.")
        try:
            statusLabel.setFont(Font(_ThemeFontFamily(), Font.PLAIN, 13))
        except:
            pass
        frame.add(statusLabel, BorderLayout.NORTH)

        # ---- Right pane: content area (scrollable, HTML rendered) ----
        textArea = JEditorPane()
        textArea.setEditable(False)
        textArea.setContentType("text/html")
        try:
            paperRgb = _ThemeRgbStr("TASPAPERCOLOUR", "249,246,238")
            textArea.setBackground(_RgbStrToColor(paperRgb, Color(249, 246, 238)))
        except:
            pass
        try:
            textArea.setFont(Font(_ThemeFontFamily(), Font.PLAIN, 14))
        except:
            pass
        rightScroll = JScrollPane(textArea)

        class _LinkHandler:
            def hyperlinkUpdate(self, e):
                try:
                    if e.getEventType() == HyperlinkEvent.EventType.ACTIVATED:
                        try:
                            url = e.getURL()
                        except:
                            url = None
                        if url is not None:
                            _OpenLink(str(url.toString()))
                        else:
                            try:
                                desc = e.getDescription()
                            except:
                                desc = None
                            if desc is not None:
                                _OpenLink(str(desc))
                except Exception as exH:
                    _LogExc("hyperlinkUpdate failed", exH)

        try:
            textArea.addHyperlinkListener(_LinkHandler())
        except Exception as exL:
            _LogExc("addHyperlinkListener failed", exL)

        # ---- Left pane: search box + topic list (scrollable) ----
        listModel = DefaultListModel()
        for t in originalTopics:
            listModel.addElement(t)

        topicList = JList(listModel)
        topicList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        try:
            topicList.setFont(Font(_ThemeFontFamily(), Font.PLAIN, 13))
        except:
            pass
        listScroll = JScrollPane(topicList)

        searchField = JTextField()
        # --- Placeholder state ---
        PlaceholderText = "Search..."
        PlaceholderGrey = Color(160, 160, 160)
        try:
            NormalTextColour = _RgbStrToColor(_ThemeRgbStr("TASINKCOLOUR", "0,0,0"), Color(0, 0, 0))
        except:
            NormalTextColour = Color(0, 0, 0)
        try:
            searchField.setFont(Font(_ThemeFontFamily(), Font.PLAIN, 13))
        except:
            pass
        IsPlaceholderBox = [True]  # mutable flag for inner closures
        searchField.setText(PlaceholderText)
        searchField.setForeground(PlaceholderGrey)

        # Build the left panel with BorderLayout: search on top, list in center
        leftPanel = JPanel(BorderLayout())
        leftPanel.add(searchField, BorderLayout.NORTH)
        leftPanel.add(listScroll, BorderLayout.CENTER)

        # ---- Split pane: 1/4 left, 3/4 right ----
        splitPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, leftPanel, rightScroll)
        splitPane.setResizeWeight(0.25)         # left takes 1/4 when resizing
        splitPane.setDividerLocation(0.25)      # initial divider at 25% of width
        frame.add(splitPane, BorderLayout.CENTER)

        # ---- Helpers ----
        def LoadContent(topicName):
            """Load topicName.md (or .txt fallback) into the right-hand HTML pane."""
            try:
                mdPath = tashelpDir + "/" + topicName + ".md"
                txtPath = tashelpDir + "/" + topicName + ".txt"
                filePath = None
                isMd = True
                if File(mdPath).exists():
                    filePath = mdPath
                    isMd = True
                elif File(txtPath).exists():
                    filePath = txtPath
                    isMd = False
                else:
                    try:
                        key = str(topicName).lower()
                        if key in topicExt and topicExt[key] == ".txt" and File(txtPath).exists():
                            filePath = txtPath
                            isMd = False
                    except:
                        pass
                if filePath is not None:
                    try:
                        with open(filePath, "r") as f:
                            content = f.read()
                        if isMd:
                            html = _MarkdownToHtml(content)
                        else:
                            html = _TextToHtml(content)
                        textArea.setText(html)
                        statusLabel.setText("Showing help for: " + topicName)
                    except Exception as e:
                        textArea.setText(_WrapHtml("<p>Error reading file: " + _EscapeHtml(str(e)) + "</p>"))
                        statusLabel.setText("Error loading topic.")
                        _LogExc("LoadContent failed (I/O)", e)
                else:
                    textArea.setText(_WrapHtml("<p>Help file not found: " + _EscapeHtml(topicName) + ".md</p>"))
                    statusLabel.setText("Topic missing.")
                    _Log("Missing file: " + mdPath)
                try:
                    textArea.setCaretPosition(0)
                except:
                    pass
            except Exception as exLoad:
                _LogExc("LoadContent failed", exLoad)

        def SelectInitialTopic():
            """Select and load the desired initial topic, case-insensitive."""
            try:
                if listModel.getSize() == 0:
                    textArea.setText(_WrapHtml("<p>No help files found in:<br>" + _EscapeHtml(tashelpDir) + "</p>"))
                    statusLabel.setText("No topics available.")
                    _Log("No topics available")
                    return
                wanted = str(initialTopic).strip().lower()
                for idx in range(listModel.getSize()):
                    item = listModel.getElementAt(idx)
                    if item.lower() == wanted:
                        topicList.setSelectedIndex(idx)
                        LoadContent(item)
                        _Log("Initial topic selected: " + item)
                        return
                # Fallback: first topic
                topicList.setSelectedIndex(0)
                firstItem = listModel.getElementAt(0)
                LoadContent(firstItem)
                _Log("Initial topic fallback: " + firstItem)
            except Exception as exSel:
                _LogExc("SelectInitialTopic failed", exSel)

        # ---- Live filtering (case-insensitive) ----
        def CurrentQuery():
            """Return the current query if not in placeholder; otherwise empty string."""
            return "" if IsPlaceholderBox[0] else searchField.getText().strip().lower()

        def FilterTopics():
            """Filter displayed topics based on searchField content; maintain selection if possible."""
            try:
                query = CurrentQuery()
                prevSelection = topicList.getSelectedValue()
                listModel.clear()

                if len(query) == 0:
                    for t in originalTopics:
                        listModel.addElement(t)
                    if IsPlaceholderBox[0]:
                        statusLabel.setText("Type to filter topics.")
                    else:
                        statusLabel.setText("Select a topic from the list.")
                else:
                    matches = []
                    for t in originalTopics:
                        if query in t.lower():
                            matches.append(t)
                    for t in matches:
                        listModel.addElement(t)
                    if len(matches) == 0:
                        statusLabel.setText("No topics match: \"" + searchField.getText().strip() + "\"")
                    else:
                        statusLabel.setText("Filtered topics: " + str(len(matches)))

                if prevSelection is not None:
                    for idx in range(listModel.getSize()):
                        if listModel.getElementAt(idx) == prevSelection:
                            topicList.setSelectedIndex(idx)
                            return

                if listModel.getSize() > 0 and len(query) > 0:
                    topicList.clearSelection()
            except Exception as exFilter:
                _LogExc("FilterTopics failed", exFilter)

        def SetPlaceholderActive(active):
            try:
                IsPlaceholderBox[0] = True if active else False
                if active:
                    searchField.setText(PlaceholderText)
                    searchField.setForeground(PlaceholderGrey)
                else:
                    searchField.setForeground(NormalTextColour)
            except Exception as exPH:
                _LogExc("SetPlaceholderActive failed", exPH)

        SetPlaceholderActive(True)

        class _DocListener(DocumentListener):
            def insertUpdate(self, e):
                try:
                    if not IsPlaceholderBox[0]:
                        FilterTopics()
                except Exception as ex:
                    _LogExc("insertUpdate failed", ex)
            def removeUpdate(self, e):
                try:
                    if not IsPlaceholderBox[0]:
                        FilterTopics()
                except Exception as ex:
                    _LogExc("removeUpdate failed", ex)
            def changedUpdate(self, e):
                try:
                    if not IsPlaceholderBox[0]:
                        FilterTopics()
                except Exception as ex:
                    _LogExc("changedUpdate failed", ex)

        searchField.getDocument().addDocumentListener(_DocListener())

        class _FocusHandler(FocusAdapter):
            def focusGained(self, e):
                try:
                    if IsPlaceholderBox[0]:
                        SetPlaceholderActive(False)
                        searchField.setText("")  # clear the placeholder text
                except Exception as ex:
                    _LogExc("focusGained failed", ex)
            def focusLost(self, e):
                try:
                    txt = searchField.getText()
                    if txt is None or len(txt.strip()) == 0:
                        SetPlaceholderActive(True)
                        FilterTopics()  # reset list to full when placeholder shows
                except Exception as ex:
                    _LogExc("focusLost failed", ex)

        searchField.addFocusListener(_FocusHandler())

        def OnEnter(e):
            try:
                if not IsPlaceholderBox[0] and listModel.getSize() > 0:
                    topicList.setSelectedIndex(0)
            except Exception as ex:
                _LogExc("OnEnter failed", ex)
        searchField.addActionListener(OnEnter)

        def OnSelection(event):
            try:
                if not event.getValueIsAdjusting():
                    selected = topicList.getSelectedValue()
                    if selected:
                        LoadContent(selected)
            except Exception as ex:
                _LogExc("OnSelection failed", ex)

        topicList.addListSelectionListener(OnSelection)

        # ---- Initial content ----
        SelectInitialTopic()
        FilterTopics()

        # ---- Ensure initial focus is on the topic list, not the search box ----
        # 1) windowOpened hook (primary)
        class _FocusOnOpen(WindowAdapter):
            def windowOpened(self, e):
                try:
                    # Request focus to the list; also ensure selection is visible
                    topicList.requestFocusInWindow()
                    topicList.ensureIndexIsVisible(topicList.getSelectedIndex())
                    _Log("Focus set to topic list on windowOpened")
                except Exception as ex:
                    _LogExc("windowOpened focus set failed", ex)
        frame.addWindowListener(_FocusOnOpen())

        # 2) post-show EDT nudge (secondary fallback)
        def _FocusNudge():
            try:
                topicList.requestFocusInWindow()
                _Log("Focus nudge to topic list after setVisible")
            except Exception as ex:
                _LogExc("Focus nudge failed", ex)
                    
        class _SetIconOnOpen(WindowAdapter):
            def windowOpened(self, e):
                try:
                    # Apply the icon AFTER the frame is realized to avoid decoration/bounds churn
                    frame.setIconImage(TASIcon.CreateClockIconImage(32))
                    _Log("Help icon applied on windowOpened")
                except Exception as iconEx:
                    _LogExc("Help icon set failed on open", iconEx)

        # Register the listener once the frame has been constructed
        frame.addWindowListener(_SetIconOnOpen())    
        # ---- Show window (non-blocking) ----
        frame.setVisible(True)
        SwingUtilities.invokeLater(_FocusNudge)

        _Log("Help window displayed")

    except Exception as e:
        _LogExc("Failed to open help window", e)
        try:
            JOptionPane.showMessageDialog(
                None,
                "Failed to open help window:\n" + str(e),
                "TAS Help Error",
                JOptionPane.ERROR_MESSAGE
            )
        except:
            pass
