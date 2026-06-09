#!/bin/bash
cd "$(dirname "$0")/app"
export QT_QPA_PLATFORM=wayland
export WAYLAND_DISPLAY=wayland-0
python3 main.py "$@"
