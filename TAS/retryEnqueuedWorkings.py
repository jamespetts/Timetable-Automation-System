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

import jmri, os, enqueuedWorkings, traceback, csv
# TAS_SYS_PATH_SNIPPET: make the TAS folder importable even when scripts: still points elsewhere.
try:
    import os as _tas_os_path
    import sys as _tas_sys_path
    _tas_script_dir = None
    try:
        import jmri as _tas_jmri_path
        _tas_script_dir = _tas_jmri_path.util.FileUtil.getExternalFilename('profile:jython/TAS')
    except Exception:
        _tas_script_dir = None
    if _tas_script_dir and _tas_script_dir not in _tas_sys_path.path:
        _tas_sys_path.path.insert(0, _tas_script_dir)
except Exception:
    pass
from jmri.profile import ProfileManager
import TASUtil as TU
import TASBeanLookup as TBL

import TASPathResolver as TPR
def get_forms_for(reporting_number):
    try:     
        memTimetable = TBL.ProvideMemoryBySuffix("CURRENTTIMETABLE", "")
        if memTimetable is None or memTimetable.getValue() is None:
            return ""
        timetable_name = memTimetable.getValue()
        profile = ProfileManager.getDefault().getActiveProfile()
        timetable_file = TPR.GetTimetableCsvPath(timetable_name)
        if not os.path.exists(timetable_file):
            return ""
        with open(timetable_file, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            # Spreadsheet semantics: header row is 1, first data row is 2
            for rowIndex, row in enumerate(reader, start=2):
                rnCell = (row.get("Reporting number", "") or "").strip()
                rn = rnCell if rnCell != "" else TU.MakeDefaultReportingNumberFromRow(rowIndex)
                if rn == reporting_number:
                    return (row.get("Forms", "") or "").strip()
        return ""
    except Exception as e:
        print("Error reading timetable for {}: {}".format(reporting_number, e))
        return ""

scriptsPath = jmri.util.FileUtil.getScriptsPath()

if enqueuedWorkings.countWorkings() == 0:
    print("No enqueued workings to check")
else:
    print("Checking", enqueuedWorkings.countWorkings(), "enqueued workings")
    # Iterate a copy of the enqueued workings list, as every time that a working fails
    # to run, it may re-enqueue itself, so we have to avoid infinite loops.
    workingsCopy = enqueuedWorkings.getEnqueuedWorkingsCopy()
    for reportingNumber, direction in workingsCopy:
        if not reportingNumber or not direction:
            continue
        scriptName = None
        try:
            scriptName = TPR.ResolveWorkingScriptReadPath(direction, reportingNumber)
        except Exception:
            scriptName = None
        if scriptName is None:
            scriptName = os.path.join(scriptsPath, "TAS", "workings", direction, reportingNumber + ".py")
        print("Retrying ", scriptName)
        formsNext = get_forms_for(reportingNumber)
        if formsNext == "":
            formsNext = None
        if not os.path.isfile(scriptName):
            print("No working script found for {} at {} (skipping)".format(reportingNumber, scriptName))
        else:
            try:
                execfile(scriptName)
            except Exception as e:
                # Keep traceback for real execution errors inside the script,
                # but avoid noise for simple "file not found" cases (handled above).
                traceback.print_exc()
                print("ERROR executing working script '{}': {}".format(scriptName, e))
    