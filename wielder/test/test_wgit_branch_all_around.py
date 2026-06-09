import pytest
from pyhocon import ConfigFactory

from wielder.util import wgit


def test_branch_all_around_rejects_staged_files(monkeypatch):
    repo_specs = [
        {"name": ".", "repo_path": "/repo"},
        {"name": "workflow-wielder", "repo_path": "/repo/workflow-wielder"},
    ]

    def fake_status(repo_path):
        if repo_path == "/repo/workflow-wielder":
            return ["A  staged.py\n"]
        return []

    monkeypatch.setattr(wgit, "_git_status_lines", fake_status)

    with pytest.raises(RuntimeError, match="Staged changes were detected"):
        wgit._assert_branch_all_around_clean(repo_specs)


def test_branch_all_around_rejects_unpushed_current_branch(monkeypatch):
    repo_specs = [{"name": ".", "repo_path": "/repo"}]

    monkeypatch.setattr(wgit, "_current_branch", lambda repo_path: "feature/work")
    monkeypatch.setattr(wgit, "_remote_branch_exists", lambda repo_path, branch: True)
    monkeypatch.setattr(wgit, "_get_branch_divergence_counts", lambda repo_path, branch: (0, 1))

    with pytest.raises(RuntimeError, match="currently checked-out branches are not fully pushed"):
        wgit._assert_current_branches_are_pushed(repo_specs)


def test_branch_all_around_rejects_branch_parity_mismatch(monkeypatch):
    repo_specs = [
        {"name": ".", "repo_path": "/repo"},
        {"name": "workflow-wielder", "repo_path": "/repo/workflow-wielder"},
    ]

    def fake_current_branch(repo_path):
        if repo_path == "/repo/workflow-wielder":
            return "feature/model/secure_site"
        return "feature/model/main"

    monkeypatch.setattr(wgit, "_current_branch", fake_current_branch)

    with pytest.raises(RuntimeError, match="checked-out branch is not coordinated"):
        wgit._assert_current_branch_parity(repo_specs, "feature/model/main")


def test_branch_all_around_creates_and_pushes_branches_after_preflight(monkeypatch):
    repo_specs = [
        {"name": ".", "repo_path": "/repo"},
        {"name": "workflow-wielder", "repo_path": "/repo/workflow-wielder"},
    ]
    commands = []

    monkeypatch.setattr(wgit, "_repo_specs_for_super_repo", lambda repo_path: repo_specs)
    monkeypatch.setattr(wgit, "_assert_branch_all_around_clean", lambda repo_specs: None)
    monkeypatch.setattr(wgit, "_fetch_branch_all_around_repos", lambda repo_specs: None)
    monkeypatch.setattr(wgit, "_assert_current_branch_parity", lambda repo_specs, source_branch: None)
    monkeypatch.setattr(wgit, "_assert_current_branches_are_pushed", lambda repo_specs: None)
    monkeypatch.setattr(wgit, "_assert_source_branches_are_pushed", lambda repo_specs, source_branch: None)
    monkeypatch.setattr(wgit, "_assert_target_branches_absent", lambda repo_specs, target_branch: None)
    monkeypatch.setattr(
        wgit,
        "_assert_super_repo_source_gitlinks_match_submodule_sources",
        lambda repo_path, repo_specs, source_branch: None,
    )
    monkeypatch.setattr(wgit, "_run_git_command", lambda command: commands.append(command) or [])

    wgit._branch_all_around_from_branches(
        repo_path="/repo",
        source_branch="feature/model/main",
        target_branch="feature/model/workstation",
        push=True,
    )

    assert commands == [
        "git -C /repo switch --no-track -c feature/model/workstation origin/feature/model/main",
        "git -C /repo push -u origin feature/model/workstation",
        "git -C /repo/workflow-wielder switch --no-track -c feature/model/workstation origin/feature/model/main",
        "git -C /repo/workflow-wielder push -u origin feature/model/workstation",
    ]


def test_branch_all_around_requires_desired_branch_in_config(monkeypatch):
    monkeypatch.setattr(wgit, "_current_branch", lambda repo_path: "feature/model/main")

    conf = ConfigFactory.parse_string('developer_conf_path = "/repo/context_conf/default_conf/developer.conf"')

    with pytest.raises(RuntimeError, match="wgit.desired_branch"):
        wgit.branch_all_around(repo_path="/repo", conf=conf)


def test_branch_all_around_plan_reports_dirty_before_missing_desired_branch(monkeypatch):
    repo_specs = [
        {"name": ".", "repo_path": "/repo"},
        {"name": "workflow-wielder", "repo_path": "/repo/workflow-wielder"},
    ]
    conf = ConfigFactory.parse_string('developer_conf_path = "/repo/context_conf/default_conf/developer.conf"')

    monkeypatch.setattr(wgit, "_repo_specs_for_super_repo", lambda repo_path: repo_specs)
    monkeypatch.setattr(wgit, "_current_branch", lambda repo_path: "feature/model/main")
    monkeypatch.setattr(
        wgit,
        "_git_status_lines",
        lambda repo_path: [" M wield.py\n"] if repo_path == "/repo/workflow-wielder" else [],
    )

    with pytest.raises(RuntimeError) as exc_info:
        wgit.branch_all_around(repo_path="/repo", conf=conf, dry_run=True)

    message = str(exc_info.value)
    assert "local worktrees are dirty" in message
    assert "[workflow-wielder] /repo/workflow-wielder" in message
    assert "wgit.desired_branch" in message


def test_branch_all_around_plan_reports_dirty_without_fetching(monkeypatch):
    repo_specs = [{"name": ".", "repo_path": "/repo"}]
    conf = ConfigFactory.parse_string(
        """
        wgit {
          desired_branch = "feature/model/workstation"
        }
        """
    )

    monkeypatch.setattr(wgit, "_repo_specs_for_super_repo", lambda repo_path: repo_specs)
    monkeypatch.setattr(wgit, "_current_branch", lambda repo_path: "feature/model/main")
    monkeypatch.setattr(wgit, "_git_status_lines", lambda repo_path: ["?? tmp.txt\n"])
    monkeypatch.setattr(
        wgit,
        "_branch_all_around_from_branches",
        lambda **kwargs: pytest.fail("dirty plan should not reach branch creation preflight"),
    )

    with pytest.raises(RuntimeError, match="local worktrees are dirty"):
        wgit.branch_all_around(repo_path="/repo", conf=conf, dry_run=True)


def test_branch_all_around_reads_desired_branch_from_config(monkeypatch):
    calls = []
    conf = ConfigFactory.parse_string(
        """
        wgit {
          desired_branch = "feature/model/workstation"
        }
        """
    )

    monkeypatch.setattr(wgit, "_current_branch", lambda repo_path: "feature/model/main")
    monkeypatch.setattr(
        wgit,
        "_branch_all_around_from_branches",
        lambda **kwargs: calls.append(kwargs),
    )

    wgit.branch_all_around(repo_path="/repo", conf=conf, push=True, dry_run=False)

    assert calls == [
        {
            "repo_path": "/repo",
            "source_branch": "feature/model/main",
            "target_branch": "feature/model/workstation",
            "push": True,
            "dry_run": False,
        }
    ]
