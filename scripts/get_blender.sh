#!/usr/bin/env bash
# Download the Linux build of Blender used for headless validation and tests.
set -euo pipefail
VERSION="${BLENDER_VERSION:-5.2.2}"
SERIES="${VERSION%.*}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.tools"
NAME="blender-$VERSION-linux-x64"
[ -x "$DEST/$NAME/blender" ] && { echo "$DEST/$NAME/blender"; exit 0; }
mkdir -p "$DEST" && cd "$DEST"
BASE="https://download.blender.org/release/Blender$SERIES"
curl -fsSL -O "$BASE/$NAME.tar.xz"
curl -fsSL "$BASE/blender-$VERSION.sha256" | grep "$NAME.tar.xz" | sha256sum -c -
tar xf "$NAME.tar.xz" && rm "$NAME.tar.xz"
echo "$DEST/$NAME/blender"
