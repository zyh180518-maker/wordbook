#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发布热更资源：生成 latest.json + 版本化 HTML（供 GitHub Pages / raw / jsDelivr 使用）
- 从 git tag（vX.Y.Z）读版本号
- 对 www/index.html 计算 MD5（二进制模式，对实际字节）
- 生成 www/index-<version>.html（版本化副本，避免 CDN/Pages 缓存冲突）
- 生成 www/latest.json（固定文件名，前端检查更新用；含多源 URL + md5 + apk 信息）
用法：仓库根目录执行  python3 scripts/release-assets.py（在 tag 构建时运行）
"""
import hashlib, json, os, re, sys

WWW_INDEX = "www/index.html"
LATEST_JSON = "www/latest.json"

GITEE_OWNER = os.environ.get("GITEE_OWNER", "zyh2077")
GITEE_REPO = os.environ.get("GITEE_REPO", "workbook.ds.cqjtu")
GITEE_TOKEN = os.environ.get("GITEE_TOKEN", "")

def parse_tag(ref):
    m = re.search(r"v(\d+)\.(\d+)\.(\d+)", ref.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

def push_to_gitee(files, version):
    """把热更文件上传/覆盖到 Gitee 公开仓库（国内镜像源，手机无代理直连）。
    无 GITEE_TOKEN 时跳过并提示（CI 配好 Secrets 后自动生效）。"""
    if not GITEE_TOKEN:
        print("WARN: GITEE_TOKEN not set, skip Gitee push (国内镜像未启用)")
        return
    import base64, urllib.request, urllib.parse
    api = "https://gitee.com/api/v5/repos/%s/%s/contents" % (GITEE_OWNER, GITEE_REPO)
    for path, data in files:
        url = api + "/" + path
        sha = None
        try:
            req = urllib.request.Request(url + ("?access_token=%s" % GITEE_TOKEN))
            with urllib.request.urlopen(req, timeout=20) as r:
                existing = json.load(r)
                sha = existing.get("sha")
        except Exception:
            sha = None  # 文件不存在或查询失败 → 直接创建
        body = urllib.parse.urlencode({
            "access_token": GITEE_TOKEN,
            "content": base64.b64encode(data).decode(),
            "message": "release v%s hot-update assets" % version,
            "sha": sha,
        }).encode() if sha else urllib.parse.urlencode({
            "access_token": GITEE_TOKEN,
            "content": base64.b64encode(data).decode(),
            "message": "release v%s hot-update assets" % version,
        }).encode()
        req = urllib.request.Request(url, data=body, method="PUT" if sha else "POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                json.load(r)
            print("gitee upload OK: %s" % path)
        except Exception as e:
            print("WARN: gitee upload failed for %s: %r" % (path, e))

def main():
    if not os.path.exists(WWW_INDEX):
        sys.exit("ERROR: %s not found" % WWW_INDEX)

    ref = os.environ.get("GITHUB_REF", "")
    tag = parse_tag(ref)
    if tag is None:
        print("no vX.Y.Z tag in GITHUB_REF (%r), skip release assets" % ref)
        return
    version = "%d.%d.%d" % tag

    # 二进制模式读取，保证 md5 对实际字节（避免文本模式换行转换的坑）
    with open(WWW_INDEX, "rb") as f:
        html_bytes = f.read()
    md5 = hashlib.md5(html_bytes).hexdigest()

    html_file = "index-%s.html" % version
    # 版本化副本（永远不覆盖旧版本文件）
    with open(os.path.join("www", html_file), "wb") as f:
        f.write(html_bytes)

    base = "zyh180518-maker/wordbook"
    apk_info = {
        "version": version,
        "url": "https://github.com/%s/releases/latest/download/app-debug.apk" % base,
        "md5": "",
        "size": 0
    }
    # 若已构建 APK（debug 产物），填充真实 md5/size 供前端校验与体积显示
    import glob
    apks = sorted(glob.glob("android/app/build/outputs/apk/debug/*.apk"))
    if apks:
        apk_path = apks[-1]
        with open(apk_path, "rb") as f:
            apk_bytes = f.read()
        apk_info["md5"] = hashlib.md5(apk_bytes).hexdigest()
        apk_info["size"] = len(apk_bytes)
        print("APK found: %s (%d bytes, md5 %s)" % (apk_path, len(apk_bytes), apk_info["md5"]))
    else:
        print("WARN: no debug APK found, apk info left empty (html hot-update only)")

    latest = {
        "version": version,
        "htmlFile": html_file,
        # 主源：GitHub Pages（无代理国内可达 + CORS *，旧版 v1.4.x~v1.5.1 启动器只能读 htmlUrl、
        # 无兜底链，Gitee raw 无 CORS 会拦它们 → 主源必须 Pages）；Gitee/raw/jsdelivr 做兜底
        "htmlUrl": "https://zyh180518-maker.github.io/wordbook/www/%s" % html_file,
        "htmlUrlBackup": [
            "https://gitee.com/%s/%s/raw/master/%s" % (GITEE_OWNER, GITEE_REPO, html_file),
            "https://raw.githubusercontent.com/%s/gh-pages/%s" % (base, html_file),
            "https://cdn.jsdelivr.net/gh/%s@gh-pages/%s" % (base, html_file),
        ],
        "md5": md5,
        # APK 信息：全量下载安装（差分二期后追加 diffUrl/diffMd5/diffSize）
        "apk": apk_info
    }

    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print("release assets ready: version=%s md5=%s htmlFile=%s" % (version, md5, html_file))
    print("latest.json written to", LATEST_JSON)

    # 国内镜像：同步热更文件到 Gitee 仓库根目录（无 www/ 前缀，对应 raw/master/ 直链）
    push_to_gitee([
        ("latest.json", open(LATEST_JSON, "rb").read()),
        (html_file, html_bytes),
    ], version)

if __name__ == "__main__":
    main()
