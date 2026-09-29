Read when: Task modifies or debugs WeatherForecastUIApp.py or WeatherForecastUINewspaper.py.

# Weather UI

File WeatherForecastUIApp.py header states 2010s-style mobile app UI, UI frontend only, reads future weather published by WeatherGenerator.py with schema WG2, shows sunrise and sunset for current day.

Classes in WeatherForecastUIApp.py: Card extends JPanel, _WxAppSpinnerPanel extends JPanel, _WxAppAlertButton extends JButton, _WxAppAlertCard extends JPanel, _WxAppAlertDialog extends JDialog, BigIconPanel extends JPanel, MiniIconPanel extends JPanel, BlueCtaButton extends JButton, HourCell extends Card, AdBanner extends Card, PillButton extends JButton, NowBar extends Card, WeatherForecastUI extends jmri.jmrit.automat.AbstractAutomaton.

Methods in WeatherForecastUI include init, _cleanup, _minutes_of_day, _RunOnEdt, _Log, _abs_min_now, _read_points, _sunrise_sunset_for_abs, _setPage, _nearest_value_at, _page_midnight_abs, _read_int, _read_enabled, _read_str, _reload_ads_from_mem, _applyProTitle, _apply_ad_visibility_and_timer, _PushFirstAdIfNeeded, _advance_ad, _onAdTick, _runGlassOp, _forecast_ready, _show_loading, _hide_loading, _update_loading_state, _OwnerWindow, _ShowPaymentDeclined, _onTick, handle.

## App UI load sequence

init renders with _onTick before setVisible, on purpose. AbstractAutomaton.run runs init then handle, and waitChange blocks until a watched Memory changes, so the first render would otherwise arrive only after the 4000 ms refresh Timer initial delay.

_WxAppSpinnerPanel is an iOS-style twelve-spoke indicator on the window glass pane, animated by its own javax.swing.Timer. _update_loading_state, called at the end of _onTick, shows it only while _read_points is empty, and after WXAPP_LOADING_TIMEOUT_MS replaces the caption once and logs to the console. The series can genuinely be absent at start-up, because WeatherGenerator.py publishes from handle, which waits on the clock Memory.

Style decision: for this window the user chose a late-2010s mobile app look over design goal C1 skeuomorphism. Apply the same choice to further work here.

Memories in WeatherForecastUIApp.py: CURRENTTIME, DAYOFWEEK, CLOUDCOVERPCT, WX_SCHEMA, WX_FC_STEP_MIN, WX_FC_LENGTH, WX_FC_ISSUE_ABSMIN, WX_FC_POINTS, WX_UPDATED_ABSMIN, DAYNIGHT_PRESET, SPOOFADSENABLED, AD_ROTATE_SEC, AD_MODE, AD_COUNT, ADn_BRAND, ADn_L1, ADn_L2, ADn_CTA.

Config file: profile:jython/config/daynight.csv through TASPathResolver.GetProfileJythonDir else jmri.util.FileUtil.getExternalFilename("profile:jython/config/daynight.csv"). FALLBACK_SUN dict is defined in file.

WeatherForecastUIApp.py calls execfile on SecretScriptDoNotRun.py for one ad entry. SecretScriptDoNotRun.py must not be executed except when explicitly requested, but the ad click path in WeatherForecastUIApp.py is the documented caller.

File WeatherForecastUINewspaper.py defines class WeatherForecastNewspaper extends jmri.jmrit.automat.AbstractAutomaton. Method handle returns false for static edition. Supports modern and old styles with AM_START, AM_END, PM_START, PM_END half-day averaging.

Classes in WeatherForecastUINewspaper.py: RuleLine, Masthead, IconCanvas, ModernHalfRow, OldFlowLine, ModernAd, OldAd, SmallOldAd, WeatherForecastNewspaper.

Memories in WeatherForecastUINewspaper.py: CURRENTTIME, DAYOFWEEK, WX_FC_STEP_MIN, WX_FC_POINTS, WX_NEWS_STYLE, WX_NEWS_DAYS, WX_NEWS_PAPERNAME, DAYNIGHT_PRESET, SPOOFADSENABLED, AD_COUNT, ADn_BRAND, L1, L2, CTA.

Both files use TASBeanLookup.ProvideMemoryBySuffix, TASPathResolver, TASIcon.SetFrameClockIcon, jmri.InstanceManager.getDefault(jmri.Timebase and MemoryManager), jmri.util.JmriJFrame, javax.swing Timer JPanel JLabel.

Open question: none. Facts verified against file content and the JMRI 5.16 source of AbstractAutomaton, AbstractAutomaton.waitChange and JmriJFrame in this session.
