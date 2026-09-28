Read when: Task modifies or debugs DisruptionGenerator.py, DisruptionRegister.py, or Disruption.csv.

# Disruption Generator and Register

File DisruptionGenerator.py header states disruption generation and updates with support for virtual timing points.

Functions in DisruptionGenerator.py:
parseTimeToMinutes, minutesToStrHMM, timetablePathFromMemory, loadDisruptionGroups, iterTodayRows, _currentSeedBase, seedFor, rngUniformInt, rngPickGeometric, _HasTimingForRNAtTP, _HasAnyTimingToday, _dispatcher, _getActiveTrainByName, _absStartMinute, _isDelayedStart, _build_tp_events, _classify_working, _apply_step_evolution, _min_dwell_minutes, _apply_stop_rules, _publish_at_virtual_tp, _getFormationChildren, _propagateCancellation, isActive, _NextDay, cullSpuriousDisruptions, updateDisruptions, _first_time_in_row, _last_time_in_row, _find_row_by_rn, _legacy_per_train, _ensure_initialized, _master_initialize, _apply_cadenced_updates, _init_state_for_train, _advance_internal, _publish_due_virtuals, _check_crossed_into_layout, _backfill_missed_pre_virtuals, _readMem, _readMemStr, _readMemBool, _ensureMemDefault, _provisionDefaults.

Pattern _TP_PATTERN = ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive. State _state = {"_day": None, "trains": {}}.

Memories: CURRENTTIMETABLE, DAYOFWEEK, CURRENTTIME, ALLOWDELAYS, ALLOWCANCELLATIONS, DISRUPTIONSEEDBASE, TP_WEIGHT_DELAY_PRE_FIRSTTP, TP_WEIGHT_EARLY_PRE_FIRSTTP, TP_P_LATE_DEPART_ON_EARLY, TP_MIN_DWELL_LE_2_MIN, TP_MIN_DWELL_LE_5_MIN, TP_MIN_DWELL_GT_5_MIN, TP_POST_GRACE_MINUTES.

Config files:
- profile:timetable/<name>.csv through TASPathResolver.GetTimetableCsvPath else FileUtil.getExternalFilename("profile:timetable/" + name + ".csv").
- profile:timetable/Disruption.csv with tab delimiter and fields Disruption group, Delay probability, Max delay, Early probability, Max early, Cancellation probability, Minutes before to check max, Minutes before to check min, Cancel if later than, Max recovery mins/min.

Calls: TASPathResolver.GetTimetableCsvPath, DisruptionRegister registerDisruption updateDisruption getDisruption deregisterDisruption, TimingRegister getTiming listTimingPoints getBlocks ensureTimingPoint registerTiming, TASUtil.MakeDefaultReportingNumberFromRow, TrainLocatorRegister.getRosterId, TASBeanLookup, PlatformAllocationRegister.deregisterPlatform.

File DisruptionRegister.py header states class for storing data for delays and cancellations. Cancellation equals delay greater than 1440 minutes.

Variables and functions: register = Hashtable(), registerDisruption, getDisruption, deregisterDisruption, updateDisruption, _AtomicReplace, save, load, _register_shutdown. Lock _Lock = RLock().

File: profile:disruption_register.json through FileUtil.getExternalFilename("profile:disruption_register.json") else os.path.join(FileUtil.getProfilePath(), "disruption_register.json") with .tmp and .bad.<stamp> handling.

Shutdown: jmri.ShutDownManager.instance().addShutdownTask(save) with fallback Runtime hook. Uses java.util.Hashtable, java.lang.Runtime Thread Runnable, java.nio.file.Files Paths StandardCopyOption.

Open question: none. Facts verified against file content read in this session.
