import gzip,json,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import installer_backend as backend

class InstallerTests(unittest.TestCase):
    def test_swf_compression_variants_verify_full_content_apply_and_restore(self):
        import base64,zlib
        from preserve_font_resources import swf_content_sha256,patch_font_bytes
        from hud_layout import patch_hud
        body=b'\0'+b'\0'*4+struct.pack('<H',(37<<6)|4)+b'\x01\0AB'+b'\0\0'
        original=b'CWS\x0a'+struct.pack('<I',len(body)+8)+zlib.compress(body,1)
        for kind in ('font_recipe','hud_recipe'):
            with self.subTest(kind=kind):
                target=f'mods/TestMod/{kind}.swf';source=self.game/target;source.write_bytes(original)
                recipe={} if kind=='font_recipe' else {'replacements':[{'tag':37,'id':1,
                    'input_sha256':backend.sha(b'\x01\0AB'),'body':base64.b64encode(b'\x01\0CD').decode()}]}
                expected=patch_font_bytes(original,{})[0] if kind=='font_recipe' else patch_hud(original,recipe)
                raw=gzip.compress(json.dumps(recipe).encode());blob=backend.sha(raw)
                (self.package/'blobs'/blob).write_bytes(raw)
                op={'target':target,'kind':kind,'blob':blob,'input_sha256':backend.sha(original),
                    'output_sha256':backend.sha(expected)}
                def write():
                    (self.package/'manifest.json').write_text(json.dumps({'default_profile':'test','operations':[op]}))
                compress=zlib.compress
                with patch('preserve_font_resources.zlib.compress',side_effect=lambda data,level=-1:compress(data,0)):
                    write()
                    with self.assertRaisesRegex(backend.InstallError,'Generated output checksum failed'):self.prepare()
                    op['output_swf_content_sha256']='0'*64;write()
                    with self.assertRaisesRegex(backend.InstallError,'Generated output checksum failed'):self.prepare()
                    op['output_swf_content_sha256']=swf_content_sha256(expected);write()
                    prepared=self.prepare()['operations'][0]
                self.assertTrue(prepared['compression_variant'])
                staged=(self.stage/target).read_bytes();self.assertNotEqual(staged,expected)
                self.assertEqual(swf_content_sha256(staged),swf_content_sha256(expected))
                backup=backend.apply(self.stage);self.assertEqual(source.read_bytes(),staged)
                backend.restore(backup);self.assertEqual(source.read_bytes(),original)

    def test_compression_variant_requires_pinned_content_and_apply_restore_byte_hashes(self):
        import zlib
        from test_patch_engine import record,field,group
        from patch_engine import patch_plugin,plugin_content_sha256
        original=record(b'TES4',b'')+group(record(b'MISC',field(b'FULL',b'Hello\0')+field(b'ZZZZ',b'opaque'*100),1,0x40000))
        mapping={('MISC',1,'FULL',0):('Hello','안녕하세요')}
        expected,_=patch_plugin(original,mapping)
        target='mods/TestMod/Example.esm';source=self.game/target;source.write_bytes(original)
        recipe=gzip.compress(json.dumps({'kind':'plugin','translations':[[list(k),list(v)] for k,v in mapping.items()]},ensure_ascii=False).encode())
        blob=backend.sha(recipe);(self.package/'blobs'/blob).write_bytes(recipe)
        operation={'target':target,'kind':'text_recipe','blob':blob,'input_sha256':backend.sha(original),
                   'output_sha256':backend.sha(expected)}
        manifest={'default_profile':'test','operations':[operation]}
        def write():
            (self.package/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        compress=zlib.compress
        with patch('patch_engine.zlib.compress',side_effect=lambda data:compress(data,0)):
            for digest in (None,'0'*64):
                if digest is None:operation.pop('output_plugin_content_sha256',None)
                else:operation['output_plugin_content_sha256']=digest
                write()
                with self.assertRaisesRegex(backend.InstallError,'Generated output checksum failed'):self.prepare()
                self.assertFalse((self.stage/'prepared.json').exists())
            operation['output_plugin_content_sha256']=plugin_content_sha256(expected);write()
            prepared=self.prepare()['operations'][0]
        staged=(self.stage/target).read_bytes()
        self.assertNotEqual(staged,expected)
        self.assertEqual(plugin_content_sha256(staged),operation['output_plugin_content_sha256'])
        self.assertTrue(prepared['compression_variant'])
        self.assertEqual(prepared['output_sha256'],backend.sha(staged))
        self.assertEqual(prepared['release_output_sha256'],backend.sha(expected))
        # Integrity enforcement still uses exact bytes after content verification.
        (self.stage/target).write_bytes(staged+b'tampered')
        with self.assertRaises(backend.InstallError):backend.apply(self.stage)
        self.assertEqual(source.read_bytes(),original)
        (self.stage/target).write_bytes(staged)
        backup=backend.apply(self.stage);self.assertEqual(source.read_bytes(),staged)
        backend.restore(backup);self.assertEqual(source.read_bytes(),original)

    def setUp(self):
        process_check=patch.object(backend,'check_game_closed',return_value=None);process_check.start();self.addCleanup(process_check.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.game=self.root/'Game';self.package=self.root/'package';self.stage=self.root/'stage'
        (self.game/'profiles/test').mkdir(parents=True);(self.game/'profiles/test/modlist.txt').write_text('+TestMod\n',encoding='utf-8')
        (self.package/'blobs').mkdir(parents=True)
        self.original=self.game/'mods/TestMod/original.txt';self.original.parent.mkdir(parents=True);self.original.write_bytes(b'original')
        self.new=self.game/'mods/TestMod/strings/new_en.strings'
        operations=[]
        for target,kind,old,new in [('mods/TestMod/original.txt','copy',b'original',b'patched'),('mods/TestMod/strings/new_en.strings','fallback_strings',None,b'new')]:
            blob=backend.sha(new);(self.package/'blobs'/blob).write_bytes(new)
            operations.append({'target':target,'kind':kind,'blob':blob,'input_sha256':backend.sha(old) if old else None,'output_sha256':blob})
        (self.package/'manifest.json').write_text(json.dumps({'default_profile':'test','operations':operations}),encoding='utf-8')
    def prepare(self):return backend.generate(self.game,self.package,self.stage)
    def test_apply_restore_and_repeat(self):
        self.prepare();backup=backend.apply(self.stage)
        self.assertEqual(self.original.read_bytes(),b'patched');self.assertEqual(self.new.read_bytes(),b'new')
        backend.restore(backup);self.assertEqual(self.original.read_bytes(),b'original');self.assertFalse(self.new.exists())
        backend.restore(backup);self.assertEqual(self.original.read_bytes(),b'original')
    def test_changed_after_prepare_stops_all_writes(self):
        self.prepare();self.original.write_bytes(b'user edit')
        with self.assertRaises(backend.InstallError):backend.apply(self.stage)
        self.assertFalse(self.new.exists());self.assertEqual(self.original.read_bytes(),b'user edit')
    def test_restore_refuses_to_erase_user_changes(self):
        self.prepare();backup=backend.apply(self.stage);self.original.write_bytes(b'user edit')
        with self.assertRaises(backend.InstallError):backend.restore(backup)
        self.assertTrue(self.new.exists())
    def test_partial_failure_rolls_back(self):
        self.prepare();real=backend.atomic;failed=False
        def fail_once(path,raw):
            nonlocal failed
            if Path(path).name=='new_en.strings' and not failed:failed=True;raise OSError('simulated failure')
            return real(path,raw)
        with patch.object(backend,'atomic',side_effect=fail_once):
            with self.assertRaises(OSError):backend.apply(self.stage)
        self.assertEqual(self.original.read_bytes(),b'original');self.assertFalse(self.new.exists())
    def test_escape_and_corrupt_payload_fail(self):
        with self.assertRaises(backend.InstallError):backend.safe(self.game,'../escape')
        with self.assertRaises(backend.InstallError):backend.generate(self.game,self.package,self.game)
        blob=next((self.package/'blobs').iterdir());blob.write_bytes(b'corrupt')
        with self.assertRaises(backend.InstallError):self.prepare()
        self.assertEqual(self.original.read_bytes(),b'original')
    def test_base_content_version_mismatch_stops_generation(self):
        steam=self.root/'Steam';(steam/'Data').mkdir(parents=True);(steam/'Data/Test.esm').write_bytes(b'new version')
        self.game.joinpath('ModOrganizer.ini').write_text('gamePath = @ByteArray('+str(steam).replace('\\','\\\\')+')\n',encoding='utf-8')
        p=self.package/'manifest.json';m=json.loads(p.read_text());m['base_content_checks']=[{'name':'Test.esm','required':True,'sha256':backend.sha(b'old version')}];p.write_text(json.dumps(m))
        report=self.prepare()
        self.assertTrue(report['base_content_drifted'])
        self.assertEqual([o['status'] for o in report['operations']],['unsupported_base_version','unsupported_base_version'])
        self.assertEqual(self.original.read_bytes(),b'original')
        with self.assertRaises(backend.InstallError):backend.apply(self.stage)

    def test_changed_base_version_allows_only_verified_text_and_freezes_current_base_hash(self):
        def table(text):
            raw=text.encode('utf8')+b'\0'
            return struct.pack('<IIII',1,len(raw),333,0)+raw
        english=table('Original English')
        path=self.game/'mods/TestMod/strings/Name_en.strings';path.parent.mkdir(parents=True);path.write_bytes(english)
        translated=table('원문 번역')
        recipe=gzip.compress(json.dumps({'kind':'.strings','translations':[[333,['Original English','원문 번역']]]},ensure_ascii=False).encode())
        digest=backend.sha(recipe);(self.package/'blobs'/digest).write_bytes(recipe)
        manifest=json.loads((self.package/'manifest.json').read_text(encoding='utf8'))
        manifest['operations'].append({'target':'mods/TestMod/strings/Name_en.strings','kind':'text_recipe',
                                       'blob':digest,'input_sha256':backend.sha(english),
                                       'output_sha256':backend.sha(translated)})
        steam=self.root/'Steam';(steam/'Data').mkdir(parents=True)
        base=steam/'Data'/'Test.esm';base.write_bytes(b'updated base content')
        (self.game/'ModOrganizer.ini').write_text('gamePath = @ByteArray('+str(steam).replace('\\','\\\\')+')\n',encoding='utf8')
        manifest['base_content_checks']=[{'name':'Test.esm','required':True,'sha256':backend.sha(b'old base content')}]
        (self.package/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
        prepared=self.prepare()
        self.assertEqual([o['status'] for o in prepared['operations']],
                         ['unsupported_base_version','unsupported_base_version','prepared'])
        base.write_bytes(b'changed AGAIN after preparation')
        with self.assertRaises(backend.InstallError):backend.apply(self.stage)
        base.write_bytes(b'updated base content')
        backup=backend.apply(self.stage)
        self.assertEqual(path.read_bytes(),translated)
        backend.restore(backup)
        self.assertEqual(path.read_bytes(),english)
    def test_copy_upgrade_accepts_only_known_previous_output(self):
        path=self.package/'manifest.json';manifest=json.loads(path.read_text())
        op=manifest['operations'][0]
        op['upgrade_from']=[{'input_sha256':backend.sha(b'previous translation'),'blob':op['blob']}]
        path.write_text(json.dumps(manifest))
        self.original.write_bytes(b'previous translation')
        self.prepare();backup=backend.apply(self.stage)
        self.assertEqual(self.original.read_bytes(),b'patched')
        backend.restore(backup);self.assertEqual(self.original.read_bytes(),b'previous translation')
        self.original.write_bytes(b'user translation')
        with self.assertRaises(backend.InstallError):self.prepare()
    def test_upgrade_existing_translation_and_restore(self):
        def strings(text):
            block=text.encode('utf-8')+b'\0'
            return struct.pack('<IIII',1,len(block),123,0)+block
        old=strings('기존 번역');new=strings('새 번역')
        path=self.game/'mods/TestMod/name_en.strings';path.write_bytes(old)
        raw=gzip.compress(json.dumps({'kind':'.strings','translations':[[123,['기존 번역','새 번역']]]},ensure_ascii=False).encode())
        blob=backend.sha(raw);(self.package/'blobs'/blob).write_bytes(raw)
        op={'target':'mods/TestMod/name_en.strings','kind':'text_recipe','input_sha256':backend.sha(strings('English')),'output_sha256':backend.sha(new),'blob':blob,'upgrade_from':[{'input_sha256':backend.sha(old),'blob':blob}]}
        (self.package/'manifest.json').write_text(json.dumps({'default_profile':'test','operations':[op]}))
        self.prepare();backup=backend.apply(self.stage);self.assertEqual(path.read_bytes(),new)
        backend.restore(backup);self.assertEqual(path.read_bytes(),old)
        path.write_bytes(strings('사용자 수정'))
        report=self.prepare()
        self.assertEqual(report['operations'][0]['status'],'no_matching_changes')
        self.assertEqual(path.read_bytes(),strings('사용자 수정'))

    def test_updated_plugin_reuses_matching_field_and_restores_updated_original(self):
        from test_patch_engine import record,field,group
        from plugin_anchors import build_anchor
        def plugin(first,second,extra=b''):
            return record(b'TES4',b'')+group(
                record(b'MISC',field(b'EDID',b'RecordOne\0')+field(b'FULL',first.encode()+b'\0'),1)+
                record(b'MISC',field(b'EDID',b'RecordTwo\0')+field(b'FULL',second.encode()+b'\0'),2)+extra)
        original=plugin('Hello','Old text')
        updated=plugin('Hello','Rewritten upstream',record(b'MISC',field(b'FULL',b'New object\0'),3))
        mapping={('MISC',1,'FULL',0):('Hello','안녕하세요'),
                 ('MISC',2,'FULL',0):('Old text','예전 글')}
        desired,_=backend.patch_plugin(original,mapping)
        target=self.game/'mods/TestMod/Example.esm';target.write_bytes(updated)
        recipe=gzip.compress(json.dumps({'kind':'plugin','translations':[[list(k),list(v)] for k,v in mapping.items()]},ensure_ascii=False).encode())
        blob=backend.sha(recipe);(self.package/'blobs'/blob).write_bytes(recipe)
        operation={'target':'mods/TestMod/Example.esm','kind':'text_recipe','blob':blob,
                   'input_sha256':backend.sha(original),'output_sha256':backend.sha(desired)}
        (self.package/'manifest.json').write_text(json.dumps({'default_profile':'test','target_version':'test','operations':[operation]}),encoding='utf-8')
        anchor={'schema':1,'target_version':'test','plugins':{
            operation['target']:dict(input_sha256=backend.sha(original),**build_anchor(original,mapping))}}
        (self.package/'compatibility-anchors.json').write_text(json.dumps(anchor),encoding='utf-8')
        report=self.prepare();prepared=report['operations'][0]
        self.assertEqual(prepared['status'],'prepared')
        self.assertEqual(prepared['compatibility'],'reused_unchanged_sources')
        self.assertEqual((prepared['matched_changes'],prepared['skipped_changed'],prepared['skipped_missing']),(1,1,0))
        self.assertNotEqual(prepared['output_sha256'],operation['output_sha256'])
        staged=(self.stage/'mods/TestMod/Example.esm').read_bytes()
        self.assertEqual(backend.sha(staged),prepared['output_sha256'])
        self.assertIn(b'Rewritten upstream\0',staged)
        self.assertIn(b'New object\0',staged)
        self.assertIn('안녕하세요\0'.encode(),staged)
        backup=backend.apply(self.stage)
        self.assertEqual(target.read_bytes(),staged)
        backend.restore(backup)
        self.assertEqual(target.read_bytes(),updated)

    def test_updated_strings_missing_and_changed_ids_do_not_block_matching_id(self):
        def strings(items):
            data=b'';index=b''
            for key,text in items:
                raw=text.encode('utf-8')+b'\0'
                index+=struct.pack('<II',key,len(data));data+=raw
            return struct.pack('<II',len(items),len(data))+index+data
        base=strings([(1,'English A'),(2,'English B')])
        updated=strings([(1,'English A'),(2,'Replaced B'),(3,'New')])
        desired=strings([(1,'한국어 A'),(2,'한국어 B')])
        target=self.game/'mods/TestMod/strings/Example_en.strings';target.parent.mkdir(parents=True);target.write_bytes(updated)
        recipe=gzip.compress(json.dumps({'kind':'.strings','translations':[[1,['English A','한국어 A']],[2,['English B','한국어 B']]]},ensure_ascii=False).encode())
        blob=backend.sha(recipe);(self.package/'blobs'/blob).write_bytes(recipe)
        operation={'target':'mods/TestMod/strings/Example_en.strings','kind':'text_recipe','blob':blob,
                   'input_sha256':backend.sha(base),'output_sha256':backend.sha(desired)}
        (self.package/'manifest.json').write_text(json.dumps({'default_profile':'test','operations':[operation]}),encoding='utf-8')
        report=self.prepare();item=report['operations'][0]
        self.assertEqual(item['matched_changes'],1)
        generated=(self.stage/'mods/TestMod/strings/Example_en.strings').read_bytes()
        self.assertEqual({id:text for id,text,_ in backend.patch_strings.__globals__['read_strings'](generated,'.strings')},
                         {1:'한국어 A',2:'Replaced B',3:'New'})
        self.assertEqual(item['output_sha256'],backend.sha(generated))

    def test_disabled_or_shadowed_mod_text_recipe_does_not_block_other_mods(self):
        def table(text):
            raw=text.encode()+b'\0'
            return struct.pack('<IIII',1,len(raw),12,0)+raw
        base=table('English');translated=table('한국어')
        blob_raw=gzip.compress(json.dumps({'kind':'.strings','translations':[[12,['English','한국어']]]},ensure_ascii=False).encode())
        blob=backend.sha(blob_raw);(self.package/'blobs'/blob).write_bytes(blob_raw)
        def operation(name):
            return {'target':f'mods/{name}/strings/Name_en.strings','kind':'text_recipe','blob':blob,
                    'input_sha256':backend.sha(base),'output_sha256':backend.sha(translated)}
        source=self.game/'mods/TestMod/strings/Name_en.strings';source.parent.mkdir(parents=True);source.write_bytes(base)
        shadow=self.game/'mods/OtherMod/strings/Name_en.strings';shadow.parent.mkdir(parents=True);shadow.write_bytes(base)
        manifest={'default_profile':'test','operations':[operation('AbsentMod'),operation('TestMod')]}
        (self.package/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
        report=self.prepare()
        self.assertEqual([r['status'] for r in report['operations']],['source_mod_not_enabled','prepared'])
        # Fresh preview for an enabled higher-priority mod that wins the same
        # relative file; the patcher must not edit the shadowed copy.
        (self.game/'profiles/test/modlist.txt').write_text('+OtherMod\n+TestMod\n',encoding='utf8')
        (self.stage/'prepared.json').unlink()
        self.stage.joinpath('mods/TestMod/strings/Name_en.strings').unlink()
        report=self.prepare()
        self.assertEqual([r['status'] for r in report['operations']],['source_mod_not_enabled','source_mod_not_winning'])
        self.assertEqual(source.read_bytes(),base)
if __name__=='__main__':unittest.main()
