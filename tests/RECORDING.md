# 記録機能の隔離検証

通常環境の稼働・ユーザーworkspaceを保持し、検証用イメージと空の専用workspaceを使う。
live/error/clock試験はカメラやシミュレーションを操作する。通常コンテナでは実行しない。
全スクリプトは `OPENARM_ISOLATED_TEST=1` を要求する。replayはROS_DOMAIN_ID=184も要求する。
既存の記録名がある場合は同名保護で失敗するので、試験には新しい空ディレクトリを使う。

実行場所: Ubuntuホストのrepoルート。通常イメージとは別名でビルドする。

```bash
docker build -t openarm-sim:recording-check docker
```

実行場所: Ubuntuホストのrepoルート。専用workspaceを作る。

```bash
mkdir -p "$PWD/.openarm/recording-check-v1"
```

実行場所: Ubuntuホストのrepoルート。1.0を隔離起動する。

```bash
docker run -d --name openarm-recording-check-v1 --network none --shm-size 512m --user "$(id -u):$(id -g)" -e OPENARM_VERSION=1 -e HOME=/workspaces/OpenArm_dev -v "$PWD/.openarm/recording-check-v1:/workspaces/OpenArm_dev" -v "$PWD/tests:/tests:ro" openarm-sim:recording-check headless
```

実行場所: Ubuntuホスト。実GUIハンドラー、記録内容、同名・二重起動・終了保護を検証する。

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 openarm-recording-check-v1 /opt/openarm/scripts/entrypoint.sh xvfb-run -a python /tests/recording_live_check.py
```

実行場所: Ubuntuホスト。容量不足はmockで注入し、実際のディスクを満杯にしない。最後にGUI再起動を行う。

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 openarm-recording-check-v1 /opt/openarm/scripts/entrypoint.sh xvfb-run -a python /tests/recording_error_check.py
```

実行場所: Ubuntuホスト。スタック起動完了後、外部再起動による時計後戻り・停止の保護を確認する。

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 openarm-recording-check-v1 /opt/openarm/scripts/entrypoint.sh python /tests/recording_clock_check.py
```

実行場所: Ubuntuホスト。別ドメインの読み取り専用再生試験。

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 -e ROS_DOMAIN_ID=184 openarm-recording-check-v1 /opt/openarm/scripts/entrypoint.sh python /tests/recording_replay_check.py
```

実行場所: Ubuntuホスト。試験終了後に専用コンテナを停止する。記録データは削除しない。

```bash
docker stop -t 25 openarm-recording-check-v1
```

2.0は上記のコンテナ名・workspaceのv1をv2へ、OPENARM_VERSION=1を2へ変更して独立実行する。
停止・起動を跨いでrecordings配下の全ファイルSHA-256を比較する。ROSログ等は比較対象にしない。
GUIが自動記録を再開しないことと、monitor_deathの未完了表示も確認する。

短時間試験は全パケットの無損失や長時間・高解像度記録性能を保証しない。
強制電断のファイル完全性・実ディスク故障の試験は行わない。
