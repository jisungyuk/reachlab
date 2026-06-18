#!/bin/bash
# Build ReachLab as a standalone executable using PyInstaller
set -e

REPO_DIR="$(dirname "$(realpath "$0")")"
DESKTOP="$HOME/Desktop"

cd "$REPO_DIR/app"

PYINSTALLER="${HOME}/.local/bin/pyinstaller"
if ! command -v pyinstaller &>/dev/null && [ ! -f "$PYINSTALLER" ]; then
    echo "PyInstaller not found. Install it with: pip install pyinstaller --break-system-packages"
    exit 1
fi
${PYINSTALLER:-pyinstaller} \
    --name ReachLab \
    --windowed \
    --onedir \
    --noconfirm \
    --icon "$REPO_DIR/assets/icon.png" \
    --distpath "$DESKTOP" \
    --workpath "$REPO_DIR/build" \
    --specpath "$REPO_DIR" \
    main.py

# Rename output folder (keep executable name unchanged)
if [ -d "$DESKTOP/ReachLab_app" ]; then
    rm -rf "$DESKTOP/ReachLab_app"
fi
mv "$DESKTOP/ReachLab" "$DESKTOP/ReachLab_app"

# Always copy config.json from source
if [ -f "$REPO_DIR/app/config.json" ]; then
    cp "$REPO_DIR/app/config.json" "$DESKTOP/ReachLab_app/config.json"
fi

echo ""
echo "Build complete!"
echo "ReachLab is on your Desktop — open ReachLab_app and run ReachLab."
