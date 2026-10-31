"""Strictly apply a 4-tag Genesis 8.8.4.1 HUD recipe.

Separate candidate module. Production integration must copy this module into
the tracked repository only after review. The existing v1 HUD handler is kept.
"""

import base64
import gzip
import hashlib
import json
import re
import struct
from collections import Counter

from preserve_font_resources import add_glyphs, decode_font, korean, tags_bytes


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def exact_hex(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "Invalid SHA256 syntax")
    return value


def _blob(reader, sha):
    exact_hex(sha)
    content = reader(sha)
    require(isinstance(content, bytes) and digest(content) == sha,
            "External glyph blob SHA mismatch")
    require(len(content) < 20_000_000, "Font recipe blob too large")
    contents = gzip.decompress(content)
    require(len(contents) < 35_000_000, "Uncompressed font recipe too large")
    return json.loads(contents)


def apply_hud_recipe_v2(raw, recipe, load_blob):
    """Apply 3 ordinary tag replacements + 1 semantic embedded font merge."""
    require(recipe.get("schema") == 2 and recipe.get("kind") == "hud_recipe_v2",
            "Unsupported HUD recipe schema")
    require(recipe.get("target_version") == "8.8.41", "Unsupported HUD target version")
    require(raw[:4] == bytes.fromhex(recipe["source_magic_hex"]) == b"GFX\x0c",
            "Expected Genesis HUD uncompressed GFX v12")
    require(digest(raw) == exact_hex(recipe["input_sha256"]), "HUD source hash changed")
    require(struct.unpack_from("<I", raw, 4)[0] == len(raw), "Malformed GFX byte length")

    originals = tags_bytes(raw)
    require(len(originals) == recipe["source_tag_count"], "HUD tag count changed")
    require(originals[-1] == (0, b""), "Missing SWF End tag")
    require(not any(t in (11, 33) for t, _ in originals),
            "Static text references require manual font remapping")

    target = recipe["font_addition"]
    require(target["tag"] == 75 and target["id"] == 2400,
            "Unsupported font insertion target")
    glyph_ref = target["glyph_source"]
    require(glyph_ref["font_id"] == 1 and glyph_ref["expected_added_glyphs"] == 11225,
            "Unexpected font source specification")
    definitions = _blob(load_blob, glyph_ref["blob_sha256"])
    require(str(glyph_ref["font_id"]) in definitions, "Missing referenced font glyph map")
    encoded = definitions[str(glyph_ref["font_id"])]
    require(len(encoded) == glyph_ref["expected_added_glyphs"],
            "Font repertoire size changed")
    additions = {}
    for raw_code, fields in encoded.items():
        code = int(raw_code)
        require(korean(code) and code not in additions, "Invalid Korean codepoint")
        require(set(fields) == {"shape", "advance", "bounds"},
                "Incomplete font glyph record")
        addition = {k: base64.b64decode(v, validate=True) for k, v in fields.items()}
        require(len(addition["advance"]) == 2 and addition["bounds"] and addition["shape"],
                "Malformed Korean glyph")
        additions[code] = addition

    changes = {}
    for r in recipe["replacements"]:
        key = (r["tag"], r["id"])
        require(key[0] in (37, 39) and key not in changes, "Invalid or duplicate HUD edit")
        body = base64.b64decode(r["body"], validate=True)
        require(len(body) >= 2 and struct.unpack_from("<H", body)[0] == key[1],
                "Replacement definition ID changed")
        require(digest(body) == exact_hex(r["output_sha256"]),
                "Replacement payload checksum changed")
        changes[key] = (exact_hex(r["input_sha256"]), body)
    require(set(changes) == {(37, 1227), (39, 1229), (39, 1230)},
            "Expected three known HUD layout changes")
    font_key = (75, target["id"])
    require(font_key not in changes, "Embedded font selected twice")
    source_font_sha = exact_hex(target["input_sha256"])
    expected_font_sha = exact_hex(target["output_sha256"])

    seen = set()
    result_tags = []
    for tag, body in originals:
        key = (tag, struct.unpack_from("<H", body)[0]) if tag in (37, 39, 75) and len(body) >= 2 else None
        if key in changes:
            require(key not in seen, "Duplicate HUD tag ID")
            expected, replacement = changes[key]
            require(digest(body) == expected, f"HUD tag changed: {key}")
            seen.add(key)
            body = replacement
        elif key == font_key:
            require(key not in seen, "Duplicate embedded font ID")
            require(digest(body) == source_font_sha, "Embedded font source changed")
            old = decode_font(body)
            require(body[5:5 + body[4]].decode("utf8") == target["source_font_name"],
                    "Unexpected embedded font name")
            require(len(old["glyphs"]) == target["source_glyphs"], "Native glyph count changed")
            require(old["flags"] == 0x84, "Embedded font flag structure changed")
            require(not set(old["glyphs"]) & set(additions), "Korean source glyph collision")
            require(not any(t == 73 and b[:2] == body[:2] for t, b in originals),
                    "Font alignment table would require rebuilding")
            patched_font = add_glyphs(body, additions)
            require(digest(patched_font) == expected_font_sha,
                    "Merged font tag hash differs")
            new = decode_font(patched_font)
            require(len(new["glyphs"]) == target["output_glyphs"],
                    "Merged font glyph count changed")
            require(new["metrics"] == old["metrics"] and new["kerning"] == old["kerning"],
                    "Native font metrics changed")
            require(all(new["glyphs"].get(c) == spec for c, spec in old["glyphs"].items()),
                    "Original embedded glyph was modified")
            seen.add(key)
            body = patched_font
        result_tags.append((tag, body))
    require(seen == set(changes) | {font_key},
            "Required HUD tag missing")

    bits = raw[8] >> 3
    start = 8 + (5 + 4 * bits + 7) // 8 + 4
    out = bytearray(raw[8:start])
    for tag, body in result_tags:
        n = len(body)
        require(0 <= tag <= 1023 and n <= 0xFFFFFFFF, "Invalid SWF tag")
        if n < 63:
            out.extend(struct.pack("<H", (tag << 6) | n))
        else:
            out.extend(struct.pack("<HI", (tag << 6) | 63, n))
        out.extend(body)
    candidate = raw[:4] + struct.pack("<I", 8 + len(out)) + bytes(out)
    require(digest(candidate) == exact_hex(recipe["output_sha256"]),
            "Final GFX output hash differs")
    rebuilt = tags_bytes(candidate)
    require([t for t, _ in rebuilt] == [t for t, _ in originals],
            "SWF tag order changed")
    require(Counter(t for t, _ in rebuilt) == Counter(t for t, _ in originals),
            "SWF tag type counts changed")
    return candidate
