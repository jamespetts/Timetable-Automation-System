Read when: Start of each session, before reading any other file in ai/.

# TAS Knowledge Base Index

This file lists head-topic files. Read a head-topic file only when the task matches its Read when condition. Do not read detailed-topic files directly from this file. Detailed-topic files are listed inside head-topic files.

Target: JMRI 5.16. Language: Jython 2.7. Entry script: TimetableAutomation.py.

## Overarching

0. ai/design-goals.md
   Read when: Task makes a design decision affecting more than one feature, adds a feature, changes a user interface, changes time handling, changes error handling, or changes setup flow. Read before other head-topic files for such tasks.

## Head topics

1. ai/entry-startup.md
   Read when: Task concerns TimetableAutomation.py, main menu, scripts path check, dual-install check, startup actions check, RunExternalScript, About dialog, Licence text, changelog text.
2. ai/memories-beanlookup.md
   Read when: Task concerns JMRI Memories, Memory suffix lookup, SafeGetOrCreateMemoryValue, SafeGetMemoryValue, SafeSetMemoryValue, ProvideMemoryBySuffix, FindMemoryBySuffix, prefix handling for IM and InM.
3. ai/paths-files.md
   Read when: Task concerns file paths, profile:jython, scripts:, profile:timetable, workings directories, FileUtil, TASPathResolver, TASScriptsPathGuard.
4. ai/timetable-workings.md
   Read when: Task concerns timetable CSV format, RunWTT.py, CheckWhenTimeChanges.py, WorkingCreator.py, TASWorkingsUi.py, startTrain.py, trainFinder.py, enqueuedWorkings.py, retryEnqueuedWorkings.py, TimingRegister.py interaction with startTrain, CheckTimingPoints.py.
5. ai/displays.md
   Read when: Task concerns WTTDisplay.py, StationWorking.py, PID*.py displays, TRUST-TRJA.py, NSEClock.py, signaller displays, public displays, display discovery tags.
6. ai/weather-daynight.md
   Read when: Task concerns WeatherGenerator.py, WeatherForecastUIApp.py, WeatherForecastUINewspaper.py, DayTracker.py, DayNight.py, StreetLightController.py, config/climate.csv, config/daynight.csv, config/streetlights.tsv, Memories WX_*, CLOUDCOVERPCT, DAYOFWEEK, SUNRISESECONDS, SUNSETSECONDS, SOLARDAY.
7. ai/disruptions-timing.md
   Read when: Task concerns DisruptionGenerator.py, DisruptionRegister.py, TimingRegister.py, NotebookDisruption.py, TeleprinterDisruption.py, Disruption.csv, timing points TPArr and TPDep, delay values, cancellation values.
8. ai/timewarp-clock.md
   Read when: Task concerns TimeWarp.py, TimeWarpChecker.py, TASFastClockStartup.py, ALLOWTIMEWARP Memory, fast-clock time, DispatcherFrame ActiveTrain status.
9. ai/setup-wizard-help.md
   Read when: Task concerns TASSetup.py, TASWiz.py, HardwareDirectionConfig.py, TASHelp.py, tashelp/*.txt, TASFontCheck.py, TASIcon.py, TASUtil.py, configuration UI, wizard steps, help viewer, font check, window icon.
10. ai/registers-direction.md
    Read when: Task concerns NormalDirectionRegister.py, LastReportedDirection.py, OrientationRegister.py, PlatformAllocationRegister.py, TrainLocatorRegister.py, formationRegister.py, RosterSearch.py, roster ID normalisation, reporting number defaults TAS plus row number.

## Rules

- Each head-topic file starts with a Read when line. Each detailed-topic file starts with a Read when line.
- Detailed-topic files are located in ai/details/. Head-topic files list the detailed-topic files that belong to the head topic.
- All knowledge base documents use ASCII only, precise literal text, and no metaphor.
- Verify each fact against repository code or JMRI 5.16 documentation or JMRI 5.16 source on Github. If a fact cannot be verified, stop and ask the user.
- Temporary files are placed only in ai/temp/. At the end of each session delete all files in ai/temp/, then write ai/temp/handoff.md only when incomplete work remains for a new session. ai/temp/handoff.md contains only the description of the incomplete work. Delete ai/temp/handoff.md when the handed off work is complete.
