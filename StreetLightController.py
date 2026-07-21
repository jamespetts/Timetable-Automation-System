# This file is part of the Timetable Automation System by James E. Petts
#
# The Timetable Automation System is free software: you can redistribute it and/or modify it under the terms of the 
# GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version.
#
# The Timetable Automation System is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General 
# Public License for more details.

import os
import csv
import java
import jmri
import TASBeanLookup as TBL

from java.awt import BorderLayout, Dimension, FlowLayout, GridBagConstraints, GridBagLayout, Insets
from java.lang import Runnable
from javax.swing import (JButton, JDialog, JLabel, JList, JOptionPane,
                         JPanel, JScrollPane, JSplitPane, JTextField, JSpinner,
                         SpinnerNumberModel, ListSelectionModel, DefaultListModel,
                         SwingUtilities)

CONFIG_PROFILE_PATH = "profile:jython/config/streetlights.tsv"
CONFIG_COLUMNS = ["group_name", "dusk_offset_seconds", "dawn_offset_seconds", "light_system_names"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def GetConfigPath():
    try:
        return jmri.util.FileUtil.getExternalFilename(CONFIG_PROFILE_PATH)
    except Exception:
        return "jython/config/streetlights.tsv"


def LoadStreetLightGroups():
    groups = []
    path = GetConfigPath()
    if not os.path.isfile(path):
        return groups
    try:
        fh = open(path, "r")
        try:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                name = str(row.get("group_name", "")).strip()
                if name == "":
                    continue
                try:
                    duskOffset = int(str(row.get("dusk_offset_seconds", "0")).strip())
                    dawnOffset = int(str(row.get("dawn_offset_seconds", "0")).strip())
                except Exception:
                    print("[StreetLightController] Ignoring group with an invalid offset: " + name)
                    continue
                rawLights = str(row.get("light_system_names", "")).strip()
                lightNames = [item.strip() for item in rawLights.split(";") if item.strip() != ""]
                groups.append({"name": name, "duskOffset": duskOffset,
                               "dawnOffset": dawnOffset, "lightNames": lightNames})
        finally:
            fh.close()
    except Exception as ex:
        print("[StreetLightController] Could not load configuration: " + str(ex))
    return groups


def SaveStreetLightGroups(groups):
    path = GetConfigPath()
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    tempPath = path + ".tmp"
    fh = open(tempPath, "w")
    try:
        writer = csv.DictWriter(fh, fieldnames=CONFIG_COLUMNS, delimiter="\t",
                                lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for group in groups:
            writer.writerow({
                "group_name": group["name"],
                "dusk_offset_seconds": str(int(group["duskOffset"])),
                "dawn_offset_seconds": str(int(group["dawnOffset"])),
                "light_system_names": ";".join(group["lightNames"])
            })
    finally:
        fh.close()
    if os.path.isfile(path):
        os.remove(path)
    os.rename(tempPath, path)


def _FormatClockSeconds(totalSeconds):
    try:
        value = int(totalSeconds) % 86400
        hours = value // 3600
        minutes = (value % 3600) // 60
        seconds = value % 60
        if seconds == 0:
            return "%02d:%02d" % (hours, minutes)
        return "%02d:%02d:%02d" % (hours, minutes, seconds)
    except Exception:
        return "unavailable"


def _ReadPublishedSolarSecond(suffix):
    memory = TBL.FindMemoryBySuffix(suffix)
    if memory is None or memory.getValue() is None:
        return None
    try:
        return int(str(memory.getValue()).strip()) % 86400
    except Exception:
        return None


class DurationEditor(JPanel):
    def __init__(self, initialSeconds=0):
        JPanel.__init__(self, FlowLayout(FlowLayout.LEFT, 3, 0))
        self.Sign = 1

        self.SignButton = JButton("+")
        self.SignButton.setMargin(Insets(1, 5, 1, 5))
        self.SignButton.setToolTipText("Click to change between before (-) and after (+).")
        self.SignButton.addActionListener(lambda event: self._ToggleSign())

        self.HoursSpinner = self._MakeSpinner(0, 0, 999, 1, "00")
        self.MinutesSpinner = self._MakeSpinner(0, 0, 59, 1, "00")
        self.SecondsSpinner = self._MakeSpinner(0, 0, 59, 1, "00")

        self.add(self.SignButton)
        self.add(self.HoursSpinner)
        self.add(JLabel(":"))
        self.add(self.MinutesSpinner)
        self.add(JLabel(":"))
        self.add(self.SecondsSpinner)
        self.setSeconds(initialSeconds)

    def _MakeSpinner(self, value, minimum, maximum, step, pattern):
        spinner = JSpinner(SpinnerNumberModel(value, minimum, maximum, step))
        spinner.setEditor(JSpinner.NumberEditor(spinner, pattern))
        editorField = spinner.getEditor().getTextField()
        editorField.setColumns(2 if pattern == "00" else len(pattern))
        editorField.setHorizontalAlignment(JTextField.RIGHT)
        return spinner

    def _ToggleSign(self):
        self.Sign = -self.Sign
        self.SignButton.setText("-" if self.Sign < 0 else "+")

    def _CommitEditors(self):
        self.HoursSpinner.commitEdit()
        self.MinutesSpinner.commitEdit()
        self.SecondsSpinner.commitEdit()

    def getSeconds(self):
        self._CommitEditors()
        hours = int(self.HoursSpinner.getValue())
        minutes = int(self.MinutesSpinner.getValue())
        seconds = int(self.SecondsSpinner.getValue())
        return self.Sign * (hours * 3600 + minutes * 60 + seconds)

    def setSeconds(self, totalSeconds):
        totalSeconds = int(totalSeconds)
        self.Sign = -1 if totalSeconds < 0 else 1
        value = abs(totalSeconds)
        hours = value // 3600
        minutes = (value % 3600) // 60
        seconds = value % 60
        if hours > 999:
            hours = 999
            minutes = 59
            seconds = 59
        self.SignButton.setText("-" if self.Sign < 0 else "+")
        self.HoursSpinner.setValue(hours)
        self.MinutesSpinner.setValue(minutes)
        self.SecondsSpinner.setValue(seconds)

    def setEnabled(self, enabled):
        JPanel.setEnabled(self, enabled)
        for component in [self.SignButton, self.HoursSpinner, self.MinutesSpinner, self.SecondsSpinner]:
            component.setEnabled(enabled)



def _LightDisplayName(light):
    systemName = str(light.getSystemName())
    try:
        userName = light.getUserName()
        if userName is not None and str(userName).strip() != "":
            return systemName + " - " + str(userName).strip()
    except Exception:
        pass
    return systemName


class StreetLightConfigDialog(JDialog):
    def __init__(self, owner=None):
        JDialog.__init__(self, owner, "Configure street lights", True)
        self.setDefaultCloseOperation(JDialog.DISPOSE_ON_CLOSE)
        self.Groups = LoadStreetLightGroups()
        self.SelectedIndex = -1
        self.LightBySystemName = {}
        self.setLayout(BorderLayout(8, 8))
        self._LoadJmriLights()
        self._BuildUi()
        self._RefreshGroups()
        self.setSize(850, 560)
        self.setMinimumSize(Dimension(760, 480))
        self.setLocationRelativeTo(owner)

    def _LoadJmriLights(self):
        manager = jmri.InstanceManager.getDefault(jmri.LightManager)
        try:
            beans = list(manager.getNamedBeanSet())
        except Exception:
            beans = []
        beans.sort(key=lambda bean: _LightDisplayName(bean).lower())
        for light in beans:
            self.LightBySystemName[str(light.getSystemName())] = light

    def _BuildUi(self):
        left = JPanel(BorderLayout(4, 4))
        left.add(JLabel("Lighting groups"), BorderLayout.NORTH)
        self.GroupModel = DefaultListModel()
        self.GroupList = JList(self.GroupModel)
        self.GroupList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        left.add(JScrollPane(self.GroupList), BorderLayout.CENTER)
        createButton = JButton("Create new lighting group...")
        deleteButton = JButton("Delete group")
        buttonRow = JPanel()
        buttonRow.add(createButton)
        buttonRow.add(deleteButton)
        left.add(buttonRow, BorderLayout.SOUTH)

        right = JPanel(GridBagLayout())
        gbc = GridBagConstraints()
        gbc.insets = Insets(4, 4, 4, 4)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        gbc.gridx = 0
        gbc.gridy = 0
        right.add(JLabel("Group name:"), gbc)
        gbc.gridx = 1
        self.NameField = JTextField(24)
        right.add(self.NameField, gbc)

        gbc.gridx = 0
        gbc.gridy = 1
        gbc.gridwidth = 2
        self.SolarTimesLabel = JLabel(self._GetSolarTimesText())
        right.add(self.SolarTimesLabel, gbc)

        gbc.gridwidth = 1
        gbc.gridx = 0
        gbc.gridy = 2
        right.add(JLabel("Turn on offset from sunset (HH:MM:SS):"), gbc)
        gbc.gridx = 1
        gbc.weightx = 0.0
        gbc.fill = GridBagConstraints.NONE
        gbc.anchor = GridBagConstraints.WEST
        self.DuskOffsetEditor = DurationEditor(0)
        self.DuskOffsetEditor.setToolTipText("Use - for before sunset and + for after sunset.")
        right.add(self.DuskOffsetEditor, gbc)

        gbc.gridx = 0
        gbc.gridy = 3
        right.add(JLabel("Turn off offset from sunrise (HH:MM:SS):"), gbc)
        gbc.gridx = 1
        self.DawnOffsetEditor = DurationEditor(0)
        self.DawnOffsetEditor.setToolTipText("Use - for before sunrise and + for after sunrise.")
        right.add(self.DawnOffsetEditor, gbc)

        lists = JPanel(GridBagLayout())
        lg = GridBagConstraints()
        lg.insets = Insets(4, 4, 4, 4)
        lg.gridy = 0
        lg.weightx = 1.0
        lg.fill = GridBagConstraints.HORIZONTAL
        lg.gridx = 0
        lists.add(JLabel("Available JMRI Lights"), lg)
        lg.gridx = 2
        lists.add(JLabel("Lights in this group"), lg)
        lg.gridy = 1
        lg.weighty = 1.0
        lg.fill = GridBagConstraints.BOTH
        lg.gridx = 0
        self.AvailableModel = DefaultListModel()
        self.AvailableList = JList(self.AvailableModel)
        self.AvailableList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
        lists.add(JScrollPane(self.AvailableList), lg)
        lg.gridx = 1
        lg.weightx = 0.0
        controls = JPanel(GridBagLayout())
        addButton = JButton("Add >")
        removeButton = JButton("< Remove")
        cg = GridBagConstraints()
        cg.gridy = 0
        controls.add(addButton, cg)
        cg.gridy = 1
        controls.add(removeButton, cg)
        lists.add(controls, lg)
        lg.gridx = 2
        lg.weightx = 1.0
        self.AssignedModel = DefaultListModel()
        self.AssignedList = JList(self.AssignedModel)
        self.AssignedList.setSelectionMode(ListSelectionModel.MULTIPLE_INTERVAL_SELECTION)
        lists.add(JScrollPane(self.AssignedList), lg)

        gbc.gridx = 0
        gbc.gridy = 4
        gbc.gridwidth = 2
        gbc.weightx = 1.0
        gbc.weighty = 1.0
        gbc.anchor = GridBagConstraints.CENTER
        gbc.fill = GridBagConstraints.BOTH
        right.add(lists, gbc)

        split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, left, right)
        split.setDividerLocation(245)
        self.add(split, BorderLayout.CENTER)

        bottom = JPanel()
        saveButton = JButton("Save")
        cancelButton = JButton("Cancel")
        bottom.add(saveButton)
        bottom.add(cancelButton)
        self.add(bottom, BorderLayout.SOUTH)

        self.GroupList.addListSelectionListener(lambda event: self._GroupSelected(event))
        createButton.addActionListener(lambda event: self._CreateGroup())
        deleteButton.addActionListener(lambda event: self._DeleteGroup())
        addButton.addActionListener(lambda event: self._AddLights())
        removeButton.addActionListener(lambda event: self._RemoveLights())
        saveButton.addActionListener(lambda event: self._Save())
        cancelButton.addActionListener(lambda event: self.dispose())

    def _GetSolarTimesText(self):
        sunrise = _ReadPublishedSolarSecond("SUNRISESECONDS")
        sunset = _ReadPublishedSolarSecond("SUNSETSECONDS")
        dayMemory = TBL.FindMemoryBySuffix("DAYOFWEEK")
        dayName = "Today"
        try:
            value = dayMemory.getValue() if dayMemory is not None else None
            if value is not None and str(value).strip() != "":
                dayName = str(value).strip()
        except Exception:
            pass
        if sunrise is None or sunset is None:
            return "Today's sunrise and sunset are unavailable until the day/night cycle is running. Times vary through the week."
        return "%s: sunrise %s; sunset %s. Times vary through the week." % (
            dayName, _FormatClockSeconds(sunrise), _FormatClockSeconds(sunset))


    def _CommitCurrent(self, showErrors=True):
        if self.SelectedIndex < 0 or self.SelectedIndex >= len(self.Groups):
            return True
        try:
            name = str(self.NameField.getText()).strip()
            if name == "":
                raise ValueError("Enter a name for the lighting group.")
            for index, group in enumerate(self.Groups):
                if index != self.SelectedIndex and group["name"].strip().lower() == name.lower():
                    raise ValueError("Lighting group names must be unique.")
            try:
                duskOffset = self.DuskOffsetEditor.getSeconds()
                dawnOffset = self.DawnOffsetEditor.getSeconds()
            except Exception:
                raise ValueError("Enter each offset in signed HH:MM:SS format, for example -00:10:00.")
            lightNames = []
            for index in range(self.AssignedModel.getSize()):
                lightNames.append(str(self.AssignedModel.getElementAt(index)).split(" - ", 1)[0])
            self.Groups[self.SelectedIndex] = {"name": name, "duskOffset": duskOffset,
                                               "dawnOffset": dawnOffset, "lightNames": lightNames}
            return True
        except Exception as ex:
            if showErrors:
                JOptionPane.showMessageDialog(self, str(ex), "Street-light configuration", JOptionPane.WARNING_MESSAGE)
            return False

    def _RefreshGroups(self, selectIndex=None):
        self.GroupModel.clear()
        for group in self.Groups:
            self.GroupModel.addElement(group["name"])
        if selectIndex is None and len(self.Groups) > 0:
            selectIndex = 0
        if selectIndex is not None and selectIndex >= 0 and selectIndex < len(self.Groups):
            self.GroupList.setSelectedIndex(selectIndex)

    def _GroupSelected(self, event):
        if event.getValueIsAdjusting():
            return
        newIndex = self.GroupList.getSelectedIndex()
        if newIndex == self.SelectedIndex:
            return
        if self.SelectedIndex >= 0 and not self._CommitCurrent(True):
            self.GroupList.setSelectedIndex(self.SelectedIndex)
            return
        self.SelectedIndex = newIndex
        self._LoadSelectedGroup()

    def _LoadSelectedGroup(self):
        enabled = self.SelectedIndex >= 0 and self.SelectedIndex < len(self.Groups)
        for component in [self.NameField, self.DuskOffsetEditor, self.DawnOffsetEditor,
                          self.AvailableList, self.AssignedList]:
            component.setEnabled(enabled)
        self.AvailableModel.clear()
        self.AssignedModel.clear()
        if not enabled:
            self.NameField.setText("")
            return
        group = self.Groups[self.SelectedIndex]
        self.NameField.setText(group["name"])
        self.DuskOffsetEditor.setSeconds(int(group["duskOffset"]))
        self.DawnOffsetEditor.setSeconds(int(group["dawnOffset"]))
        assigned = set(group["lightNames"])
        assignedElsewhere = set()
        for index, otherGroup in enumerate(self.Groups):
            if index == self.SelectedIndex:
                continue
            for systemName in otherGroup["lightNames"]:
                assignedElsewhere.add(systemName)
        for systemName in sorted(self.LightBySystemName.keys()):
            displayName = _LightDisplayName(self.LightBySystemName[systemName])
            if systemName in assigned:
                self.AssignedModel.addElement(displayName)
            elif systemName not in assignedElsewhere:
                self.AvailableModel.addElement(displayName)

    def _CreateGroup(self):
        if not self._CommitCurrent(True):
            return
        name = JOptionPane.showInputDialog(self, "Name for the new lighting group:", "Create new lighting group", JOptionPane.QUESTION_MESSAGE)
        if name is None:
            return
        name = str(name).strip()
        if name == "":
            return
        for group in self.Groups:
            if group["name"].lower() == name.lower():
                JOptionPane.showMessageDialog(self, "A lighting group with that name already exists.", "Street-light configuration", JOptionPane.WARNING_MESSAGE)
                return
        self.Groups.append({"name": name, "duskOffset": 0, "dawnOffset": 0, "lightNames": []})
        self.SelectedIndex = -1
        self._RefreshGroups(len(self.Groups) - 1)

    def _DeleteGroup(self):
        index = self.GroupList.getSelectedIndex()
        if index < 0:
            return
        if JOptionPane.showConfirmDialog(self, "Delete the selected lighting group?", "Delete lighting group", JOptionPane.YES_NO_OPTION) != JOptionPane.YES_OPTION:
            return
        del self.Groups[index]
        self.SelectedIndex = -1
        self._RefreshGroups(min(index, len(self.Groups) - 1))
        if len(self.Groups) == 0:
            self._LoadSelectedGroup()

    def _MoveSelected(self, sourceList, sourceModel, targetModel):
        values = list(sourceList.getSelectedValuesList())
        for value in values:
            targetModel.addElement(value)
            sourceModel.removeElement(value)

    def _AddLights(self):
        self._MoveSelected(self.AvailableList, self.AvailableModel, self.AssignedModel)

    def _RemoveLights(self):
        self._MoveSelected(self.AssignedList, self.AssignedModel, self.AvailableModel)

    def _Save(self):
        if not self._CommitCurrent(True):
            return
        used = {}
        for group in self.Groups:
            if len(group["lightNames"]) == 0:
                JOptionPane.showMessageDialog(self, "Every lighting group must contain at least one JMRI Light.", "Street-light configuration", JOptionPane.WARNING_MESSAGE)
                return
            for systemName in group["lightNames"]:
                if systemName in used:
                    JOptionPane.showMessageDialog(self, "JMRI Light " + systemName + " is assigned to both " + used[systemName] + " and " + group["name"] + ".", "Street-light configuration", JOptionPane.WARNING_MESSAGE)
                    return
                used[systemName] = group["name"]
        try:
            SaveStreetLightGroups(self.Groups)
            self.dispose()
        except Exception as ex:
            JOptionPane.showMessageDialog(self, "Could not save the street-light configuration.\n\n" + str(ex), "Street-light configuration", JOptionPane.ERROR_MESSAGE)


def ShowStreetLightConfigDialog(owner=None):
    dialog = StreetLightConfigDialog(owner)
    dialog.setVisible(True)
    return len(LoadStreetLightGroups()) > 0


class StreetLightController(jmri.jmrit.automat.AbstractAutomaton):
    def init(self):
        self.Groups = LoadStreetLightGroups()
        self.LightManager = jmri.InstanceManager.getDefault(jmri.LightManager)
        self.Timebase = jmri.InstanceManager.getDefault(jmri.Timebase)
        self.DayMemory = TBL.FindMemoryBySuffix("DAYOFWEEK")
        self.SunriseMemory = TBL.FindMemoryBySuffix("SUNRISESECONDS")
        self.SunsetMemory = TBL.FindMemoryBySuffix("SUNSETSECONDS")
        self.SolarDayMemory = TBL.FindMemoryBySuffix("SOLARDAY")
        self.ResolvedGroups = []
        for group in self.Groups:
            lights = []
            for systemName in group["lightNames"]:
                light = self.LightManager.getBySystemName(systemName)
                if light is None:
                    print("[StreetLightController] JMRI Light not found: " + systemName)
                else:
                    lights.append(light)
            if len(lights) > 0:
                self.ResolvedGroups.append((group, lights))
        if self.SunriseMemory is None or self.SunsetMemory is None:
            print("[StreetLightController] Waiting for DayNight.py to publish sunrise and sunset.")
        print("[StreetLightController] Loaded %d configured group(s); resolved %d active group(s)." %
              (len(self.Groups), len(self.ResolvedGroups)))

        # Set the correct state immediately at layout start. AbstractAutomaton.start()
        # calls init() before entering the repeating handle() cycle.
        self._ApplyCurrentState()

    def _RefreshMemories(self):
        if self.DayMemory is None:
            self.DayMemory = TBL.FindMemoryBySuffix("DAYOFWEEK")
        if self.SunriseMemory is None:
            self.SunriseMemory = TBL.FindMemoryBySuffix("SUNRISESECONDS")
        if self.SunsetMemory is None:
            self.SunsetMemory = TBL.FindMemoryBySuffix("SUNSETSECONDS")
        if self.SolarDayMemory is None:
            self.SolarDayMemory = TBL.FindMemoryBySuffix("SOLARDAY")

    def _CurrentSecondOfDay(self):
        calendar = java.util.Calendar.getInstance()
        calendar.setTime(self.Timebase.getTime())
        return (calendar.get(java.util.Calendar.HOUR_OF_DAY) * 3600 +
                calendar.get(java.util.Calendar.MINUTE) * 60 +
                calendar.get(java.util.Calendar.SECOND))

    def _ReadSolarSecond(self, memory):
        if memory is None or memory.getValue() is None:
            return None
        try:
            return int(str(memory.getValue()).strip()) % 86400
        except Exception:
            return None

    def _ApplyCurrentState(self):
        self._RefreshMemories()
        sunrise = self._ReadSolarSecond(self.SunriseMemory)
        sunset = self._ReadSolarSecond(self.SunsetMemory)
        currentDay = None
        solarDay = None
        try:
            if self.DayMemory is not None and self.DayMemory.getValue() is not None:
                currentDay = str(self.DayMemory.getValue()).strip()
            if self.SolarDayMemory is not None and self.SolarDayMemory.getValue() is not None:
                solarDay = str(self.SolarDayMemory.getValue()).strip()
        except Exception:
            currentDay = None
            solarDay = None

        # If DayNight.py publishes SOLARDAY, use it as the atomic snapshot guard.
        # Older compatible DayNight.py versions publish sunrise and sunset only.
        solarSnapshotReady = (solarDay is None or solarDay == "" or currentDay == solarDay)
        if sunrise is None or sunset is None or not solarSnapshotReady:
            return False

        now = self._CurrentSecondOfDay()
        for group, lights in self.ResolvedGroups:
            onSecond = (sunset + int(group["duskOffset"])) % 86400
            offSecond = (sunrise + int(group["dawnOffset"])) % 86400
            if onSecond == offSecond:
                shouldBeOn = False
            elif onSecond < offSecond:
                shouldBeOn = now >= onSecond and now < offSecond
            else:
                shouldBeOn = now >= onSecond or now < offSecond
            target = jmri.Light.ON if shouldBeOn else jmri.Light.OFF
            for light in lights:
                try:
                    if light.getState() != target:
                        light.setState(target)
                except Exception as ex:
                    print("[StreetLightController] Could not command " + str(light.getSystemName()) + ": " + str(ex))
        return True

    def handle(self):
        self._ApplyCurrentState()
        self.waitMsec(250)
        return True


def StartStreetLightController():
    controller = StreetLightController()
    controller.setName("TAS street-light controller")
    controller.start()
    return controller


streetLightController = StartStreetLightController()
