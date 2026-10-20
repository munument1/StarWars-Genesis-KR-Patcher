import struct,unittest,zlib
from patch_engine import PatchError,patch_plugin,patch_strings,read_strings

def record(name,body,fid=0,flags=0):
    if flags&0x40000:body=struct.pack('<I',len(body))+zlib.compress(body)
    return name+struct.pack('<III',len(body),flags,fid)+b'\x12\x34\x56\x78\x90\0\0\0'+body
def field(name,value):return name+struct.pack('<H',len(value))+value
def group(body):return b'GRUP'+struct.pack('<I',24+len(body))+b'\x01\x02\x03\x04'+b'\x05'*12+body
def strings(kind):
    text=b'Hello <Alias=Player>\0';block=text if kind=='.strings' else struct.pack('<I',len(text))+text
    return struct.pack('<II',1,len(block))+struct.pack('<II',42,0)+block

class EngineTests(unittest.TestCase):
    def test_compression_nested_group_extended_and_unknown_fields(self):
        body=field(b'EDID',b'test\0')+field(b'ZZZZ',bytes(range(255)))+field(b'FULL',b'Hello\0')
        source=record(b'TES4',field(b'HEDR',b'123456789012'))+group(group(record(b'MISC',body,0x123,0x40000)))
        key=('MISC',0x123,'FULL',0);translation='한'*24000
        result,changed=patch_plugin(source,{key:('Hello',translation)})
        self.assertEqual(changed,[key]);self.assertEqual(result[:42],source[:42])
        # Independent header/decompression checks, not the engine field parser.
        offset=42+48;length,flags,fid=struct.unpack_from('<III',result,offset+4)
        self.assertEqual(flags,0x40000);self.assertEqual(fid,0x123)
        payload=result[offset+24:offset+24+length];plain=zlib.decompress(payload[4:])
        self.assertEqual(len(plain),struct.unpack_from('<I',payload)[0])
        self.assertIn(field(b'ZZZZ',bytes(range(255))),plain)
        self.assertIn(b'XXXX\x04\0'+struct.pack('<I',len(translation.encode())+1)+b'FULL\0\0',plain)
        self.assertEqual(struct.unpack_from('<I',result,46)[0],len(result)-42)

    def test_unchanged_is_byte_exact(self):
        original=record(b'TES4',b'')+record(b'MISC',field(b'FULL',b'Hi\0'),1,0x40000)
        result,_=patch_plugin(original,{('MISC',1,'FULL',0):('Hi','Hi')})
        self.assertEqual(original,result)

    def test_source_mismatch_and_missing_target_fail(self):
        original=record(b'TES4',b'')+record(b'MISC',field(b'FULL',b'Hi\0'),1)
        for mapping in [{('MISC',1,'FULL',0):('Wrong','안녕')},{('MISC',2,'FULL',0):('Hi','안녕')}]:
            with self.assertRaises(PatchError):patch_plugin(original,mapping)

    def test_compatible_plugin_reuses_matching_fields_and_preserves_updated_ones(self):
        original=record(b'TES4',b'')+group(
            record(b'MISC',field(b'FULL',b'Hello\0'),1,0x40000)+
            record(b'MISC',field(b'FULL',b'Changed upstream\0'),2))
        translation={('MISC',1,'FULL',0):('Hello','안녕하세요'),
                     ('MISC',2,'FULL',0):('Original','예전 번역'),
                     ('MISC',3,'FULL',0):('Deleted','제거됨')}
        result,changed,skipped=patch_plugin(original,translation,compatible=True)
        self.assertEqual(changed,[('MISC',1,'FULL',0)])
        self.assertEqual(set(skipped),{(('MISC',2,'FULL',0),'source_changed'),
                                       (('MISC',3,'FULL',0),'target_missing')})
        self.assertIn(field(b'FULL','안녕하세요\0'.encode('utf8')),zlib.decompress(result[24+24+24+4:]))
        self.assertIn(field(b'FULL',b'Changed upstream\0'),result)
        again,changes,_=patch_plugin(result,translation,compatible=True)
        self.assertEqual(again,result)
        self.assertEqual(changes,[])

    def test_compatible_still_rejects_corrupt_structure_or_bad_tokens(self):
        bad=record(b'TES4',b'')+record(b'MISC',field(b'FULL',b'Hello <Alias=Player>\0'),1)
        with self.assertRaises(PatchError):
            patch_plugin(bad,{('MISC',1,'FULL',0):('Hello <Alias=Player>','안녕하세요')},compatible=True)
        with self.assertRaises(PatchError):
            patch_plugin(bad[:-2],{('MISC',1,'FULL',0):('Hello','안녕')},compatible=True)

    def test_compatible_plugin_can_upgrade_known_previous_korean_translation(self):
        key=('MISC',1,'FULL',0)
        updated=record(b'TES4',b'')+record(b'MISC',field(b'FULL','옛 한국어\0'.encode()),1)
        new,changes,skips=patch_plugin(updated,{key:('English','새 한국어')},compatible=True,
                                         aliases={key:[('옛 한국어','새 한국어')]})
        self.assertEqual(changes,[key]);self.assertEqual(skips,[])
        self.assertIn('새 한국어\0'.encode(),new)

    def test_compatible_strings_upgrade_known_previous_korean(self):
        previous='옛 한국어\0'.encode();raw=struct.pack('<IIII',1,len(previous),123,0)+previous
        new,changes,skips=patch_strings(raw,'.strings',{123:('English','새 한국어')},compatible=True,
                                        aliases={123:[('옛 한국어','새 한국어')]})
        self.assertEqual(changes,[123]);self.assertEqual(skips,[])
        self.assertEqual(read_strings(new,'.strings')[0][1],'새 한국어')

    def test_malformed_source_repair_requires_exact_raw_bytes(self):
        raw=bytes.fromhex('4e75747269656e74858f')
        original=record(b'TES4',b'')+record(b'MISC',field(b'FULL',raw+b'\0'),1)
        key=('MISC',1,'FULL',0)
        with self.assertRaises(UnicodeDecodeError):patch_plugin(original,{key:('Nutrient…�','영양소')})
        with self.assertRaises(PatchError):patch_plugin(original,{key:('Nutrient…�','영양소','4e75747269656e74')})
        generated,changed=patch_plugin(original,{key:('Nutrient…�','영양소',raw.hex())})
        self.assertEqual(changed,[key]);self.assertIn(field(b'FULL','영양소\0'.encode()),generated)
        unchanged,_=patch_plugin(generated,{key:('영양소','영양소')})
        self.assertEqual(unchanged,generated)

    def test_strings_all_formats_and_ids(self):
        for kind in ['.strings','.dlstrings','.ilstrings']:
            original=strings(kind);result,changed=patch_strings(original,kind,{42:('Hello <Alias=Player>','안녕 <Alias=Player>')})
            self.assertEqual(changed,[42]);self.assertEqual(read_strings(result,kind)[0][:2],(42,'안녕 <Alias=Player>'))
            self.assertEqual(struct.unpack_from('<II',result,8),(42,0))
            self.assertEqual(struct.unpack_from('<I',result,4)[0],len(result)-16)

    def test_compatible_strings_only_changes_matching_ids(self):
        for kind in ('.strings','.dlstrings','.ilstrings'):
            entries=[(42,'Hello'),(43,'Changed upstream'),(99,'new entry')]
            blocks=[];directory=[];offset=0
            for sid,value in entries:
                encoded=value.encode()+b'\0'
                block=encoded if kind=='.strings' else struct.pack('<I',len(encoded))+encoded
                directory.append(struct.pack('<II',sid,offset));blocks.append(block);offset+=len(block)
            source=struct.pack('<II',len(entries),offset)+b''.join(directory)+b''.join(blocks)
            current,changes,skips=patch_strings(source,kind,{42:('Hello','안녕'),43:('Old','옛것'),55:('Missing','없음')},compatible=True)
            self.assertEqual(changes,[42]);self.assertEqual(set(skips),{(43,'source_changed'),(55,'target_missing')})
            values={sid:value for sid,value,_ in read_strings(current,kind)}
            self.assertEqual(values,{42:'안녕',43:'Changed upstream',99:'new entry'})

    def test_placeholders_and_localized_plugins_fail_closed(self):
        with self.assertRaises(PatchError):patch_strings(strings('.strings'),'.strings',{42:('Hello <Alias=Player>','안녕')})
        with self.assertRaises(PatchError):patch_plugin(record(b'TES4',b'',flags=0x80),{('MISC',1,'FULL',0):('Hi','안녕')})

    def test_controls_preserved_without_blocking_localized_dialogue_prefixes(self):
        from patch_engine import check_translation
        with self.assertRaises(PatchError):check_translation('Press [Cancel:14].','[취소]를 누르세요.')
        check_translation('Press [Cancel:14].','[Cancel:14]를 누르세요.')
        check_translation('[Cloak] Black Cloak','[망토] 검은색 망토')

    def test_book_caption_can_translate_but_image_asset_cannot_change(self):
        from patch_engine import check_translation
        original="<image name='BookImage_SlaytonLogo' caption='Slayton Aerospace'>"
        check_translation(original,"<image name='BookImage_SlaytonLogo' caption='슬레이튼 에어로스페이스'>")
        with self.assertRaises(PatchError):check_translation(original,"<image name='different_asset' caption='슬레이튼 에어로스페이스'>")

    def test_printf_format_specifiers_are_protected(self):
        # Real Genesis strings have %.0f, and older regexes missed it.
        from patch_engine import check_translation,translation_tokens
        original='Progress: %.0f of %1$05d %u %% <Alias=Player>'
        self.assertEqual(translation_tokens(original),{
            '%.0f':1,'%1$05d':1,'%u':1,'%%':1,'<Alias=Player>':1})
        check_translation(original,'진행: %.0f / %1$05d %u %% <Alias=Player>')
        with self.assertRaises(PatchError):check_translation(original,'진행: %1$05d %u %% <Alias=Player>')
        with self.assertRaises(PatchError):check_translation('Remaining %s','남은 수량 %d')

if __name__=='__main__':unittest.main()
