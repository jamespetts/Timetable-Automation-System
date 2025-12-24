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
# Register for storing data showing the platform that trains have been allocated.
# Used for PIDs to handle platform alterations.
# If the train is not registered in this hashtable, it is assumed to have its timetable allocated platform
# Platforms are stored as strings.

import jmri, os, json
from java.util import Hashtable
from jmri.util import FileUtil
from java.lang import Runtime, Thread, Runnable
from jmri.implementation import AbstractShutDownTask
from jmri import ShutDownManager

register = Hashtable()

_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "platform_allocation_register.json")

def registerPlatform(reportingNumber, platform):
    print("Registering", reportingNumber, "at platform", platform)
    register.put(reportingNumber, str(platform))

def getPlatform(reportingNumber):
    return register.get(reportingNumber)

def deregisterPlatform(reportingNumber):
    register.remove(reportingNumber)
    
def updatePlatform(reportingNumber, platform):
    if register.containsKey(reportingNumber):
        register.put(reportingNumber, str(platform))
        return True  # Indicate success
    else:
        return False  # Indicate failure (train not found)

def save():
    d = {}
    for k in register.keySet().toArray():
        v = register.get(k)
        d[str(k)] = "" if v is None else str(v)
    try:
        with open(_SAVE_PATH, "w") as f:
            json.dump(d, f)
    except Exception as e:
        print("PlatformAllocationRegister: save() failed:", str(e))

def load():
    if not os.path.exists(_SAVE_PATH):
        return
    try:
        with open(_SAVE_PATH, "r") as f:
            d = json.load(f)
    except Exception as e:
        print("PlatformAllocationRegister: load() failed:", str(e))
        return
    register.clear()
    for k, v in d.items():
        try:
            register.put(str(k), "" if v is None else str(v))
        except Exception as e:
            print("PlatformAllocationRegister: load() entry failed:", str(e))
        
class _SaveTask(AbstractShutDownTask):
    def __init__(self):
        AbstractShutDownTask.__init__(self, "PlatformAllocationRegister Save")
    # JMRI calls run() during shutdown (post-4.20 guidance).
    def run(self):
        save()

class _Saver(Runnable):
    # JVM fallback hook; print any exception instead of swallowing it.
    def run(self):
        try:
            save()
        except Exception as e:
            print("PlatformAllocationRegister: JVM save() failed:", str(e))

def _register_shutdown():
    # Primary: JMRI shutdown manager via InstanceManager
    try:
        jmri.InstanceManager.getDefault(jmri.ShutDownManager).register(_SaveTask())
        return
    except Exception as e:
        print("PlatformAllocationRegister: JMRI shutdown registration failed:", str(e))
    # Fallback: JVM shutdown hook
    try:
        Runtime.getRuntime().addShutdownHook(Thread(_Saver()))
    except Exception as e:
        print("PlatformAllocationRegister: JVM shutdown hook registration failed:", str(e))


# Register to save on shutdown on module import
_register_shutdown()

# Load on module import
load()