# Block flicker monitor

## Overview

This is an optional setting. It is off by default. Enable it in Setup, General tab, with "Enable occupancy sensor flicker monitor (requires restart)". Restart JMRI after changing the setting.

When enabled, the script watches all blocks for a double flicker: occupied, then unoccupied, then occupied again, or unoccupied, then occupied, then unoccupied again, all within 3 seconds. A double flicker often means dirty track or loose wiring and can cause automation failures that are otherwise difficult to trace. A single brief drop is not reported.

Whenever a flicker is detected, this is logged in the system console and a warning window is shown.
