#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 注入原生 TTS 桥：生成 TtsBridge.java，并 patch MainActivity.java
# 在 WebView 里暴露 window.AndroidTTS.speak(text)（走系统 TTS 引擎，离线可用）
# 用法：仓库根目录执行  python3 scripts/patch-tts.py（在 `npx cap add android` 之后）
import os, sys

APP_DIR = "android/app/src/main/java/com/wordbook/review"
MAIN = os.path.join(APP_DIR, "MainActivity.java")
BRIDGE = os.path.join(APP_DIR, "TtsBridge.java")

BRIDGE_SRC = '''package com.wordbook.review;

import android.content.Context;
import android.speech.tts.TextToSpeech;
import android.webkit.JavascriptInterface;

import java.util.Locale;

/**
 * 原生 TTS 桥：暴露给 WebView 里 window.AndroidTTS.speak(text)。
 * 走系统 TTS 引擎（离线可用，不依赖 Google TTS / 网络）。
 */
public class TtsBridge {
    private final TextToSpeech tts;
    private String pending = null;
    private volatile boolean ready = false;
    private volatile boolean configured = false;

    public TtsBridge(Context context) {
        // 回调里不引用 tts（避免 final 字段/局部变量初始化判定错误），只设置 ready 标志
        tts = new TextToSpeech(context, status -> {
            ready = (status == TextToSpeech.SUCCESS);
        });
    }

    @JavascriptInterface
    public void speak(String text) {
        if (text == null || text.isEmpty()) return;
        if (!ready) { pending = text; return; }
        configureOnce();
        String toSpeak = text;
        if (pending != null) { toSpeak = pending; pending = null; } // 补读引擎就绪前缓存的文本
        tts.speak(toSpeak, TextToSpeech.QUEUE_FLUSH, null, "wb-" + System.currentTimeMillis());
    }

    /** 首次发音时配置语言/语速/音调（此时 tts 已赋值，避免回调期 NPE） */
    private void configureOnce() {
        if (configured) return;
        configured = true;
        int res = tts.setLanguage(Locale.US);
        if (res == TextToSpeech.LANG_MISSING_DATA || res == TextToSpeech.LANG_NOT_SUPPORTED) {
            // 无英文语音包：退回系统默认语言，仍尽量发声
            tts.setLanguage(Locale.getDefault());
        }
        tts.setSpeechRate(0.85f); // 语速稍慢，适合背词
        tts.setPitch(1.1f);        // 音调稍高，更自然
    }

    @JavascriptInterface
    public void stop() {
        if (ready) tts.stop();
    }

    @JavascriptInterface
    public boolean isReady() {
        return ready;
    }
}
'''

ONCREATE_ANCHOR = "        super.onCreate(savedInstanceState);"
INJECT = ONCREATE_ANCHOR + """
        // 注入原生 TTS 桥：HTML 里 window.AndroidTTS.speak(text)
        WebView webView = getBridge().getWebView();
        if (webView != null) {
            webView.addJavascriptInterface(new TtsBridge(this), "AndroidTTS");
        }"""

IMPORT_ANCHOR = "import android.os.Bundle;"
IMPORT_ADD = "import android.os.Bundle;\nimport android.webkit.WebView;"

# 若 updater 桥已注入（patch-updater.py 先跑），复用其 webView 变量追加 TTS 行，避免重复声明
UPDATER_LINE = '            webView.addJavascriptInterface(new UpdaterBridge(this), "AndroidUpdater");'
UPDATER_PLUS_TTS = UPDATER_LINE + '\n            webView.addJavascriptInterface(new TtsBridge(this), "AndroidTTS");'

# Capacitor 6.2+ 极简模板：MainActivity 是空类（无 onCreate、无 android.os.Bundle import）
EMPTY_CLASS = "public class MainActivity extends BridgeActivity {}"
EMPTY_CLASS_IMPORT = "import com.getcapacitor.BridgeActivity;"
EMPTY_CLASS_IMPORT_ADD = "import android.os.Bundle;\nimport android.webkit.WebView;\nimport com.getcapacitor.BridgeActivity;"
EMPTY_CLASS_REPL = '''public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // 注入原生 TTS 桥：HTML 里 window.AndroidTTS.speak(text)
        WebView webView = getBridge().getWebView();
        if (webView != null) {
            webView.addJavascriptInterface(new TtsBridge(this), "AndroidTTS");
        }
    }
}'''


def main():
    if not os.path.exists(MAIN):
        sys.exit("ERROR: %s not found (run after `npx cap add android`)" % MAIN)

    # 1) 生成 TtsBridge.java（幂等）
    if os.path.exists(BRIDGE):
        print("TtsBridge.java already exists, skip")
    else:
        with open(BRIDGE, "w", encoding="utf-8") as f:
            f.write(BRIDGE_SRC)
        print("generated:", BRIDGE)

    # 2) patch MainActivity.java（幂等；与 patch-updater.py 协调，避免重复声明 webView）
    with open(MAIN, "r", encoding="utf-8") as f:
        src = f.read()

    if "AndroidTTS" in src:
        print("MainActivity already patched, skip")
        return
    if UPDATER_LINE in src:
        # updater 桥已注入（patch-updater.py 先跑）→ 复用其 webView 变量追加 TTS 行
        src = src.replace(UPDATER_LINE, UPDATER_PLUS_TTS, 1)
    elif EMPTY_CLASS in src:
        # Capacitor 6.2+ 极简空类模板 → 重写类体（注入 onCreate + TTS 桥）
        if "import android.os.Bundle;" not in src:
            src = src.replace(EMPTY_CLASS_IMPORT, EMPTY_CLASS_IMPORT_ADD, 1)
        src = src.replace(EMPTY_CLASS, EMPTY_CLASS_REPL, 1)
    else:
        # 旧模板（有 onCreate + super.onCreate）
        if IMPORT_ANCHOR not in src:
            sys.exit("ERROR: cannot find import anchor in MainActivity.java, template changed?")
        if ONCREATE_ANCHOR not in src:
            sys.exit("ERROR: cannot find onCreate anchor in MainActivity.java, template changed?")
        if "import android.webkit.WebView;" not in src:
            src = src.replace(IMPORT_ANCHOR, IMPORT_ADD, 1)
        src = src.replace(ONCREATE_ANCHOR, INJECT, 1)

    with open(MAIN, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched:", MAIN)


if __name__ == "__main__":
    main()
