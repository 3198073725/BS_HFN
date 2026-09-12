# 本地工具

项目使用的 FFmpeg 9.0.1 位于 `ffmpeg/bin`：

- `ffmpeg.exe`：视频转码、HLS 切片和封面生成
- `ffprobe.exe`：提取视频元信息
- `ffplay.exe`：本地播放与调试

后端通过 `backend/.env` 中的相对路径加载这些工具。`ffmpeg` 目录包含大型第三方二进制文件，默认不提交到 Git。
