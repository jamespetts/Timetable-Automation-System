# DCC power on at start-up

## Overview

This is an optional setting and is off by default. Enable it in Setup, General tab, with "Turn DCC power on at start-up (requires restart)". Restart JMRI after changing the setting.

When enabled, this setting checks the DCC track power each time JMRI starts.

- If the power is already on, nothing is done. The power is not interrupted.
- If the power is off or idle, it is turned on.
- If the power state is not known, this setting does not change it. It waits for the state to become known and then acts as above. If the state is still not known after 15 seconds, a warning window will be shown.

This system will wait up to 30 seconds for a hardware connection to publish a power manager, so it is safe to have it run at start-up.

Turning this option on also disables any enabled JMRI Start-Up entry that runs the script PowerOn.py that JMRI supplies with the program. Without this, JMRI would turn the power on unconditionally at start-up, which would interrupt power that is already on and would leave an unknown power state unknown.

The script that runs this setting is maintained automatically at the top of the Start-Up list, before the panel file and the other start-up scripts, so track power is on before they act. The Setup window moves it back to the top whenever it saves the Start-Up list.

The change to the Start-Up list applies to the current profile only, and takes effect at the next start of JMRI. If you turn this option off again and you want JMRI's own script to turn the power on, re-enable that entry in Edit, Preferences, Start Up.

The script writes its findings to the system console, each line starting with [TAS].
