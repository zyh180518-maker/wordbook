#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 从 git tag（vX.Y.Z）设置 android versionCode/versionName
# versionCode = X*10000 + Y*100 + Z，保证每次发版递增，可覆盖安装升级
# 用法：仓库根目录执行  python3 scripts/patch-version.py（在 `npx cap add android` 之后）
import os, re, sys

GRADLE = "android/app/build.gradle"


def parse_tag(ref):
    # "refs/tags/v1.4.0" -> (1, 4, 0)
    m = re.search(r"v(\d+)\.(\d+)\.(\d+)", ref.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def main():
    if not os.path.exists(GRADLE):
        sys.exit("ERROR: %s not found (run after `npx cap add android`)" % GRADLE)

    ref = os.environ.get("GITHUB_REF", "")
    tag = parse_tag(ref)
    if tag is None:
        print("no vX.Y.Z tag in GITHUB_REF (%s), skip version patch" % ref)
        return
    version_name = "%d.%d.%d" % tag
    version_code = tag[0] * 10000 + tag[1] * 100 + tag[2]

    with open(GRADLE, "r", encoding="utf-8") as f:
        src = f.read()

    if "versionCode %d" % version_code in src:
        print("version already %s (code %d), skip" % (version_name, version_code))
        return

    pattern = r'(versionCode\s+)\d+(\s*\n\s*versionName\s+)"[^"]*"'
    repl = r'\g<1>%d\g<2>"%s"' % (version_code, version_name)
    new_src, n = re.subn(pattern, repl, src, count=1)
    if n == 0:
        sys.exit("ERROR: cannot find versionCode/versionName in build.gradle, template changed?")

    with open(GRADLE, "w", encoding="utf-8") as f:
        f.write(new_src)
    print("version set: %s -> code %d" % (version_name, version_code))


if __name__ == "__main__":
    main()
