# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the 
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General 
# Public License for more details.

# You should have received a copy of the GNU General Public License along with the Timetable Automation System.
# If not, see <https://www.gnu.org/licenses/>. 
#

import jmri
import csv
import os
import java
from java.util import Calendar, Date
from java.text import SimpleDateFormat
from jmri.profile import ProfileManager

# ---- Profile + timetable path (relative to active profile) ----
profile = ProfileManager.getDefault().getActiveProfile()
profilePath = profile.getPath()
try:
    profile_str = profilePath.toString()
except:
    try:
        profile_str = profilePath.getAbsolutePath()
    except:
        profile_str = str(profilePath)
print(profile_str)

mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)

def ReadMemStr(name, defaultValue):
    try:
        m = mm.getMemory(name)
        v = m.getValue() if m is not None else None
        if v is None:
            return defaultValue
        s = str(v).strip()
        return s if s else defaultValue
    except Exception:
        return defaultValue

def ReadMemBool(name, defaultFalse):
    s = ReadMemStr(name, None)
    if s is None:
        return defaultFalse
    s = s.strip().lower()
    return s in ("true", "1", "yes", "on")

timetableName = ReadMemStr("IMCURRENTTIMETABLE", "")
timetablePath = os.path.join(profile_str, "timetable", timetableName + ".csv")

# ---- Memories ----
currentTimeString = ReadMemStr("IMCURRENTTIME", "")
currentDay = ReadMemStr("IMDAYOFWEEK", "Monday")
timeWarpEnabled = ReadMemBool("IMALLOWTIMEWARP", False)

# ---- Day order ----
DAYS_OF_WEEK = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

def ParseTime(time_str):
    """
    Manual, BOM-safe time parser for timetable cells.
    Accepts:
      - 24-hour: "HH:MM" or "HH:MM:SS" (optional trailing 'h')
      - 12-hour: "h:mm AM/PM" or "h:mm:SS AM/PM" (optional space before AM/PM)
    Strips non-ASCII and collapses whitespace. Returns java.util.Date or None.
    """
    if not time_str:
        return None

    try:
        s = str(time_str)
    except Exception:
        s = "%s" % (time_str,)

    # Strip leading/trailing whitespace and optional trailing 'h'
    s = s.strip()
    if not s:
        return None
    if s.lower().endswith("h"):
        s = s[:-1].strip()

    # Remove all non-ASCII characters defensively (e.g., BOM, LRM/RLM, NBSP)
    s_ascii = []
    for ch in s:
        if 32 <= ord(ch) <= 126:  # printable ASCII
            s_ascii.append(ch)
    s = "".join(s_ascii).strip()
    if not s:
        return None

    # Collapse whitespace to single space
    s = " ".join(s.split())

    # Detect 12-hour by presence of am/pm
    sLower = s.lower()
    is12h = ("am" in sLower) or ("pm" in sLower)

    # Split "time [am|pm]"
    parts = s.split(" ")
    timePart = parts[0]
    ampm = parts[1].lower() if (is12h and len(parts) >= 2) else None

    fields = timePart.split(":")
    if len(fields) < 2:
        return None

    try:
        hour = int(fields[0])
        minute = int(fields[1])
        second = int(fields[2]) if len(fields) >= 3 else 0
    except Exception:
        return None

    # Validate ranges
    if hour < 0 or minute < 0 or second < 0 or minute >= 60 or second >= 60:
        return None

    if is12h:
        hour = hour % 12
        if ampm == "pm":
            hour += 12
        # "12:xx am" becomes 00:xx; handled by %12 above
    else:
        if hour == 24:
            hour = 0
        if hour > 24:
            return None

    # Build Date with today's date and parsed time-of-day
    cal = Calendar.getInstance()
    cal.setTime(Date())
    cal.set(Calendar.HOUR_OF_DAY, hour)
    cal.set(Calendar.MINUTE, minute)
    cal.set(Calendar.SECOND, second)
    cal.set(Calendar.MILLISECOND, 0)
    return cal.getTime()

def MinutesSinceMidnight(dateObj):
    hhmm = SimpleDateFormat("HH:mm").format(dateObj).split(":")
    return int(hhmm[0]) * 60 + int(hhmm[1])

def CircularEarlier(candidateOff, candidateHHMM, bestOff, bestHHMM):
    # True if candidate (offsetDays, 'HH:mm') is earlier than best.
    return (candidateOff < bestOff) or (candidateOff == bestOff and candidateHHMM < bestHHMM)

def FindNextWorkingFromTimetable(currentDayName, currentTimeObj):
    # Scan timetable for next Trigger/Arr/Dep over next 7 days
    print("timetable_file: " + timetablePath)
    schedule = []  # list of (offsetDays, timeObj, dayName)
    if os.path.exists(timetablePath):
        for label in ("Trigger", "Arr", "Dep"):
            try:
                with open(timetablePath, "r") as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    for row in reader:
                        try:
                            cell = (row.get(label, "") or "").strip()
                            if not cell:
                                continue
                            tObj = ParseTime(cell)
                            if not tObj:
                                continue
                            for off in (0, 1, 2, 3, 4, 5, 6):
                                idx = (DAYS_OF_WEEK.index(currentDayName) + off) % 7 if currentDayName in DAYS_OF_WEEK else off
                                dayName = DAYS_OF_WEEK[idx]
                                flag = (row.get(dayName, "") or "").strip().lower()
                                if flag == "true":
                                    schedule.append((off, tObj, dayName))
                                elif flag not in ("true", "false", ""):
                                    print("Warning: Unexpected timetable value for {}: '{}'".format(dayName, flag))
                        except Exception:
                            pass
            except IOError as e:
                print("Error opening timetable:", timetablePath)
                print("IOException:", e)
                schedule = []
                break
    else:
        print("Error: timetable file not found:", timetablePath)

    valid = []
    if currentTimeObj is not None:
        for (off, tObj, dayName) in schedule:
            try:
                if off == 0:
                    if tObj.after(currentTimeObj):
                        valid.append((off, tObj, dayName))
                else:
                    valid.append((off, tObj, dayName))
            except Exception:
                pass
    else:
        valid = list(schedule)

    best = None
    for cand in valid:
        if best is None:
            best = cand
            continue
        try:
            hb = SimpleDateFormat("HH:mm").format(best[1])
            hc = SimpleDateFormat("HH:mm").format(cand[1])
            if CircularEarlier(cand[0], hc, best[0], hb):
                best = cand
        except Exception:
            pass
    return best

def SnapshotActiveTrains(df):
    # Snapshot to avoid iterating a live list while Dispatcher mutates it
    try:
        return java.util.ArrayList(df.getActiveTrainsList())
    except Exception:
        return df.getActiveTrainsList()

def AnyTrainRunningNow(df):
    # True if any train is RUNNING/WORKING/PAUSED/READY/STOPPED
    try:
        trains = SnapshotActiveTrains(df)
        size = trains.size()
        for i in range(size):
            at = trains.get(i)
            if at is None:
                continue
            st = at.getStatus()
            if st in (
                jmri.jmrit.dispatcher.ActiveTrain.RUNNING,
                jmri.jmrit.dispatcher.ActiveTrain.WORKING,
                jmri.jmrit.dispatcher.ActiveTrain.PAUSED,
                jmri.jmrit.dispatcher.ActiveTrain.READY,
                jmri.jmrit.dispatcher.ActiveTrain.STOPPED
            ):
                return True
        return False
    except Exception as e:
        print("AnyTrainRunningNow failed:", e)
        return False

def FindEarliestActiveTrainTimedStart(currentDayName, minsNow):
    """
    Return earliest (offsetDays, timeObj, dayName) among clock-held ActiveTrains:
      - status == WAITING
      - has valid departure HH:MM OR getDelayedStart() == TIMEDDELAY
    """
    df = jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame)
    if df is None:
        return None
    trains = SnapshotActiveTrains(df)
    size = trains.size()
    best = None
    for i in range(size):
        at = trains.get(i)
        if at is None:
            continue
        try:
            waiting = (at.getStatus() == jmri.jmrit.dispatcher.ActiveTrain.WAITING)
            hr = int(at.getDepartureTimeHr())
            mn = int(at.getDepartureTimeMin())
            hasClockDepart = (0 <= hr <= 23) and (0 <= mn <= 59)
            isTimedDelay = (at.getDelayedStart() == jmri.jmrit.dispatcher.ActiveTrain.TIMEDDELAY)
            if not (waiting and (hasClockDepart or isTimedDelay)):
                continue
            if not hasClockDepart:
                continue
            calHM = Calendar.getInstance()
            calHM.set(Calendar.HOUR_OF_DAY, hr)
            calHM.set(Calendar.MINUTE, mn)
            calHM.set(Calendar.SECOND, 0)
            calHM.set(Calendar.MILLISECOND, 0)
            tObj = calHM.getTime()
            depMins = hr * 60 + mn
            off = 0 if depMins > minsNow else 1
            dayName = DAYS_OF_WEEK[(DAYS_OF_WEEK.index(currentDayName) + off) % 7] if currentDayName in DAYS_OF_WEEK else currentDayName
            cand = (off, tObj, dayName)
            if best is None:
                best = cand
            else:
                hb = SimpleDateFormat("HH:mm").format(best[1])
                hc = SimpleDateFormat("HH:mm").format(cand[1])
                if CircularEarlier(cand[0], hc, best[0], hb):
                    best = cand
        except Exception as e:
            print("ActiveTrain scan error: {}".format(e))
    return best

if timeWarpEnabled:
    print("Time warp activated")

    # Ensure any due enqueued working is retried before deciding where to warp
    try:
        scriptsPath = jmri.util.FileUtil.getScriptsPath()
        execfile(os.path.join(scriptsPath, "retryEnqueuedWorkings.py"))
    except Exception as e:
        print("Warning: retryEnqueuedWorkings failed:", e)

    # Small wait to allow working scripts to create ActiveTrains
    try:
        java.lang.Thread.sleep(200)
    except Exception:
        pass

    # Re-test Dispatcher: abort warp if a train is already moving/working/paused/ready/stopped
    df0 = jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame)
    if df0 is not None and AnyTrainRunningNow(df0):
        print("Time warp blocked: ActiveTrain is running/working/paused/ready/stopped")
        try:
            mm.getMemory("IMALLOWTIMEWARP").setValue("False")
        except Exception:
            pass
    else:
        currentTimeObject = ParseTime(currentTimeString)

        bestTimetable = FindNextWorkingFromTimetable(currentDay, currentTimeObject)

        if currentTimeObject is not None:
            minsNow = MinutesSinceMidnight(currentTimeObject)
        else:
            tb = jmri.InstanceManager.getDefault(jmri.Timebase)
            tNow = tb.getTime()
            minsNow = MinutesSinceMidnight(tNow)

        bestActive = FindEarliestActiveTrainTimedStart(currentDay, int(minsNow))

        def PickEarlier(a, b):
            if a is None: return b
            if b is None: return a
            ha = SimpleDateFormat("HH:mm").format(a[1])
            hb = SimpleDateFormat("HH:mm").format(b[1])
            return a if CircularEarlier(a[0], ha, b[0], hb) else b

        bestOverall = PickEarlier(bestActive, bestTimetable)

        if bestOverall is not None:
            next_offset, next_timeObj, next_day = bestOverall

            # Final guard: abort if a train started moving just before apply
            df1 = jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame)
            if df1 is not None and AnyTrainRunningNow(df1):
                print("Time warp aborted: movement detected during final apply.")
                try:
                    mm.getMemory("IMALLOWTIMEWARP").setValue("False")
                except Exception:
                    pass
            else:
                cal_now = Calendar.getInstance()
                cal_now.setTime(Date())
                cal_now.add(Calendar.DAY_OF_MONTH, int(next_offset))

                cal_hm = Calendar.getInstance()
                cal_hm.setTime(next_timeObj)

                cal_now.set(Calendar.HOUR_OF_DAY, cal_hm.get(Calendar.HOUR_OF_DAY))
                cal_now.set(Calendar.MINUTE,     cal_hm.get(Calendar.MINUTE))
                cal_now.set(Calendar.SECOND,     0)
                cal_now.set(Calendar.MILLISECOND, 0)

                date_to_set = cal_now.getTime()

                timeBase = jmri.InstanceManager.getDefault(jmri.Timebase)
                timeBase.setTime(date_to_set)
                fmt_am_pm = SimpleDateFormat("h:mm a")
                formatted_time = fmt_am_pm.format(date_to_set)

                mm.getMemory("IMCURRENTTIME").setValue(formatted_time)
                mm.getMemory("IMDAYOFWEEK").setValue(next_day)

                print("Advanced to {} (earliest candidate) on {}".format(formatted_time, next_day))
        else:
            print("No upcoming working found in timetable or ActiveTrains.")
else:
    print("Time warp not enabled (IMALLOWTIMEWARP is false or missing).")