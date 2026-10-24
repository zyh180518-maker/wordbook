#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
注入 APK 自更新桥：生成 UpdaterBridge.java + patch MainActivity.java + AndroidManifest.xml
- window.AndroidUpdater.getInstalledVersion() → 当前 versionName
- window.AndroidUpdater.downloadAndInstall(url, fileName, md5) → 下载 APK（应用专属目录）
  校验 MD5 后经 FileProvider 调起系统安装器（全量包；bsdiff 差分二期再做）
用法：仓库根目录执行  python3 scripts/patch-updater.py（在 `npx cap add android` 之后）
"""
import os, sys

APP_DIR = "android/app/src/main/java/com/wordbook/review"
MAIN = os.path.join(APP_DIR, "MainActivity.java")
BRIDGE = os.path.join(APP_DIR, "UpdaterBridge.java")
MANIFEST = "android/app/src/main/AndroidManifest.xml"
FILE_PATHS_XML = "android/app/src/main/res/xml/file_paths.xml"

BRIDGE_SRC = '''package com.wordbook.review;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Environment;
import android.webkit.JavascriptInterface;
import androidx.core.content.FileProvider;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * APK 自更新桥：暴露给 WebView 里 window.AndroidUpdater。
 * 下载 APK 到应用专属目录 → MD5 校验 → FileProvider 调起系统安装器。
 * 离线可用，不依赖 Google Play；首次安装需用户允许「安装未知应用」。
 */
public class UpdaterBridge {
    private final Context ctx;

    public UpdaterBridge(Context context) {
        this.ctx = context.getApplicationContext();
    }

    /** 当前安装版本（versionName），供前端对比 */
    @JavascriptInterface
    public String getInstalledVersion() {
        try {
            return ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "0.0.0";
        }
    }

    /** 下载并安装 APK。md5 传空串则跳过校验。 */
    @JavascriptInterface
    public void downloadAndInstall(final String urlStr, final String fileName, final String md5) {
        if (urlStr == null || urlStr.isEmpty()) return;
        new Thread(new Runnable() {
            @Override
            public void run() {
                File target = null;
                try {
                    File dir = new File(ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "updates");
                    if (!dir.exists() && !dir.mkdirs()) dir = ctx.getFilesDir();
                    target = new File(dir, fileName);
                    download(urlStr, target);
                    if (md5 != null && !md5.isEmpty()) {
                        String got = md5(target);
                        if (!md5.equalsIgnoreCase(got)) {
                            target.delete();
                            return;
                        }
                    }
                    install(target);
                } catch (Exception e) {
                    if (target != null && target.exists()) target.delete();
                }
            }
        }).start();
    }

    private void download(String urlStr, File target) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(60000);
        conn.setInstanceFollowRedirects(true);
        conn.connect();
        int code = conn.getResponseCode();
        if (code != HttpURLConnection.HTTP_OK) throw new IOException2("HTTP " + code);
        InputStream in = conn.getInputStream();
        OutputStream out = new FileOutputStream(target);
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
        out.flush();
        out.close();
        in.close();
        conn.disconnect();
    }

    private void install(File apk) {
        Uri uri = FileProvider.getUriForFile(ctx, ctx.getPackageName() + ".fileprovider", apk);
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            ctx.startActivity(intent);
        } catch (Exception e) {
            // 部分 ROM 需要显式跳转安装界面
            Intent fallback = new Intent(Intent.ACTION_INSTALL_PACKAGE);
            fallback.setData(uri);
            fallback.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(fallback);
        }
    }

    private String md5(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("MD5");
        InputStream in = new java.io.FileInputStream(f);
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) != -1) md.update(buf, 0, n);
        in.close();
        StringBuilder sb = new StringBuilder();
        for (byte b : md.digest()) sb.append(String.format("%02x", b));
        return sb.toString();
    }

    private static class IOException2 extends Exception {
        IOException2(String m) { super(m); }
    }
}
'''

ONCREATE_ANCHOR = "        super.onCreate(savedInstanceState);"
INJECT = ONCREATE_ANCHOR + """
        // 注入 APK 自更新桥：HTML 里 window.AndroidUpdater.downloadAndInstall(url, name, md5)
        WebView webView = getBridge().getWebView();
        if (webView != null) {
            webView.addJavascriptInterface(new UpdaterBridge(this), "AndroidUpdater");
        }"""

IMPORT_ANCHOR = "import android.os.Bundle;"
IMPORT_ADD = "import android.os.Bundle;\\nimport android.webkit.WebView;"

# 若 TTS 桥已注入（patch-tts.py 先跑），复用其 webView 变量追加 updater 行，避免重复声明
TTS_LINE = '            webView.addJavascriptInterface(new TtsBridge(this), "AndroidTTS");'
TTS_PLUS_UPDATER = TTS_LINE + '\n            webView.addJavascriptInterface(new UpdaterBridge(this), "AndroidUpdater");'

MANIFEST_PERMISSION = '<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />'
PROVIDER_BLOCK = '''        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.fileprovider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data
                android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/file_paths" />
        </provider>'''

FILE_PATHS = '''<?xml version="1.0" encoding="utf-8"?>
<paths>
    <external-files-path name="downloads" path="Download/updates/" />
    <files-path name="internal_updates" path="updates/" />
</paths>
'''


def main():
    if not os.path.exists(MAIN):
        sys.exit("ERROR: %s not found (run after `npx cap add android`)" % MAIN)

    # 1) 生成 UpdaterBridge.java（幂等）
    if os.path.exists(BRIDGE):
        print("UpdaterBridge.java already exists, skip")
    else:
        with open(BRIDGE, "w", encoding="utf-8") as f:
            f.write(BRIDGE_SRC)
        print("generated:", BRIDGE)

    # 2) patch MainActivity.java（幂等；与 patch-tts.py 协调，避免重复声明 webView）
    with open(MAIN, "r", encoding="utf-8") as f:
        src = f.read()
    if "AndroidUpdater" in src:
        print("MainActivity already has updater bridge, skip")
    else:
        if TTS_LINE in src:
            # TTS 桥已注入（patch-tts.py 先跑）→ 复用其 webView 变量追加 updater 行
            src = src.replace(TTS_LINE, TTS_PLUS_UPDATER, 1)
        else:
            if "import android.webkit.WebView;" not in src:
                src = src.replace(IMPORT_ANCHOR, IMPORT_ADD, 1)
            if ONCREATE_ANCHOR not in src:
                sys.exit("ERROR: cannot find onCreate anchor in MainActivity.java, template changed?")
            src = src.replace(ONCREATE_ANCHOR, INJECT, 1)
        with open(MAIN, "w", encoding="utf-8") as f:
            f.write(src)
        print("patched:", MAIN)

    # 3) patch AndroidManifest.xml（幂等）
    if not os.path.exists(MANIFEST):
        sys.exit("ERROR: %s not found" % MANIFEST)
    with open(MANIFEST, "r", encoding="utf-8") as f:
        mf = f.read()
    changed = False
    if "REQUEST_INSTALL_PACKAGES" not in mf:
        if "<uses-permission " in mf:
            mf = mf.replace("<uses-permission ", MANIFEST_PERMISSION + "\n    <uses-permission ", 1)
        else:
            # 无权限块（异常模板）→ 插在 <application 前
            mf = mf.replace("<application", "    " + MANIFEST_PERMISSION + "\n    <application", 1)
        changed = True
    if "fileprovider" not in mf.lower():
        anchor = "</application>"
        if anchor not in mf:
            sys.exit("ERROR: cannot find </application> in AndroidManifest.xml")
        mf = mf.replace(anchor, PROVIDER_BLOCK + "\n    " + anchor, 1)
        changed = True
    if changed:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write(mf)
        print("patched:", MANIFEST)

    # 4) 生成 file_paths.xml（幂等）
    if os.path.exists(FILE_PATHS_XML):
        print("file_paths.xml already exists, skip")
    else:
        os.makedirs(os.path.dirname(FILE_PATHS_XML), exist_ok=True)
        with open(FILE_PATHS_XML, "w", encoding="utf-8") as f:
            f.write(FILE_PATHS)
        print("generated:", FILE_PATHS_XML)


if __name__ == "__main__":
    main()
