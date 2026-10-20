"""Bound version-drift translation targets to source plugin master/EditorID identity.

ESM records can encode master indices in their FormIDs. Inserting a new MAST
changes these indices even if the English string is unchanged. The signed-off
baseline file therefore supplies master names and record EditorIDs for safe
remapping; no runtime inference from translated text alone is permitted.
"""

import struct
import zlib
from collections import Counter
from patch_engine import PatchError,field_spans


def scan_identity(data,targets):
    """Return (masters, {record/formid: EDID or ''}) for explicit target forms."""
    if len(data)<24 or data[:4]!=b'TES4':raise PatchError('Missing TES4 header')
    size=struct.unpack_from('<I',data,4)[0]
    if size>len(data)-24:raise PatchError('Invalid TES4 header size')
    masters=[]
    for name,index,value,field in field_spans(data[24:24+size]):
        if name=='MAST':
            if not value.endswith(b'\0') or not value[:-1]:raise PatchError('Invalid MAST name')
            try: master=value[:-1].decode('utf-8').lower().replace('\\','/')
            except UnicodeDecodeError as e:raise PatchError('Invalid MAST encoding') from e
            master=master.rsplit('/',1)[-1]
            if master in masters:raise PatchError('Duplicate MAST')
            masters.append(master)
    wanted=set(targets)
    hits={}
    def walk(start,end,depth=0):
        if depth>48:raise PatchError('Excessive GRUP nesting')
        pos=start
        while pos<end:
            if pos+24>end:raise PatchError('Truncated record header')
            tag=data[pos:pos+4];size=struct.unpack_from('<I',data,pos+4)[0]
            if tag==b'GRUP':
                if size<24 or pos+size>end:raise PatchError('Invalid GRUP size')
                walk(pos+24,pos+size,depth+1);pos+=size;continue
            finish=pos+24+size
            if finish>end:raise PatchError('Record outside GRUP')
            key=(tag.decode('ascii'),struct.unpack_from('<I',data,pos+12)[0])
            if key in wanted:
                if key in hits:raise PatchError('Duplicate target record identity')
                flags=struct.unpack_from('<I',data,pos+8)[0]
                if flags&0x20:
                    hits[key]=None;pos=finish;continue
                body=data[pos+24:finish]
                if flags&0x40000:
                    if len(body)<4:raise PatchError('Truncated compressed record')
                    declared=struct.unpack_from('<I',body)[0]
                    if declared>128*1024*1024:raise PatchError('Unsafe compressed record size')
                    try:body=zlib.decompress(body[4:])
                    except zlib.error as e:raise PatchError('Invalid zlib record') from e
                    if len(body)!=declared:raise PatchError('Record decompression mismatch')
                edids=[v[:-1].decode('utf-8','replace') for n,i,v,span in field_spans(body)
                       if n=='EDID' and v.endswith(b'\0')]
                if len(edids)>1:raise PatchError('Ambiguous record EDID')
                hits[key]=edids[0] if edids else ''
            pos=finish
        if pos!=end:raise PatchError('Misaligned group')
    walk(24+size,len(data))
    return masters,hits


def build_anchor(data,mapping):
    """Create immutable identity markers for a hash-verified release ESM."""
    targets={(key[0],key[1]) for key in mapping}
    masters,hits=scan_identity(data,targets)
    if set(hits)!=targets or any(x is None for x in hits.values()):
        raise PatchError('Release identity is missing a translation target')
    return {'masters':masters,
            'edids':{f'{record}:{formid:08X}':edid for (record,formid),edid in sorted(hits.items())}}


def remap_translations(data,mapping,anchor,aliases=None):
    """Rebind only targets with safely resolved master owner and EditorID.

    Returns (mapping, aliases, skipped). Other targets are not even exposed to
    the patch engine, preventing incorrect FormID reuse after master shifts.
    """
    old_masters=anchor['masters']
    current_masters,_=scan_identity(data,())
    shifted={}
    skipped=[]
    for key,spec in mapping.items():
        record,fid,field,index=key
        old_slot=fid>>24
        if old_slot<len(old_masters):
            owner=old_masters[old_slot]
            if owner not in current_masters:
                skipped.append((key,'owner_missing'));continue
            slot=current_masters.index(owner)
        elif old_slot==len(old_masters):slot=len(current_masters)
        else:
            skipped.append((key,'unsupported_formid'));continue
        if slot>=0xFD:
            skipped.append((key,'unsupported_formid'));continue
        newkey=(record,(slot<<24)|(fid&0xFFFFFF),field,index)
        if newkey in shifted:
            raise PatchError('Ambiguous remapped translation keys')
        shifted[newkey]=(key,spec)
    wanted={(k[0],k[1]) for k in shifted}
    _,current_edids=scan_identity(data,wanted)
    selected={};translated_aliases={}
    for key,(oldkey,spec) in shifted.items():
        base_edid=anchor['edids'].get(f'{oldkey[0]}:{oldkey[1]:08X}')
        current_edid=current_edids.get((key[0],key[1]))
        if (base_edid is None or current_edid is None or
            (base_edid and base_edid!=current_edid) or
            (not base_edid and old_masters!=current_masters)):
            skipped.append((oldkey,'identity_changed'));continue
        selected[key]=spec
        if aliases and oldkey in aliases:translated_aliases[key]=aliases[oldkey]
    return selected,translated_aliases,skipped
