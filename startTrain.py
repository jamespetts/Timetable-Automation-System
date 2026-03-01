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

import jmri, os, sys, formationRegister, enqueuedWorkings, DisruptionRegister, time, OrientationRegister
from jmri.jmrit.dispatcher import TrainInfoFile, ActiveTrain, AutoActiveTrain
from jmri import InstanceManager
import TASPathResolver as TPR
import xml.etree.ElementTree as ET
import java
import TimingRegister as TR
import TASUtil as TU
import TrainLocatorRegister as TLR
import TASBeanLookup as TBL

def IsDefaultReportingNumber(s):
    # Treat as "default" only if it is exactly 'TAS' (uppercase) followed by digits
    try:
        x = str(s).strip()
    except Exception:
        return False
    if x == "":
        return False
    if not x.startswith("TAS"):
        return False
    # Require strictly digits after 'TAS'
    return x[3:].isdigit()

def addMinutesToTime(minutes_to_add):
    from datetime import datetime, timedelta

    currentTimeMemory = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")

    if currentTimeMemory is None or currentTimeMemory.getValue() is None:
        print("ERROR: IMCURRENTTIME memory not available or has no value.")
        return None, None

    currentTimeStr = str(currentTimeMemory.getValue()).strip()

    try:
        # Parse time in format like "9:19 AM"
        currentTime = datetime.strptime(currentTimeStr, "%I:%M %p")
    except ValueError:
        print("ERROR: IMCURRENTTIME value is not in expected format 'H:MM AM/PM':", currentTimeStr)
        return None, None

    # Add minutes
    newTime = currentTime + timedelta(minutes=minutes_to_add)

    return newTime.hour, newTime.minute


def checkEndBlock(traininfoName):
    # Read traininfo file
    profilePath = jmri.util.FileUtil.getProfilePath()
    filename = os.path.join(profilePath, "dispatcher", "traininfo", traininfoName + ".xml")

    if not os.path.isfile(filename):
        print("Error: traininfo file not found:", filename)
        return None

    tree = ET.parse(filename)
    root = tree.getroot()
    ti = root.find('traininfo')
    if ti is None:
        print("Error: traininfo element not found")
        return None

    # Use endblockid (system id) from the XML for lookup
    endBlockId = ti.get('endblockid')
    if not endBlockId:
        print("Error: endblockid not found in traininfo file")
        return None
    else:
        return endBlockId


def ResolveStartBlockFromTrainInfo(ti):
    """
    Resolve and return the jmri.Block that TrainInfo 'ti' will start from.
    Returns: jmri.Block or None
    """
    bm = InstanceManager.getDefault(jmri.BlockManager)

    # Prefer TrainInfo API
    try:
        if hasattr(ti, "getStartBlockId"):
            sbid = ti.getStartBlockId()
            if sbid:
                blk = bm.getBlock(sbid)
                if blk is not None:
                    return blk
    except Exception:
        pass

    try:
        if hasattr(ti, "getStartBlockName"):
            sbname = ti.getStartBlockName()
            if sbname:
                # Try user name first
                blk = bm.getByUserName(sbname)
                if blk is not None:
                    return blk
                # Fallback to named bean lookup if available in this build
                try:
                    nb = bm.getNamedBean(sbname)
                    if nb is not None:
                        return nb
                except Exception:
                    pass
    except Exception:
        pass

    return None


def IsStartSectionAllocatedForBlock(startBlock):
    """
    Return True if any Section that contains 'startBlock' is allocated,
    i.e. section.getState() != Section.FREE. Otherwise return False.
    Minimal, API-accurate, and robust across typical JMRI builds.
    """
    # Resolve the SectionManager from the correct package
    try:
        sectionManager = InstanceManager.getDefault(jmri.SectionManager)
    except Exception:
        sectionManager = None

    if sectionManager is None:
        print("ERROR: Section manager unavailable")
        return False

    # Obtain the set of Sections from the manager (preferred API)
    try:
        sections = sectionManager.getNamedBeanSet()
    except Exception:
        sections = None

    if not sections:
        return False

    # For a simple fallback, keep the start block's system name handy
    sbSys = None
    try:
        sbSys = startBlock.getSystemName() if startBlock is not None else None
    except Exception:
        pass

    for sec in sections:
        # 1) Prefer the direct membership check
        contains = False
        try:
            contains = bool(sec.containsBlock(startBlock))
        except Exception:
            contains = False

        # 2) Fallback: scan the section's block list if needed
        if not contains:
            try:
                blist = sec.getBlockList() or []
                for b in blist:
                    try:
                        if sbSys is not None and b.getSystemName() == sbSys:
                            contains = True
                            break
                    except Exception:
                        continue
            except Exception:
                contains = False

        if not contains:
            continue

        # Allocated <> state != FREE
        try:
            if sec.getState() != jmri.Section.FREE:
                return True
        except Exception:
            # If state not readable, treat as not allocated (fail open)
            pass

    return False
    
# --- Shared helpers for timing-point logging (camelCase) ---

def tpGetMainName():
    """Return current profile name as the timing point name (never empty)."""
    try:
        name = jmri.profile.ProfileManager.getDefault().getActiveProfileName()
        if name is None or str(name).strip() == "":
            return "DEFAULT"
        return str(name)
    except Exception:
        return "DEFAULT"

def tpGetBlocksSet():
    """
    Return a set of strings for the blocks assigned to the timing point.
    Values come from TimingRegister.assignBlocks(...).
    """
    tp = tpGetMainName()
    try:
        b = TR.getBlocks(tp)  # list[str] or None
    except Exception:
        b = None
    return set([str(x) for x in (b or [])])

def tpBlockMatchesList(block, namesSet):
    """
    True if 'block' matches any entry in namesSet by system name, user name, or str(block).
    """
    if block is None:
        return False
    try:
        sysn = str(block.getSystemName() or "")
    except Exception:
        sysn = ""
    try        :
        user = str(block.getUserName() or "")
    except Exception:
        user = ""
    if sysn in namesSet:
        return True
    if user in namesSet:
        return True
    if str(block) in namesSet:
        return True
    return False

def tpAnyTpBlockOccupied(namesSet):
    """
    True if any block named in namesSet is currently OCCUPIED.
    """
    try:
        bm = jmri.InstanceManager.getDefault(jmri.BlockManager)
    except Exception:
        return False
    if not namesSet:
        return False
    for n in namesSet:
        b = None
        try:
            b = bm.getByUserName(n)
        except Exception:
            b = None
        if b is None:
            try:
                b = bm.getBlock(n)
            except Exception:
                b = None
        if b is None:
            continue
        try:
            if b.getState() == jmri.Block.OCCUPIED:
                return True
        except Exception:
            pass
    return False

def tpGetTimeAndDay():
    """
    Read fast-clock time and day-of-week from JMRI memories.
    Returns (timeStr, dayStr); empty strings if unavailable.
    """
    try:        
        t = TBL.ProvideMemoryBySuffix("CURRENTTIME", "")
        d = TBL.ProvideMemoryBySuffix("DAYOFWEEK", "")
        timeStr = str(t.getValue()).strip() if (t is not None and t.getValue() is not None) else ""
        dayStr  = str(d.getValue()).strip() if (d is not None and d.getValue() is not None) else ""
        return timeStr, dayStr
    except Exception:
        return "", ""

def tpRegister(reportingNumber, direction, kind="Dep"):
    """
    Register a timing at the main timing point via TimingRegister.registerTiming(...).
    'kind' is only used for console logging.
    """
    tp = tpGetMainName()
    timeStr, dayStr = tpGetTimeAndDay()
    try:
        TR.registerTiming(tp, str(reportingNumber), str(direction), timeStr, dayStr)
        print("TimingRegister:", kind, "logged for", reportingNumber, "at", tp, "time", timeStr, "day", dayStr)
    except Exception as e:
        print("Warning: failed to register timing for", reportingNumber, "at", tp, ":", e)


# createActiveTrainFromTrainInfo(ti, rosterEntry) -> ActiveTrain
# - traininfoName: TrainInfo object (from TrainInfoFile.readTrainInfo)
# - rosterEntry: jmri.jmrit.roster.RosterEntry instance
# Registers the next working that this train forms
# Returns: ActiveTrain instance 

def startTrain(traininfoName, rosterEntry, reportingNumber, direction, formsNext = None):
    import formationRegister, enqueuedWorkings
    
    # Get the pre-generated disruption (None => treat as 0 on start)
    try:
        rawDelay = DisruptionRegister.getDisruption(reportingNumber)
    except Exception as e:
        # Intermittent JSON parse/IO issues should not block running the working
        print("Disruption generator error:", e)
        rawDelay = None
    try:
        delayMinutes = int(rawDelay) if rawDelay is not None else 0
    except Exception:
        delayMinutes = 0
        
    # Check whether this is starting from an enqueued working and also dequeue the working
    try:
        workingRN, workingDir = enqueuedWorkings.popWorking(reportingNumber, direction)
        print(workingRN)
    except:
        workingRN = None
        workingDir = None
        print("Did not remove " + reportingNumber + " from queue")
        
    if delayMinutes > 1440:
        # Train cancelled
        print("Train cancelled: " + reportingNumber)
        return None
    
    if not traininfoName:
        print("No train or trainfo file supplied. Will retry periodically.")    
        enqueuedWorkings.enqueueWorking(reportingNumber, direction)
        return None
    
    df = jmri.InstanceManager.getDefault(jmri.jmrit.dispatcher.DispatcherFrame)
    
    # Make sure that we always wait the minimum turnaround time before departing
    if workingRN is not None:
        mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
        raw = TBL.ProvideMemoryBySuffix("TASTURNAROUNDMINUTES", "0").getValue()
        try:
            turnaroundTime = int(str(raw))          # This is necessary as the memory variable is a string by default
        except Exception:
            print(u"TASTURNAROUNDMINUTES is not numeric: {!r}".format(raw))
            turnaroundTime = 0

        delayMinutes = int(delayMinutes)            # belt & braces
        delayMinutes = max(delayMinutes, turnaroundTime)
      
    # This is necessary to inject our reporting number as a name.
    # Thanks to Dave Sand for this code snippet.
    tif = jmri.jmrit.dispatcher.TrainInfoFile()
    ti = tif.readTrainInfo(traininfoName + ".xml")
    # Register RN -> RosterID mapping for train location/disruption purposes.
    try:
        if (reportingNumber is not None) and (rosterEntry is not None):
            rid = rosterEntry.getId()
            if rid is not None:
                # Overwrite and enforce uniqueness per rosterId
                TLR.registerTrain(str(reportingNumber), str(rid))
    except Exception as _e:
        # Non-fatal; continue even if the locator mapping failed
        print("Warning: TrainLocatorRegister failed:", _e)
    # For any TAS-prefixed RN (auto or user-supplied), do not set the train user name.
    if (reportingNumber is not None) and (not TU.IsDefaultReportingNumber(reportingNumber)):
        ti.setTrainUserName(reportingNumber)
    if OrientationRegister.IsContained(rosterEntry.getId()):
        # This train is in reverse orientation compared to what is expected. Reverse the orientation in the TrainInfo object.
        ti.setRunInReverse(not ti.getRunInReverse())
    if delayMinutes > 0:
        hour, minute = addMinutesToTime(delayMinutes)
        if hour is not None and minute is not None:
            ti.setDepartureTimeHr(hour)
            ti.setDepartureTimeMin(minute)
            ti.setDelayedStart(ActiveTrain.TIMEDDELAY)
            print("Setting departure time to: ", hour, ":", minute)
    # Use a unique name per attempt to avoid file-lock collisions
    uniqueSuffix = u"{}_{}_{}".format(
        reportingNumber if reportingNumber is not None else "UNKNOWN",
        os.getpid(),
        int(time.time())
    )
    cloneName = "clone_{}.xml".format(uniqueSuffix)

    tif.writeTrainInfo(ti, cloneName)
    
    # Disable the time warp instantly
    TBL.SafeSetMemoryValue("ALLOWTIMEWARP", "false")
        
    startBlock = ResolveStartBlockFromTrainInfo(ti)
    if(IsStartSectionAllocatedForBlock(startBlock)):
        print("Error: Start block defined in", rosterEntry.getId(), " ", traininfoName, " is already allocated.")
        activeTrain = None
    else:         
        if rosterEntry is not None:
            df.loadTrainFromTrainInfo(cloneName, "ROSTER", rosterEntry.getId())
        else:
            df.loadTrainFromTrainInfo(cloneName)
        activeTrain = df.getActiveTrainForRoster(rosterEntry)
    
    # Best-effort cleanup: remove the per-attempt traininfo file we just used
    try:
        profilePath = jmri.util.FileUtil.getProfilePath()
        tiPath = os.path.join(profilePath, "dispatcher", "traininfo", cloneName)
        if os.path.isfile(tiPath):
            os.remove(tiPath)
    except Exception:
        print("Warning: failed to erase " + tiPath)
        pass
    
    if activeTrain is None:
        print("Error starting train: failed to create active train for ", rosterEntry.getId(), " ", traininfoName)
        enqueuedWorkings.enqueueWorking(reportingNumber, direction)
    else:
        if activeTrain.getTransit() is not None:         
            print("Starting train: ", activeTrain.getActiveTrainName())     
                      
            # Set up a listener for its termination
            class ATListener(java.beans.PropertyChangeListener):
                # --- Case (1) setup ---
                def __init__(self):
                    try:
                        self.tpNames = tpGetBlocksSet()
                    except Exception:
                        self.tpNames = set()
                    self.armedThrottle = False
                    self.depLogged = False
                    self.fallbackArmed = False
                    self.throttleListener = None
                    self.throttleAddress = None
                    # Case (3) flags also live here for convenience:
                    self.armedAfterPause = False
                    self.depLoggedAfterPause = False
                    self.arrLogged = False
                
                def armDepartureOnPhysicalMove(self, at):
                    """
                    Attach a throttle listener that logs departure at first SpeedSetting > 0,
                    but only if this ActiveTrain starts at the timing point.
                    """
                    if self.armedThrottle or self.depLogged:
                        return
                    try:
                        startBlk = at.getStartBlock()
                    except Exception:
                        startBlk = None

                    # Obtain loco address from roster entry
                    try:
                        re = at.getRosterEntry()
                        print("Arm 4")
                    except Exception:
                        re = None
                    locoAddr = None
                    if re is not None:
                        try:
                            locoAddr = re.getDccLocoAddress()  # BasicRosterEntry API
                        except Exception:
                            locoAddr = None

                    if locoAddr is None:
                        self.fallbackArmed = True
                        return

                    # One-shot listener for throttle "SpeedSetting"
                    tm = jmri.InstanceManager.getDefault(jmri.ThrottleManager)
                    outer = self

                    class _ThrottleMoveListener(java.beans.PropertyChangeListener):
                        def __init__(self, tmgr, addr):
                            self.tmgr = tmgr
                            self.addr = addr
                            self.done = False
                        def propertyChange(self, ev):
                            if self.done:
                                return
                            try:
                                if str(ev.getPropertyName()) == "SpeedSetting":
                                    try:
                                        v = float(ev.getNewValue())
                                    except Exception:
                                        v = 0.0

                                    if v > 0.0:
                                        print("Train started moving: " + reportingNumber)
                                        if not outer.depLogged:
                                            tpRegister(reportingNumber, direction, kind="Dep")
                                            outer.depLogged = True
                                            self.done = True
                                            try:
                                                self.tmgr.removeListener(self.addr, self)
                                            except Exception:
                                                pass
                            except Exception:
                                pass

                    try:
                        l = _ThrottleMoveListener(tm, locoAddr)
                        tm.attachListener(locoAddr, l)  # observe, do not own throttle
                        self.throttleListener = l
                        self.throttleAddress = locoAddr
                        self.armedThrottle = True
                    except Exception:
                        self.fallbackArmed = True
                
                
                
                # --- Physical timing points: block->TP listeners (minimal, robust) ---

                def BuildPhysicalTPBlockMap(self):
                    # Build self.blockToTpNames: jmri.Block -> set([tpName,...])
                    self.blockToTpNames = {}
                    try:
                        bm = InstanceManager.getDefault(jmri.BlockManager)
                    except Exception:
                        return

                    try:
                        tps = TR.listTimingPoints() or []
                    except Exception:
                        tps = []

                    # Exclude the base/main TP (handled elsewhere in this file)
                    try:
                        mainLower = str(tpGetMainName()).strip().lower()
                    except Exception:
                        mainLower = ""

                    for tp in tps:
                        try:
                            tpLower = str(tp).strip().lower()
                        except Exception:
                            tpLower = ""
                        if tpLower == mainLower:
                            continue

                        # Names configured for this physical TP
                        try:
                            names = TR.getBlocks(tp) or []
                        except Exception:
                            names = []

                        for n in names:
                            b = None
                            # Resolve by system name first
                            try:
                                b = bm.getBlock(str(n))
                            except Exception:
                                b = None
                            # Fallback to user name
                            if b is None:
                                try:
                                    b = bm.getByUserName(str(n))
                                except Exception:
                                    b = None
                            if b is None:
                                continue

                            # Map block -> set of TP names (allow multiple TPs per block if needed)
                            s = self.blockToTpNames.get(b)
                            if s is None:
                                s = set()
                                self.blockToTpNames[b] = s
                            s.add(str(tp))

                def AttachPhysicalTPListeners(self, at):
                    # Prepare per-TP dedupe and listener storage
                    if not hasattr(self, "blockToTpNames"):
                        self.blockToTpNames = {}
                    self.tpArrLogged = set()   # TP names with Arr already logged
                    self.tpDepLogged = set()   # TP names with Dep already logged
                    self.blockListeners = []

                    # Build mapping (skip if no blocks assigned anywhere)
                    try:
                        self.BuildPhysicalTPBlockMap()
                    except Exception:
                        self.blockToTpNames = {}

                    if not self.blockToTpNames:
                        return  # nothing to attach

                    outer = self

                    # Listener that reacts to this block's 'state' changes
                    class _BlockStateListener(java.beans.PropertyChangeListener):
                        def __init__(self, block):
                            self.block = block

                        def propertyChange(self, ev):
                            # Only react to state changes on this block
                            try:
                                pname = ev.getPropertyName()
                            except Exception:
                                pname = ""
                            if pname != "state":
                                # Some JMRI builds define a constant; accept either form
                                try:
                                    if pname != jmri.Block.PROPERTY_STATE:
                                        return
                                except Exception:
                                    return

                            try:
                                newState = int(ev.getNewValue())
                            except Exception:
                                newState = None

                            # Arrival on OCCUPIED; Departure on first state != OCCUPIED
                            try:
                                tpSet = outer.blockToTpNames.get(self.block, set())
                            except Exception:
                                tpSet = set()

                            # Read current time/day once per event
                            timeStr, dayStr = tpGetTimeAndDay()

                            if newState == jmri.Block.OCCUPIED:
                                # ARRIVAL
                                for tpName in list(tpSet):
                                    if tpName in outer.tpArrLogged:
                                        continue
                                    try:
                                        TR.registerTiming(tpName, reportingNumber, direction, timeStr, dayStr)
                                        outer.tpArrLogged.add(tpName)
                                    except Exception as e:
                                        print("Warning: failed to register physical TP Arr for", tpName, ":", e)
                            else:
                                # DEPARTURE
                                for tpName in list(tpSet):
                                    if tpName in outer.tpDepLogged:
                                        continue
                                    try:
                                        TR.registerTiming(tpName, reportingNumber, direction, timeStr, dayStr)
                                        outer.tpDepLogged.add(tpName)
                                    except Exception as e:
                                        print("Warning: failed to register physical TP Dep for", tpName, ":", e)

                    # Attach one listener per block
                    for blockBean in list(self.blockToTpNames.keys()):
                        try:
                            lst = _BlockStateListener(blockBean)
                            blockBean.addPropertyChangeListener(lst)
                            self.blockListeners.append((blockBean, lst))
                        except Exception as e:
                            print("Warning: could not attach block listener:", e)
                
                def propertyChange(self, event):                        
                    # Case (1) fallback: WAITING -> RUNNING if we could not attach a throttle listener
                    if self.fallbackArmed and not self.depLogged and \
                       event.getPropertyName() == jmri.jmrit.dispatcher.ActiveTrain.PROPERTY_STATUS:
                        try:
                            newStatus = int(event.getNewValue())
                            oldStatus = int(event.getOldValue()) if event.getOldValue() is not None else None
                        except Exception:
                            newStatus = None
                            oldStatus = None
                        if oldStatus == jmri.jmrit.dispatcher.ActiveTrain.WAITING and \
                           newStatus == jmri.jmrit.dispatcher.ActiveTrain.RUNNING:
                            src = event.getSource()
                            if isinstance(src, jmri.jmrit.dispatcher.ActiveTrain):
                                tpRegister(reportingNumber, direction, kind="Dep")
                                self.depLogged = True
                                self.fallbackArmed = False
                    
                    # Case (3): through train; depart after scheduled dwell at timing point
                    if event.getPropertyName() == jmri.jmrit.dispatcher.ActiveTrain.PROPERTY_STATUS:
                        try:
                            newStatus = int(event.getNewValue())
                            oldStatus = int(event.getOldValue()) if event.getOldValue() is not None else None
                        except Exception:
                            newStatus = None; oldStatus = None

                        # Arm when entering a scheduled dwell (PAUSED) while a timing-point block is occupied
                        if newStatus == jmri.jmrit.dispatcher.ActiveTrain.PAUSED:
                            try:
                                if tpAnyTpBlockOccupied(tpGetBlocksSet()):
                                    self.armedAfterPause = True
                            except Exception:
                                pass

                        # Log departure on first RUNNING after that PAUSED
                        if self.armedAfterPause and newStatus == jmri.jmrit.dispatcher.ActiveTrain.RUNNING:
                            print("Train running after pause: " + reportingNumber)
                            if not self.depLoggedAfterPause:
                                tpRegister(reportingNumber, direction, kind="Dep")
                                self.depLoggedAfterPause = True
                            self.armedAfterPause = False
                    
                    pname = event.getPropertyName()
                    if pname == ActiveTrain.PROPERTY_MODE:
                        new_mode = int(event.getNewValue())   
                        if new_mode == ActiveTrain.TERMINATED:
                            print("Train terminated:", reportingNumber)                           
                            # Remove physical TP block listeners
                            try:
                                if hasattr(self, "blockListeners"):
                                    for (blockBean, lst) in list(self.blockListeners or []):
                                        try:
                                            blockBean.removePropertyChangeListener(lst)
                                        except Exception:
                                            pass
                                    self.blockListeners = []
                            except Exception:
                                pass

                            # Case (2): arrival at main timing point upon termination
                            if not self.arrLogged:
                                tpRegister(reportingNumber, direction, kind="Arr"); self.arrLogged = True
                            DisruptionRegister.deregisterDisruption(reportingNumber)
                            
                            # We need to retry the enqueued workings immediately here so that we
                            # cannot time warp to the next working afterwards if there is an enqueued working
                            # waiting for this train.
                            scriptsPath = jmri.util.FileUtil.getScriptsPath()
                        try:
                            scriptName = TPR.ResolveScriptReadPath("retryEnqueuedWorkings.py")
                        except Exception:
                            scriptName = None
                        if scriptName is None:
                            scriptName = os.path.join(scriptsPath, "retryEnqueuedWorkings.py")
                        execfile(scriptName)                            

            atlisten = ATListener()
            activeTrain.addPropertyChangeListener(atlisten)
            # Arm the passive throttle listener immediately so we can't miss the first movement
            atlisten.armDepartureOnPhysicalMove(activeTrain)
                    
            # Attach per-block listeners for physical timing points
            atlisten.AttachPhysicalTPListeners(activeTrain)
            
            # Then erase the current working's entry in the formation register
            formationRegister.deregisterTrain(reportingNumber)
            
            # Now register this train with its next formation reporting number.
            if formsNext is not None:
                # The "forms" entry in the timetable is not compulsory. Only create an entry
                # if the string representing this is non-null.
                formationRegister.registerNextFormation(str(formsNext), rosterEntry.getId())          
        else:
            print("Error: ActiveTrain has no Transit assigned for ", rosterEntry.getId(), " ", traininfoName)
            enqueuedWorkings.enqueueWorking(reportingNumber, direction)
    
    return activeTrain
    
    
