from wielder.util.imager import _build_current_image_version


def test_reuse_existing_version_skips_current_version_build():
    assert not _build_current_image_version(
        force=False,
        reuse_existing_version=True,
    )


def test_reuse_existing_version_false_builds_current_version():
    assert _build_current_image_version(
        force=False,
        reuse_existing_version=False,
    )


def test_legacy_force_remains_compatibility_shim():
    assert _build_current_image_version(
        force=True,
        reuse_existing_version=None,
    )
