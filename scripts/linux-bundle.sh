#!/usr/bin/env bash
# Pack E — portable Linux tarball for Motif (no Apple signing required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="Motif-linux-$(uname -m)"
DEST="${1:-$ROOT/dist/$NAME}"
rm -rf "$DEST"
mkdir -p "$DEST"
# Copy source + launcher; first-run still creates .venv via start.py
rsync -a --exclude .venv --exclude __pycache__ --exclude .git --exclude dist \
  --exclude '*.pyc' --exclude Motif.app \
  "$ROOT/" "$DEST/Motif/"
cat > "$DEST/run-motif.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/Motif"
exec python3 start.py "$@"
EOF
chmod +x "$DEST/run-motif.sh" "$DEST/Motif/start" || true
mkdir -p "$ROOT/dist"
TAR="$ROOT/dist/${NAME}.tar.gz"
tar -C "$(dirname "$DEST")" -czf "$TAR" "$(basename "$DEST")"
echo "Built $TAR"
echo "Run: tar -xzf $TAR && ./$(basename "$DEST")/run-motif.sh"
