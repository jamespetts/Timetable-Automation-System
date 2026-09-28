Read when: Task modifies or debugs WorkingCreator.py, TASWorkingsUi.py, workings editor UI, or generated working scripts.

# WorkingCreator and TASWorkingsUi

File WorkingCreator.py lines: 960. File TASWorkingsUi.py lines: 1163.

WorkingCreator.py:
- Provides ShowWorkingCreator(rn, direction, rowIndex, formsNext).
- Generates scripts under workings/<Direction>/<RN>.py.
- Save path uses TASPathResolver.GetWorkingsWriteDir(direction) else jmri.util.FileUtil.getExternalFilename("profile:jython/workings/" + direction) plus rn + ".py" with os.makedirs.
- Reads timetable rows with csv.DictReader delimiter tab. Keys Reporting number, Forms, Trigger, Arr, Dep.
- Determines direction with _DetermineWorkingDirection with priority Trigger then Arr then Dep.
- Validates syntax with compile(code, path, "exec") in _IsScriptSyntacticallyValid.
- Provides GetWorkingsStatusForTimetable(csvPath) returning dict with keys ok, missing, invalid, total.
- Checks TrainInfo availability with jmri.jmrit.dispatcher.TrainInfoFile readTrainInfo(name + ".xml") and info.getTrainFromSetLater().
- Generated script contains: import jmri, os; from jmri.util import FileUtil; scriptsPath = jmri.util.FileUtil.getScriptsPath(); execfile for startTrain.py; execfile for trainFinder.py; optionally execfile for RosterSearch.py; traininfoNames list; rosterIds assignment; rosterEntry, traininfoName = trainFinder(traininfoNames, rosterIds); activeTrain = startTrain(traininfoName, rosterEntry, reportingNumber, direction, formsNext).
- Uses jmri.jmrit.dispatcher.TrainInfoFile, jmri.jmrit.roster.Roster with getAllEntries and getId, FileUtil.getProfilePath and getExternalFilename.

TASWorkingsUi.py:
- Provides BuildWorkingsPanel(hostFrame, getTimetablePathFunc, profileJythonFilePathFunc, applyThemeFunc, makePaperPanelFunc, makeHeadingFunc, makeWrappedLabelFunc, themePaper, themeFontFamily, themeTextColor, listSelBg, listSelFg, logInfoFunc, logWarnFunc, logErrorFunc) returning (panel, controller).
- Defines class WorkingsUiController with WorkingsDirty, WorkingsCurrentItem, WorkingsSuppressDirty, WorkingsRightPanel, HasUnsavedChanges.
- Defines class WorkingItem with RN, Direction, RowIndex, ScriptPath, HasScript, ValidScript, IsExtra, Time and Label() returning "%s (%s) - row %d [%s]".
- Defines ShowWorkingsDialog with title Workings.
- ExtractWorkings uses csv.DictReader delimiter tab with keys Reporting number, Forms, Dep, Arr, Trigger.
- DetermineDirection checks Trigger in header and non-blank values.
- ValidateWorkingScriptReasons checks for strings: import containing jmri and os, from jmri.util import FileUtil, scriptsPath = jmri.util.FileUtil.getScriptsPath(), execfile(os.path.join(scriptsPath, "startTrain.py"), globals()), execfile(os.path.join(scriptsPath, "trainFinder.py"), globals()), trainFinder( call, startTrain( call with ordering.
- Reports workings dirs as newDir, legacyDir, newHasAny, legacyHasAny, chosenDir, chosenIsLegacy for profile:jython/workings versus scriptsPath/workings.

Open question: none. Facts verified against file content read in this session.
