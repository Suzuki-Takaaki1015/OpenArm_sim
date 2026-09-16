# シーンプリセットの隔離検証

通常環境とユーザーworkspaceを使わず、両モデルそれぞれの専用workspaceをbindしたコンテナで実行する。
必要なROSスタックをheadless起動し、testsをコンテナの/tmpへコピーする。Xvfbは既存イメージのものを使用する。

**検証コンテナ内**（OPENARM_ISOLATED_TEST=1を明示、scene_presets/mixed.jsonのない専用workspace）:

```bash
OPENARM_ISOLATED_TEST=1 xvfb-run -a python /tmp/presets_live_check.py
```

GUIの新規保存・復元・同名拒否、机/builtin/YCB/OPL/衣類12個、物理とMoveIt、無効JSON構造とモデル差異、
衝突拒否、実行中の実ROSアクションを確認する。通常の配置サービスで準備し、実GUIハンドラーを呼ぶ。

**検証コンテナ内・別ROSドメイン**:

```bash
OPENARM_ISOLATED_TEST=1 ROS_DOMAIN_ID=183 python /tmp/presets_transaction_check.py
```

実MuJoCoモデルの復元途中へ故障を注入し、全変更対象の配列・辞書が一致して復旧することを確認する。
JSONサイズ・重複キー・非有限値・パス・リンク・未確認コントローラも検査する。
永続性は検証コンテナを停止・再起動してmixedを読込し、元JSONのハッシュ保持とシーン復元を確認する。
これらの試験は通常GUIを操作しない。
