#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 把稳定签名配置注入 Capacitor 生成的 android/app/build.gradle
# 用法：在仓库根目录执行  python3 scripts/patch-signing.py
import os, sys

path = "android/app/build.gradle"
if not os.path.exists(path):
    sys.exit("ERROR: %s not found (run after `npx cap add android`)" % path)

with open(path, "r", encoding="utf-8") as f:
    src = f.read()

anchor = """    buildTypes {
        release {"""
inject = """    signingConfigs {
        debug {
            storeFile file('debug.keystore')
            storePassword 'android'
            keyAlias 'androiddebugkey'
            keyPassword 'android'
            storeType 'PKCS12'
        }
    }
    buildTypes {
        debug {
            signingConfig signingConfigs.debug
        }
        release {"""

if "signingConfigs.debug" in src:
    print("already patched, skip")
    sys.exit(0)
if anchor not in src:
    sys.exit("ERROR: cannot find anchor block in build.gradle, template changed?")

with open(path, "w", encoding="utf-8") as f:
    f.write(src.replace(anchor, inject, 1))
print("patched:", path)
