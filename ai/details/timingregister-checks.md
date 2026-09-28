Read when: Task modifies or debugs TimingRegister.py or CheckTimingPoints.py synchronization.

# TimingRegister and Checks

File TimingRegister.py lines: 589. Header states each entry is a tuple of reportingNumber, direction, time and day of week.

Storage: timingRegister = Hashtable() with per-timing-point dicts {"timings": [], "blocks": []}. Locking with ReentrantReadWriteLock and _rlock and _wlock. File _SAVE_PATH is profile:timingRegister.json through FileUtil.getExternalFilename. Meta dict _meta with __meta__ key in JSON.

Functions:
- _parseTimeToMinutes
- _activeProfileBaseTP
- _ttPath
- _todayName
- _findRowForRNToday
- _schedMinutesFromRow with base TP using Arr and Dep, non-base using tp plus name plus kind
- registerTiming(timingPointName, reportingNumber, direction, time, day) with overwrite per RN plus Dir plus Day
- assignBlocks, clearBlocks, getBlocks, getTiming, removeByDay, ensureTimingPoint, clearTimings, deleteTimingPoint, listTimingPoints, setMeta, getMeta, save, load, _register_shutdown

registerTiming side effect: loads timetable through TASPathResolver.GetTimetableCsvPath(ttName) with csv.DictReader delimiter tab and columns Reporting number, day column, Arr, Dep, TPArr <name>, TPDep <name>. Computes delay = actual minutes minus scheduled minutes. Calls DisruptionRegister.registerDisruption or updateDisruption unless current minutes >= 1441.

Memories: CURRENTTIMETABLE, DAYOFWEEK through TASBeanLookup.SafeGetMemoryValue.

JMRI APIs: jmri.InstanceManager.getDefault(jmri.MemoryManager), jmri.profile.ProfileManager.getDefault().getActiveProfile().getName(), jmri.util.FileUtil.getExternalFilename("profile:timingRegister.json"), java.util.Hashtable, java.util.concurrent.locks.ReentrantReadWriteLock, java.lang.Runtime Thread Runnable, jmri.ShutDownManager.

CheckTimingPoints.py provides sync_timing_points_from_timetable(verbose=True). Pattern pat = ^TP(\d*)(Arr|Dep)\s+(.+)$ case-insensitive. Stores timetable_tp_case[tp_name.lower()] = tp_name. Calls TR.listTimingPoints, ensureTimingPoint, getBlocks, deleteTimingPoint, clearTimings, removeByDay, getMeta("lastMaintenanceDay"), setMeta.

Open question: none. Facts verified against file content read in this session.
