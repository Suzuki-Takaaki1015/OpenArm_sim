# 描画・同期の回帰検証

以下は **Ubuntuホストのリポジトリ直下** で実行します。実動試験は専用コンテナ内の机・物体・attachmentを変更します。通常の `openarm-auto` では実行しないでください。

ホストだけで実行できる同期状態機械・既存診断のテスト：

```bash
python3 -m unittest discover -s tests -v
```

修正したソースから検証用イメージをビルドします。

```bash
docker build -t openarm-sim:render-sync-test -f docker/Dockerfile docker
```

両モデルの材質、表示専用リンク、支柱の三角形保存、D435視界と深度を確認します。

```bash
docker run --rm --network none --gpus all -e LIBGL_ALWAYS_SOFTWARE=0 -e MUJOCO_GL=egl -e NVIDIA_DRIVER_CAPABILITIES=all -v "$PWD/tests/render_model_check.py:/tmp/render_model_check.py:ro" openarm-sim:render-sync-test python /tmp/render_model_check.py
```

モデル2.0の隔離環境を起動します。1.0は `OPENARM_VERSION=1` に変更し、同じ試験を行います。

```bash
docker run -d --name openarm-render-check --network none --gpus all -e OPENARM_VERSION=2 -e ROS_DOMAIN_ID=74 -e LIBGL_ALWAYS_SOFTWARE=0 -e NVIDIA_DRIVER_CAPABILITIES=all openarm-sim:render-sync-test headless
```

試験をコピーします。

```bash
docker cp tests/render_sync_live_check.py openarm-render-check:/tmp/render_sync_live_check.py
```

追加・削除・移動、机、YCB、OPL家具、消失・古い位置からの復旧、attached物体の二重追加防止と独立した実物表示を確認します。

```bash
docker exec openarm-render-check /opt/openarm/scripts/entrypoint.sh python /tmp/render_sync_live_check.py
```

正常終了時は実時間の受信間隔と反映待ち時間を出力します。これは無負荷の厳密なリアルタイム保証ではなく、実際の試験環境での測定値です。画像生成は従来どおり既定2 fpsです。

自由落下の実物追従も確認できます。これは隔離コンテナの物理ノードを短時間停止してテスト用の実物落下を配信し、必ず元のノードを再開します。

```bash
docker cp tests/render_sync_drop_check.py openarm-render-check:/tmp/render_sync_drop_check.py
```

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 openarm-render-check /opt/openarm/scripts/entrypoint.sh python /tmp/render_sync_drop_check.py
```

実GUIの再起動操作と、物理時刻・机・物体・実物表示の初期化を確認します。

```bash
docker cp tests/render_gui_restart_check.py openarm-render-check:/tmp/render_gui_restart_check.py
```

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 openarm-render-check /opt/openarm/scripts/entrypoint.sh xvfb-run -a python /tmp/render_gui_restart_check.py
```

MoveItだけの再起動と、物理状態を保った再同期を確認する場合は最後に実行します。この試験は隔離環境のlaunch親プロセスを停止して自動全体リセットを抑え、move_groupを単独再起動します。試験後はコンテナを削除して終了してください。

```bash
docker cp tests/render_sync_recovery_check.py openarm-render-check:/tmp/render_sync_recovery_check.py
```

```bash
docker exec -e OPENARM_ISOLATED_TEST=1 openarm-render-check /opt/openarm/scripts/entrypoint.sh python /tmp/render_sync_recovery_check.py
```

GUI・RGBD・家具操作は [OPL回帰手順](OPL.md) も実施します。テスト環境の終了：

```bash
docker rm -f openarm-render-check
```
