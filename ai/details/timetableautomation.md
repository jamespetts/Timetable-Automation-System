Read when: Task modifies or debugs TimetableAutomation.py main menu, main menu button toggles, startup path logic, dual-install warning, RunExternalScript, or About dialog.

# TimetableAutomation.py

File: TAS/TimetableAutomation.py. Lines: 1823. VERSION = "1.5". The main menu UI is in TAS/TASMainMenu.py (see ai/details/tasmainmenu.md).

Startup functions:
- _TasGetThisScriptDir() returns directory of the current script.
- _TasIsWritableDir(path) returns true when directory is writable.
- _TasScriptsPathLooksLikeProgramDir(path) returns true when scripts path is inside program directory.
- _EnsureTasScriptsPath() imports TASScriptsPathGuard and calls NeedsScriptsPathUpdate and EnsureScriptsPathChanged. It runs at import time.
- _StartupMgr() returns jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager).
- _ActiveProfile() returns jmri.profile.ProfileManager.getDefault().getActiveProfile().
- _FindPerformScriptModelsByBaseName(models, baseName) returns matching PerformScriptModel entries.
- _BuildStartUpPathMismatchReport() builds report of startup scripts pointing to wrong location.
- _ApplyStartUpPathFix() sets file names to profile:jython/TAS location and calls mgr.savePreferences(prof) and mgr.setRestartRequired().
- _ShowStartUpPathMismatchDialog() shows JOptionPane dialog for fix.
- _CheckStartUpPathsOnce() runs the mismatch check one time.
- _DirContainsAnyOf(dirPath, names) and _DirHasAnyPyUnder(dirPath) support outside-folder detection.
- _CheckForDualInstallAndWarnOnce() warns when TAS files exist outside profile:jython/TAS (program folder, foreign scripts folder). Flat leftovers at the profile root are handled by migration instead.
- _CheckTasLocationAndMigrateOnce() runs first: self-installs from elsewhere, moves legacy flat files into profile:jython/TAS with an explanatory dialog, updates Start-Up entries quietly. Helpers: _TasTargetDir, _TasProfileJythonDir, _TasListNames, _TasReadVersion, _TasVersionKey, _TasSameContent, _TasCopyFile, _TasCopyTreeContents, _TasDeleteEmptyDirsBottomUp, _TasMoveUserDataDir, _TasDeleteSuperseded, _TasRepointStartUpEntriesQuiet, _TasFixStartupPathsQuiet, _TasOptionDialog. User data dirs workings and config are merged with backup; differing old files are backed up under _TAS-migration-backup before replacement and are never deleted without a successful backup.
- _CheckTasOwnStartupEntryOnce() warns when TimetableAutomation.py is not an enabled Start-Up entry, mutable through Memory TAS_STARTUP_REMINDER_MUTED.
- Run() runs the four checks above and then calls TASMainMenu.ShowMainMenu(). It does not build UI itself.

Main menu:
- The UI moved to TASMainMenu.py in version 1.5 because TimetableAutomation.py must stay below the 100000 byte JSR-223 parse mark limit. See ai/details/tasmainmenu.md.

Size limit:
- JMRI runs entry scripts through the JSR-223 script engine, which parses each file twice and can only reset the parser up to 100000 bytes. Any file run from the Scripting menu or the Start Up list must stay below that limit. Imported modules are not affected.

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
