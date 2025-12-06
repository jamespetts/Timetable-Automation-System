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

from javax.swing import JFrame, JPanel, JSplitPane, JScrollPane, JList, JTextArea, JLabel
from javax.swing import ListSelectionModel, JOptionPane, JTextField, DefaultListModel, SwingUtilities
from javax.swing.event import DocumentListener
from java.awt import BorderLayout, Dimension, Color
from java.io import File
from java.lang import System
from java.awt.event import FocusAdapter, WindowAdapter
import jmri
import traceback
import TASIcon

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
    initialTopic: name of topic WITHOUT .txt (case-insensitive), default "General".
    """
    _Log("Show(initialTopic=" + str(initialTopic) + ") called")
    try:
        # Resolve help directory relative to the active profile
        tashelpDir = jmri.util.FileUtil.getProfilePath() + "/jython/tashelp"
        helpDir = File(tashelpDir)
        _Log("Help dir: " + tashelpDir)

        # Gather topics safely (strip .txt, preserve original case, sort)
        originalTopics = []
        try:
            if helpDir.exists() and helpDir.isDirectory():
                fileArray = helpDir.listFiles()
                if fileArray:
                    for f in fileArray:
                        name = f.getName()
                        if name.endswith(".txt"):
                            originalTopics.append(name[:-4])
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
        frame.add(statusLabel, BorderLayout.NORTH)

        # ---- Right pane: content area (scrollable) ----
        textArea = JTextArea()
        textArea.setEditable(False)
        textArea.setLineWrap(True)
        textArea.setWrapStyleWord(True)
        rightScroll = JScrollPane(textArea)

        # ---- Left pane: search box + topic list (scrollable) ----
        listModel = DefaultListModel()
        for t in originalTopics:
            listModel.addElement(t)

        topicList = JList(listModel)
        topicList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        listScroll = JScrollPane(topicList)

        searchField = JTextField()
        # --- Placeholder state ---
        PlaceholderText = "Search..."
        PlaceholderGrey = Color(160, 160, 160)
        NormalTextColour = Color(0, 0, 0)
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
            """Load the contents of topicName.txt into the right-hand text area."""
            try:
                filePath = tashelpDir + "/" + topicName + ".txt"
                if File(filePath).exists():
                    try:
                        with open(filePath, "r") as f:
                            content = f.read()
                        textArea.setText(content)
                        statusLabel.setText("Showing help for: " + topicName)
                    except Exception as e:
                        textArea.setText("Error reading file: " + str(e))
                        statusLabel.setText("Error loading topic.")
                        _LogExc("LoadContent failed (I/O)", e)
                else:
                    textArea.setText("Help file not found: " + topicName + ".txt")
                    statusLabel.setText("Topic missing.")
                    _Log("Missing file: " + filePath)
                textArea.setCaretPosition(0)
            except Exception as exLoad:
                _LogExc("LoadContent failed", exLoad)

        def SelectInitialTopic():
            """Select and load the desired initial topic, case-insensitive."""
            try:
                if listModel.getSize() == 0:
                    textArea.setText("No help files found in:\n" + tashelpDir)
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
