# ReachLab

A Python/PyQt5 desktop app for measuring upper-limb reaching kinematics and "reachable workspace" using a Polhemus Liberty electromagnetic motion tracking system, built for stroke motor-recovery research.

## Why

In stroke hand-opening recovery training, we kept seeing that as patients regained hand-opening ability, compensatory movement at the shoulder and elbow often increased, an interaction that standard clinical measures (Box and Block Test, Fugl-Meyer Assessment) aren't designed to capture. Reachable workspace, how far and where a person's hand can actually go, gives a fuller picture of real upper-limb recovery than those scales can.

## What it does

- Reads real-time 3D position from a multi-sensor Polhemus Liberty tracker.
- Runs a configurable reaching-task paradigm (calibration → trial-based reaching) with live visual feedback.
- Computes a reachable-workspace envelope per participant per arm: a 60-bin angular map of maximum/average reach distance, plus area and summary statistics.
- Includes a digitization module for placing anatomical landmarks (MCP, wrist, elbow, upper arm, trunk) relative to sensor frames, tracking full 3D position for each upper-extremity landmark rather than a single point.
- Includes a calibration workflow with quantitative accuracy validation against a physical reference grid, visualized as a color-coded error field.
- Cross-platform (Windows and Linux).

The current version's primary analysis is reachable workspace, but because it tracks full 3D positions for each upper-extremity landmark, it can support further kinematic and biomechanical analyses beyond workspace alone.

## Hardware/software this expects

- Python 3.12 + PyQt5
- A Polhemus Liberty electromagnetic tracking system

## Status

Built and maintained solo; actively used in ongoing research. This is a lab research tool tied to specific hardware, not a general-purpose package.
