[app]
title = PS5 ELF Sender
package.name = ps5elfsender
package.domain = org.ps5elfsender
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.1.0
requirements = python3,kivy,plyer,pyjnius,android
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
