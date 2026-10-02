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
from org.jdom2.input import SAXBuilder

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


def _RcSafe(value):
    # Text-safe conversion for values that can hold any character, notably XML
    # attribute values such as decoder family names with umlauts. Jython's str() on
    # such a Java string raises UnicodeEncodeError under the ASCII default encoding,
    # so unicode space is used throughout and nothing here can raise.
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    try:
        return unicode(value)
    except Exception:
        pass
    try:
        return unicode(str(value), "utf-8", "replace")
    except Exception:
        return u"?"


def RCLog(msg):
    try:
        print(u"[TAS] " + _RcSafe(msg))
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
        RCLog("Could not read train detection configuration: " + _RcSafe(ex))
    return result


def SaveConfig(config):
    path = RCConfigPath()
    parent = os.path.dirname(path)
    try:
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
    except Exception as ex:
        RCLog("Could not create train detection configuration folder: " + _RcSafe(ex))
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
        RCLog("Could not write train detection configuration: " + _RcSafe(ex))
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


def _RcReadXml(path):
    # Reads one XML file with a plain non-validating parser: no DTD, no schema, no
    # network, no XInclude processing. Includes are resolved by hand in
    # _RcCollectVariables, because that keeps every file read working the same way
    # whether JMRI validates or not.
    builder = SAXBuilder(False)
    try:
        builder.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", False)
    except Exception:
        pass
    document = builder.build(_JavaFile(_RcSafe(path)))
    if document is None:
        return None
    return document.getRootElement()


def _RcHrefPath(href):
    # Maps a decoder definition include reference to a local file. The references read
    # http://jmri.org/xml/decoders/..., which is the shipped xml folder.
    try:
        text = str(href or "")
    except Exception:
        return None
    marker = "xml/decoders/"
    found = text.find(marker)
    if found < 0:
        return None
    relative = text[found + len(marker):].replace("/", os.path.sep)
    return os.path.join(_RcXmlDir(), "decoders", relative)


def _RcCollectVariables(node, depth, visiting, found):
    # Gathers every variable element under a decoder element, following one include at
    # a time through local files. Included files whose root is <variables> contribute
    # their <variable> children directly.
    if node is None or depth > 24:
        return
    try:
        tag = str(node.getName() or "")
    except Exception:
        return
    if tag == "variable":
        found.append(node)
        return
    try:
        children = list(node.getChildren())
    except Exception:
        return
    for child in children:
        try:
            name = str(child.getName() or "")
        except Exception:
            continue
        if name == "variable":
            found.append(child)
        elif name == "variables":
            _RcCollectVariables(child, depth + 1, visiting, found)
        elif name == "include":
            try:
                uri = str(child.getNamespaceURI() or "")
            except Exception:
                uri = ""
            if uri.find("XInclude") < 0:
                continue
            try:
                href = str(child.getAttributeValue("href") or "")
            except Exception:
                continue
            path = _RcHrefPath(href)
            if path is None or path in visiting or not os.path.isfile(path):
                continue
            visiting.add(path)
            try:
                included = _RcReadXml(path)
            except Exception:
                included = None
            if included is not None:
                _RcCollectVariables(included, depth + 1, visiting, found)
            visiting.discard(path)
        else:
            _RcCollectVariables(child, depth + 1, visiting, found)


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
            RCLog("RailCom: decoder index not found at " + _RcSafe(path))
            _DecoderIndexCache["families"] = None
            return None
        element = _RcReadXml(path)
        index = element.getChild("decoderIndex") if element is not None else None
        if index is not None:
            families = index.getChild("familyList")
        if families is None:
            RCLog("RailCom: decoder index has no familyList")
    except Exception as ex:
        RCLog("RailCom: could not read the decoder index: " + _RcSafe(ex))
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
            if _RcSafe(fam.getAttributeValue("name")) != _RcSafe(family):
                continue
            if fallback is None:
                fallback = _RcSafe(fam.getAttributeValue("file"))
            for mod in fam.getChildren("model"):
                if _RcSafe(mod.getAttributeValue("model")) == _RcSafe(model):
                    return _RcSafe(fam.getAttributeValue("file"))
    except Exception as ex:
        RCLog("RailCom: could not search the decoder index: " + _RcSafe(ex))
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
    key = (_RcSafe(family), _RcSafe(model))
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
            RCLog("RailCom: decoder definition file not found: " + _RcSafe(path))
            _DecoderFileCache[key] = result
            return result
        element = _RcReadXml(path)
    except Exception as ex:
        RCLog("RailCom: could not read the decoder definition " + fileName + ": " + _RcSafe(ex))
        _DecoderFileCache[key] = result
        return result
    try:
        decoder = element.getChild("decoder") if element is not None else None
        if decoder is not None:
            _RcCollectVariables(decoder, 0, set([path]), result)
    except Exception as ex:
        RCLog("RailCom: could not read variables from " + fileName + ": " + _RcSafe(ex))
    if len(result) == 0:
        RCLog("RailCom: no variables read from " + fileName)
    _DecoderFileCache[key] = result
    return result


def _RcRailComSwitch(variables):
    # Finds the RailCom on/off switch among the decoder definition's variables and
    # returns (itemName, defaultValue) or None when the decoder has no such switch.
    for var in variables:
        try:
            item = _RcSafe(var.getAttributeValue("item"))
            cv = _RcSafe(var.getAttributeValue("CV"))
            mask = _RcSafe(var.getAttributeValue("mask"))
        except Exception:
            continue
        if item.lower().find("railcom") < 0:
            continue
        if cv != RC_CV or mask != RC_MASK:
            continue
        try:
            defaultValue = int(_RcSafe(var.getAttributeValue("default") or "0").strip())
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
        path = _RcSafe(entry.getPathName())
    except Exception:
        path = None
    if not path:
        return values
    try:
        if not os.path.isfile(path):
            return values
        element = _RcReadXml(path)
    except Exception as ex:
        RCLog("Could not read roster entry file " + _RcSafe(path) + ": " + _RcSafe(ex))
        return values
    try:
        if element is None:
            return values
        loco = element.getChild("locomotive")
        if loco is None:
            loco = element
        # The stored values sit in values/decoderDef/varValue in the roster file.
        container = loco.getChild("values")
        if container is None:
            container = loco
        inner = container.getChild("decoderDef")
        if inner is not None:
            container = inner
        for varValue in container.getChildren("varValue"):
            try:
                item = _RcSafe(varValue.getAttributeValue("item"))
                value = _RcSafe(varValue.getAttributeValue("value"))
            except Exception:
                continue
            if item != u"":
                values[item] = value
    except Exception:
        pass
    return values


def _RcStoredIsOn(values, item, defaultValue):
    # True when the entry's stored value for the RailCom switch reads as on. The stored
    # value is the variable's own value (an enum index for an on/off switch, where the
    # standard disabled/enabled list reads Disabled as 0 and Enabled as 1), not a CV
    # byte, so a plain zero test is used rather than a bit test. An entry with no stored
    # value falls back to the decoder definition default.
    if item in values:
        raw = _RcSafe(values[item]).strip()
        try:
            return int(raw) != 0
        except Exception:
            s = raw.lower()
            return s in ("1", "true", "yes", "on", "enabled")
    try:
        return int(_RcSafe(defaultValue).strip()) != 0
    except Exception:
        return False


def _RcPlaceBits(byteValue, mask, value):
    # Places an integer variable value into the V positions of an 8 character mask,
    # rightmost V taking the value's lowest bit. Returns the updated byte value.
    try:
        remaining = int(value)
    except Exception:
        return int(byteValue)
    result = int(byteValue)
    position = 0
    for bit in range(len(mask)):
        if mask[len(mask) - 1 - bit] == "V":
            if ((remaining >> position) & 1) != 0:
                result = result | (1 << bit)
            else:
                result = result & (~(1 << bit) & 0xFF)
            position += 1
    return result & 0xFF


def _RcSwitchOnValue(switchVar):
    # The numeric value that switches RailCom on for one switch variable. The switch is
    # an on/off list, so this counts its enumChoice entries (resolving one include level
    # for the shared disabled/enabled list) and takes the position of the first entry
    # whose name reads as enabled, defaulting to 1.
    choices = []
    try:
        for choice in switchVar.getChildren("enumChoice"):
            try:
                choices.append(_RcSafe(choice.getAttributeValue("choice")))
            except Exception:
                continue
        if len(choices) == 0:
            for child in list(switchVar):
                try:
                    tag = _RcSafe(child.getName())
                    uri = _RcSafe(child.getNamespaceURI())
                except Exception:
                    continue
                if tag != u"include" or uri.find(u"XInclude") < 0:
                    continue
                try:
                    href = _RcSafe(child.getAttributeValue("href"))
                except Exception:
                    continue
                path = _RcHrefPath(href)
                if path is None or not os.path.isfile(path):
                    continue
                try:
                    root = _RcReadXml(path)
                except Exception:
                    continue
                if root is None:
                    continue
                for choice in root.getChildren("enumChoice"):
                    try:
                        choices.append(_RcSafe(choice.getAttributeValue("choice")))
                    except Exception:
                        continue
    except Exception:
        pass
    for index in range(len(choices)):
        if choices[index].lower().find("enabl") >= 0:
            return index
    return 1


def _RcCv29WriteValue(variables, values, switchItem, onValue):
    # Builds the full CV 29 byte to write: every CV 29 variable contributes its stored
    # entry value, else its definition default, placed through its mask, with the RailCom
    # switch forced to its on value. Starting from zero means an unknown bit reads as
    # the variable default, never as the present decoder value, because POM cannot read.
    byteValue = 0
    for var in variables:
        try:
            cv = _RcSafe(var.getAttributeValue("CV"))
            mask = _RcSafe(var.getAttributeValue("mask"))
            item = _RcSafe(var.getAttributeValue("item"))
        except Exception:
            continue
        if cv != RC_CV or len(mask) == 0:
            continue
        if item == switchItem:
            contributed = onValue
        elif item in values:
            try:
                contributed = int(_RcSafe(values[item]).strip())
            except Exception:
                continue
        else:
            try:
                contributed = int(_RcSafe(var.getAttributeValue("default") or "0").strip())
            except Exception:
                continue
        byteValue = _RcPlaceBits(byteValue, mask, contributed)
    return byteValue & 0xFF


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
        return _RcSafe(self.rosterId) + u"  [" + _RcSafe(self.address) + u"]"


def ScanRoster():
    # Builds one RcEntry per roster entry. Slow: reads each entry's stored variable
    # values, so call it off the Event Dispatch Thread.
    config = LoadConfig()
    entries = []
    try:
        roster = jmri.jmrit.roster.Roster.getDefault()
    except Exception as ex:
        RCLog("JMRI roster unavailable: " + _RcSafe(ex))
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
        RCLog("RailCom: could not list the roster entries: " + _RcSafe(ex))
        return entries
    RCLog("RailCom: scanning " + str(len(seq)) + " roster entry/entries")
    for entry in seq:
        try:
            rec = RcEntry()
            rec.rosterId = _RcSafe(entry.getId())
            try:
                rec.address = _RcSafe(entry.getDccAddress())
            except Exception:
                rec.address = u""
            try:
                rec.longAddress = bool(entry.isLongAddress())
            except Exception:
                rec.longAddress = False
            try:
                rec.decoderFamily = _RcSafe(entry.getDecoderFamily())
                rec.decoderModel = _RcSafe(entry.getDecoderModel())
            except Exception:
                rec.decoderFamily = u""
                rec.decoderModel = u""
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
            RCLog("RailCom: skipped a roster entry: " + _RcSafe(ex))
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
        RCLog("Programmer manager lookup failed: " + _RcSafe(ex))
        return None
    if mgr is None:
        return None
    try:
        if not mgr.isAddressedModePossible():
            return None
    except Exception as ex:
        RCLog("Could not read the addressed mode capability: " + _RcSafe(ex))
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
        RCLog("RailCom: could not obtain a programming on main programmer: " + _RcSafe(ex))
    if prog is None:
        RCLog("RailCom: programming on main returned no programmer")
        return False
    try:
        mode = prog.getMode()
        try:
            modeName = str(mode.getStandardName() or "")
        except Exception:
            modeName = ""
        # An addressed programmer is a programming on main programmer. Its mode is an
        # operations mode such as OPSBYTEMODE, never the service mode DIRECTMODE.
        if not modeName.startswith("OPS"):
            RCLog("RailCom: programming on main is in mode " + _RcSafe(mode) +
                  " rather than an operations mode")
            return False
        if not prog.getCanWrite():
            RCLog("RailCom: programming on main cannot write")
            return False
    except Exception as ex:
        RCLog("RailCom: could not read the programming on main programmer: " + _RcSafe(ex))
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
                RCLog("RailCom enable callback failed: " + _RcSafe(ex))
        if self.done is not None:
            try:
                self.done()
            except Exception:
                pass


def EnableRailCom(rec, mgr, callback=None):
    # Switches RailCom on for one roster entry over programming on main. The full CV 29
    # byte is rebuilt from the entry's stored variable values, else the definition
    # defaults, with the RailCom switch forced to its on value: POM cannot read, so the
    # present decoder value cannot be preserved, and a bare switch bit would clear the
    # direction and speed step bits.
    if rec is None or mgr is None:
        return False
    try:
        address = int(_RcSafe(rec.address).strip())
    except Exception:
        RCLog("No DCC address for " + _RcSafe(rec.rosterId) + "; RailCom not enabled")
        return False
    variables = _RcDecoderVariables(rec.decoderFamily, rec.decoderModel)
    switchVar = None
    for var in variables:
        try:
            if _RcSafe(var.getAttributeValue("item")) == _RcSafe(rec.enableItem):
                switchVar = var
                break
        except Exception:
            continue
    if switchVar is None:
        RCLog("RailCom: no RailCom switch in the decoder definition for " + _RcSafe(rec.rosterId))
        return False
    values = {}
    try:
        roster = jmri.jmrit.roster.Roster.getDefault()
        found = roster.getEntryForId(_RcSafe(rec.rosterId)) if roster is not None else None
        if found is not None:
            values = _RcEntryVarValues(found)
    except Exception as ex:
        RCLog("RailCom: could not re-read " + _RcSafe(rec.rosterId) + ": " + _RcSafe(ex))
    value = _RcCv29WriteValue(variables, values, _RcSafe(rec.enableItem),
                              _RcSwitchOnValue(switchVar))
    RCLog("RailCom: writing CV" + RC_CV + "=" + _RcSafe(value) + " to " + _RcSafe(rec.rosterId) +
          " (address " + _RcSafe(address) + ")")
    try:
        prog = mgr.getAddressedProgrammer(bool(rec.longAddress), address)
    except Exception as ex:
        RCLog("Could not get a programmer for " + _RcSafe(rec.rosterId) + ": " + _RcSafe(ex))
        return False
    if prog is None:
        RCLog("No programmer available for " + _RcSafe(rec.rosterId))
        return False
    try:
        prog.writeCV(RC_CV, value, _RcPomListener(rec, callback, None))
    except Exception as ex:
        RCLog("Could not write CV" + RC_CV + " to " + _RcSafe(rec.rosterId) + ": " + _RcSafe(ex))
        return False
    return True
