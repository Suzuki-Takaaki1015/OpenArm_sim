#!/usr/bin/env python3
"""Offline source checks, or explicitly selected disposable-container checks."""
import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_files(root):
    for folder in ('docker/app', 'docker/scripts', 'docker/demos', 'scripts', 'tests'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and not any(p.endswith('.egg-info') for p in path.parts):
                yield path
    yield from sorted(root.glob('*.py'))


def models(root):
    """Check pinned XML and file references without importing MuJoCo."""
    for version in (1, 2):
        folder = root / f'docker/vendor/v{version}'
        paths = sorted(folder.rglob('*.xml'))
        require(paths, f'モデル{version}: XMLがありません: {folder}')
        refs = 0
        for path in paths:
            tree = ET.parse(path)
            compiler = tree.find('compiler')
            meshdir = compiler.get('meshdir', '') if compiler is not None else ''
            for node in tree.iter():
                value = node.get('file')
                if value is None or node.tag not in ('include', 'model', 'mesh'):
                    continue
                target = path.parent / (meshdir if node.tag == 'mesh' else '') / value
                require(target.is_file(), f'{path.relative_to(root)}: {node.tag}参照がありません: {target}')
                refs += 1
        print(f'PASS 静的モデル{version}: XML {len(paths)} / ファイル参照 {refs}', flush=True)


def samples(root):
    package = root / 'docker/demos/openarm_demos'
    xml = ET.parse(package / 'package.xml')
    name = xml.findtext('name')
    require((package / 'resource' / name).is_file(), 'ament resourceとpackage名が不一致')
    tree = ast.parse((package / 'setup.py').read_text(encoding='utf-8'))
    setup = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'setup')
    values = {n.arg: ast.literal_eval(n.value) for n in setup.keywords}
    require(values['name'] == name, 'setup.py / package.xmlの名前が不一致')
    require(values['version'] == xml.findtext('version'), 'setup.py / package.xmlのversionが不一致')
    for entry in values['entry_points']['console_scripts']:
        target = entry.split('=', 1)[1].strip()
        module, function = target.split(':')
        path = package.joinpath(*module.split('.')).with_suffix('.py')
        code = ast.parse(path.read_text(encoding='utf-8'))
        require(any(isinstance(n, ast.FunctionDef) and n.name == function for n in code.body), f'entry pointがありません: {entry}')
    print('PASS サンプル: package名/version/ament resource/実行入口', flush=True)


def static():
    count = 0
    for path in source_files(ROOT):
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            count += 1
    print(f'PASS Python構文 {count}ファイル（import/実行なし）', flush=True)
    models(ROOT)
    samples(ROOT)
    # Empty or skipped suites are not complete regression passes.
    runner = ('import sys, unittest; '
              'suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py"); '
              'result = unittest.TextTestRunner(verbosity=2).run(suite); '
              'sys.exit(0 if result.testsRun and result.wasSuccessful() and not result.skipped else 1)')
    subprocess.run([sys.executable, '-B', '-c', runner], cwd=ROOT, check=True, timeout=90)
    print('PASS 静的チェックとホスト回帰試験\n未検証: 生成設定・実描画・ROS通信・GUI・腕動作。実行中環境の診断はoa-doctor。', flush=True)


def isolated(args):
    require(sys.platform.startswith('linux'), 'isolatedはDockerを利用できるUbuntuホストで実行してください')
    require(args.image, 'isolatedには --image が必要です（自動pull/buildなし）')
    image_id = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    require(image_id.startswith('sha256:'), 'ローカルイメージIDを取得できません')
    name = 'openarm-dev-check-' + uuid.uuid4().hex
    print(f'隔離試験: suite={args.suite}, image={image_id}, container={name}', flush=True)
    command = ['docker', 'run', '--rm', '--pull=never', '--name', name, '--network', 'none',
               '--cap-drop=ALL', '--security-opt=no-new-privileges',
               '--mount', f'type=bind,src={ROOT},dst=/source,readonly',
               '-e', 'OPENARM_ISOLATED_TEST=1', '-e', 'MUJOCO_GL=osmesa',
               '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'ROS_DOMAIN_ID=183',
               image_id, 'python', '/source/tests/generated_model_check.py', '--suite', args.suite]
    try:
        subprocess.run(command, check=True, timeout=480)
    finally:
        # Only the unguessable name created by this invocation; never an existing demo.
        result = subprocess.run(['docker', 'rm', '-f', name], capture_output=True, text=True, timeout=20)
        if result.returncode and 'No such container' not in result.stderr:
            raise RuntimeError(f'隔離コンテナの片付けを確認できません: {name}: {result.stderr}')
    print('PASS 選択した隔離試験のみ。未検証: ROS通信・実GUI・把持・記録・全機能統合。', flush=True)


def main():
    parser = argparse.ArgumentParser(description='変更者向け開発チェック。既定はネット/Docker/ROS不要。oa-doctorは実行中環境の診断用。',
        epilog='終了コード: 0=選択範囲のみ成功、1=失敗/前提不足/時間切れ、2=引数誤り、130=中断。全機能合格を意味しません。')
    sub = parser.add_subparsers(dest='mode')
    sub.add_parser('static', help='既定: Python構文、両モデルXML参照、サンプル整合、既存test_*.py（Ubuntu/Python 3.10+）')
    live = sub.add_parser('isolated', help='明示選択: ローカルイメージからnetwork none一時コンテナ。pull/build/通常環境操作なし')
    live.add_argument('--image', required=True, help='現在ソースをビルドしたローカル検証イメージ。配布ソース一致を先に検査')
    live.add_argument('--suite', choices=('models', 'physics'), default='models', help='models: 両モデル設定・D435描画。physics: 加えて既存OPL物理/プリセット復旧試験。ROSスタックは起動しない')
    args = parser.parse_args()
    try:
        static() if args.mode in (None, 'static') else isolated(args)
        return 0
    except KeyboardInterrupt:
        print('中断: 合格ではありません', file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, SyntaxError, ET.ParseError, subprocess.SubprocessError, StopIteration, KeyError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
