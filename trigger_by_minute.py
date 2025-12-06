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

import time
import threading

def fast_clock_monitor():
    import jmri
    from jmri import InstanceManager
    import os

    memory = InstanceManager.getDefault(jmri.MemoryManager).getMemory("IMCURRENTTIME")
    if memory is None:
        print("[FastClockTrigger] ERROR: IMCURRENTTIME memory not found.")
        return

    print("[FastClockTrigger] Background thread started. Monitoring fast clock...")

    last_minute = None

    # Get the JMRI user files directory
    jmri_user_path = os.path.expanduser("~\\Documents\\Model railway\\JMRI")
    script_path = os.path.join(jmri_user_path, "Maesteg", "jython", "adjust_lighting_by_time.py")

    while True:
        current_time = memory.getValue()
        if current_time:
            try:
                clean_time = current_time.replace("AM", "").replace("PM", "").strip()
                hour, minute = map(int, clean_time.split(":"))

                if minute != last_minute:
                    last_minute = minute
                    print("[FastClockTrigger] Minute changed to {}. Running script...".format(minute))

                    try:
                        execfile(script_path)
                    except Exception as e:
                        print("[FastClockTrigger] Error running script: {}".format(e))

            except Exception as e:
                print("[FastClockTrigger] Error parsing time '{}': {}".format(current_time, e))

        time.sleep(5)

# Start the background thread
thread = threading.Thread(target=fast_clock_monitor)
thread.setDaemon(True)
thread.start()

print("[FastClockTrigger] Monitoring thread launched.")