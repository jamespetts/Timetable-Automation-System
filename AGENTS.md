# Timetable Automation System (TAS) — Agent Guide

## Project Overview
Jython 2.7 scripts for JMRI (Java Model Railroad Interface). Provides timetable automation, public/signaller displays, weather, day/night cycle, disruption generation, and time warp.

**Entry point:** `TimetableAutomation.py` — run via JMRI "Scripting > Run Script..."

**License:** GPL v3. All code files must have the standard GPL v. 3 header.

## AI Operating Rules
- Use no metaphor in any output, file content, code comment, commit message, or internal chain-of-thought. This prohibition includes internal reasoning. State facts directly without comparison phrases.
- All text produced by the AI must be precise and literal.
- Do not invent identifiers, file names, Memory names, configuration keys, or JMRI API signatures. Verify each reference against the repository code or against the publicly available JMRI 5.16 documentation. If the documentation is ambiguous, contradictory, incomplete, or inconsistent with observed behaviour, inspect the corresponding JMRI 5.16 source code on Github and relevant tests before relying on the API.
- If a fact cannot be resolved by examining the repository code or the JMRI 5.16 documentation or source, stop and ask the user.
- Keep responses short. Report file paths as `path:line_number` when referencing specific code.

## AI Knowledge Base (ai/)
- The directory `ai/` contains the indexed knowledge base that describes how the code works for future agents.
- Entry point is `ai/index.md`. Read `ai/index.md` at the start of each session.
- `ai/index.md` links head-topic files. Each head-topic file links detailed-topic files. Do not link detailed-topic files directly from `ai/index.md`.
- Each knowledge base file starts with a `Read when:` line that states the exact task conditions that require reading that file. Read a file only when its `Read when:` condition matches the current task.
- All knowledge base documents are `.md` files under `ai/`. Detailed-topic files are under `ai/details/`.
- All knowledge base documents must use ASCII only, precise literal text, and no metaphor.
- Keep knowledge base documents much shorter than the code. For details, the AI can read the code. Record only facts needed to locate and use the code.
- AI temporary and scratch files must be placed only in `ai/temp/`. At the end of each session delete all files in `ai/temp/`, then write `ai/temp/handoff.md` only when incomplete work remains for a new session. `ai/temp/handoff.md` contains only the description of the incomplete work. Delete `ai/temp/handoff.md` when the handed off work is complete.

## Installation & Runtime
- Copy all files to JMRI profile's `jython/` directory (NOT program folder)
- First run prompts to set `scripts:` location to this folder; restart JMRI after
- Application scripts run inside JMRI; selected pure helper modules can be tested outside JMRI
- Target JMRI 5.16+ / Jython 2.7.

## Key Modules
| Module | Purpose |
|--------|---------|
| `TimetableAutomation.py` | Entry point (self-installs, migrates flat installs, loads TASMainMenu) |
| `TASMainMenu.py` | Main menu UI loaded by TimetableAutomation.py |
| `TASBeanLookup.py` | Prefix-independent JMRI Memory lookup and access across connections |
| `TASPathResolver.py` | Portable path resolution (profile:jython/TAS → profile:jython → scripts:) |
| `TASSetup.py` | Multi-tab configuration UI (General, Displays, Day/Night) |
| `TASWiz.py` | Setup wizard |
| `RunWTT.py` | Working timetable runner |
| `WTTDisplay.py` | Timetable display |
| `WeatherGenerator.py` / `WeatherForecastUI*.py` | Weather system |
| `DayTracker.py` / `DayNight.py` | Day/night cycle |
| `DisruptionGenerator.py` | Disruption system |
| `TimeWarp.py` / `TimeWarpChecker.py` | Time warp |
| `PID*.py` | Public information displays (many variants) |
| `TASHelp.py` | Help system (loads `tashelp/*.md`) |

## Configuration
- Runtime settings are primarily stored in **JMRI Memories** and accessed prefix-independently via 'TASBeanLookup'
- Key memories: `CURRENTTIMETABLE`, `ALLOWTIMEWARP`, `WX_UI`, `CLOUDCOVERPCT`, `PUBLICDISPLAYLIST`, `SIGNALLERDISPLAYLIST`, `TASCOVERCOLOUR`, `TASINNERCOLOUR`, `TASINKCOLOUR`, `TAS_FONT_FAMILY`
- Timetable CSV in `profile:timetable/<name>.csv`
- Configuration files are stored under `profile:jython/TAS/config/`, including `daynight.csv`, `climate.csv`, and `streetlights.tsv`. The csv files are actually tab separated. 'streetlights.tsv' is automatically created only when street lights are configured by the user.

## Development Conventions
- **Single authoritative source of truth** - for every value being represented, there should be a single authoritative source of truth. Do not create competing authoritative stores for the same value; use shared utilities and derive or snapshot state where needed. Before adding a Memory, file, or register entry, verify that no existing Memory, file, or register already represents the same value.
- **ASCII only** — no non-ASCII chars in source
- **No hard-coded absolute paths** — use JMRI path schemes through FileUtil or TASPathResolver and resolve them at runtime
- **Thread-safe** — treat JMRI as threaded; protect shared state and perform Swing UI access on the Event Dispatch Thread
- **Jython 2.7 syntax** — no f-strings, type hints, or Python 3 features
- **Imports:** Use Jython-compatible imports for JMRI and Java classes, following existing local patterns
- **Startup script names:** JMRI runs every Start-Up script through one shared Jython JSR-223 context, so top-level names collide between start-up scripts and a later script silently replaces an earlier script's object. Give every top-level name in a start-up script a per-script prefix (for example `FLICKER_` / `_Flicker`, `DCCPOWER_` / `_DccPower`), and bind any object a function uses later as a default argument. See `ai/details/startup-power-warnings.md`.
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
| Add a help topic | Add `<topic>.md` to `tashelp/`; will auto-appear in Help menu |
| Modify timetable format | Update the relevant readers/writers and verify compatibility with all example timetable schemas
| Change colours/fonts | Edit memories via Setup UI or directly in JMRI Memory Table |

## Gotchas
- **Entry script size limit:** JMRI runs TimetableAutomation.py through the JSR-223 script engine, which parses the file twice and can only reset the parser up to 100000 bytes. Keep the entry script below that size; put new code in imported modules such as TASMainMenu.py
- **Install location:** canonical home is `profile:jython/TAS/` (since 1.5); `TimetableAutomation.py` auto-migrates flat installs and self-installs from elsewhere with an explanatory dialogue
- **Copies outside the profile TAS folder:** TAS warns about TAS files in the program folder or a foreign scripts folder — delete those copies (program folder needs admin rights)
- **Startup script path mismatch:** TAS detects if Start-Up actions point to wrong copy; offers auto-fix
- **Scripts directory must be writable** — first-run check enforces this
- **Memory prefixes vary by connection** — always use `TASBeanLookup` (`SafeGetOrCreateMemoryValue`, etc.)
- **No pip/venv** — dependencies are JMRI core only

## File Layout
```
TAS devel/
├── README.md                     # Github front page (install instructions, links, features)
├── TAS/                          # Everything TAS (installed as profile:jython/TAS)
│   ├── TimetableAutomation.py    # Entry point (self-installs, migrates flat installs)
│   ├── TASMainMenu.py            # Main menu UI (kept separate: entry must stay under 100000 bytes)
│   ├── TASBeanLookup.py          # Bean lookup utility
│   ├── TASPathResolver.py        # Path resolution (TAS_SUBDIR = 'TAS')
│   ├── TASSetup.py               # Configuration UI
│   ├── TASWiz.py                 # Setup wizard
│   ├── RunWTT.py                 # Timetable runner
│   ├── WTTDisplay.py             # Timetable display
│   ├── WeatherGenerator.py       # Weather engine
│   ├── WeatherForecastUI*.py     # Weather UIs
│   ├── DayTracker.py / DayNight.py # Day/night cycle
│   ├── DisruptionGenerator.py    # Disruptions
│   ├── TimeWarp*.py              # Time warp
│   ├── PID*.py                   # Public displays (20+ variants)
│   ├── TASScriptsPathGuard.py    # Startup path logic
│   ├── TASWindowRegistry.py      # Main menu window toggles
│   ├── TASHelp.py                # Help system
│   ├── tashelp/*.md             # Help topics
│   ├── config/daynight.csv       # Day/night config
│   ├── config/climate.csv        # Climate config
│   ├── Example timetables/*.csv  # Sample timetables
│   ├── changelog.txt             # Version history
│   ├── Licence.txt               # GPL v3
│   └── Timetable Automation System installation instructions.txt
├── ai/index.md                   # Knowledge base entry point
├── ai/*.md                       # Head-topic files
├── ai/details/*.md               # Detailed-topic files
└── ai/temp/                      # AI scratch files; preserve only handoff.md
```

## Deprecated
* CheckTimetable.py