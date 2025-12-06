# -*- coding: utf-8 -*-
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
# Tabs: General, Display configuration, Day/night cycle.
# ASCII-only, portable paths, thread-safe.

import os, csv, re
import java
import traceback
from java.awt import (BorderLayout, Color, Dimension, Font,
    GridBagConstraints, GridBagLayout, Insets, RenderingHints)
from java.awt.image import BufferedImage
from java.io import File  # canonical path comparisons
from java.lang import Runnable
from java.awt.event import FocusAdapter, MouseAdapter, MouseEvent
from javax.swing import (Box, JButton, JCheckBox, JFileChooser, JLabel, JDialog,
    JList, JOptionPane, JPanel, JScrollPane, JTabbedPane, JTextField,
    ListSelectionModel, SwingUtilities, UIManager, DefaultListModel,
    DefaultListCellRenderer, BorderFactory, JComboBox, JRadioButton, ButtonGroup)
from javax.swing.filechooser import FileNameExtensionFilter
from javax.swing import JTextPane
from javax.swing.event import DocumentListener, ListSelectionListener
from javax.swing.text import StyleContext, StyledDocument, SimpleAttributeSet, StyleConstants
from java.awt.event import KeyAdapter, KeyEvent
from java.awt import GridLayout

# JMRI
import jmri
from jmri.util import FileUtil  # portable profile/scripts paths

from java.awt import GraphicsEnvironment
from javax.swing import JColorChooser

# ------------------------------- Logging -------------------------------
TAG = "[TASSetup] "
def LogInfo(msg, alsoDialog=False, title="Info"):
    try: print(TAG + str(msg))
    except: pass
    if alsoDialog:
        try: JOptionPane.showMessageDialog(None, str(msg), title, JOptionPane.INFORMATION_MESSAGE)
        except: pass
def LogWarn(msg, alsoDialog=False, title="Warning"):
    try: print(TAG + "WARN: " + str(msg))
    except: pass
    if alsoDialog:
        try: JOptionPane.showMessageDialog(None, str(msg), title, JOptionPane.WARNING_MESSAGE)
        except: pass
def LogError(msg, ex=None, alsoDialog=True, title="Error"):
    try:
        print(TAG + "ERROR: " + str(msg))
        if ex is not None:
            print(TAG + "TRACEBACK:")
            traceback.print_exc()
    except: pass
    if alsoDialog:
        try: JOptionPane.showMessageDialog(None, str(msg), title, JOptionPane.ERROR_MESSAGE)
        except: pass
        
# -------------------- Colour helpers --------------------
def _RgbStrToColorOrDefault(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) != 3: return defaultColor
        r,g,b = [max(0, min(255, int(float(x)))) for x in parts]
        return Color(r, g, b)
    except:
        return defaultColor

def _ColorToRgbStr(c):
    try:
        return "%d,%d,%d" % (c.getRed(), c.getGreen(), c.getBlue())
    except:
        return GetDefaultBackgroundRGB()

# --------------------------- Memory helpers ---------------------------
def ProvideMemory(Name):
    # Provide existing Memory by system or user name;
    # create if missing (JMRI-provided ensure).
    mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
    if mm is None:
        raise Exception("MemoryManager not available")
    mem = None
    try:
        mem = mm.getBySystemName(Name)
    except:
        mem = None
    if mem is None:
        try:
            mem = mm.getByUserName(Name)
        except:
            mem = None
    if mem is None:
        mem = mm.provideMemory(Name)
    return mem

def GetMemoryString(Name, Default=""):
    """
    Return the memory value as-is.
    Apply Default ONLY when the memory did not exist and was just created
    (and has no value). Existing blank/whitespace values are respected.
    """
    try:
        mm = jmri.InstanceManager.getDefault(jmri.MemoryManager)
        if mm is None:
            return Default  # conservative fallback

        # Try to find an existing memory without creating one
        mem = None
        try:
            mem = mm.getBySystemName(Name)
        except:
            mem = None
        if mem is None:
            try:
                mem = mm.getByUserName(Name)
            except:
                mem = None

        if mem is None:
            # First creation: provide and seed with Default once
            mem = mm.provideMemory(Name)
            try:
                if mem.getValue() is None:
                    mem.setValue(Default)
            except:
                return Default
            return Default

        # Existing memory: respect whatever value it holds (even blank/whitespace)
        try:
            v = mem.getValue()
        except:
            v = None
        if v is None:
            # existing memory but unset -> treat as blank (do not force Default)
            return ""
        return str(v)
    except Exception:
        return Default

def SetMemoryString(Name, Value):
    """
    Set memory to the given string value verbatim (no stripping),
    so the UI may deliberately store " " to render blank headers.
    """
    try:
        m = ProvideMemory(Name)
        m.setValue(str(Value))
        print(TAG + "Set " + Name + " = " + str(Value))
    except Exception as ex:
        LogError("Failed to set memory " + Name + ": " + str(ex), ex=ex, alsoDialog=False)

def GetMemoryBool(Name, Default=False):
    s=GetMemoryString(Name,"")
    if isinstance(s,bool): return s
    t=str(s).strip().lower()
    if t in ["1","true","yes","y","on","enabled"]: return True
    if t in ["0","false","no","n","off","disabled"]: return False
    return Default

def SetMemoryBool(Name, Value):
    SetMemoryString(Name, "true" if bool(Value) else "false")
    
def ScriptExists(scriptName):
    try:
        path = ProfileJythonFilePath(scriptName)
        return os.path.isfile(path)
    except:
        return False    

# ------------------------------- Theme --------------------------------
THEME_FONT_FAMILY = GetMemoryString("IMTAS_FONT_FAMILY", "Gill Sans MT")
THEME_TEXT_COLOR = Color(30, 30, 30)
THEME_PAPER = _RgbStrToColorOrDefault(GetMemoryString("IMTASPAPERCOLOUR", "249,246,238"), Color(249, 246, 238))
THEME_ACCENT = Color(80, 80, 80)
LIST_SEL_BG = Color(210, 225, 235)
LIST_SEL_FG = Color(20, 20, 20)

def ApplyTheme(component):
    try: component.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
    except: pass

def MakePaperPanel():
    class PaperPanel(JPanel):
        def __init__(self):
            JPanel.__init__(self)
            self.setOpaque(True); self.setBackground(THEME_PAPER)
            self.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createMatteBorder(1,1,1,1, Color(180,170,150)),
                BorderFactory.createEmptyBorder(12,12,12,12)))
            self.texture = self._makeTexture()
        def _makeTexture(self):
            w,h=64,64
            img=BufferedImage(w,h,BufferedImage.TYPE_INT_ARGB); g=img.createGraphics()
            g.setColor(THEME_PAPER); g.fillRect(0,0,w,h)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g.setColor(Color(200,196,184,22))
            for i in range(150):
                x=int(java.lang.Math.random()*w); y=int(java.lang.Math.random()*h)
                g.fillRect(x,y,1,1)
            g.dispose(); return img
        def paintComponent(self,g):
            super(PaperPanel,self).paintComponent(g)
            iw=self.texture.getWidth(); ih=self.texture.getHeight()
            for y in range(0,self.getHeight(),ih):
                for x in range(0,self.getWidth(),iw):
                    g.drawImage(self.texture,x,y,None)
    p=PaperPanel(); ApplyTheme(p); return p

def MakeHeading(text):
    lbl=JLabel(text)
    lbl.setForeground(THEME_ACCENT)
    lbl.setFont(Font(THEME_FONT_FAMILY, Font.BOLD, 16))
    return lbl

def MakeWrappedLabel(htmlText, widthPx=560, lineHeight=1.25, bold=False):
    """
    Create a JLabel that wraps text using HTML with an explicit width and tuned line-height.
    - widthPx: wrapping width in pixels
    - lineHeight: CSS line-height multiplier for compact spacing (e.g., 1.20–1.30)
    - bold: True for heading-style weight/size; False for body copy style
    """
    # Build HTML with controlled width and line-height.
    # Keep ASCII-only content for Jython compatibility.
    html = "<html><div style='width:{0}px; line-height:{1};'>{2}</div></html>".format(
        int(widthPx), float(lineHeight), htmlText
    )
    lbl = JLabel(html)
    try:
        style = Font.BOLD if bold else Font.PLAIN
        size = 16 if bold else 13
        lbl.setFont(Font(THEME_FONT_FAMILY, style, size))
        lbl.setForeground(THEME_TEXT_COLOR if not bold else THEME_ACCENT)
    except:
        pass
    return lbl

# --- Force the chosen font on all controls (recursive) ---
from java.awt import Container
from javax.swing import JTable, JList, JScrollPane, JTabbedPane

def _SetFontIfPossible(comp, family, style=Font.PLAIN, size=13):
    try:
        comp.setFont(Font(family, style, size))
    except:
        pass

def _ApplyFontRecursive(comp, family):
    # Apply to this component
    _SetFontIfPossible(comp, family)

    # Special cases / nested internals
    try:
        # JTable header
        if isinstance(comp, JTable):
            hdr = comp.getTableHeader()
            if hdr is not None:
                _SetFontIfPossible(hdr, family, Font.BOLD, 13)
        # JList cell renderer might need a nudge
        if isinstance(comp, JList):
            rnd = comp.getCellRenderer()
            if rnd is not None:
                try: rnd.setFont(Font(family, Font.PLAIN, 13))
                except: pass
        # JScrollPane: also set viewport view
        if isinstance(comp, JScrollPane):
            vp = comp.getViewport()
            if vp is not None:
                view = vp.getView()
                if view is not None: _SetFontIfPossible(view, family)
        # JTabbedPane: set tab component fonts if present
        if isinstance(comp, JTabbedPane):
            try:
                count = comp.getTabCount()
                for i in range(count):
                    tab = comp.getTabComponentAt(i)
                    if tab is not None: _SetFontIfPossible(tab, family, Font.BOLD, 13)
            except:
                pass
    except:
        pass

    # Recurse into children if Container
    try:
        if isinstance(comp, Container):
            for child in comp.getComponents():
                _ApplyFontRecursive(child, family)
    except:
        pass

def ApplyTheme(component):
    # Preserve original semantics but use the recursive applier
    try:
        _ApplyFontRecursive(component, THEME_FONT_FAMILY)
    except:
        pass

# -------------------- TAS Interface Defaults (minimal) --------------------
def GetDefaultFontFamily():
    # Safe default (TimetableAutomation will still guard its own fallback)
    return "Gill Sans MT"

def GetDefaultBackgroundRGB():
    # CoverPanel default background (Color(240,238,220))
    return "240,238,220"

# ------------------------------- Keys ---------------------------------
IMCurrentTimetable   = "IMCURRENTTIMETABLE"
IMAllowDelays        = "IMALLOWDELAYS"
IMAllowCANCELLATIONS = "IMALLOWCANCELLATIONS"
IMPublicDisplayList  = "IMPUBLICDISPLAYLIST"
IMSignallerDisplayList = "IMSIGNALLERDISPLAYLIST"

# Timetable (WTTDisplay) parameter memories
IMWTT_PageMode        = "IMWTT_PAGE_MODE"           # str: "WEEKDAYS_SAT_SUN" / "SEVEN_DAYS" / "MONSAT_PLUS_SUN" / "ALL_WEEK"
IMWTT_Time24          = "IMWTT_TIME_24H"            # bool: true/false
IMWTT_TimeSeparator   = "IMWTT_TIME_SEPARATOR"      # str: single character (":" or " " or ".")
IMWTT_EcsLabel        = "IMWTT_ECS_LABEL"           # str: e.g., "ECS"
IMWTT_EcsMatch        = "IMWTT_ECS_DEST_MATCH"      # str: comma-separated tokens (lowercased)
IMWTT_DirectionSplit  = "IMWTT_DIRECTION_SPLIT"     # bool: true/false
IMWTT_OdHeaderVertical = "IMWTT_OD_HEADER_VERTICAL" # bool: true/false (unchecked=horizontal default)

# Day/Night & Weather (UI values consumed by DayNight/Weather scripts)
IMLowThrottleAddr = "IMLOWCTTHROTTLEADDR"
IMHighThrottleAddr = "IMHIGHCTTHROTTLEADDR"
IMDayNightPreset = "IMDAYNIGHT_PRESET"
IMWxClimate   = "IMWX_CLIMATE"
IMWxCloudPct  = "IMCLOUDCOVERPCT"
IMWxUiChoice  = "IMWX_UI"          # "App" or "Newspaper"
IMWxNewsStyle = "IMWX_NEWS_STYLE"  # "Old" or "Modern"

# DayNight time-warp blackout configuration (matches DayNight.py)
IMTimeWarpBlackoutSeconds = "IMTIMEWARPBLACKOUTSECONDS"
IMTimeWarpThresholdMinutes = "IMTIMEWARPTHRESHOLDMINUTES"

# NEW: Auto-working enable memory switch (non-startup, no restart)
IMTASAutoWorking = "IMTASAUTOWORKING"

# --------------------------- Portable paths ---------------------------
def GetTimetableDirFile():
    path = FileUtil.getExternalFilename("profile:timetable")
    return File(path)

def StripCsvExt(name):
    s=str(name).strip()
    return s[:-4] if s.lower().endswith(".csv") else s

def ProfileJythonFilePath(name):
    try:
        return FileUtil.getExternalFilename("profile:jython/" + name)
    except:
        return "jython/" + name

def _NormRN(s):
    # Case-insensitive matching for reporting numbers; blank -> ""
    try:
        return str(s).strip().upper()
    except Exception:
        return ""


# -------- Start-Up detection & mutation (authoritative, robust) -------
# APIs: StartupActionsManager.getActions(), .addAction(), .savePreferences(Profile)
# StartupModel.isEnabled()/setEnabled(...); PerformScriptModel.getFileName()/setFileName(...)
# Paths via jmri.util.FileUtil "profile:" scheme.

def _StartupMgr():
    try:
        return jmri.InstanceManager.getDefault(jmri.util.startup.StartupActionsManager)
    except:
        return None

def _ActiveProfile():
    try:
        pm = jmri.profile.ProfileManager.getDefault()
        return pm.getActiveProfile()
    except:
        return None

def _CanonLower(p):
    try:
        return File(p).getCanonicalPath().lower()
    except:
        return str(p).lower()

def _MatchScriptPath(model, scriptFileName):
    """True iff model's script path points to profile:jython/<scriptFileName>."""
    try:
        path = model.getFileName()
        if path is None: return False
        pcanon = _CanonLower(str(path))
        target = _CanonLower(ProfileJythonFilePath(scriptFileName))
        base = File(scriptFileName).getName().lower()
        if pcanon == target: return True
        if pcanon.endswith(File.separator + base): return True
        if pcanon.endswith("/" + base): return True
        if pcanon.endswith("\\\\" + base): return True
        return False
    except:
        return False

def _FindPerformScriptModelFor(scriptFileName):
    mgr = _StartupMgr()
    if mgr is None: return None
    try:
        actions = mgr.getActions()
    except:
        return None
    for m in actions:
        try:
            if not isinstance(m, jmri.util.startup.PerformScriptModel):
                continue
            if _MatchScriptPath(m, scriptFileName):
                return m
        except:
            continue
    return None

def _IsScriptEnabled(scriptFileName):
    m = _FindPerformScriptModelFor(scriptFileName)
    return (m is not None) and bool(m.isEnabled())

def _EnsureScriptEnabled(scriptFileName, enabled):
    """Create/toggle PerformScriptModel, then save to active profile."""
    mgr = _StartupMgr()
    if mgr is None:
        LogWarn("StartupActionsManager unavailable")
        return False
    model = _FindPerformScriptModelFor(scriptFileName)
    if model is None and enabled:
        try:
            model = jmri.util.startup.PerformScriptModel()
            model.setFileName(ProfileJythonFilePath(scriptFileName))
            model.setEnabled(True)
            mgr.addAction(model)
        except Exception as ex:
            LogError("Could not add startup script: " + scriptFileName + " :: " + str(ex), ex=ex)
            return False
    elif model is not None:
        try:
            model.setEnabled(bool(enabled))
        except Exception as ex:
            LogError("Could not change enabled state: " + scriptFileName + " :: " + str(ex), ex=ex)
            return False
    else:
        pass  # model missing and enabling False -> nothing to do

    try:
        prof = _ActiveProfile()
        if prof is not None:
            mgr.savePreferences(prof)
        return True
    except Exception as ex:
        LogError("Could not save Start-Up preferences: " + str(ex), ex=ex)
        return False

def IsDayNightEnabled():
    return _IsScriptEnabled("DayNight.py")

def IsWeatherEnabled():
    return _IsScriptEnabled("WeatherGenerator.py")

def IsTimeActionsEnabled():
    return _IsScriptEnabled("CheckWhenTimeChanges.py") and _IsScriptEnabled("DayTracker.py") and _IsScriptEnabled("TimeWarpChecker.py")

# ---------------------- Timetable validation helpers -------------------
def _MakeDefaultRN(rowNumber):
    # Default reporting number: header row is 1, first data row is 2 -> TAS<rowNumber>
    return "TAS" + str(int(rowNumber))

def _ParseTimeToMinutes(timeStr):
    """
    Parse 12h/24h times to minutes since midnight.
    Accepts: "13:15", "13:15:00", "1:15 PM", "01:15 pm", optional seconds, optional trailing 'h'.
    Returns int or None.
    """
    if timeStr is None: return None
    s = str(timeStr).strip()
    if not s: return None
    s = re.sub(r"\s+", " ", s)
    if s.lower().endswith('h'):
        s = s[:-1].strip()
    m = re.match(r'^\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?\s*$', s, flags=re.IGNORECASE)
    if not m: return None
    hour = int(m.group(1)); minute = int(m.group(2)); ampm = m.group(4).lower() if m.group(4) else None
    if minute >= 60 or hour > 24 or hour < 0 or minute < 0: return None
    if ampm:
        hour = hour % 12
        if ampm == 'pm': hour += 12
    else:
        if hour == 24: hour = 0
    return hour*60 + minute

def _TimetableFilePath():
    name = GetMemoryString(IMCurrentTimetable, "").strip()
    if not name: return None
    ttDir = FileUtil.getExternalFilename("profile:timetable")
    return os.path.join(ttDir, name + ".csv")

def _ValidateTimetable():
    """
    Returns (isValid, firstMessage, headerInfo)
    headerInfo: dict with keys:
    - hasTrigger, hasArr, hasDep, hasAnyDayColumn
    Row rule: a row is valid if it has at least one of Trigger/Arr/Dep filled; any filled time must parse.
    """
    path = _TimetableFilePath()
    if path is None:
        return (False, "No current timetable set.", None)
    if not os.path.isfile(path):
        return (False, "Timetable file does not exist: " + path, None)
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            header = reader.fieldnames or []
            hasTrigger = ("Trigger" in header)
            hasArr = ("Arr" in header)
            hasDep = ("Dep" in header)
        
            # Read rows once and compute formation mapping for this timetable
            rows = list(reader)

            formedBy = {}  # destination RN (norm) -> forming RN (original case)
            for idx, r in enumerate(rows, start=2):
                rnCell = (r.get("Reporting number", "") or "").strip()
                formingRN = rnCell if rnCell != "" else _MakeDefaultRN(idx)
                formsCell = (r.get("Forms", "") or "").strip()
                if formsCell != "":
                    formedBy[_NormRN(formsCell)] = formingRN
                   
            if not (hasTrigger or hasArr or hasDep):
                return (False, "Missing time columns: need at least one of 'Trigger', 'Arr' or 'Dep'.",
                        {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":False})
            dayCols = [c for c in header if c.lower() in
                       ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]]
            hasAnyDayColumn = (len(dayCols) > 0)
            sawData = False
            for rowIndex, row in enumerate(rows, start=2):
                sawData = True
                cells = []
                if hasTrigger:
                    v = (row.get("Trigger","") or "").strip()
                    if v != "": cells.append(("Trigger", v))
                if hasArr:
                    v = (row.get("Arr","") or "").strip()
                    if v != "": cells.append(("Arr", v))
                if hasDep:
                    v = (row.get("Dep","") or "").strip()
                    if v != "": cells.append(("Dep", v))
                if len(cells) == 0:
                    return (False, "Row %d: no time in Trigger/Arr/Dep." % rowIndex,
                            {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
                for col, val in cells:
                    if _ParseTimeToMinutes(val) is None:
                        return (False, "Row %d: invalid %s time '%s'." % (rowIndex, col, val),
                                {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
            if not sawData:
                return (False, "Timetable has no data rows.",
                        {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
            return (True, "", {"hasTrigger":hasTrigger,"hasArr":hasArr,"hasDep":hasDep,"hasAnyDayColumn":hasAnyDayColumn})
    except Exception as ex:
        return (False, "Error reading timetable: " + str(ex), None)

def _CheckWorkingScripts():
    """
    Returns (isValid, firstMessage)
    For each row:
    - If Trigger present -> require scripts/workings/Trigger/<RN>.py
    - Else if Arr present -> require scripts/workings/Arr/<RN>.py
    - Else if Dep present -> require scripts/workings/Dep/<RN>.py
    RN = explicit 'Reporting number' or default TAS<rowNumber>.
    """
    path = _TimetableFilePath()
    if path is None or not os.path.isfile(path):
        return (False, "No valid timetable file to check working scripts.")
    scriptsPath = jmri.util.FileUtil.getScriptsPath()
    try:
        with open(path, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            header = reader.fieldnames or []
            hasTrigger = ("Trigger" in header); hasArr = ("Arr" in header); hasDep = ("Dep" in header)
            for rowIndex, row in enumerate(reader, start=2):
                direction = None               
                triggerPresent = hasTrigger and (row.get("Trigger","") or "").strip() != ""
                arrPresent = hasArr and (row.get("Arr","") or "").strip() != ""
                depPresent = hasDep and (row.get("Dep","") or "").strip() != ""

                # If trigger and dep present but no arr → require only trigger script
                if triggerPresent:
                    direction = "Trigger"
                elif arrPresent:
                    direction = "Arr"
                elif depPresent:
                    direction = "Dep"
                else:
                    return (False, "Row %d: no time in Trigger/Arr/Dep; cannot determine working script directory." % rowIndex)
                rnCell = (row.get("Reporting number","") or "").strip()
                rn = rnCell if rnCell != "" else _MakeDefaultRN(rowIndex)
                scriptPath = os.path.join(scriptsPath, "workings", direction, rn + ".py")
                if not os.path.isfile(scriptPath):
                    return (False, "Row %d: missing working script for RN %s in %s directory." % (rowIndex, rn, direction))
            return (True, "")
    except Exception as ex:
        return (False, "Error checking working scripts: " + str(ex))

# ------------------------- Dual-list panel -----------------------------
class RestrictedCsvChooser(JFileChooser):
    def __init__(self, baseDir):
        JFileChooser.__init__(self, baseDir)
        self.baseDir = baseDir.getCanonicalFile()
        self.setDialogTitle("Select timetable CSV")
        self.setFileSelectionMode(JFileChooser.FILES_ONLY)
        self.setAcceptAllFileFilterUsed(False)
        self.addChoosableFileFilter(FileNameExtensionFilter("CSV files (*.csv)", ["csv"]))
    def approveSelection(self):
        sel = self.getSelectedFile()
        if sel is None: return
        try:
            canonical = sel.getCanonicalFile()
            if not canonical.getName().lower().endswith(".csv"):
                LogWarn("Rejected non-CSV selection: " + canonical.getName(), alsoDialog=True)
                return
            allowed = self.baseDir.getPath()
            cpath = canonical.getPath()
            if not (cpath == allowed or cpath.startswith(allowed + File.separator)):
                LogWarn("Rejected selection outside timetable folder: " + cpath, alsoDialog=True)
                return
        except Exception as ex:
            LogError("Error validating selection: " + str(ex), ex=ex, alsoDialog=True)
            return
        JFileChooser.approveSelection(self)

def MakeDualListPanel(TitleText, AvailableTuples, InitialSelectedNames, OnChangeCallback):
    panel = MakePaperPanel()
    panel.setLayout(GridBagLayout())
    gbc = GridBagConstraints()
    gbc.insets = Insets(4,4,4,4)
    gbc.fill = GridBagConstraints.BOTH
    gbc.weightx = 1.0
    gbc.weighty = 0.0
    gbc.gridx = 0
    gbc.gridy = 0
    title = MakeHeading(TitleText)
    panel.add(title, gbc)

    availModel = DefaultListModel()
    selectedModel = DefaultListModel()
    selectedSet = set(InitialSelectedNames)

    for fname, _friendly in AvailableTuples:
        if fname not in selectedSet:
            availModel.addElement(fname)
    for fname in InitialSelectedNames:
        selectedModel.addElement(fname)
    
    class FriendlyRenderer(DefaultListCellRenderer):
        def getListCellRendererComponent(self, lst, value, index, isSelected, cellHasFocus):
            # If value is a WorkingItem, use its Label(); else assume it's a string
            if hasattr(value, "Label"):
                labelText = value.Label()
            else:
                labelText = str(value)
            comp = DefaultListCellRenderer.getListCellRendererComponent(
                self, lst, labelText, index, isSelected, cellHasFocus
            )
            comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
            # Color logic only applies to WorkingItem objects
            if hasattr(value, "IsExtra") and getattr(value, "IsExtra", False):
                comp.setForeground(Color(128, 128, 128))  # Grey for extra scripts
            elif hasattr(value, "HasScript") and not value.HasScript:
                comp.setForeground(Color(255, 0, 0))      # Red for missing
            elif hasattr(value, "ValidScript") and not value.ValidScript:
                comp.setForeground(Color(255, 140, 0))    # Orange for invalid
            else:
                comp.setForeground(THEME_TEXT_COLOR)
            comp.setBackground(LIST_SEL_BG if isSelected else THEME_PAPER)
            comp.setOpaque(True)
            return comp

    availList = JList(availModel)
    availList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
    availList.setCellRenderer(FriendlyRenderer())
    availList.setSelectionBackground(LIST_SEL_BG)
    availList.setSelectionForeground(LIST_SEL_FG)

    selectedList = JList(selectedModel)
    selectedList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
    selectedList.setCellRenderer(FriendlyRenderer())
    selectedList.setSelectionBackground(LIST_SEL_BG)
    selectedList.setSelectionForeground(LIST_SEL_FG)

    btnAdd = JButton("Add >>")
    btnRemove = JButton("<< Remove")

    def FireChange():
        sel = [selectedModel.getElementAt(i) for i in range(selectedModel.getSize())]
        LogInfo("Selection for \"" + TitleText + "\": " + ",".join(sel))
        OnChangeCallback(sel)

    def AddAction(e):
        idx = availList.getSelectedIndices()
        if idx is None or len(idx) == 0: return
        items = [availModel.getElementAt(i) for i in idx]
        for it in items:
            if it not in [selectedModel.getElementAt(i) for i in range(selectedModel.size())]:
                selectedModel.addElement(it)
        for i in sorted(idx, reverse=True):
            availModel.remove(i)
        FireChange()

    def RemoveAction(e):
        idx = selectedList.getSelectedIndices()
        if idx is None or len(idx) == 0: return
        items = [selectedModel.getElementAt(i) for i in idx]
        for i in sorted(idx, reverse=True):
            selectedModel.remove(i)
        existing = [availModel.getElementAt(i) for i in range(availModel.size())]
        merged = existing + items
        merged.sort(key=lambda n: FRIENDLY.get(n, n))
        availModel.removeAllElements()
        for it in merged:
            availModel.addElement(it)
        FireChange()

    btnAdd.addActionListener(lambda e: AddAction(e))
    btnRemove.addActionListener(lambda e: RemoveAction(e))

    gbc.gridy = 1
    gbc.weighty = 1.0
    leftScroll = JScrollPane(availList)
    leftScroll.setPreferredSize(Dimension(220, 140))
    leftScroll.getViewport().setBackground(THEME_PAPER)
    panel.add(leftScroll, gbc)

    btnPanel = Box.createVerticalBox()
    btnPanel.add(btnAdd)
    btnPanel.add(Box.createVerticalStrut(6))
    btnPanel.add(btnRemove)

    gbc.gridx = 1
    gbc.weightx = 0.0
    gbc.fill = GridBagConstraints.NONE
    panel.add(btnPanel, gbc)

    gbc.gridx = 2
    gbc.weightx = 1.0
    gbc.fill = GridBagConstraints.BOTH
    rightScroll = JScrollPane(selectedList)
    rightScroll.setPreferredSize(Dimension(220, 140))
    rightScroll.getViewport().setBackground(THEME_PAPER)
    panel.add(rightScroll, gbc)

    return panel

# ------------------------------- Main frame ----------------------------
IMPublicDisplayList = "IMPUBLICDISPLAYLIST"
IMSignallerDisplayList = "IMSIGNALLERDISPLAYLIST"

PUBLIC_SCRIPTS = [
    ("NSEClock.py", "NSE clock"),
    ("PIDCRTSingle.py", "Per platform CRT PID"),
    ("PIDCRTSummary.py", "Summary of departures CRT PID"),
    ("PIDFingerboard.py", "Fingerboard"),
    ("PIDSmall.py", "Small modern platform PID"),
]
SIGNALLER_SCRIPTS = [("TRUST-TRJA.py", "TRUST TRJA")]
FRIENDLY = dict(PUBLIC_SCRIPTS + SIGNALLER_SCRIPTS)

class TASSetupFrame(jmri.util.JmriJFrame):
    def __init__(self):
        # Base frame setup
        jmri.util.JmriJFrame.__init__(self, "Timetable Automation System setup")
        self.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
        self.setSize(780, 890)

        # --- CRITICAL: capture initial states BEFORE building tabs/UI ---
        # These are used by BuildGeneralTab()/BuildDayNightTab() to set initial checkbox states.
        # Also used later to determine whether we must prompt for a restart on close.
        self.InitialTimeActions = IsTimeActionsEnabled()   # CheckWhenTimeChanges.py at Start-Up
        self.InitialDayNight   = IsDayNightEnabled()       # DayNight.py at Start-Up
        self.InitialWeather    = IsWeatherEnabled()        # WeatherGenerator.py at Start-Up

        # Track current (user intent during this session); start equal to initial
        self.CurrentTimeActions = self.InitialTimeActions
        self.CurrentDayNight    = self.InitialDayNight
        self.CurrentWeather     = self.InitialWeather        
        
        # Hardware orientation sensing (LastReportedDirection.py) at Start-Up
        self.InitialDirectionSensing = _IsScriptEnabled("LastReportedDirection.py")
        self.CurrentDirectionSensing = self.InitialDirectionSensing
        
        # TAS menu on Start-Up (TimetableAutomation.py)
        self.InitialTASMenu = _IsScriptEnabled("TimetableAutomation.py")
        self.CurrentTASMenu = self.InitialTASMenu

        # --- Build tabs AFTER initial/current state is ready ---
        tabs = JTabbedPane()
        ApplyTheme(tabs)
        tabs.addTab("General setup", self.BuildGeneralTab())
        tabs.addTab("Timetable", self.BuildTimetableTab())
        tabs.addTab("Workings", self.BuildWorkingsTab())
        tabs.addTab("Timing points", self.BuildTimingPointsTab())
        tabs.addTab("Orientation", self.BuildOrientationTab())
        tabs.addTab("Display configuration", self.BuildDisplayTab())
        tabs.addTab("Day/night cycle", self.BuildDayNightTab())
        tabs.addTab("Interface", self.BuildInterfaceTab())

        # Finalize
        self.getContentPane().add(tabs, BorderLayout.CENTER)
        self.PackAndCenter()
        
        # Set window icon using TASIcon utility
        try:
            from TASIcon import SetFrameClockIcon
            SetFrameClockIcon(self, 32)  # 32px icon size
        except Exception as ex:
            print("[TASSetup] Failed to set setup window icon: " + str(ex))
     
        self.setVisible(True)
        # Ensure initial font is applied across all controls
        try:
            _ApplyFontRecursive(self.getContentPane(), THEME_FONT_FAMILY)
        except:
            pass
        LogInfo("Setup window opened.")

    def PackAndCenter(self):
        self.pack()
        try: self.setLocationRelativeTo(None)
        except: pass

    # ------------------------------ General ----------------------------
    
    def RefreshFonts(self):
        # Apply THEME_FONT_FAMILY to all tabs and headings
        try:
            for comp in self.getContentPane().getComponents():
                ApplyTheme(comp)
                for sub in comp.getComponents():
                    ApplyTheme(sub)
        except:
            pass
    
    def BuildGeneralTab(self):
        panel = MakePaperPanel()
        panel.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10,10,10,10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 0.0
        gbc.weighty = 0.0

        # Top-centered Setup wizard
        gbc.gridx = 0; gbc.gridy = 0; gbc.gridwidth = 3
               
        header = Box.createHorizontalBox()
        header.add(Box.createHorizontalGlue())
        wizardBtn = JButton("Setup wizard")

        # Check if TASWiz.py exists in profile:jython
        wizExists = ScriptExists("TASWiz.py")
        wizardBtn.setVisible(wizExists)
        wizardBtn.setEnabled(wizExists)

        # If enabled, make the button double height
        if wizExists:
            # Get current preferred size and double the height
            size = wizardBtn.getPreferredSize()
            wizardBtn.setPreferredSize(Dimension(size.width, size.height * 2))

        def DoWizard(e=None):
            try:
                path = ProfileJythonFilePath("TASWiz.py")
                if not os.path.isfile(path):
                    LogWarn("TASWiz.py not found at: " + path, alsoDialog=True)
                    return
                execfile(path, {})
            except Exception as ex:
                LogError("Setup wizard failed: " + str(ex), ex=ex, alsoDialog=True)

        if wizExists:
            wizardBtn.addActionListener(lambda e: DoWizard())

        header.add(wizardBtn)
        header.add(Box.createHorizontalGlue())
        panel.add(header, gbc)

        # (A) NEW: Enable time-based actions (requires restart) — controls CheckWhenTimeChanges.py at Start-Up
        gbc.gridwidth = 3
        gbc.gridx = 0; gbc.gridy = 1
        timeRow = Box.createHorizontalBox()
        self.ChkTimeActions = JCheckBox("Enable time-based actions (requires restart)")
        self.ChkTimeActions.setOpaque(False)
        self.ChkTimeActions.setSelected(self.InitialTimeActions)
        # (A0) Show TAS menu on Start-Up (requires restart) — controls TimetableAutomation.py at Start-Up
        gbc.gridwidth = 3
        gbc.gridx = 0; gbc.gridy = 1
        tasMenuRow = Box.createHorizontalBox()
        self.ChkTASMenu = JCheckBox("Show the Timetable Automation System menu on startup")
        self.ChkTASMenu.setOpaque(False)
        self.ChkTASMenu.setSelected(self.InitialTASMenu)

        def OnTASMenu(e=None):
            want = self.ChkTASMenu.isSelected()
            ok = _EnsureScriptEnabled("TimetableAutomation.py", want)
            actual = _IsScriptEnabled("TimetableAutomation.py")
            self.CurrentTASMenu = actual
            self.ChkTASMenu.setSelected(actual)
            if not ok:
                LogWarn("Could not change Start-Up for TimetableAutomation.py", alsoDialog=True)

        self.ChkTASMenu.addActionListener(OnTASMenu)
        tasMenuRow.add(self.ChkTASMenu)
        panel.add(tasMenuRow, gbc)

        # Error label for missing TAS menu script
        gbc.gridy += 1
        self.LblTASMenuError = JLabel("")
        ApplyTheme(self.LblTASMenuError)
        panel.add(self.LblTASMenuError, gbc)

        missingTAS = []
        if not ScriptExists("TimetableAutomation.py"):
            missingTAS.append("TimetableAutomation.py")

        if missingTAS:
            self.ChkTASMenu.setSelected(False)
            self.ChkTASMenu.setEnabled(False)
            msgTAS = "<html>" + "<br/>".join(["Missing script: " + m for m in missingTAS]) + "</html>"
            self.LblTASMenuError.setText(msgTAS)

        # Add a spacer so "Enable time-based actions" moves down cleanly, but nothing else shifts
        gbc.gridy += 1
        panel.add(JLabel(" "), gbc)
        def OnTimeActions(e=None):
            want = self.ChkTimeActions.isSelected()

            # Enable/disable all scripts under the single master toggle
            ok = _EnsureScriptEnabled("CheckWhenTimeChanges.py", want) and _EnsureScriptEnabled("TimeWarpChecker.py") and _EnsureScriptEnabled("DayTracker.py", want)
            
            # Reflect actual combined state and track it for the restart prompt
            actual = IsTimeActionsEnabled()
            self.CurrentTimeActions = actual
            self.ChkTimeActions.setSelected(actual)

            if not (ok):
                LogWarn("Could not change Start-Up for one or more time-based action scripts.", alsoDialog=True)

        self.ChkTimeActions.addActionListener(OnTimeActions)
        timeRow.add(self.ChkTimeActions)
        panel.add(timeRow, gbc)
        
        # Error label for missing scripts
        gbc.gridy += 1
        self.LblTimeActionsError = JLabel("")
        ApplyTheme(self.LblTimeActionsError)
        panel.add(self.LblTimeActionsError, gbc)

        # Check existence of both scripts
        missing = []
        if not ScriptExists("CheckWhenTimeChanges.py"): missing.append("CheckWhenTimeChanges.py")
        if not ScriptExists("DayTracker.py"): missing.append("DayTracker.py")
        if not ScriptExists("TimeWarpChecker.py"): missing.append("TimeWarpChecker.py")
        if missing:
            self.ChkTimeActions.setSelected(False)
            self.ChkTimeActions.setEnabled(False)
            msg = "<html>" + "<br/>".join(["Missing script: " + m for m in missing]) + "</html>"
            self.LblTimeActionsError.setText(msg)

        # Add extra vertical space before next checkbox
        gbc.gridy += 1
        spacer = JLabel(" ")  # blank spacer for padding
        panel.add(spacer, gbc)

        # Now increment again for the second checkbox row
        gbc.gridy += 1

        # (B) "Run trains automatically" row (checkbox + status label) — NOW uses IMTASAutoWorking memory only
        gbc.gridwidth = 3
        gbc.gridx = 0
        gbc.gridy += 1  # move down below the TAS menu section
        # Add twice as much vertical space below the time-based actions error label
        gbc.gridy += 1
        panel.add(JLabel(" "), gbc)  # spacer row 1
        gbc.gridy += 1
        panel.add(JLabel(" "), gbc)  # spacer row 2

        # Now place the second checkbox on the next row
        gbc.gridy += 1
        runRow = Box.createHorizontalBox()
        self.ChkRunAuto = JCheckBox("Run trains automatically from timetable")
        self.ChkRunAuto.setOpaque(False)

        # Disable second checkbox whenever the first is disabled
        if not self.ChkTimeActions.isEnabled():
            self.ChkRunAuto.setEnabled(False)

        self.LblRunAutoStatus = JLabel("")  # concise, wrapped status (HTML)
        runRow.add(self.ChkRunAuto)
        runRow.add(Box.createHorizontalStrut(12))
        runRow.add(self.LblRunAutoStatus)
        panel.add(runRow, gbc)
        
        # Disable second checkbox if first is disabled
        if not self.ChkTimeActions.isEnabled():
            self.ChkRunAuto.setEnabled(False)

        # NOTE: Removed separate “Requires restart to take effect.” label — restart is for time-based actions only

        # Current timetable heading + widgets
        gbc.gridwidth = 1
        gbc.gridx = 0
        gbc.gridy += 1  # place heading just after the second checkbox row
        panel.add(MakeHeading("Current timetable"), gbc)

        txt = JTextField(28)
        txt.setToolTipText("Select the timetable used for this layout")
        txt.setText(GetMemoryString(IMCurrentTimetable, ""))

        def CommitText():
            name = StripCsvExt(txt.getText().strip())
            SetMemoryString(IMCurrentTimetable, name)
            self.UpdateRunAutoControls()
            # No Start-Up change for auto-run now; validations still inform status
        txt.addActionListener(lambda e: CommitText())
        class CommitOnFocusLost(FocusAdapter):
            def focusLost(self, e): CommitText()
        txt.addFocusListener(CommitOnFocusLost())

        btnBrowse = JButton("Browse...")
        btnBrowse.setToolTipText("Select the timetable used for this layout")
        def DoBrowse(e):
            try:
                dirFile = GetTimetableDirFile()
                chooser = RestrictedCsvChooser(dirFile)
                memName = StripCsvExt(txt.getText().strip())
                if memName != "":
                    pre = File(dirFile, memName + ".csv")
                    chooser.setSelectedFile(pre)
                result = chooser.showOpenDialog(self)
                if result == JFileChooser.APPROVE_OPTION:
                    sel = chooser.getSelectedFile()
                    bare = StripCsvExt(sel.getName())
                    txt.setText(bare)
                    CommitText()
            except Exception as ex:
                LogError("Browse failed: " + str(ex), ex=ex, alsoDialog=True)
        btnBrowse.addActionListener(lambda e: DoBrowse(e))
        
        gbc.gridx = 1; gbc.weightx = 1.0
        panel.add(txt, gbc)
        gbc.gridx = 2; gbc.weightx = 0.0
        panel.add(btnBrowse, gbc)

        # Wire up RunAuto checkbox logic (memory-based)
        def OnRunAuto(e=None):
            want = self.ChkRunAuto.isSelected()
            # Track memory for auto-working; create if first time set to true
            SetMemoryBool(IMTASAutoWorking, want)
            self.UpdateRunAutoControls()
        self.ChkRunAuto.addActionListener(OnRunAuto)
        self.UpdateRunAutoControls()

        # --- Place "Allow delays / Allow cancellations" BELOW the Run Auto row ---
        gbc.gridx = 0
        gbc.gridwidth = 3
        gbc.fill = GridBagConstraints.NONE
        gbc.gridy += 1  # move to the next row under "Run trains automatically from timetable"

        boxPanel = Box.createHorizontalBox()
        chkDelays = JCheckBox("Allow delays")
        chkDelays.setOpaque(False)
        chkDelays.setSelected(GetMemoryBool(IMAllowDelays, False))
        chkDelays.addActionListener(lambda e: SetMemoryBool(IMAllowDelays, chkDelays.isSelected()))
        chkCancellations = JCheckBox("Allow cancellations")
        chkCancellations.setOpaque(False)
        chkCancellations.setSelected(GetMemoryBool(IMAllowCANCELLATIONS, False))
        chkCancellations.addActionListener(lambda e: SetMemoryBool(IMAllowCANCELLATIONS, chkCancellations.isSelected()))
        boxPanel.add(chkDelays); boxPanel.add(Box.createHorizontalStrut(18))
        boxPanel.add(chkCancellations)
        panel.add(boxPanel, gbc)
        
        # -- Reset registers row: two buttons with confirmations --
        gbc.gridy += 1
        gbc.gridwidth = 3
        gbc.fill = GridBagConstraints.NONE
        resetRow = Box.createHorizontalBox()

        btnResetDisruption = JButton("Reset disruption data")
        btnResetTiming = JButton("Reset timing data")

        def DoResetDisruption(e=None):
            try:
                msg = ("This will permanently clear all recorded delays and cancellations.\n"
                       "This action cannot be undone.\n\nProceed?")
                choice = JOptionPane.showConfirmDialog(
                    self, msg, "Confirm reset (disruption data)",
                    JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE
                )
                if choice == JOptionPane.OK_OPTION:
                    # DisruptionRegister: synchronized Hashtable + save()
                    import DisruptionRegister as DR
                    try:
                        DR.register.clear()
                        DR.save()
                        # Also re-seed disruption generator: IMDISRUPTIONSEEDBASE = current time (ms)
                        try:
                            from java.lang import System as _JSystem
                            SetMemoryString("IMDISRUPTIONSEEDBASE", str(_JSystem.currentTimeMillis()))
                        except Exception:
                            import time as _pyTime
                            SetMemoryString("IMDISRUPTIONSEEDBASE", str(int(_pyTime.time() * 1000)))
                        LogInfo("[TAS] Disruption register cleared.", alsoDialog=True, title="Done")
                    except Exception as ex:
                        LogError("Failed to clear disruption register: " + str(ex), ex=ex, alsoDialog=True)
            except Exception as exOuter:
                LogError("Reset disruption action failed: " + str(exOuter), ex=exOuter, alsoDialog=True)

        def DoResetTiming(e=None):
            try:
                msg = ("This will permanently clear all timing point records (timings at every TP).\n"
                       "Blocks definitions remain as-is; only timing tuples are removed when entries are deleted.\n"
                       "This action cannot be undone.\n\nProceed?")
                choice = JOptionPane.showConfirmDialog(
                    self, msg, "Confirm reset (timing data)",
                    JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE
                )
                if choice == JOptionPane.OK_OPTION:
                    import TimingRegister as TR
                    try:
                        # Remove every timing point entry using lock-safe helpers
                        tps = TR.listTimingPoints() or []
                        for tp in tps:
                            try:
                                TR.deleteTimingPoint(tp)
                            except Exception as exDel:
                                print("[TASSetup] WARN: Could not delete timing point {}: {}".format(tp, exDel))
                        TR.save()
                        LogInfo("[TAS] Timing register cleared.", alsoDialog=True, title="Done")
                    except Exception as ex:
                        LogError("Failed to clear timing register: " + str(ex), ex=ex, alsoDialog=True)
            except Exception as exOuter:
                LogError("Reset timing action failed: " + str(exOuter), ex=exOuter, alsoDialog=True)

        btnResetDisruption.addActionListener(lambda e: DoResetDisruption(e))
        btnResetTiming.addActionListener(lambda e: DoResetTiming(e))

        resetRow.add(btnResetDisruption)
        resetRow.add(Box.createHorizontalStrut(12))
        resetRow.add(btnResetTiming)

        panel.add(resetRow, gbc)

        # --- Enqueued workings status + reset button ---
        import enqueuedWorkings as EW

        # Status label showing current count
        gbc.gridy += 1
        self.LblEnqueued = JLabel("Enqueued workings: %d" % EW.countWorkings())
        ApplyTheme(self.LblEnqueued)
        panel.add(self.LblEnqueued, gbc)  
        # Grey-out rule: disable the reset button when there are no enqueued workings
        currentCount = EW.countWorkings()

        # Reset button      
        gbc.gridy += 1
        btnResetEnqueued = JButton("Reset enqueued workings")
        # Set initial enabled state: only enabled when there is something to clear
        btnResetEnqueued.setEnabled(currentCount > 0)

        def DoResetEnqueued(e=None):
            try:
                msg = (
                    "This will permanently clear all enqueued workings.\n"
                    "These are the workings that could not run at their scheduled times.\n"
                    "This action cannot be undone.\n\nProceed?"
                )
                choice = JOptionPane.showConfirmDialog(
                    self,
                    msg,
                    "Confirm reset (enqueued workings)",
                    JOptionPane.OK_CANCEL_OPTION,
                    JOptionPane.WARNING_MESSAGE
                )
                if choice == JOptionPane.OK_OPTION:                  
                    EW.ClearWorkings()
                    # Update label + button enabled state immediately
                    newCount = EW.countWorkings()
                    self.LblEnqueued.setText("Enqueued workings: %d" % newCount)
                    btnResetEnqueued.setEnabled(newCount > 0)
                    self.LblEnqueued.setText("Enqueued workings: %d" % EW.countWorkings())
            except Exception as ex:
                LogError("Failed to clear enqueued workings: " + str(ex), ex=ex, alsoDialog=True)

        btnResetEnqueued.addActionListener(lambda e: DoResetEnqueued())
        panel.add(btnResetEnqueued, gbc)
        
        return panel

        # Wire up RunAuto checkbox logic (memory-based)
        def OnRunAuto(e=None):
            want = self.ChkRunAuto.isSelected()
            # Track memory for auto-working; create if first time set to true
            SetMemoryBool(IMTASAutoWorking, want)
            self.UpdateRunAutoControls()
        self.ChkRunAuto.addActionListener(OnRunAuto)
        self.UpdateRunAutoControls()

        return panel

    def UpdateRunAutoControls(self):
        # 1) Read current memory state
        isEnabled = GetMemoryBool(IMTASAutoWorking, False)

        # 2) Run validations (unchanged) for informative status only
        ttOK, ttMsg, hdr = _ValidateTimetable()
        wsOK, wsMsg = _CheckWorkingScripts()

        # 3) Concise, wrapped status: general explanation + first issue only
        statusHtml = ""
        if not ttOK:
            statusHtml = "<html>Cannot enable automatic running: timetable is not valid.<br/>First issue: %s There may be more issues.</html>" % ttMsg
        elif not wsOK:
            statusHtml = "<html>Cannot enable automatic running: required working scripts are missing.<br/>First issue: %s There may be more issues.</html>" % wsMsg
        else:
            statusHtml = ""
        self.LblRunAutoStatus.setText(statusHtml)

        # 4) Checkbox mirrors memory
        self.ChkRunAuto.setSelected(isEnabled)

        # 5) Grey-out rule with master toggle guard:
        # If the master time-based actions checkbox is disabled (missing scripts),
        # always disable auto-working; otherwise apply the normal validation rule.
        masterEnabled = self.ChkTimeActions.isEnabled()
        if not masterEnabled:
            self.ChkRunAuto.setEnabled(False)
        else:
            # If currently disabled and validations cannot be met -> disable (grey out).
            # If currently enabled -> allow interaction (you may want to turn it off).
            canEnable = ttOK and wsOK
            self.ChkRunAuto.setEnabled(isEnabled or canEnable)

    # ------------------------ Display configuration --------------------
    def BuildDisplayTab(self):
        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(8,8,8,8)
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0
        gbc.weighty = 1.0

        pubSel = [s for s in GetMemoryString(IMPublicDisplayList, "").split(",") if s.strip() != ""]
        sigSel = [s for s in GetMemoryString(IMSignallerDisplayList, "").split(",") if s.strip() != ""]

        def SavePublic(selection):
            SetMemoryString(IMPublicDisplayList, ",".join(selection))
        def SaveSignaller(selection):
            SetMemoryString(IMSignallerDisplayList, ",".join(selection))

        gbc.gridx = 0; gbc.gridy = 0
        pubPanel = MakeDualListPanel("Public information displays",
            PUBLIC_SCRIPTS, pubSel, SavePublic)
        root.add(pubPanel, gbc)

        gbc.gridx = 0; gbc.gridy = 1
        sigPanel = MakeDualListPanel("Signallers' displays",
            SIGNALLER_SCRIPTS, sigSel, SaveSignaller)
        root.add(sigPanel, gbc)

        return root
        
     # --------------------------- Interface -----------------------
    def BuildInterfaceTab(self):
        # Interface tab for TimetableAutomation front-page UI settings
        # ASCII-only, modular, memory-backed, thread-safe.

        root = MakePaperPanel()
        root.setLayout(GridBagLayout())

        gbc = GridBagConstraints()
        gbc.insets = Insets(10, 10, 10, 10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Heading
        root.add(MakeHeading("TimetableAutomation UI settings"), gbc)
        
        def ApplyFont(e=None):
            try:
                sel = str(cmbFont.getSelectedItem())
                if sel and len(sel.strip()) > 0:
                    SetMemoryString("IMTAS_FONT_FAMILY", sel.strip())
                    # Update theme and refresh UI
                    global THEME_FONT_FAMILY
                    THEME_FONT_FAMILY = sel.strip()
                    self.RefreshFonts()
            except:
                pass
 
        
        # -------------------- (A) Typeface (system fonts) --------------------
        gbc.gridy += 1
        rowFont = Box.createHorizontalBox()
        lblFont = JLabel("Typeface (font family):")
        # Collect available font family names from Java AWT
        try:
            families = list(GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames())
            families.sort(key=lambda s: s.lower())
        except:
            families = [GetDefaultFontFamily()]
        cmbFont = JComboBox(families)
        currentFont = GetMemoryString("IMTAS_FONT_FAMILY", GetDefaultFontFamily())
        # Choose current if present; else fall back to default
        try:
            if currentFont in families:
                cmbFont.setSelectedItem(currentFont)
            else:
                cmbFont.setSelectedItem(GetDefaultFontFamily())
        except:
            pass
        def ApplyFont(e=None):
            try:
                sel = str(cmbFont.getSelectedItem())
                if sel and len(sel.strip()) > 0:
                    SetMemoryString("IMTAS_FONT_FAMILY", sel.strip())
                    # Update the theme font and refresh everything
                    global THEME_FONT_FAMILY
                    THEME_FONT_FAMILY = sel.strip()
                    # Re-apply fonts recursively to the entire content pane
                    cp = self.getContentPane()
                    if cp is not None:
                        _ApplyFontRecursive(cp, THEME_FONT_FAMILY)
                        # Ensure tab headers and title bar revalidate/repaint
                        try:
                            cp.revalidate(); cp.repaint()
                        except:
                            pass
            except:
                pass
        cmbFont.addActionListener(lambda e: ApplyFont(e))
        rowFont.add(lblFont); rowFont.add(Box.createHorizontalStrut(8)); rowFont.add(cmbFont)
        root.add(rowFont, gbc)

        # -------------------- (B) Background colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg = Box.createHorizontalBox()
        lblBg = JLabel("Background colour:")

        # Swatch panel (robust against LAF quirks)
        swatch = JPanel()
        swatch.setOpaque(True)
        swatch.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size: BoxLayout honors min/max for JPanel
        sw, sh = 100, 36
        swatch.setPreferredSize(Dimension(sw, sh))
        swatch.setMinimumSize(Dimension(sw, sh))
        swatch.setMaximumSize(Dimension(sw, sh))

        # Initial colour from memory (fallback to TimetableAutomation default cover colour 240,238,220)
        memRgb = GetMemoryString("IMTASCOVERCOLOUR", GetDefaultBackgroundRGB())
        currentColor = _RgbStrToColorOrDefault(memRgb, Color(240,238,220))
        swatch.setBackground(currentColor)

        class SwatchClick(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch.getBackground()
                    # Parent None avoids inner-class 'self' confusion in Jython
                    chosen = JColorChooser.showDialog(None, "Choose background colour", initial)
                    if chosen is not None:
                        swatch.setBackground(chosen)
                        SetMemoryString("IMTASCOVERCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch.addMouseListener(SwatchClick())

        # Reset button: revert to TimetableAutomation default cover colour
        btnReset = JButton("Reset")
        def DoReset(e=None):
            try:
                defaultColor = _RgbStrToColorOrDefault(GetDefaultBackgroundRGB(), Color(240,238,220))
                swatch.setBackground(defaultColor)
                SetMemoryString("IMTASCOVERCOLOUR", _ColorToRgbStr(defaultColor))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)
        btnReset.addActionListener(lambda e: DoReset(e))

        rowBg.add(lblBg)
        rowBg.add(Box.createHorizontalStrut(8))
        rowBg.add(swatch)
        rowBg.add(Box.createHorizontalStrut(8))
        rowBg.add(btnReset)
        root.add(rowBg, gbc)
        
        # -------------------- (B2) Inner panel background colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg2 = Box.createHorizontalBox()
        lblBg2 = JLabel("Inner background colour:")

        # Swatch panel (robust against LAF quirks)
        swatch2 = JPanel()
        swatch2.setOpaque(True)
        swatch2.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size: BoxLayout honors min/max for JPanel
        sw2, sh2 = 100, 36
        swatch2.setPreferredSize(Dimension(sw2, sh2))
        swatch2.setMinimumSize(Dimension(sw2, sh2))
        swatch2.setMaximumSize(Dimension(sw2, sh2))

        # Initial colour from memory (fallback to TimetableAutomation inner default 220,235,220)
        memRgb2 = GetMemoryString("IMTASINNERCOLOUR", "220,235,220")
        currentColor2 = _RgbStrToColorOrDefault(memRgb2, Color(220,235,220))
        swatch2.setBackground(currentColor2)

        class Swatch2Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch2.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose inner background colour", initial)
                    if chosen is not None:
                        swatch2.setBackground(chosen)
                        SetMemoryString("IMTASINNERCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch2.addMouseListener(Swatch2Click())

        # Reset button: revert to TimetableAutomation inner default colour
        btnReset2 = JButton("Reset")
        def DoReset2(e=None):
            try:
                defaultColor2 = Color(220,235,220)
                swatch2.setBackground(defaultColor2)
                SetMemoryString("IMTASINNERCOLOUR", _ColorToRgbStr(defaultColor2))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset2.addActionListener(lambda e: DoReset2(e))

        rowBg2.add(lblBg2)
        rowBg2.add(Box.createHorizontalStrut(8))
        rowBg2.add(swatch2)
        rowBg2.add(Box.createHorizontalStrut(8))
        rowBg2.add(btnReset2)
        root.add(rowBg2, gbc)
        
        # (B2.5) Ink colour (text/lines/boxes/button outlines) — JColorChooser
        gbc.gridy += 1
        rowInk = Box.createHorizontalBox()
        lblInk = JLabel("Ink colour (text/lines/boxes/button outlines):")
        # Swatch panel
        swatchInk = JPanel()
        swatchInk.setOpaque(True)
        swatchInk.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))
        # Fixed size like other swatches
        swi, shi = 100, 36
        swatchInk.setPreferredSize(Dimension(swi, shi))
        swatchInk.setMinimumSize(Dimension(swi, shi))
        swatchInk.setMaximumSize(Dimension(swi, shi))
        # Initial colour from memory (default = black 0,0,0)
        memRgbInk = GetMemoryString("IMTASINKCOLOUR", "0,0,0")
        currentInk = _RgbStrToColorOrDefault(memRgbInk, Color(0,0,0))
        swatchInk.setBackground(currentInk)

        class SwatchInkClick(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatchInk.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose ink colour", initial)
                    if chosen is not None:
                        swatchInk.setBackground(chosen)
                        SetMemoryString("IMTASINKCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatchInk.addMouseListener(SwatchInkClick())

        # Reset button -> default black
        btnResetInk = JButton("Reset")
        def DoResetInk(e=None):
            try:
                defaultInk = Color(0,0,0)
                swatchInk.setBackground(defaultInk)
                SetMemoryString("IMTASINKCOLOUR", _ColorToRgbStr(defaultInk))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)
        btnResetInk.addActionListener(lambda e: DoResetInk(e))

        rowInk.add(lblInk)
        rowInk.add(Box.createHorizontalStrut(8))
        rowInk.add(swatchInk)
        rowInk.add(Box.createHorizontalStrut(8))
        rowInk.add(btnResetInk)
        root.add(rowInk, gbc)

        # -------------------- (B3) Paper background colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg3 = Box.createHorizontalBox()
        lblBg3 = JLabel("Setup & WTT paper colour:")

        # Swatch panel
        swatch3 = JPanel()
        swatch3.setOpaque(True)
        swatch3.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size
        sw3, sh3 = 100, 36
        swatch3.setPreferredSize(Dimension(sw3, sh3))
        swatch3.setMinimumSize(Dimension(sw3, sh3))
        swatch3.setMaximumSize(Dimension(sw3, sh3))

        # Initial colour from memory (default = WTTDisplay.py paper 249,246,238)
        memRgb3 = GetMemoryString("IMTASPAPERCOLOUR", "249,246,238")
        currentColor3 = _RgbStrToColorOrDefault(memRgb3, Color(249,246,238))
        swatch3.setBackground(currentColor3)

        class Swatch3Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch3.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose paper colour", initial)
                    if chosen is not None:
                        swatch3.setBackground(chosen)
                        SetMemoryString("IMTASPAPERCOLOUR", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch3.addMouseListener(Swatch3Click())

        # Reset button -> default 249,246,238
        btnReset3 = JButton("Reset")
        def DoReset3(e=None):
            try:
                defaultColor3 = Color(249,246,238)
                swatch3.setBackground(defaultColor3)
                SetMemoryString("IMTASPAPERCOLOUR", _ColorToRgbStr(defaultColor3))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset3.addActionListener(lambda e: DoReset3(e))

        rowBg3.add(lblBg3)
        rowBg3.add(Box.createHorizontalStrut(8))
        rowBg3.add(swatch3)
        rowBg3.add(Box.createHorizontalStrut(8))
        rowBg3.add(btnReset3)
        root.add(rowBg3, gbc)
        
        # -------------------- (B4) WTT darker band colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg4 = Box.createHorizontalBox()
        lblBg4 = JLabel("WTT darker band colour:")

        # Swatch panel
        swatch4 = JPanel()
        swatch4.setOpaque(True)
        swatch4.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size
        sw4, sh4 = 100, 36
        swatch4.setPreferredSize(Dimension(sw4, sh4))
        swatch4.setMinimumSize(Dimension(sw4, sh4))
        swatch4.setMaximumSize(Dimension(sw4, sh4))

        # Initial colour from memory (default = legacy dark band 245,242,235)
        memRgb4 = GetMemoryString("IMTASWTTBANDDARK", "245,242,235")
        currentColor4 = _RgbStrToColorOrDefault(memRgb4, Color(245,242,235))
        swatch4.setBackground(currentColor4)

        class Swatch4Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch4.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose WTT darker band colour", initial)
                    if chosen is not None:
                        swatch4.setBackground(chosen)
                        SetMemoryString("IMTASWTTBANDDARK", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch4.addMouseListener(Swatch4Click())

        # Reset button -> default 245,242,235
        btnReset4 = JButton("Reset")
        def DoReset4(e=None):
            try:
                defaultColor4 = Color(245,242,235)
                swatch4.setBackground(defaultColor4)
                SetMemoryString("IMTASWTTBANDDARK", _ColorToRgbStr(defaultColor4))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset4.addActionListener(lambda e: DoReset4(e))

        rowBg4.add(lblBg4)
        rowBg4.add(Box.createHorizontalStrut(8))
        rowBg4.add(swatch4)
        rowBg4.add(Box.createHorizontalStrut(8))
        rowBg4.add(btnReset4)
        root.add(rowBg4, gbc)
        
        # -------------------- ((B5) WTT lighter band colour (JColorChooser) --------------------
        gbc.gridy += 1
        rowBg5 = Box.createHorizontalBox()
        lblBg5 = JLabel("WTT lighter band colour:")

        # Swatch panel
        swatch5 = JPanel()
        swatch5.setOpaque(True)
        swatch5.setBorder(BorderFactory.createLineBorder(Color(80,80,80), 1))

        # Fixed size
        sw5, sh5 = 100, 36
        swatch5.setPreferredSize(Dimension(sw5, sh5))
        swatch5.setMinimumSize(Dimension(sw5, sh5))
        swatch5.setMaximumSize(Dimension(sw5, sh5))

        # Initial colour from memory (default = legacy light band 255,253,247)
        memRgb5 = GetMemoryString("IMTASWTTBANDLIGHT", "255,253,247")
        currentColor5 = _RgbStrToColorOrDefault(memRgb5, Color(255,253,247))
        swatch5.setBackground(currentColor5)

        class Swatch5Click(MouseAdapter):
            def mouseClicked(self, e):
                try:
                    initial = swatch5.getBackground()
                    chosen = JColorChooser.showDialog(None, "Choose WTT lighter band colour", initial)
                    if chosen is not None:
                        swatch5.setBackground(chosen)
                        SetMemoryString("IMTASWTTBANDLIGHT", _ColorToRgbStr(chosen))
                except Exception as ex:
                    LogWarn("Colour chooser failed: " + str(ex), alsoDialog=True)

        swatch5.addMouseListener(Swatch5Click())

        # Reset button -> default 255,253,247
        btnReset5 = JButton("Reset")
        def DoReset5(e=None):
            try:
                defaultColor5 = Color(255,253,247)
                swatch5.setBackground(defaultColor5)
                SetMemoryString("IMTASWTTBANDLIGHT", _ColorToRgbStr(defaultColor5))
            except Exception as ex:
                LogWarn("Reset failed: " + str(ex), alsoDialog=True)

        btnReset5.addActionListener(lambda e: DoReset5(e))

        rowBg5.add(lblBg5)
        rowBg5.add(Box.createHorizontalStrut(8))
        rowBg5.add(swatch5)
        rowBg5.add(Box.createHorizontalStrut(8))
        rowBg5.add(btnReset5)
        root.add(rowBg5, gbc)
        
        
        # -------------------- (C) Cover header text: IMRAILWAYCO / IMREGION / IMSECTION --------------------
        # IMRAILWAYCO
        gbc.gridy += 1
        rowRail = Box.createHorizontalBox()
        lblRail = JLabel("Railway company:")
        txtRail = JTextField(24)
        txtRail.setText(GetMemoryString("IMRAILWAYCO", "BRITISH RAILWAYS"))
        def CommitRail():
            SetMemoryString("IMRAILWAYCO", txtRail.getText().strip())
        txtRail.addActionListener(lambda e: CommitRail())
        class RailLost(FocusAdapter):
            def focusLost(self, e): CommitRail()
        txtRail.addFocusListener(RailLost())
        rowRail.add(lblRail); rowRail.add(Box.createHorizontalStrut(8)); rowRail.add(txtRail)
        root.add(rowRail, gbc)

        # IMREGION
        gbc.gridy += 1
        rowRegion = Box.createHorizontalBox()
        lblRegion = JLabel("Region:")
        txtRegion = JTextField(24)
        txtRegion.setText(GetMemoryString("IMREGION", "LONDON MIDLAND REGION"))
        def CommitRegion():
            SetMemoryString("IMREGION", txtRegion.getText().strip())
        txtRegion.addActionListener(lambda e: CommitRegion())
        class RegionLost(FocusAdapter):
            def focusLost(self, e): CommitRegion()
        txtRegion.addFocusListener(RegionLost())
        rowRegion.add(lblRegion); rowRegion.add(Box.createHorizontalStrut(8)); rowRegion.add(txtRegion)
        root.add(rowRegion, gbc)

        # IMSECTION
        gbc.gridy += 1
        rowSection = Box.createHorizontalBox()
        lblSection = JLabel("Section:")
        txtSection = JTextField(24)
        txtSection.setText(GetMemoryString("IMSECTION", "SECTION B"))
        def CommitSection():
            SetMemoryString("IMSECTION", txtSection.getText().strip())
        txtSection.addActionListener(lambda e: CommitSection())
        class SectionLost(FocusAdapter):
            def focusLost(self, e): CommitSection()
        txtSection.addFocusListener(SectionLost())
        rowSection.add(lblSection); rowSection.add(Box.createHorizontalStrut(8)); rowSection.add(txtSection)
        root.add(rowSection, gbc)

        # -------------------- (D) Spacer for future interface controls --------------------
        gbc.gridy += 1
        spacer = JLabel("")
        ApplyTheme(spacer)
        root.add(spacer, gbc)

        return root

    def BuildTimetableTab(self):
        """
        Timetable (WTTDisplay) parameter configuration.
        Controls chosen per field:
          - PAGE_MODE        : JComboBox (drop-down of known modes)
          - TIME_24H         : JCheckBox (boolean)
          - TIME_SEPARATOR   : JTextField (single character; limited to length 1)
          - ECS_LABEL        : JTextField (single line)
          - _ECS_DEST_MATCH  : JTextArea (multi-line; one token per line)
          - DIRECTION_SPLIT  : JCheckBox (boolean)
        """
        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10, 10, 10, 10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Heading
        root.add(MakeHeading("Working Timetable (WTT) display options"), gbc)

        # (1) PAGE_MODE — drop-down (matches WTTDisplay recognized modes)
        gbc.gridy += 1
        rowMode = Box.createHorizontalBox()
        lblMode = JLabel("Page mode:")
        ApplyTheme(lblMode)
        modes = ["WEEKDAYS_SAT_SUN", "SEVEN_DAYS", "MONSAT_PLUS_SUN", "ALL_WEEK"]
        friendlyModes = {
            "WEEKDAYS_SAT_SUN": "Weekdays, Saturdays, Sundays",
            "SEVEN_DAYS": "Each day of the week individually",
            "MONSAT_PLUS_SUN": "Weekdays (including Saturdays), Sundays",
            "ALL_WEEK": "All week in one view"
            }
        
        # Combo box with friendly names
        cmbMode = JComboBox(list(friendlyModes.values()))
        ApplyTheme(cmbMode)

        # Load current internal code and select corresponding friendly name
        currentModeCode = GetMemoryString(IMWTT_PageMode, "WEEKDAYS_SAT_SUN")
        currentFriendly = friendlyModes.get(currentModeCode, friendlyModes["WEEKDAYS_SAT_SUN"])
        cmbMode.setSelectedItem(currentFriendly)

        # Commit logic: map friendly name back to internal code
        def ApplyPageMode(e=None):
            try:
                selFriendly = str(cmbMode.getSelectedItem()).strip()
                for code, friendly in friendlyModes.items():
                    if friendly == selFriendly:
                        SetMemoryString(IMWTT_PageMode, code)
                        break
            except:
                pass

        cmbMode.addActionListener(lambda e: ApplyPageMode(e))

        rowMode.add(lblMode)
        rowMode.add(Box.createHorizontalStrut(8))
        rowMode.add(cmbMode)
        root.add(rowMode, gbc)

        cmbMode.addActionListener(lambda e: ApplyPageMode(e))
        rowMode.add(lblMode); rowMode.add(Box.createHorizontalStrut(8)); rowMode.add(cmbMode)
        root.add(rowMode, gbc)

        # (2) TIME_24H — checkbox
        gbc.gridy += 1
        row24 = Box.createHorizontalBox()
        chk24 = JCheckBox("Use 24-hour time")
        chk24.setOpaque(False)
        chk24.setSelected(GetMemoryBool(IMWTT_Time24, True))
        def ApplyTime24(e=None):
            SetMemoryBool(IMWTT_Time24, chk24.isSelected())
        chk24.addActionListener(ApplyTime24)
        row24.add(chk24)
        root.add(row24, gbc)

        # (3) TIME_SEPARATOR — single-character text field
        gbc.gridy += 1
        rowSep = Box.createHorizontalBox()
        lblSep = JLabel("Time separator (single character):")
        ApplyTheme(lblSep)
        txtSep = JTextField(2)
        sepVal = GetMemoryString(IMWTT_TimeSeparator, " ")
        if sepVal is None or len(sepVal.strip()) == 0: sepVal = " "
        txtSep.setText(sepVal[:1])
        def ApplySep():
            s = txtSep.getText().strip()
            if len(s) == 0: s = " "
            SetMemoryString(IMWTT_TimeSeparator, s[:1])
        txtSep.addActionListener(lambda e: ApplySep())
        class SepLost(FocusAdapter):
            def focusLost(self, e): ApplySep()
        txtSep.addFocusListener(SepLost())
        rowSep.add(lblSep); rowSep.add(Box.createHorizontalStrut(8)); rowSep.add(txtSep)
        root.add(rowSep, gbc)

        # (4) ECS_LABEL — single-line text field
        gbc.gridy += 1
        rowEcsLabel = Box.createHorizontalBox()
        lblEcs = JLabel("ECS label (text):")
        ApplyTheme(lblEcs)
        txtEcs = JTextField(12)
        txtEcs.setText(GetMemoryString(IMWTT_EcsLabel, "ECS"))
        def ApplyEcsLabel():
            SetMemoryString(IMWTT_EcsLabel, txtEcs.getText().strip())
        txtEcs.addActionListener(lambda e: ApplyEcsLabel())
        class EcsLost(FocusAdapter):
            def focusLost(self, e): ApplyEcsLabel()
        txtEcs.addFocusListener(EcsLost())
        rowEcsLabel.add(lblEcs); rowEcsLabel.add(Box.createHorizontalStrut(8)); rowEcsLabel.add(txtEcs)
        root.add(rowEcsLabel, gbc)

        # (5) _ECS_DEST_MATCH — multi-line tokens (one per line). Stored lowercased, comma-separated.
        gbc.gridy += 1
        rowEcsMatch = Box.createHorizontalBox()
        lblMatch = JLabel("ECS destination synonyms (one per line):")
        ApplyTheme(lblMatch)
        from javax.swing import JTextArea
        txtArea = JTextArea(4, 24)
        ApplyTheme(txtArea)
        txtArea.setLineWrap(True); txtArea.setWrapStyleWord(True)
        rawMatch = GetMemoryString(IMWTT_EcsMatch, "empty to depot,empty,ety.,ecs")
        preload = [t.strip() for t in rawMatch.split(",") if len(t.strip()) > 0]
        txtArea.setText("\n".join(preload))
        def ApplyEcsMatch():
            lines = txtArea.getText().split("\n")
            tokens = []
            for ln in lines:
                t = (ln or "").strip().lower()
                if len(t) > 0: tokens.append(t)
            SetMemoryString(IMWTT_EcsMatch, ",".join(tokens))
        class MatchLost(FocusAdapter):
            def focusLost(self, e): ApplyEcsMatch()
        txtArea.addFocusListener(MatchLost())
        sp = JScrollPane(txtArea)
        rowEcsMatch.add(lblMatch); rowEcsMatch.add(Box.createHorizontalStrut(8)); rowEcsMatch.add(sp)
        root.add(rowEcsMatch, gbc)

        # (6) DIRECTION_SPLIT — checkbox
        gbc.gridy += 1
        rowDir = Box.createHorizontalBox()
        chkDir = JCheckBox("Split pages by direction (e.g., DOWN / UP)")
        chkDir.setOpaque(False)
        chkDir.setSelected(GetMemoryBool(IMWTT_DirectionSplit, True))
        def ApplyDir(e=None):
            SetMemoryBool(IMWTT_DirectionSplit, chkDir.isSelected())
        chkDir.addActionListener(ApplyDir)
        rowDir.add(chkDir)
        root.add(rowDir, gbc)
                
        # (7) Origin/Destination header orientation — checkbox
        gbc.gridy += 1
        rowOdHdr = Box.createHorizontalBox()
        chkOdVertical = JCheckBox("Vertical headers")
        chkOdVertical.setOpaque(False)
        # Default is horizontal (false); reflect current memory setting
        chkOdVertical.setSelected(GetMemoryBool(IMWTT_OdHeaderVertical, False))
        def ApplyOdVertical(e=None):
            SetMemoryBool(IMWTT_OdHeaderVertical, chkOdVertical.isSelected())
        chkOdVertical.addActionListener(ApplyOdVertical)
        rowOdHdr.add(chkOdVertical)
        root.add(rowOdHdr, gbc)

        # Final spacer
        gbc.gridy += 1
        spacer = JLabel("")
        ApplyTheme(spacer)
        root.add(spacer, gbc)

        # Apply chosen font to the entire tab
        try:
            _ApplyFontRecursive(root, THEME_FONT_FAMILY)
        except:
            pass
        return root
    
    # --- Workings tab: list extracted workings, check for script, edit/save/revert ---   
    class WorkingItem(object):
        # Lightweight record: RN + Direction + RowIndex + ScriptPath + HasScript + ValidScript
        def __init__(self, rn, direction, rowIndex, scriptPath, hasScript, validScript, timeText=""):
            self.RN = rn
            self.Direction = direction
            self.RowIndex = rowIndex
            self.ScriptPath = scriptPath
            self.HasScript = hasScript
            self.ValidScript = validScript
            self.IsExtra = False
            self.Time = timeText
        def Label(self):
            # Example: "2G56 (Trigger) - row 42 [12:34]"
            timePart = (" [" + self.Time + "]") if self.Time else ""
            return "%s (%s) - row %d%s" % (self.RN, self.Direction, int(self.RowIndex), timePart)

    def BuildWorkingsTab(self):
        panel = MakePaperPanel()
        panel.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10,10,10,10)
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Left: JList of workings
        leftModel = DefaultListModel()
        leftList = JList(leftModel)
        leftList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        leftScroll = JScrollPane(leftList)
        leftScroll.setPreferredSize(Dimension(200, 420))

        # Custom renderer: bright red for missing script (appears mid-grey to red-blind viewers)
        class WorkingsRenderer(DefaultListCellRenderer):
            def getListCellRendererComponent(self, lst, value, index, isSelected, cellHasFocus):
                labelText = value.Label()
                comp = DefaultListCellRenderer.getListCellRendererComponent(
                    self, lst, labelText, index, isSelected, cellHasFocus
                )
                comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
                # Ghost workings: always grey, regardless of validity or selection
                if getattr(value, "IsExtra", False):
                    comp.setForeground(Color(128, 128, 128))
                elif not value.HasScript:
                    # Missing script: bright red
                    comp.setForeground(Color(255, 0, 0))
                elif not getattr(value, "ValidScript", True):
                    # Invalid script: orange
                    comp.setForeground(Color(255, 140, 0))
                else:
                    comp.setForeground(THEME_TEXT_COLOR)
                # Keep selection background but do NOT override the foreground for ghosts
                comp.setBackground(LIST_SEL_BG if isSelected else THEME_PAPER)
                comp.setOpaque(True)
                return comp
                
        leftList.setCellRenderer(WorkingsRenderer())

        # Right: placeholder panel we swap between editor and action buttons       
        rightPanel = JPanel()
        rightPanel.setOpaque(True)
        rightPanel.setBackground(THEME_PAPER)
        rightPanel.setLayout(GridBagLayout())
        # NOTE: no outer scroll here—editor has its own scroll pane; buttons remain fixed

        # Track editor state
        self.WorkingsDirty = False
        self.WorkingsCurrentItem = None
        self.WorkingsRightPanel = rightPanel      
        self.WorkingsSuppressDirty = False

        # Helpers ---------------------------------------------------------------

        def TimetablePath():
            # Reuse your memory-backed timetable file logic
            return _TimetableFilePath()
      
        
        def ValidateWorkingScriptReasons(path):
            # Return a list of specific validation failures for this script.
            # If list is empty, the script is valid.
            reasons = []

            try:
                if not (path and os.path.isfile(path)):
                    # Missing script is handled as red elsewhere; here we treat it invalid with a reason.
                    reasons.append("Script file not found.")
                    return reasons
                with open(path, "r") as f:
                    raw = f.read()
                lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            except Exception as ex:
                reasons.append("Error reading script: " + str(ex))
                return reasons

            def isIgnored(line):
                s = (line or "").strip()
                return (s == "" or s.startswith("#") or s.startswith("import ") or s.startswith("from "))

            # Index important lines (trimmed) — flexible header import
            importHeaderIdx = None  # any single "import ..." line whose comma list contains jmri and os
            importFileUtil = None
            scriptsPathLine = None
            execStartTrainLine = None
            execTrainFinderLine = None

            for idx, ln in enumerate(lines):
                s = ln.strip()

                # Flexible detection: "import jmri, os, random" (order-insensitive, extra tokens allowed)
                if importHeaderIdx is None and s.startswith("import "):
                    listStr = s[7:].strip()
                    tokens = [t.strip() for t in listStr.split(",") if t.strip() != ""]
                    baseNames = []
                    for t in tokens:
                        # Tolerate "jmri as x" (take the first word)
                        parts = t.split()
                        base = parts[0].strip().lower() if parts else ""
                        baseNames.append(base)
                    if ("jmri" in baseNames) and ("os" in baseNames):
                        importHeaderIdx = idx

                if importFileUtil is None and s == "from jmri.util import FileUtil":
                    importFileUtil = idx
                if scriptsPathLine is None and s == "scriptsPath = jmri.util.FileUtil.getScriptsPath()":
                    scriptsPathLine = idx
                if execStartTrainLine is None and s == "execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())":
                    execStartTrainLine = idx
                if execTrainFinderLine is None and s == "execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())":
                    execTrainFinderLine = idx

            # First non-ignored line (real code)
            firstReal = None
            for idx, ln in enumerate(lines):
                if not isIgnored(ln):
                    firstReal = idx
                    break

            # Header rules
            if importHeaderIdx is None:
                reasons.append("Missing header import list containing 'jmri' and 'os' (e.g., 'import jmri, os')")
            if importFileUtil is None:
                reasons.append("Missing header line: from jmri.util import FileUtil")

            if firstReal is not None:
                if importHeaderIdx is not None and not (importHeaderIdx < firstReal):
                    reasons.append("Header imports must appear before any real code (line with both 'jmri' and 'os')")
                if importFileUtil is not None and not (importFileUtil < firstReal):
                    reasons.append("Header imports must appear before any real code: 'from jmri.util import FileUtil'")

            # Loader lines presence
            if scriptsPathLine is None:
                reasons.append("Missing loader line: scriptsPath = jmri.util.FileUtil.getScriptsPath()")
            if execStartTrainLine is None:
                reasons.append("Missing loader line: execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())")

            # scriptsPath must be after imports (when imports present)         
            if scriptsPathLine is not None:
                if importHeaderIdx is not None and scriptsPathLine < importHeaderIdx:
                    reasons.append("scriptsPath must appear after the header import line containing 'jmri' and 'os'")
                if importFileUtil is not None and scriptsPathLine < importFileUtil:
                    reasons.append("scriptsPath must appear after the header imports: 'from jmri.util import FileUtil'")

            # trainFinder call must have a prior loader line
            firstTfCall = None
            for idx, ln in enumerate(lines):
                s = ln.strip()
                if s.startswith("#"):
                    continue
                if "trainFinder(" in s:
                    firstTfCall = idx
                    break
            if firstTfCall is not None:
                if execTrainFinderLine is None or not (execTrainFinderLine < firstTfCall):
                    reasons.append("trainFinder( call found without prior execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())")

            # startTrain(...) must occur after the startTrain loader
            startTrainCallAfter = False
            if execStartTrainLine is not None:
                for idx, ln in enumerate(lines):
                    s = ln.strip()
                    if s.startswith("#"):
                        continue
                    if "startTrain(" in s and idx > execStartTrainLine:
                        startTrainCallAfter = True
                        break
            if execStartTrainLine is not None and not startTrainCallAfter:
                reasons.append("No startTrain( call after execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())")

            return reasons

        def ValidateWorkingScript(path):
            return len(ValidateWorkingScriptReasons(path)) == 0

            def isIgnored(line):
                s = (line or "").strip()
                return (s == "" or s.startswith("#") or s.startswith("import ") or s.startswith("from "))

            # Indices of important lines (exact matches, trimmed)
            importJmriOs = None
            importFileUtil = None
            scriptsPathLine = None
            execStartTrainLine = None
            execTrainFinderLine = None

            for idx, ln in enumerate(lines):
                s = ln.strip()
                if importJmriOs is None and s == "import jmri, os":
                    importJmriOs = idx
                if importFileUtil is None and s == "from jmri.util import FileUtil":
                    importFileUtil = idx
                if scriptsPathLine is None and s == "scriptsPath = jmri.util.FileUtil.getScriptsPath()":
                    scriptsPathLine = idx
                if execStartTrainLine is None and s == "execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())":
                    execStartTrainLine = idx
                if execTrainFinderLine is None and s == "execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())":
                    execTrainFinderLine = idx

            # First non-ignored line (must come after the two import lines)
            firstReal = None
            for idx, ln in enumerate(lines):
                if not isIgnored(ln):
                    firstReal = idx
                    break

            # Rule 1: two import lines must appear before any real code
            if firstReal is None:
                # No real code at all: still require the import lines to exist
                if importJmriOs is None or importFileUtil is None:
                    return False
            else:
                if importJmriOs is None or importFileUtil is None:
                    return False
                if not (importJmriOs < firstReal and importFileUtil < firstReal):
                    return False

            # Rule 2: scriptsPath line and exec startTrain.py line must exist (anywhere after imports)
            if scriptsPathLine is None or execStartTrainLine is None:
                return False
            if importJmriOs is not None and scriptsPathLine < importJmriOs:
                return False
            if importFileUtil is not None and scriptsPathLine < importFileUtil:
                return False

            # Rule 3: If there is a trainFinder( call (in a non-comment line), there must be a prior execfile(... 'trainFinder.py' ...)
            firstTfCall = None
            for idx, ln in enumerate(lines):
                s = ln.strip()
                if s.startswith("#"):
                    continue
                if "trainFinder(" in s:
                    firstTfCall = idx
                    break
            if firstTfCall is not None:
                if execTrainFinderLine is None or not (execTrainFinderLine < firstTfCall):
                    return False

            # Rule 4: There must be a call to startTrain(...) after the exec startTrain loader line (non-comment line)
            startTrainCallAfter = False
            for idx, ln in enumerate(lines):
                s = ln.strip()
                if s.startswith("#"):
                    continue
                if "startTrain(" in s and idx > execStartTrainLine:
                    startTrainCallAfter = True
                    break
            if not startTrainCallAfter:
                return False

            return True
        
        
        def ExtractWorkings():
            items = []
            path = TimetablePath()
            if path is None or not os.path.isfile(path):
                return items
            try:
                scriptsPath = jmri.util.FileUtil.getScriptsPath()
                # Read the timetable once
                with open(path, "r") as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    header = reader.fieldnames or []
                    hasTrigger = ("Trigger" in header)
                    hasArr = ("Arr" in header)
                    hasDep = ("Dep" in header)
                    rows = list(reader)

                # Build formation map: destination RN (normalized) -> forming RN (original case or TAS<row>)
                formedBy = {}
                for idx, r in enumerate(rows, start=2):
                    rnCell = (r.get("Reporting number", "") or "").strip()
                    formingRN = rnCell if rnCell != "" else _MakeDefaultRN(idx)
                    formsCell = (r.get("Forms", "") or "").strip()
                    if formsCell != "":
                        formedBy[_NormRN(formsCell)] = formingRN

                # Build the workings list, attaching FormsNext where applicable
                for rowIndex, row in enumerate(rows, start=2):
                    direction = None 
                    triggerPresent = hasTrigger and (row.get("Trigger", "") or "").strip() != ""
                    arrPresent = hasArr and (row.get("Arr", "") or "").strip() != ""
                    depPresent = hasDep and (row.get("Dep", "") or "").strip() != ""

                    # If trigger and dep present but no arr → treat as trigger-only
                    if triggerPresent:
                        direction = "Trigger"
                    elif arrPresent:
                        direction = "Arr"
                    elif depPresent:
                        direction = "Dep"
                    else:
                        # No time in Trigger/Arr/Dep -> cannot determine a script directory; skip
                        continue

                    rnCell = (row.get("Reporting number", "") or "").strip()
                    rn = rnCell if rnCell != "" else _MakeDefaultRN(rowIndex)
                    scriptPath = os.path.join(scriptsPath, "workings", direction, rn + ".py")
                    hasScript = os.path.isfile(scriptPath)
                    valid = ValidateWorkingScript(scriptPath) if hasScript else False
                    
                    # Determine time based on direction
                    timeText = ""
                    if direction == "Dep":
                        timeText = (row.get("Dep", "") or "").strip()
                    elif direction == "Arr":
                        timeText = (row.get("Arr", "") or "").strip()
                    elif direction == "Trigger":
                        timeText = (row.get("Trigger", "") or "").strip()

                    it = self.WorkingItem(rn, direction, rowIndex, scriptPath, hasScript, valid, timeText)

                    # If any timetable row says "Forms <this RN>", mark the forming RN
                    try:
                        normRN = _NormRN(rn)
                        if normRN in formedBy:
                            it.FormsNext = formedBy[normRN]
                    except Exception:
                        pass

                    items.append(it)

                return items
            except Exception as ex:
                LogWarn("Workings load failed: " + str(ex), alsoDialog=True)
                return []

        def RefreshLeftList():
            # Clear and repopulate
            leftModel.removeAllElements()
            for it in ExtractWorkings():
                leftModel.addElement(it)                   
            try:
                scriptsPath = jmri.util.FileUtil.getScriptsPath()
                timetableRNs = set([_NormRN(it.RN) for it in ExtractWorkings()])
                for direction in ["Trigger", "Arr", "Dep"]:
                    dirPath = os.path.join(scriptsPath, "workings", direction)
                    if not os.path.isdir(dirPath):
                        continue
                    for fname in os.listdir(dirPath):
                        if not fname.lower().endswith(".py"):
                            continue
                        rn = fname[:-3]  # strip .py
                        if _NormRN(rn) in timetableRNs:
                            continue
                        scriptPath = os.path.join(dirPath, fname)
                        reasons = ValidateWorkingScriptReasons(scriptPath)
                        if len(reasons) < 6:  # passes at least one check                          
                            valid = ValidateWorkingScript(scriptPath)
                            extraItem = self.WorkingItem(rn, direction, 0, scriptPath, True, valid)
                            extraItem.IsExtra = True
                            leftModel.addElement(extraItem)

            except Exception as ex:
                LogWarn("Extra script scan failed: " + str(ex), alsoDialog=False)
            
        # --- Simple text editor (AI could not cope with trying to make a proper Python editor with syntax highlighting)    
        class PyCodeEditor(JTextPane):
            def __init__(self):
                JTextPane.__init__(self)
                # Apply theme font only (no syntax styling)
                try:
                    ApplyTheme(self)
                    self.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
                except:
                    pass
                # Plain UI background (match general Swing UI, not the textured paper theme)
                try:
                    from javax.swing import UIManager
                    bg = UIManager.getColor("TextArea.background")
                    if bg is not None:
                        self.setBackground(bg)
                    else:
                        self.setBackground(Color(240, 240, 240))
                except:
                    self.setBackground(Color(240, 240, 240))
                self.setCaretColor(Color(40, 40, 40))
                self.setOpaque(True)
           
        
        def BuildEditorPane(item):
            # -- Create the editor and wrap in its own scroll pane --
            editor = PyCodeEditor()
            txtScroll = JScrollPane(editor)
            txtScroll.setVerticalScrollBarPolicy(JScrollPane.VERTICAL_SCROLLBAR_AS_NEEDED)
            txtScroll.setHorizontalScrollBarPolicy(JScrollPane.HORIZONTAL_SCROLLBAR_AS_NEEDED)
            # Match the general UI background (not the paper theme)
            try:
                from javax.swing import UIManager
                bg = UIManager.getColor("TextArea.background")
                if bg is not None:
                    txtScroll.getViewport().setBackground(bg)
            except:
                pass

            # Buttons
            btnSave = JButton("Save")
            btnRevert = JButton("Revert")
            btnDelete = JButton("Delete")
            
            # Dynamic explanation: appears only when the current item is invalid (orange)
            explain = MakeWrappedLabel("", widthPx=520, lineHeight=1.20, bold=False)
            explain.setVisible(False)
           
            def UpdateExplain():
                # Ghost workings: explain why they're grey even if valid
                if getattr(item, "IsExtra", False):
                    explain.setText(
                        "<html>This script is not linked to any entry in the current timetable.<br/>"
                        "It may belong to a different timetable or be kept for future use.</html>"
                    )
                    explain.setVisible(True)
                    return
                # Otherwise, show invalid reasons if any
                reasons = ValidateWorkingScriptReasons(item.ScriptPath)
                if len(reasons) > 0:
                    html = "<html>" + "<br/>".join(["* " + r for r in reasons]) + "</html>"
                    explain.setText(html)
                    explain.setVisible(True)
                else:
                    explain.setText("")
                    explain.setVisible(False)

            # -- Load the file (normalize line endings), without diagnostics --
            def LoadFromDisk():
                try:
                    with open(item.ScriptPath, "r") as f:
                        raw = f.read()
                    norm = raw.replace("\r\n", "\n").replace("\r", "\n")
                    # Suppress "dirty" while setting text programmatically
                    self.WorkingsSuppressDirty = True
                    editor.setText(norm)
                    editor.setCaretPosition(0)  # Ensure scroll starts at top
                    def _Post():
                        self.WorkingsSuppressDirty = False
                        self.WorkingsDirty = False                     
                        item.ValidScript = ValidateWorkingScript(item.ScriptPath)  # sync validity with what's on disk
                        leftList.repaint()
                        UpdateExplain()
                    SwingUtilities.invokeLater(RunnableAdapter(_Post))
                except Exception as ex:
                    LogWarn("Failed to load working script: " + str(ex), alsoDialog=True)

            # -- Save handler --           
            def DoSave(e=None):
                try:
                    parentDir = os.path.dirname(item.ScriptPath)
                    if not os.path.isdir(parentDir):
                        os.makedirs(parentDir)
                    with open(item.ScriptPath, "w") as f:
                        f.write(editor.getText())
                    self.WorkingsDirty = False
                    item.HasScript = True
                    item.ValidScript = ValidateWorkingScript(item.ScriptPath)
                    UpdateExplain()
                    leftList.repaint()
                    # No modal dialog on save—console log only
                    LogInfo("Saved " + item.ScriptPath, alsoDialog=False, title="Saved")
                except Exception as ex:
                    # Keep the error dialog for failures
                    LogError("Save failed: " + str(ex), ex=ex, alsoDialog=True)

            # -- Revert handler --
            def DoRevert(e=None):
                if self.WorkingsDirty:
                    choice = JOptionPane.showConfirmDialog(
                        self.WorkingsRightPanel,
                        "Discard unsaved changes and reload from file?",
                        "Confirm revert",
                        JOptionPane.OK_CANCEL_OPTION,
                        JOptionPane.WARNING_MESSAGE
                    )
                    if choice != JOptionPane.OK_OPTION:
                        return
                LoadFromDisk()

            # -- Delete handler (with confirmation) --     
            def DoDelete(e=None):
                choice = JOptionPane.showConfirmDialog(
                    self.WorkingsRightPanel,
                    "Delete this working script file?\nThis action cannot be undone.",
                    "Confirm delete",
                    JOptionPane.OK_CANCEL_OPTION,
                    JOptionPane.WARNING_MESSAGE
                )
                if choice != JOptionPane.OK_OPTION:
                    return
                try:
                    if os.path.isfile(item.ScriptPath):
                        os.remove(item.ScriptPath)
                    # Update state
                    self.WorkingsDirty = False
                    item.HasScript = False
                    item.ValidScript = False
                    # If this is a ghost working, remove it from the list model
                    if getattr(item, "IsExtra", False):
                        leftModel.removeElement(item)
                    else:
                        # For timetable-linked items, switch to action pane
                        BuildActionPane(item)
                    leftList.repaint()
                    LogInfo("Deleted " + item.ScriptPath, alsoDialog=False, title="Deleted")
                except Exception as ex:
                    LogError("Delete failed: " + str(ex), ex=ex, alsoDialog=True)

            # -- Dirty only for user edits (style changes don't mark dirty) --
            class DirtyHook(DocumentListener):
                def insertUpdate(innerSelf, e):
                    if getattr(self, "WorkingsSuppressDirty", False): return
                    self.WorkingsDirty = True
                def removeUpdate(innerSelf, e):
                    if getattr(self, "WorkingsSuppressDirty", False): return
                    self.WorkingsDirty = True
                def changedUpdate(innerSelf, e):
                    # No syntax styling; but if the LAF sets attributes, ignore them
                    return
            editor.getDocument().addDocumentListener(DirtyHook())
         
            # -- Layout on the right panel --
            rpG = GridBagConstraints()
            rpG.insets = Insets(6, 6, 6, 6)
            rpG.gridx = 0

            self.WorkingsRightPanel.removeAll()

            # Row 0: dynamic explanation (visible only when invalid)
            rpG.gridy = 0
            rpG.fill = GridBagConstraints.HORIZONTAL
            rpG.weightx = 1.0
            rpG.weighty = 0.0
            self.WorkingsRightPanel.add(explain, rpG)

            # Row 1: editor scroll pane
            rpG.gridy = 1
            rpG.fill = GridBagConstraints.BOTH
            rpG.weightx = 1.0
            rpG.weighty = 1.0
            self.WorkingsRightPanel.add(txtScroll, rpG)

            # Row 2: buttons
            rpG.gridy = 2
            rpG.fill = GridBagConstraints.NONE
            rpG.weightx = 0.0
            rpG.weighty = 0.0     
            btnRow = Box.createHorizontalBox()
            btnRow.add(btnSave)
            btnRow.add(Box.createHorizontalStrut(8))
            btnRow.add(btnRevert)
            btnRow.add(Box.createHorizontalStrut(8))
            btnRow.add(btnDelete)
            self.WorkingsRightPanel.add(btnRow, rpG)

            # Wire the buttons
            btnSave.addActionListener(lambda e: DoSave())
            btnRevert.addActionListener(lambda e: DoRevert())
            btnDelete.addActionListener(lambda e: DoDelete())

            self.WorkingsRightPanel.revalidate()
            self.WorkingsRightPanel.repaint()

            # Initial load after UI is in place (then update explanation)
            LoadFromDisk()
            UpdateExplain()

        def BuildActionPane(item):
            # No script exists: show "New empty script" and "Create working..."
            btnNew = JButton("New empty script")
            btnCreate = JButton("Create working...")

            def DoNew(e=None):
                try:
                    parentDir = os.path.dirname(item.ScriptPath)
                    if not os.path.isdir(parentDir):
                        os.makedirs(parentDir)
                    # Create blank file with the basic elements      
                    with open(item.ScriptPath, "w") as f:
                        f.write(
                            "# Working script for reporting number %s (%s)\n"
                            "import jmri, os\n"
                            "from jmri.util import FileUtil\n"
                            "\n"
                            "# Get the scripts path and load the scripts\n"
                            "scriptsPath = jmri.util.FileUtil.getScriptsPath()\n"
                            "execfile(os.path.join(scriptsPath, 'trainFinder.py'), globals())\n"
                            "execfile(os.path.join(scriptsPath, 'startTrain.py'), globals())\n"
                            "\n"
                            "# TODO: add your logic here, e.g. startTrain(traininfoName, rosterEntry, reportingNumber, direction)\n"
                            % (item.RN, item.Direction)
                        )                  
                    item.HasScript = True
                    item.ValidScript = ValidateWorkingScript(item.ScriptPath)  # run validator now
                    BuildEditorPane(item)
                    leftList.repaint()

                except Exception as ex:
                    LogError("Failed to create blank working script: " + str(ex), ex=ex, alsoDialog=True)

            def DoCreate(e=None):
                try:
                    # Look in profile's Jython folder for WorkingCreator.py
                    wcPath = ProfileJythonFilePath("WorkingCreator.py")
                    if os.path.isfile(wcPath):
                        try:
                            import imp
                            mod = imp.load_source("WorkingCreator", wcPath)
                            # Pass RN, Direction, RowIndex, and formsNext (if available)
                            # formsNext should come from the timetable row; if not yet extracted, use None
                            mod.ShowWorkingCreator(item.RN, item.Direction, item.RowIndex, item.FormsNext if hasattr(item, "FormsNext") else None)
                            
                            # Refresh the workings list so newly saved script appears immediately
                            RefreshLeftList()
                            # Try to reselect the same RN/direction row and swap to editor if script now exists
                            try:
                                count = leftModel.getSize()
                                targetIndex = -1
                                for i in range(count):
                                    it2 = leftModel.getElementAt(i)
                                    if it2.RN == item.RN and it2.Direction == item.Direction and int(it2.RowIndex) == int(item.RowIndex):
                                        targetIndex = i
                                        break
                                if targetIndex >= 0:
                                    leftList.setSelectedIndex(targetIndex)
                                    self.WorkingsCurrentItem = leftModel.getElementAt(targetIndex)
                                    if self.WorkingsCurrentItem.HasScript:
                                        BuildEditorPane(self.WorkingsCurrentItem)
                                    else:
                                        BuildActionPane(self.WorkingsCurrentItem)
                            except Exception:
                                pass

                        except Exception as exInner:
                            LogError("WorkingCreator.py error: " + str(exInner), ex=exInner, alsoDialog=True)
                    else:
                        JOptionPane.showMessageDialog(
                            panel,
                            "WorkingCreator.py not found",
                            "Error",
                            JOptionPane.ERROR_MESSAGE
                        )
                except Exception as ex:
                    LogError("Create working failed: " + str(ex), ex=ex, alsoDialog=True)

            btnNew.addActionListener(lambda e: DoNew())
            btnCreate.addActionListener(lambda e: DoCreate())

            # Layout
            rpG = GridBagConstraints()
            rpG.insets = Insets(6,6,6,6)
            rpG.fill = GridBagConstraints.NONE
            rpG.weightx = 0.0
            rpG.weighty = 0.0
            rpG.gridx = 0
            rpG.gridy = 0

            self.WorkingsRightPanel.removeAll()
            row = Box.createVerticalBox()
            row.add(btnNew)
            row.add(Box.createVerticalStrut(8))
            row.add(btnCreate)
            self.WorkingsRightPanel.add(row, rpG)
            self.WorkingsRightPanel.revalidate()
            self.WorkingsRightPanel.repaint()

        # Selection change: confirm if dirty, then swap right pane
        class LeftSelHook(ListSelectionListener):
            def valueChanged(innerSelf, e):
                if e.getValueIsAdjusting():
                    return
                newItem = leftList.getSelectedValue()
                if newItem is None:
                    return
                if self.WorkingsDirty and self.WorkingsCurrentItem is not None:
                    choice = JOptionPane.showConfirmDialog(
                        panel,
                        "You have unsaved changes. Discard and switch to another working?",
                        "Unsaved changes",
                        JOptionPane.OK_CANCEL_OPTION,
                        JOptionPane.WARNING_MESSAGE
                    )
                    if choice != JOptionPane.OK_OPTION:
                        # Restore previous selection
                        try:
                            idx = leftModel.indexOf(self.WorkingsCurrentItem)
                            if idx >= 0: leftList.setSelectedIndex(idx)
                        except Exception:
                            pass
                        return
                    # Discard dirty flag on confirmed switch
                    self.WorkingsDirty = False
                self.WorkingsCurrentItem = newItem
                if newItem.HasScript:
                    BuildEditorPane(newItem)
                else:
                    BuildActionPane(newItem)
        leftList.addListSelectionListener(LeftSelHook())     
        
        # Header spanning both columns; do not let it consume vertical space
        hdr = MakeHeading("Workings (from current timetable)")
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.gridwidth = 2
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.weighty = 0.0
        panel.add(hdr, gbc)
        
        # Row with left list and right editor; this row gets the vertical weight
        gbc.gridy += 1
        gbc.gridwidth = 1
        gbc.fill = GridBagConstraints.BOTH
        gbc.weighty = 1.0

        # Left column: make it lighter horizontally
        gbc.weightx = 0.40
        gbc.gridx = 0
        panel.add(leftScroll, gbc)

        # Right column: give it more horizontal room
        gbc.weightx = 0.60
        gbc.gridx = 1
        panel.add(rightPanel, gbc)

        # Populate left list
        RefreshLeftList()
        return panel
    
    def BuildTimingPointsTab(self):
        # "Timing points" tab — dual list: left = virtual TPs from timetable,
        # right = physical TPs (blocks assigned via TimingRegister).
        import TimingRegister as TR
        from jmri import InstanceManager
        from jmri import BlockManager

        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10, 10, 10, 10)
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # --- Helpers ---
        def _CurrentTimetablePath():
            try:
                name = GetMemoryString(IMCurrentTimetable, "").strip()
                if name == "":
                    return None
                prof = jmri.profile.ProfileManager.getDefault().getActiveProfile().getPath().toString()
                return os.path.join(prof, "timetable", name + ".csv")
            except Exception:
                return None

        def _ExtractVirtualTPNamesFromTimetable():
            path = _CurrentTimetablePath()
            out = set()
            if not (path and os.path.exists(path)):
                return []
            try:
                with open(path, "r") as f:
                    reader = csv.DictReader(f, delimiter="\t")
                    headers = reader.fieldnames or []   
                    # Match "TPArr <name>" or "TPDep <name>" (case-insensitive), tolerate extra spaces
                    pat = re.compile(r'^TP(?:Arr|Dep)\s+(.+)$', re.IGNORECASE)
                    for h in headers:
                        if not h:
                            continue
                        m = pat.match(str(h).strip())
                        if m:
                            nm = (m.group(1) or "").strip()
                            if nm != "":
                                out.add(nm)
            except Exception as ex:
                LogWarn("Could not read timetable header for timing points: " + str(ex), alsoDialog=False)
            return sorted(list(out), key=lambda s: s.lower())

        def _ListPhysicalTPs():
            names = []
            try:
                for tp in TR.listTimingPoints() or []:
                    try:
                        blocks = TR.getBlocks(tp)
                        if isinstance(blocks, list) and len(blocks) > 0:
                            names.append(tp)
                    except Exception:
                        pass
            except Exception as ex:
                LogWarn("Could not list physical timing points: " + str(ex), alsoDialog=False)
            return sorted(names, key=lambda s: s.lower())

        def _AllBlocks():
            items = []
            try:
                bm = InstanceManager.getDefault(BlockManager)
                if bm is None:
                    return items
                try:
                    beans = bm.getNamedBeanSet()
                    seq = beans.toArray() if hasattr(beans, "toArray") else list(beans)
                except Exception:
                    seq = []
                for b in seq:
                    try:
                        sys = str(b.getSystemName())
                    except Exception:
                        sys = None
                    if not sys:
                        continue
                    try:
                        usr = b.getUserName()
                        lbl = (str(usr).strip() + " (" + sys + ")") if usr else sys
                    except Exception:
                        lbl = sys
                    items.append((sys, lbl))
            except Exception as ex:
                LogWarn("Could not enumerate blocks: " + str(ex), alsoDialog=False)
            items.sort(key=lambda t: t[1].lower())
            return items

        # --- List models & views ---
        virtModel = DefaultListModel()
        physModel = DefaultListModel()     
        
        def RefreshLists():
            # Refresh both list models, ensuring the virtual list excludes any TP
            # that is present in the physical list (case-insensitive).
            try:
                vnames = _ExtractVirtualTPNamesFromTimetable()
            except Exception:
                vnames = []
            try:
                pnames = _ListPhysicalTPs()
            except Exception:
                pnames = []

            # Case-insensitive physical set for filtering
            psetLower = set([str(p).strip().lower() for p in (pnames or [])])

            # Left list (virtual): show only names not already physical
            try:
                virtModel.removeAllElements()
                for nm in vnames:
                    if str(nm).strip().lower() not in psetLower:
                        virtModel.addElement(nm)
            except Exception:
                pass

            # Right list (physical): unchanged
            try:
                physModel.removeAllElements()
                for nm in pnames:
                    physModel.addElement(nm)
            except Exception:
                pass

            # Build a case-insensitive set of physical names for filtering
            psetLower = set([str(p).strip().lower() for p in (pnames or [])])

            # --- Left list (virtual): vnames minus pnames (case-insensitive)


        virtList = JList(virtModel)
        virtList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        virtScroll = JScrollPane(virtList)
        virtScroll.setPreferredSize(Dimension(300, 240))

        physList = JList(physModel)
        physList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        physScroll = JScrollPane(physList)
        physScroll.setPreferredSize(Dimension(300, 240))
             
        # Two separate header labels for proper column alignment
        lblLeft = JLabel("Virtual timing points (from current timetable)")
        lblRight = JLabel("Physical timing points (blocks assigned in register)")
        ApplyTheme(lblLeft)
        ApplyTheme(lblRight)

        # Left header in column 0, row 0
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.gridwidth = 1
        gbc.anchor = GridBagConstraints.WEST
        root.add(lblLeft, gbc)

        # Right header in column 1, row 0
        gbc.gridx = 1
        gbc.gridy = 0
        gbc.gridwidth = 1
        gbc.anchor = GridBagConstraints.WEST
        root.add(lblRight, gbc)
       
        # Reset constraints for the scroll panes (row 1)
        gbc.gridy += 1
        gbc.gridx = 0
        gbc.gridwidth = 1
        gbc.anchor = GridBagConstraints.CENTER  # ensure list panes aren't stuck to WEST from header
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        root.add(virtScroll, gbc)

        # Right list in column 1
        gbc.gridx = 1
        root.add(physScroll, gbc)


        # --- Block picker dialog ---
        def ShowBlockPicker(tpName, preselectedSysNames):
            dlg = JDialog(self, "Assign blocks to '" + str(tpName) + "'", True)
            dlg.setSize(480, 420)
            dlg.setLayout(BorderLayout())

            items = _AllBlocks()  # [(sysName, label), ...]
            blocksModel = DefaultListModel()
            for _, label in items:
                blocksModel.addElement(label)

            lstBlocks = JList(blocksModel)
            lstBlocks.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
            try:
                idxs = []
                preSet = set([str(x).strip() for x in (preselectedSysNames or [])])
                for i, (sys, _) in enumerate(items):
                    if sys in preSet:
                        idxs.append(i)
                if idxs:
                    lstBlocks.setSelectedIndices([j for j in idxs])
            except Exception:
                pass

            dlg.add(JScrollPane(lstBlocks), BorderLayout.CENTER)

            btnPanel = Box.createHorizontalBox()
            btnAssign = JButton("Assign")
            btnCancel = JButton("Cancel")
            btnPanel.add(btnAssign)
            btnPanel.add(Box.createHorizontalStrut(12))
            btnPanel.add(btnCancel)
            dlg.add(btnPanel, BorderLayout.SOUTH)
            ApplyTheme(lstBlocks); ApplyTheme(btnPanel); ApplyTheme(btnAssign); ApplyTheme(btnCancel)

            def DoAssign(e=None):
                try:
                    selIdx = lstBlocks.getSelectedIndices() or []
                    chosen = []
                    for k in selIdx:
                        try:
                            sysName = items[int(k)][0]
                            chosen.append(sysName)
                        except Exception:
                            pass
                    TR.assignBlocks(tpName, chosen)
                    TR.save()
                    RefreshLists()
                    dlg.dispose()
                except Exception as ex:
                    LogError("Failed to assign blocks: " + str(ex), ex=ex, alsoDialog=True)

            btnAssign.addActionListener(lambda e: DoAssign())
            btnCancel.addActionListener(lambda e: dlg.dispose())
            dlg.setLocationRelativeTo(self)
            dlg.setVisible(True)

        # --- Buttons row ---
        gbc.gridx = 0; gbc.gridy += 1; gbc.weightx = 1.0; gbc.weighty = 0.0; gbc.fill = GridBagConstraints.NONE
        leftBtns = Box.createHorizontalBox()
        btnAssignBlocks = JButton("Assign blocks")
        leftBtns.add(btnAssignBlocks)
        root.add(leftBtns, gbc)

        gbc.gridx = 1
        rightBtns = Box.createHorizontalBox()
        btnEditBlocks = JButton("Edit blocks")
        btnDeleteBlocks = JButton("Delete all blocks")
        rightBtns.add(btnEditBlocks)
        rightBtns.add(Box.createHorizontalStrut(12))
        rightBtns.add(btnDeleteBlocks)
        root.add(rightBtns, gbc)
        ApplyTheme(btnAssignBlocks); ApplyTheme(btnEditBlocks); ApplyTheme(btnDeleteBlocks)

        def DoAssignBlocks(e=None):
            tp = virtList.getSelectedValue()
            if tp is None:
                LogWarn("Select a virtual timing point first.", alsoDialog=True)
                return
            pre = TR.getBlocks(str(tp)) or []
            ShowBlockPicker(str(tp), pre)

        def DoEditBlocks(e=None):
            tp = physList.getSelectedValue()
            if tp is None:
                LogWarn("Select a physical timing point first.", alsoDialog=True)
                return
            pre = TR.getBlocks(str(tp)) or []
            ShowBlockPicker(str(tp), pre)

        def DoDeleteBlocks(e=None):
            tp = physList.getSelectedValue()
            if tp is None:
                LogWarn("Select a physical timing point first.", alsoDialog=True)
                return
            msg = ("This will delete all block assignments stored for timing point '{}'.\n"
                   "The timing point itself is kept; only its physical bindings are removed.\n"
                   "This action cannot be undone.\n\nProceed?").format(str(tp))
            choice = JOptionPane.showConfirmDialog(
                self, msg, "Confirm delete (blocks)", JOptionPane.OK_CANCEL_OPTION, JOptionPane.WARNING_MESSAGE
            )
            if choice != JOptionPane.OK_OPTION:
                return
            try:
                TR.clearBlocks(str(tp))
                TR.save()
                RefreshLists()
                LogInfo("[TAS] Cleared blocks for timing point '" + str(tp) + "'.", alsoDialog=True, title="Done")
            except Exception as ex:
                LogError("Failed to clear blocks: " + str(ex), ex=ex, alsoDialog=True)

        btnAssignBlocks.addActionListener(lambda e: DoAssignBlocks())
        btnEditBlocks.addActionListener(lambda e: DoEditBlocks())
        btnDeleteBlocks.addActionListener(lambda e: DoDeleteBlocks())

        RefreshLists()
        return root
    
    def BuildOrientationTab(self):
        import OrientationRegister as OR       
        from jmri import InstanceManager
        from jmri.jmrit.roster import Roster  
        
        # Color renderer needs access to the two direction registers used by the hardware UI
        try:
            import NormalDirectionRegister as NDR
        except Exception:
            NDR = None
        try:
            import LastReportedDirection as LRD
        except Exception:
            LRD = None
      
        panel = MakePaperPanel()
        panel.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(8, 8, 8, 8)
        gbc.fill = GridBagConstraints.BOTH
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        gbc.gridx = 0
        gbc.gridy = 0

        # Heading
        panel.add(
            MakeWrappedLabel(
                "All of the Train Info files that define what happens when we run a working "
                "assume that a train is in a particular orientation. "
                "If a train is in the opposite orientation on the layout, it will go the wrong way. "
                "To correct that, this is a list of all the trains that are facing the opposite way to the "
                "orientation expected by the Train Info files. "
                "Trains on this list will run in the correct direction if they are in inverse orientation.",
                widthPx=560,    # tweak to taste; matches your tab width
                lineHeight=1.25 # tighter than default; adjust 1.2–1.3 as desired
            ),
            gbc
)
        # Hardware orientation sensing controls
        # Row 1: checkbox
        rowSenseTop = Box.createHorizontalBox()
        self.ChkDirSense = JCheckBox("Enable hardware orientation sensing*")
        self.ChkDirSense.setOpaque(False)

        initialEnabled = _IsScriptEnabled("LastReportedDirection.py")
        self.ChkDirSense.setSelected(initialEnabled)

        def OnDirSense(e=None):
            want = self.ChkDirSense.isSelected()
            ok = _EnsureScriptEnabled("LastReportedDirection.py", want)
            actual = _IsScriptEnabled("LastReportedDirection.py")
            self.ChkDirSense.setSelected(actual)
            try:
                self.BtnDirSenseConfig.setEnabled(actual)
            except Exception:
                pass
            self.CurrentDirectionSensing = actual
            if not ok:
                LogWarn("Could not change Start-Up for LastReportedDirection.py", alsoDialog=True)

        self.ChkDirSense.addActionListener(OnDirSense)
        rowSenseTop.add(self.ChkDirSense)

        # Row 2: note
        self.LblDirSenseNote = MakeWrappedLabel(
            "*Requires compatible hardware. See under Help for details.",
            widthPx=560, lineHeight=1.20, bold=False
        )

        # Row 3: button
        rowSenseCfg = Box.createHorizontalBox()
        self.BtnDirSenseConfig = JButton("Configure hardware orientation sensing...")
        self.BtnDirSenseConfig.setEnabled(initialEnabled)

        def DoDirSenseConfig(e=None):
            try:
                path = ProfileJythonFilePath("HardwareDirectionConfig.py")
                if os.path.isfile(path):
                    execfile(path, {})
                else:
                    JOptionPane.showMessageDialog(
                        panel,
                        "No configuration script found.\nCreate: profile:jython/HardwareDirectionConfig.py",
                        "Configuration",
                        JOptionPane.INFORMATION_MESSAGE
                    )
            except Exception as ex:
                LogError("Hardware orientation sensing configuration failed: " + str(ex),
                         ex=ex, alsoDialog=True)

        self.BtnDirSenseConfig.addActionListener(lambda e: DoDirSenseConfig())
        rowSenseCfg.add(self.BtnDirSenseConfig)

        # Stack the three rows tightly in a single subpanel
        dirSensePanel = JPanel()
        dirSensePanel.setOpaque(False)
        dirSensePanel.setLayout(GridBagLayout())

        dg = GridBagConstraints()
        dg.insets = Insets(0, 0, 0, 0)
        dg.gridx = 0
        dg.gridy = 0
        dg.fill = GridBagConstraints.HORIZONTAL
        dg.weightx = 1.0
        dg.weighty = 0.0
        dirSensePanel.add(rowSenseTop, dg)

        dg.gridy = 1
        dirSensePanel.add(self.LblDirSenseNote, dg)

        dg.gridy = 2
        dirSensePanel.add(rowSenseCfg, dg)

        # Add the subpanel as one compact block
        gbc.gridy += 1
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weighty = 0.0
        panel.add(dirSensePanel, gbc)

        # Error label for missing orientation-sensing script
        gbc.gridy += 1
        self.LblDirSenseError = JLabel("")
        ApplyTheme(self.LblDirSenseError)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weighty = 0.0
        panel.add(self.LblDirSenseError, gbc)

        # If missing, disable controls and show an error
        if not ScriptExists("LastReportedDirection.py"):
            try:
                self.ChkDirSense.setSelected(False)
                self.ChkDirSense.setEnabled(False)
                self.BtnDirSenseConfig.setEnabled(False)
                self.LblDirSenseError.setText("Missing script: LastReportedDirection.py")
            except Exception:
                pass


        # Two lists: left = normal direction (not inverted), right = inverted direction (in register)
        gbc.gridy += 1
        leftModel = DefaultListModel()
        rightModel = DefaultListModel()

        # Load roster and split into left/right
        try:
            import jmri.jmrit.roster as JR
            roster = JR.Roster.getDefault()
            allIDs = []
            if roster is not None:
                entries = roster.matchingList(None, None, None, None, None, None, None)
                for re in entries.toArray():
                    allIDs.append(re.getId())
            invertedSet = set(OR.GetOrientationRegisterCopy())
            for rid in allIDs:
                if rid in invertedSet:
                    rightModel.addElement(rid)
                else:
                    leftModel.addElement(rid)
        except Exception as ex:
            LogWarn("Roster unavailable or failed: " + str(ex), alsoDialog=True)

        # Lists
        leftList = JList(leftModel)
        rightList = JList(rightModel)
        leftList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        rightList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)      
        
        # Apply same text colors as HardwareDirectionConfig:
        #   - cyan: in LastReportedDirection only
        #   - dark blue: in both NormalDirectionRegister and LastReportedDirection
        #   - dark purple: in NormalDirectionRegister only      
        from javax.swing import DefaultListCellRenderer

        class OrientationColorRenderer(DefaultListCellRenderer):
            def __init__(self):
                DefaultListCellRenderer.__init__(self)

                # Helper: normalize roster IDs
                def _Norm(s):
                    try:
                        return str(s).strip().lower()
                    except:
                        return ""

                # Snapshot normal register keys (case-insensitive)
                try:
                    self.normalKeys = set([_Norm(k) for k in (NDR.GetCopy().keys() if NDR else [])])
                except Exception:
                    self.normalKeys = set()

                # Build roster address index: lower(rid) -> addr, addr -> [display RIDs]
                self.ridLowerToAddr = {}
                self.addrToRidList = {}
                try:
                    roster = jmri.jmrit.roster.Roster.getDefault()
                    if roster is not None:
                        entries = roster.matchingList(None, None, None, None, None, None, None)
                        seq = entries.toArray() if hasattr(entries, "toArray") else list(entries)
                        for re in seq:
                            try:
                                rid = str(re.getId())
                                addr = str(re.getDccAddress()) if hasattr(re, "getDccAddress") else ""
                                if addr is None or addr.strip() == "":
                                    addr = ""
                                lrid = _Norm(rid)
                                if lrid != "":
                                    self.ridLowerToAddr[lrid] = addr
                                    lst = self.addrToRidList.get(addr, [])
                                    lst.append(rid)
                                    self.addrToRidList[addr] = lst
                            except Exception:
                                pass
                except Exception:
                    pass

                # Expand last-reported set to include ALL roster IDs that share the same DCC address
                self.lastKeys = set()
                try:
                    lm = getattr(LRD, "lastReportedDirection", {})
                    for k in (lm.keys() if lm else []):
                        lk = _Norm(k)
                        if lk == "":
                            continue
                        addr = self.ridLowerToAddr.get(lk, None)
                        if addr is None:
                            # Address unknown: include the original key only
                            self.lastKeys.add(lk)
                            continue
                        siblings = self.addrToRidList.get(addr, []) or []
                        for rid in siblings:
                            self.lastKeys.add(_Norm(rid))
                except Exception:
                    # Fallback to raw keys if anything goes wrong
                    try:
                        lm = getattr(LRD, "lastReportedDirection", {})
                        for k in (lm.keys() if lm else []):
                            self.lastKeys.add(_Norm(k))
                    except Exception:
                        pass

                # Palette (match HardwareDirectionConfig)
                self.cyan = Color(0, 200, 200)
                self.darkBlue = Color(0, 51, 102)
                self.darkPurple = Color(76, 0, 153)

            def getListCellRendererComponent(self, lst, value, index, isSelected, cellHasFocus):
                comp = DefaultListCellRenderer.getListCellRendererComponent(
                    self, lst, value, index, isSelected, cellHasFocus
                )
                try:
                    rid = str(value)
                    lower = rid.strip().lower()
                    inNormal = lower in self.normalKeys
                    inLast = lower in self.lastKeys

                    if inLast and not inNormal:
                        fg = self.cyan          # last-only -> cyan
                    elif inNormal and inLast:
                        fg = self.darkBlue      # both -> dark blue
                    elif inNormal and not inLast:
                        fg = self.darkPurple    # normal-only -> dark purple
                    else:
                        fg = comp.getForeground()

                    comp.setForeground(fg)

                    # Keep TASSetup theme: paper selection/background and font
                    try:
                        comp.setBackground(LIST_SEL_BG if isSelected else THEME_PAPER)
                        comp.setOpaque(True)
                    except Exception:
                        pass
                    try:
                        comp.setFont(Font(THEME_FONT_FAMILY, Font.PLAIN, 13))
                    except Exception:
                        pass
                except Exception:
                    pass
                return comp

        # Use the colored renderer for both lists
        try:
            _renderer = OrientationColorRenderer()
            leftList.setCellRenderer(_renderer)
            rightList.setCellRenderer(_renderer)
        except Exception:
            pass


        # Move buttons (ASCII-only)
        btnMoveRight = JButton(">>")
        btnMoveLeft  = JButton("<<")
              
        # Attach listeners for buttons
        btnMoveRight.addActionListener(lambda e: DoMoveRight())
        btnMoveLeft.addActionListener(lambda e: DoMoveLeft())
        
        
        # Refresh button: rebuild both lists from current registers
        btnRefresh = JButton("Refresh")
        def DoRefresh(e=None):
            try:
                # Reload roster and orientation register
                import OrientationRegister as ORlocal
                from jmri.jmrit.roster import Roster
                roster = Roster.getDefault()
                allIDs = []
                if roster is not None:
                    entries = roster.matchingList(None, None, None, None, None, None, None)
                    seq = entries.toArray() if hasattr(entries, "toArray") else list(entries)
                    for re in seq:
                        try:
                            allIDs.append(str(re.getId()))
                        except Exception:
                            pass

                invertedSet = set(ORlocal.GetOrientationRegisterCopy() if hasattr(ORlocal, "GetOrientationRegisterCopy") else [])

                # Clear models
                leftModel.removeAllElements()
                rightModel.removeAllElements()

                # Repopulate
                for rid in allIDs:
                    if rid in invertedSet:
                        rightModel.addElement(rid)
                    else:
                        leftModel.addElement(rid)

                # Reapply color renderer
                try:
                    _renderer2 = OrientationColorRenderer()
                    leftList.setCellRenderer(_renderer2)
                    rightList.setCellRenderer(_renderer2)
                    leftList.repaint()
                    rightList.repaint()
                except Exception:
                    pass

                LogInfo("[TASSetup] Orientation lists refreshed.")
            except Exception as ex:
                LogError("Failed to refresh orientation lists: " + str(ex), ex=ex, alsoDialog=True)

        btnRefresh.addActionListener(lambda e: DoRefresh())


        def DoMoveRight(e=None):
            idx = leftList.getSelectedIndex()
            if idx < 0: return
            rid = leftModel.getElementAt(idx)
            try:
                leftModel.remove(idx)
                rightModel.addElement(rid)
                OR.AddTrain(rid)
                OR.save()
                LogInfo("[TASSetup] Orientation: added " + str(rid))
            except Exception as ex:
                LogError("Failed to add to orientation register: " + str(ex), ex=ex, alsoDialog=True)

        def DoMoveLeft(e=None):
            idx = rightList.getSelectedIndex()
            if idx < 0: return
            rid = rightModel.getElementAt(idx)
            try:
                rightModel.remove(idx)
                leftModel.addElement(rid)
                OR.RemoveTrain(rid)
                OR.save()
                LogInfo("[TASSetup] Orientation: removed " + str(rid))
            except Exception as ex:
                LogError("Failed to remove from orientation register: " + str(ex), ex=ex, alsoDialog=True)

        # Layout with headings and equal-width columns (matching Display configuration pattern)        
        
        
        # Row: lists with equal widths and buttons in the middle
        gbc.gridy += 1
        gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH

        # Create a sub-panel with GridLayout to enforce equal column widths
        listsPanel = JPanel(GridLayout(1, 3, 12, 0))  # 3 columns, 12px horizontal gap

        # Left list
        leftScroll = JScrollPane(leftList)
        leftScroll.getViewport().setBackground(THEME_PAPER)
        listsPanel.add(leftScroll)

        # Buttons in the middle
        btnPanel = Box.createVerticalBox()
        btnPanel.add(btnMoveRight)
        btnPanel.add(Box.createVerticalStrut(6))
        btnPanel.add(btnMoveLeft)
        listsPanel.add(btnPanel)       
        btnPanel.add(Box.createVerticalStrut(12))  # extra space before refresh
        btnPanel.add(btnRefresh)

        # Right list
        rightScroll = JScrollPane(rightList)
        rightScroll.getViewport().setBackground(THEME_PAPER)
        listsPanel.add(rightScroll)

        # Add the sub-panel to the main panel
        panel.add(listsPanel, gbc)



        return panel


    # --------------------------- Day/night cycle -----------------------
    def BuildDayNightTab(self):
        root = MakePaperPanel()
        root.setLayout(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(10,10,10,10)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0

        # (1) Day/Night enable — authoritative from Start-Up; clicking mutates Start-Up
        gbc.gridy = 0
        row1 = Box.createHorizontalBox()
        chkDN = JCheckBox("Enable day/night cycle (requires restart)")
        chkDN.setOpaque(False)
        chkDN.setSelected(IsDayNightEnabled())
        def OnDN(e=None):
            want = chkDN.isSelected()
            ok = _EnsureScriptEnabled("DayNight.py", want)
            chkDN.setSelected(IsDayNightEnabled())
            self.CurrentDayNight = IsDayNightEnabled()
            if not ok:
                LogWarn("Could not change Start-Up for DayNight.py", alsoDialog=True)
        chkDN.addActionListener(OnDN)
        row1.add(chkDN)
        root.add(row1, gbc)
        
        gbc.gridy += 1
        self.LblDayNightError = JLabel("")
        ApplyTheme(self.LblDayNightError)
        root.add(self.LblDayNightError, gbc)

        if not ScriptExists("DayNight.py"):
            chkDN.setSelected(False)
            chkDN.setEnabled(False)
            self.LblDayNightError.setText("Missing script: DayNight.py")

        # (2) Warm/cool addresses (used by DayNight.py)
        gbc.gridy = 1
        root.add(MakeHeading("Lighting DCC addresses"), gbc)
        gbc.gridy = 2
        addrRow = Box.createHorizontalBox()
        lblWarm = JLabel("Warm (low colour temperature):")
        txtWarm = JTextField(8); txtWarm.setText(GetMemoryString(IMLowThrottleAddr, "990"))
        lblCool = JLabel(" Cool (high colour temperature):")
        txtCool = JTextField(8); txtCool.setText(GetMemoryString(IMHighThrottleAddr, "991"))
        def CommitAddrWarm():
            s = txtWarm.getText().strip()
            try: n=int(float(s)); SetMemoryString(IMLowThrottleAddr, str(n))
            except: LogWarn("Warm address invalid: " + s, alsoDialog=True)
        def CommitAddrCool():
            s = txtCool.getText().strip()
            try: n=int(float(s)); SetMemoryString(IMHighThrottleAddr, str(n))
            except: LogWarn("Cool address invalid: " + s, alsoDialog=True)
        class WarmLost(FocusAdapter):
            def focusLost(self, e): CommitAddrWarm()
        class CoolLost(FocusAdapter):
            def focusLost(self, e): CommitAddrCool()
        txtWarm.addActionListener(lambda e: CommitAddrWarm()); txtWarm.addFocusListener(WarmLost())
        txtCool.addActionListener(lambda e: CommitAddrCool()); txtCool.addFocusListener(CoolLost())
        addrRow.add(lblWarm); addrRow.add(Box.createHorizontalStrut(6)); addrRow.add(txtWarm)
        addrRow.add(lblCool); addrRow.add(Box.createHorizontalStrut(6)); addrRow.add(txtCool)
        root.add(addrRow, gbc)

        # (3) Weather generator enable — from Start-Up; clicking mutates Start-Up
        gbc.gridy = 3
        row3 = Box.createHorizontalBox()
        chkWX = JCheckBox("Use weather generator (requires restart)")
        chkWX.setOpaque(False)
        chkWX.setSelected(IsWeatherEnabled())
        def OnWX(e=None):
            want = chkWX.isSelected()
            ok = _EnsureScriptEnabled("WeatherGenerator.py", want)
            chkWX.setSelected(IsWeatherEnabled())
            self.CurrentWeather = IsWeatherEnabled()
            if not ok:
                LogWarn("Could not change Start-Up for WeatherGenerator.py", alsoDialog=True)
            RefreshWXEnableState()
        chkWX.addActionListener(OnWX)
        row3.add(chkWX)
        root.add(row3, gbc)
        
        gbc.gridy += 1
        self.LblWeatherError = JLabel("")
        ApplyTheme(self.LblWeatherError)
        root.add(self.LblWeatherError, gbc)

        if not ScriptExists("WeatherGenerator.py"):
            chkWX.setSelected(False)
            chkWX.setEnabled(False)
            self.LblWeatherError.setText("Missing script: WeatherGenerator.py")

        # (4) Climate preset
        gbc.gridy = 4
        row4 = Box.createHorizontalBox()
        lblClimate = JLabel("Climate preset:")
        climateNames = self.LoadClimateNames()
        cmbClimate = JComboBox(climateNames)
        currentClimate = GetMemoryString(IMWxClimate, "SouthWales_EarlySep")
        cmbClimate.setSelectedItem(currentClimate if currentClimate in climateNames else "SouthWales_EarlySep")
        def ApplyClimate():
            val = str(cmbClimate.getSelectedItem())
            SetMemoryString(IMWxClimate, val)
        cmbClimate.addActionListener(lambda e: ApplyClimate())
        row4.add(lblClimate); row4.add(Box.createHorizontalStrut(8)); row4.add(cmbClimate)
        root.add(row4, gbc)
     
        # (4b) Daylight hours preset
        gbc.gridy += 1
        row4b = Box.createHorizontalBox()
        lblDaylight = JLabel("Daylight hours preset:")
        daylightNames = self.LoadDayNightNames()
        cmbDaylight = JComboBox(daylightNames)
        currentDaylight = GetMemoryString(IMDayNightPreset, "Maesteg_Sep2017")
        cmbDaylight.setSelectedItem(currentDaylight if currentDaylight in daylightNames else "Maesteg_Sep2017")
        def ApplyDaylight():
            val = str(cmbDaylight.getSelectedItem())
            SetMemoryString(IMDayNightPreset, val)
        cmbDaylight.addActionListener(lambda e: ApplyDaylight())
        row4b.add(lblDaylight); row4b.add(Box.createHorizontalStrut(8)); row4b.add(cmbDaylight)
        root.add(row4b, gbc)
        
        # (5) Cloud cover (%) and Minimum night glow (0.0-1.0) side by side
        gbc.gridy += 1
        rowCloudGlow = Box.createHorizontalBox()

        # Cloud cover control
        lblCloud = JLabel("Cloud cover (%):")
        txtCloud = JTextField(3)
        txtCloud.setText(GetMemoryString(IMWxCloudPct, "0"))
        def ApplyCloud():
            s = txtCloud.getText().strip()
            try:
                n = int(float(s))
                n = max(0, min(100, n))
                SetMemoryString(IMWxCloudPct, str(n))
            except:
                LogWarn("Cloud cover must be 0..100", alsoDialog=True)
        class CloudLost(FocusAdapter):
            def focusLost(self, e): ApplyCloud()
        txtCloud.addActionListener(lambda e: ApplyCloud())
        txtCloud.addFocusListener(CloudLost())

        # Minimum night glow control
        lblGlow = JLabel("Minimum night glow (0.0-1.0):")
        txtGlow = JTextField(4)
        txtGlow.setText(GetMemoryString("IMMINNIGHTGLOW", "0.02"))
        def CommitGlow():
            s = txtGlow.getText().strip()
            try:
                v = float(s)
                if v < 0.0: v = 0.0
                if v > 1.0: v = 1.0
                SetMemoryString("IMMINNIGHTGLOW", str(v))
            except:
                LogWarn("Night glow must be a number between 0.0 and 1.0", alsoDialog=True)
        class GlowLost(FocusAdapter):
            def focusLost(self, e): CommitGlow()
        txtGlow.addActionListener(lambda e: CommitGlow())
        txtGlow.addFocusListener(GlowLost())

        # Add both controls to the same row
        rowCloudGlow.add(lblCloud)
        rowCloudGlow.add(Box.createHorizontalStrut(6))
        rowCloudGlow.add(txtCloud)
        rowCloudGlow.add(Box.createHorizontalStrut(24))  # spacing between groups
        rowCloudGlow.add(lblGlow)
        rowCloudGlow.add(Box.createHorizontalStrut(6))
        rowCloudGlow.add(txtGlow)

        root.add(rowCloudGlow, gbc)
 
        def ApplyCloud():
            s = txtCloud.getText().strip()
            try:
                n = int(float(s)); n = max(0, min(100, n))
                SetMemoryString(IMWxCloudPct, str(n))
            except:
                LogWarn("Cloud cover must be 0..100", alsoDialog=True)
        class CloudLost(FocusAdapter):
            def focusLost(self, e): ApplyCloud()
        txtCloud.addActionListener(lambda e: ApplyCloud()); txtCloud.addFocusListener(CloudLost())

        def RefreshWXEnableState():
            enabled = IsWeatherEnabled()
            cmbClimate.setEnabled(enabled)
            txtCloud.setEnabled(not enabled)
        RefreshWXEnableState()
        
        # --- Time-warp blackout (placed above Weather forecast UI)
        gbc.gridy += 1
        root.add(MakeHeading("Time-warp blackout"), gbc)

        # Row A: checkbox + threshold minutes
        gbc.gridy += 1
        warpRow = Box.createHorizontalBox()

        # Create checkbox FIRST
        chkBlackout = JCheckBox("Enable blackout when time warp exceeds")
        chkBlackout.setOpaque(False)

        # Read current memory values
        secsVal = GetMemoryString(IMTimeWarpBlackoutSeconds, "2").strip()
        minsVal = GetMemoryString(IMTimeWarpThresholdMinutes, "5").strip()

        # Determine initial enabled state from seconds (0 => disabled)
        try:
            initialSecs = float(secsVal) if secsVal != "" else 0.0
        except:
            initialSecs = 2.0
        chkBlackout.setSelected(initialSecs > 0.0)

        # Threshold minutes field
        txtWarpMins = JTextField(3)
        try:
            txtWarpMins.setText(str(max(0, int(float(minsVal)))))
        except:
            txtWarpMins.setText("5")

        # Commit logic for threshold
        def CommitWarpMins():
            s = txtWarpMins.getText().strip()
            try:
                n = max(0, int(float(s)))
                SetMemoryString(IMTimeWarpThresholdMinutes, str(n))
            except:
                pass

        txtWarpMins.addActionListener(lambda e: CommitWarpMins())
        class WarpMinsLost(FocusAdapter):
            def focusLost(self, e): CommitWarpMins()
        txtWarpMins.addFocusListener(WarpMinsLost())

        # Add components to row
        warpRow.add(chkBlackout)
        warpRow.add(Box.createHorizontalStrut(6))
        warpRow.add(txtWarpMins)
        warpRow.add(Box.createHorizontalStrut(6))
        warpRow.add(JLabel("minutes"))
        root.add(warpRow, gbc)

        # Row B: blackout seconds
        gbc.gridy += 1
        secsRow = Box.createHorizontalBox()
        lblSecs = JLabel("Blackout duration (seconds):")
        txtBlackoutSecs = JTextField(4)
        try:
            txtBlackoutSecs.setText(str(max(0.0, float(secsVal))))
        except:
            txtBlackoutSecs.setText("2")

        def CommitBlackoutSecs():
            s = txtBlackoutSecs.getText().strip()
            try:
                v = max(0.0, float(s))
                SetMemoryString(IMTimeWarpBlackoutSeconds, ("%s" % v))
            except:
                pass

        txtBlackoutSecs.addActionListener(lambda e: CommitBlackoutSecs())
        class BlackoutSecsLost(FocusAdapter):
            def focusLost(self, e): CommitBlackoutSecs()
        txtBlackoutSecs.addFocusListener(BlackoutSecsLost())

        # Toggle logic
        def ApplyBlackoutToggle():
            try:
                if chkBlackout.isSelected():
                    txtBlackoutSecs.setEnabled(True)
                    try:
                        v = float(txtBlackoutSecs.getText().strip())
                        if v == 0.0:
                            txtBlackoutSecs.setText("2")
                    except:
                        txtBlackoutSecs.setText("2")
                    CommitBlackoutSecs()
                else:
                    txtBlackoutSecs.setEnabled(False)
                    SetMemoryString(IMTimeWarpBlackoutSeconds, "0")
            except:
                pass

        txtBlackoutSecs.setEnabled(chkBlackout.isSelected())
        ApplyBlackoutToggle()
        chkBlackout.addActionListener(lambda e: ApplyBlackoutToggle())

        secsRow.add(lblSecs)
        secsRow.add(Box.createHorizontalStrut(8))
        secsRow.add(txtBlackoutSecs)
        root.add(secsRow, gbc)

        
        # Enable/disable the newspaper title controls depending on UI choice
        def RefreshPaperTitleEnable():
            # rbApp / rbNewsO / rbNewsM are in scope here
            useNewspaper = (rbNewsO.isSelected() or rbNewsM.isSelected())
            try:
                txtPaper.setEnabled(useNewspaper)
            except:
                pass
            try:
                lblPaper.setEnabled(useNewspaper)
            except:
                pass
            try:
                lblExplain.setEnabled(useNewspaper)
            except:
                pass

        # (6) Weather forecast UI (radio buttons)      
        gbc.gridy += 1
        root.add(MakeHeading("Weather forecast UI"), gbc)
        gbc.gridy += 1
        uiRow = Box.createHorizontalBox()
        rbApp = JRadioButton("Mobile app"); rbApp.setOpaque(False)
        rbNewsO = JRadioButton("Newspaper (Old)"); rbNewsO.setOpaque(False)
        rbNewsM = JRadioButton("Newspaper (Modern)"); rbNewsM.setOpaque(False)
        group = ButtonGroup(); group.add(rbApp); group.add(rbNewsO); group.add(rbNewsM)
        uiChoice = GetMemoryString(IMWxUiChoice, "Newspaper").strip()
        style = GetMemoryString(IMWxNewsStyle, "Old").strip()
        if uiChoice.lower() == "app":
            rbApp.setSelected(True)
        else:
            if style.lower() == "modern": rbNewsM.setSelected(True)
            else: rbNewsO.setSelected(True)
        def ApplyUi():
            if rbApp.isSelected():
                SetMemoryString(IMWxUiChoice, "App")
            elif rbNewsO.isSelected():
                SetMemoryString(IMWxUiChoice, "Newspaper")
                SetMemoryString(IMWxNewsStyle, "Old")
            else:
                SetMemoryString(IMWxUiChoice, "Newspaper")
                SetMemoryString(IMWxNewsStyle, "Modern")
            # ALSO: update enable/disable for the Newspaper title controls
            RefreshPaperTitleEnable()
            RefreshAdsControlEnable()
        rbApp.addActionListener(lambda e: ApplyUi())
        rbNewsO.addActionListener(lambda e: ApplyUi())
        rbNewsM.addActionListener(lambda e: ApplyUi())
        uiRow.add(rbApp); uiRow.add(Box.createHorizontalStrut(16)); uiRow.add(rbNewsO)
        uiRow.add(Box.createHorizontalStrut(12)); uiRow.add(rbNewsM)
        root.add(uiRow, gbc)       
        
        # (7) Newspaper title (used by WeatherForecastUINewspaper)
        gbc.gridy += 1
        rowPaper = Box.createHorizontalBox()
        lblPaper = JLabel("Newspaper title:")
        ApplyTheme(lblPaper)

        txtPaper = JTextField(28)
        # Default template uses the active profile name token
        initPaper = GetMemoryString("IMWX_NEWS_PAPERNAME", "The {PROFILE} Echo")
        txtPaper.setText(initPaper)

        def CommitPaper():
            s = txtPaper.getText().strip()
            if len(s) == 0:
                s = "The {PROFILE} Echo"
            SetMemoryString("IMWX_NEWS_PAPERNAME", s)

        txtPaper.addActionListener(lambda e: CommitPaper())
        class PaperLost(FocusAdapter):
            def focusLost(self, e): CommitPaper()
        txtPaper.addFocusListener(PaperLost())

        rowPaper.add(lblPaper); rowPaper.add(Box.createHorizontalStrut(8)); rowPaper.add(txtPaper)
        root.add(rowPaper, gbc)
        # Set enabled/disabled state at creation time
        RefreshPaperTitleEnable()

        # Explanatory text about tokens
        gbc.gridy += 1
        lblExplain = JLabel("<html>"
            "Use <b>{PROFILE}</b> anywhere in the text to insert the active profile name.<br/>"
            "Example: <i>The {PROFILE} Echo</i>"
            "</html>")
        ApplyTheme(lblExplain)
        root.add(lblExplain, gbc)
        
        # (8) Forecast reliability (%)
        gbc.gridy += 1
        rowAcc = Box.createHorizontalBox()
        lblAcc = JLabel("Forecast reliability (%):")
        ApplyTheme(lblAcc)

        txtAcc = JTextField(4)
        # Default = 80; clamp 0..100 when committing
        initAcc = GetMemoryString("IMWX_FORECAST_ACCURACY", "80")
        txtAcc.setText(initAcc)

        def CommitAcc():
            s = txtAcc.getText().strip()
            try:
                n = int(float(s))
                n = max(0, min(100, n))
                SetMemoryString("IMWX_FORECAST_ACCURACY", str(n))
            except:
                # keep prior value if invalid; optional: show warning
                pass

        txtAcc.addActionListener(lambda e: CommitAcc())
        class AccLost(FocusAdapter):
            def focusLost(self, e): CommitAcc()
        txtAcc.addFocusListener(AccLost())

        rowAcc.add(lblAcc); rowAcc.add(Box.createHorizontalStrut(8)); rowAcc.add(txtAcc)
        root.add(rowAcc, gbc)
        
        # (9) Show spoof mobile ads (App only)
        gbc.gridy += 1
        rowAds = Box.createHorizontalBox()
        lblAds = JLabel("Show spoof mobile ads:")
        ApplyTheme(lblAds)

        chkSpoofAds = JCheckBox("")
        chkSpoofAds.setOpaque(False)
        chkSpoofAds.setSelected(GetMemoryBool("IMSPOOFADSENABLED", True))

        def OnSpoofAds(e=None):
            SetMemoryBool("IMSPOOFADSENABLED", chkSpoofAds.isSelected())

        chkSpoofAds.addActionListener(OnSpoofAds)

        rowAds.add(lblAds); rowAds.add(Box.createHorizontalStrut(8)); rowAds.add(chkSpoofAds)
        root.add(rowAds, gbc)

        # Helper: enable the checkbox only when Mobile app UI is selected
        def RefreshAdsControlEnable():
            try:
                chkSpoofAds.setEnabled(rbApp.isSelected())
                lblAds.setEnabled(True)   # label stays visible; checkbox greys out when app is not selected
            except:
                pass

        # Initial enable/disable at creation time
        RefreshAdsControlEnable()

        return root


    # ---- Helper: read climate names from profile:jython/config/climate.csv ----
    def LoadClimateNames(self):
        names = ["SouthWales_EarlySep"]
        try:
            path = FileUtil.getExternalFilename("profile:jython/config/climate.csv")
            import java.io as jio
            f = jio.File(path)
            if not f.exists() or not f.isFile(): return names
            fis = jio.FileInputStream(f)
            isr = java.io.InputStreamReader(fis, "US-ASCII")
            br = java.io.BufferedReader(isr)
            header = br.readLine()
            idx = -1
            if header:
                cols = header.split("\t")
                for i,c in enumerate(cols):
                    if c.strip().lower() == "name": idx = i; break
            line = br.readLine()
            seen = set(names)
            while line is not None:
                parts = line.split("\t")
                if idx >= 0 and idx < len(parts):
                    val = parts[idx].strip()
                    if val and val not in seen:
                        names.append(val); seen.add(val)
                line = br.readLine()
            br.close(); isr.close(); fis.close()
        except Exception as ex:
            LogWarn("Could not read climate presets: " + str(ex))
        return names

    # ---- Helper: read day/night preset names from profile:jython/config/daynight.csv ----
    def LoadDayNightNames(self):
        names = ["Maesteg_Sep2017"]
        try:
            path = FileUtil.getExternalFilename("profile:jython/config/daynight.csv")
            import java.io as jio
            f = jio.File(path)
            if not f.exists() or not f.isFile(): return names
            fis = jio.FileInputStream(f)
            isr = java.io.InputStreamReader(fis, "US-ASCII")
            br = java.io.BufferedReader(isr)
            header = br.readLine()
            idx = -1
            if header:
                cols = header.split("\t")
                for i,c in enumerate(cols):
                    if c.strip().lower() == "name": idx = i; break
            line = br.readLine()
            seen = set(names)
            while line is not None:
                parts = line.split("\t")
                if idx >= 0 and idx < len(parts):
                    val = parts[idx].strip()
                    if val and val not in seen:
                        names.append(val); seen.add(val)
                line = br.readLine()
            br.close(); isr.close(); fis.close()
        except Exception as ex:
            LogWarn("Could not read day/night presets: " + str(ex))
        return names


        # --------------------- Restart prompt on close ---------------------- 
        def dispose(self):
            # First, guard against unsaved edits in the Workings tab
            try:
                if getattr(self, "WorkingsDirty", False):
                    choice = JOptionPane.showConfirmDialog(
                        self,
                        "You have unsaved changes in a working script.\nDiscard changes and close the setup window?",
                        "Unsaved changes",
                        JOptionPane.OK_CANCEL_OPTION,
                        JOptionPane.WARNING_MESSAGE
                    )
                    if choice != JOptionPane.OK_OPTION:
                        return  # abort closing; user wants to keep editing
            except Exception:
                pass

            # Then apply your existing restart-needed prompt logic           
            changed = (self.InitialTASMenu != self.CurrentTASMenu or
                       self.InitialTimeActions != self.CurrentTimeActions or
                       self.InitialDayNight != self.CurrentDayNight or
                       self.InitialWeather != self.CurrentWeather or
                       self.InitialDirectionSensing != self.CurrentDirectionSensing)
            if changed:
                try:
                    JOptionPane.showMessageDialog(
                        self,
                        "Some changes require a restart to take effect.\nPlease close and restart JMRI manually.",
                        "Restart Required",
                        JOptionPane.INFORMATION_MESSAGE
                    )
                except Exception as ex:
                    LogWarn("Please restart JMRI manually to apply changes.", alsoDialog=False)
        jmri.util.JmriJFrame.dispose(self)

# -------------------------------- Entry --------------------------------
class RunnableAdapter(Runnable):
    def __init__(self, func): self.func = func
    def run(self): self.func()

def ShowTASSetup():
    def Run():
        try: TASSetupFrame()
        except Exception as ex:
            LogError("Error opening Timetable Automation System setup: " + str(ex), ex=ex, alsoDialog=True)
    if SwingUtilities.isEventDispatchThread():
        Run()
    else:
        SwingUtilities.invokeLater(RunnableAdapter(Run))

ShowTASSetup()