import subprocess
from pathlib import Path

from wielder.util.wgit import WGit, clone_or_update


def _run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def test_clone_or_update_warns_and_skips_dirty_destination(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    _run(["git", "init"], source)
    _run(["git", "config", "user.name", "Codex"], source)
    _run(["git", "config", "user.email", "codex@example.com"], source)

    (source / "README.md").write_text("initial\n")
    _run(["git", "add", "README.md"], source)
    _run(["git", "commit", "-m", "initial"], source)
    old_commit = _run(["git", "rev-parse", "HEAD"], source)

    destination_root = tmp_path / "stage"
    destination_root.mkdir()
    destination = destination_root / "source"

    clone_or_update(source.as_posix(), destination.as_posix(), name="source", commit_sha=old_commit, local=True)

    untracked_conf = destination / "conf" / "test_model.conf"
    untracked_conf.parent.mkdir(parents=True, exist_ok=True)
    untracked_conf.write_text("stale local file\n")

    tracked_conf = source / "conf" / "test_model.conf"
    tracked_conf.parent.mkdir(parents=True, exist_ok=True)
    tracked_conf.write_text("tracked file in new commit\n")
    _run(["git", "add", "conf/test_model.conf"], source)
    _run(["git", "commit", "-m", "track test_model"], source)
    new_commit = _run(["git", "rev-parse", "HEAD"], source)

    clone_or_update(source.as_posix(), destination.as_posix(), name="source", commit_sha=new_commit, local=True)

    staged_head = _run(["git", "rev-parse", "HEAD"], destination)
    assert staged_head == old_commit


def test_clone_or_update_tolerates_clean_destination_without_stash(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    _run(["git", "init"], source)
    _run(["git", "config", "user.name", "Codex"], source)
    _run(["git", "config", "user.email", "codex@example.com"], source)

    (source / "README.md").write_text("initial\n")
    _run(["git", "add", "README.md"], source)
    _run(["git", "commit", "-m", "initial"], source)
    commit_sha = _run(["git", "rev-parse", "HEAD"], source)

    destination_root = tmp_path / "stage"
    destination_root.mkdir()
    destination = destination_root / "source"

    clone_or_update(source.as_posix(), destination.as_posix(), name="source", commit_sha=commit_sha, local=True)
    clone_or_update(source.as_posix(), destination.as_posix(), name="source", commit_sha=commit_sha, local=True)

    staged_head = _run(["git", "rev-parse", "HEAD"], destination)
    assert staged_head == commit_sha


def test_clone_or_update_replaces_stale_non_git_local_destination(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    _run(["git", "init"], source)
    _run(["git", "config", "user.name", "Codex"], source)
    _run(["git", "config", "user.email", "codex@example.com"], source)

    (source / "README.md").write_text("initial\n")
    _run(["git", "add", "README.md"], source)
    _run(["git", "commit", "-m", "initial"], source)
    commit_sha = _run(["git", "rev-parse", "HEAD"], source)

    destination_root = tmp_path / "stage"
    destination_root.mkdir()
    destination = destination_root / "source"
    destination.mkdir()
    (destination / "stale.txt").write_text("stale non-git staging payload\n")

    clone_or_update(source.as_posix(), destination.as_posix(), name="source", commit_sha=commit_sha, local=True)

    staged_head = _run(["git", "rev-parse", "HEAD"], destination)
    assert staged_head == commit_sha
    assert not (destination / "stale.txt").exists()
    assert (destination / "README.md").read_text() == "initial\n"


def test_wgit_reports_submodule_paths_and_tracked_root_items(tmp_path):
    source = tmp_path / "source"
    source.mkdir()

    _run(["git", "init"], source)
    _run(["git", "config", "user.name", "Codex"], source)
    _run(["git", "config", "user.email", "codex@example.com"], source)

    (source / "README.md").write_text("initial\n")
    (source / ".gitmodules").write_text(
        '[submodule "Wielder"]\n'
        "\tpath = Wielder\n"
        "\turl = git@example.com:Wielder.git\n"
        '[submodule "domain-app"]\n'
        "\tpath = domain-app\n"
        "\turl = git@example.com:domain-app.git\n"
    )
    _run(["git", "add", "README.md", ".gitmodules"], source)
    _run(["git", "commit", "-m", "initial"], source)

    wgit = WGit(source.as_posix())

    assert wgit.get_submodule_paths() == ["Wielder", "domain-app"]
    assert set(wgit.get_tracked_root_items()) == {"README.md", ".gitmodules"}
