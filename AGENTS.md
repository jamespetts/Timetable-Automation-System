# Timetable Automation System (TAS) — Agent Guide

## Project Overview
Jython 2.7 scripts for JMRI (Java Model Railroad Interface). Provides timetable automation, public/signaller displays, weather, day/night cycle, disruption generation, and time warp.

**Entry point:** `TimetableAutomation.py` — run via JMRI "Scripting > Run Script..."

**License:** GPL v3. All code files must have the standard GPL v. 3 header.

## Installation & Runtime
- Copy all files to JMRI profile's `jython/` directory (NOT program folder)
- First run prompts to set `scripts:` location to this folder; restart JMRI after
- Application scripts run inside JMRI; selected pure helper modules can be tested outside JMRI
- Target JMRI 5.16+ / Jython 2.7.

## Key Modules
| Module | Purpose |
|--------|---------|
| `TimetableAutomation.py` | Main menu, startup path/dual-install checks |
| `TASBeanLookup.py` | Prefix-independent JMRI Memory lookup and access across connections |
| `TASPathResolver.py` | Portable path resolution (profile:jython → scripts:) |
| `TASSetup.py` | Multi-tab configuration UI (General, Displays, Day/Night) |
| `TASWiz.py` | Setup wizard |
| `RunWTT.py` | Working timetable runner |
| `WTTDisplay.py` | Timetable display |
| `WeatherGenerator.py` / `WeatherForecastUI*.py` | Weather system |
| `DayTracker.py` / `DayNight.py` | Day/night cycle |
| `DisruptionGenerator.py` | Disruption system |
| `TimeWarp.py` / `TimeWarpChecker.py` | Time warp |
| `PID*.py` | Public information displays (many variants) |
| `TASHelp.py` | Help system (loads `tashelp/*.txt`) |

## Configuration
- Runtime settings are primarily stored in **JMRI Memories** and accessed prefix-independently via 'TASBeanLookup'
- Key memories: `CURRENTTIMETABLE`, `ALLOWTIMEWARP`, `WX_UI`, `CLOUDCOVERPCT`, `PUBLICDISPLAYLIST`, `SIGNALLERDISPLAYLIST`, `TASCOVERCOLOUR`, `TASINNERCOLOUR`, `TASINKCOLOUR`, `TAS_FONT_FAMILY`
- Timetable CSV in `profile:timetable/<name>.csv`
- Configuration files are stored under `profile:jython/config/`, including `daynight.csv`, `climate.csv`, and `streetlights.tsv`. The csv files are actually tab separated. 'streetlights.tsv' is automatically created only when street lights are configured by the user.

## Development Conventions
- **Single source of truth** - do not create competing authoritative stores for the same state; use shared utilities and derive or snapshot state where needed
- **ASCII only** — no non-ASCII chars in source
- **No hard-coded absolute paths** — use JMRI path schemes through FileUtil or TASPathResolver and resolve them at runtime
- **Thread-safe** — treat JMRI as threaded; protect shared state and perform Swing UI access on the Event Dispatch Thread
- **Jython 2.7 syntax** — no f-strings, type hints, or Python 3 features
- **Imports:** Use Jython-compatible imports for JMRI and Java classes, following existing local patterns
- **Window icons:** Use `TASIcon.SetFrameClockIcon()` for new TAS top-level windows; do not duplicate the clock-icon drawing code
- **Error handling:** Follow existing local patterns; log useful diagnostics and use JOptionPane only for errors requiring user attention
- **Version:** Defined by `VERSION` in TimetableAutomation.py
- **Time parsing:** Accept common 12-hour and 24-hour formats and normalise parsed times to minutes since midnight
- **Roster IDs:** Check each register's existing normalisation rules; NormalDirectionRegister is case-insensitive, while older register APIs may be case-sensitive
- **Help:** Update the relevant `tashelp/` text when adding or changing user-facing behaviour.
- **Changelog:** Update `changelog.txt` under the current version for significant features or user-facing changes.
- **SecretScriptDoNotRun.py:** This is an Easter egg game. Do not execute it unless explicitly asked to run it; execution opens a game window and may write a high-score file.

## Testing & Verification
- **No automated test suite** — verify by running in JMRI
- **Static validation** - Use static validation as below specified for every changed script
- Manual verification: Start JMRI → Scripting → Run `TimetableAutomation.py` → exercise menus. NOTE: when configured, TimetableAutomation.py is a startup script.
- Check console for `[TAS]` prefixed logs

### Static Validation

- Verify Jython 2.7 compatibility, ASCII-only source, and four-space indentation.
- Verify that new or changed references to TAS functions, classes, files, and configuration keys exist.
- Validate every new or changed JMRI API call against the publicly available
  JMRI 5.16 documentation.
- If the documentation is ambiguous, contradictory, incomplete, or inconsistent
  with observed behaviour, inspect the corresponding JMRI 5.16 source code on Github and
  relevant tests before relying on the API.


## Common Tasks
| Task | How |
|------|-----|
| Add a new PID display | Create `PID<Name>.py` following existing tagged display patterns; TASSetup.py discovers display scripts from their metadata comments |
| Add a help topic | Add `<topic>.txt` to `tashelp/`; will auto-appear in Help menu |
| Modify timetable format | Update the relevant readers/writers and verify compatibility with all example timetable schemas
| Change colours/fonts | Edit memories via Setup UI or directly in JMRI Memory Table |

## Gotchas
- **Dual-install detection:** TAS warns if scripts exist in both `profile:jython` and legacy `scripts:` — delete legacy copy
- **Startup script path mismatch:** TAS detects if Start-Up actions point to wrong copy; offers auto-fix
- **Scripts directory must be writable** — first-run check enforces this
- **Memory prefixes vary by connection** — always use `TASBeanLookup` (`SafeGetOrCreateMemoryValue`, etc.)
- **No pip/venv** — dependencies are JMRI core only

## File Layout
```
TAS devel/
├── TimetableAutomation.py      # Entry point
├── TASBeanLookup.py            # Bean lookup utility
├── TASPathResolver.py          # Path resolution
├── TASSetup.py                 # Configuration UI
├── TASWiz.py                   # Setup wizard
├── RunWTT.py                   # Timetable runner
├── WTTDisplay.py               # Timetable display
├── WeatherGenerator.py         # Weather engine
├── WeatherForecastUI*.py       # Weather UIs
├── DayTracker.py / DayNight.py # Day/night cycle
├── DisruptionGenerator.py      # Disruptions
├── TimeWarp*.py                # Time warp
├── PID*.py                     # Public displays (20+ variants)
├── TASScriptsPathGuard.py      # Startup path logic
├── TASHelp.py                  # Help system
├── tashelp/*.txt               # Help topics
├── config/daynight.csv         # Day/night config
├── config/climate.csv          # Climate config
├── Example timetables/*.csv    # Sample timetables
├── changelog.txt               # Version history
├── Licence.txt                 # GPL v3
└── Timetable Automation System installation instructions.txt
```

## Deprecated
* CheckTimetable.py