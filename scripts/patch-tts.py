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
        // 回调只设 ready 标志并触发补读；不在 lambda 内直接引用 tts（避免初始化判定编译错误）
        tts = new TextToSpeech(context, status -> {
            ready = (status == TextToSpeech.SUCCESS);
            if (ready) flushPending(); // 引擎就绪后自动补读初始化期间缓存的文本
        });
    }

    @JavascriptInterface
    public boolean speak(String text) {
        if (text == null || text.isEmpty()) return true;
        if (!ready) { pending = text; return true; } // 引擎初始化中：缓存文本，就绪后自动补读
        configureOnce();
        return tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "wb-" + System.currentTimeMillis())
                == TextToSpeech.SUCCESS;
    }

    /** 引擎就绪后自动补读缓存文本（修复“点击没声音”：首次点击时引擎通常尚未绑定完成） */
    private void flushPending() {
        String text = pending;
        pending = null;
        if (text == null || text.isEmpty()) return;
        configureOnce();
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "wb-flush-" + System.currentTimeMillis());
    }

    /** 首次发音时配置语言/语速/音调（此时 tts 已赋值，避免回调期 NPE） */
    private void configureOnce() {
        if (configured) return;
        configured = true;
        // 语言：优先美音 → 通用英文 → 系统默认；都不支持也照常 speak（引擎会用自身默认语音，多数仍能出声）
        int res = tts.setLanguage(Locale.US);
        if (res == TextToSpeech.LANG_MISSING_DATA || res == TextToSpeech.LANG_NOT_SUPPORTED) {
            res = tts.setLanguage(Locale.ENGLISH);
        }
        if (res == TextToSpeech.LANG_MISSING_DATA || res == TextToSpeech.LANG_NOT_SUPPORTED) {
            tts.setLanguage(Locale.getDefault());
        }
        // 音色优化：优先系统的自然/神经英文音色（更接近真人），无则保持引擎默认
        try {
            java.util.Set<android.speech.tts.Voice> voices = tts.getVoices();
            if (voices != null) {
                android.speech.tts.Voice best = null;
                for (android.speech.tts.Voice v : voices) {
                    if (v == null || v.getLocale() == null) continue;
                    if (!"en".equalsIgnoreCase(v.getLocale().getLanguage())) continue;
                    String n = v.getName() == null ? "" : v.getName().toLowerCase();
                    if (n.contains("natural") || n.contains("neural") || n.contains("online")
                            || n.contains("enhanced") || n.contains("premium")) { best = v; break; }
                    if (best == null && (n.contains("female") || n.contains("samantha")
                            || n.contains("aria") || n.contains("jenny") || n.contains("michelle"))) {
                        best = v;
                    }
                }
                if (best != null) tts.setVoice(best);
            }
        } catch (Throwable ignored) { /* 部分引擎 getVoices 异常：忽略，保持默认音色 */ }
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
