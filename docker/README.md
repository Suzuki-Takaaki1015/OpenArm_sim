# OpenArm / MuJoCo / MoveIt 2 Docker

Ubuntu 24.04 + ROS 2 Jazzy用のOpenArm v1双腕シミュレーションです。
構築ホストはVMware内のUbuntu 24.04（amd64）。ROSやMuJoCoはコンテナに含みます。
検証結果・配布可否は `VALIDATION.md` を参照してください。

## 構成

```text
RVizのMotionPlanningパネル / ROS 2 MoveGroup action
  -> MoveIt 2（OMPL、KDL）
  -> ros2_control / JointTrajectoryController
  -> JointStateTopicSystem
  -> MuJoCo Pythonブリッジ（PD + バイアス補償）
  -> 関節の実測状態、/clock、TF
```

- 左右7関節の腕と、左右各2関節のグリッパー。
- 物理モデルは公式OpenArm MJCF、MuJoCo 3.3.4。モデルのコミットは `vendor/MODEL_REVISION` に固定。
- URDFを同じMJCFから生成し、全リンクの座標を数値照合。
- MoveItで計画した軌道をMuJoCoのトルク制御で追従。関節位置の直接書き換えによる模擬実行ではありません。
- 軌道制御100 Hz、物理ステップ500 Hz、描画約30 Hz。負荷によって実時間より遅くなります。
- MuJoCoとRVizをコンテナ内の仮想画面で表示。noVNCを通してブラウザーで操作します。
- デフォルトはMesaソフトウェア描画。GPU、ホストのX11共有、privileged設定は不要。

ROSパッケージはTUNAのHTTPSミラーから取得し、ROS公式の署名鍵で検証します。
ミラーはビルド引数 `ROS_APT_MIRROR` で変更できます。起動時には使用しません。

## 起動

ホストに必要なのはDocker EngineとCompose v2です。開発ユーザーがDockerを使える状態にします。

```bash
cd ~/openarm-docker
docker compose build
docker compose up -d
docker compose logs -f sim
```

Ubuntu VM内のブラウザー:

http://localhost:6080/vnc.html?autoconnect=true&resize=scale

ROSコマンド用ターミナル:

```bash
docker compose exec sim /opt/openarm/scripts/entrypoint.sh bash
ros2 control list_controllers
ros2 action list
ros2 topic echo /joint_states --once
```

起動時に5つのコントローラーがactiveになるまで待ちます。
`left_arm_controller`、`right_arm_controller`、`left_gripper_controller`、
`right_gripper_controller`、`joint_state_broadcaster`です。

## RViz / MoveIt 2で操作

1. RVizのMotionPlanningでPlanning Groupを `right_arm` または `left_arm` にする。
2. 手先のインタラクティブマーカーを少し動かす。
3. **Plan** で軌道を確認し、**Execute** でMuJoCo内の腕を動かす。
4. または **Plan & Execute** を使用する。
5. グリッパーは `right_gripper` / `left_gripper` と、名前付き目標 `open` / `home` を使う。

初期検証では、小さな動作と速度・加速度倍率0.2を使っています。
運動学的に届かない目標、関節限界、自己干渉では計画が失敗する場合があります。
noVNC画面内にMuJoCoとRVizの両ウィンドウがあります。左右に並べて表示します。Alt+Tabでも切り替えられます。
MuJoCoのcontrolスライダーは制御ループが上書きするため、指令はROS側から送ります。

## 画面なしの検証

```bash
# ROSや表示を介さない物理テスト
docker compose run --rm --no-deps sim physics-test
# URDFとMuJoCoの全リンク座標を12姿勢で照合
docker compose run --rm --no-deps sim python /opt/openarm/app/test_kinematics.py
# 専用コンテナ内でスタックを起動し、MoveItの計画と実行を検証
docker compose run --rm --no-deps sim check
```

`check` は両腕の関節目標、右手先の位置・姿勢目標、左右グリッパーの開閉を
MoveGroup action経由で実行し、MuJoCoの実測状態で追従を確認します。
単なる計画成功やアクション応答だけで成功と判定しません。
既存のGUIスタックで同じ検証を実行する場合:

```bash
docker compose exec sim /opt/openarm/scripts/entrypoint.sh \
  python /opt/openarm/app/check_moveit.py --existing
```

表示なしで常時稼働する場合:

```bash
docker compose run --rm --no-deps sim headless
```

## ROSインターフェース

| 名前 | 内容 |
|---|---|
| `/move_action` | MoveIt MoveGroup action |
| `/left_arm_controller/follow_joint_trajectory` | 左腕のFollowJointTrajectory action |
| `/right_arm_controller/follow_joint_trajectory` | 右腕のFollowJointTrajectory action |
| `/left_gripper_controller/follow_joint_trajectory` | 左の2本指を同時指令 |
| `/right_gripper_controller/follow_joint_trajectory` | 右の2本指を同時指令 |
| `/joint_states` | ros2_controlが配信する状態 |
| `/mujoco/joint_states` | MuJoCoから読み出した実測状態 |
| `/mujoco/joint_commands` | ros2_controlから物理ブリッジへの内部指令 |
| `/clock` | MuJoCoのシミュレーション時刻 |
| `/tf`、`/tf_static` | 同じURDFに基づく座標変換 |

ROS_DOMAIN_ID=42、ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOSTが既定です。
まず全ノードを同一コンテナ内で使います。別コンテナ/ホストとのDDS通信は別途設定が必要です。
内部の `/mujoco/joint_commands` へ直接送るとコントローラーの指令と競合するため、
利用者はMoveItまたはFollowJointTrajectory actionを使います。
リセットは `docker compose restart sim` でスタック全体を再起動します。

## Windowsから画面を開く

VM内のブラウザーを使う場合、追加設定は不要です。
Windowsからは、SSHログイン可能なユーザーでトンネルを作成します。

```powershell
ssh -N -L 6080:127.0.0.1:6080 USER@VM_IP
```

そのままWindowsで同じlocalhost URLを開きます。
開発用SSH鍵はホスト側だけにあり、イメージや配布物には含めません。
Web画面に認証は付けていないため、既定の公開先はVMの127.0.0.1に限定しています。

## 開発

```bash
docker compose down
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
# app配下を編集後
docker compose restart sim
```

`generate_config.py` や依存関係を編集した場合はイメージを再ビルドしてください。
配布時は `compose.yaml` 単体を使い、ホストのソースをマウントしません。

## イメージの配布

検証済みイメージをファイルとして保存します。起動時のGitHub/PyPI接続は不要です。

```bash
mkdir -p release
docker image inspect openarm-sim:0.2.0 > release/image-inspect.json
docker save openarm-sim:0.2.0 | gzip > release/openarm-sim-0.2.0-amd64.tar.gz
(cd release && sha256sum openarm-sim-0.2.0-amd64.tar.gz > SHA256SUMS)
```

配布先（amd64 LinuxのDocker環境）:

```bash
sha256sum -c SHA256SUMS
gunzip -c openarm-sim-0.2.0-amd64.tar.gz | docker load
docker run --rm --init --shm-size=512m \
  -p 127.0.0.1:6080:6080 --name openarm-sim openarm-sim:0.2.0
```

Docker Hub/GHCRには公開していません。完成イメージ、ソース、検証記録、
第三者ライセンスを合わせて保管します。aptや推移依存は完全固定ではないため、
再ビルドで同一バイトは保証しません。同じ環境の配布にはイメージのtarまたはdigestを使用します。

## 範囲と制約

- OpenArm **v1** の双腕モデルを対象とします。v2や実機接続は対象外です。
- ホスト目安:4 vCPU、8 GB RAM以上。ビルド/イメージ保管用に空き20 GB以上。
- 姿勢の到達性と自己干渉をMoveItで扱います。物体把持や接触精度の検証済み環境ではありません。
- 画面の床は表示用で、床との物理接触は無効です。
- URDFの衝突形状とMuJoCoの接触判定方式は同一ではありません。
- トピック接続による遅延があります。ハードリアルタイム用途ではありません。
- 指のアクチュエータ形式は公式モデルで左右が異なります。
- ARM64、Windows/macOSのDocker Desktopは、このVMでの検証とは別に確認が必要です。

## 上流

- OpenArm MJCF: https://github.com/enactic/openarm_mujoco
- ROS 2 Jazzy: https://www.ros.org/reps/rep-2000.html
- MoveIt 2: https://moveit.picknik.ai/
- Topic hardware interface: https://github.com/ros-controls/topic_based_hardware_interfaces
- MuJoCo: https://mujoco.readthedocs.io/en/stable/python.html
- Docker: https://docs.docker.com/engine/install/ubuntu/
