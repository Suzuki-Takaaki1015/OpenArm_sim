# ランチャー検証記録

## 実行環境

VMware / Ubuntu 24.04 / amd64 / 4 CPUs / 7.7 GiB RAM。
Docker Engine 29.1.3 + Compose v2。イメージ openarm-sim:0.3.0。

## 確認済み

- 初回に `.venv` を作成し、venvのPythonへ切り替えて実行。
- Composeによるイメージ構築、Docker内 `/opt/venv` の利用。
- 再実行でイメージを再利用（ソースのSHA-256ラベルで判断）。
- SSHにX11表示がない場合、理由を表示してCPUブラウザーモードへ切り替え。
- CPUレンダラーはglxinfoでllvmpipe、Accelerated: noを確認。
- 5コントローラーactiveとnoVNCのHTTP応答を待って起動成功を表示。
- GPU必須指定はこのSSH環境で終了コード1となり、理由を表示。
- 起動判断の単体テスト5件はWindows Python 3.12とUbuntuの両方で成功。
- 新ランチャーのコンテナでMoveIt計画・実行が成功。
  両腕の関節目標、右手先の位置姿勢目標、左右グリッパーの開閉を含む。
  手先位置誤差0.656 mm、姿勢誤差0.0393 rad。
  腕最大誤差0.00108 rad未満、指最大誤差4.22 mm未満。
- 完全なJSON結果は `.openarm/moveit-validation.json`、ログは同名.log（ローカル生成物）。

## 未検証・制約

- NVIDIA/AMD/Intel GPU実機での描画は未検証。
  コンテナ内glxinfoと起動状態を確認する実装だが、GPU動作確認済みとはしない。
- Windows/macOSのDockerによるシミュレーション起動は未検証。Windowsではランチャーの単体テストのみ。
- ARM64/Apple SiliconとリモートDockerは未対応として停止する。
- 物理演算はCPU。GPUはOpenGL描画用で、MJX/CUDA物理演算は含まない。
- Python、Docker、Compose、GPUドライバーなどのホスト側前提条件は利用者が用意する。
- 外部PCや新しいOSへの対応は追加の動作確認が必要。
