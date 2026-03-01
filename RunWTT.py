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
import re
from java.text import SimpleDateFormat
from java.util import Date
from java.lang import System
from jmri.profile import ProfileManager
from jmri.util import FileUtil
import TASUtil as TU
import TASBeanLookup as TBL

# --- Memory manager ---
memoryManager = jmri.InstanceManager.getDefault(jmri.MemoryManager)

# --- Get profile path ---
profile = ProfileManager.getDefault().getActiveProfile()
profilePath = profile.getPath()   # java.nio.file.Path

# --- Get timetable file name ---
memTimetable = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
if memTimetable is None:
    print("Error: CURRENTTIMETABLE memory variable is not defined.")
elif memTimetable.getValue() is None:
    print("Error: CURRENTTIMETABLE has no value.")
else:
    timetableName = memTimetable.getValue()
    timetableFile = None
    try:
        timetableFile = FileUtil.getExternalFilename("profile:timetable/" + str(timetableName) + ".csv")
    except Exception:
        timetableFile = None
    if not timetableFile:
        timetableFile = os.path.join(profilePath.toString(), "timetable", timetableName + ".csv")
    # --- Proceed only if timetableFile is valid ---
    if not os.path.exists(timetableFile):
        print("Error: Timetable file does not exist:", timetableFile)

    else:
        # --- Get current time and day ---
        currentTimeStr = TBL.ProvideMemoryBySuffix("CURRENTTIME", "").getValue()
        currentDay = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "").getValue()

        # --- Day order ---
        daysOfWeek = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # --- Time parsing helper ---
        def parseTimeToMinutes(timeStr):
            """
            Parse a time string to minutes since midnight (int).

            Supported:
              - 24-hour: "13:15", "13:15:00", optional trailing 'h' (e.g., "13:15h")
              - 12-hour: "1:15 PM", "1:15PM", "01:15 pm", optional seconds
            Returns int minutes (0..1439) or None if blank/unparsable.
            """
            # Local import ensures availability in JSR-223 contexts even if globals differ
            import re as _re

            if timeStr is None:
                return None

            # Jython 2.7: ensure we have a text value
            try:
                is_string = isinstance(timeStr, basestring)
            except NameError:
                is_string = isinstance(timeStr, str)
            s = (timeStr if is_string else str(timeStr)).strip()
            if not s:
                return None

            # Normalize odd spaces & optional trailing 'h' using actual Unicode chars
            try:
                s = (s.replace(u'\u00A0', u' ')
                       .replace(u'\u200E', u'')
                       .replace(u'\u200F', u''))
            except Exception:
                pass
            s = _re.sub(r'\s+', ' ', s)
            if s.lower().endswith('h'):
                s = s[:-1].strip()

            # HH:MM[:SS] with optional AM/PM (space optional)
            m = _re.match(r'^\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?\s*$', s, flags=_re.IGNORECASE)
            if not m:
                print("[RunWTT] Debug: could not parse time '{}'".format(timeStr))
                return None

            hour   = int(m.group(1))
            minute = int(m.group(2))
            ampm   = m.group(4).lower() if m.group(4) else None

            # Range checks
            if minute >= 60 or hour > 24 or hour < 0 or minute < 0:
                print("[RunWTT] Debug: invalid time '{}'".format(timeStr))
                return None

            if ampm:
                # 12-hour conversion
                hour = hour % 12
                if ampm == 'pm':
                    hour += 12
            else:
                # 24-hour: treat 24:xx as 00:xx
                if hour == 24:
                    hour = 0

            return hour * 60 + minute

        # --- Get current time in minutes ---
        currentMinutes = parseTimeToMinutes(currentTimeStr)
        
        # Generate disruption 
        try:
            import DisruptionGenerator as DG
            # Jython 2.x: reload is a built-in, but fallback to imp.reload if needed
            try:
                reload
            except NameError:
                import imp
                imp.reload(DG)
            else:
                reload(DG)
            DG.updateDisruptions()
        except Exception as e:
            print("Disruption generator error:", e)


        # --- Read timetable and find exact match ---
         # Check trigger, arrival and departure times and trigger the appropriate script
        for direction in ["Trigger", "Arr", "Dep"]:
            reportingNumber = None
            with open(timetableFile, "r") as f:
                reader = csv.DictReader(f, delimiter="\t")
                # Spreadsheet row numbers: header = 1, first data row = 2
                for rowNumber, row in enumerate(reader, start=2):
                    if direction not in row or not row[direction].strip():
                        continue  # Skip if the direction is missing or empty
                    if direction == "Arr" and "Trigger" in row and row["Trigger"].strip() != "":
                        # Where both "Trigger" and "Arr" exist, only trigger
                        # the script on "Trigger" and use the "Arr" time only
                        # for timetables, PIDs and timekeeping.
                        continue
                    timeStr = row[direction].strip()
                    timeMinutes = parseTimeToMinutes(timeStr)
                    if timeMinutes is None or timeMinutes != currentMinutes:
                        continue
                    dayValue = row.get(currentDay, "").strip().lower()
                    if dayValue == "true":
                        rnCell = row.get("Reporting number", "").strip()
                        if rnCell == "":
                            # Auto-generate default reporting number using spreadsheet row number
                            reportingNumber = TU.MakeDefaultReportingNumberFromRow(rowNumber)  # e.g., TAS40
                        else:
                            reportingNumber = rnCell  # Use supplied RN as-is
                        formsNext = row.get("Forms", "").strip()
                        break
                    elif dayValue not in ["true", "false", ""]:
                        print("Warning: Unexpected value in timetable for day '{}' : '{}'".format(currentDay, dayValue))

            # --- Trigger script if match found ---
            if reportingNumber:
                scriptsPath = jmri.util.FileUtil.getScriptsPath()
                scriptName = None
                try:
                    # Prefer profile:jython workings via scheme resolution (non-breaking fallback)
                    scriptName = FileUtil.getExternalFilename("profile:jython/workings/" + str(direction) + "/" + str(reportingNumber) + ".py")
                except Exception:
                    scriptName = None
                if not scriptName:
                    scriptName = os.path.join(scriptsPath, "workings", direction, reportingNumber + ".py")
                if not os.path.isfile(scriptName):
                    print("No working script found for {} at {} (skipping)".format(reportingNumber, scriptName))
                else:
                    try:
                        execfile(scriptName)
                        print("Triggered script: " + scriptName)
                    except Exception as e:
                        print("Error triggering script '{}': {}".format(scriptName, e))

                    print("No working script found for {} at {} (skipping)".format(reportingNumber, scriptName))

