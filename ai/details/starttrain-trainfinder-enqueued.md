Read when: Task modifies or debugs startTrain.py, trainFinder.py, enqueuedWorkings.py, retryEnqueuedWorkings.py, DispatcherFrame train creation, or enqueued retry.

# StartTrain TrainFinder Enqueued

File startTrain.py lines: 768. File trainFinder.py lines: 263. File enqueuedWorkings.py lines: 148. File retryEnqueuedWorkings.py lines: 77.

startTrain.py:
- Provides startTrain(traininfoName, rosterEntry, reportingNumber, direction, formsNext) returning activeTrain.
- Provides createActiveTrainFromTrainInfo(ti, rosterEntry).
- Defines local IsDefaultReportingNumber(s) as startswith "TAS" and x[3:].isdigit().
- Defines _TrainInfoXmlPath(nameOrFile) returning jmri.util.FileUtil.getExternalFilename("profile:dispatcher/traininfo/" + nm).
- Defines addMinutesToTime(minutes_to_add) reading CURRENTTIME with format %I:%M %p.
- Defines checkEndBlock(traininfoName) reading endblockid.
- Defines ResolveStartBlockFromTrainInfo(ti) using getStartBlockId, getStartBlockName, BlockManager getBlock, getByUserName, getNamedBean.
- Defines IsStartSectionAllocatedForBlock(startBlock) using SectionManager NamedBeanSet with sec.containsBlock, getBlockList, getState compared to jmri.Section.FREE.
- Defines tpGetMainName, tpGetBlocksSet with TR.getBlocks, tpBlockMatchesList, tpAnyTpBlockOccupied, tpGetTimeAndDay, tpRegister(reportingNumber, direction, kind="Dep") calling TR.registerTiming.
- Defines inner class ATListener extends java.beans.PropertyChangeListener with armDepartureOnPhysicalMove, BuildPhysicalTPBlockMap, AttachPhysicalTPListeners, propertyChange.
- Memories: CURRENTTIME, DAYOFWEEK, TASTURNAROUNDMINUTES through ProvideMemoryBySuffix. Sets ALLOWTIMEWARP to false through SafeSetMemoryValue.
- Registers formation only when formsNext is non-empty after strip.
- Uses DispatcherFrame with loadTrainFromTrainInfo, getActiveTrainForRoster, getActiveTrainName, getTransit, getStartBlock, getRosterEntry.
- Calls formationRegister.deregisterTrain, registerNextFormation, getTrainForFormation; enqueuedWorkings.popWorking, enqueueWorking; DisruptionRegister.getDisruption, deregisterDisruption; OrientationRegister.IsContained; TimingRegister as TR; TrainLocatorRegister as TLR; TASUtil as TU; TASBeanLookup as TBL; TASPathResolver.ResolveScriptReadPath("retryEnqueuedWorkings.py") with execfile.

trainFinder.py:
- Provides trainFinder(traininfoNames, rosterIds, reportingNumber).
- Two passes for passNum in [1, 2].
- Defines isTransitIdle(traininfoName) reading FileUtil.getProfilePath() + "/dispatcher/traininfo/" + name + ".xml" with ti.get("transitid") and jmri.Transit.IDLE.
- Requires blockManager.getBlock startblockid with block.getState() == jmri.Block.OCCUPIED.
- When reportingNumber is not None: checks formationRegister.getTrainForFormation(rnKey) first, then TLR.getRosterId(rnKeyUp), roster.getEntryForId. Skips traininfo when block value positively identifies a different roster entry. Returns (rosterEntry, traininfoName) only for matching stock. Returns (None, None) when no formation entry exists.
- Else: checks block.getValue() with roster.getEntry(int(text)) or getEntryForId(text) or TLR.getRosterId(text.upper()). Filters by rosterIds. Fallback checks DCC text stripping LD with getEntriesByDccAddress and prefers entry.getSpeedProfile().

enqueuedWorkings.py:
- Stores list workings of tuples (reportingNumber, direction).
- File _SAVE_PATH is FileUtil.getExternalFilename("profile:enqueuedWorkings.json") else os.path.join(FileUtil.getProfilePath(), "enqueuedWorkings.json").
- Functions: enqueueWorking, getEnqueuedWorking, dequeueWorking, popWorking, getEnqueuedWorkingsCopy, countWorkings, ClearWorkings, save, load.
- save uses tmp file with java.nio.file.Files.move REPLACE_EXISTING and ATOMIC_MOVE with fallback os.rename. load attempts 3 reads.
- Shutdown uses ShutDownManager.instance().addShutdownTask(save) else Runtime hook.

retryEnqueuedWorkings.py:
- Reads enqueuedWorkings.getEnqueuedWorkingsCopy().
- Reads Memory CURRENTTIMETABLE through TASBeanLookup.ProvideMemoryBySuffix.
- Reads timetable with csv.DictReader delimiter tab. Keys Reporting number, Forms. Empty Reporting number uses TASUtil.MakeDefaultReportingNumberFromRow(rowIndex). Empty Forms uses None.
- For each (reportingNumber, direction) calls TASPathResolver.ResolveWorkingScriptReadPath with fallback to scripts path join, then execfile(scriptName).

Open question: none. Facts verified against file content read in this session.
