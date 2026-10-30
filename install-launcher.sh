#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TARGET="$HOME/.local/share/applications/easy-github-uploader.desktop"
mkdir -p "$(dirname "$TARGET")"
# The directory can contain spaces; desktop Exec uses double-quoted paths.
if [[ "$ROOT" == *\"* ]]; then
  echo 'The folder path contains a quote. Move the app to a simpler path.' >&2
  exit 1
fi
cat > "$TARGET" <<EOF
[Desktop Entry]
Type=Application
Name=Easy-Github-Uploader
Comment=Upload project folders to GitHub
Exec="$ROOT/start.sh"
Path=$ROOT
Icon=folder-upload
Terminal=true
Categories=Development;Utility;
StartupNotify=true
EOF
chmod +x "$TARGET"
echo "Application menu shortcut created: $TARGET"
echo 'Look for Easy-Github-Uploader in the KDE application menu.'
