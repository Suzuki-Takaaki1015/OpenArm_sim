# OpenArm_sim

OpenArm v1双腕 / Ubuntu 24.04 / ROS 2 Jazzy / MoveIt 2 / MuJoCo。

## クローン後の実行

Python 3.10以上と、起動済みのDockerとCompose v2が必要です。Ubuntuではpython3-venvも用意します。
ROSやMuJoCoのホスト側インストールは不要です。

```bash
python3 start.py
```

Windowsでは `py -3 start.py` を使います。Linuxコンテナモードが必要です。
ランチャーがOS、DockerのCPUアーキテクチャとメモリー、venv、イメージ、GPU描画、
ROSの5コントローラーを順に確認し、[CHECK] / [OK] / [WARN] / [FAIL]で進捗を表示します。
初回ビルドはネット接続と数GBのダウンロードが必要です。ログは `.openarm/build.log`。
ソース変更を検出すると自動で再ビルドします。通常の2回目以降はイメージを再利用します。

`.venv` は標準ライブラリーだけのランチャー専用環境です。
シミュレーション用venvはDocker内の `/opt/venv` に作られ、MuJoCoなどを格納します。
Docker・GPUドライバー・管理者設定を勝手にインストール/変更することはありません。
不足時には必要な操作を表示します。

## GPUとCPUの選択

- Linux + ローカルDocker Engine + X11/XWaylandセッションで、NVIDIAまたはMesaのGPUを候補にします。
- 同じコンテナ・ユーザー・デバイス・X認証でglxinfoを実行し、ハードウェアOpenGLを確認します。
- GPU時はホストのデスクトップにRVizとMuJoCoのウィンドウを表示します。
- GPUが使えない場合はCPUソフトウェア描画＋noVNCへ自動切り替えます。
- CPU時は http://localhost:6080/vnc.html?autoconnect=true&resize=scale を開きます。
- SSH端末にDISPLAYがなければCPUを選びます。GPU表示はLinuxデスクトップの端末から実行してください。
- NVIDIAはホストドライバーとNVIDIA Container Toolkitが必要です。未設定時はCPUへ切り替えます。
- GPUは描画を高速化します。今回のMuJoCo物理演算はCPUです（MJXへの変更ではありません）。
- Windows Docker Desktop、Intel MacはCPUブラウザー表示を使います。この構成ではWSL2のCUDA対応だけでOpenGL利用可能とは判定しません。
- ARM64 / Apple Silicon / リモートDockerは未対応として明示的に停止します。
- VMwareで物理GPUがゲストへ見えない場合もCPUで実行できます。

```bash
python3 start.py --cpu                 # CPUを指定
python3 start.py --gpu                 # GPU必須。使用できなければ停止
python3 start.py --check               # チェック・ビルド・GPU検査まで
python3 start.py --port 6081           # CPU画面のポート変更
python3 start.py --rebuild             # 再ビルド
python3 start.py --logs                # ログ表示
python3 start.py --stop                # 停止
```

ランチャー専用のコンテナ名は `openarm-auto` です。同じ名前を他のクローンが使用している場合は停止しません。
再実行すると自分のコンテナを再作成し、ロボットの姿勢も初期化します。
表示ポートは127.0.0.1のみ。GPU時は必要なGPUデバイスとX11ソケット、認証ファイルを共有します。
`xhost +` やprivilegedは使用しません。

## ROS操作・検証

```bash
docker exec -it openarm-auto /opt/openarm/scripts/entrypoint.sh bash
# 上記ターミナル内
ros2 control list_controllers
# ホストからMoveItの実行検証
docker exec openarm-auto /opt/openarm/scripts/entrypoint.sh python /opt/openarm/app/check_moveit.py --existing
```

RVizでPlanning Groupを選択し、手先を動かしてPlan、Executeで実行します。
詳細は [Docker操作手順](docker/README.md)、既存の物理/MoveIt検証は [検証記録](docker/VALIDATION.md)。
ランチャーの実機検証範囲はLAUNCHER_VALIDATION.mdを参照してください。

公式資料: [Docker](https://docs.docker.com/engine/install/ubuntu/)、
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)、
[Docker Desktop GPUの範囲](https://docs.docker.com/desktop/features/gpu/)。
