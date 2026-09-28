Read when: Task modifies or debugs WTTDisplay.py working timetable UI.

# WTTDisplay.py

File: WTTDisplay.py. Lines: 1690. Header states JMRI 5.12 and Jython 2.7.

Function LoadServicesMaster(csv_path) returns list of dicts with keys rep, arr, dep, origin, dest, plat, cls, load, trigger, tp, days, dir, note.

Direction handling:
- Functions _NormDirectionKey, _BuildDirectionPairMap, _BuildDirectionPriorityMapFromPairings, _DirectionPriority, DeriveDirectionOrder.
- Constants DIRECTION_PAIRINGS, DIRECTION_PAIR_MAP, DIRECTION_PRIORITY_MAP.

Paging:
- Functions DayGroupsFromMode, DisplayLabelForHeader, _ScoreRowForGroup, BuildPages.

Headers:
- Functions HtmlEscape, _IsEcsDest, _DestHasTimingPointTimeForDest, _OdPhrase, MakeWrappedHeaderHtml, AutoAdjustHeaderHeight.

Legend:
- Functions ComputeRunCode, ExplainCode.

UI classes and functions:
- VerticalLabel, VerticalHeaderRenderer, WTTCellRenderer, ZebraTable, WheelPager, _Action, SetTopRowHeading, ApplyPage, GoTo, NextPage, PrevPage, RefreshButtons, _BuildTimingRowsForPage, _FitFrameSnug.

Timing point ordering:
- Functions _TypicalTimeForDefault, _TypicalTimeForTp, _ComputeTpOffsetMedians, _ComputeGroupEndpointMean, _TpRangeFor, _TpSplitAndInsert, _BuildOrderedNamesForCategory, _ComputeTpOrderGrouped, _OppositeDirectionKey, _ComputeTpOrderGroupedFromDiffs, _ComputeTpOrder, _BuildTpOrderIndexByDirection, _ShouldCollapseTpArrRow.
- Globals TP_NAMES, TP_ORDER_BY_DIR, HAS_TRIGGER_COL, TP_GROUP_OF, NUM_DATA_COLS=12, DATA_START_COL=2, ROW_CODES=0, ROW_TOP_BOLD=1, LAYOUT_NAME = GetProfileName().

CSV parsing:
- Sample check uses tab when tab in sample else comma with csv.reader.
- find_col is case-insensitive for Reporting number, Direction, Notes or notes or Note or note, Arr, Dep, Trigger, Origin, Destination, Platform, Class, Timing load plus TIMING_LOAD_LABEL override.
- TP pattern is ^tp(\d*)(arr|dep)\s+(.+)$ case-insensitive. TP_GROUP_OF[name]=gnum.
- Days flags accepted are TRUE, T, 1, Y, YES.

Memories through TASBeanLookup.SafeGetMemoryValue with _ReadMemStr and _ReadMemBool:
WTT_PAGE_MODE default WEEKDAYS_SAT_SUN, WTT_TIME_24H true, WTT_TIME_SEPARATOR " ", WTT_ECS_LABEL ECS, WTT_TIMING_LOAD_LABEL Timing load, WTT_REP_NO_LABEL Rep. no., WTT_ECS_DEST_MATCH empty to depot,empty,ety.,ecs, WTT_DIRECTION_SPLIT true, WTT_OD_HEADER_VERTICAL false, WTT_TP_NAME_DOT_LEADERS false, TASPAPERCOLOUR 249,246,238, TASWTTBANDLIGHT 255,253,247, TASWTTBANDDARK 245,242,235, TAS_FONT_FAMILY Gill Sans MT, CURRENTTIMETABLE.

JMRI APIs: jmri.util.FileUtil, jmri.InstanceManager, jmri.util.JmriJFrame(Working Timetable), javax.swing JTable JLabel JPanel JScrollPane, java.awt BorderLayout Color Dimension Font FlowLayout, java.text.SimpleDateFormat with h:mm a, H:mm, HH:mm, TASIcon.SetFrameClockIcon(frame, 32).

Inter-file: TASBeanLookup as TBL, TASPathResolver.GetTimetableCsvPath, TASUtil as TU with IsDefaultReportingNumber for SHOW_REP_ROW.

Open question: none. Facts verified against file content read in this session.
