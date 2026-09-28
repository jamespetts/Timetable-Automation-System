Read when: Task modifies or debugs NotebookDisruption.py or TeleprinterDisruption.py.

# Notebook and Teleprinter Disruption

File NotebookDisruption.py header states handwriting-on-ruled-paper disruption output for signallers.

Discovery tags in NotebookDisruption.py:
- <<SIG-DISP-NAME: Message notebook>>
- <<DESCRIPTION: A notebook where status messages about trains (delays, cancellations, etc.) are written down by hand by the signaller.>>
- <<SETTING DESCRIPTION BOOLEAN: Use 24-hour time>>

Hub key _HUB_MODULE_KEY = TASHandwritingDisruptionHub with _GetOrCreateHub.

Classes: RunnableAdapter implements Runnable, BookPanel extends JPanel, BookFrame extends JFrame.

Functions include _ReadMemStr, _ReadMemBool, _FindTpCellValue, _DayIndex, _ParseTimeToMinutes, _FormatMinutes, _ComputeWeekAbsMinute, _AgeMinutes, _ActiveProfilePath, _TimetablePathFromMemory, _LoadTimetableIndex, _RowForTrain, _GetDestinationFromRow, _GetOriginFromRow, _GetDueTimeScheduledMinutes, _GetLayoutEtaScheduledMinutes, _MakeTrainIdentifier, _InferArrDepForTP, _GetScheduledMinuteForTP, _StatusFromDelta, _IsCancelledValue, _ToDisplayCase, _FormatTimeForEntry, _BuildMessageText, _BuildEntryLine, _BuildDayHeaderText, _EstimateWrappedLineCountForPageText, _WouldEntryFitOnPage, _AppendEntryToExistingPageLocked, _EnsureTrainState, _RateLimitMinutes, _NotifyWindows, _NewWriterState, _StartNextPendingIfIdleLocked, _AddIncomingPage, _AddMessage, _CullOldPages, _PollOnce, _RgbStrToColor, _FadeInkColor, _DrawWoodSurface, _PickHandwritingFont, _Jitter, _WrapTextToLines.

Memories: CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE, TAS_USER_SETTING_USE_24_HOUR_TIME through ProvideMemoryBySuffix, plus TASPAPERCOLOUR, TASINKCOLOUR, TASRULELINECOLOUR, TASMARGINCOLOUR, TASHANDWRITINGFONT through _ReadMemStr.

Timetable read through FileUtil.getExternalFilename("profile:timetable/" + name + ".csv") with csv.DictReader delimiter tab. Pattern _TP_KEY_PAT = ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive.

Calls: TASBeanLookup as TBL, TASUtil as TU with MakeDefaultReportingNumberFromRow and IsDefaultReportingNumber, DisruptionRegister as DR with getDisruption, TimingRegister as TR with listTimingPoints and getTiming, TASIcon.SetFrameClockIcon.

File TeleprinterDisruption.py header states teleprinter-style disruption output for signallers.

Discovery tags in TeleprinterDisruption.py:
- <<SIG-DISP-NAME: Teleprinter>>
- <<DESCRIPTION: A teleprinter which shows train status messages (delays, cancellations, etc.) as notified. Suitable for circa 1960s-1990s.>>
- <<SETTING DESCRIPTION BOOLEAN: Use 24-hour time>>

Hub key _HUB_MODULE_KEY = TASTeleprinterDisruptionHub.

Classes: PrinterPanel, StackPanel, TeleprinterFrame, RunnableAdapter.

Functions parallel NotebookDisruption.py with _GetOrCreateHub, _ReadMemStr, _ReadMemBool, _BuildMessageText, _EnsureTrainState, _PollOnce, _DrawInTray, _StartHubPollingIfNeeded, _OpenWindow.

Memories: CURRENTTIME, DAYOFWEEK, CURRENTTIMETABLE, TAS_USER_SETTING_USE_24_HOUR_TIME, TASPAPERCOLOUR, TASINKCOLOUR.

Timetable read through TASPathResolver.GetTimetableCsvPath else os.path.join(profilePath, timetable, name + .csv).

Calls: TASBeanLookup as TBL, TASPathResolver, TASUtil as TU, DisruptionRegister as DR with getDisruption, TimingRegister as TR, TASIcon.SetFrameClockIcon.

Open question: none. Facts verified against file content read in this session.
