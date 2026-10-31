"""Portable, offline checks for packaged recipes and source guards."""
import hashlib
import gzip
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ReleasePayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = ROOT / "installer-data"
        cls.manifest = json.loads((cls.package / "manifest.json").read_text(encoding="utf-8"))

    def test_all_blobs_are_content_addressed(self):
        for op in self.manifest["operations"]:
            specs = [(op["blob"], op["target"])] if "blob" in op else []
            specs.extend((item["blob"], op["target"]) for item in op.get("upgrade_from", []))
            for digest, name in specs:
                with self.subTest(target=name, digest=digest):
                    self.assertEqual(len(digest), 64)
                    raw = (self.package / "blobs" / digest).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)

    def test_anchor_hash_and_version_match(self):
        manifest = self.manifest
        expected = manifest.get("compatibility_anchor_sha256")
        if not expected:
            return
        source = (self.package / "compatibility-anchors.json").read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), expected)
        anchor = json.loads(source)
        self.assertEqual(anchor["target_version"], manifest["target_version"])

    def test_unique_safe_targets(self):
        targets = [entry["target"] for entry in self.manifest["operations"]]
        self.assertEqual(len(targets), len(set(target.casefold() for target in targets)))
        for target in targets:
            with self.subTest(target=target):
                self.assertNotIn("\\", target)
                self.assertNotIn("..", Path(target).parts)
                self.assertFalse(Path(target).is_absolute())
                self.assertTrue(target.startswith("mods/") or target == "GENESIS_DOCUMENTS.bat")

    def test_hud_v2_has_embedded_font_blob_dependency(self):
        for op in self.manifest["operations"]:
            if op["kind"] != "hud_recipe_v2":
                continue
            with self.subTest(target=op["target"]):
                source = (self.package / "blobs" / op["blob"]).read_bytes()
                recipe = json.loads(gzip.decompress(source))
                self.assertEqual(recipe["schema"], 2)
                self.assertEqual(recipe["target_version"], self.manifest["target_version"])
                self.assertEqual(recipe["input_sha256"], op["input_sha256"])
                self.assertEqual(recipe["output_sha256"], op["output_sha256"])
                glyph = recipe["font_addition"]["glyph_source"]["blob_sha256"]
                blob = (self.package / "blobs" / glyph).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), glyph)


if __name__ == "__main__":
    unittest.main()
