# Building PS5 ELF Sender

Each platform has to be built on that platform (PyInstaller doesn't cross-compile),
so the easiest route is the included GitHub Actions workflow.

## Easiest: GitHub Actions (all four at once)

1. Put this folder in a GitHub repo (the folder contents at the repo root).
2. Either open **Actions > Build installers > Run workflow**, or push a tag:
   `git tag v1.1.0 && git push origin v1.1.0` (this also attaches the files to a Release).
3. Download the artifacts:

| Platform | Output |
|---|---|
| Windows | `PS5-ELF-Sender.exe` (single file) |
| macOS (Apple Silicon) | `PS5-ELF-Sender-macos-arm64.zip` containing the `.app` |
| Debian/Ubuntu | `ps5-elf-sender_1.1.0_all.deb` |
| Android | debug `.apk` from `android/` |

## Building locally

**Windows** (Python 3.12 from python.org, run in PowerShell):
```
pip install pyinstaller tkinterdnd2
pyinstaller --onefile --windowed --name PS5-ELF-Sender --collect-all tkinterdnd2 ps5_elf_sender.py
```
Result: `dist\PS5-ELF-Sender.exe`

**macOS** (python.org or Homebrew Python with Tk):
```
pip3 install pyinstaller tkinterdnd2
pyinstaller --windowed --name "PS5 ELF Sender" --collect-all tkinterdnd2 ps5_elf_sender.py
```
Result: `dist/PS5 ELF Sender.app`. Builds for the Mac you run it on (Apple Silicon or Intel).

**Debian**:
```
bash build_deb.sh
```

**Android** (Linux or WSL; slow the first time, it downloads the SDK/NDK):
```
pip install buildozer
cd android && buildozer android debug
```
Result: `android/bin/*.apk`

## Installing the unsigned builds

- **Windows:** SmartScreen warns on unsigned apps. Click *More info > Run anyway*.
- **macOS:** Gatekeeper blocks unsigned apps. Right-click the app > *Open*, or run
  `xattr -dr com.apple.quarantine "PS5 ELF Sender.app"`.
- **Android:** enable *Install unknown apps* for your browser or file manager, then open the APK.

## Notes

- The Android app is a separate Kivy version (Tkinter doesn't run on Android). It has the
  queue, delay, test, send and cancel, but no saved profiles or drag-and-drop.
- Android file picking goes through `plyer`, which can't always resolve files from every
  location. If a payload won't load, copy it to the Downloads folder and pick it from there.
- The Android app needs the phone and PS5 on the same network.
