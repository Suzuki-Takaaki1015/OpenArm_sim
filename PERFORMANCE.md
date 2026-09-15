# GPU・制御・復旧

UbuntuホストにはNVIDIAドライバーとNVIDIA Container Toolkitが必要です。
これらはPythonパッケージではなく、venvやDockerイメージだけでは代替できません。
ROS 2とMuJoCo、Python依存関係はコンテナ内にあります。ドライバーをイメージへコピーしないでください。
Toolkit未導入の場合は `/usr/bin/bash scripts/setup_nvidia.sh` をホストで実行します。
Dockerサービスの再起動を伴います。既存ドライバーのインストール・更新は行いません。
公式手順: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

起動: `/usr/bin/bash start.sh`。GPUを必須にする場合は `--gpu` を追加します。
成功時は `rendering: GPU` と `OpenGL renderer string: NVIDIA ...` を確認してください。
物理計算はCPUです。DockerのCPU・メモリの固定上限は設けていません。
MuJoCoとビューアーの同期は目標60 Hz、物理ステップは2 ms、ROS状態更新は100 Hzです。
物理の実時間比率はシーンGUIの「状態を更新」で確認できます（1.00が実時間）。
GPUの使用率を100%にすることや実時間以上で進めること自体は目標にしていません。

以前の外部PDトルク計算では、軽い関節で速度フィードバックが数値的に不安定になる動作を再現しました。
PDをMuJoCoアクチュエーター内に移し、implicitfastで速度フィードバックを扱います。
元のトルク制限と速度指令制限は維持しています。
MuJoCoの積分説明: https://mujoco.readthedocs.io/en/3.3.4/computation/index.html

GUIの「シミュレーションを再起動」は、MuJoCo・コントローラー・MoveIt・RViz・カメラをまとめて再起動します。
腕、作業台、物体、カメラ配信は初期状態に戻り、進行中の軌道も終了します。
シーンGUIと開発コンテナは維持します。Dockerソケットはコンテナへ公開していません。
ROSのサービスが応答しない場合でも、コンテナ内の監督プロセスへ再起動を要求できます。
コンテナ全体が停止した場合はホストで起動スクリプトを実行してください。

2026-09-15: st機（i7 / RTX3060Ti / RAM32GB）でNVIDIA OpenGL、実時間比約1.00、
6回のROS軌道Action成功、GUI再起動後の5コントローラーactiveを確認。
12秒分の単体往復試験では右腕の最大速度が約14.50から0.52 rad/sに改善しました。
この検証は全姿勢・全衝突条件での安定性を保証するものではありません。
