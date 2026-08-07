# Timetable Automation System (TAS) — Agent Guide

## Project Overview
Jython 2.7 scripts for JMRI (Java Model Railroad Interface). Provides timetable automation, public/signaller displays, weather, day/night cycle, disruption generation, and time warp.

**Entry point:** `TimetableAutomation.py` — run via JMRI "Scripting > Run Script..."

**License:** GPL v3. All files must have the standard GPL v. 3 header.

## Installation & Runtime
- Copy all files to JMRI profile's `jython/` directory (NOT program folder)
- First run prompts to set `scripts:` location to this folder; restart JMRI after
- Runs inside JMRI; no standalone execution
- Requires JMRI 5.12+ / Jython 2.7. Intended for JMRI 5.16+

## Key Modules
| Module | Purpose |
|--------|---------|
| `TimetableAutomation.py` | Main menu, startup path/dual-install checks |
| `TASBeanLookup.py` | Robust JMRI Memory/Turnout/Sensor lookup across connections |
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
- All settings stored in **JMRI Memories** (prefix-agnostic via `TASBeanLookup`)
- Key memories: `CURRENTTIMETABLE`, `ALLOWTIMEWARP`, `WX_UI`, `CLOUDCOVERPCT`, `PUBLICDISPLAYLIST`, `SIGNALLERDISPLAYLIST`, `TASCOVERCOLOUR`, `TASINNERCOLOUR`, `TASINKCOLOUR`, `TAS_FONT_FAMILY`
- Timetable CSV in `profile:timetable/<name>.csv`
- Config CSV files in `config/` (`daynight.csv`, `climate.csv`)

## Development Conventions
- **Single source of truth** - no multiple variables for the same single state anywhere
- **ASCII only** — no non-ASCII chars in source
- **No absolute paths** — use `profile:jython/...`, `scripts:...`, `profile:timetable/...` via `FileUtil` or `TASPathResolver`
- **Thread-safe** — SwingUtilities.invokeLater for UI updates
- **Jython 2.7 syntax** — no f-strings, type hints, or Python 3 features
- **Imports:** `import jmri`, `from javax.swing import ...`, `from java.awt import ...`
- **Error handling:** Log to console + show `JOptionPane` dialogs
- **Version:** Defined in `TimetableAutomation.py:22` (`VERSION = "1.5"`)

## Testing & Verification
- **No automated test suite** — verify by running in JMRI
- **Static validation** - Use static validation as below specified.
- Manual verification: Start JMRI → Scripting → Run `TimetableAutomation.py` → exercise menus. NOTE: when configured, TimetableAutomation.py is a startup script.
- Check console for `[TAS]` prefixed logs

### Static Validation

For every changed Jython script:

- Validate every new or changed JMRI API call against the publicly available
  JMRI 5.16 documentation.
- If the documentation is ambiguous, contradictory, incomplete, or inconsistent
  with observed behaviour, inspect the corresponding JMRI 5.16 source code on Github and
  relevant tests before relying on the API.


## Common Tasks
| Task | How |
|------|-----|
| Add a new PID display | Create `PID<Name>.py` following existing patterns; register in `TASSetup.py` display lists |
| Add a help topic | Add `<topic>.txt` to `tashelp/`; will auto-appear in Help menu |
| Modify timetable format | Edit CSV in `profile:timetable/`; update `CheckTimetable.py` validation |
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
├── CheckTimetable.py           # Timetable validation
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