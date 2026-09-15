# センサー・把持対象の環境API

## D435相当の仮想RGB-Dカメラ

公式OpenArm v1のD435胸部マウントを想定した仮想センサーです。
公式CAD: https://github.com/enactic/openarm_hardware/releases/tag/1.1.0
D435仕様: https://www.realsenseai.com/products/stereo-depth-camera-d435/

公式STEPの取付面・ネジ穴に基づく配置です。M6高さ740 mmは本環境で定めた組立基準です。実機も同じ高さに取り付けてください。[取付寸法図と導出](CAMERA_MOUNT.md)を参照。個体校正は別途必要です。

初期OFF。GUIの「配信開始」で有効化。既定2 fps、color 320x180、depth 424x240。
低負荷設定なので実機のストリームモードをそのまま再現するものではありません。
RGB垂直FOV42度、depth58度を基準とした理想ピンホール投影です。
解像度/FPS/FOV/距離範囲はcamera_config.jsonで変更して再ビルドできます。

| トピック | メッセージ / 内容 |
|---|---|
| /camera/camera/color/image_raw | sensor_msgs/Image、rgb8 |
| /camera/camera/color/camera_info | sensor_msgs/CameraInfo |
| /camera/camera/depth/image_rect_raw | sensor_msgs/Image、16UC1、mm、無効値0 |
| /camera/camera/depth/camera_info | sensor_msgs/CameraInfo |
| /camera/camera/aligned_depth_to_color/image_raw | color画角に整列した16UC1深度 |
| /camera/camera/aligned_depth_to_color/camera_info | colorと同じ内部パラメーター |
| /tf_static | camera_link、camera_color_optical_frame、camera_depth_optical_frame |

光学座標はx右、y下、z前。各フレームのstampは同じMuJoCo状態のシミュレーション時刻。
画像とCameraInfoはRELIABLE / VOLATILE / KEEP_LAST(2)。RViz標準のRELIABLE受信とsensor_dataのBEST_EFFORT受信の両方に対応します。CameraInfoは実際の描画解像度/FOVから生成。
深度は光軸方向のZ距離です。対応するCameraInfoとTFを使って3次元座標へ変換します。
画像からの物体認識、位置推定、把持姿勢生成はメンバー側で実装してください。

理想RGB-Dであり、RealSenseデバイス/USB/librealsenseのエミュレーターではありません。
RGB/depthには公式URDFの公称15 mmオフセットを使用し、個体ごとの外部校正・歪み・
IR照射・ステレオマッチング・欠測ノイズ・透明PETの深度誤差は再現しません。
カメラは物理計算と別プロセスで描画しますが、CPU/メモリーは消費します。
停止ボタンは配信を停止します。ロード済み描画モデルのメモリーはプロセス終了まで保持します。

## 自由に動く把持対象

GUIで種類ごとに配置・削除・ランダム再配置できます。初期状態は未配置。
配置時は机も有効化。物体がある間は机の削除を拒否します。
机上の範囲内へランダム配置し、既存物体やロボットとの初期重なりを避けます。
配置・削除・再配置は腕を停止させ、実行中の軌道がないときに操作します。

- 直方体: 50x40x80 mm、100 g。
- ボトル: 最大径約65 mm、高さ約215 mm、525 g（満水500 mL相当の代表近似）。
  円柱・肩・口・キャップを組み合わせた不透明な剛体。メーカー固有形状ではありません。

どちらもMuJoCoのfree jointを持ち、重力・接触・摩擦で移動/落下します。
指への固定や自動attachによる擬似把持は行いません。
PETの弾性変形や液体の揺れは含まず、把持成功を保証する接触調整もしていません。
MoveIt側へ現在姿勢を反映します。ボトルのMoveIt衝突形状は保守的な円柱近似です。
メンバーの把持モジュールがMoveItでattachした物体は、この更新から除外します。
MoveItのattachはMuJoCoの物理拘束を作らないため、実際の保持は指の接触に依存します。

| API | 用途 |
|---|---|
| /openarm/objects/box/set_enabled | std_srvs/SetBool、直方体の配置/削除 |
| /openarm/objects/bottle/set_enabled | std_srvs/SetBool、ボトルの配置/削除 |
| /openarm/objects/{box,bottle}/reposition | std_srvs/Trigger、再配置 |
| /openarm/camera/set_enabled | std_srvs/SetBool、カメラ配信 |
| /openarm/camera/status | std_srvs/Trigger、配信状態・エラー |
| /openarm/scene/status | std_srvs/Trigger、物体の配置状態 |
| /openarm/sim_state | std_msgs/StringのJSON、環境内部用の物理状態スナップショット |

/openarm/sim_stateはカメラとMoveIt同期用の真値です。認識アルゴリズムへの入力とは別です。
リセットはスタック再起動で行い、物体未配置・カメラOFFへ戻ります。
