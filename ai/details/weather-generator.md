Read when: Task modifies or debugs WeatherGenerator.py or climate.csv.

# WeatherGenerator.py

File: WeatherGenerator.py. Header states generation of cloud cover and rolling 48-hour forecast with Memories IMCURRENTTIME input, IMDAYOFWEEK input, IMCLOUDCOVERPCT output for NOW only. File states it needs to be a startup script.

Class WeatherGenerator extends jmri.jmrit.automat.AbstractAutomaton. Methods init and handle. Start code: weather = WeatherGenerator(); weather.setName("Weather generator"); weather.start().

Internal methods:
- _daily_event_params
- _true_cloud_pct_at
- _issue_time_for
- _forecast_values_for_issue
- _ensure_issue_present_for_time
- _ensure_forward_coverage
- _forecast_value_at
- _get_minutes_of_day
- _abs_minute_now
- _publish_issue_points

Module functions: _hash32, _prng01, _gauss, _lerp, _sigma_for_horizon, _dow_idx, _fmt_hhmm, _dow_name_from_abs_minute, _parse_float, _parse_int, _load_climate_from_tsv.

Constants: BASE_SEED, FORECAST_ISSUE_PERIOD_MIN, FORECAST_HOURS, FORECAST_STEP_MIN, FORECAST_ACCURACY, FORECAST_COVERAGE_MARGIN_MIN, LOG_FORECAST_ON_ISSUE, BUILTIN_CLIMATES, MODERN_SIGMA, VINTAGE_SIGMA.

Memories through TASBeanLookup: WX_CLIMATE, WX_FORECAST_ACCURACY, WX_SCHEMA, WX_FC_STEP_MIN, WX_FC_LENGTH, WX_FC_ISSUE_ABSMIN, WX_FC_POINTS, WX_UPDATED_ABSMIN, WX_FC_ISSUES, WX_FC_LIST, WX_FC_ plus issueAbsMin dynamic key, CURRENTTIME, DAYOFWEEK, CLOUDCOVERPCT.

Config file: profile:jython/TAS/config/climate.csv resolved through TASPathResolver.GetTASDir plus os.path.join config climate.csv else jmri.util.FileUtil.getExternalFilename("profile:jython/TAS/config/climate.csv"). Format is tab-delimited with csv.DictReader delimiter tab.

JMRI APIs: jmri.jmrit.automat.AbstractAutomaton, jmri.InstanceManager.getDefault(jmri.Timebase), jmri.InstanceManager.getDefault(jmri.MemoryManager), jmri.util.FileUtil.getExternalFilename, java.text.SimpleDateFormat, waitChange.

Open question: none. Facts verified against file content read in this session.
