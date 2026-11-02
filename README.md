# 单词复习本（离线单文件版）

个人离线单词 / 六级复习本。应用本体是单个 HTML（无框架、无外部依赖），题库、听力与音频全部随包，学习进度存浏览器 localStorage，完全离线可用。

当前版本 `1.9.29`：六级 32 套卷 / 1035 题，听力 53 个音频（约 325 MB）。

## 目录

- `www/index.html` —— 应用本体：样式、逻辑、热更逻辑都在这一个文件里（改它要同步两处 `APP_VERSION`）
- `www/cet6-exams.json` —— 六级题库（32 套 / 1035 题，含选项、原文段落）
- `www/listening.json` —— 听力原文与译文（四级、六级各套）
- `www/listen/*.m4a` —— 听力音频 53 个，约 325 MB（AAC-LC 32 kbps 单声道）
- `www/listen-timing.json` —— 每套听力的句级时间轴（`turns`），用于精听定位
- `www/cet4.json` / `www/cet6.json` —— 词表（四级 4544 词、六级 6662 词）；`www/dict.json` —— 释义库
- `www/latest.json`、`www/index-<版本>.html` —— **热更源，由 CI 生成，不要手改、不要手删**
- `.github/workflows/build-apk.yml` —— CI：打 APK / 发 Release / 生成热更资产 / 部署 Pages
- `scripts/` —— CI 用的补丁脚本（版本号、TTS 桥、APK 更新桥、签名、热更资产）
- `capacitor.config.json`、`package.json`、`assets/` —— Capacitor 壳、依赖与图标启动图素材
- `android-signing/debug.keystore` —— 固定 debug 签名，保证新 APK 可覆盖安装升级
- `archive/` —— 历史数据留存

## 打包与发布

1. 推送 `main` → Actions 自动构建 APK（产物在该次 Actions 的 artifact 里）
2. 打标签 `git tag vX.Y.Z && git push --tags` → 自动建 Release 并附 `app-debug.apk`，同时生成 `www/latest.json` 与 `www/index-X.Y.Z.html` 提交回 `main`，再部署 GitHub Pages

## 两条更新路径

- **只改界面 / 逻辑（HTML）**：打 tag 后手机在应用内「检查更新」即可热更，不用重装。热更源按顺序取：Gitee → GitHub Pages 的 `latest.json` → gh-pages → jsdelivr 兜底
- **改了数据或音频**（题库、听力原文、音频）：热更覆盖不了，必须发新 APK 整包重装。重装前应用内「导出备份」，装好后「导入备份」

## 开发历程

全周期记录（2026-10-22 起笔 → 1.9.29 收尾）：`HISTORY.md`；手机可看排版版：`www/history.html`（部署在 Pages，约 `https://zyh180518-maker.github.io/wordbook/www/history.html`）。

## 手机安装

下载 Release 里的 `app-debug.apk`（约 330–350 MB，音频占大头）→ 允许"安装未知来源应用" → 安装 → 打开即用（完全离线）。签名固定，新版本可直接覆盖安装。

## 备份数据

应用内「导出备份」可下载 / 复制完整 JSON；「导入备份」一键恢复。
