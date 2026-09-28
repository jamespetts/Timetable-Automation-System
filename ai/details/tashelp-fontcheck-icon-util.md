Read when: Task modifies or debugs TASHelp.py, tashelp/*.txt, TASFontCheck.py, TASIcon.py, or TASUtil.py.

# TASHelp FontCheck Icon Util

File TASHelp.py lines: 334. Defines Show(initialTopic="General"). Help directory is jmri.util.FileUtil.getProfilePath() + "/jython/tashelp". File open is tashelpDir + "/" + topicName + ".txt" with Python open. Inner functions LoadContent, SelectInitialTopic, CurrentQuery, FilterTopics, SetPlaceholderActive, OnEnter, OnSelection. Inner classes _DocListener implements DocumentListener, _FocusHandler extends FocusAdapter, _FocusOnOpen extends WindowAdapter, _SetIconOnOpen extends WindowAdapter. Uses TASIcon.CreateClockIconImage(32) and frame.setIconImage. Called by TimetableAutomation.RunExternalScript(TASHelp.py, Help) which execfiles the file then calls Show(). Default Show argument is General.

tashelp/ files observed (10 files):
Day and night cycle.txt, Disruption.txt, Enqueued workings.txt, General.txt, Public Information Displays.txt, Signallers' displays.txt, Time warp.txt, Timetable.txt, Train orientation.txt, Workings.txt.

File TASFontCheck.py lines: 1423. Defines class FontRequirement, class FontCheckResult, class StatusCellRenderer, class FontsFrame. Functions _NormalizeFamily, _CanonFamily, _CanonVariants, _IsLogicalFont, _LooksLikeFontName, _ProfileJythonDir, _ProfileDir, _ShouldSkipFile, _ListProfileScripts, _ReadText, _AvailableFontFamilies, _ReadMemStrSuffix, _HasInstalledDigital7MonoFamily, _FileExistsAny, _StripDocstringsAndFullLineComments, _ExtractQuotedStrings, _FindMatchingBracket, _ExtractPrefsLists, _ExtractFontCtorFamilies, _ExtractPickFamilyCandidateLists, BuildRequirementsFromProfileScripts, EvaluateRequirements, RunFontCheckDialog, GetFontCheckResults, CountMissingFonts, RunFontCheck, GetMissingFontsCount with GetFontCheckResults CountMissingFonts RunFontCheck defined twice verbatim at end of file. Constants LOGICAL_FONTS, JOHNSTON_EQUIV, LIGHTBOX_ACCEPTABLE, LIGHTBOX_FALLBACK_ONLY, GENERIC_FALLBACKS, READ_LIMIT, SKIP_PREFIXES, OK_BG WARN_BG BAD_BG NEUTRAL_BG. Scans profile:jython/*.py skipping TASFontCheck prefix, compares to GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames(), displays colour-coded report with DuckDuckGo links. Does not install fonts. Memory TAS_FONT_FAMILY through TASBeanLookup.SafeGetMemoryValue. Uses TASIcon.SetFrameClockIcon.

File TASIcon.py lines: 142. Defines _Log, _LogExc, CreateClockIconImage, SetFrameClockIcon. Drawing is 10:10 with red second hand at 8. Uses java.awt.Color BasicStroke RenderingHints, java.awt.image.BufferedImage, java.lang.Math, java.lang.System, Frame.setIconImage(img), Frame.getTitle(). No Memories, no files. Called by TimetableAutomation.TASWTTStartup, TASFontCheck.FontsFrame, TASHelp.

File TASUtil.py lines: 52. Defines IsDefaultReportingNumber and MakeDefaultReportingNumberFromRow. MakeDefaultReportingNumberFromRow(rowNumber) returns TAS + rowNumber. IsDefaultReportingNumber returns true when s starts with TAS and remainder is alphanumeric. No JMRI dependency, no Memories, no files.

Open question: none. Facts verified against file content read in this session.
