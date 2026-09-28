Read when: Task concerns JMRI Memories, Memory suffix lookup, SafeGetOrCreateMemoryValue, SafeGetMemoryValue, SafeSetMemoryValue, ProvideMemoryBySuffix, FindMemoryBySuffix, prefix handling for IM and InM.

# Memories and TASBeanLookup

Runtime settings are stored in JMRI Memories. Access is through TASBeanLookup.py. TASBeanLookup.py provides prefix-independent lookup by suffix.

Functions in TASBeanLookup.py:
- FindMemoryBySuffix
- SafeGetMemoryValue
- ProvideMemoryBySuffix
- SafeGetOrCreateMemoryValue
- SafeSetMemoryValue
- Internal: _NormSuffix, _PreferredInternalPrefixes, _SelectBySuffixWithPreference, _FindAllMatchesBySuffix, _WarnIfCollision, _IsNestedImSystemName, _ForensicDump

TASBeanLookup.py uses jmri.InstanceManager.memoryManagerInstance() or jmri.InstanceManager.getDefault(jmri.MemoryManager). It uses memManager.getSystemPrefix(), memManager.getSystemNamePrefix(), memManager.isValidSystemNameFormat(), memManager.makeSystemName(), memManager.getNamedBeanSet(), memManager.provideMemory(). It uses mem.getSystemName(), mem.getValue(), mem.setValue().

TASBeanLookup.py defines ENABLE_TASBEANLOOKUP_FORENSICS, LOG_TASBEANLOOKUP_ALL_CREATES, _WARNED_COLLISIONS, _FORENSIC_LOCK with java.util.concurrent.locks.ReentrantLock.

Observed Memory suffixes used across the repository include:
CURRENTTIMETABLE, CURRENTTIME, DAYOFWEEK, ALLOWTIMEWARP, TASAUTOWORKING, ALLOWDELAYS, ALLOWCANCELLATIONS, DISRUPTIONSEEDBASE, WX_UI, WX_CLIMATE, WX_NEWS_STYLE, WX_NEWS_PAPERNAME, WX_FORECAST_ACCURACY, WX_SCHEMA, WX_FC_STEP_MIN, WX_FC_LENGTH, WX_FC_ISSUE_ABSMIN, WX_FC_POINTS, WX_UPDATED_ABSMIN, WX_FC_ISSUES, WX_FC_LIST, WX_FC_<issueAbsMin>, WX_FORECAST_ACCURACY duplicated as WX_FORECAST_ACCURACY, CLOUDCOVERPCT, PUBLICDISPLAYLIST, SIGNALLERDISPLAYLIST, TASCOVERCOLOUR, TASINNERCOLOUR, TASINKCOLOUR, TASCOVERINKCOLOUR, TASPAPERCOLOUR, TASWTTBANDLIGHT, TASWTTBANDDARK, TAS_FONT_FAMILY, RAILWAYCO, REGION, SECTION, WTT_PAGE_MODE, WTT_TIME_24H, WTT_TIME_SEPARATOR, WTT_TP_NAME_DOT_LEADERS, WTT_ECS_LABEL, WTT_ECS_DEST_MATCH, WTT_TIMING_LOAD_LABEL, WTT_REP_NO_LABEL, WTT_DIRECTION_SPLIT, WTT_OD_HEADER_VERTICAL, DAYNIGHT_PRESET, LOWCTTHROTTLEADDR, HIGHCTTHROTTLEADDR, MINNIGHTGLOW, TIMEWARPBLACKOUTSECONDS, TIMEWARPTHRESHOLDMINUTES, SUNRISESECONDS, SUNSETSECONDS, SOLARDAY, TASFASTCLOCKUSESAVEDSTARTUP, TASSAVEDFASTCLOCKTIME, TASTURNAROUNDMINUTES, PID_DEPARTURE_TP, PID_PLATFORM_OVERRIDES, PID_CRT_PAGE_SECONDS, PID_COMPANY_NAME, PID_CRT_WITHIN_MINUTES, PID_ECS_FILTER_TERMS, DAYNIGHT_PRESET duplicated, SPOOFADSENABLED, AD_ROTATE_SEC, AD_MODE, AD_COUNT, ADn_BRAND, ADn_L1, ADn_L2, ADn_CTA, TAS_USER_SETTING_ plus setting key, TASTURNAROUNDMINUTES duplicated.

Rule: code must use TASBeanLookup functions for Memory access. Code must not construct IM-prefixed Memory names directly except inside TASBeanLookup.py and the local wrappers in TASFastClockStartup.py that prefer TASBeanLookup when available.

Detailed topics:
- ai/details/tasbeanlookup.md
