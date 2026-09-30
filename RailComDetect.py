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
# RailComDetect.py
# Train detection support for the Timetable Automation System. Imported module, not a
# start-up script, so its names have their own namespace.
#
# This module decides, for each roster entry, whether its decoder supports RailCom and
# whether RailCom is switched on in that entry. Nothing is listed by name. The decision
# is taken from the JMRI decoder definition for the entry's decoder family and model,
# so a decoder that TAS has never seen is handled the same way as a known one.
#
# Research result behind the rule, over all 2112 decoder definitions shipped with JMRI:
# every decoder definition that offers RailCom offers an on/off RailCom switch on CV 29
# at bit 3, mask XXXXVXXX. That is true for all 13 brands found (Doehler und Haass,
# Electronic Solutions Ulm, Hornby, Kuehn, Lenz, MD Electronics, MTB Model, PIKO, Tams,
# Tehnologistic, Uhlenbrock, Wekomm, Zimo). CV 29 bit 3 is also the bit the NMRA
# specification gives to RailCom. Other CVs carry RailCom channel selection (CV 28),
# quality of service (CV 10), and vendor extras (CV 13, CV 144, CV 158, and Uhlenbrock
# cut-out CVs). Those select behaviour but do not switch RailCom on, so they are not
# used to decide capability. CV 12 and CV 127 carry "CTC/Railcommand Power
# Conversion", which matches a RailCom name search but is RailCom unrelated, so the CV
# number is checked as well as the name.
#
# Reading is from the roster entry's own stored variable values, so "on" means the value
# JMRI holds for that entry, not the decoder definition default.
# JMRI 5.16 / Jython 2.7. ASCII only. Thread-safe; Swing access on the EDT.

import os
import jmri
from java.io import File as _JavaFile

# The CV and bit that switch RailCom on and off, per the NMRA specification and every
# JMRI decoder definition that offers RailCom.
RC_CV = "29"
RC_MASK = "XXXXVXXX"
RC_BIT = 3

# Roster entries marked as not RailCom capable by the user, and per-entry RailCom
# initialisation fix settings. Both live in the configuration file below.
RC_CONFIG_PROFILE_PATH = "profile:jython/config/railcomfix.tsv"
RC_CONFIG_COLUMNS = ["roster_id", "not_capable", "fix", "function"]

RC_FUNCTION_DEFAULT = 4
RC_FUNCTION_MIN = 0
RC_FUNCTION_MAX = 28


def RCLog(msg):
    try:
        print("[TAS] " + str(msg))
    except Exception:
        pass


# ------------------------------------------------------------------ configuration

def RCConfigPath():
    try:
        return jmri.util.FileUtil.getExternalFilename(RC_CONFIG_PROFILE_PATH)
    except Exception:
        return os.path.join("jython", "config", "railcomfix.tsv")


def LoadConfig():
    # Returns dict keyed by lower-cased roster ID:
    #   notCapable: "1" when the user marked the entry as not RailCom capable
    #   fix: "1" when the RailCom initialisation fix applies to the entry
    #   function: function number used for that entry
    result = {}
    path = RCConfigPath()
    try:
        if not os.path.isfile(path):
            return result
        import csv
        fh = open(path, "r")
        try:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    rid = str(row.get("roster_id", "")).strip()
                except Exception:
                    continue
                if rid == "":
                    continue
                key = rid.lower()
                result[key] = {
                    "rosterId": rid,
                    "notCapable": _RcFlag(row.get("not_capable")),
                    "fix": _RcFlag(row.get("fix")),
                    "function": _RcFunction(row.get("function"), RC_FUNCTION_DEFAULT),
                }
        finally:
            fh.close()
    except Exception as ex:
        RCLog("Could not read train detection configuration: " + str(ex))
    return result


def SaveConfig(config):
    path = RCConfigPath()
    parent = os.path.dirname(path)
    try:
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
    except Exception as ex:
        RCLog("Could not create train detection configuration folder: " + str(ex))
        return False
    tempPath = path + ".tmp"
    try:
        import csv
        fh = open(tempPath, "w")
        try:
            writer = csv.DictWriter(fh, fieldnames=RC_CONFIG_COLUMNS, delimiter="\t",
                                    lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for key in sorted(config.keys()):
                rec = config[key]
                writer.writerow({
                    "roster_id": str(rec.get("rosterId", key)),
                    "not_capable": "1" if rec.get("notCapable") else "0",
                    "fix": "1" if rec.get("fix") else "0",
                    "function": str(_RcFunction(rec.get("function"), RC_FUNCTION_DEFAULT)),
                })
        finally:
            fh.close()
        if os.path.isfile(path):
            os.remove(path)
        os.rename(tempPath, path)
    except Exception as ex:
        RCLog("Could not write train detection configuration: " + str(ex))
        return False
    return True


def _RcFlag(value):
    try:
        s = str(value).strip().lower()
    except Exception:
        return False
    return s in ("1", "true", "yes", "on")


def _RcFunction(value, default):
    try:
        n = int(str(value).strip())
    except Exception:
        return default
    if n < RC_FUNCTION_MIN or n > RC_FUNCTION_MAX:
        return default
    return n


# ------------------------------------------------------- decoder definition reading

_DecoderFileCache = {}
_DecoderIndexCache = {"loaded": False, "families": None}


def _RcXmlDir():
    # The JMRI xml folder, which holds decoderIndex.xml and the decoders folder.
    return os.path.join(str(jmri.jmrit.XmlFile.xmlDir()), "")


def _RcFamilyList():
    # The family list from decoderIndex.xml, read once. JMRI's own DecoderIndexFile is
    # not used here: this reads the same shipped index directly, so no dependence on
    # InstanceManager initialisation order or on which matchingDecoderList overload is
    # called. Each family element carries name, mfg and file; its model children carry
    # the model names.
    if _DecoderIndexCache["loaded"]:
        return _DecoderIndexCache["families"]
    _DecoderIndexCache["loaded"] = True
    families = None
    try:
        path = os.path.join(_RcXmlDir(), "decoderIndex.xml")
        if not os.path.isfile(path):
            RCLog("RailCom: decoder index not found at " + str(path))
            _DecoderIndexCache["families"] = None
            return None
        element = jmri.jmrit.XmlFile().rootFromFile(_JavaFile(path))
        index = element.getChild("decoderIndex")
        if index is not None:
            families = index.getChild("familyList")
        if families is None:
            RCLog("RailCom: decoder index has no familyList")
    except Exception as ex:
        RCLog("RailCom: could not read the decoder index: " + str(ex))
        families = None
    _DecoderIndexCache["families"] = families
    return families


def _RcDecoderFileName(family, model):
    # The decoder definition file name for a decoder family and model, or None.
    families = _RcFamilyList()
    if families is None:
        return None
    fallback = None
    try:
        for fam in families.getChildren("family"):
            if str(fam.getAttributeValue("name") or "") != str(family):
                continue
            if fallback is None:
                fallback = str(fam.getAttributeValue("file") or "")
            for mod in fam.getChildren("model"):
                if str(mod.getAttributeValue("model") or "") == str(model):
                    return str(fam.getAttributeValue("file") or "")
    except Exception as ex:
        RCLog("RailCom: could not search the decoder index: " + str(ex))
        return None
    # Some roster entries record the family name as the model.
    if fallback:
        return fallback
    return None


def _RcDecoderVariables(family, model):
    # The variable elements of the decoder definition for a family and model, with
    # XInclude resolved. Cached per family and model, because the roster commonly holds
    # many entries of one decoder.
    #
    # DecoderFile holds the <model> element rather than the whole <decoder> element and
    # exposes no accessor for a definition file's variables, so the file is read here.
    # jmri.jmrit.XmlFile uses JMRI's SAXBuilder, which has XInclude enabled and resolves
    # the http://jmri.org/xml/decoders/... includes locally, so includes need no handling.
    key = (str(family), str(model))
    if key in _DecoderFileCache:
        return _DecoderFileCache[key]
    result = []
    fileName = _RcDecoderFileName(family, model)
    if not fileName:
        RCLog("RailCom: no decoder definition matches family '" + str(family) +
              "' with model '" + str(model) + "'")
        _DecoderFileCache[key] = result
        return result
    path = os.path.join(_RcXmlDir(), "decoders", fileName)
    try:
        if not os.path.isfile(path):
            RCLog("RailCom: decoder definition file not found: " + str(path))
            _DecoderFileCache[key] = result
            return result
        element = jmri.jmrit.XmlFile().rootFromFile(_JavaFile(path))
    except Exception as ex:
        RCLog("RailCom: could not read the decoder definition " + fileName + ": " + str(ex))
        _DecoderFileCache[key] = result
        return result
    try:
        decoder = element.getChild("decoder")
        if decoder is not None:
            for variables in decoder.getChildren("variables"):
                for var in variables.getChildren("variable"):
                    result.append(var)
    except Exception as ex:
        RCLog("RailCom: could not read variables from " + fileName + ": " + str(ex))
    if len(result) == 0:
        RCLog("RailCom: no variables read from " + fileName)
    _DecoderFileCache[key] = result
    return result


def _RcRailComSwitch(variables):
    # Finds the RailCom on/off switch among the decoder definition's variables and
    # returns (itemName, defaultValue) or None when the decoder has no such switch.
    for var in variables:
        try:
            item = str(var.getAttributeValue("item") or "")
            cv = str(var.getAttributeValue("CV") or "")
            mask = str(var.getAttributeValue("mask") or "")
        except Exception:
            continue
        if item.lower().find("railcom") < 0:
            continue
        if cv != RC_CV or mask != RC_MASK:
            continue
        try:
            defaultValue = int(str(var.getAttributeValue("default") or "0").strip())
        except Exception:
            defaultValue = 0
        return (item, defaultValue)
    return None


# ------------------------------------------------------------- roster entry reading

def _RcEntryVarValues(entry):
    # Reads the variable values JMRI stores for one roster entry. The entry's own XML
    # file holds them as varValue elements.
    values = {}
    try:
        path = entry.getPathName()
    except Exception:
        path = None
    if not path:
        return values
    try:
        if not os.path.isfile(path):
            return values
        element = jmri.jmrit.XmlFile().rootFromFile(_JavaFile(str(path)))
    except Exception as ex:
        RCLog("Could not read roster entry file " + str(path) + ": " + str(ex))
        return values
    try:
        for varValue in element.getChildren("varValue"):
            try:
                item = str(varValue.getAttributeValue("item") or "")
                value = str(varValue.getAttributeValue("value") or "")
            except Exception:
                continue
            if item != "":
                values[item] = value
    except Exception:
        pass
    return values


def _RcStoredIsOn(values, item, defaultValue):
    # True when the entry's stored value for the RailCom switch reads as on. An entry
    # with no stored value falls back to the decoder definition default.
    if item in values:
        raw = str(values[item]).strip()
        try:
            return ((int(raw) >> RC_BIT) & 1) != 0
        except Exception:
            s = raw.lower()
            return s in ("1", "true", "yes", "on")
    return ((int(defaultValue) >> RC_BIT) & 1) != 0


# ------------------------------------------------------------------- public results

class RcEntry(object):
    # One roster entry's train detection record.
    def __init__(self):
        self.rosterId = ""
        self.address = ""
        self.longAddress = False
        self.decoderFamily = ""
        self.decoderModel = ""
        self.definitionKnown = False   # a decoder definition was found for this entry
        self.detectedCapable = False   # the definition offers a RailCom on/off switch
        self.storedOn = False         # the entry's stored value has that switch on
        self.notCapable = False       # the user marked the entry as not capable
        self.fix = False
        self.function = RC_FUNCTION_DEFAULT
        self.enableItem = ""          # item name of the RailCom switch, for the POM write
        self.enableDefault = 0

    def EffectiveCapable(self):
        if self.notCapable:
            return False
        return self.detectedCapable

    def FullyEnabled(self):
        return (self.EffectiveCapable() and self.storedOn and self.definitionKnown)

    def __str__(self):
        # Used by any Swing renderer that falls back to toString().
        return str(self.rosterId) + "  [" + str(self.address) + "]"


def ScanRoster():
    # Builds one RcEntry per roster entry. Slow: reads each entry's stored variable
    # values, so call it off the Event Dispatch Thread.
    config = LoadConfig()
    entries = []
    try:
        roster = jmri.jmrit.roster.Roster.getDefault()
    except Exception as ex:
        RCLog("JMRI roster unavailable: " + str(ex))
        return entries
    if roster is None:
        return entries
    try:
        allEntries = roster.getAllEntries()
        if allEntries is None:
            RCLog("RailCom: the roster returned no entry list")
            return entries
        seq = list(allEntries)
    except Exception as ex:
        RCLog("RailCom: could not list the roster entries: " + str(ex))
        return entries
    RCLog("RailCom: scanning " + str(len(seq)) + " roster entry/entries")
    for entry in seq:
        try:
            rec = RcEntry()
            rec.rosterId = str(entry.getId())
            try:
                rec.address = str(entry.getDccAddress() or "")
            except Exception:
                rec.address = ""
            try:
                rec.longAddress = bool(entry.isLongAddress())
            except Exception:
                rec.longAddress = False
            try:
                rec.decoderFamily = str(entry.getDecoderFamily() or "")
                rec.decoderModel = str(entry.getDecoderModel() or "")
            except Exception:
                rec.decoderFamily = ""
                rec.decoderModel = ""
            variables = _RcDecoderVariables(rec.decoderFamily, rec.decoderModel)
            switch = _RcRailComSwitch(variables)
            rec.definitionKnown = len(variables) > 0
            if switch is not None:
                rec.detectedCapable = True
                rec.enableItem = switch[0]
                rec.enableDefault = switch[1]
                values = _RcEntryVarValues(entry)
                rec.storedOn = _RcStoredIsOn(values, switch[0], switch[1])
            key = rec.rosterId.lower()
            saved = config.get(key)
            if saved is not None:
                rec.notCapable = bool(saved.get("notCapable"))
                rec.fix = bool(saved.get("fix"))
                rec.function = int(saved.get("function", RC_FUNCTION_DEFAULT))
            entries.append(rec)
        except Exception as ex:
            RCLog("RailCom: skipped a roster entry: " + str(ex))
    capable = [r for r in entries if r.detectedCapable]
    RCLog("RailCom: " + str(len(capable)) + " of " + str(len(entries)) +
          " roster entries have a decoder definition offering RailCom")
    return entries


def SplitEntries(entries):
    # Returns (capable, notCapable). An entry the user marked as not capable counts as
    # not capable.
    capable = []
    notCapable = []
    for rec in entries:
        if rec.EffectiveCapable():
            capable.append(rec)
        else:
            notCapable.append(rec)
    return (capable, notCapable)


def FixEntries(entries):
    # Roster entries the RailCom initialisation fix applies to: RailCom capable, fully
    # switched on, and ticked in the configuration file.
    return [rec for rec in entries if rec.fix and rec.FullyEnabled()]


# --------------------------------------------------------- programming on main (POM)

def PomManager():
    # Returns the AddressedProgrammerManager when the layout supports programming on
    # main, otherwise None. JMRI has no ProgrammerChecker. AddressedProgrammerManager
    # is the POM interface, and isAddressedModePossible is what each system reports:
    # LnProgrammerManager returns true, the default returns false.
    try:
        mgr = jmri.InstanceManager.getNullableDefault(jmri.AddressedProgrammerManager)
    except Exception as ex:
        RCLog("Programmer manager lookup failed: " + str(ex))
        return None
    if mgr is None:
        return None
    try:
        if not mgr.isAddressedModePossible():
            return None
    except Exception as ex:
        RCLog("Could not read the addressed mode capability: " + str(ex))
        return None
    return mgr


def PomAvailable():
    # True when this layout can program on main. Tested by asking the
    # AddressedProgrammerManager for a real addressed programmer and checking that it
    # writes in direct mode, because that is exactly what enabling RailCom needs.
    mgr = PomManager()
    if mgr is None:
        RCLog("RailCom: no programming on main is available on this layout")
        return False
    prog = None
    try:
        prog = mgr.getAddressedProgrammer(False, 0)
    except Exception as ex:
        RCLog("RailCom: could not obtain a programming on main programmer: " + str(ex))
    if prog is None:
        RCLog("RailCom: programming on main returned no programmer")
        return False
    try:
        if prog.getMode() != jmri.ProgrammingMode.DIRECTMODE:
            RCLog("RailCom: programming on main is in mode " + str(prog.getMode()) +
                  " rather than direct mode")
            return False
        if not prog.getCanWrite():
            RCLog("RailCom: programming on main cannot write")
            return False
    except Exception as ex:
        RCLog("RailCom: could not read the programming on main programmer: " + str(ex))
        return False
    RCLog("RailCom: programming on main is available")
    return True


class _RcPomListener(jmri.ProgListener):
    def __init__(self, record, callback, done):
        self.record = record
        self.callback = callback
        self.done = done

    def programmingOpReply(self, cv, value):
        ok = (value == jmri.ProgListener.OK)
        if self.callback is not None:
            try:
                self.callback(self.record, ok)
            except Exception as ex:
                RCLog("RailCom enable callback failed: " + str(ex))
        if self.done is not None:
            try:
                self.done()
            except Exception:
                pass


def EnableRailCom(rec, mgr, callback=None):
    # Writes the RailCom switch on for one roster entry over programming on main. The
    # value written is the decoder definition's default for that switch with the RailCom
    # bit set, because POM cannot read the present value.
    if rec is None or mgr is None:
        return False
    try:
        address = int(str(rec.address).strip())
    except Exception:
        RCLog("No DCC address for " + str(rec.rosterId) + "; RailCom not enabled")
        return False
    value = (int(rec.enableDefault) | (1 << RC_BIT)) & 0xFF
    try:
        prog = mgr.getAddressedProgrammer(bool(rec.longAddress), address)
    except Exception as ex:
        RCLog("Could not get a programmer for " + str(rec.rosterId) + ": " + str(ex))
        return False
    if prog is None:
        RCLog("No programmer available for " + str(rec.rosterId))
        return False
    try:
        prog.writeCV(RC_CV, value, _RcPomListener(rec, callback, None))
    except Exception as ex:
        RCLog("Could not write CV" + RC_CV + " to " + str(rec.rosterId) + ": " + str(ex))
        return False
    return True
