"""Verify pinned plugin and SWF recipes; optionally pin portable output hashes.

Metadata creation requires the historical byte-exact release output. Validation
can then run under any zlib implementation. Never writes to the game directory.
"""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from patch_engine import patch_plugin,plugin_content_sha256
from preserve_font_resources import patch_font_bytes,swf_content_sha256
from hud_layout import patch_hud


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--package',type=Path,default=Path(__file__).resolve().parents[1]/'installer-data')
    parser.add_argument('--write-metadata',action='store_true')
    args=parser.parse_args()
    manifest_path=args.package/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    result={'python':sys.version.split()[0],'zlib':zlib.ZLIB_RUNTIME_VERSION,
            'plugins':0,'swfs':0,'byte_exact':0,'compression_variants':0,'translations':0}
    for operation in manifest['operations']:
        if operation['kind'] not in ('text_recipe','font_recipe','hud_recipe'):continue
        blob=(args.package/'blobs'/operation['blob']).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=operation['blob']:raise ValueError('Corrupt recipe blob')
        recipe=json.loads(gzip.decompress(blob))
        if operation['kind']=='text_recipe' and recipe['kind']!='plugin':continue
        source=args.game/operation['target'];original=source.read_bytes()
        if hashlib.sha256(original).hexdigest()!=operation['input_sha256']:
            raise ValueError(f'Expected pinned original: {source}')
        if operation['kind']=='text_recipe':
            output,changes=patch_plugin(original,{tuple(k):tuple(v) for k,v in recipe['translations']})
            digest=plugin_content_sha256(output);key='output_plugin_content_sha256'
            result['plugins']+=1;result['translations']+=len(changes)
        else:
            if operation['kind']=='font_recipe':
                additions={int(fid):{int(c):{k:base64.b64decode(v) for k,v in glyph.items()}
                                    for c,glyph in glyphs.items()} for fid,glyphs in recipe.items()}
                output,_=patch_font_bytes(original,additions)
            else:output=patch_hud(original,recipe)
            digest=swf_content_sha256(output);key='output_swf_content_sha256'
            result['swfs']+=1
        exact=hashlib.sha256(output).hexdigest()==operation['output_sha256']
        if args.write_metadata:
            if not exact:raise ValueError(f'Cannot pin an unverified release output: {source}')
            operation[key]=digest
        elif digest!=operation.get(key):
            raise ValueError(f'File content mismatch: {source}')
        if source.read_bytes()!=original:raise ValueError('Game file changed during verification')
        result['byte_exact']+=exact;result['compression_variants']+=not exact
    if not result['plugins']:raise ValueError('No plugin recipes verified')
    if args.write_metadata:
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
