# OpenArm_sim

Ubuntu 24.04 / ROS 2 Jazzy / MoveIt 2 / MuJoCoによるOpenArm v1双腕の開発環境。
Python 3.10以上、Docker Engine（Linuxコンテナ）とCompose v2が必要です。
対象はamd64。Ubuntu 24.04のVMで検証し、他OS・GPU実機は未検証です。

```bash
python3 start.py
```

OS・Docker・メモリー・venvをチェックし、初回はDockerをビルドします。
2回目以降はソースが変わらなければ既存イメージを再利用します。
ホストの.venvはランチャー用、ROS/MuJoCoの環境はコンテナの/opt/venvです。

## 表示と負荷

Desktopの利用可能なX11/XWaylandセッションではホストGUIに表示。
GPUのOpenGL検査が通ればGPU描画、通らなければCPU描画です。
GUIセッションがないServer/SSH環境ではブラウザー表示を使用します。
Desktop/Serverのインストール名ではなく、接続できるGUIセッションで判定します。

```bash
python3 start.py --headless           # GUIなしの開発用
python3 start.py --cpu                # CPU描画を指定
python3 start.py --display browser    # ブラウザー表示を指定
python3 start.py --display native     # ホストGUI必須
python3 start.py --stop
```

ブラウザー: http://localhost:6080/vnc.html?autoconnect=true&resize=scale
物理計算はCPU。GPUは描画用です。カメラも初期OFFで、必要な時だけGUIから配信します。

## GUIの操作

シーンパネルで作業台、直方体、500 mLボトル、D435配信を操作できます。
物体を配置すると机も有効になります。机を消す前に把持対象を削除してください。
RVizはInteractを選び、MotionPlanning / Planning Request / Query Goal Stateを有効化し、
手先マーカーを動かしてPlan、Executeします。カメラ回転はMove Cameraで左ドラッグ。
MuJoCoは左ドラッグで視点回転、右ドラッグで移動、ホイールで拡大縮小します。

## 短い開発コマンド

```bash
python3 install_shell.py
source ~/.bashrc

oa                          # ROS環境付きコンテナ内ターミナル
oa-ros node list
oa-ros control list_controllers
oa-scene status
oa-logs
```

.bashrcの既存内容を保全し、重複しないsource行を追加します。
Windowsではpy -3 start.py。Windows/macOSのDockerでの実行は未検証でCPU表示を想定。
ARM64/Apple SiliconとリモートDockerは未対応として停止します。
コンテナ名はopenarm-auto。同名を別のクローンが使用中の場合は変更せず停止します。

## メンバー向けインターフェース

カメラトピック、座標、物体サービス、近似範囲は [ENVIRONMENT.md](ENVIRONMENT.md) を参照。
D435は公式マウントの寸法に基づき取り付けます。高さ740 mmは本環境の基準です。[取付寸法図](CAMERA_MOUNT.md)を参照してください。
認識・把持姿勢生成・自動把持のモジュールは含みません。
不要な検証スクリプトは配布ツリーから除き、実行に必要なコードだけを同梱します。
テストを削除しても、wait_ready.pyとgenerate_config.pyは起動に必要なので残しています。

モデルはenactic/openarm_mujocoの固定コミットを使用。
依存パッケージやモデルのライセンスはdocker/THIRD_PARTY.mdとvendor/LICENSEを参照。
イメージを配布する場合はdocker save/loadを使用できます。公開レジストリへのpushは未実施です。

## VS Codeでの開発

Ubuntu DesktopにVS Codeをインストールし、`python3 install_shell.py` と `source ~/.bashrc` を一度実行します。以後は `oa-code` で実行中のコンテナへ接続したVS Codeが開きます。Dev Containers拡張が未導入の場合は自動インストールします。

`oa-code --check` で接続の前提条件を確認できます。コンテナは先に `python3 start.py` で起動してください。古いコンテナは一度再起動すると開発用フォルダーが共有されます。

VS Codeで開く `/workspaces/OpenArm_sim` は、起動したホスト側チェックアウトそのものです。ここで編集したファイルはコンテナを削除・再作成しても残ります。コンテナの `/opt/openarm` へ直接編集した内容はイメージに保存されないため、開発は共有フォルダーで行ってください。シミュレーター本体のソース変更を反映する際は `python3 start.py` で再ビルド・再起動します。

統合ターミナルの既定プロファイルはOpenArm ROS 2で、ROS環境と `/opt/venv` を使用します。初回の接続時はVS Code Serverのダウンロードが発生します。Ubuntuのデスクトップ端末から実行してください。Windows側VS CodeからのRemote SSH接続はこのコマンドの対象外です。
