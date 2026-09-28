Read when: Task modifies or debugs StationWorking.py station working display.

# StationWorking.py

File: StationWorking.py. Lines: 1644. Header states StationWorkingBookDisplay for JMRI 5.14 and Jython 2.7.

Discovery tags:
- <<SIG-DISP-NAME: Station working>>
- <<DESCRIPTION: Shows station workings (arrival/departure/platform/remarks) in a station-working-book format, with optional auto-follow of the next expected train (delay-aware).>>

Function LoadServicesMaster(csvPath) returns list of dicts with keys rep, dir, trigger, arr, dep, origin, dest, plat, notes, remarks, forms, calling, special, via, tp, days.

Remark functions:
- _FindTimingPointTimeForStation
- _ExpandCallingPattern
- ExpandRemarks expands {calling pattern}, {notes}, {forms}, {special}, {via}, newline token.

Delay functions:
- _BuildFormsFromMap
- _BuildTrainDaysMap
- _EffectiveDelayMinutesForRn
- _ServiceKeyTimeMinutes
- _ComputeExpectedMinuteForSvc
- _ChooseCurrentModelRow

UI:
- Classes WrapCellRenderer, SWBCellRenderer, HeaderCellRenderer, DepCellRenderer, SWBJTable.
- Objects _table, _tableModel, scroll, controlsPanel with btnPrev, btnNext, btnSnap, chkFollow, chkHighlight, statusLabel, pageLabel.
- Classes _Action, WheelPager, _ColModelListener, _FrameResizer, _WindowCloser.
- State _state with master, pages, pageIndex, total, formsFrom, trainDays, hideNo, hideDir, hidePfm, layoutName, currentDay, currentTime.
- Functions _BuildPages, _DecideColumnHiding, _ColumnsForState with columns No., Time, Dir, From, To, Arr, Dep, Pfm, Remarks, _PreferredColumnWidths, _RebuildTableForCurrentPage, _UpdateHighlightAndMaybeFollow, _SnapToCurrent, _GoToPage, NextPage, PrevPage, _LoadAll, _UpdateStatusLine, _HandleDayOrTimeChange, _OnTimeChanged, _OnDayChanged, _OnTimetableChanged, _Cleanup, _SelectPageForDay, _EnsureRowVisible.

CSV:
- Sample check uses tab when present else comma with csv.DictReader.
- Pattern _TP_HEADER_PAT = ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive.
- Get Reporting number empty uses TASUtil.MakeDefaultReportingNumberFromRow(rowIndex).
- Day values accepted are TRUE, T, 1, Y, YES uppercased.
- Columns Direction, Trigger, Arr, Dep, Origin, Destination, Platform, Notes, Remarks, Forms, Calling pattern, Special, Via.

Memories:
- WTT_PAGE_MODE, WTT_TIME_24H, WTT_TIME_SEPARATOR, TASPAPERCOLOUR, TASWTTBANDLIGHT, TASWTTBANDDARK, TAS_FONT_FAMILY, CURRENTTIMETABLE, DAYOFWEEK, CURRENTTIME.
- Listeners: TimeMem = TASBeanLookup.ProvideMemoryBySuffix(CURRENTTIME, ""), DayMem, TimetableMem with addPropertyChangeListener.

JMRI APIs: JmriJFrame(Station working), SimpleDateFormat, BorderLayout Color Dimension Font FlowLayout Point, KeyEvent MouseWheelListener ComponentAdapter WindowAdapter, JTable JLabel JPanel JScrollPane, DefaultTableModel DefaultTableCellRenderer.

Inter-file: TASBeanLookup, TASPathResolver.GetTimetableCsvPath, TASUtil.IsDefaultReportingNumber and MakeDefaultReportingNumberFromRow, DisruptionRegister.getDisruption, TASIcon.SetFrameClockIcon.

Open question: none. Facts verified against file content read in this session.
