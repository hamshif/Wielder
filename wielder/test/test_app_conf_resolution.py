import tempfile
import unittest
from pathlib import Path

from wielder.wield.wield_conf import resolve_app_conf_path


class TestResolveAppConfPath(unittest.TestCase):
    def test_resolves_flat_app_conf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            apps_root = Path(tmpdir) / "apps"
            app_conf_path = apps_root / "cool" / "app.conf"
            app_conf_path.parent.mkdir(parents=True)
            app_conf_path.write_text('super_hero = "pinky"\n')

            resolved_path = resolve_app_conf_path(apps_root, "cool", required=True)

            self.assertEqual(resolved_path, app_conf_path)

    def test_resolves_nested_app_conf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            apps_root = Path(tmpdir) / "apps"
            app_conf_path = apps_root / "ingestion" / "provider" / "assay" / "app.conf"
            app_conf_path.parent.mkdir(parents=True)
            app_conf_path.write_text('ingestion.provider.assay.filename_token = "-ASSAY_TOKEN_"\n')

            resolved_path = resolve_app_conf_path(apps_root, "ingestion/provider/assay", required=True)

            self.assertEqual(resolved_path, app_conf_path)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            apps_root = Path(tmpdir) / "apps"

            with self.assertRaises(ValueError):
                resolve_app_conf_path(apps_root, "../assay", required=True)

    def test_rejects_windows_separators(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            apps_root = Path(tmpdir) / "apps"

            with self.assertRaises(ValueError):
                resolve_app_conf_path(apps_root, r"ingestion\provider\assay", required=True)


if __name__ == "__main__":
    unittest.main()
