Read when: Task modifies or debugs TASBeanLookup.py or Memory access.

# TASBeanLookup.py

File: TASBeanLookup.py. Lines: 349.

Purpose: prefix-independent Memory lookup by suffix.

Exported functions:
- FindMemoryBySuffix(suffix)
- SafeGetMemoryValue(suffix, default)
- ProvideMemoryBySuffix(suffix, default)
- SafeGetOrCreateMemoryValue(suffix, default)
- SafeSetMemoryValue(suffix, value)

Internal functions:
- _NormSuffix
- _PreferredInternalPrefixes
- _SelectBySuffixWithPreference
- _IsNestedImSystemName
- _FindAllMatchesBySuffix
- _WarnIfCollision
- _ForensicDump

Globals: ENABLE_TASBEANLOOKUP_FORENSICS, LOG_TASBEANLOOKUP_ALL_CREATES, _WARNED_COLLISIONS, _FORENSIC_LOCK with java.util.concurrent.locks.ReentrantLock.

JMRI calls:
- jmri.InstanceManager.memoryManagerInstance()
- jmri.InstanceManager.getDefault(jmri.MemoryManager)
- memManager.getSystemPrefix()
- memManager.getSystemNamePrefix()
- memManager.isValidSystemNameFormat()
- memManager.makeSystemName()
- memManager.getNamedBeanSet()
- memManager.provideMemory()
- mem.getSystemName()
- mem.getValue()
- mem.setValue()

Behavior: FindMemoryBySuffix searches NamedBeanSet for system names ending with the suffix after normalisation. ProvideMemoryBySuffix creates the Memory when absent. SafeGetOrCreateMemoryValue returns value or default and creates when absent. SafeSetMemoryValue sets value on provided Memory.

Open question: none. Facts verified against file content read in this session.
