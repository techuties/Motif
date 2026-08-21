#!/bin/bash
# Fallback launcher. Prefer Motif.app so TCC permissions attach to Motif, not
# Terminal. Quote everything: this project often lives under iCloud
# ("Mobile Documents"). Qt cannot scan plugin dirs whose path contains spaces, so
# we also alias plugins into a space-free cache.
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

if [ -x "$ROOT/Motif.app/Contents/MacOS/Motif" ]; then
  open "$ROOT/Motif.app"
  exit 0
fi

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi

if [ -z "$PY" ]; then
  echo "Motif needs Python 3.11+ (python3 not found)." >&2
  echo ""
  echo "Press Return to close."
  read -r
  exit 1
fi

PLUGIN=""
for candidate in "$ROOT"/.venv/lib/python*/site-packages/PySide6/Qt/plugins; do
  if [ -d "$candidate/platforms" ]; then
    PLUGIN="$candidate"
    break
  fi
done

if [ -n "$PLUGIN" ]; then
  case "$PLUGIN" in
    *" "*)
      CACHE="${HOME}/Library/Caches/Motif/qt-plugins"
      mkdir -p "$CACHE"
      for sub in "$PLUGIN"/*; do
        [ -d "$sub" ] || continue
        name="$(basename "$sub")"
        mkdir -p "$CACHE/$name"
        for f in "$sub"/*; do
          [ -e "$f" ] || continue
          ln -sfn "$f" "$CACHE/$name/$(basename "$f")"
        done
      done
      PLUGIN="$CACHE"
      ;;
  esac
  export QT_PLUGIN_PATH="$PLUGIN"
  export QT_QPA_PLATFORM_PLUGIN_PATH="$PLUGIN/platforms"
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-cocoa}"
fi

"$PY" "$ROOT/start.py" "$@"
status=$?
if [ "$status" -ne 0 ]; then
  echo ""
  echo "Motif failed (exit $status). Press Return to close."
  read -r
fi
exit "$status"
