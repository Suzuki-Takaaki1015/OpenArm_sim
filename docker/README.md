# Docker runtime

リポジトリのstart.pyを使用してください。操作・ビルド手順はルートREADME.md、
カメラ・物体APIはENVIRONMENT.mdを参照します。

単独ビルド: `docker build -t openarm-sim:0.6.0 .`
起動: `docker run --rm --init --shm-size=512m -p 127.0.0.1:6080:6080 openarm-sim:0.6.0`
保存: `docker save openarm-sim:0.6.0 | gzip > openarm-sim-0.6.0-amd64.tar.gz`
復元: `docker load -i openarm-sim-0.6.0-amd64.tar.gz`

Docker内はUbuntu 24.04 + ROS 2 Jazzy。モデルとPython依存を同梱し、起動時の追加取得は不要。
ROS aptは署名検証を保持したHTTPSミラーを使用。再ビルドの完全な同一バイト性は保証しません。

YCBライブラリ103項目は両ロボットで共通です。使い方・近似の範囲・帰属は [YCB.md](YCB.md) を参照してください。
