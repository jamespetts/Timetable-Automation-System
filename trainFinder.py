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
import jmri, os
import TrainLocatorRegister as TLR

# Find a start block and a train
#
# First parameter: a list of file names of traininfo files. Will be checked in order for a suitable train.
# If neither of the following parameters are set, it will choose the first traininfo file whose start block
# contains any train.
#
# Second parameter: the reporting number of the working (to force a train formed from a previous working for this working)
# Default: will not be restricted to the specific train
#
# Third parameter: a list of roster IDs of trains that may be used
# Default: will not be restricted to finding one of these trains
def trainFinder(traininfoNames, rosterIds=None, reportingNumber=None):
    import xml.etree.ElementTree as ET
    from jmri import InstanceManager
    from jmri.util import FileUtil
    import formationRegister 
    
    # Helper: check if Transit is idle
    def isTransitIdle(traininfoName):
        try:
            filename = FileUtil.getProfilePath() + "/dispatcher/traininfo/" + traininfoName + ".xml"
            if not os.path.isfile(filename):
                return True  # Missing file: treat as available
            tree = ET.parse(filename)
            root = tree.getroot()
            ti = root.find('traininfo')
            if ti is None:
                return True
            transitId = ti.get('transitid')
            if not transitId:
                return True
            tm = InstanceManager.getDefault(jmri.TransitManager)
            transit = tm.getTransit(transitId)
            if transit and transit.getState() != jmri.Transit.IDLE:
                return False
        except Exception:
            return True  # Fail-safe: assume available
        return True
    
    for passNum in [1, 2]:
        for traininfoName in traininfoNames:          
            if passNum == 1 and not isTransitIdle(traininfoName):
                        continue  # Skip busy Transit in first pass
                        
            # Read traininfo file
            filename = FileUtil.getProfilePath() + "/dispatcher/traininfo/" + traininfoName + ".xml"
            if not os.path.isfile(filename):
                print("Error: traininfo file not found:", filename)
                continue

            tree = ET.parse(filename)
            root = tree.getroot()
            ti = root.find('traininfo')
            if ti is None:
                print("Error: traininfo element not found")
                continue

            # Use startblockid (system id) from the XML for lookup
            start_block_id = ti.get('startblockid')
            if not start_block_id:
                print("Error: startblockid not found in traininfo file")
                continue

            # Get block object by id
            blockManager = InstanceManager.getDefault(jmri.BlockManager)
            block = blockManager.getBlock(start_block_id)
            if block is None:
                print("Error: Block not found:", start_block_id)
                continue

            # Check occupancy
            if block.getState() != jmri.Block.OCCUPIED:
                print("Block", start_block_id, "is not occupied")
                continue

            # Roster handle
            roster = jmri.jmrit.roster.Roster.getDefault()

            # If a reporting number is supplied, prefer formation mapping; fallback to locator
            if reportingNumber is not None:
                rnKey = str(reportingNumber).strip()
                rnKeyUp = rnKey.upper()

                # Formation FIRST (authoritative)
                rosterId = formationRegister.getTrainForFormation(rnKey)

                # Fallback: Train Locator Register
                if rosterId is None or str(rosterId).strip() == "":
                    rosterId = TLR.getRosterId(rnKeyUp)

                print("Using pre-defined train", rosterId, "for working", rnKey)
                rosterEntry = roster.getEntryForId(rosterId)
                if rosterEntry is None:
                    print(u"Train {} not found in the start block for working {}".format(rosterId, rnKey))
                    return None, None

                # We must return here: when a train is registered for this working, use only this train.
                return rosterEntry, traininfoName

            # No reporting number supplied: infer from the start block
            # Check block memory
            memValue = block.getValue()
            if memValue is None:
                print("Error: Memory value is empty in block", block)
                continue

            text = str(memValue).strip()

            # Try roster numeric index first
            rosterEntry = None
            try:
                rosterEntry = roster.getEntry(int(text))
            except Exception:
                rosterEntry = roster.getEntryForId(text)

            # If not a roster id/index, try block value as a reporting number via the locator
            if rosterEntry is None and text != "":
                rid = TLR.getRosterId(text.upper())
                if rid:
                    rosterEntry = roster.getEntryForId(rid)

            # If we have specific trains in mind, ensure the detected train is one of them
            print("Check roster entry", rosterEntry)
            if rosterEntry:
                if not rosterIds:
                    print("Found train:", rosterEntry)
                    return rosterEntry, traininfoName
                else:
                    for rosterId in rosterIds:
                        print("Checking...", rosterId, rosterEntry)
                        if rosterEntry is roster.getEntryForId(rosterId):
                            print("Found train:", rosterEntry)
                            return rosterEntry, traininfoName

            # Fall back to DCC address (possibly with "LD" prefix)
            dccAddress = text
            if dccAddress is None:
                print("Error: memory value empty after conversion (getTrainFromTraininfo)")
                continue
            if dccAddress.upper().startswith("LD"):
                dccAddress = dccAddress[2:]

            # If a specific set of trains was provided, only allow those with matching DCC address
            permissibleTrain = False
            if rosterIds:
                for rosterId in rosterIds:
                    try:
                        if roster.getEntryForId(rosterId).getDccAddress() == dccAddress:
                            permissibleTrain = True
                            break
                    except Exception:
                        continue
            else:
                permissibleTrain = True

            if permissibleTrain == False:
                print("No permissible train", permissibleTrain)
                continue

            # Search roster for matching DCC address
            matches = jmri.jmrit.roster.Roster.getDefault().getEntriesByDccAddress(dccAddress)

            # Prefer entry with speed profile
            try:
                it = iter(matches)
            except Exception:
                it = None
            if it is not None:
                for entry in matches:
                    try:
                        if entry is not None and entry.getSpeedProfile():
                            return entry, traininfoName
                    except Exception:
                        pass

            # If there are no matches at all, try the next traininfo (or fail at end)
            emptyMatches = False
            try:
                emptyMatches = (matches is None) or (matches.size() == 0)
            except Exception:
                try:
                    emptyMatches = (matches is None) or (len(matches) == 0)
                except Exception:
                    emptyMatches = True

            if emptyMatches:
                print("No roster entries found with DCC address:", dccAddress, "for start block", start_block_id, "in", traininfoName)
                continue  # continue the 'for traininfoName in traininfoNames' loop

            # Otherwise use the first available match
            try:
                rosterEntry = matches.get(0)
            except Exception:
                try:
                    rosterEntry = matches[0]
                except Exception:
                    rosterEntry = None

            if rosterEntry is None:
                print("Vehicle not found for DCC address:", dccAddress)
                continue  # try next traininfo file

            return rosterEntry, traininfoName

    print("Failed to find train")
    return None, None