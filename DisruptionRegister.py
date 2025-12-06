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
#
# Class for storing data for delays and cancellations to trains.
# Cancellation = delay of > 1440 minutes

import jmri, os, json
from java.util import Hashtable
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri import ShutDownManager

register = Hashtable()

_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "disruption_register.json")

def registerDisruption(reportingNumber, delayMinutes):
    print("Registering", delayMinutes, "delay to", reportingNumber)
    register.put(reportingNumber, delayMinutes)

def getDisruption(reportingNumber):
    return register.get(reportingNumber)

def deregisterDisruption(reportingNumber):
    register.remove(reportingNumber)
    
def updateDisruption(reportingNumber, newDelayMinutes):
    if register.containsKey(reportingNumber):
        register.put(reportingNumber, newDelayMinutes)
        return True  # Indicate success
    else:
        return False  # Indicate failure (train not found)

def save():
    d = {}
    for k in register.keySet().toArray():
        d[str(k)] = int(register.get(k))
    with open(_SAVE_PATH, "w") as f:
        json.dump(d, f)

def load():
    if not os.path.exists(_SAVE_PATH):
        return
    with open(_SAVE_PATH, "r") as f:
        d = json.load(f)
    register.clear() 
    for k, v in d.items():
        try:
            register.put(k, int(v))
        except:
            register.put(k, 0)
        
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

# Register to save on shutdown on module import
_register_shutdown()

# Load on module import
load()