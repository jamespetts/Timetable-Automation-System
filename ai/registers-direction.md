Read when: Task concerns NormalDirectionRegister.py, LastReportedDirection.py, OrientationRegister.py, PlatformAllocationRegister.py, TrainLocatorRegister.py, formationRegister.py, RosterSearch.py, roster ID normalisation, reporting number defaults TAS plus row number.

# Registers and Direction

NormalDirectionRegister.py maps roster ID to normal direction string. Functions: SetNormalDirection(RosterId, Direction), GetNormalDirection(RosterId, Default), ToggleNormalDirection(RosterId, A, B), RemoveNormalDirection(RosterId), ClearAll, Count, GetCopy, ListIds, Save, Load. File is profile:normalDirectionRegister.json. Keys are normalised with _NormId(s) = str(s).strip().lower(). Direction values are stored with _CleanDirection(s) = str(s).strip() with no case change. GetCopy returns dict of lowercased roster ID to direction string. ToggleNormalDirection compares lowercased current value to A.lower() and B.lower().

LastReportedDirection.py monitors LocoNet E0 messages with opcode 0xE0 through class LastDirectionListener extends LocoNetListener with method message(self, msg). It stores dict lastReportedDirection of roster ID display case to direction string West, East, North, South, Unknown. File is profile:LastReportedDirection.json. It uses jmri.jmrit.roster.Roster.getDefault().getEntriesByDccAddress(dccAddressStr) to map DCC address to roster entries. Comparison of reported direction to normal direction uses str(value).strip().lower(). Rule: if reported equals normal, ensure roster ID is not in OrientationRegister; if reported differs, ensure roster ID is in OrientationRegister; if no normal entry, take no action.

OrientationRegister.py stores list orientation of roster ID strings. Functions: AddTrain(rosterID), GetTrain(index), RemoveTrain(rosterID), GetOrientationRegisterCopy, CountTrains, IsContained(rosterID), save, load. File is profile:OrientationRegister.json. Comparisons use exact equality with no strip and no case change.

PlatformAllocationRegister.py stores platform strings in register = Hashtable(). Functions: registerPlatform(reportingNumber, platform), getPlatform(reportingNumber), deregisterPlatform(reportingNumber), updatePlatform(reportingNumber, platform), addPlatformListener(listener), removePlatformListener(listener), save, load. File is profile:platform_allocation_register.json. Keys are used verbatim with no normalisation. Change notification uses jmri.beans.PropertyChangeSupport with firePropertyChange("platformAllocationChanged", ...).

TrainLocatorRegister.py stores dict _register of reporting number to roster ID with threading.RLock. Functions: registerTrain(reportingNumber, rosterId), deregisterTrain(reportingNumber), deregisterByRosterId(rosterId), getRosterId(reportingNumber), reverseLookup(rosterId), snapshot, save, load. File is profile:train_locator_register.json. Normalisation is str(value).strip() with case-sensitive equality. registerTrain enforces one roster ID maps to one reporting number by deleting stale keys with same roster ID.

formationRegister.py stores register = Hashtable() of next reporting number to roster ID. Functions: registerNextFormation(nextReportingNumber, rosterId), getTrainForFormation(nextReportingNumber), deregisterTrain(nextReportingNumber), save, load. File is profile:formation_register.json. Keys are used verbatim with no normalisation.

RosterSearch.py defines rosterSearch(idList, modelList, commentList). It uses jmri.jmrit.roster.Roster.getDefault().getAllEntries() with entry.getId(), entry.getModel(), entry.getComment(). Matching is case-insensitive substring: tok.lower() in text.lower(). Whitespace-only tokens are ignored. None or empty list means field ignored. List containing None means field required.

Reporting number defaults: TASUtil.MakeDefaultReportingNumberFromRow(rowNumber) returns TAS plus rowNumber. TASSetup._NormRN(s) = str(s).strip().upper(). TASSetup._MakeDefaultRN(rowNumber) = TAS plus int(rowNumber).

Detailed topics:
- ai/details/registers-direction.md
- ai/details/platform-trainlocator-formation-rostersearch.md
