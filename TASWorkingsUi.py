# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>.
#
# Shared Workings UI for TASSetup and TASWiz.
#
# Provides a single implementation of the Workings editor UI so both TASSetup and the setup wizard can host it.
# Designed for JMRI 5.14 + Jython (Python 2.7). ASCII-only.

import os
import csv
import java
import traceback

from java.awt import BorderLayout, Color, Dimension, Font, GridBagConstraints, GridBagLayout, Insets
from java.lang import Runnable
from java.io import File

from javax.swing import (Box, JButton, JDialog, JList, JOptionPane, JPanel, JScrollPane,
                         JTextPane, ListSelectionModel, SwingUtilities, DefaultListModel,
                         DefaultListCellRenderer, BorderFactory)
from javax.swing.event import DocumentListener, ListSelectionListener

# JMRI
import jmri

# Optional resolver (profile-first working script lookup)
try:
    import TASPathResolver as TPR
except Exception:
    TPR = None

TAG = "[TASWorkingsUi] "

def _SafeStr(x):
    try:
        return '' if x is None else str(x)
    except:
        return ''

class RunnableAdapter(Runnable):
    def __init__(self, func):
        self.Func = func
    def run(self):
        self.Func()

class WorkingsUiController(object):
    def __init__(self):
        self.WorkingsDirty = False
        self.WorkingsCurrentItem = None
        self.WorkingsSuppressDirty = False
        self.WorkingsRightPanel = None
        self._Host = None
    def HasUnsavedChanges(self):
        try:
            return bool(self.WorkingsDirty)
        except:
            return False

class WorkingItem(object):
    # Lightweight record: RN + Direction + RowIndex + ScriptPath + HasScript + ValidScript
    def __init__(self, rn, direction, rowIndex, scriptPath, hasScript, validScript, timeText=""):
        self.RN = rn
        self.Direction = direction
        self.RowIndex = rowIndex
        self.ScriptPath = scriptPath
        self.HasScript = hasScript
        self.ValidScript = validScript
        self.IsExtra = False
        self.Time = timeText
    def Label(self):
        # Example: "2G56 (Trigger) - row 42 [12:34]"
        timePart = (" [" + self.Time + "]") if self.Time else ""
        try:
            return "%s (%s) - row %d%s" % (self.RN, self.Direction, int(self.RowIndex), timePart)
        except:
            return "%s (%s)" % (self.RN, self.Direction)

class PyCodeEditor(JTextPane):
    def __init__(self, themeFontFamily, applyThemeFunc=None):
        JTextPane.__init__(self)
        try:
            if applyThemeFunc is not None:
                applyThemeFunc(self)
        except:
            pass
        try:
            self.setFont(Font(themeFontFamily, Font.PLAIN, 13))
        except:
            pass
        # Plain UI background (match general Swing UI, not paper theme)
        try:
            from javax.swing import UIManager
            bg = UIManager.getColor("TextArea.background")
            if bg is not None:
                self.setBackground(bg)
            else:
                self.setBackground(Color(240, 240, 240))
        except:
            self.setBackground(Color(240, 240, 240))
        try:
            self.setCaretColor(Color(40, 40, 40))
        except:
            pass
        try:
            self.setOpaque(True)
        except:
            pass

def _DefaultMakeWrappedLabel(themeFontFamily, themeTextColor, themeAccent, htmlText, widthPx=520, lineHeight=1.20, bold=False):
    # Fallback wrapper if caller doesn't provide MakeWrappedLabel.
    from javax.swing import JLabel
    try:
        html = "<html><div style='width:%dpx; line-height:%s;'>%s</div></html>" % (int(widthPx), str(float(lineHeight)), str(htmlText))
    except:
        html = "<html>%s</html>" % str(htmlText)
    lbl = JLabel(html)
    try:
        style = Font.BOLD if bold else Font.PLAIN
        size = 16 if bold else 13
        lbl.setFont(Font(themeFontFamily, style, size))
        lbl.setForeground(themeAccent if bold else themeTextColor)
    except:
        pass
    return lbl

def BuildWorkingsPanel(hostFrame,
                       getTimetablePathFunc,
                       profileJythonFilePathFunc,
                       applyThemeFunc,
                       makePaperPanelFunc,
                       makeHeadingFunc,
                       makeWrappedLabelFunc,
                       themePaper,
                       themeFontFamily,
                       themeTextColor,
                       listSelBg,
                       listSelFg,
                       logInfoFunc,
                       logWarnFunc,
                       logErrorFunc):
    """
    Build and return (panel, controller) for the Workings UI.

    hostFrame: parent window for dialogs.
    getTimetablePathFunc: function -> absolute path to current timetable .csv, or None.
    profileJythonFilePathFunc: function(name) -> absolute path under profile:jython.

    The remaining args allow TASSetup and TASWiz to keep their own theme and helpers.
    """

    controller = WorkingsUiController()
    controller._Host = hostFrame

    # Guard helpers
    def LogInfo(msg):
        try:
            logInfoFunc(msg)
        except:
            try:
                print(TAG + _SafeStr(msg))
            except:
                pass

    def LogWarn(msg, alsoDialog=False):
        try:
            logWarnFunc(msg, alsoDialog=alsoDialog)
            return
        except:
            pass
        try:
            print(TAG + "WARN: " + _SafeStr(msg))
        except:
            pass
        if alsoDialog:
            try:
                JOptionPane.showMessageDialog(hostFrame, _SafeStr(msg), "Warning", JOptionPane.WARNING_MESSAGE)
            except:
                pass

    def LogError(msg, ex=None, alsoDialog=True):
        try:
            logErrorFunc(msg, ex=ex, alsoDialog=alsoDialog)
            return
        except:
            pass
        try:
            print(TAG + "ERROR: " + _SafeStr(msg))
            if ex is not None:
                print(TAG + "TRACEBACK:")
                traceback.print_exc()
        except:
            pass
        if alsoDialog:
            try:
                JOptionPane.showMessageDialog(hostFrame, _SafeStr(msg), "Error", JOptionPane.ERROR_MESSAGE)
            except:
                pass

    # Fallback wrapped label
    def MakeWrappedLabel(txt, widthPx=520, lineHeight=1.20, bold=False):
        try:
            if makeWrappedLabelFunc is not None:
                return makeWrappedLabelFunc(txt, widthPx=widthPx, lineHeight=lineHeight, bold=bold)
        except:
            pass
        return _DefaultMakeWrappedLabel(themeFontFamily, themeTextColor, Color(80, 80, 80), txt, widthPx=widthPx, lineHeight=lineHeight, bold=bold)

    # Timetable + WorkingCreator helpers
    def TimetablePath():
        try:
            return getTimetablePathFunc()
        except:
            return None

    def LoadWorkingCreatorModule():
        try:
            import imp
            pth = None
            try:
                pth = profileJythonFilePathFunc('WorkingCreator.py')
            except:
                pth = None
            if not pth:
                return None
            try:
                if not os.path.isfile(pth):
                    return None
            except:
                return None
            return imp.load_source('WorkingCreator_shared_i', pth)
        except Exception as ex:
            LogWarn('Working creator module load failed: ' + _SafeStr(ex), alsoDialog=False)
            return None

    def _NormRN(s):
        try:
            return _SafeStr(s).strip().upper()
        except:
            return ""

    def _MakeDefaultRN(rowNumber):
        # Header row is 1, first data row is 2 -> TAS<rowNumber>
        try:
            return "TAS" + str(int(rowNumber))
        except:
            return "TAS"

    def DetermineDirection(header, row):
        # If trigger and dep present but no arr -> treat as trigger-only
        try:
            triggerPresent = ('Trigger' in header) and (_SafeStr(row.get('Trigger', '')).strip() != '')
        except:
            triggerPresent = False
        try:
            arrPresent = ('Arr' in header) and (_SafeStr(row.get('Arr', '')).strip() != '')
        except:
            arrPresent = False
        try:
            depPresent = ('Dep' in header) and (_SafeStr(row.get('Dep', '')).strip() != '')
        except:
            depPresent = False
        if triggerPresent:
            return 'Trigger'
        if arrPresent:
            return 'Arr'
        if depPresent:
            return 'Dep'
        return None


    # ---------------- Workings folder selection (no mixing) ----------------
    # Policy: use profile:jython/workings if it contains ANY .py scripts.
    # Only if it contains NONE do we fall back to scriptsPath/workings.
    # Never mix between locations in a single refresh.
    def _HasAnyPyUnder(dirPath):
        try:
            if dirPath is None:
                return False
            p = str(dirPath)
            if (not os.path.isdir(p)):
                return False
            for root, dirs, files in os.walk(p):
                for fn in files:
                    try:
                        if str(fn).lower().endswith('.py'):
                            return True
                    except:
                        pass
            return False
        except:
            return False

    def _GetWorkingsDirsReport():
        # Returns dict: newDir, legacyDir, newHasAny, legacyHasAny, chosenDir, chosenIsLegacy
        newDir = None
        try:
            # Prefer resolver for profile path if available
            if TPR is not None and hasattr(TPR, 'GetProfileJythonDir'):
                pj = TPR.GetProfileJythonDir()
                if pj:
                    newDir = os.path.join(str(pj), 'workings')
        except:
            newDir = None
        if not newDir:
            try:
                from jmri.util import FileUtil as _FU
                newDir = _FU.getExternalFilename('profile:jython/workings')
            except:
                newDir = None
        legacyDir = None
        try:
            rep = _GetWorkingsDirsReport()
            baseDir = rep.get('chosenDir')
            if baseDir is None or str(baseDir).strip() == '':
                return items
            baseDir = str(baseDir)
            if scriptsPath:
                legacyDir = os.path.join(str(scriptsPath), 'workings')
        except:
            legacyDir = None
        newHasAny = _HasAnyPyUnder(newDir)
        legacyHasAny = _HasAnyPyUnder(legacyDir)
        if newHasAny:
            chosenDir = newDir
            chosenIsLegacy = False
        else:
            chosenDir = legacyDir
            chosenIsLegacy = True
        return {
            'newDir': newDir,
            'legacyDir': legacyDir,
            'newHasAny': newHasAny,
            'legacyHasAny': legacyHasAny,
            'chosenDir': chosenDir,
            'chosenIsLegacy': chosenIsLegacy,
        }

    def _WorkingsLocationNoteLines():
        # User-facing lines explaining where workings are read from.
        try:
            r = _GetWorkingsDirsReport()
        except:
            r = {}
        newDir = r.get('newDir', None)
        legacyDir = r.get('legacyDir', None)
        newHasAny = bool(r.get('newHasAny', False))
        legacyHasAny = bool(r.get('legacyHasAny', False))
        chosenDir = r.get('chosenDir', None)
        chosenIsLegacy = bool(r.get('chosenIsLegacy', False))
        lines = []
        if chosenDir is None or str(chosenDir).strip() == '':
            lines.append('No workings folder could be found.')
            if newDir and str(newDir).strip() != '':
                lines.append('Main workings folder: ' + str(newDir))
            if legacyDir and str(legacyDir).strip() != '':
                lines.append('Legacy workings folder: ' + str(legacyDir))
            return lines
        if chosenIsLegacy:
            lines.append('Workings are being read from the legacy folder: ' + str(chosenDir))
            if newDir and str(newDir).strip() != '':
                if newHasAny:
                    lines.append('Note: workings were also found in the main folder: ' + str(newDir))
                else:
                    lines.append('This is because no workings were found in the main folder: ' + str(newDir))
        else:
            lines.append('Working scripts are being read from the main folder: ' + str(chosenDir))
            if legacyDir and str(legacyDir).strip() != '' and legacyHasAny:
                lines.append('Working scripts were also found in the legacy folder: ' + str(legacyDir))
                lines.append('Those legacy workings are ignored to avoid mixing files from two places.')
            elif legacyDir and str(legacyDir).strip() != '':
                lines.append('No workings were found in the legacy folder: ' + str(legacyDir))
        return lines
    def ValidateWorkingScriptReasons(path):
        # Return a list of specific validation failures for this script.
        # If list is empty, the script is valid.
        reasons = []
        try:
            if not (path and os.path.isfile(path)):
                reasons.append('Script file not found.')
                return reasons
            with open(path, 'r') as f:
                raw = f.read()
            lines = raw.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        except Exception as ex:
            reasons.append('Error reading script: ' + _SafeStr(ex))
            return reasons

        def isIgnored(line):
            s = (_SafeStr(line)).strip()
            return (s == '' or s.startswith('#') or s.startswith('import ') or s.startswith('from '))

        importHeaderIdx = None
        importFileUtil = None
        scriptsPathLine = None
        execStartTrainLine = None
        execTrainFinderLine = None
        for idx, ln in enumerate(lines):
            s = (_SafeStr(ln)).strip()
            # Flexible detection: "import jmri, os, random" (order-insensitive)
            if importHeaderIdx is None and s.startswith('import '):
                listStr = s[7:].strip()
                tokens = [t.strip() for t in listStr.split(',') if t.strip() != '']
                baseNames = []
                for t in tokens:
                    parts = t.split()
                    base = parts[0].strip().lower() if parts else ''
                    baseNames.append(base)
                if ('jmri' in baseNames) and ('os' in baseNames):
                    importHeaderIdx = idx
            if importFileUtil is None and s == 'from jmri.util import FileUtil':
                importFileUtil = idx
            if scriptsPathLine is None and s == 'scriptsPath = jmri.util.FileUtil.getScriptsPath()':
                scriptsPathLine = idx
            if execStartTrainLine is None and s == "execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())":
                execStartTrainLine = idx
            if execTrainFinderLine is None and s == "execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())":
                execTrainFinderLine = idx

        firstReal = None
        for idx, ln in enumerate(lines):
            if not isIgnored(ln):
                firstReal = idx
                break

        if importHeaderIdx is None:
            reasons.append("Missing header import list containing 'jmri' and 'os' (e.g., 'import jmri, os')")
        if importFileUtil is None:
            reasons.append('Missing header line: from jmri.util import FileUtil')
        if firstReal is not None:
            if importHeaderIdx is not None and not (importHeaderIdx < firstReal):
                reasons.append("Header imports must appear before any real code (line with both 'jmri' and 'os')")
            if importFileUtil is not None and not (importFileUtil < firstReal):
                reasons.append("Header imports must appear before any real code: 'from jmri.util import FileUtil'")

        if scriptsPathLine is None:
            reasons.append('Missing loader line: scriptsPath = jmri.util.FileUtil.getScriptsPath()')
        if execStartTrainLine is None:
            reasons.append("Missing loader line: execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())")

        if scriptsPathLine is not None:
            if importHeaderIdx is not None and scriptsPathLine < importHeaderIdx:
                reasons.append('scriptsPath must appear after the header import line containing jmri and os')
            if importFileUtil is not None and scriptsPathLine < importFileUtil:
                reasons.append('scriptsPath must appear after the header imports: from jmri.util import FileUtil')

        firstTfCall = None
        for idx, ln in enumerate(lines):
            s = (_SafeStr(ln)).strip()
            if s.startswith('#'):
                continue
            if 'trainFinder(' in s:
                firstTfCall = idx
                break
        if firstTfCall is not None:
            if execTrainFinderLine is None or not (execTrainFinderLine < firstTfCall):
                reasons.append("trainFinder( call found without prior execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())")

        startTrainCallAfter = False
        if execStartTrainLine is not None:
            for idx, ln in enumerate(lines):
                s = (_SafeStr(ln)).strip()
                if s.startswith('#'):
                    continue
                if 'startTrain(' in s and idx > execStartTrainLine:
                    startTrainCallAfter = True
                    break
        if execStartTrainLine is not None and not startTrainCallAfter:
            reasons.append("No startTrain( call after execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())")

        return reasons

    def ValidateWorkingScript(path):
        try:
            return len(ValidateWorkingScriptReasons(path)) == 0
        except:
            return False

    def ExtractWorkings():
        items = []
        path = TimetablePath()
        if path is None or not os.path.isfile(path):
            return items
        try:
            rep = _GetWorkingsDirsReport()
            baseDir = rep.get('chosenDir')
            if baseDir is None or str(baseDir).strip() == '':
                return
            baseDir = str(baseDir)
            with open(path, 'r') as f:
                reader = csv.DictReader(f, delimiter='\t')
                header = reader.fieldnames or []
                rows = list(reader)

            formedBy = {}
            for idx, r in enumerate(rows, start=2):
                rnCell = (_SafeStr(r.get('Reporting number', ''))).strip()
                formingRN = rnCell if rnCell != '' else _MakeDefaultRN(idx)
                formsCell = (_SafeStr(r.get('Forms', ''))).strip()
                if formsCell != '':
                    formedBy[_NormRN(formsCell)] = formingRN

            for rowIndex, row in enumerate(rows, start=2):
                direction = DetermineDirection(header, row)
                if direction is None:
                    continue
                rnCell = (_SafeStr(row.get('Reporting number', ''))).strip()
                rn = rnCell if rnCell != '' else _MakeDefaultRN(rowIndex)
                scriptPath = os.path.join(str(baseDir), str(direction), str(rn) + '.py')
                hasScript = os.path.isfile(scriptPath)
                valid = ValidateWorkingScript(scriptPath) if hasScript else False

                timeText = ''
                try:
                    if direction == 'Dep':
                        timeText = (_SafeStr(row.get('Dep', ''))).strip()
                    elif direction == 'Arr':
                        timeText = (_SafeStr(row.get('Arr', ''))).strip()
                    elif direction == 'Trigger':
                        timeText = (_SafeStr(row.get('Trigger', ''))).strip()
                except:
                    timeText = ''

                it = WorkingItem(rn, direction, rowIndex, scriptPath, hasScript, valid, timeText)
                try:
                    normRN = _NormRN(rn)
                    if normRN in formedBy:
                        it.FormsNext = formedBy[normRN]
                except:
                    pass
                items.append(it)
        except Exception as ex:
            LogWarn('Workings load failed: ' + _SafeStr(ex), alsoDialog=True)
        return items

    # --- UI construction ---
    panel = makePaperPanelFunc()
    try:
        panel.setLayout(GridBagLayout())
    except:
        pass

    gbc = GridBagConstraints()
    gbc.insets = Insets(10, 10, 10, 10)
    gbc.fill = GridBagConstraints.BOTH
    gbc.weightx = 1.0
    gbc.weighty = 1.0
    gbc.gridx = 0
    gbc.gridy = 0

    # Left list
    leftModel = DefaultListModel()
    leftList = JList(leftModel)
    leftList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)

    class WorkingsRenderer(DefaultListCellRenderer):
        def getListCellRendererComponent(self, lst, value, index, isSelected, cellHasFocus):
            try:
                labelText = value.Label()
            except:
                labelText = _SafeStr(value)
            comp = DefaultListCellRenderer.getListCellRendererComponent(self, lst, labelText, index, isSelected, cellHasFocus)
            try:
                comp.setFont(Font(themeFontFamily, Font.PLAIN, 13))
            except:
                pass
            try:
                if getattr(value, 'IsExtra', False):
                    comp.setForeground(Color(128, 128, 128))
                elif not getattr(value, 'HasScript', True):
                    comp.setForeground(Color(255, 0, 0))
                elif not getattr(value, 'ValidScript', True):
                    comp.setForeground(Color(255, 140, 0))
                else:
                    comp.setForeground(themeTextColor)
            except:
                pass
            try:
                comp.setBackground(listSelBg if isSelected else themePaper)
                comp.setOpaque(True)
            except:
                pass
            return comp

    try:
        leftList.setCellRenderer(WorkingsRenderer())
        leftList.setSelectionBackground(listSelBg)
        leftList.setSelectionForeground(listSelFg)
    except:
        pass

    leftScroll = JScrollPane(leftList)
    try:
        leftScroll.setPreferredSize(Dimension(260, 420))
    except:
        pass

    # Right panel (swap editor/action)
    rightPanel = JPanel()
    try:
        rightPanel.setOpaque(True)
        rightPanel.setBackground(themePaper)
        rightPanel.setLayout(GridBagLayout())
    except:
        pass

    controller.WorkingsRightPanel = rightPanel

    def RefreshLeftList():
        try:
            leftModel.removeAllElements()
        except:
            # fallback
            try:
                while leftModel.getSize() > 0:
                    leftModel.remove(0)
            except:
                pass
        items = ExtractWorkings()
        for it in items:
            try:
                leftModel.addElement(it)
            except:
                pass

        try:
            RefreshWorkingsLocationNote()
        except:
            pass

        # Also scan for extra scripts not in timetable
        try:
            scriptsPath = jmri.util.FileUtil.getScriptsPath()
            timetableRNs = set([_NormRN(it.RN) for it in items])
            for direction in ['Trigger', 'Arr', 'Dep']:
                dirPath = os.path.join(str(baseDir), direction)
                if not os.path.isdir(dirPath):
                    continue
                for fname in os.listdir(dirPath):
                    if not fname.lower().endswith('.py'):
                        continue
                    rn = fname[:-3]
                    if _NormRN(rn) in timetableRNs:
                        continue
                    scriptPath = os.path.join(dirPath, fname)
                    reasons = ValidateWorkingScriptReasons(scriptPath)
                    if len(reasons) < 6:
                        valid = ValidateWorkingScript(scriptPath)
                        extraItem = WorkingItem(rn, direction, 0, scriptPath, True, valid)
                        extraItem.IsExtra = True
                        leftModel.addElement(extraItem)
        except Exception as ex:
            LogWarn('Extra script scan failed: ' + _SafeStr(ex), alsoDialog=False)

    try:
        RefreshWorkingsLocationNote()
    except:
        pass

    def BuildEditorPane(item):
        editor = PyCodeEditor(themeFontFamily, applyThemeFunc=applyThemeFunc)
        txtScroll = JScrollPane(editor)
        try:
            txtScroll.setVerticalScrollBarPolicy(JScrollPane.VERTICAL_SCROLLBAR_AS_NEEDED)
            txtScroll.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_AS_NEEDED)
        except:
            pass
        # Explanation label
        explain = MakeWrappedLabel('', widthPx=520, lineHeight=1.20, bold=False)
        try:
            explain.setVisible(False)
        except:
            pass

        def UpdateExplain():
            if getattr(item, 'IsExtra', False):
                try:
                    explain.setText("<html>This script is not linked to any entry in the current timetable.<br/>It may belong to a different timetable or be kept for future use.</html>")
                    explain.setVisible(True)
                except:
                    pass
                return
            reasons = []
            try:
                reasons = ValidateWorkingScriptReasons(item.ScriptPath)
            except:
                reasons = []
            if reasons and len(reasons) > 0:
                try:
                    html = '<html>' + '<br/>'.join(['* ' + _SafeStr(r) for r in reasons]) + '</html>'
                    explain.setText(html)
                    explain.setVisible(True)
                except:
                    pass
            else:
                try:
                    explain.setText('')
                    explain.setVisible(False)
                except:
                    pass

        def LoadFromDisk():
            try:
                with open(item.ScriptPath, 'r') as f:
                    raw = f.read()
                norm = raw.replace('\r\n', '\n').replace('\r', '\n')
                controller.WorkingsSuppressDirty = True
                try:
                    editor.setText(norm)
                    editor.setCaretPosition(0)
                except:
                    pass
                def _Post():
                    controller.WorkingsSuppressDirty = False
                    controller.WorkingsDirty = False
                    try:
                        item.ValidScript = ValidateWorkingScript(item.ScriptPath)
                    except:
                        item.ValidScript = False
                    try:
                        leftList.repaint()
                    except:
                        pass
                    UpdateExplain()
                try:
                    SwingUtilities.invokeLater(RunnableAdapter(_Post))
                except:
                    _Post()
            except Exception as ex:
                LogWarn('Failed to load working script: ' + _SafeStr(ex), alsoDialog=True)

        def DoSave(_e=None):
            try:
                parentDir = os.path.dirname(item.ScriptPath)
                if not os.path.isdir(parentDir):
                    os.makedirs(parentDir)
                with open(item.ScriptPath, 'w') as f:
                    f.write(_SafeStr(editor.getText()))
                controller.WorkingsDirty = False
                item.HasScript = True
                item.ValidScript = ValidateWorkingScript(item.ScriptPath)
                UpdateExplain()
                try:
                    leftList.repaint()
                except:
                    pass
                LogInfo('Saved ' + _SafeStr(item.ScriptPath))
            except Exception as ex:
                LogError('Save failed: ' + _SafeStr(ex), ex=ex, alsoDialog=True)

        def DoRevert(_e=None):
            if controller.WorkingsDirty:
                try:
                    choice = JOptionPane.showConfirmDialog(rightPanel,
                                                          'Discard unsaved changes and reload from file?',
                                                          'Confirm revert',
                                                          JOptionPane.OK_CANCEL_OPTION,
                                                          JOptionPane.WARNING_MESSAGE)
                    if choice != JOptionPane.OK_OPTION:
                        return
                except:
                    return
            LoadFromDisk()

        def DoDelete(_e=None):
            try:
                choice = JOptionPane.showConfirmDialog(rightPanel,
                                                      'Delete this working script file?\nThis action cannot be undone.',
                                                      'Confirm delete',
                                                      JOptionPane.OK_CANCEL_OPTION,
                                                      JOptionPane.WARNING_MESSAGE)
                if choice != JOptionPane.OK_OPTION:
                    return
            except:
                return
            try:
                if os.path.isfile(item.ScriptPath):
                    os.remove(item.ScriptPath)
                controller.WorkingsDirty = False
                item.HasScript = False
                item.ValidScript = False
                if getattr(item, 'IsExtra', False):
                    try:
                        leftModel.removeElement(item)
                    except:
                        pass
                else:
                    BuildActionPane(item)
                try:
                    leftList.repaint()
                except:
                    pass
                LogInfo('Deleted ' + _SafeStr(item.ScriptPath))
            except Exception as ex:
                LogError('Delete failed: ' + _SafeStr(ex), ex=ex, alsoDialog=True)

        class DirtyHook(DocumentListener):
            def insertUpdate(innerSelf, e):
                if getattr(controller, 'WorkingsSuppressDirty', False):
                    return
                controller.WorkingsDirty = True
            def removeUpdate(innerSelf, e):
                if getattr(controller, 'WorkingsSuppressDirty', False):
                    return
                controller.WorkingsDirty = True
            def changedUpdate(innerSelf, e):
                return

        try:
            editor.getDocument().addDocumentListener(DirtyHook())
        except:
            pass

        btnSave = JButton('Save')
        btnRevert = JButton('Revert')
        btnDelete = JButton('Delete')
        try:
            if applyThemeFunc is not None:
                applyThemeFunc(btnSave); applyThemeFunc(btnRevert); applyThemeFunc(btnDelete)
        except:
            pass

        # Layout right panel
        rpG = GridBagConstraints()
        rpG.insets = Insets(6, 6, 6, 6)
        rpG.gridx = 0
        try:
            rightPanel.removeAll()
        except:
            pass

        rpG.gridy = 0
        rpG.fill = GridBagConstraints.HORIZONTAL
        rpG.weightx = 1.0
        rpG.weighty = 0.0
        rightPanel.add(explain, rpG)

        rpG.gridy = 1
        rpG.fill = GridBagConstraints.BOTH
        rpG.weightx = 1.0
        rpG.weighty = 1.0
        rightPanel.add(txtScroll, rpG)

        rpG.gridy = 2
        rpG.fill = GridBagConstraints.NONE
        rpG.weightx = 0.0
        rpG.weighty = 0.0
        btnRow = Box.createHorizontalBox()
        btnRow.add(btnSave)
        btnRow.add(Box.createHorizontalStrut(8))
        btnRow.add(btnRevert)
        btnRow.add(Box.createHorizontalStrut(8))
        btnRow.add(btnDelete)
        rightPanel.add(btnRow, rpG)

        btnSave.addActionListener(lambda e: DoSave(e))
        btnRevert.addActionListener(lambda e: DoRevert(e))
        btnDelete.addActionListener(lambda e: DoDelete(e))

        try:
            rightPanel.revalidate(); rightPanel.repaint()
        except:
            pass

        LoadFromDisk()
        UpdateExplain()

    def BuildActionPane(item):
        btnNew = JButton('New empty script')
        btnCreate = JButton('Create working...')
        try:
            if applyThemeFunc is not None:
                applyThemeFunc(btnNew); applyThemeFunc(btnCreate)
        except:
            pass

        def DoNew(_e=None):
            try:
                parentDir = os.path.dirname(item.ScriptPath)
                if not os.path.isdir(parentDir):
                    os.makedirs(parentDir)
                with open(item.ScriptPath, 'w') as f:
                    f.write(
                        "# Working script for reporting number %s (%s)\n" % (item.RN, item.Direction) +
                        "import jmri, os\n" +
                        "from jmri.util import FileUtil\n\n" +
                        "# Get the scripts path and load the scripts\n" +
                        "scriptsPath = jmri.util.FileUtil.getScriptsPath()\n" +
                        "execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())\n" +
                        "execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())\n\n" +
                        "# TODO: add your logic here, e.g. startTrain(traininfoName, rosterEntry, reportingNumber, direction)\n"
                    )
                item.HasScript = True
                item.ValidScript = ValidateWorkingScript(item.ScriptPath)
                BuildEditorPane(item)
                try:
                    leftList.repaint()
                except:
                    pass
            except Exception as ex:
                LogError('Failed to create blank working script: ' + _SafeStr(ex), ex=ex, alsoDialog=True)

        def DoCreate(_e=None):
            try:
                mod = LoadWorkingCreatorModule()
                if mod is None:
                    JOptionPane.showMessageDialog(panel, 'WorkingCreator.py not found', 'Error', JOptionPane.ERROR_MESSAGE)
                    return
                try:
                    formsNext = getattr(item, 'FormsNext', None)
                except:
                    formsNext = None
                try:
                    if hasattr(mod, 'ShowWorkingCreator'):
                        mod.ShowWorkingCreator(item.RN, item.Direction, item.RowIndex, formsNext)
                    else:
                        JOptionPane.showMessageDialog(panel, 'WorkingCreator.py does not define ShowWorkingCreator().', 'Error', JOptionPane.ERROR_MESSAGE)
                        return
                except Exception as exInner:
                    LogError('WorkingCreator.py error: ' + _SafeStr(exInner), ex=exInner, alsoDialog=True)
                    return

                RefreshLeftList()
                # Reselect the same entry if present
                try:
                    count = leftModel.getSize()
                    target = -1
                    for i in range(count):
                        it2 = leftModel.getElementAt(i)
                        if it2.RN == item.RN and it2.Direction == item.Direction and int(it2.RowIndex) == int(item.RowIndex):
                            target = i
                            break
                    if target >= 0:
                        leftList.setSelectedIndex(target)
                        controller.WorkingsCurrentItem = leftModel.getElementAt(target)
                        if controller.WorkingsCurrentItem.HasScript:
                            BuildEditorPane(controller.WorkingsCurrentItem)
                        else:
                            BuildActionPane(controller.WorkingsCurrentItem)
                except:
                    pass
            except Exception as ex:
                LogError('Create working failed: ' + _SafeStr(ex), ex=ex, alsoDialog=True)

        btnNew.addActionListener(lambda e: DoNew(e))
        btnCreate.addActionListener(lambda e: DoCreate(e))

        rpG = GridBagConstraints()
        rpG.insets = Insets(6, 6, 6, 6)
        rpG.fill = GridBagConstraints.NONE
        rpG.weightx = 0.0
        rpG.weighty = 0.0
        rpG.gridx = 0
        rpG.gridy = 0
        try:
            rightPanel.removeAll()
        except:
            pass
        row = Box.createVerticalBox()
        row.add(btnNew)
        row.add(Box.createVerticalStrut(8))
        row.add(btnCreate)
        rightPanel.add(row, rpG)
        try:
            rightPanel.revalidate(); rightPanel.repaint()
        except:
            pass

    class LeftSelHook(ListSelectionListener):
        def valueChanged(innerSelf, e):
            try:
                if e.getValueIsAdjusting():
                    return
            except:
                pass
            newItem = leftList.getSelectedValue()
            if newItem is None:
                return
            if controller.WorkingsDirty and controller.WorkingsCurrentItem is not None:
                try:
                    choice = JOptionPane.showConfirmDialog(panel,
                                                          'You have unsaved changes. Discard and switch to another working?',
                                                          'Unsaved changes',
                                                          JOptionPane.OK_CANCEL_OPTION,
                                                          JOptionPane.WARNING_MESSAGE)
                    if choice != JOptionPane.OK_OPTION:
                        try:
                            idx = leftModel.indexOf(controller.WorkingsCurrentItem)
                            if idx >= 0:
                                leftList.setSelectedIndex(idx)
                        except:
                            pass
                        return
                except:
                    return
                controller.WorkingsDirty = False

            controller.WorkingsCurrentItem = newItem
            if getattr(newItem, 'HasScript', False):
                BuildEditorPane(newItem)
            else:
                BuildActionPane(newItem)

    try:
        leftList.addListSelectionListener(LeftSelHook())
    except:
        pass

    # Header
    try:
        hdr = makeHeadingFunc('Workings (from current timetable)')
    except:
        hdr = MakeWrappedLabel('Workings (from current timetable)', bold=True)

    gbc.gridx = 0
    gbc.gridy = 0
    gbc.gridwidth = 2
    gbc.fill = GridBagConstraints.HORIZONTAL
    gbc.weightx = 1.0
    gbc.weighty = 0.0
    panel.add(hdr, gbc)

    # Subtle note explaining which workings folder is being used (and if legacy workings are ignored).
    noteLbl = None
    try:
        noteLbl = MakeWrappedLabel('', widthPx=640, lineHeight=1.20, bold=False)
        try:
            noteLbl.setFont(Font(themeFontFamily, Font.PLAIN, 11))
            noteLbl.setForeground(Color(128, 128, 128))
        except:
            pass
    except:
        noteLbl = None

    def RefreshWorkingsLocationNote():
        try:
            if noteLbl is None:
                return
            lines = _WorkingsLocationNoteLines()
            html = '<html>' + '<br/>'.join([_SafeStr(x) for x in lines]) + '</html>'
            noteLbl.setText(html)
        except:
            pass


    
    try:
        if noteLbl is not None:
            gbc.gridy = 2
            gbc.gridwidth = 2
            gbc.fill = GridBagConstraints.HORIZONTAL
            gbc.weightx = 1.0
            gbc.weighty = 0.0
            panel.add(noteLbl, gbc)
    except:
        pass
    RefreshWorkingsLocationNote()

# Row with left and right
    gbc.gridy = 1
    gbc.gridwidth = 1
    gbc.fill = GridBagConstraints.BOTH
    gbc.weighty = 1.0

    gbc.weightx = 0.40
    gbc.gridx = 0
    panel.add(leftScroll, gbc)

    gbc.weightx = 0.60
    gbc.gridx = 1
    panel.add(rightPanel, gbc)

    RefreshLeftList()
    return (panel, controller)

def ShowWorkingsDialog(ownerFrame,
                       getTimetablePathFunc,
                       profileJythonFilePathFunc,
                       applyThemeFunc,
                       makePaperPanelFunc,
                       makeHeadingFunc,
                       makeWrappedLabelFunc,
                       themePaper,
                       themeFontFamily,
                       themeTextColor,
                       listSelBg,
                       listSelFg,
                       logInfoFunc,
                       logWarnFunc,
                       logErrorFunc,
                       title='Workings'):
    """Open the shared Workings UI in a dialog. Returns (dialog, controller)."""
    panel, controller = BuildWorkingsPanel(ownerFrame,
                                          getTimetablePathFunc,
                                          profileJythonFilePathFunc,
                                          applyThemeFunc,
                                          makePaperPanelFunc,
                                          makeHeadingFunc,
                                          makeWrappedLabelFunc,
                                          themePaper,
                                          themeFontFamily,
                                          themeTextColor,
                                          listSelBg,
                                          listSelFg,
                                          logInfoFunc,
                                          logWarnFunc,
                                          logErrorFunc)
    dlg = JDialog(ownerFrame, str(title), False)
    try:
        dlg.setDefaultCloseOperation(JDialog.DO_NOTHING_ON_CLOSE)
    except:
        pass
    try:
        dlg.getContentPane().setLayout(BorderLayout())
        dlg.getContentPane().add(panel, BorderLayout.CENTER)
    except:
        pass
    try:
        dlg.setSize(900, 650)
    except:
        pass
    try:
        dlg.setLocationRelativeTo(ownerFrame)
    except:
        pass

    # Close guard for unsaved changes
    try:
        class _WL(java.awt.event.WindowAdapter):
            def windowClosing(innerSelf, e):
                try:
                    if controller is not None and controller.HasUnsavedChanges():
                        choice = JOptionPane.showConfirmDialog(dlg,
                                                              'You have unsaved changes in a working script.\nDiscard changes and close?',
                                                              'Unsaved changes',
                                                              JOptionPane.OK_CANCEL_OPTION,
                                                              JOptionPane.WARNING_MESSAGE)
                        if choice != JOptionPane.OK_OPTION:
                            return
                    dlg.dispose()
                except:
                    try:
                        dlg.dispose()
                    except:
                        pass
        dlg.addWindowListener(_WL())
    except:
        pass

    try:
        dlg.setVisible(True)
    except:
        pass
    return (dlg, controller)
