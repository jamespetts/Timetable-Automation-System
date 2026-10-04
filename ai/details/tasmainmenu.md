Read when: Task modifies or debugs TASMainMenu.py, the TAS main menu UI, CoverPanel, AboutDialog, TASWTTStartup, main menu theme refresh, or RunExternalScript.

# TASMainMenu.py

File: TAS/TASMainMenu.py. Lines: 1002.

Loaded by TAS/TimetableAutomation.py. Kept separate so that TimetableAutomation.py stays below the 100000 byte JSR-223 parse mark limit.

Functions:
- GetActiveProfileName() reads jmri.profile.ProfileManager.getDefault().getActiveProfileName().
- GetTimetableName() reads Memory TIMETABLE_MEMORY_NAME (set by TimetableAutomation.py to CURRENTTIMETABLE) through TBL.SafeGetMemoryValue.
- RunExternalScript(FileName, FriendlyName, Arg=None) resolves the script through TPR.ResolveScriptReadPath, falling back to scripts:FileName, then execfile(fullPath, SafeGlobals). If SafeGlobals has Show, it calls Show() or Show(Arg). It sets TAS_MAINMENU_THEME_REFRESH_CALLBACK to RefreshMainMenuTheme when FileName is TASSetup.py.
- PreferredFontFamily, FitFontForSingleLine, BuildTitleLines build title text and fonts.
- LoadLicenceText and LoadChangeLogText read Licence.txt and changelog.txt through TPR.FindInputStreamFor with scripts: fallback.
- ReadMemStr(Name, Default="") is the compatibility wrapper for TBL.SafeGetOrCreateMemoryValue.
- RefreshMainMenuTheme() runs on the EDT and calls CoverPanel.RefreshThemeFromMemories on the current _TASMainMenuFrame.
- ShowMainMenu() sets the system look and feel and, on the EDT, creates TASWTTStartup, stores it in _TASMainMenuFrame and shows it.

Classes:
- CoverPanel extends JPanel. Constants KEY_TIMETABLE, KEY_PUBLIC, KEY_SIGNALLERS, KEY_WEATHER, KEY_SETUP, KEY_HELP. Methods MakeBtn, ToggleWindows, ShowStub, ShowAbout, IsTimeWarpAllowed, UpdateTimeWarpEnabled, OnTimeWarp, OnWeatherForecast, RunConfiguredPublic, RunConfiguredSignallers, FRIENDLY_NAME, RefreshThemeFromMemories, paintComponent.
- AboutDialog extends JDialog. Shows the licence and change log text.
- TASWTTStartup extends JFrame. Creates CoverPanel and sets the clock icon through TASIcon.SetFrameClockIcon.

Names supplied by TimetableAutomation.py at run time:
- VERSION
- SYSTEM_NAME
- TIMETABLE_MEMORY_NAME
- _IsStartUpScriptEnabled

Modules imported at top level:
- TASBeanLookup as TBL
- TASPathResolver as TPR (optional)
- TASWindowRegistry as TASWINREG (optional)

JMRI APIs used: jmri.util.FileUtil.getExternalFilename, jmri.profile.ProfileManager.getDefault, jmri.InstanceManager memory and startup APIs through TASBeanLookup.

Open question: none. Facts verified against file content read in this session.
