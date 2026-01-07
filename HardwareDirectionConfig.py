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
# UI for configuring "normal" hardware orientation per roster ID.
# Theming: match TAS setup window font and paper background via memory keys:
#   - Typeface: Memory "TAS_FONT_FAMILY" (e.g., "Gill Sans MT")
#   - Paper colour: Memory "TASPAPERCOLOUR" as "R,G,B" (e.g., "249,246,238")
#
# Foreground (text) colors indicate state:
#   - Cyan text: last-reported only
#   - Dark blue text: in both registers
#   - Dark purple text: normal-only
#
# Layout:
#   - Explanatory text at top, full width, padded.
#   - Status label (left-aligned) above "Current orientation".
#   - "Current orientation" centred; buttons left-aligned with extra spacing.
#
# Behavior:
#   - Cyan: Normal/Inverted enabled, Delete disabled; status "Undefined" (cyan)
#   - Dark blue: all buttons enabled; status "Normal" or "Inverted" (dark blue)
#   - Dark purple: Delete enabled only; status "Current orientation unknown" (dark purple)
#
# ASCII only; CamelCase; case-insensitive roster IDs; no absolute paths.

import jmri
from javax.swing import JFrame, JPanel, JScrollPane, JTable, JButton, JLabel, JOptionPane, JTextArea, Box
from javax.swing import BoxLayout, ListSelectionModel, SwingUtilities, UIManager
from javax.swing.table import DefaultTableModel, DefaultTableCellRenderer
from javax.swing.border import EmptyBorder
from javax.swing.event import ListSelectionListener
from java.awt import BorderLayout, Color, Dimension, Font
from java.lang import Runnable
import TASBeanLookup as TBL

# Import registers (must be available on JMRI's Jython path)
try:
    import NormalDirectionRegister
except Exception as e:
    print("Error: cannot import NormalDirectionRegister: " + str(e))
    raise

try:
    import LastReportedDirection
except Exception as e:
    print("Error: cannot import LastReportedDirection: " + str(e))
    raise

# Text colors (foreground)
CYAN_TEXT = Color(0, 200, 200)
DARK_BLUE_TEXT = Color(0, 51, 102)
DARK_PURPLE_TEXT = Color(76, 0, 153)

# Class tags
CLASS_CYAN = "cyan"        # last-only
CLASS_BLUE = "blue"        # both
CLASS_PURPLE = "purple"    # normal-only

# Theme: read font family and paper background like TASSetup (no import)


def GetMemoryString(Suffix, DefaultValue):
    # Read (and if needed create) a JMRI Memory by suffix, prefix-agnostic.
    # Uses TASBeanLookup so this works across IM, I2M, I3M... internal prefixes.
    try:
        val = TBL.SafeGetOrCreateMemoryValue(Suffix, DefaultValue)
        return DefaultValue if val is None else str(val)
    except Exception:
        return DefaultValue

def RgbStrToColorOrDefault(rgbStr, defaultColor):
    try:
        parts = [p.strip() for p in str(rgbStr).split(",")]
        if len(parts) != 3:
            return defaultColor
        r = max(0, min(255, int(float(parts[0]))))
        g = max(0, min(255, int(float(parts[1]))))
        b = max(0, min(255, int(float(parts[2]))))
        return Color(r, g, b)
    except Exception:
        return defaultColor

THEME_FONT_FAMILY = GetMemoryString("TAS_FONT_FAMILY", "Gill Sans MT")
THEME_PAPER = RgbStrToColorOrDefault(GetMemoryString("TASPAPERCOLOUR", "249,246,238"), Color(249, 246, 238))

def SetPaperBackground(component):
    try:
        component.setOpaque(True)
        component.setBackground(THEME_PAPER)
    except Exception:
        pass

def SetFontIfPossible(component, family, style=Font.PLAIN, size=13):
    try:
        component.setFont(Font(family, style, size))
    except Exception:
        pass

# Apply typeface recursively across the component tree
from java.awt import Container
from javax.swing import JTable as _JTable, JList as _JList, JScrollPane as _JScrollPane, JTabbedPane as _JTabbedPane
def ApplyThemeRecursive(comp, family):
    try:
        SetFontIfPossible(comp, family)
        if isinstance(comp, _JTable):
            hdr = comp.getTableHeader()
            if hdr is not None:
                SetFontIfPossible(hdr, family, Font.BOLD, 13)
        if isinstance(comp, _JList):
            rnd = comp.getCellRenderer()
            if rnd is not None:
                try:
                    rnd.setFont(Font(family, Font.PLAIN, 13))
                except Exception:
                    pass
        if isinstance(comp, _JScrollPane):
            vp = comp.getViewport()
            if vp is not None and vp.getView() is not None:
                SetFontIfPossible(vp.getView(), family)
        if isinstance(comp, _JTabbedPane):
            try:
                count = comp.getTabCount()
                for i in range(count):
                    tab = comp.getTabComponentAt(i)
                    if tab is not None:
                        SetFontIfPossible(tab, family, Font.BOLD, 13)
            except Exception:
                pass
    except Exception:
        pass
    try:
        if isinstance(comp, Container):
            for child in comp.getComponents():
                ApplyThemeRecursive(child, family)
    except Exception:
        pass

# Helpers (ASCII, CamelCase, case-insensitive IDs)

def NormId(s):
    try:
        return str(s).strip().lower()
    except:
        return ""

def TitleCase(s):
    try:
        t = str(s).strip()
        if t == "":
            return ""
        return t[0:1].upper() + t[1:].lower()
    except:
        return s


# Lighting decoder address helper (exclude from orientation lists)
def NormAddr(s):
    try:
        t = str(s).strip()
    except:
        return ''
    if t is None:
        return ''
    t = str(t).strip()
    if t == '':
        return ''
    if t.isdigit():
        try:
            return str(int(t))
        except:
            try:
                return t.lstrip('0') or '0'
            except:
                return t
    return t

def GetLightingAddressSet():
    addrs = set([])
    for memName in ['LOWCTTHROTTLEADDR', 'HIGHCTTHROTTLEADDR']:
        try:
            raw = GetMemoryString(memName, '').strip()
        except:
            raw = ''
        raw = NormAddr(raw)
        if raw != '':
            addrs.add(raw)
    return addrs
# --------- Roster/DCC helpers (expand last-reported to all IDs sharing an address) ---------

def BuildRosterAddressIndex():
    """Return (ridLowerToAddr, addrToRidList).
    ridLowerToAddr: lower(rosterId) -> DCC address as string
    addrToRidList:  DCC address as string -> list of roster IDs (original display case)
    """
    ridLowerToAddr = {}
    addrToRidList = {}
    try:
        roster = jmri.jmrit.roster.Roster.getDefault()
        if roster is None:
            return (ridLowerToAddr, addrToRidList)
        entries = roster.matchingList(None, None, None, None, None, None, None)
        seq = entries.toArray() if hasattr(entries, "toArray") else list(entries)
        for re in seq:
            try:
                rid = str(re.getId())
                addr = str(re.getDccAddress()) if hasattr(re, "getDccAddress") else ""
                if addr is None or addr.strip() == "":
                    addr = ""
                lower = NormId(rid)
                if lower != "":
                    ridLowerToAddr[lower] = addr
                    lst = addrToRidList.get(addr, [])
                    lst.append(rid)
                    addrToRidList[addr] = lst
            except Exception:
                pass
    except Exception:
        pass
    return (ridLowerToAddr, addrToRidList)

def ExpandLastMapToAllIds(lastMap):
    """Expand lastReportedDirection so every roster ID sharing the same DCC address appears."""
    expanded = {}
    try:
        ridLowerToAddr, addrToRidList = BuildRosterAddressIndex()
        src = {}
        for k, v in (lastMap or {}).items():
            lk = NormId(k)
            if lk != "":
                src[lk] = v
        for lowerRid, direction in src.items():
            addr = ridLowerToAddr.get(lowerRid, None)
            if addr is None:
                display = None
                try:
                    for origK in lastMap.keys():
                        if NormId(origK) == lowerRid:
                            display = str(origK)
                            break
                except Exception:
                    pass
                if display is None:
                    display = lowerRid
                expanded[display] = direction
                continue
            siblings = addrToRidList.get(addr, []) or []
            for rid in siblings:
                expanded[str(rid)] = direction
    except Exception:
        try:
            for k, v in (lastMap or {}).items():
                expanded[str(k)] = v
        except Exception:
            pass
    return expanded

def RosterIdClusterFor(displayRosterId):
    """Return roster IDs that share the same DCC address as displayRosterId."""
    cluster = [displayRosterId]
    try:
        ridLowerToAddr, addrToRidList = BuildRosterAddressIndex()
        addr = ridLowerToAddr.get(NormId(displayRosterId), None)
        if addr is None:
            return cluster
        siblings = addrToRidList.get(addr, []) or []
        if len(siblings) > 0:
            return siblings
    except Exception:
        pass
    return cluster

# -----------------------------------------------------------------------------------------------

def BuildRegistersSnapshot():
    # Return shallow copies to avoid concurrent mutation during rendering
    normalMap = {}
    try:
        normalMap = NormalDirectionRegister.GetCopy()  # {lowerId: directionStr}
    except Exception as e:
        print("Warning: GetCopy() failed: " + str(e))
    lastMap = {}
    try:
        lastMap = dict(LastReportedDirection.lastReportedDirection)  # shallow copy
    except Exception as e:
        print("Warning: copy of lastReportedDirection failed: " + str(e))
    return (normalMap, lastMap)

def BuildListingData():
    # Produce [(displayId, classTag)] sorted by displayId
    normalMap, lastMap = BuildRegistersSnapshot()

    expandedLast = ExpandLastMapToAllIds(lastMap)

    # Filter out roster entries that are actually layout lighting decoders (warm/cool).
    lightingAddrs = GetLightingAddressSet()
    ridLowerToAddr, _addrToRidList = BuildRosterAddressIndex()
    lastLowerToDisplay = {}
    for k in expandedLast.keys():
        lk = NormId(k)
        if lk != "" and lk not in lastLowerToDisplay:
            lastLowerToDisplay[lk] = k

    unionLower = set(normalMap.keys()).union(set(lastLowerToDisplay.keys()))

    rows = []
    for lowerId in sorted(list(unionLower)):
        try:
            addr = ridLowerToAddr.get(lowerId, '')
        except:
            addr = ''
        if NormAddr(addr) != '' and NormAddr(addr) in lightingAddrs:
            continue
        inNormal = lowerId in normalMap
        inLast = lowerId in lastLowerToDisplay
        if inLast and not inNormal:
            cls = CLASS_CYAN
        elif inNormal and inLast:
            cls = CLASS_BLUE
        else:
            cls = CLASS_PURPLE
        displayId = lastLowerToDisplay.get(lowerId, lowerId)
        rows.append((displayId, cls))
    return rows

def DetermineOppositeDirection(currentValue, lastMap):
    # Prefer any observed value different to currentValue; else use fallback pairs
    try:
        cur = str(currentValue).strip()
    except:
        cur = ""
    curLower = cur.lower()

    observedValues = set()
    for v in lastMap.values():
        try:
            vv = str(v).strip()
        except:
            vv = ""
        if vv != "":
            observedValues.add(vv)

    for v in observedValues:
        if v.strip().lower() != curLower:
            return v

    fallback = {
        "east": "west",
        "west": "east",
        "south": "north",
        "north": "south",
        "southbound": "northbound",
        "northbound": "southbound"
    }
    if curLower in fallback:
        return TitleCase(fallback[curLower])
    return None

# Table model and renderer

class ListingTableModel(DefaultTableModel):
    def __init__(self, rows):
        DefaultTableModel.__init__(self, [], [])
        self.addColumn("Roster ID")
        self.addColumn("Class")
        for (disp, cls) in rows:
            self.addRow([disp, cls])

    def isCellEditable(self, row, col):
        return False

class RowColorRenderer(DefaultTableCellRenderer):
    # Use foreground (text) colors to indicate state; keep default backgrounds/selection
    def getTableCellRendererComponent(self, table, value, isSelected, hasFocus, row, column):
        comp = DefaultTableCellRenderer.getTableCellRendererComponent(
            self, table, value, isSelected, hasFocus, row, column
        )
        try:
            cls = table.getModel().getValueAt(row, 1)
            if cls == CLASS_CYAN:
                fg = CYAN_TEXT
            elif cls == CLASS_BLUE:
                fg = DARK_BLUE_TEXT
            else:
                fg = DARK_PURPLE_TEXT
            comp.setForeground(fg)
        except Exception:
            pass
        return comp

# Selection listener that calls back into the UI instance
class SelectionHook(ListSelectionListener):
    def __init__(self, outer):
        self.outer = outer
    def valueChanged(self, e):
        try:
            if e.getValueIsAdjusting():
                return
        except Exception:
            pass
        try:
            self.outer.UpdateButtonStates()
            self.outer.UpdateStatusLabel()
        except Exception:
            pass

# Main UI

class HardwareDirectionConfigUI(Runnable):
    def __init__(self):
        self.frame = None
        self.table = None
        self.normalBtn = None
        self.invertedBtn = None
        self.deleteBtn = None
        self.explainText = None
        self.statusLabel = None

    def run(self):
        self.frame = JFrame("Hardware Direction Configuration")
        self.frame.setLayout(BorderLayout())

        try:
            SetPaperBackground(self.frame.getContentPane())
        except Exception:
            pass

        topPanel = JPanel()
        topPanel.setLayout(BorderLayout())
        topPanel.setBorder(EmptyBorder(10, 10, 10, 10))
        SetPaperBackground(topPanel)

        # Explanatory text (ASCII-only)
        self.explainText = JTextArea("Configure the orientation of your trains here so that the Timetable Automation System knows which way around is normal. Place your trains on the track in a section with working hardware orientation sensing. They should appear in a light cyan in the list below. Choose whether they are facing in their normal or inverted orientation using the 'Normal' and 'Inverted' buttons, or erase the configuration with 'Delete'.")
        self.explainText.setEditable(False)
        self.explainText.setLineWrap(True)
        self.explainText.setWrapStyleWord(True)
        self.explainText.setOpaque(False)
        topPanel.add(self.explainText, BorderLayout.CENTER)

        self.frame.add(topPanel, BorderLayout.NORTH)

        rows = BuildListingData()
        model = ListingTableModel(rows)
        self.table = JTable(model)
        self.table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)

        try:
            self.table.getColumnModel().getColumn(1).setMinWidth(0)
            self.table.getColumnModel().getColumn(1).setMaxWidth(0)
            self.table.getColumnModel().getColumn(1).setWidth(0)
        except Exception:
            pass
        self.table.getColumnModel().getColumn(0).setCellRenderer(RowColorRenderer())

        scroll = JScrollPane(self.table)
        scroll.setBorder(EmptyBorder(8, 8, 8, 4))
        try:
            SetPaperBackground(scroll)
            vp = scroll.getViewport()
            if vp is not None:
                vp.setBackground(THEME_PAPER)
        except Exception:
            pass
        self.frame.add(scroll, BorderLayout.CENTER)

        rightOuter = JPanel()
        rightOuter.setLayout(BorderLayout())
        rightOuter.setBorder(EmptyBorder(12, 16, 12, 16))
        SetPaperBackground(rightOuter)

        rightInner = JPanel()
        rightInner.setLayout(BoxLayout(rightInner, BoxLayout.Y_AXIS))
        rightInner.setBorder(EmptyBorder(4, 0, 4, 0))
        rightInner.setOpaque(False)

        self.statusLabel = JLabel(" ")
        self.statusLabel.setAlignmentX(JLabel.LEFT_ALIGNMENT)
        rightInner.add(self.statusLabel)
        rightInner.add(Box.createVerticalStrut(8))

        header = JLabel("Current orientation")
        header.setAlignmentX(JLabel.CENTER_ALIGNMENT)
        rightInner.add(header)
        rightInner.add(Box.createVerticalStrut(14))

        self.normalBtn = JButton("Normal", actionPerformed=self.OnNormal)
        self.normalBtn.setAlignmentX(JButton.LEFT_ALIGNMENT)
        rightInner.add(self.normalBtn)
        rightInner.add(Box.createVerticalStrut(10))

        self.invertedBtn = JButton("Inverted", actionPerformed=self.OnInverted)
        self.invertedBtn.setAlignmentX(JButton.LEFT_ALIGNMENT)
        rightInner.add(self.invertedBtn)
        rightInner.add(Box.createVerticalStrut(10))

        self.deleteBtn = JButton("Delete", actionPerformed=self.OnDelete)
        self.deleteBtn.setAlignmentX(JButton.LEFT_ALIGNMENT)
        rightInner.add(self.deleteBtn)

        rightOuter.add(rightInner, BorderLayout.NORTH)
        self.frame.add(rightOuter, BorderLayout.EAST)

        try:
            selHook = SelectionHook(self)
            self.table.getSelectionModel().addListSelectionListener(selHook)
        except Exception:
            pass

        try:
            ApplyThemeRecursive(self.frame.getContentPane(), THEME_FONT_FAMILY)
        except Exception:
            pass

        self.UpdateButtonStates()
        self.UpdateStatusLabel()

        self.frame.setSize(780, 500)
        self.frame.setLocationRelativeTo(None)
        self.frame.setVisible(True)

    def GetSelectedRowInfo(self):
        idx = self.table.getSelectedRow()
        if idx < 0:
            return (None, None, None)
        try:
            disp = str(self.table.getModel().getValueAt(idx, 0))
            cls = str(self.table.getModel().getValueAt(idx, 1))
            lowerId = NormId(disp)
            return (disp, cls, lowerId)
        except Exception:
            return (None, None, None)

    def UpdateButtonStates(self):
        disp, cls, lowerId = self.GetSelectedRowInfo()
        if disp is None:
            self.normalBtn.setEnabled(False)
            self.invertedBtn.setEnabled(False)
            self.deleteBtn.setEnabled(False)
            return
        if cls == CLASS_CYAN:
            self.normalBtn.setEnabled(True)
            self.invertedBtn.setEnabled(True)
            self.deleteBtn.setEnabled(False)
        elif cls == CLASS_BLUE:
            self.normalBtn.setEnabled(True)
            self.invertedBtn.setEnabled(True)
            self.deleteBtn.setEnabled(True)
        else:
            self.normalBtn.setEnabled(False)
            self.invertedBtn.setEnabled(False)
            self.deleteBtn.setEnabled(True)

    def UpdateStatusLabel(self):
        disp, cls, lowerId = self.GetSelectedRowInfo()
        if disp is None:
            self.statusLabel.setText(" ")
            self.statusLabel.setForeground(Color.black)
            return

        if cls == CLASS_CYAN:
            self.statusLabel.setText("Undefined")
            self.statusLabel.setForeground(CYAN_TEXT)
            return

        if cls == CLASS_PURPLE:
            self.statusLabel.setText("Current orientation unknown")
            self.statusLabel.setForeground(DARK_PURPLE_TEXT)
            return

        try:
            normVal = NormalDirectionRegister.GetNormalDirection(disp, None)
            lastMap = dict(LastReportedDirection.lastReportedDirection)
            lastVal = None
            if disp in lastMap:
                lastVal = str(lastMap.get(disp))
            else:
                for k, v in lastMap.items():
                    if NormId(k) == lowerId:
                        lastVal = str(v)
                        break
            nv = (str(normVal).strip().lower() if normVal is not None else "")
            lv = (str(lastVal).strip().lower() if lastVal is not None else "")
            if nv != "" and lv != "" and nv == lv:
                self.statusLabel.setText("Normal")
            else:
                self.statusLabel.setText("Inverted")
            self.statusLabel.setForeground(DARK_BLUE_TEXT)
        except Exception:
            self.statusLabel.setText("Normal")
            self.statusLabel.setForeground(DARK_BLUE_TEXT)

    def RefreshTable(self):
        rows = BuildListingData()
        model = ListingTableModel(rows)
        self.table.setModel(model)
        try:
            self.table.getColumnModel().getColumn(1).setMinWidth(0)
            self.table.getColumnModel().getColumn(1).setMaxWidth(0)
            self.table.getColumnModel().getColumn(1).setWidth(0)
        except Exception:
            pass
        self.table.getColumnModel().getColumn(0).setCellRenderer(RowColorRenderer())
        self.UpdateButtonStates()
        self.UpdateStatusLabel()

    def _ApplyForCluster(self, displayRosterId, fn):
        """Apply a function to all roster IDs that share the DCC address with displayRosterId."""
        try:
            cluster = RosterIdClusterFor(displayRosterId)
            for rid in cluster:
                fn(rid)
        except Exception:
            try:
                fn(displayRosterId)
            except Exception:
                pass

    def OnNormal(self, event):
        disp, cls, lowerId = self.GetSelectedRowInfo()
        if disp is None:
            return
        try:            
            # Use the entire DCC-address cluster to resolve a last-reported value
            lastMap = dict(LastReportedDirection.lastReportedDirection)

            # Gather the cluster (all roster IDs that share the same DCC address as the selected row)
            cluster = RosterIdClusterFor(disp)

            # Try exact/CI matches for any roster ID in the cluster
            value = None
            for rid in cluster:
                if rid in lastMap:
                    value = str(lastMap.get(rid))
                    break
                # Case-insensitive match against lastMap keys
                lrid = NormId(rid)
                for k, v in lastMap.items():
                    if NormId(k) == lrid:
                        value = str(v)
                        break
                if value is not None:
                    break

            # Fallback: if still no value, try exact/CI against the selected ID
            if value is None:
                if disp in lastMap:
                    value = str(lastMap.get(disp))
                else:
                    for k, v in lastMap.items():
                        if NormId(k) == lowerId:
                            value = str(v)
                            break

            # Validate usable value
            if value is None or value.strip() == "" or value.strip().lower() == "unknown":
                JOptionPane.showMessageDialog(
                    self.frame,
                    "Cannot set normal orientation: no usable last-reported value for this roster ID.",
                    "No last-reported value",
                    JOptionPane.ERROR_MESSAGE
                )
                return

            def _setFn(rid):
                NormalDirectionRegister.SetNormalDirection(rid, value)
            self._ApplyForCluster(disp, _setFn)

            try:
                NormalDirectionRegister.Save()
            except Exception:
                pass
            self.RefreshTable()
        except Exception as e:
            JOptionPane.showMessageDialog(self.frame, "Error: " + str(e), "Operation failed", JOptionPane.ERROR_MESSAGE)

    def OnInverted(self, event):
        disp, cls, lowerId = self.GetSelectedRowInfo()
        if disp is None:
            return
        try:        
            # Use the entire DCC-address cluster to resolve the current last-reported value
            lastMap = dict(LastReportedDirection.lastReportedDirection)

            # Cluster of roster IDs at the same DCC address
            cluster = RosterIdClusterFor(disp)

            # Try exact/CI matches across the cluster first
            curVal = None
            for rid in cluster:
                if rid in lastMap:
                    curVal = str(lastMap.get(rid))
                    break
                lrid = NormId(rid)
                for k, v in lastMap.items():
                    if NormId(k) == lrid:
                        curVal = str(v)
                        break
                if curVal is not None:
                    break

            # Fallback: selected ID only
            if curVal is None:
                if disp in lastMap:
                    curVal = str(lastMap.get(disp))
                else:
                    for k, v in lastMap.items():
                        if NormId(k) == lowerId:
                            curVal = str(v)
                            break

            # Validate usable current value
            if curVal is None or curVal.strip() == "" or curVal.strip().lower() == "unknown":
                JOptionPane.showMessageDialog(
                    self.frame,
                    "Cannot determine how orientation are keyed. Place the train on the track the opposite way around in a section connected to orientation sensing hardware and select 'normal'",
                    "Cannot determine orientation",
                    JOptionPane.ERROR_MESSAGE
                )
                return

            opp = DetermineOppositeDirection(curVal, lastMap)
            if opp is None or opp.strip() == "":
                JOptionPane.showMessageDialog(
                    self.frame,
                    "Cannot determine how orientation are keyed. Place the train on the track the opposite way around in a section connected to orientation sensing hardware and select 'normal'",
                    "Cannot determine orientation",
                    JOptionPane.ERROR_MESSAGE
                )
                return

            def _setFn(rid):
                NormalDirectionRegister.SetNormalDirection(rid, opp)
            self._ApplyForCluster(disp, _setFn)

            try:
                NormalDirectionRegister.Save()
            except Exception:
                pass
            self.RefreshTable()
        except Exception as e:
            JOptionPane.showMessageDialog(self.frame, "Error: " + str(e), "Operation failed", JOptionPane.ERROR_MESSAGE)

    def OnDelete(self, event):
        disp, cls, lowerId = self.GetSelectedRowInfo()
        if disp is None:
            return
        try:
            def _delFn(rid):
                NormalDirectionRegister.RemoveNormalDirection(rid)
            self._ApplyForCluster(disp, _delFn)

            try:
                NormalDirectionRegister.Save()
            except Exception:
                pass
            self.RefreshTable()
        except Exception as e:
            JOptionPane.showMessageDialog(self.frame, "Error: " + str(e), "Operation failed", JOptionPane.ERROR_MESSAGE)

# Entry point: show UI on EDT
def Show():
    ui = HardwareDirectionConfigUI()
    SwingUtilities.invokeLater(ui)

try:
    Show()
except Exception as e:
    print("Failed to show HardwareDirectionConfig UI: " + str(e))