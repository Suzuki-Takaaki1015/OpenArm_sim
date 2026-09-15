# OpenArm_sim

Ubuntu 24.04 / ROS 2 Jazzy / MoveIt 2 / MuJoCoによるOpenArm v1双腕の開発環境。
Ubuntu 24.04では `bash start.sh` が不足するPython・venv・Git・Docker・Composeをインストールします。
初回はインターネット接続とsudo権限が必要です。GitがなければリポジトリのZIPをダウンロード・展開しても構いません。
対象はamd64。Ubuntu 24.04のVMで検証し、他OS・GPU実機は未検証です。

```bash
bash start.sh
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
bash start.sh --headless           # GUIなしの開発用
bash start.sh --cpu                # CPU描画を指定
bash start.sh --display browser    # ブラウザー表示を指定
bash start.sh --display native     # ホストGUI必須
bash start.sh --stop
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
bash start.sh --setup-only  # 通常起動でも自動登録
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


## コンテナ内の開発ワークスペース

`oa-code` は Docker の `openarm-auto` に接続し、`/workspaces/OpenArm_dev` を開きます。
VS Code左下にコンテナ接続が表示されます。新しいターミナルで `test -f /.dockerenv && echo container` と `which ros2` を実行して確認できます。
Git、Python、colcon、C/C++ビルドはコンテナ内で実行されます。

`src/` に `git clone <repository-url>` で開発リポジトリをクローンします。
ワークスペース直下で `colcon build --symlink-install`、続いて `source install/setup.bash` を実行します。
Gitのユーザー名・メールや非公開リポジトリの認証は開発者自身が設定してください。
ホストのSSH秘密鍵を自動コピーすることはありません。

ファイルはホストの `<checkout>/.openarm/dev_ws` に保存され、コンテナを作り直しても残ります。
`src`、`build`、`install`、`log` が永続化されます。`.openarm` を削除すると開発データも消えるので注意してください。
環境自体のソースは `/workspaces/OpenArm_sim` にもあります。
`/opt/openarm` の直接編集や共有フォルダー外のデータはコンテナ再作成時に失われます。
追加のOS依存関係を配布する場合は `docker/Dockerfile` に記述し、`bash start.sh --rebuild` で反映します。

## 初回セットアップ

`bash start.sh --setup-only` でホスト依存関係とシェルコマンド登録までを行えます。
既存Dockerが使える場合は置き換えません。新規導入はUbuntuのdocker.io / docker-compose-v2を使用します。
Dockerグループは管理者相当の権限を持ちます。当回の起動はグループを再読み込みし、ログアウトなしで続行します。
既に開いている別ターミナルでDocker権限エラーになる場合はUbuntuからログアウトしてログインしてください。
自動インストールはUbuntu 24.04 amd64のみ対象です。VS Code本体の自動導入はこのスクリプトには含めません。
VS Codeがある場合、`oa-code` がDev Containers拡張を自動導入します。

GPU設定・制御改善・GUI再起動の説明は [PERFORMANCE.md](PERFORMANCE.md) を参照してください。

## オフライン起動

通常は `/usr/bin/bash start.sh` で接続状況を確認します（確認は最大約8秒）。
オフラインと判定した場合はapt更新・インストール・Dockerイメージビルドを行いません。
必要なホストパッケージとローカルイメージが揃っていれば、そのまま起動します。
不足していれば理由を表示して終了します。既存コンテナの停止・置き換え前に判定します。
明示的に通信確認も省く場合は `/usr/bin/bash start.sh --offline` を使用します。
オフライン時は既存イメージを使用するため、未ビルドのソース変更は反映されません。
`--offline --rebuild` は実行せず、理由を表示します。

`start.py`、`install_shell.py`、`scripts/oa_code.py` は内部処理として必要です。
通常操作の入口はstart.shです。シェルコマンドは起動時に自動登録されます。
既に開いている端末へ反映する場合のみ `source ~/.bashrc` を実行してください。
子プロセスのstart.shから、親ターミナルの関数を直接変更することはできません。

## 把持物体の指定配置

シーンGUIの「位置を指定して配置」で直方体／ボトルを選択し、X・Y（m）と向き（度）を入力して「指定位置へ配置」を押します。
world座標でXは前方、Yは左方向です。高さは机上へ自動調整します。
「手前・左」「手前・右」は入力値を変更するプリセットです。続けて「指定位置へ配置」を押してください。
既に表示中の物体も移動できます。机外・アームや他物体との重なりは拒否し、元の位置を保持します。
配置操作は腕を止めてから行ってください。プリセットは把持成功を保証するIK検証済み姿勢ではありません。
MoveItの衝突物体も物理シミュレーションの位置へ同期します。
