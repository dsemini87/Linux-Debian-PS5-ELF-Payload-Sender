#!/usr/bin/env bash
# Builds ps5-elf-sender_<version>_all.deb from ps5_elf_sender.py (same folder).
# Usage:  ./build_deb.sh
#         MAINTAINER="Your Name <you@example.com>" ./build_deb.sh
# Needs:  dpkg-deb (package: dpkg)
set -euo pipefail
cd "$(dirname "$0")"

PKG=ps5-elf-sender
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' ps5_elf_sender.py)"
MAINTAINER="${MAINTAINER:-PS5 ELF Sender <root@localhost>}"

[ -n "$VERSION" ] || { echo "Could not read VERSION from ps5_elf_sender.py" >&2; exit 1; }

# Stage in a temp dir (not next to the sources) so file copies are real files
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ROOT="$STAGE/${PKG}_${VERSION}_all"

mkdir -p "$ROOT/DEBIAN" \
         "$ROOT/usr/bin" \
         "$ROOT/usr/share/$PKG" \
         "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/scalable/apps" \
         "$ROOT/usr/share/doc/$PKG"

# --- application ---
install -m 0644 ps5_elf_sender.py "$ROOT/usr/share/$PKG/ps5_elf_sender.py"

cat > "$ROOT/usr/bin/$PKG" <<'EOF'
#!/bin/sh
exec python3 /usr/share/ps5-elf-sender/ps5_elf_sender.py "$@"
EOF
chmod 0755 "$ROOT/usr/bin/$PKG"

# --- desktop entry ---
cat > "$ROOT/usr/share/applications/$PKG.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=PS5 ELF Sender
Comment=Send ELF payloads to a jailbroken PS5
Exec=ps5-elf-sender
Icon=ps5-elf-sender
Terminal=false
Categories=Utility;Network;
Keywords=PS5;ELF;payload;sender;
EOF
chmod 0644 "$ROOT/usr/share/applications/$PKG.desktop"

# --- icon ---
cat > "$ROOT/usr/share/icons/hicolor/scalable/apps/$PKG.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect x="8" y="8" width="112" height="112" rx="24" fill="#12182b"/>
  <path d="M64 28 L92 62 H74 V92 H54 V62 H36 Z" fill="#35d0ff"/>
  <rect x="30" y="100" width="68" height="8" rx="4" fill="#7b61ff"/>
</svg>
EOF
chmod 0644 "$ROOT/usr/share/icons/hicolor/scalable/apps/$PKG.svg"

# --- docs ---
cat > "$ROOT/usr/share/doc/$PKG/copyright" <<'EOF'
PS5 ELF Sender
No license specified. Edit this file before distributing the package.
EOF
chmod 0644 "$ROOT/usr/share/doc/$PKG/copyright"

# --- control ---
INSTALLED_SIZE="$(du -sk "$ROOT" | cut -f1)"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-tk
Recommends: python3-tkinterdnd2
Installed-Size: $INSTALLED_SIZE
Maintainer: $MAINTAINER
Description: GUI ELF payload sender for jailbroken PS5 consoles
 Sends .elf payloads over TCP to an ELF loader running on a jailbroken
 PS5. Supports saved console profiles, an ordered payload queue,
 drag-and-drop (with python3-tkinterdnd2), a delay between payloads and
 cancel.
EOF

mkdir -p dist
dpkg-deb --root-owner-group --build "$ROOT" "dist/${PKG}_${VERSION}_all.deb"
echo "Built: dist/${PKG}_${VERSION}_all.deb"
