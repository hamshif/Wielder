import logging
import git
import os
import shutil
import shlex
import subprocess
import tempfile
from pyhocon import ConfigFactory as Cf
from pyhocon.exceptions import ConfigMissingException
from wielder.util.commander import async_cmd
from wielder.util.log_util import setup_logging
from wielder.util.util import DirContext


class WGit:

    def __init__(self, repo_path):

        self.repo_path = repo_path
        self.local_system = 'unix' if os.name != 'nt' else 'win'
        self.awk_command = 'gawk' if self.local_system == 'win' else 'awk'

        with DirContext(repo_path):

            dir_name = repo_path.split(os.sep)[-1]

            latest_commit = async_cmd('git rev-parse --verify HEAD')[0][:-1]

            logging.debug(f'latest_commit for {dir_name}: {latest_commit}')
            self.commit = latest_commit

            branches = async_cmd('git branch')

            branch = 'HEAD'

            for b in branches:

                if b[0] == '*':

                    branch = b[1:-1].strip()

            self.branch = branch

    def get_submodule_commit(self, sub):

        with DirContext(self.repo_path):

            _cmd = f'git ls-tree HEAD {sub}'

            submodule_pointer = async_cmd(_cmd)
            if len(submodule_pointer) == 0:
                return None

            submodule_pointer = submodule_pointer[0].split(' ')[2].split('\t')[0]
            logging.debug(f'submodule {sub} pointer commit: {submodule_pointer}')

            return submodule_pointer

    def get_submodule_names(self):

        with DirContext(self.repo_path):

            print_line = '{ print $2 }'
            _cmd = f"git config --file .gitmodules --get-regexp path | {self.awk_command} '{print_line}'"

            response = async_cmd(_cmd)
            submodule_names = []

            for dirty_submodule_name in response:

                submodule_name = dirty_submodule_name.replace('\n', '')
                if os.name == 'nt':
                    if submodule_name[-1:] == '\r':
                        submodule_name = submodule_name[:-1]

                submodule_names.append(submodule_name)

            logging.debug(response)

            return submodule_names

    def get_submodule_paths(self) -> list[str]:
        gitmodules_path = os.path.join(self.repo_path, ".gitmodules")
        if not os.path.exists(gitmodules_path):
            return []
        response = _run_git_command(
            f"git -C {_quote(self.repo_path)} config --file .gitmodules --get-regexp path"
        )
        paths = []
        for line in response:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                paths.append(parts[1].strip())
        return paths

    def get_tracked_root_items(self, treeish: str = "HEAD") -> list[str]:
        response = _run_git_command(
            f"git -C {_quote(self.repo_path)} ls-tree --name-only {_quote(treeish)}"
        )
        return [line.strip() for line in response if line.strip()]

    def export_tree_to(self, destination: str, treeish: str = "HEAD") -> None:
        os.makedirs(destination, exist_ok=True)
        command = [
            "git",
            "-C",
            self.repo_path,
            "archive",
            "--format=tar",
            treeish,
        ]
        logging.info("Exporting git tree with command:\n%s", shlex.join(command))
        archive_proc = subprocess.Popen(command, stdout=subprocess.PIPE)
        try:
            extract_proc = subprocess.run(
                ["tar", "-xf", "-", "-C", destination],
                stdin=archive_proc.stdout,
                check=False,
            )
            if archive_proc.stdout is not None:
                archive_proc.stdout.close()
            archive_returncode = archive_proc.wait()
            if archive_returncode != 0:
                raise RuntimeError(
                    f"git archive failed with exit code {archive_returncode}: {shlex.join(command)}"
                )
            if extract_proc.returncode != 0:
                raise RuntimeError(
                    f"tar extraction failed with exit code {extract_proc.returncode} into [{destination}]"
                )
        finally:
            if archive_proc.poll() is None:
                archive_proc.kill()

    def update_submodules(self):

        with DirContext(self.repo_path):

            _cmd = 'git submodule update --init --recursive'

            response = async_cmd(_cmd)

            logging.debug(response)

            return response

    def update_submodule(self, sub_path):

        with DirContext(self.repo_path):

            _cmd = f'git submodule update --init -- {sub_path}'

            response = async_cmd(_cmd)

            logging.debug(response)

            return response

    def get_diff(self, sub):

        sub_path = f'{self.repo_path}/{sub}'

        with DirContext(sub_path):

            _cmd = f'git status'

            status = async_cmd(_cmd)

            print(status)

    def as_hocon(self):

        hs = self.as_hocon_injection()
        return Cf.parse_string(hs)

    def as_hocon_injection(self):

        d = vars(self)

        a = ''

        for k, v in d.items():

            a = f'{a}\ngit.{k}:{v}'

        return a

    def as_dict_injection(self):

        d = vars(self)

        injection = {'git': {'subs': {}, 'branches': {}}}

        for k, v in d.items():

            injection['git'][k] = v

        for sub in self.get_submodule_names():

            injection['git']['subs'][sub] = self.get_submodule_commit(sub)
            injection['git']['branches'][sub] = self.get_submodule_branch(sub)

        return injection

    def get_submodule_branch(self, sub):

        full_path = f'{self.repo_path}/{sub}'
        with DirContext(full_path):

            _cmd = f'git rev-parse --abbrev-ref HEAD;'
            branch = async_cmd(_cmd)[0].replace('\n', '')

            if os.name == 'nt':
                if branch[-1:] == '\r':
                    branch = branch[:-1]

        return branch

    def get_commit_message(self, conf, user_message: str) -> str:
        """
        Constructs a standardized, semantic commit message for the agentic organization.
        Parses active_feature schema: <type>/<name>/<node>
        """
        # 1. Extract Agent and Feature details from HOCON
        agent_type = conf.agent.type
        agent_index = conf.agent.index
        agent_id = conf.agent_id
        
        # Parse feature journey
        # TODO: Audit whether git.active_feature is still required for headless
        # branch-control workflows before removing or relocating this config key.
        active_feature = conf.git.active_feature
        f_parts = active_feature.split('/')
        f_type = f_parts[0] if len(f_parts) > 0 else "unknown"
        f_name = f_parts[1] if len(f_parts) > 1 else "initial"
        f_node = f_parts[2] if len(f_parts) > 2 else "main"

        user = conf.user
        machine = conf.machine
        branch = self.branch

        # 2. Build Header
        # Format: [<agent_type>/<agent_index>] (<feature_type>/<feature_name>) <user_message>
        header = f"[{agent_type}/{agent_index}] ({f_type}/{f_name}) {user_message}"

        # 3. Build Metadata Block (Footer)
        metadata = [
            "\n",
            "--- Agentic Metadata ---",
            f"Agent ID: {agent_id}",
            f"Identity: {user} @ {machine}",
            f"Branch:   {branch}",
            f"Feature:  {active_feature}",
            "Source:   Wielder Agentic Organization"
        ]

        return f"{header}\n" + "\n".join(metadata)

    def merge_super_repo(self, conf) -> None:
        target_branch = str(conf.git.promotion.super_repo_target)
        source_branch = self.branch
        source_commit = _run_git_command(
            f"git -C {_quote(self.repo_path)} rev-parse --verify HEAD"
        )[0].strip()

        if source_branch == target_branch:
            logging.info(
                f"Skipping super-repo merge because source branch [{source_branch}] already matches target branch [{target_branch}]."
            )
            return

        if _has_local_git_changes(self.repo_path):
            logging.info(
                f"Super-repo worktree is dirty at [{self.repo_path}]. Proceeding anyway by merging exact commit [{source_commit}] in a temporary worktree."
            )

        _run_git_command(f"git -C {_quote(self.repo_path)} fetch origin")
        temp_worktree = tempfile.mkdtemp(prefix="wgit-merge-super-")
        _run_git_command(
            f"git -C {_quote(self.repo_path)} worktree add --detach {_quote(temp_worktree)} {_quote(f'origin/{target_branch}')}"
        )
        _run_git_command(
            f"git -C {_quote(temp_worktree)} merge --no-commit --no-ff {_quote(source_commit)}"
        )
        logging.info(
            f"Super-repo merge preview completed in temporary worktree [{temp_worktree}]. "
            f"Target branch [{target_branch}] remains uncommitted there until you inspect or commit it."
        )

    def merge_submodules_then_super_repo(self, conf) -> None:
        promotion_conf = conf.git.promotion
        merge_specs = []
        super_target_branch = str(promotion_conf.super_repo_target)

        for submodule_name in self.get_submodule_names():
            submodule_repo = f"{self.repo_path}/{submodule_name}"
            source_branch = self.get_submodule_branch(submodule_name)
            source_commit = _get_repo_head_commit(submodule_repo)
            target_branch = str(promotion_conf.submodule_targets[submodule_name])
            merge_specs.append(
                {
                    "name": submodule_name,
                    "repo_path": submodule_repo,
                    "source_branch": source_branch,
                    "source_commit": source_commit,
                    "target_branch": target_branch,
                }
            )

        for merge_spec in merge_specs:
            _preview_repo_merge(
                repo_path=merge_spec["repo_path"],
                repo_label=merge_spec["name"],
                source_branch=merge_spec["source_branch"],
                source_commit=merge_spec["source_commit"],
                target_branch=merge_spec["target_branch"],
                temp_prefix=f"wgit-preview-{merge_spec['name']}-",
            )

        _checkout_target_branch(self.repo_path, super_target_branch)

        merged_submodule_commits = {}
        for merge_spec in merge_specs:
            merged_submodule_commits[merge_spec["name"]] = _merge_repo_branch_into_target(
                repo_path=merge_spec["repo_path"],
                repo_label=merge_spec["name"],
                source_branch=merge_spec["source_branch"],
                target_branch=merge_spec["target_branch"],
            )

        _finalize_super_repo_merge(
            repo_path=self.repo_path,
            target_branch=super_target_branch,
            merged_submodule_commits=merged_submodule_commits,
        )

    def branch_all_around(
        self,
        conf,
        push: bool = True,
        dry_run: bool = False,
    ) -> None:
        branch_all_around(
            repo_path=self.repo_path,
            conf=conf,
            push=push,
            dry_run=dry_run,
        )


def is_repo(path):

    try:
        _ = git.Repo(path).git_dir
        return True
    except git.exc.NoSuchPathError:
        return False
    except git.exc.InvalidGitRepositoryError:
        return False


def _run_git_command(command: str) -> list[str]:
    logging.info(f"Running git command:\n{command}")
    return async_cmd(command, verbose=True, strict=True)


def _git_status_lines(destination: str) -> list[str]:
    return _run_git_command(
        f"git -C {_quote(destination)} status --porcelain --untracked-files=all --ignore-submodules=none"
    )


def _has_local_git_changes(destination: str) -> bool:
    status_lines = _git_status_lines(destination)
    return any(line.strip() for line in status_lines)


def _has_staged_git_changes(destination: str) -> bool:
    staged_lines = _run_git_command(f"git -C {_quote(destination)} diff --cached --name-only")
    return any(line.strip() for line in staged_lines)


def _quote(value: str) -> str:
    return shlex.quote(str(value))


def _get_repo_head_commit(repo_path: str) -> str:
    return _run_git_command(
        f"git -C {_quote(repo_path)} rev-parse --verify HEAD"
    )[0].strip()


def _preview_repo_merge(
    repo_path: str,
    repo_label: str,
    source_branch: str,
    source_commit: str,
    target_branch: str,
    temp_prefix: str,
) -> None:
    if source_branch == target_branch:
        logging.info(
            f"Skipping preview for [{repo_label}] because source branch [{source_branch}] already matches target branch [{target_branch}]."
        )
        return

    if _has_local_git_changes(repo_path):
        logging.info(
            f"Worktree is dirty for [{repo_label}] at [{repo_path}]. Previewing exact commit [{source_commit}] anyway."
        )

    _run_git_command(f"git -C {_quote(repo_path)} fetch origin")
    temp_worktree = tempfile.mkdtemp(prefix=temp_prefix)
    _run_git_command(
        f"git -C {_quote(repo_path)} worktree add --detach {_quote(temp_worktree)} {_quote(f'origin/{target_branch}')}"
    )
    _run_git_command(
        f"git -C {_quote(temp_worktree)} merge --no-commit --no-ff {_quote(source_commit)}"
    )
    _run_git_command(
        f"git -C {_quote(repo_path)} worktree remove --force {_quote(temp_worktree)}"
    )
    logging.info(
        f"Preview merge is clean for [{repo_label}]: [{source_branch}] -> [{target_branch}] using commit [{source_commit}]."
    )


def _branch_is_ahead_of_origin(repo_path: str, branch_name: str) -> bool:
    behind_count, ahead_count = _get_branch_divergence_counts(repo_path, branch_name)
    return ahead_count > 0


def _get_branch_divergence_counts(repo_path: str, branch_name: str) -> tuple[int, int]:
    counts = _run_git_command(
        f"git -C {_quote(repo_path)} rev-list --left-right --count {_quote(f'origin/{branch_name}...{branch_name}')}"
    )[0].strip()
    behind_count, ahead_count = counts.split()
    return int(behind_count), int(ahead_count)


def _sync_target_branch_with_origin(repo_path: str, target_branch: str) -> None:
    behind_count, ahead_count = _get_branch_divergence_counts(repo_path, target_branch)

    if behind_count == 0 and ahead_count == 0:
        logging.info(
            f"Target branch [{target_branch}] in [{repo_path}] is already in sync with origin."
        )
        return

    if behind_count == 0 and ahead_count > 0:
        logging.info(
            f"Target branch [{target_branch}] in [{repo_path}] is ahead of origin by [{ahead_count}] commit(s) and not behind. Keeping local branch state."
        )
        return

    if behind_count > 0 and ahead_count == 0:
        _run_git_command(
            f"git -C {_quote(repo_path)} merge --ff-only {_quote(f'origin/{target_branch}')}"
        )
        return

    logging.info(
        f"Target branch [{target_branch}] in [{repo_path}] has diverged from origin by behind=[{behind_count}] ahead=[{ahead_count}]. Merging origin branch into local target before promotion continues."
    )
    _run_git_command(
        f"git -C {_quote(repo_path)} merge --no-ff --no-edit {_quote(f'origin/{target_branch}')}"
    )


def _branch_exists_locally(repo_path: str, branch_name: str) -> bool:
    response = _run_git_command(
        f"git -C {_quote(repo_path)} branch --list {_quote(branch_name)}"
    )
    return any(line.strip() for line in response)


def _remote_branch_exists(repo_path: str, branch_name: str) -> bool:
    response = _run_git_command(
        f"git -C {_quote(repo_path)} show-ref --verify --quiet {_quote(f'refs/remotes/origin/{branch_name}')} "
        f"&& echo yes || echo no"
    )
    return response[0].strip() == "yes"


def _resolve_git_ref(repo_path: str, ref: str) -> str:
    return _run_git_command(
        f"git -C {_quote(repo_path)} rev-parse --verify {_quote(ref)}"
    )[0].strip()


def _current_branch(repo_path: str) -> str:
    branch = _run_git_command(
        f"git -C {_quote(repo_path)} rev-parse --abbrev-ref HEAD"
    )[0].strip()
    if branch == "HEAD":
        raise RuntimeError(f"Refusing branch-all-around because [{repo_path}] is on detached HEAD.")
    return branch


def _conf_value(conf, key: str):
    return conf.get(key)


def _developer_conf_hint(conf) -> str:
    if "developer_conf_path" in conf:
        return str(conf.developer_conf_path)
    if "bootstrap_conf_root" in conf:
        return f"{conf.bootstrap_conf_root}/developer.conf"
    if "context_conf_root" in conf:
        return f"{conf.context_conf_root}/developer.conf"
    return "the active context pack developer.conf"


def _desired_branch_from_conf(conf) -> str:
    try:
        desired_branch = str(_conf_value(conf, "wgit.desired_branch")).strip()
    except (AttributeError, ConfigMissingException, KeyError) as exc:
        raise RuntimeError(
            "Refusing branch-all-around because `wgit.desired_branch` is not configured. "
            f"Declare it in {_developer_conf_hint(conf)}, for example:\n\n"
            "wgit {\n"
            '  desired_branch = "feature/<journey>/<node>"\n'
            "}"
        ) from exc

    if not desired_branch:
        raise RuntimeError(
            "Refusing branch-all-around because `wgit.desired_branch` is empty. "
            f"Set a non-empty value in {_developer_conf_hint(conf)}."
        )

    return desired_branch


def _status_line_has_staged_change(status_line: str) -> bool:
    return bool(status_line) and status_line[0] not in (" ", "?")


def _get_submodule_commit_at_ref(repo_path: str, treeish: str, submodule_name: str) -> str:
    response = _run_git_command(
        f"git -C {_quote(repo_path)} ls-tree {_quote(treeish)} -- {_quote(submodule_name)}"
    )
    if not response:
        raise RuntimeError(
            f"Source branch [{treeish}] in [{repo_path}] does not record submodule [{submodule_name}]."
        )
    return response[0].split()[2]


def _repo_specs_for_super_repo(repo_path: str) -> list[dict[str, str]]:
    wgit = WGit(repo_path)
    repo_specs = [{"name": ".", "repo_path": repo_path}]
    for submodule_name in wgit.get_submodule_names():
        repo_specs.append(
            {
                "name": submodule_name,
                "repo_path": os.path.join(repo_path, submodule_name),
            }
        )
    return repo_specs


def _collect_branch_all_around_dirty_reports(
    repo_specs: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    dirty_reports = []
    staged_reports = []
    for repo_spec in repo_specs:
        status_lines = [line.rstrip() for line in _git_status_lines(repo_spec["repo_path"]) if line.strip()]
        if status_lines:
            dirty_reports.append(
                f"[{repo_spec['name']}] {repo_spec['repo_path']}\n" + "\n".join(status_lines)
            )
        staged_lines = [line for line in status_lines if _status_line_has_staged_change(line)]
        if staged_lines:
            staged_reports.append(
                f"[{repo_spec['name']}] {repo_spec['repo_path']}\n" + "\n".join(staged_lines)
            )
    return dirty_reports, staged_reports


def _format_branch_all_around_dirty_reports(
    dirty_reports: list[str],
    staged_reports: list[str],
) -> str:
    staged_message = ""
    if staged_reports:
        staged_message = "\n\nStaged changes were detected:\n" + "\n\n".join(staged_reports)
    return (
        "Refusing branch-all-around because local worktrees are dirty. "
        "Staged, unstaged, untracked, and submodule changes must all be cleared first:\n"
        + "\n\n".join(dirty_reports)
        + staged_message
    )


def _branch_all_around_dirty_message(repo_specs: list[dict[str, str]]) -> str:
    dirty_reports, staged_reports = _collect_branch_all_around_dirty_reports(repo_specs)
    if not dirty_reports:
        return ""
    return _format_branch_all_around_dirty_reports(dirty_reports, staged_reports)


def _assert_branch_all_around_clean(repo_specs: list[dict[str, str]]) -> None:
    dirty_message = _branch_all_around_dirty_message(repo_specs)
    if dirty_message:
        raise RuntimeError(dirty_message)


def _assert_current_branches_are_pushed(repo_specs: list[dict[str, str]]) -> None:
    unpushed_reports = []
    for repo_spec in repo_specs:
        repo_path = repo_spec["repo_path"]
        current_branch = _current_branch(repo_path)
        if not _remote_branch_exists(repo_path, current_branch):
            unpushed_reports.append(
                f"[{repo_spec['name']}] current branch {current_branch} has no origin/{current_branch}"
            )
            continue
        _, ahead_count = _get_branch_divergence_counts(repo_path, current_branch)
        if ahead_count > 0:
            unpushed_reports.append(
                f"[{repo_spec['name']}] current branch {current_branch} is ahead of origin/{current_branch} by {ahead_count} commit(s)"
            )
    if unpushed_reports:
        raise RuntimeError(
            "Refusing branch-all-around because currently checked-out branches are not fully pushed:\n"
            + "\n".join(unpushed_reports)
        )


def _assert_current_branch_parity(
    repo_specs: list[dict[str, str]],
    source_branch: str,
) -> None:
    mismatch_reports = []
    for repo_spec in repo_specs:
        current_branch = _current_branch(repo_spec["repo_path"])
        if current_branch != source_branch:
            mismatch_reports.append(
                f"[{repo_spec['name']}] is on [{current_branch}] instead of [{source_branch}]"
            )
    if mismatch_reports:
        raise RuntimeError(
            "Refusing branch-all-around because the checked-out branch is not coordinated across repos:\n"
            + "\n".join(mismatch_reports)
        )


def _assert_source_branches_are_pushed(
    repo_specs: list[dict[str, str]],
    source_branch: str,
) -> None:
    unpushed_reports = []
    for repo_spec in repo_specs:
        repo_path = repo_spec["repo_path"]
        if not _remote_branch_exists(repo_path, source_branch):
            raise RuntimeError(
                f"Refusing branch-all-around because origin/{source_branch} is missing for [{repo_spec['name']}] at [{repo_path}]."
            )
        if not _branch_exists_locally(repo_path, source_branch):
            continue
        behind_count, ahead_count = _get_branch_divergence_counts(repo_path, source_branch)
        if ahead_count > 0:
            unpushed_reports.append(
                f"[{repo_spec['name']}] {source_branch} is ahead of origin/{source_branch} by {ahead_count} commit(s)"
            )
    if unpushed_reports:
        raise RuntimeError(
            "Refusing branch-all-around because source branches have local-only commits:\n"
            + "\n".join(unpushed_reports)
        )


def _assert_target_branches_absent(
    repo_specs: list[dict[str, str]],
    target_branch: str,
) -> None:
    existing_reports = []
    for repo_spec in repo_specs:
        repo_path = repo_spec["repo_path"]
        if _branch_exists_locally(repo_path, target_branch):
            existing_reports.append(f"[{repo_spec['name']}] local branch exists")
        if _remote_branch_exists(repo_path, target_branch):
            existing_reports.append(f"[{repo_spec['name']}] origin branch exists")
    if existing_reports:
        raise RuntimeError(
            "Refusing branch-all-around because the target branch already exists:\n"
            + "\n".join(existing_reports)
        )


def _assert_super_repo_source_gitlinks_match_submodule_sources(
    repo_path: str,
    repo_specs: list[dict[str, str]],
    source_branch: str,
) -> None:
    mismatch_reports = []
    for repo_spec in repo_specs:
        submodule_name = repo_spec["name"]
        if submodule_name == ".":
            continue
        recorded_commit = _get_submodule_commit_at_ref(
            repo_path,
            f"origin/{source_branch}",
            submodule_name,
        )
        submodule_source_commit = _resolve_git_ref(
            repo_spec["repo_path"],
            f"origin/{source_branch}^{{commit}}",
        )
        if recorded_commit != submodule_source_commit:
            mismatch_reports.append(
                f"[{submodule_name}] super-repo origin/{source_branch} records {recorded_commit}, "
                f"but submodule origin/{source_branch} is {submodule_source_commit}"
            )
    if mismatch_reports:
        raise RuntimeError(
            "Refusing branch-all-around because the source branch is not cleanly aligned across gitlinks:\n"
            + "\n".join(mismatch_reports)
        )


def _fetch_branch_all_around_repos(repo_specs: list[dict[str, str]]) -> None:
    for repo_spec in repo_specs:
        _run_git_command(
            f"git -C {_quote(repo_spec['repo_path'])} fetch --no-recurse-submodules origin"
        )


def _branch_all_around_from_branches(
    repo_path: str,
    source_branch: str,
    target_branch: str,
    push: bool = True,
    dry_run: bool = False,
) -> None:
    repo_specs = _repo_specs_for_super_repo(repo_path)
    _assert_branch_all_around_clean(repo_specs)
    _fetch_branch_all_around_repos(repo_specs)
    _assert_current_branch_parity(repo_specs, source_branch)
    _assert_current_branches_are_pushed(repo_specs)
    _assert_source_branches_are_pushed(repo_specs, source_branch)
    _assert_target_branches_absent(repo_specs, target_branch)
    _assert_super_repo_source_gitlinks_match_submodule_sources(
        repo_path=repo_path,
        repo_specs=repo_specs,
        source_branch=source_branch,
    )

    for repo_spec in repo_specs:
        branch_command = (
            f"git -C {_quote(repo_spec['repo_path'])} switch --no-track -c "
            f"{_quote(target_branch)} {_quote(f'origin/{source_branch}')}"
        )
        push_command = (
            f"git -C {_quote(repo_spec['repo_path'])} push -u origin {_quote(target_branch)}"
        )
        if dry_run:
            logging.info(f"Dry run branch command:\n{branch_command}")
            if push:
                logging.info(f"Dry run push command:\n{push_command}")
            continue
        _run_git_command(branch_command)
        if push:
            _run_git_command(push_command)

    _assert_branch_all_around_clean(repo_specs)


def branch_all_around(
    repo_path: str,
    conf,
    push: bool = True,
    dry_run: bool = False,
) -> None:
    dirty_message = ""
    if dry_run:
        dirty_message = _branch_all_around_dirty_message(
            _repo_specs_for_super_repo(repo_path)
        )
        if dirty_message:
            logging.info(
                "WGit branch-all-around plan found local worktree dirt:\n%s",
                dirty_message,
            )

    source_branch = _current_branch(repo_path)
    try:
        target_branch = _desired_branch_from_conf(conf)
    except RuntimeError as exc:
        if dry_run and dirty_message:
            raise RuntimeError(f"{dirty_message}\n\n{exc}") from exc
        raise

    if dry_run and dirty_message:
        raise RuntimeError(dirty_message)

    if source_branch == target_branch:
        raise RuntimeError(
            "Refusing branch-all-around because the current branch already matches "
            f"`wgit.desired_branch` [{target_branch}]. Stand on the source branch first."
        )

    _branch_all_around_from_branches(
        repo_path=repo_path,
        source_branch=source_branch,
        target_branch=target_branch,
        push=push,
        dry_run=dry_run,
    )


def _checkout_target_branch(repo_path: str, target_branch: str) -> None:
    _run_git_command(f"git -C {_quote(repo_path)} fetch origin")
    if _branch_exists_locally(repo_path, target_branch):
        _run_git_command(
            f"git -C {_quote(repo_path)} checkout {_quote(target_branch)}"
        )
    else:
        _run_git_command(
            f"git -C {_quote(repo_path)} checkout -b {_quote(target_branch)} {_quote(f'origin/{target_branch}')}"
        )
    _sync_target_branch_with_origin(repo_path, target_branch)


def _merge_repo_branch_into_target(
    repo_path: str,
    repo_label: str,
    source_branch: str,
    target_branch: str,
) -> str:
    if _has_local_git_changes(repo_path):
        logging.info(
            f"Worktree is dirty for [{repo_label}] at [{repo_path}]. Proceeding with the real branch-switch workflow may fail if those edits block checkout to [{target_branch}]."
        )

    _checkout_target_branch(repo_path, target_branch)

    if source_branch == target_branch:
        logging.info(
            f"Skipping branch merge for [{repo_label}] because source branch [{source_branch}] already matches target branch [{target_branch}]."
        )
    else:
        _run_git_command(
            f"git -C {_quote(repo_path)} merge --no-ff --no-edit {_quote(source_branch)}"
        )

    merged_commit = _get_repo_head_commit(repo_path)
    if _branch_is_ahead_of_origin(repo_path, target_branch):
        _run_git_command(
            f"git -C {_quote(repo_path)} push origin {_quote(target_branch)}"
        )
        logging.info(
            f"Merged [{repo_label}] branch [{source_branch}] into target branch [{target_branch}] at commit [{merged_commit}] and pushed it to origin."
        )
    else:
        logging.info(
            f"[{repo_label}] target branch [{target_branch}] was already in sync with origin after merge evaluation at commit [{merged_commit}]."
        )

    return merged_commit


def _has_merge_head(repo_path: str) -> bool:
    merge_head_lines = _run_git_command(
        f"git -C {_quote(repo_path)} rev-parse -q --verify MERGE_HEAD || true"
    )
    if not merge_head_lines:
        return False
    merge_head = merge_head_lines[0].strip()
    return bool(merge_head)


def _finalize_super_repo_merge(
    repo_path: str,
    target_branch: str,
    merged_submodule_commits: dict[str, str],
) -> None:
    if _has_local_git_changes(repo_path):
        logging.info(
            f"Super-repo worktree is dirty at [{repo_path}] before finalization. This is expected if submodule gitlinks moved during branch promotion."
        )

    for submodule_name, merged_commit in merged_submodule_commits.items():
        _run_git_command(
            f"git -C {_quote(repo_path)} update-index --cacheinfo 160000,{_quote(merged_commit)},{_quote(submodule_name)}"
        )

    if _has_staged_git_changes(repo_path):
        _run_git_command(
            f"git -C {_quote(repo_path)} commit -m {_quote(f'Update submodule pointers on {target_branch}')}"
        )
        merged_commit = _get_repo_head_commit(repo_path)
        logging.info(
            f"Finalized super-repo target branch [{target_branch}] at commit [{merged_commit}] by recording promoted submodule gitlinks."
        )
    else:
        merged_commit = _get_repo_head_commit(repo_path)
        logging.info(
            f"Super-repo target branch [{target_branch}] has no staged merge or gitlink changes to commit. No new super-repo commit was created."
        )

    if _branch_is_ahead_of_origin(repo_path, target_branch):
        _run_git_command(
            f"git -C {_quote(repo_path)} push origin {_quote(target_branch)}"
        )
        logging.info(
            f"Pushed super-repo target branch [{target_branch}] to origin at commit [{merged_commit}]."
        )
    else:
        logging.info(
            f"Super-repo target branch [{target_branch}] is already in sync with origin after merge evaluation."
        )


def clone_or_update(source, destination, name=None, branch='master', commit_sha=None, local=False):

    logging.info("\nclone_or_update_local_repository\n")

    should_clone = not is_repo(destination)

    logging.info(f"should_clone: {should_clone}\n source: {source}\n destination: {destination}\n name: {name}\n branch: {branch}\n commit_sha: {commit_sha}\n local: {local}")

    if should_clone:
        logging.info(f"Cloning {source} to: {destination}")

        if local:
            if os.path.exists(destination):
                logging.warning(
                    "Replacing stale non-git local clone destination before staging: %s",
                    destination,
                )
                if os.path.isdir(destination):
                    shutil.rmtree(destination)
                else:
                    os.remove(destination)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            _run_git_command(
                f"git clone {_quote(source)} {_quote(destination)}"
            )
        else:
            _run_git_command(f"git clone {_quote(source)} {_quote(destination)}")
    else:
        logging.info("Destination already has git repo")

    revert = branch
    if commit_sha is not None:
        revert = commit_sha

    if _has_local_git_changes(destination):
        logging.warning(
            "Skipping staged sandbox update because local git changes were detected in: %s. "
            "Inspect, stash, or discard them explicitly before rerunning.",
            destination,
        )
        return
    logging.info("No local staged sandbox changes detected. Proceeding without stash.")
    _run_git_command(f"git -C {destination} fetch")
    _run_git_command(f"git -C {destination} checkout {revert}")
    _run_git_command(f"git -C {destination} config pull.rebase false")

    if commit_sha is None:
        _run_git_command(f"git -C {destination} pull")
    else:
        head = _run_git_command(f"git -C {destination} rev-parse --verify HEAD")[0].strip()
        if head != commit_sha:
            raise RuntimeError(
                f"Staging clone failed to reach requested commit. destination={destination} expected={commit_sha} actual={head}"
            )


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    logging.info('Configured logging')
    logging.debug('Configured logging')
