import tempfile
import unittest
from pathlib import Path

from wielder.wield.wield_conf import resolve_ecosystem_manifest_path


class TestResolveEcosystemManifestPath(unittest.TestCase):
    def test_resolves_flat_ecosystem_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecosystem_root = Path(tmpdir) / "ecosystem"
            manifest_path = ecosystem_root / "kind_gpu_model_binding" / "ecosystem_manifest.conf"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('surface = "kind"\n')

            resolved_path = resolve_ecosystem_manifest_path(
                ecosystem_root,
                "kind_gpu_model_binding",
                required=True,
            )

            self.assertEqual(resolved_path, manifest_path)

    def test_resolves_namespaced_ecosystem_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecosystem_root = Path(tmpdir) / "ecosystem"
            manifest_path = (
                ecosystem_root
                / "model_binding"
                / "aws_model_binding"
                / "ecosystem_manifest.conf"
            )
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('surface = "aws"\n')

            resolved_path = resolve_ecosystem_manifest_path(
                ecosystem_root,
                "aws_model_binding",
                required=True,
            )

            self.assertEqual(resolved_path, manifest_path)

    def test_fails_closed_on_ambiguous_ecosystem_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ecosystem_root = Path(tmpdir) / "ecosystem"
            flat_manifest_path = ecosystem_root / "kind_gpu_model_binding" / "ecosystem_manifest.conf"
            namespaced_manifest_path = (
                ecosystem_root
                / "model_binding"
                / "kind_gpu_model_binding"
                / "ecosystem_manifest.conf"
            )
            flat_manifest_path.parent.mkdir(parents=True)
            namespaced_manifest_path.parent.mkdir(parents=True)
            flat_manifest_path.write_text('surface = "kind"\n')
            namespaced_manifest_path.write_text('surface = "kind"\n')

            with self.assertRaises(RuntimeError):
                resolve_ecosystem_manifest_path(
                    ecosystem_root,
                    "kind_gpu_model_binding",
                    required=True,
                )


if __name__ == "__main__":
    unittest.main()
