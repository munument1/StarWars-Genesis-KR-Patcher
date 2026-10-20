import unittest

from patch_engine import PatchError
from plugin_anchors import build_anchor,remap_translations
from test_patch_engine import field,group,record


def fixture(masters,editor='SameEditor',text='Hello',master_slot=1):
    header=b''.join(field(b'MAST',s.encode()+b'\0') for s in masters)
    translated=record(b'TES4',header)+group(record(b'MISC',
        field(b'EDID',editor.encode()+b'\0')+field(b'FULL',text.encode()+b'\0'),
        (master_slot<<24)|123))
    return translated


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.mapping={('MISC',0x0100007B,'FULL',0):('Hello','안녕하세요')}
        self.original=fixture(['Starfield.esm','OldMaster.esm'])
        self.anchor=build_anchor(self.original,self.mapping)

    def test_master_reordering_resolves_same_owner_and_editor(self):
        moved=fixture(['Starfield.esm','Inserted.esm','OldMaster.esm'],master_slot=2)
        translated,aliases,skips=remap_translations(moved,self.mapping,self.anchor)
        self.assertFalse(skips)
        self.assertEqual(translated,{('MISC',0x0200007B,'FULL',0):('Hello','안녕하세요')})

    def test_recycled_form_id_must_not_receive_translation(self):
        moved=fixture(['Starfield.esm','OldMaster.esm'],editor='DifferentEditor')
        translated,aliases,skips=remap_translations(moved,self.mapping,self.anchor)
        self.assertFalse(translated)
        self.assertEqual(skips,[(('MISC',0x0100007B,'FULL',0),'identity_changed')])

    def test_missing_master_and_unsupported_formid_do_not_guess(self):
        changed=fixture(['Starfield.esm','Unrelated.esm'])
        mapped,aliases,skips=remap_translations(changed,self.mapping,self.anchor)
        self.assertEqual(mapped,{})
        self.assertEqual(skips,[(('MISC',0x0100007B,'FULL',0),'owner_missing')])

    def test_new_record_with_same_form_id_and_text_wrong_editor_is_skipped(self):
        data=fixture(['Starfield.esm','OldMaster.esm'],editor='ReusedEditor',text='Hello')
        mapped,_,skips=remap_translations(data,self.mapping,self.anchor)
        self.assertEqual(mapped,{})
        self.assertEqual(skips[0][1],'identity_changed')

    def test_duplicate_target_fails_closed(self):
        masters=['Starfield.esm','OldMaster.esm']
        header=record(b'TES4',b''.join(field(b'MAST',x.encode()+b'\0') for x in masters))
        extra=record(b'MISC',field(b'EDID',b'SameEditor\0')+field(b'FULL',b'Hello\0'),0x0100007B)
        duplicate=header+group(extra+extra)
        with self.assertRaises(PatchError):
            build_anchor(duplicate,self.mapping)


if __name__=='__main__':unittest.main()
