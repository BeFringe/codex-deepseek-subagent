"""Bind the final candidate to its complete source tree, including raw bytes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

FINAL_PATCH = '14acd83f16c35acef0be7d9e511f3012ffa0bff8b6438a5890dbd3eddddc99d7'
CUMULATIVE = '9804546dabff267b30230ac0b9007867febf9f3c5ea147ce62647dd7603f4bf5'
SOURCE_RECEIPT = '6f5e5b6819287f82eb1ea76b51c6c8659b52ded7d067bf7d52196c945e32f12b'
SOURCE_TREE = '45f946181672a55b78b04506f0436e170576bdde'
COMPLETE_REPLAY = '40f7ca3da65cb3027e53bac0b871b69fa4a1452d8a27d0edf2008ed61ed5d7b7'
COMPLETE_SOURCE_RECEIPT = 'd708e619ac054dd70bb6289b08e3728540ed213c24d4f952196b91d30ed2c418'
SOURCE_FILES = {
    'codex-rs/core/src/tools/g4_catalog_receipt.rs': '959b76e42137bfb147b7d8c94bb00650946d0562ed71bfabac6890e0075c12bb',
    'codex-rs/core/src/tools/handlers/multi_agents_v2/close_agent.rs': '265c526eb0d6c7a0f6eae33e4ae45fb06ff26a92f5857281b334087a3251736b',
}


def raw_source_tree(source_root):
    # A separate index preserves the source checkout's index. Disable Windows
    # newline cleaning so a normalized diff cannot conceal different build bytes.
    with tempfile.TemporaryDirectory(prefix='p7-source-index-') as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / 'index'))
        command = ['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
                   '-c', 'diff.autoRefreshIndex=false', '-C', str(source_root)]
        for args in (['read-tree', 'HEAD'], ['add', '--all']):
            subprocess.run(command + args, env=env, check=True, capture_output=True)
        return subprocess.run(command + ['write-tree'], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()


def verify_current_source(root, source_root, build):
    if build['patch_sha256'] != CUMULATIVE:
        return
    receipt_path = Path(root) / 'probes/current-signed-runtime-g4-explicit-plaintext-delivery-source-candidate.json'
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != SOURCE_RECEIPT:
        raise ValueError('final source chain receipt drift')
    complete_path = Path(root) / 'probes/current-signed-runtime-g4-complete-source-tree-20260912.json'
    if hashlib.sha256(complete_path.read_bytes()).hexdigest() != COMPLETE_SOURCE_RECEIPT:
        raise ValueError('complete source contract receipt drift')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    for entry in receipt['patch_chain']:
        if hashlib.sha256((Path(root) / entry['path']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('final source patch chain drift')
    if (build.get('final_patch_sha256') != FINAL_PATCH
            or build.get('source_chain_receipt_sha256') != SOURCE_RECEIPT
            or build.get('source_tree') != SOURCE_TREE
            or build.get('complete_source_patch_sha256') != COMPLETE_REPLAY
            or build.get('complete_source_receipt_sha256') != COMPLETE_SOURCE_RECEIPT
            or build.get('additional_source_files_sha256') != SOURCE_FILES):
        raise ValueError('complete final source build identity mismatch')
    source_root = Path(source_root)
    actual = {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    if actual != SOURCE_FILES:
        raise ValueError('source files absent from canonical tracked diff changed')
    untracked = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
                               '-c', 'diff.autoRefreshIndex=false', '-C', str(source_root),
                               'ls-files', '--others', '--exclude-standard', '-z'],
                               check=True, capture_output=True).stdout
    if set(untracked.decode('utf-8').rstrip('\0').split('\0')) != set(SOURCE_FILES):
        raise ValueError('unexpected untracked build source files')
    if raw_source_tree(source_root) != SOURCE_TREE:
        raise ValueError('complete raw source tree drift')
