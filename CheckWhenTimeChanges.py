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
# This needs to be a STARTUP SCRIPT

import jmri, os
from jmri.util import FileUtil
from jmri.profile import ProfileManager
from java.beans import PropertyChangeListener
import TASBeanLookup as TBL

class CheckWhenTimeChanges(PropertyChangeListener):
    def propertyChange(self, event):
        if event.getPropertyName() == "value":
            scriptsPath = jmri.util.FileUtil.getScriptsPath()
            
            memoryManager = jmri.InstanceManager.getDefault(jmri.MemoryManager)
            memAutoWorking = TBL.FindMemoryBySuffix("TASAUTOWORKING")
            
            autoWorking = False
            if memAutoWorking is not None:
                val = memAutoWorking.getValue()
                if val is not None:
                    t = str(val).strip().lower()
                    autoWorking = t in ["true", "1", "yes", "on"]
    
            if autoWorking:
                try:          
                    scriptName = os.path.join(scriptsPath, "RunWTT.py")
                    execfile(scriptName)
                except Exception as e:
                    print("Error executing:", scriptName, e)
                try:
                    scriptName = os.path.join(scriptsPath, "retryEnqueuedWorkings.py")
                    execfile(scriptName)
                except Exception as e:
                    print("Error executing:", scriptName, e)
            try:
                scriptName = os.path.join(scriptsPath, "CheckTimingPoints.py")
                execfile(scriptName)
            except Exception as e:
                print("Error executing:", scriptName, e)

# Attach the listener
memoryManager = jmri.InstanceManager.getDefault(jmri.MemoryManager)
memCurrentTime = TBL.FindMemoryBySuffix("CURRENTTIME")

if memCurrentTime is not None:
    listener = CheckWhenTimeChanges()
    memCurrentTime.addPropertyChangeListener(listener)
    print("Listener attached to CURRENTTIME.")
else:
    print("Error: CURRENTTIME memory variable not found.")