Read when: Task concerns TimetableAutomation.py, main menu, main menu button toggles, scripts path check, dual-install check, startup actions check, RunExternalScript, About dialog, Licence text, changelog text.

# Entry and Startup

Entry script is TAS/TimetableAutomation.py. It is the only TAS file that has to be run from JMRI's Scripting menu or Start Up list. VERSION = "1.5" is defined in TimetableAutomation.py. TimetableAutomation.py loads TASMainMenu.py, which holds the main menu UI classes.

Run method is Run() in TimetableAutomation.py. Run() calls _CheckTasLocationAndMigrateOnce(), _CheckStartUpPathsOnce(), _CheckForDualInstallAndWarnOnce() and _CheckTasOwnStartupEntryOnce(), then calls TASMainMenu.ShowMainMenu().

JSR-223 size limit: JMRI runs entry scripts through the JSR-223 script engine, which parses each file twice and can only reset the parser up to 100000 bytes. TimetableAutomation.py must stay below 100000 bytes. Module files imported by it, including TASMainMenu.py, have no such limit. This is why the main menu UI lives in TASMainMenu.py.

Functions in TimetableAutomation.py:
- _TasGetThisScriptDir, _TasIsWritableDir, _TasScriptsPathLooksLikeProgramDir, _TasScriptsIsParentOfTasDir, _EnsureTasScriptsPath
- _IsStartUpScriptEnabled, _DebugPrintStartUp
- _CanonLower, _StartupMgr, _ActiveProfile, _ProfileJythonScriptPath, _FindPerformScriptModelsByBaseName, _BuildStartUpPathMismatchReport, _ApplyStartUpPathFix, _ShowStartUpPathMismatchDialog, _CheckStartUpPathsOnce
- _DirContainsAnyOf, _DirHasAnyPyUnder, _CheckForDualInstallAndWarnOnce
- _TasTargetDir, _TasProfileJythonDir, _TasListNames, _TasReadVersion, _TasVersionKey, _TasSameContent, _TasCopyFile, _TasCopyTreeContents, _TasDeleteEmptyDirsBottomUp, _TasMoveUserDataDir, _TasDeleteSuperseded, _TasFixStartupPathsQuiet, _TasOptionDialog, _CheckTasLocationAndMigrateOnce
- _IsTasStartupReminderMuted, _CheckTasOwnStartupEntryOnce, Run

Functions and classes in TASMainMenu.py:
- GetActiveProfileName, GetTimetableName, RunExternalScript, ReadMemStr
- PreferredFontFamily, FitFontForSingleLine, BuildTitleLines, LoadLicenceText, LoadChangeLogText
- RefreshMainMenuTheme, ShowMainMenu
- Class CoverPanel with MakeBtn, ToggleWindows, ShowStub, ShowAbout, IsTimeWarpAllowed, UpdateTimeWarpEnabled, OnTimeWarp, OnWeatherForecast, RunConfiguredPublic, RunConfiguredSignallers, FRIENDLY_NAME, RefreshThemeFromMemories, paintComponent
- Class AboutDialog, class TASWTTStartup

TimetableAutomation.py sets TASMainMenu.VERSION, TASMainMenu.SYSTEM_NAME, TASMainMenu.TIMETABLE_MEMORY_NAME and TASMainMenu._IsStartUpScriptEnabled before ShowMainMenu is called.

CoverPanel.ToggleWindows(key, opener) uses TASWindowRegistry.Toggle so that the buttons which open another window close it on a second press. The module is imported as TASWINREG. Details in ai/details/timetableautomation.md.

_TASStartUpScriptNames list in TimetableAutomation.py contains: TimetableAutomation.py, CheckWhenTimeChanges.py, DayTracker.py, TimeWarpChecker.py, DayNight.py, WeatherGenerator.py, LastReportedDirection.py, TASFastClockStartup.py, BlockFlickerMonitor.py, DccPowerOnStart.py, DccPowerOffOnClose.py, RailComFix.py, StreetLightController.py, TASHelp.py.

RunExternalScript(path, name) uses execfile(fullPath, SafeGlobals). If identifier Show exists in globals after execfile, RunExternalScript calls the function with zero arguments or with one string argument. RunExternalScript sets TAS_MAINMENU_THEME_REFRESH_CALLBACK to RefreshMainMenuTheme before execfile when the script is TASSetup.py.

Memories read in TASMainMenu.py: CURRENTTIMETABLE, ALLOWTIMEWARP, WX_UI, CLOUDCOVERPCT, PUBLICDISPLAYLIST, SIGNALLERDISPLAYLIST, TASCOVERCOLOUR, TASINNERCOLOUR, TASINKCOLOUR, TASCOVERINKCOLOUR, TAS_FONT_FAMILY, RAILWAYCO, REGION, SECTION.

Files read: Licence.txt and changelog.txt through TASPathResolver.FindInputStreamFor with keys scripts:Licence.txt and scripts:changelog.txt.

Detailed topics:
- ai/details/timetableautomation.md
- ai/details/tasmainmenu.md
- ai/details/taswindowregistry.md
- ai/details/tasscriptspathguard.md
- ai/details/tasfastclockstartup.md
- ai/details/startup-power-warnings.md
