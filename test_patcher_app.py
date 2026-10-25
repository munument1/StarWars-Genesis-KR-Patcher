import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import patcher_app


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_metadata_rejects_previous_genesis_version(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'manifest.json').write_text(
                json.dumps({'target_version': '8.8.32', 'version': '0.2.6'}), encoding='utf-8'
            )
            with patch.object(patcher_app, 'package_dir', return_value=package):
                with self.assertRaisesRegex(ValueError, 'Package version'):
                    patcher_app.check_release_metadata()

    def test_release_metadata_rejects_stale_patcher_version(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'manifest.json').write_text(
                json.dumps({'target_version': '8.8.4', 'version': '0.1.0'}), encoding='utf-8'
            )
            with patch.object(patcher_app, 'package_dir', return_value=package):
                with self.assertRaisesRegex(ValueError, 'Package version'):
                    patcher_app.check_release_metadata()

    def test_release_metadata_accepts_supported_versions(self):
        manifest = {'target_version': '8.8.4', 'version': '0.2.6'}
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with patch.object(patcher_app, 'package_dir', return_value=package):
                self.assertEqual(patcher_app.check_release_metadata(), manifest)

    def test_release_metadata_requires_intact_anchor_file(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)
            payload=b'{"schema":1}'
            manifest={'target_version':'8.8.4','version':'0.2.6',
                      'compatibility_anchor_sha256':hashlib.sha256(payload).hexdigest()}
            (package/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with patch.object(patcher_app,'package_dir',return_value=package):
                with self.assertRaisesRegex(ValueError,'identity metadata'):
                    patcher_app.check_release_metadata()
                (package/'compatibility-anchors.json').write_bytes(b'corrupted')
                with self.assertRaisesRegex(ValueError,'identity metadata'):
                    patcher_app.check_release_metadata()
                (package/'compatibility-anchors.json').write_bytes(payload)
                self.assertEqual(patcher_app.check_release_metadata(),manifest)


if __name__ == '__main__':
    unittest.main()
