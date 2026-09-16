# 変更者向け開発チェック

実行場所は **UbuntuホストのOpenArm_simリポジトリ直下**。Python 3.10以上が必要です。各コードブロックは、この場所から独立してコピーできます。インストール済み環境の健康診断は `oa-doctor` を使います。

## 既定の軽量チェック

```bash
python3 -B scripts/check_dev.py
```

Python構文（アプリをimportしない）、両モデルの同梱MJCF/XMLとmesh/include/model参照、デモのpackage名・version・ament resource・実行入口、既存の `test_*.py` を検査します。標準ライブラリだけを使い、ネット接続、Docker、ROSは不要です。回帰試験は一時ディレクトリを使います。イメージのビルド・環境停止・腕移動・配置リセット・ユーザーworkspace変更はしません。

```bash
python3 -B scripts/check_dev.py --help
```

```bash
python3 -B scripts/check_dev.py isolated --help
```

静的チェックは、生成されたURDF/YAMLやROS通信、物理動作を実行したという意味ではありません。成功時にも未検証範囲を表示します。

## 明示選択の隔離検証

前提は、起動済みDocker daemonと、**現在の配布ソースからビルドしたローカル検証イメージ**です。次のビルドは任意の別操作で、初回やキャッシュ不足ではネット接続が必要です。チェックコマンド自身はインストール・pull・ビルドをしません。通常環境のタグとは別のタグを使います。

```bash
docker build -t openarm-sim:dev-check -f docker/Dockerfile docker
```

両モデルの生成済みMJCF/URDF/SRDF/ros2_control/MoveIt/関節制限・指の単位/mimic・カタログ物体・メッシュ参照を照合し、既存の材質・支柱法線・D435視界/有限深度試験を実行します。OSMesaのCPU描画なのでGPUは不要です。

```bash
python3 -B scripts/check_dev.py isolated --image openarm-sim:dev-check --suite models
```

さらに既存のOPL物理試験（34対象物・家具・支持面・衝突拒否・カメラ）と、両モデルのプリセット故障復旧/軌道ガード試験を実行します。数分程度かかり、専用プロセスの物体配置を変更します。

```bash
python3 -B scripts/check_dev.py isolated --image openarm-sim:dev-check --suite physics
```

いずれも呼出しごとのランダム名で一時コンテナを作成し、network none、ホストソースの読み取り専用mount、独立した書込み層を使います。ユーザーworkspace、通常コンテナ、ディスプレイ、ホストネットワークへ接続しません。ROSスタックや把持デモは起動しません。開始時にapp/scripts/demo配布ファイルの集合とSHA-256をイメージと比較し、不一致なら失敗します。モデル資産全体の同一性や再ビルドの再現性まで証明する比較ではありません。

各子試験に実時間期限、コンテナ実行全体に480秒の期限があります。成功・失敗・通常のCtrl-C後は、この呼出しが作成したコンテナだけ削除します。ログは端末へ出力し、コンテナ内の試験画像等は削除されます。端末プロセスの強制killやDocker daemon障害では片付けを保証できないため、開始時に表示されたコンテナ名を確認してください。失敗時に通常環境を停止して復旧する処理はありません。

## 結果の読み方

| 終了コード | 意味と対処 |
|---|---|
| 0 | 選択した範囲だけ成功。末尾の未検証項目を確認 |
| 1 | 検査失敗・前提不足・時間切れ。最初のFAIL/traceback/失敗テスト名を確認 |
| 2 | 引数誤り。helpでsuite/image指定を確認 |
| 130 | Ctrl-C中断。合格扱いしない |

ファイル参照の失敗は変更したXMLや取得済みvendorの欠落を確認します。静的構文失敗は表示されたファイルと行を修正します。イメージ不一致は指定タグを確認し、意図したソースから別途再ビルドします。Docker未導入・未起動・イメージなしはチェック失敗であり、自動導入やpullはしません。OSMesa等の依存不足、描画失敗もSKIP/PASSに置き換えません。時間切れはログを確認して原因を切り分けます。

## 残る実動確認

このコマンドは全機能最終検証の代替ではありません。実ROS通信、GUI、単腕/双腕把持、記録・再生、永続化、offline起動や通常環境反映は別途確認します。既存の詳細手順を再利用してください。これらは配置変更・再起動を含むため、各文書の専用コンテナで実施します。

- [描画・同期・ROSの回復](RENDER_SYNC.md)
- [OPL GUI・物理](OPL.md)
- [プリセットGUI・永続化](PRESETS.md)
- [記録GUI・故障時停止・隔離再生](RECORDING.md)

描画回帰の修正前との質量・慣性比較は、修正前データが必要で、このコマンドでは未検証です。ソフトウェア描画の合格は実画面のRViz/GPU表示合格とは区別します。
