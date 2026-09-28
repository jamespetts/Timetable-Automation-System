Read when: Task makes a design decision affecting more than one feature, adds a feature, changes a user interface, changes time handling, changes error handling, or changes setup flow. Read before other head-topic files for such tasks.

# Design Goals

Definitions:
- TAS means Timetable Automation System.
- Railway modeller means the user operating a model railway with JMRI and TAS.
- Realistic timetable means trains operate at stated times on stated days with stated origins, destinations, and formations.
- Skeuomorphic means the displayed window resembles a real railway item in layout, labels, and controls.
- Setup interface means windows for configuration and setup.
- Operational interface means windows used during layout operation.
- QoL means quality-of-life, where quality-of-life means a small interface function that reduces required clicks or prevents input errors.
- Self-repair means retry or fallback without manual input.
- System console means the JMRI system console.

## A. Purpose and feature scope

A1. TAS allows railway modellers to run realistic timetables on model railways. Implication: timetable execution is the primary function. Other functions support this function.

A2. Features are independent where possible. Different users use different feature sets. Implication: each optional function must run when other optional functions are disabled. Shared dependencies are limited to common data and common presentation.

## B. Time coherence and era compatibility

B1. Time is internally coherent. Time-based layout functions use the same time values. Every represented value has a single authoritative source of truth. Implication: new time-based functions must reuse the applicable store and must ask the user before creating a new store for time-related data.

B2. TAS is compatible with multiple eras. Implication: era-specific appearance must be implemented as selectable appearance variants, not as changes to shared data.

## C. Interfaces and setup effort

C1. Operational interfaces are skeuomorphic. Exemption: setup interfaces are not skeuomorphic. Implication: each operational window resembles the corresponding real item in layout, labels, and controls.

C2. Setup interfaces resemble 1990s style user interfaces to the extent consistent with the underlying interface style, with added QoL functions at AI discretion within reason. Implication: setup windows use standard controls, paper-like panels, and explicit buttons. QoL functions must not change the 1990s visual style.

C3. TAS is customisable and easy to set up. Implication: each display exposes settings. Timetable input accepts common time formats. The setup flow provides defaults. New options must provide a default that runs without manual entry.

## D. Robustness and diagnostics

D1. Automation is robust and self-repairs in predictable ways despite hardware faults such as derailments, stalls, or incorrect trains on tracks. Self-repair is an abstract category. Implication: AI proposes new self-repair forms when the need becomes apparent. Each proposal states its retry limit, its fallback path, and the condition that stops retry. Automation must not directly control trains outside the designated train-starting process.

D2. Failures are reported in the system console with sufficient detail for user inspection and AI debugging. Implication: log entries identify the operation, the location, and the data values involved. Use a dialog only for errors requiring user attention.
