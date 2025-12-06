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
# Note that each entry is a tuple of reportingNumber and direction

import jmri, os, json
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

orientation = []

_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "OrientationRegister.json")

def AddTrain(rosterID):
    if rosterID not in orientation:
        orientation.append(rosterID)
    else:
        print("Warning: attempting to append a duplicate train to the orientation register: " + rosterID)
    
def GetTrain(index):
    return orientation[index]

def RemoveTrain(rosterID):
     orientation.remove(rosterID)
     
def GetOrientationRegisterCopy():
    return orientation[:]
     
def CountTrains():
    return len(orientation)
    
def IsContained(rosterID):
    return rosterID in orientation
    
def save():
    # orientation is a list of strings; write it directly as JSON
    try:
        with open(_SAVE_PATH, "w") as f:
            json.dump(list(orientation), f)
    except Exception as e:
        print("Warning: failed to save OrientationRegister.json: {}".format(e))

def load():
    # Load list of strings directly; start empty if file missing or unreadable
    if not os.path.exists(_SAVE_PATH):
        orientation[:] = []
        return
    try:
        with open(_SAVE_PATH, "r") as f:
            loaded = json.load(f)
        # Ensure the loaded data is a list of strings
        orientation[:] = [str(x) for x in loaded]
    except Exception as e:
        print("Warning: failed to load OrientationRegister.json: {}".format(e))
        orientation[:] = []

# Try JMRI shutdown manager, fall back to JVM hook
def _register_shutdown():
    try:
        ShutDownManager.instance().addShutdownTask(save)
        return
    except Exception:
        pass
    try:
        class _Saver(Runnable):
            def run(self):
                try:
                    save()
                except Exception:
                    pass
        Runtime.getRuntime().addShutdownHook(Thread(_Saver()))
    except Exception:
        pass

# Register to save on shutdown and load on import
_register_shutdown()
load()
