"""Generate checked, noncopyrighted target metadata from the pinned Genesis originals.

Run against a clean unmodified Genesis 8.8.4 Game directory. All input files
must match the manifest's pinned SHA-256. Outputs only MAST/EDID metadata, not
the actual game plugin bytes or translated content.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plugin_anchors import build_anchor
from patch_engine import patch_plugin


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True)
    p.add_argument('--package',type=Path,default=Path(__file__).resolve().parents[1]/'installer-data')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Never overwrite a generated compatibility anchor file')
    manifest=json.loads((args.package/'manifest.json').read_text(encoding='utf-8'))
    result={'schema':1,'target_version':manifest['target_version'],'plugins':{}}
    for op in manifest['operations']:
        if op['kind']!='text_recipe' or Path(op['target']).suffix.lower() not in ('.esm','.esp'):
            continue
        plugin=args.game/op['target']
        data=plugin.read_bytes()
        if hashlib.sha256(data).hexdigest()!=op['input_sha256']:
            raise ValueError(f'Input hash differs; cannot create release anchors: {op["target"]}')
        raw=(args.package/'blobs'/op['blob']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=op['blob']:
            raise ValueError(f'Invalid recipe: {op["target"]}')
        recipe=json.loads(gzip.decompress(raw))
        if recipe['kind']!='plugin':raise ValueError('Expected ESM recipe')
        mapping={tuple(k):tuple(v) for k,v in recipe['translations']}
        anchor=build_anchor(data,mapping)
        result['plugins'][op['target']]=dict(input_sha256=op['input_sha256'],**anchor)
    if not result['plugins']:raise ValueError('No pinned plugin inputs were found')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf-8')
    print(f"Anchored {len(result['plugins'])} plugins, "
          f"{sum(len(x['edids']) for x in result['plugins'].values())} record identities")


if __name__=='__main__':main()
