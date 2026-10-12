# Train detection

## Overview

This tab shows what entries in the roster are capable of working with RailCom and which entries currently have RailCom enabled, allowing easy enabling/disabling of RailCom. One of the main reasons temporarily to disable RailCom is for double heading: two RailCom compatible locomotives in one section confuse the RailCom reader, so it is advisable to disable RailCom on one locomotive of the two before starting double heading. Enabling/disabling RailCom dynamically is only possible if your command station supports programming on main.

## The window

The upper pane is split into two halves. RailCom capable roster entries are on the left, the others are shown on the right.

The colour of an entry shows its state. Each colour means the same in both lists.

- Cyan: the decoder supports RailCom, RailCom is switched off, and this layout can program on main, so RailCom can be enabled on this item of rolling stock using this interface.
- Dark purple: the decoder supports RailCom but RailCom is switched off and this layout cannot program on main.
- Dark blue: RailCom is switched on for this entry.
- Orange: you have marked the entry as not RailCom capable. These entries are on the right.
- Brown: the decoder does not support RailCom at all. These entries are on the right.

## Enabling and disabling RailCom

Select an entry in the left-hand list and choose "Enable RailCom on selected". This writes the RailCom switch through programming on main, so the entry must be on the track with power applied. JMRI does not report a read of the present value during a programming on main write, so the value written is the decoder definition's own default for that switch with RailCom set on. The entry's roster values are not changed by this; the decoder itself is written.

To switch RailCom off again, for example before double heading, select the entry and choose "Disable RailCom on selected". This writes the RailCom switch off through programming on main in the same way; the entry must be on the track with power applied. The entry can be enabled again afterwards with "Enable RailCom on selected".

Programming on main support is tested when the tab opens. If your layout cannot program on main, the enable and disable buttons are disabled and RailCom must be enabled on the programming track using DecoderPro or using a different command station.

## Marking an entry as not RailCom capable

Some decoders report RailCom capability that the layout does not use, or a decoder reports itself as RailCom capable when no RailCom detector is fitted. Select the entry and choose "Mark selected as not RailCom capable". The entry moves to the right-hand list and is treated as having no RailCom, including by the initialisation fix below. Choose the same command again to clear the mark. This is stored in the configuration file, so it survives a restart.

## Lower half: the RailCom initialisation fix

Some RailCom decoders have an error in that they will not broadcast their address using RailCom until they have been addressed by the command station. This setting enables a workaround to this error by sending a brief command to the decoder on startup. Choose to which roster entries to apply this fix. You can choose a different function for each. Choose a function that is not used or should be off at startup.

The table repeats the roster entries whose RailCom is fully switched on, with the decoder make, model and firmware version alongside each, so entries with decoders known to need the fix can be picked out. Tick "Apply fix" for each entry that needs it. Select a row and set "Function for selected roster entry" to choose which function is sent to that entry; the input follows whichever row is selected. The default is F4.

Ticking the first entry runs the fix at once and sets RailComFix.py to run at start-up, so the fix applies each time JMRI starts. Unticking the last entry removes it from start-up again. You can also apply the fix at any time by running RailComFix.py with Scripting, Run script.

For each entry ticked, the fix acquires a throttle for that entry's DCC address, sends one function-off command, and releases the throttle. No speed setting is touched and no function is left on.

## Configuration file

Entry selections, marks, and functions are stored in profile:jython/TAS/config/railcomfix.tsv, which is tab separated with the columns roster_id, not_capable, fix and function. It is written each time you change a setting.

## How capability is decided

Across all 2112 decoder definitions shipped with JMRI, every decoder that offers RailCom offers an on and off switch on CV 29 at bit 3. This is true for every brand found, and it is the bit the NMRA specification gives to RailCom. Other CVs carry RailCom channel selection, quality of service and vendor extras, which change behaviour but do not switch RailCom on, so they are not used. CV 12 and CV 127 carry "CTC/Railcommand Power Conversion", which matches a RailCom name search but is unrelated to RailCom, so the CV number is checked as well as the name.

Whether RailCom is on is read from the value stored for the entry, not from the decoder definition default, so an entry that has been programmed is reported as it is.

All findings are written to the system console, each line starting with [TAS].
