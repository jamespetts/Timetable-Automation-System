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
# Purpose:
# Wizard-like UI for creating a working script for a specific timetable row.
# Entry point: ShowWorkingCreator(rn, direction, rowIndex, formsNext)
# Generates scripts under scripts/workings/<Direction>/<RN>.py
import jmri, os
import csv
from java.awt import BorderLayout, GridBagLayout, GridBagConstraints, Insets, Dimension, Font
from javax.swing import (JDialog, JPanel, JLabel, JButton, JCheckBox, JTextField, JTextArea,
                         JScrollPane, JList, JOptionPane, Box, DefaultListModel, ListSelectionModel)
from javax.swing.event import DocumentListener
from java.awt.event import ActionListener
from java.lang import Runnable
from javax.swing import SwingUtilities
from jmri.util import FileUtil

# Optional resolver (profile-first script lookup and profile-based writes)
try:
    import TASPathResolver as TPR
except Exception:
    TPR = None
# Theme helpers (reuse TASSetup style) -- ASCII only
from java.awt import Color

THEME_FONT_FAMILY = "Gill Sans MT"
THEME_TEXT_COLOR = Color(30, 30, 30)
THEME_PAPER = Color(249, 246, 238)
LIST_SEL_BG = Color(210, 225, 235)
LIST_SEL_FG = Color(20, 20, 20)

def ApplyTheme(comp):
    try:
        comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
    except:
        pass

def ApplyTheme(comp):
    try:
        comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
    except:
        pass
        
# Check if any selected TrainInfo is saved with "Set Later" in Dispatcher
def AnyTrainInfoHasSetLater(trainInfoNames):
    # TrainInfoFile reads user TrainInfo XMLs under dispatcher/traininfo/
    from jmri.jmrit.dispatcher import TrainInfoFile  # JMRI API class for reading TrainInfo files
    tif = TrainInfoFile()
    for name in trainInfoNames:
        try:
            # JMRI expects the .xml extension in readTrainInfo(name)
            info = tif.readTrainInfo(name + ".xml")
            # TrainInfo accessor that reflects the "Set Later" option
            if info is not None and info.getTrainFromSetLater():
                return True
        except Exception:
            # If a name can't be read, ignore it; gating should not fail hard
            pass
    return False


# Entry point

# ---------------- Headless workings audit (used by TASWiz) ----------------
# These helpers do not change the GUI behaviour. They are safe to import and call.

def _DefaultWorkingRN(rowNumber):
    # Header row is 1, first data row is 2.
    try:
        return 'TAS' + str(int(rowNumber))
    except:
        return 'TAS'

def _DetermineWorkingDirection(rowDict):
    # Priority: Trigger, then Arr, then Dep.
    try:
        t = (rowDict.get('Trigger', '') or '').strip()
        if t != '':
            return 'Trigger'
    except:
        pass
    try:
        t = (rowDict.get('Arr', '') or '').strip()
        if t != '':
            return 'Arr'
    except:
        pass
    try:
        t = (rowDict.get('Dep', '') or '').strip()
        if t != '':
            return 'Dep'
    except:
        pass
    return None

def _ReadTimetableRows(csvPath):
    rows = []
    try:
        f = open(csvPath, 'r')
        try:
            reader = csv.DictReader(f, delimiter='	')
            for r in reader:
                rows.append(r)
        finally:
            f.close()
    except:
        return []
    return rows

def _BuildFormationMap(rows):
    # destination RN (lower) -> forming RN
    formedBy = {}
    try:
        idx = 2
        for r in rows:
            rnCell = (r.get('Reporting number', '') or '').strip()
            formingRN = rnCell if rnCell != "" else _DefaultWorkingRN(idx)
            formsCell = (r.get('Forms', '') or '').strip()
            if formsCell != "":
                formedBy[str(formsCell).strip().lower()] = formingRN
            idx += 1
    except:
        formedBy = {}
    return formedBy

def _WorkingScriptPath(direction, rn):
    # Return filesystem path for a working script.
    # IMPORTANT: Workings are written under profile:jython (writable). Do not use getScriptsPath() here,
    # because it may point to a non-writable directory (e.g. Program Files on Windows).
    try:
        d = '' if direction is None else str(direction).strip()
        r = '' if rn is None else str(rn).strip()
    except:
        d = ''
        r = ''
    if d == '' or r == '':
        return None
    # Prefer resolver if available
    try:
        if TPR is not None and hasattr(TPR, 'GetProfileJythonDir'):
            pj = TPR.GetProfileJythonDir()
            if pj:
                return os.path.join(str(pj), 'workings', d, r + '.py')
    except:
        pass
    # Fallback to JMRI profile scheme
    try:
        base = FileUtil.getExternalFilename('profile:jython/workings/' + d)
        return os.path.join(str(base), r + '.py')
    except:
        return None

def _IsScriptSyntacticallyValid(path):
    # Best-effort Python syntax check. Treat any exception as invalid.
    try:
        if path is None or (not os.path.isfile(path)):
            return False
        f = open(path, 'r')
        try:
            code = f.read()
        finally:
            f.close()
        if code is None:
            return False
        if len(str(code)) == 0:
            return False
        compile(code, path, 'exec')
        return True
    except:
        return False

def GetWorkingsStatusForTimetable(csvPath):
    # Headless audit for required working scripts for a timetable CSV.
    # Returns: {ok:bool, missing:[...], invalid:[...], total:int}
    missing = []
    invalid = []
    total = 0
    if csvPath is None:
        return {'ok': False, 'missing': [], 'invalid': [], 'total': 0}
    try:
        if not os.path.isfile(csvPath):
            return {'ok': False, 'missing': [], 'invalid': [], 'total': 0}
    except:
        return {'ok': False, 'missing': [], 'invalid': [], 'total': 0}
    rows = _ReadTimetableRows(csvPath)
    formedBy = _BuildFormationMap(rows)
    idx = 2
    for r in rows:
        total += 1
        direction = _DetermineWorkingDirection(r)
        rnCell = (r.get('Reporting number', '') or '').strip()
        rn = rnCell if rnCell != "" else _DefaultWorkingRN(idx)
        formsNext = None
        try:
            key = str(rn).strip().lower()
            if key in formedBy:
                formsNext = formedBy.get(key)
        except:
            formsNext = None
        pth = _WorkingScriptPath(direction, rn)
        if direction is None or pth is None:
            missing.append({'rn': rn, 'direction': direction, 'rowIndex': idx, 'formsNext': formsNext, 'path': pth})
        else:
            try:
                if not os.path.isfile(pth):
                    missing.append({'rn': rn, 'direction': direction, 'rowIndex': idx, 'formsNext': formsNext, 'path': pth})
                elif not _IsScriptSyntacticallyValid(pth):
                    invalid.append({'rn': rn, 'direction': direction, 'rowIndex': idx, 'formsNext': formsNext, 'path': pth})
            except:
                missing.append({'rn': rn, 'direction': direction, 'rowIndex': idx, 'formsNext': formsNext, 'path': pth})
        idx += 1
    ok = (len(missing) == 0) and (len(invalid) == 0) and (total > 0)
    return {'ok': bool(ok), 'missing': missing, 'invalid': invalid, 'total': int(total)}

def ShowWorkingCreator(rn, direction, rowIndex, formsNext=None):
    dlg = JDialog(None, "Create Working", True)
    dlg.setSize(840, 1024)
    dlg.setLayout(BorderLayout())

    # State variables
    lastGeneratedScript = [""]
    trainInfoNames = []
    rosterIds = None
    useTrainInfoRosterOnly = False
    rosterSearchParams = {"id": [], "model": [], "comment": []}

    # Panel container
    root = JPanel()
    root.setLayout(GridBagLayout())
    gbc = GridBagConstraints()
    gbc.insets = Insets(8, 8, 8, 8)
    gbc.fill = GridBagConstraints.HORIZONTAL
    gbc.weightx = 1.0
    gbc.gridx = 0
    gbc.gridy = 0  

    # Heading
    lblHeading = JLabel("Set up working: %s (%s) (timetable row %d)" % (rn, direction, rowIndex))
    lblHeading.setFont(Font(THEME_FONT_FAMILY, Font.BOLD, 16))
    root.add(lblHeading, gbc)
    gbc.gridy += 1
    
    # If this working must be formed from another service's stock, show a banner at the top
    if formsNext is not None:
        lblFormed = JLabel("Formed from the stock of the working %s" % formsNext)
        ApplyTheme(lblFormed)
        # Slightly smaller than main heading; ensure bold and adequate spacing
        lblFormed.setFont(Font(THEME_FONT_FAMILY, Font.BOLD, 14))
        root.add(lblFormed, gbc)
        # Move down so the main heading has its own row and doesn't overlap
        gbc.gridy += 1
 
    # Step 1: TrainInfo selection (dual-list)
    lblTI = JLabel("Select the Train Info files to use for this working (left = available, right = selected in order):")
    ApplyTheme(lblTI)
    root.add(lblTI, gbc)

    gbc.gridy += 1
    availModel = DefaultListModel()
    selectedModel = DefaultListModel()

    # Populate available TrainInfo files
    tiDir = os.path.join(FileUtil.getProfilePath(), "dispatcher", "traininfo")
    if os.path.isdir(tiDir):
        for fname in sorted(os.listdir(tiDir)):
            if fname.lower().endswith(".xml"):
                availModel.addElement(fname[:-4])

    availList = JList(availModel)
    availList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
    selectedList = JList(selectedModel)
    selectedList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)

    availScroll = JScrollPane(availList)
    availScroll.setPreferredSize(Dimension(320, 180))
    availScroll.setMinimumSize(Dimension(320, 180))
    selectedScroll = JScrollPane(selectedList)
    selectedScroll.setPreferredSize(Dimension(320, 180))
    selectedScroll.setMinimumSize(Dimension(320, 180))

    # Buttons between lists
    btnAdd = JButton("Add >>")
    btnRemove = JButton("<< Remove")

    def AddAction(e=None):
        idxs = availList.getSelectedIndices()
        if not idxs: return
        items = [availModel.getElementAt(i) for i in idxs]
        for it in items:
            if it not in [selectedModel.getElementAt(i) for i in range(selectedModel.size())]:
                selectedModel.addElement(it)
        for i in sorted(idxs, reverse=True):
            availModel.remove(i)
        UpdateTrainInfoOnlyAvailability()

    def RemoveAction(e=None):
        idxs = selectedList.getSelectedIndices()
        if not idxs: return
        items = [selectedModel.getElementAt(i) for i in idxs]
        for i in sorted(idxs, reverse=True):
            selectedModel.remove(i)
        for it in items:
            availModel.addElement(it)
        # Sort available list alphabetically
        allAvail = [availModel.getElementAt(i) for i in range(availModel.size())]
        allAvail.sort(key=lambda s: s.lower())
        availModel.removeAllElements()
        for it in allAvail:
            availModel.addElement(it)
        UpdateTrainInfoOnlyAvailability()

    btnAdd.addActionListener(lambda e: AddAction())
    btnRemove.addActionListener(lambda e: RemoveAction())

    # Move Up / Move Down for selected list
    btnUp = JButton("Move Up")
    btnDown = JButton("Move Down")

    def MoveUp():
        idxs = selectedList.getSelectedIndices()
        if not idxs: return
        for idx in idxs:
            if idx > 0:
                val = selectedModel.getElementAt(idx)
                selectedModel.remove(idx)
                selectedModel.insertElementAt(val, idx - 1)
        selectedList.setSelectedIndices([i - 1 for i in idxs if i > 0])
        UpdateTrainInfoOnlyAvailability()

    def MoveDown():
        idxs = selectedList.getSelectedIndices()
        if not idxs: return
        for idx in reversed(idxs):
            if idx < selectedModel.size() - 1:
                val = selectedModel.getElementAt(idx)
                selectedModel.remove(idx)
                selectedModel.insertElementAt(val, idx + 1)
        selectedList.setSelectedIndices([i + 1 for i in idxs if i < selectedModel.size() - 1])
        UpdateTrainInfoOnlyAvailability()

    btnUp.addActionListener(lambda e: MoveUp())
    btnDown.addActionListener(lambda e: MoveDown())

    # Layout: two columns + buttons
    rowPanel = Box.createHorizontalBox()
    rowPanel.add(availScroll)
    btnPanel = Box.createVerticalBox()
    btnPanel.add(btnAdd)
    btnPanel.add(Box.createVerticalStrut(8))
    btnPanel.add(btnRemove)
    rowPanel.add(Box.createHorizontalStrut(12))
    rowPanel.add(btnPanel)
    rowPanel.add(Box.createHorizontalStrut(12))
    rowPanel.add(selectedScroll)
    root.add(rowPanel, gbc)

    # Row for Move Up / Move Down under selected list
    gbc.gridy += 1
    moveRow = Box.createHorizontalBox()
    moveRow.add(Box.createHorizontalStrut(260))  # indent under selected list
    moveRow.add(btnUp)
    moveRow.add(Box.createHorizontalStrut(12))
    moveRow.add(btnDown)
    root.add(moveRow, gbc)  
    
    
    
    # Dynamic gating for TrainInfo-only checkbox + explanation
    def UpdateTrainInfoOnlyAvailability():      
       
        # Current selected TrainInfo files (names without ".xml")
        selectedTI = [selectedModel.getElementAt(i) for i in range(selectedModel.size())]

        # Determine reason for disabling the checkbox (if any)
        disabledReason = None

        # Case 1: formed working -> must disable and explain
        if formsNext is not None:
            disabledReason = "Disabled because this working is formed from the stock of another working."

        # Case 2: no TrainInfo selected -> disable and explain
        elif not selectedTI:
            disabledReason = "Disabled because no TrainInfo files are selected."
              
        elif AnyTrainInfoHasSetLater(selectedTI):
            disabledReason = "Disabled because one or more selected TrainInfo files specify 'Set Later'."

        # Case 3: one or more TrainInfo files have 'set later' roster (requires XML marker)
        # We add a hook here, but DO NOT guess the XML content. Uncomment and complete when we confirm the exact tag/attribute.
        # else:
        #     if AnyTrainInfoHasSetLater(selectedTI):
        #         disabledReason = "Disabled because one or more selected TrainInfo files specify 'set later' for the roster."

        # Apply gating & explanation
        if disabledReason is not None:
            chkUseTI.setEnabled(False)
            chkUseTI.setSelected(False)
            lblTIOnlyExplain.setText(disabledReason)
        else:
            chkUseTI.setEnabled(True)
            lblTIOnlyExplain.setText("")
            
        
        # First apply TrainInfo-only and formed gating, then enforce mutual exclusion
        UpdateRosterControlsEnabled()
        UpdateRosterMutualExclusion()
    
    # Step 2: Roster selection (dual-list like TrainInfo)
    gbc.gridy += 1
    
    # Checkbox for TrainInfo-only roster option
    chkUseTI = JCheckBox("Use only roster entries from TrainInfo files")
    chkUseTI.setSelected(False)
    ApplyTheme(chkUseTI)
    root.add(chkUseTI, gbc)

    # Explanation label directly under the checkbox
    gbc.gridy += 1
    lblTIOnlyExplain = JLabel("")  # Populated by UpdateTrainInfoOnlyAvailability()
    ApplyTheme(lblTIOnlyExplain)
    root.add(lblTIOnlyExplain, gbc)

    # Continue with existing roster dual-list label
    gbc.gridy += 1
    lblRosterDual = JLabel("Select what train(s) to use from the roster (left = available, right = selected in order):")
    ApplyTheme(lblRosterDual)
    root.add(lblRosterDual, gbc)

    
    gbc.gridy += 1
    rosterAvailModel = DefaultListModel()
    rosterSelectedModel = DefaultListModel()

    rosterSelectedModel = DefaultListModel()

    # Populate available roster IDs
    try:
        rosterEntries = jmri.jmrit.roster.Roster.getDefault().getAllEntries()
        for entry in rosterEntries:
            rid = entry.getId()
            if rid and rid.strip() != "":
                rosterAvailModel.addElement(rid)
    except:
        pass

    rosterAvailList = JList(rosterAvailModel)
    rosterAvailList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
    rosterSelectedList = JList(rosterSelectedModel)
    rosterSelectedList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)

    rosterAvailScroll = JScrollPane(rosterAvailList)
    rosterAvailScroll.setPreferredSize(Dimension(320, 180))
    rosterAvailScroll.setMinimumSize(Dimension(320, 180))
    rosterSelectedScroll = JScrollPane(rosterSelectedList)
    rosterSelectedScroll.setPreferredSize(Dimension(320, 180))
    rosterSelectedScroll.setMinimumSize(Dimension(320, 180))

    # Buttons between lists
    btnRosterAdd = JButton("Add >>")
    btnRosterRemove = JButton("<< Remove")

    def RosterAddAction(e=None):
        idxs = rosterAvailList.getSelectedIndices()
        if not idxs: return
        items = [rosterAvailModel.getElementAt(i) for i in idxs]
        for it in items:
            if it not in [rosterSelectedModel.getElementAt(i) for i in range(rosterSelectedModel.size())]:
                rosterSelectedModel.addElement(it)
        for i in sorted(idxs, reverse=True):
            UpdateTrainInfoOnlyAvailability()
            UpdateRosterMutualExclusion()
            rosterAvailModel.remove(i)

    def RosterRemoveAction(e=None):
        idxs = rosterSelectedList.getSelectedIndices()
        if not idxs: return
        items = [rosterSelectedModel.getElementAt(i) for i in idxs]
        for i in sorted(idxs, reverse=True):
            rosterSelectedModel.remove(i)
        for it in items:
            rosterAvailModel.addElement(it)
        # Sort available list alphabetically
        allAvail = [rosterAvailModel.getElementAt(i) for i in range(rosterAvailModel.size())]
        allAvail.sort(key=lambda s: s.lower())
        rosterAvailModel.removeAllElements()
        for it in allAvail:
            rosterAvailModel.addElement(it)
        UpdateTrainInfoOnlyAvailability()
        UpdateRosterMutualExclusion()

    btnRosterAdd.addActionListener(lambda e: RosterAddAction())
    btnRosterRemove.addActionListener(lambda e: RosterRemoveAction())

    # Move Up / Move Down for selected list
    btnRosterUp = JButton("Move Up")
    btnRosterDown = JButton("Move Down")

    def RosterMoveUp():
        idxs = rosterSelectedList.getSelectedIndices()
        if not idxs: return
        for idx in idxs:
            if idx > 0:
                val = rosterSelectedModel.getElementAt(idx)
                rosterSelectedModel.remove(idx)
                rosterSelectedModel.insertElementAt(val, idx - 1)
        rosterSelectedList.setSelectedIndices([i - 1 for i in idxs if i > 0])
        UpdateTrainInfoOnlyAvailability()
        UpdateRosterMutualExclusion()

    def RosterMoveDown():
        idxs = rosterSelectedList.getSelectedIndices()
        if not idxs: return
        for idx in reversed(idxs):
            if idx < rosterSelectedModel.size() - 1:
                val = rosterSelectedModel.getElementAt(idx)
                rosterSelectedModel.remove(idx)
                rosterSelectedModel.insertElementAt(val, idx + 1)
        rosterSelectedList.setSelectedIndices([i + 1 for i in idxs if i < rosterSelectedModel.size() - 1])
        UpdateTrainInfoOnlyAvailability()
        UpdateRosterMutualExclusion()

    btnRosterUp.addActionListener(lambda e: RosterMoveUp())
    btnRosterDown.addActionListener(lambda e: RosterMoveDown())

    # Layout: two columns + buttons
    rosterRowPanel = Box.createHorizontalBox()
    rosterRowPanel.add(rosterAvailScroll)
    rosterBtnPanel = Box.createVerticalBox()
    rosterBtnPanel.add(btnRosterAdd)
    rosterBtnPanel.add(Box.createVerticalStrut(8))
    rosterBtnPanel.add(btnRosterRemove)
    rosterRowPanel.add(Box.createHorizontalStrut(12))
    rosterRowPanel.add(rosterBtnPanel)
    rosterRowPanel.add(Box.createHorizontalStrut(12))
    rosterRowPanel.add(rosterSelectedScroll)
    root.add(rosterRowPanel, gbc)

    # Row for Move Up / Move Down under selected list
    gbc.gridy += 1
    rosterMoveRow = Box.createHorizontalBox()
    rosterMoveRow.add(Box.createHorizontalStrut(260))  # indent under selected list
    rosterMoveRow.add(btnRosterUp)
    rosterMoveRow.add(Box.createHorizontalStrut(12))
    rosterMoveRow.add(btnRosterDown)
    root.add(rosterMoveRow, gbc)    
    # Hook the checkbox to re-apply greying when toggled; initial gating is called later
    chkUseTI.addActionListener(lambda e: UpdateRosterMutualExclusion())
    lblSearch = JLabel("When this working runs, search for train with:")

    ApplyTheme(lblSearch)
    root.add(lblSearch, gbc)
    gbc.gridy += 1

    # Helper to build one token entry block
    def MakeTokenBlock(labelText):
        block = Box.createVerticalBox()

        # Header row: label + Required checkbox
        header = Box.createHorizontalBox()
        lbl = JLabel(labelText)
        chkReq = JCheckBox("Required")
        ApplyTheme(lbl)
        ApplyTheme(chkReq)
        header.add(lbl)
        header.add(Box.createHorizontalStrut(8))
        header.add(chkReq)

        # Entry row: text field + Add button
        entryRow = Box.createHorizontalBox()
        txtToken = JTextField(12)
        btnAdd = JButton("Add")
        ApplyTheme(btnAdd)
        entryRow.add(txtToken)
        entryRow.add(Box.createHorizontalStrut(6))
        entryRow.add(btnAdd)

        # Token list: multi-line display + Remove button
        tokensModel = DefaultListModel()
        lstTokens = JList(tokensModel)
        lstTokens.setVisibleRowCount(6)
        lstTokens.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
        scroll = JScrollPane(lstTokens)
        scroll.setPreferredSize(Dimension(180, 160))
        scroll.setMinimumSize(Dimension(180, 160))
        btnRemove = JButton("Remove")
        ApplyTheme(btnRemove)

        # Actions
        def DoAdd(e=None):
            token = txtToken.getText().strip()
            if token == "":
                return
            if token not in [tokensModel.getElementAt(i) for i in range(tokensModel.size())]:
                tokensModel.addElement(token)
            txtToken.setText("")
            UpdateRosterMutualExclusion()

        def DoRemove(e=None):
            idxs = lstTokens.getSelectedIndices()
            if not idxs:
                return
            for i in sorted(idxs, reverse=True):
                tokensModel.remove(i)
            UpdateRosterMutualExclusion()

        btnAdd.addActionListener(lambda e: DoAdd())
        btnRemove.addActionListener(lambda e: DoRemove())

        # Assemble block
        block.add(header)
        block.add(Box.createVerticalStrut(4))
        block.add(entryRow)
        block.add(Box.createVerticalStrut(4))
        block.add(scroll)
        block.add(Box.createVerticalStrut(4))
        block.add(btnRemove)

        return block, tokensModel, chkReq, txtToken, btnAdd, btnRemove

    # Build three blocks (capture entry field and buttons so we can disable them)
    idBlock, idTokensModel, chkID, idTxtToken, idBtnAdd, idBtnRemove = MakeTokenBlock("ID contains:")
    modelBlock, modelTokensModel, chkModel, modelTxtToken, modelBtnAdd, modelBtnRemove = MakeTokenBlock("Model contains:")
    commentBlock, commentTokensModel, chkComment, commentTxtToken, commentBtnAdd, commentBtnRemove = MakeTokenBlock("Comment contains:")

    # Layout: three blocks side by side
    searchPanel = Box.createHorizontalBox()
    searchPanel.add(idBlock)
    searchPanel.add(Box.createHorizontalStrut(12))
    searchPanel.add(modelBlock)
    searchPanel.add(Box.createHorizontalStrut(12))
    searchPanel.add(commentBlock)

    gbc.fill = GridBagConstraints.HORIZONTAL
    gbc.weighty = 0
    root.add(searchPanel, gbc)  
    
    def UpdateRosterControlsEnabled():
        # If this working is formed from another service's stock, disable BOTH picking methods
        if formsNext is not None:
            # Roster dual-list controls
            try:
                rosterAvailList.setEnabled(False)
                rosterSelectedList.setEnabled(False)
                btnRosterAdd.setEnabled(False)
                btnRosterRemove.setEnabled(False)
                btnRosterUp.setEnabled(False)
                btnRosterDown.setEnabled(False)
            except Exception:
                pass

            # Token entry blocks: disable text fields and buttons
            try:
                idTxtToken.setEnabled(False)
                idBtnAdd.setEnabled(False)
                idBtnRemove.setEnabled(False)

                modelTxtToken.setEnabled(False)
                modelBtnAdd.setEnabled(False)
                modelBtnRemove.setEnabled(False)

                commentTxtToken.setEnabled(False)
                commentBtnAdd.setEnabled(False)
                commentBtnRemove.setEnabled(False)
            except Exception:
                pass

            # TrainInfo-only checkbox must be disabled and unchecked
            try:
                chkUseTI.setEnabled(False)
                chkUseTI.setSelected(False)
            except Exception:
                pass

            # Nothing else to do; we are forcing disablement due to formation
            return

        # Else: normal gating by TrainInfo-only checkbox
        disable = chkUseTI.isSelected()

        # Roster dual-list controls
        rosterAvailList.setEnabled(not disable)
        rosterSelectedList.setEnabled(not disable)
        btnRosterAdd.setEnabled(not disable)
        btnRosterRemove.setEnabled(not disable)
        btnRosterUp.setEnabled(not disable)
        btnRosterDown.setEnabled(not disable)

        # Token entry blocks: explicitly disable text fields and buttons
        idTxtToken.setEnabled(not disable)
        idBtnAdd.setEnabled(not disable)
        idBtnRemove.setEnabled(not disable)

        modelTxtToken.setEnabled(not disable)
        modelBtnAdd.setEnabled(not disable)
        modelBtnRemove.setEnabled(not disable)

        commentTxtToken.setEnabled(not disable)
        commentBtnAdd.setEnabled(not disable)
        commentBtnRemove.setEnabled(not disable)    
    
    def UpdateRosterMutualExclusion():
        """
        Enforce mutual exclusivity between roster selection and search tokens:
        - If TrainInfo-only is checked: disable everything (handled by UpdateRosterControlsEnabled).
        - Else if any token is present: disable roster controls, enable token controls.
        - Else if any roster entry is selected: disable token controls, enable roster controls.
        - Else: enable both sets.
        """
        
        # If this working is formed from another service's stock, never allow either method.
        # Delegate to UpdateRosterControlsEnabled() which force-disables both sets and return.
        if formsNext is not None:
            UpdateRosterControlsEnabled()
            return
        
        # Apply TI-only gating first
        if chkUseTI.isSelected():
            UpdateRosterControlsEnabled()
            return

        tokensExist = (idTokensModel.size() > 0 or
                       modelTokensModel.size() > 0 or
                       commentTokensModel.size() > 0)

        rosterSelectedExist = (rosterSelectedModel.size() > 0)

        # Decide enablement
        enableRoster = (not tokensExist)
        enableSearch = (not rosterSelectedExist)

        # Roster dual-list controls
        rosterAvailList.setEnabled(enableRoster)
        rosterSelectedList.setEnabled(enableRoster)
        btnRosterAdd.setEnabled(enableRoster)
        btnRosterRemove.setEnabled(enableRoster)
        btnRosterUp.setEnabled(enableRoster)
        btnRosterDown.setEnabled(enableRoster)

        # Token entry blocks
        idTxtToken.setEnabled(enableSearch)
        idBtnAdd.setEnabled(enableSearch)
        idBtnRemove.setEnabled(enableSearch)

        modelTxtToken.setEnabled(enableSearch)
        modelBtnAdd.setEnabled(enableSearch)
        modelBtnRemove.setEnabled(enableSearch)

        commentTxtToken.setEnabled(enableSearch)
        commentBtnAdd.setEnabled(enableSearch)
        commentBtnRemove.setEnabled(enableSearch)

    
    # Step 3: Preview and Save
    gbc.gridy += 1
    btnRow = Box.createHorizontalBox()
    btnGenerate = JButton("Generate Preview")
    btnSave = JButton("Save Script")
    btnCancel = JButton("Cancel")
    btnRow.add(btnGenerate)
    btnRow.add(Box.createHorizontalStrut(12))
    btnRow.add(btnSave)
    btnRow.add(Box.createHorizontalStrut(12))
    btnRow.add(btnCancel)
    root.add(btnRow, gbc)   
    
    # Logic: Generate script text; optionally show preview when requested
    def GenerateScript(showPreview=True, silent=False):
        selectedTI = [selectedList.getModel().getElementAt(i) for i in range(selectedList.getModel().getSize())]
        if not selectedTI:
            if not silent:
                JOptionPane.showMessageDialog(dlg, "Select at least one TrainInfo file.", "Error", JOptionPane.ERROR_MESSAGE)
            return None

        trainInfoNamesList = "[" + ",".join(['"%s"' % x for x in selectedTI]) + "]"
        scriptLines = []
        idTokens = []
        modelTokens = []
        commentTokens = []

        scriptLines.append("# Working script for RN %s (%s)" % (rn, direction))
        scriptLines.append("import jmri, os")
        scriptLines.append("from jmri.util import FileUtil")
        scriptLines.append("")
        scriptLines.append("# Get the scripts path and load the scripts")
        scriptLines.append("scriptsPath = jmri.util.FileUtil.getScriptsPath()")
        scriptLines.append("try:")
        scriptLines.append("    import TASPathResolver as TPR")
        scriptLines.append("    def _TasRead(n):")
        scriptLines.append("        p = TPR.ResolveScriptReadPath(n)")
        scriptLines.append("        return p if p is not None else os.path.join(scriptsPath, n)")
        scriptLines.append("except:")
        scriptLines.append("    def _TasRead(n):")
        scriptLines.append("        return os.path.join(scriptsPath, n)")
        scriptLines.append("execfile(_TasRead('startTrain.py'), globals())")
        scriptLines.append("execfile(_TasRead('trainFinder.py'), globals())")

        # Determine if roster search will be needed based on multi-token selectors
        idHasTokens = idTokensModel.size() > 0
        modelHasTokens = modelTokensModel.size() > 0
        commentHasTokens = commentTokensModel.size() > 0

        if not chkUseTI.isSelected() and (idHasTokens or modelHasTokens or commentHasTokens):
            scriptLines.append("execfile(_TasRead('RosterSearch.py'), globals())")
        else:
            scriptLines.append("# execfile(_TasRead('RosterSearch.py'), globals()) # Uncomment if using rosterSearch")

        scriptLines.append("")
        scriptLines.append("traininfoNames = %s" % trainInfoNamesList)

        if chkUseTI.isSelected():
            scriptLines.append("rosterEntry = None")
            scriptLines.append("rosterIds = None")
        else:
            # Collect tokens from the multi-token selectors
            idTokens = [idTokensModel.getElementAt(i) for i in range(idTokensModel.size())]
            modelTokens = [modelTokensModel.getElementAt(i) for i in range(modelTokensModel.size())]
            commentTokens = [commentTokensModel.getElementAt(i) for i in range(commentTokensModel.size())]

            if idTokens or modelTokens or commentTokens:
                # Helper to format lists for script according to RosterSearch.py convention
                def BuildList(tokens, required):
                    if not tokens:
                        return "None"
                    if required:
                        return "[None," + ",".join(['\"%s\"' % t for t in tokens]) + "]"
                    return "[" + ",".join(['\"%s\"' % t for t in tokens]) + "]"

                scriptLines.append(
                    "rosterIds = rosterSearch(%s, %s, %s)" % (
                        BuildList(idTokens, chkID.isSelected()),
                        BuildList(modelTokens, chkModel.isSelected()),
                        BuildList(commentTokens, chkComment.isSelected())
                    )
                )
            else:
                # Fallback to manually selected roster IDs (if any)
                selectedRoster = [rosterSelectedModel.getElementAt(i) for i in range(rosterSelectedModel.size())]
                if selectedRoster:
                    scriptLines.append("rosterIds = [" + ",".join(['\"%s\"' % r for r in selectedRoster]) + "]")
                else:
                    scriptLines.append("rosterIds = None")

        tfCall = "rosterEntry, traininfoName = trainFinder(traininfoNames, rosterIds"
        if formsNext is not None:
            tfCall += ", reportingNumber)"
        else:
            tfCall += ")"
        scriptLines.append(tfCall)

        scriptLines.append("activeTrain = startTrain(traininfoName, rosterEntry, reportingNumber, direction, formsNext)")

        previewText = "\n".join(scriptLines)
        lastGeneratedScript[0] = previewText

        # Show preview only when explicitly requested
        if showPreview:
            previewDlg = JDialog(dlg, "Preview Generated Script", True)
            previewDlg.setSize(1200, 640)
            previewDlg.setLayout(BorderLayout())
            textArea = JTextArea(previewText)
            textArea.setEditable(False)
            scrollPane = JScrollPane(textArea)
            previewDlg.add(scrollPane, BorderLayout.CENTER)
            textArea.setCaretPosition(0)  # Ensure scroll starts at top
            btnClose = JButton("Close")
            btnClose.addActionListener(lambda e: previewDlg.dispose())
            previewDlg.add(btnClose, BorderLayout.SOUTH)
            previewDlg.setLocationRelativeTo(dlg)
            previewDlg.setVisible(True)

        return previewText

    # Wire the preview button (explicit preview)
    btnGenerate.addActionListener(lambda e: GenerateScript(showPreview=True, silent=False))
    
    def SaveScript():
        # If nothing generated yet (or was cleared), generate now (no preview here)
        code = (lastGeneratedScript[0] or "").strip()
        if not code:
            try:
                code = (GenerateScript(showPreview=False, silent=False) or "").strip()
            except Exception:
                code = ""

        if not code:
            JOptionPane.showMessageDialog(dlg,
                "Cannot save: script generation failed. Please select at least one TrainInfo file.",
                "Error", JOptionPane.ERROR_MESSAGE)
            return
        # Workings are written under profile:jython (writable). Do not use getScriptsPath() as a fallback.
        targetDir = None
        try:
            if TPR is not None and hasattr(TPR, 'GetWorkingsWriteDir'):
                targetDir = TPR.GetWorkingsWriteDir(direction)
        except Exception:
            targetDir = None
        if targetDir is None:
            try:
                # profile:jython/workings/<direction>
                targetDir = FileUtil.getExternalFilename('profile:jython/workings/' + str(direction))
            except Exception:
                targetDir = None
        if targetDir is None:
            JOptionPane.showMessageDialog(dlg,
                'Cannot save: workings folder could not be resolved.\n' +
                'Please ensure that your JMRI profile is writable.',
                'Error', JOptionPane.ERROR_MESSAGE)
            return
        if not os.path.isdir(targetDir):
            try:
                os.makedirs(targetDir)
            except Exception as exMk:
                JOptionPane.showMessageDialog(dlg, 'Cannot create workings folder: ' + str(exMk), 'Error', JOptionPane.ERROR_MESSAGE)
                return
        targetFile = os.path.join(targetDir, rn + '.py')

        try:
            with open(targetFile, "w") as f:
                f.write(code)
            # Silent success: just close the creator window
            dlg.dispose()
        except Exception as ex:
            JOptionPane.showMessageDialog(dlg, "Failed to save script: " + str(ex), "Error", JOptionPane.ERROR_MESSAGE)


    btnSave.addActionListener(lambda e: SaveScript())
    btnCancel.addActionListener(lambda e: dlg.dispose())   
    
    # Apply initial gating now that all controls and gating functions exist
    UpdateTrainInfoOnlyAvailability()
    dlg.getContentPane().add(root, BorderLayout.CENTER)
    dlg.setLocationRelativeTo(None)
    
    # Set window icon using TASIcon utility
    try:
        from TASIcon import SetFrameClockIcon
        SetFrameClockIcon(dlg, 32)  # 32px icon size
    except Exception as ex:
        print("[WorkingCreator] Failed to set icon: " + str(ex))
    
    # --- Auto-generate a preview once on open (populates lastGeneratedScript) ---
    try:
        GenerateScript(showPreview=False, silent=True)
    except Exception:
        # If generation fails (e.g., no TrainInfo selected yet), we still show the dialog
        pass

    dlg.setVisible(True)
