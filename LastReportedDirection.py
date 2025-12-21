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
# Monitors LocoNet E0 (OPC_MULTI_SENSE_LONG) messages and stores last reported
# direction per roster ID. Also updates OrientationRegister for all roster
# entries that share the same DCC address, based on NormalDirectionRegister.
#
# Rules for orientation updates:
# - If the roster ID has a normal direction in NormalDirectionRegister:
#     - If reported direction equals normal -> ensure it is NOT in OrientationRegister.
#     - If reported direction differs       -> ensure it IS in OrientationRegister.
# - If no normal direction entry exists -> take no action.
# - Apply the above to all roster entries that share the reported DCC address.
#
# ASCII only; CamelCase; case-insensitive roster IDs for NDR API; portable paths.

import jmri, os, json
from jmri.util import FileUtil
from jmri.jmrix.loconet import LocoNetListener, LocoNetMessage, LocoNetInterface
from jmri import ShutDownManager
from java.lang import Runtime, Thread, Runnable

# Debug toggle
DEBUG = True  # Set to False to disable debug output

# Global dictionary: key = roster ID (display case), value = direction string
lastReportedDirection = {}

# Persistence path (relative to profile path)
_SAVE_PATH = os.path.join(FileUtil.getProfilePath(), "LastReportedDirection.json")

def debug(msg):
    if DEBUG:
        try:
            print("[LastReportedDirection] " + str(msg))
        except Exception:
            pass

# Optional imports: orientation and normal direction registers
try:
    import OrientationRegister as OR
except Exception:
    OR = None

try:
    import NormalDirectionRegister as NDR
except Exception:
    NDR = None

def _NormId(s):
    # Case-insensitive ID normalization
    try:
        return str(s).strip().lower()
    except Exception:
        return ""

# Save dictionary to JSON
def save():
    try:
        with open(_SAVE_PATH, "w") as f:
            json.dump(lastReportedDirection, f)
        debug("Saved LastReportedDirection.json")
    except Exception as e:
        try:
            print("Warning: failed to save LastReportedDirection.json: {0}".format(e))
        except Exception:
            pass

# Load dictionary from JSON
def load():
    global lastReportedDirection
    if not os.path.exists(_SAVE_PATH):
        lastReportedDirection = {}
        return
    try:
        with open(_SAVE_PATH, "r") as f:
            loaded = json.load(f)
        # Normalize to dict of str -> str
        lastReportedDirection = {str(k): str(v) for (k, v) in loaded.items()}
        debug("Loaded LastReportedDirection.json")
    except Exception as e:
        try:
            print("Warning: failed to load LastReportedDirection.json: {0}".format(e))
        except Exception:
            pass
        lastReportedDirection = {}

# Listener class
class LastDirectionListener(LocoNetListener):
    def message(self, msg):
        try:
            # Basic sanity: Multi Sense Long, enough bytes
            if msg is None:
                return
            n = msg.getNumDataElements()
            if n < 7:
                return
            if msg.getOpCode() != 0xE0:  # OPC_MULTI_SENSE_LONG
                return

            # Extract DCC address (bytes 4 and 5)
            adHigh = msg.getElement(4)
            adLow = msg.getElement(5)
            address = (adHigh << 7) | (adLow & 0x7F)
            dccAddressStr = str(address)

            # Build system-name prefixes for interpreter (robust across connections)
            turnoutPrefix = "LT"
            sensorPrefix = "LS"
            reporterPrefix = "LR"
            try:
                memoForPrefixes = jmri.InstanceManager.getDefault(jmri.jmrix.loconet.LocoNetSystemConnectionMemo)
                if memoForPrefixes is not None and hasattr(memoForPrefixes, "getSystemPrefix"):
                    sp = memoForPrefixes.getSystemPrefix()
                    if sp:
                        turnoutPrefix = str(sp) + "T"
                        sensorPrefix = str(sp) + "S"
                        reporterPrefix = str(sp) + "R"
            except Exception:
                pass

            # Decode human-readable text; extract facing direction
            direction = "Unknown"
            try:
                interpClass = jmri.jmrix.loconet.messageinterp.LocoNetMessageInterpret
                text = interpClass.interpretMessage(msg, turnoutPrefix, sensorPrefix, reporterPrefix)
                t = str(text).lower()
                if (" facing west " in t) or (" facing west." in t):
                    direction = "West"
                elif (" facing east " in t) or (" facing east." in t):
                    direction = "East"
                elif (" facing north " in t) or (" facing north." in t):
                    direction = "North"
                elif (" facing south " in t) or (" facing south." in t):
                    direction = "South"
                # Add any other strings if needed (e.g., "northbound", "southbound")
                if DEBUG:
                    debug("Interpret: " + str(text).strip())
            except Exception as e:
                try:
                    print("Warning: LocoNetMessageInterpret failed: {0}".format(e))
                except Exception:
                    pass

            # Resolve roster entries for this DCC address (cluster for duplicates)
            roster = jmri.jmrit.roster.Roster.getDefault()
            if roster is None:
                debug("Roster.getDefault() returned None; skipping update.")
                return

            entries = []
            try:
                matches = roster.getEntriesByDccAddress(dccAddressStr)
                try:
                    entries = list(matches.toArray())
                except Exception:
                    try:
                        entries = list(matches)
                    except Exception:
                        entries = []
            except Exception:
                entries = []

            if not entries:
                debug("No roster entries found for DCC address {0}".format(dccAddressStr))
                return

            # Collect display-case roster IDs for the address cluster
            clusterIds = []
            for re in entries:
                try:
                    clusterIds.append(str(re.getId()))
                except Exception:
                    pass

            # Update lastReportedDirection for each roster ID in the cluster
            for rid in clusterIds:
                try:
                    lastReportedDirection[rid] = direction
                    if DEBUG:
                        debug("Updated {0} -> {1}".format(rid, direction))
                except Exception:
                    pass

            # Orientation update logic for usable directions only
            dirUsable = (str(direction).strip() != "" and str(direction).strip().lower() != "unknown")
            if dirUsable and (OR is not None) and (NDR is not None):
                try:
                    for rid in clusterIds:
                        # Query normal direction (case-insensitive inside NDR)
                        normalVal = None
                        try:
                            normalVal = NDR.GetNormalDirection(rid, None)
                        except Exception:
                            normalVal = None

                        if normalVal is None:
                            # Not configured in normal register: take no action
                            continue

                        # Compare case-insensitively
                        norm = str(normalVal).strip().lower()
                        rep = str(direction).strip().lower()

                        try:
                            if rep == norm:
                                # Facing normal -> ensure NOT present in OrientationRegister
                                try:
                                    if OR.IsContained(rid):
                                        OR.RemoveTrain(rid)
                                except Exception:
                                    pass
                            else:
                                # Facing inverted -> ensure present in OrientationRegister
                                try:
                                    if not OR.IsContained(rid):
                                        OR.AddTrain(rid)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    # Persist orientation changes once per message
                    try:
                        OR.save()
                    except Exception:
                        pass
                except Exception as ex:
                    debug("Orientation update failed: {0}".format(ex))

        except Exception as e:
            try:
                print("Error in LastDirectionListener.message: {0}".format(e))
            except Exception:
                pass

# Register shutdown hook
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

# Initialize
load()
_register_shutdown()

# Attach listener via LocoNetSystemConnectionMemo (correct API since 4.11.6) (but only if we are in a LocoNet system)
try:
    memo = jmri.InstanceManager.getDefault(jmri.jmrix.loconet.LocoNetSystemConnectionMemo)
    if memo is None:
        debug("No LocoNet memo found; listener not registered.")
    else:
        lnTraffic = memo.getLnTrafficController()
        if lnTraffic is None:
            debug("Memo found but no LnTrafficController; listener not registered.")
        else:
            lnTraffic.addLocoNetListener(LocoNetInterface.ALL, LastDirectionListener())
            debug("LastDirectionListener registered via memo.")
except Exception as e:
    debug("Orientation sensing not available: LocoNet not in use")
