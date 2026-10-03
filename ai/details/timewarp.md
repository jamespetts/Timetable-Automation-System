Read when: Task modifies or debugs TimeWarp.py or TimeWarpChecker.py.

# TimeWarp

File TimeWarp.py performs one-shot warp. File TimeWarpChecker.py is a startup poller.

TimeWarp.py functions:
- ReadMemStr
- ReadMemBool
- ParseTime
- MinutesSinceMidnight
- CircularEarlier
- FindNextWorkingFromTimetable
- SnapshotActiveTrains
- AnyTrainRunningNow
- FindEarliestActiveTrainTimedStart with nested PickEarlier
- Constant DAYS_OF_WEEK = Monday through Sunday tuple.

Memories: CURRENTTIMETABLE, CURRENTTIME, DAYOFWEEK, ALLOWTIMEWARP through TASBeanLookup.SafeGetOrCreateMemoryValue for read and TASBeanLookup.SafeSetMemoryValue for write of ALLOWTIMEWARP false, CURRENTTIME formatted time, DAYOFWEEK next day.

Config: profile:timetable/<name>.csv through FileUtil.getExternalFilename("profile:timetable/" + timetableName + ".csv") else os.path.join(profile path, timetable, name + .csv) with csv.DictReader delimiter tab. Retry script profile:jython/retryEnqueuedWorkings.py through execfile(retryScript).

JMRI APIs:
- jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath()
- jmri.util.FileUtil.getExternalFilename and getScriptsPath
- jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame) with getActiveTrainsList, getStatus, getDepartureTimeHr, getDepartureTimeMin, getDelayedStart
- jmri.jmrit.dispatcher.ActiveTrain constants RUNNING, WORKING, PAUSED, READY, STOPPED, WAITING, TIMEDDELAY
- jmri.InstanceManager.getDefault(jmri.Timebase) with setTime and getTime
- java.util.Calendar and Date, java.text.SimpleDateFormat, java.lang.Thread.sleep

Behavior: FindNextWorkingFromTimetable finds earliest next Trigger, Arr, Dep. SnapshotActiveTrains and AnyTrainRunningNow check running state. When a running train exists, warp aborts. Else Timebase is set to earliest time. When warp crosses midnight, DAYOFWEEK is set to next day.

TimeWarpChecker.py:
- Class CheckActiveTrains extends java.util.TimerTask with method run and __init__(startMs, graceMs).
- Timer code: timer = java.util.Timer(); timer.schedule(CheckActiveTrains(java.lang.System.currentTimeMillis(), TIMEWARPCHECKER_STARTUP_GRACE_MS), 0, 1000).
- TIMEWARPCHECKER_STARTUP_GRACE_MS = 30000. While the elapsed time since __init__ is less than the grace, run sets ALLOWTIMEWARP to False and returns, so input hardware that reports active as it powers up cannot warp the clock during JMRI start-up.
- Memory ALLOWTIMEWARP through TASBeanLookup.ProvideMemoryBySuffix(ALLOWTIMEWARP, false) with setValue True or False.
- Reads DispatcherFrame ActiveTrain list with at.getStatus, getDepartureTimeHr, getDepartureTimeMin, getDelayedStart. Checks status WAITING and TIMEDDELAY.
- Uses jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame), jmri.jmrit.dispatcher.ActiveTrain.WAITING and TIMEDDELAY, java.util.Timer and TimerTask.

Open question: none. Facts verified against file content read in this session.
