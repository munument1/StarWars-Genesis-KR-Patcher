"""Read-only corpus regression for every pinned Genesis ESM plugin recipe.

No output game files are ever created. Uses original Game/mods files and the
release package to validate identity anchors and in-memory compatible edits.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from patch_engine import patch_plugin,check_translation
from plugin_anchors import remap_translations


def main():
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument('--game',type=Path,required=True)
    arg.add_argument('--package',type=Path,default=Path(__file__).resolve().parents[1]/'installer-data')
    args=arg.parse_args()
    pkg=args.package
    manifest=json.loads((pkg/'manifest.json').read_text('utf-8'))
    anchordata=(pkg/'compatibility-anchors.json').read_bytes()
    assert hashlib.sha256(anchordata).hexdigest()==manifest['compatibility_anchor_sha256']
    anchors=json.loads(anchordata)['plugins']
    result={'plugins':0,'identified':0,'skipped_unsupported':0,'unchanged_originals':0,
            'compatible_changed':0,'missing':0,'source_changed':0,
            'translation_pairs_checked':0}
    for op in manifest['operations']:
        if op['kind']!='text_recipe':
            continue
        rec=json.loads(gzip.decompress((pkg/'blobs'/op['blob']).read_bytes()))
        for key,spec in rec['translations']:
            if spec[0]!=spec[1]:check_translation(spec[0],spec[1])
            result['translation_pairs_checked']+=1
        if Path(op['target']).suffix.lower() not in ('.esm','.esp'):
            continue
        original=(args.game/op['target']).read_bytes()
        original_hash=hashlib.sha256(original).hexdigest()
        if original_hash!=op['input_sha256']:
            raise RuntimeError(f"Input is not pinned original: {op['target']}")
        mapping={tuple(k):tuple(v) for k,v in rec['translations']}
        anchored,aliases,skips=remap_translations(original,mapping,anchors[op['target']])
        new,changes,errors=patch_plugin(original,anchored,compatible=True)
        if any(reason not in ('unsupported_formid',) for key,reason in skips):
            raise RuntimeError(f'Unexpected identity mismatch: {op["target"]}: {skips[:5]}')
        if errors:
            raise RuntimeError(f'Unexpected changed/missing source: {op["target"]}: {errors[:5]}')
        if original_hash!=hashlib.sha256((args.game/op['target']).read_bytes()).hexdigest():
            raise RuntimeError('Game input changed during validation')
        result['plugins']+=1
        result['identified']+=len(anchored)
        result['skipped_unsupported']+=len(skips)
        result['compatible_changed']+=len(changes)
        result['unchanged_originals']+=1
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
