#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET="$DATA_HOME/applications/easy-github-uploader.desktop"
APP_ID="io.github.LionheartTim.EasyGithubUploader"
ICON_ROOT="$ROOT/assets/icons/hicolor"
mkdir -p "$(dirname "$TARGET")"
# Register the application icon in the user's XDG icon theme.
for size in 16 24 32 48 64 128 256 512; do
  source_icon="$ICON_ROOT/${size}x${size}/apps/$APP_ID.png"
  target_dir="$DATA_HOME/icons/hicolor/${size}x${size}/apps"
  if [[ ! -f "$source_icon" ]]; then
    echo "Missing application icon: $source_icon" >&2
    exit 1
  fi
  mkdir -p "$target_dir"
  cp -f "$source_icon" "$target_dir/$APP_ID.png"
done
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
Icon=$APP_ID
Terminal=true
Categories=Development;Utility;
StartupNotify=true
StartupWMClass=easy-github-uploader
EOF
chmod +x "$TARGET"
# Updating KDE's icon cache is optional; newly installed icons are still discoverable without it.
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi
echo "Application icon installed: $APP_ID"
echo "Application menu shortcut created: $TARGET"
echo 'Look for Easy-Github-Uploader in the KDE application menu.'
