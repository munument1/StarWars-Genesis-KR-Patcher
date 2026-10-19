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
                json.dumps({'target_version': '8.8.32', 'version': '0.2.4'}), encoding='utf-8'
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
        manifest = {'target_version': '8.8.4', 'version': '0.2.4'}
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with patch.object(patcher_app, 'package_dir', return_value=package):
                self.assertEqual(patcher_app.check_release_metadata(), manifest)


if __name__ == '__main__':
    unittest.main()
