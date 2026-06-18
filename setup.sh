#!/bin/bash
# Run once after cloning to set up desktop launchers.
set -e

REPO_DIR="$(dirname "$(realpath "$0")")"
DESKTOP="$HOME/Desktop"

cat > "$DESKTOP/BuildReachLab.desktop" << DESKTOP_FILE
[Desktop Entry]
Name=Build ReachLab
Exec=bash -c 'bash "$REPO_DIR/build.sh"; echo "Done. Press Enter to close..."; read'
Type=Application
Terminal=true
DESKTOP_FILE

chmod +x "$DESKTOP/BuildReachLab.desktop"
gio set "$DESKTOP/BuildReachLab.desktop" metadata::trusted true

echo "Setup complete! Double-click 'Build ReachLab' on your Desktop to build."
