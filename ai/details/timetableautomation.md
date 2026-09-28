Read when: Task modifies or debugs TimetableAutomation.py main menu, startup path logic, dual-install warning, RunExternalScript, or About dialog.

# TimetableAutomation.py

File: TimetableAutomation.py. Lines: 1690. VERSION = "1.5".

Startup functions:
- _TasGetThisScriptDir() returns directory of the current script.
- _TasIsWritableDir(path) returns true when directory is writable.
- _TasScriptsPathLooksLikeProgramDir(path) returns true when scripts path is inside program directory.
- _EnsureTasScriptsPath() imports TASScriptsPathGuard and calls NeedsScriptsPathUpdate and EnsureScriptsPathChanged. It runs at import time.
- _StartupMgr() returns jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager).
- _ActiveProfile() returns jmri.profile.ProfileManager.getDefault().getActiveProfile().
- _FindPerformScriptModelsByBaseName(models, baseName) returns matching PerformScriptModel entries.
- _BuildStartUpPathMismatchReport() builds report of startup scripts pointing to wrong location.
- _ApplyStartUpPathFix() sets file names to profile:jython location and calls mgr.savePreferences(prof) and mgr.setRestartRequired().
- _ShowStartUpPathMismatchDialog() shows JOptionPane dialog for fix.
- _CheckStartUpPathsOnce() runs the mismatch check one time.
- _DirContainsAnyOf(dirPath, names) and _DirHasAnyPyUnder(dirPath) support dual-install detection.
- _CheckForDualInstallAndWarnOnce() warns when .py files exist under both profile:jython and scripts: locations.

Main menu:
- Class CoverPanel extends JPanel. Methods: MakeBtn, ShowStub, ShowAbout, IsTimeWarpAllowed, UpdateTimeWarpEnabled, OnTimeWarp, OnWeatherForecast, RunConfiguredPublic, RunConfiguredSignallers, RefreshThemeFromMemories, paintComponent. Field FRIENDLY_NAME stores display name.
- Class AboutDialog extends JDialog. Shows Licence.txt and changelog.txt content.
- Class TASWTTStartup extends JFrame. Constructor calls SetFrameClockIcon from TASIcon.py.
- Functions PreferredFontFamily, FitFontForSingleLine, BuildTitleLines, LoadLicenceText, LoadChangeLogText, GetActiveProfileName, GetTimetableName, ReadMemStr, RefreshMainMenuTheme, Run.

JMRI APIs used:
- jmri.util.FileUtil.getExternalFilename
- jmri.util.FileUtil.getScriptsPath
- jmri.util.FileUtil.getProgramPath
- jmri.util.FileUtil.setScriptsPath
- jmri.util.FileUtil.findInputStream
- jmri.profile.ProfileManager.getDefault
- jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
- jmri.util.startup.PerformScriptModel with getFileName, setFileName, isEnabled, setEnabled
- jmri.InstanceManager.getNullableDefault(jmri.implementation.FileLocationsPreferences)

Open question: none. Facts verified against file content read in this session.
