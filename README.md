# 单词复习本（离线单文件版）

个人离线单词复习本：单 HTML 文件，数据存浏览器 localStorage，无需网络。

## 本仓库做什么
- `www/index.html` —— 应用本体（唯一需要维护的文件）
- `.github/workflows/build-apk.yml` —— 推送到 GitHub 后自动用 Capacitor 打包成安卓 APK
- `assets/` —— APK 图标与启动图素材

## 自动打包
1. 推送/合并到 `main` 分支 → GitHub Actions 自动构建 APK（产物在 Actions 的 artifact 里）
2. 打标签 `git tag v1.0.0 && git push --tags` → 自动生成 Release 并附带 APK，手机直接下载安装

## 手机安装 APK
下载 APK → 允许"安装未知来源应用" → 安装 → 打开即用（完全离线）。

## 更新版本
更新 `www/index.html` → 推送 → 重新打包；手机重装新 APK 前先「导出备份」，装好后「导入备份」即可保留数据。

## 备份数据
应用内「导出备份」可下载/复制完整 JSON；「导入备份」一键恢复。
