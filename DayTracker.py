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
# This needs to be a STARTUP SCRIPT

import java
import jmri

class DayTracker(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):
        self.clock = memories.getMemory('IMCURRENTTIME')
        self.timebase = jmri.InstanceManager.getDefault(jmri.Timebase)
        self.dayMemory = memories.getMemory('IMDAYOFWEEK')
        self.dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        self.lastHour = -1

    def getMinutes(self):
        time = self.timebase.getTime()
        timeStorageFormat = java.text.SimpleDateFormat('HH:mm')
        hhmm = timeStorageFormat.format(time).split(':')
        return int(hhmm[0]) * 60 + int(hhmm[1])

    def handle(self):
        self.waitChange([self.clock])
        minutes = self.getMinutes()
        currentHour = minutes // 60

        # Detect rollover from late night to early morning
        if self.lastHour >= 22 and currentHour < 5:
            currentDayName = self.dayMemory.getValue()
            try:
                currentIndex = self.dayNames.index(currentDayName)
            except ValueError:
                currentIndex = 0  # Default to Monday if memory is invalid

            nextIndex = (currentIndex + 1) % 7
            nextDayName = self.dayNames[nextIndex]
            self.dayMemory.setValue(nextDayName)
            print('Day updated to: {}'.format(nextDayName))

        self.lastHour = currentHour
        return True

dayTracker = DayTracker()
dayTracker.setName('Day of week tracker')
dayTracker.start()