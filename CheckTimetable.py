# DEPRECATED, FAULTY.
# This does not work. Use an alternative approach. Trigger things from LogixNG. That is the only way of accessing LogixNG data, it seems.
import jmri
from java.lang import System
from datetime import datetime
import java

class CheckTimetableAutomation(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):

        # Initialise the automation

        # Days for compatibility with DayTracker
        self.days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        # Validate required memories exist
        try:
            self.current_time_mem = memories.getMemory("IMCURRENTTIME")
            self.current_day_mem = memories.getMemory("IMDAYOFWEEK")
            
            if not self.current_time_mem or not self.current_day_mem:
                raise ValueError("Missing time or day memory")
        except Exception as e:
            print("Initialization error: {}".format(e))

    def handle(self):

        # Main automation handling method

        try:
            # Retrieve current time and day
            current_time = self.current_time_mem.getValue()  # HH:MM
            current_day = self.current_day_mem.getValue()    # e.g., "Monday"
            
            # Validate input
            if not current_time or not current_day:
                print("Missing current time or day memory.")
                return False
            
            # Parse current time
            if "AM" in current_time or "PM" in current_time:
                now = datetime.strptime(current_time.strip(), "%I:%M %p")
            else:
                now = datetime.strptime(current_time.strip(), "%H:%M")
            
            # Access LogixNG table
            table_manager = jmri.InstanceManager.getDefault(jmri.jmrit.logixng.LogixNGTableManager)
            table = table_manager.getTable("Timetable")
            
            if not table:
                print("Timetable table not found.")
                return False
            
            # Check each row for matching time and day
            for row in table.getRows():
                dep_time_str = row.getColumn("DepartureTime")
                if not dep_time_str:
                    continue
                
                if "AM" in current_time or "PM" in current_time:
                    now = datetime.strptime(current_time.strip(), "%I:%M %p")
                else:
                    now = datetime.strptime(current_time.strip(), "%H:%M")
                
                # Check if departure time matches current time and day is active
                if (dep_time.strftime("%H:%M") == now.strftime("%H:%M") and 
                    row.getColumn(current_day) == True):
                    
                    reporting_number = row.getColumn("ReportingNumber")
                    traininfo_file = row.getColumn("TrainInfoFile")
                    
                    if reporting_number and traininfo_file:
                        # Set system property to pass arguments to ActivateTrain script
                        System.setProperty("ActivateTrain.args", "{} {}".format(traininfo_file, reporting_number))
                        
                        # Execute activation script
                        try:
                            execfile("scripts/ActivateTrain.py")
                            print("Activated train {} from {}".format(reporting_number, traininfo_file))
                        except Exception as script_error:
                            print("Error executing ActivateTrain script: {}".format(script_error))
                        
                        # Return False to stop further processing after first match
                        return False
            
            # If no matching row found, continue checking
            return True
        
        except Exception as e:
            print("Unexpected error in timetable check: {}".format(e))
            return False

    def stop(self):

        # Clean up method when automation is stopped

        print("CheckTimetable automation stopped")

# Create and start the automation
CheckTimetableAutomation().start()
