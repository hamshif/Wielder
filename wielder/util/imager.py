#!/usr/bin/env python
import logging
import os
import platform
import json
import shlex
from shutil import rmtree, copyfile, copytree
import socket
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from wielder.util.aws_actions import AWSActions
from wielder.util.commander import async_cmd
from wielder.util.kuber import _get_k3d_surface_conf
from wielder.util.log_util import setup_logging
from wielder.util.util import DirContext
from wielder.wield.enumerator import (
    CloudProvider,
    ImageBuildSurface,
    ImageRegistrySurface,
    ImageRuntimeSurface,
    local_kubes,
    WieldAction,
)
import uuid
import subprocess
import shutil
from wielder.util.wgit import WGit, clone_or_update


def _run_shell(cmd: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    logging.info(f'running:\n{cmd}')
    proc = subprocess.run(
        cmd,
        shell=True,
        executable=shutil.which("bash") or "/bin/sh",
        check=False,
        env=env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {cmd}")
    return proc


def _run_command_with_logged_output(command: list[str], *, error_context: str) -> subprocess.CompletedProcess:
    logging.info("running:\n%s", shlex.join(command))
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_lines: list[str] = []
    if proc.stdout is not None:
        for line in proc.stdout:
            output_lines.append(line)
            stripped = line.rstrip()
            if stripped:
                logging.info("%s", stripped)
    returncode = proc.wait()
    if returncode != 0:
        output = "".join(output_lines).strip()
        raise RuntimeError(
            f"{error_context} failed with exit code {returncode}: {shlex.join(command)}\n{output}"
        )
    return proc


def _requires_linux_amd64_build_platform(
    build_surface: ImageBuildSurface,
    runtime_surface: ImageRuntimeSurface | None,
) -> bool:
    return (
        build_surface == ImageBuildSurface.LOCAL_DOCKER_MACOS_ARM64
        and runtime_surface is not None
        and runtime_surface not in {ImageRuntimeSurface.KIND, ImageRuntimeSurface.K3D}
    )


def _uses_registry_distribution(registry_surface: ImageRegistrySurface | None) -> bool:
    return registry_surface in {
        ImageRegistrySurface.KIND_REGISTRY,
        ImageRegistrySurface.K3D_REGISTRY,
        ImageRegistrySurface.AWS_ECR,
        ImageRegistrySurface.GCP_ARTIFACT_REGISTRY,
    }


DEFAULT_DOCKER_CONTEXT_IGNORE_PATTERNS = (
    ".git",
    "**/.git",
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    "*.pyo",
    "*.swp",
    ".pytest_cache",
    ".mypy_cache",
)


LAYERED_SUPER_REPO_COPY_MARKER = "# WIELDER_LAYERED_SUPER_REPO_COPY"
DEFAULT_LAYERED_SUPER_REPO_SHELL_DIR = "_wielder_super_repo_shell"


def _docker_context_ignore_patterns(configured_patterns=None, include_git_metadata: bool = False):
    patterns = []
    seen = set()
    git_patterns = {".git", "**/.git"}
    for pattern in DEFAULT_DOCKER_CONTEXT_IGNORE_PATTERNS:
        if include_git_metadata and pattern in git_patterns:
            continue
        if pattern not in seen:
            patterns.append(pattern)
            seen.add(pattern)
    if configured_patterns is not None:
        for pattern in configured_patterns:
            pattern = str(pattern)
            if include_git_metadata and pattern in git_patterns:
                continue
            if pattern not in seen:
                patterns.append(pattern)
                seen.add(pattern)
    return patterns, shutil.ignore_patterns(*patterns)


def _conf_value(conf, key: str, default=None):
    if conf is None:
        return default
    if isinstance(conf, dict):
        return conf.get(key, default)
    try:
        if key in conf:
            return conf[key]
    except TypeError:
        pass
    return getattr(conf, key, default)


def _ordered_layered_modules(configured_order: list[str], submodule_paths: list[str]) -> list[str]:
    ordered = []
    seen = set()
    submodule_set = set(submodule_paths)

    for module_path in configured_order:
        module_path = str(module_path).strip("/")
        if not module_path:
            continue
        if module_path not in submodule_set:
            logging.warning(
                "Layered super-repo module [%s] is not listed in .gitmodules; staging it only if the path exists.",
                module_path,
            )
        if module_path not in seen:
            ordered.append(module_path)
            seen.add(module_path)

    missing = [path for path in submodule_paths if path not in seen]
    if missing:
        logging.warning(
            "Layered super-repo config did not list submodule(s) %s; appending them after configured modules.",
            missing,
        )
        ordered.extend(missing)
    return ordered


def _copy_item(source_path: str, destination_path: str, ignore_patterns) -> None:
    if os.path.isdir(source_path):
        shutil.copytree(source_path, destination_path, ignore=ignore_patterns, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy2(source_path, destination_path)


def _stage_layered_super_repo_context(
    *,
    image_context: str,
    staging_dir: str,
    layered_super_repo_context,
    ignore_patterns,
) -> list[str]:
    if not layered_super_repo_context:
        return []

    enabled = bool(_conf_value(layered_super_repo_context, "enabled", False))
    if not enabled:
        return []

    shell_dir = str(
        _conf_value(
            layered_super_repo_context,
            "shell_dir",
            DEFAULT_LAYERED_SUPER_REPO_SHELL_DIR,
        )
    )
    module_order = list(_conf_value(layered_super_repo_context, "module_order", []) or [])
    wgit = WGit(image_context)
    submodule_paths = wgit.get_submodule_paths()
    modules = _ordered_layered_modules(module_order, submodule_paths)
    shell_destination = os.path.join(staging_dir, shell_dir)
    os.makedirs(shell_destination, exist_ok=True)

    excluded_root_items = {path.split("/", 1)[0] for path in submodule_paths}
    for item in wgit.get_tracked_root_items():
        if item in excluded_root_items:
            continue
        source_path = os.path.join(image_context, item)
        if os.path.exists(source_path):
            _copy_item(source_path, os.path.join(shell_destination, item), ignore_patterns)

    git_dir = os.path.join(image_context, ".git")
    if os.path.exists(git_dir):
        _copy_item(git_dir, os.path.join(shell_destination, ".git"), ignore_patterns)

    for module_path in modules:
        source_path = os.path.join(image_context, module_path)
        if not os.path.exists(source_path):
            raise FileNotFoundError(
                f"Layered super-repo module [{module_path}] does not exist at [{source_path}]."
            )
        destination_path = os.path.join(staging_dir, module_path)
        _preflight_git_metadata_overlay(source_path, destination_path)
        _copy_item(source_path, destination_path, ignore_patterns)

    return modules


def _stage_bulk_super_repo_context(
    *,
    image_context: str,
    staging_dir: str,
    bulk_super_repo_context,
    ignore_patterns,
) -> bool:
    if not bulk_super_repo_context:
        return False

    enabled = bool(_conf_value(bulk_super_repo_context, "enabled", False))
    if not enabled:
        return False

    destination = str(_conf_value(bulk_super_repo_context, "destination", ".")).strip("/")
    context_destination = staging_dir if destination in ("", ".") else os.path.join(staging_dir, destination)
    os.makedirs(context_destination, exist_ok=True)

    wgit = WGit(image_context)
    wgit.export_tree_to(context_destination)

    git_dir = os.path.join(image_context, ".git")
    if os.path.exists(git_dir):
        _copy_item(git_dir, os.path.join(context_destination, ".git"), ignore_patterns)

    module_order = list(_conf_value(bulk_super_repo_context, "module_order", []) or [])
    submodule_paths = wgit.get_submodule_paths()
    modules = _ordered_layered_modules(module_order, submodule_paths)

    for module_path in modules:
        source_path = os.path.join(image_context, module_path)
        if not os.path.exists(source_path):
            raise FileNotFoundError(
                f"Bulk super-repo module [{module_path}] does not exist at [{source_path}]."
            )
        destination_path = os.path.join(context_destination, module_path)
        _preflight_git_metadata_overlay(source_path, destination_path)
        WGit(source_path).export_tree_to(destination_path)

        module_git_path = os.path.join(source_path, ".git")
        if os.path.exists(module_git_path):
            _copy_item(module_git_path, os.path.join(destination_path, ".git"), ignore_patterns)

    return True


def _inject_layered_super_repo_copy_instructions(
    *,
    staging_dir: str,
    layered_super_repo_context,
    modules: list[str],
) -> None:
    if not layered_super_repo_context:
        return
    enabled = bool(_conf_value(layered_super_repo_context, "enabled", False))
    if not enabled:
        return

    marker = str(
        _conf_value(
            layered_super_repo_context,
            "copy_marker",
            LAYERED_SUPER_REPO_COPY_MARKER,
        )
    )
    shell_dir = str(
        _conf_value(
            layered_super_repo_context,
            "shell_dir",
            DEFAULT_LAYERED_SUPER_REPO_SHELL_DIR,
        )
    )
    root_destination = str(_conf_value(layered_super_repo_context, "root_destination", "/app/workspace"))
    root_destination = root_destination.rstrip("/")
    dockerfile_path = os.path.join(staging_dir, "Dockerfile")
    with open(dockerfile_path) as f:
        dockerfile = f.read()
    if marker not in dockerfile:
        raise RuntimeError(
            f"Layered super-repo context is enabled but Dockerfile [{dockerfile_path}] "
            f"does not contain marker [{marker}]."
        )

    copy_lines = [
        f"COPY {module_path}/ {root_destination}/{module_path}/"
        for module_path in modules
    ]
    copy_lines.append(f"COPY {shell_dir}/ {root_destination}/")
    rendered = dockerfile.replace(marker, "\n".join(copy_lines))
    with open(dockerfile_path, "w") as f:
        f.write(rendered)


def _preflight_git_metadata_overlay(source_path: str, destination_path: str) -> None:
    source_git_path = os.path.join(source_path, ".git")
    destination_git_path = os.path.join(destination_path, ".git")
    if os.path.isfile(source_git_path) and os.path.isdir(destination_git_path):
        raise RuntimeError(
            "Cannot overlay git-link submodule source "
            f"[{source_path}] onto existing staged repository [{destination_path}]. "
            "The source has a .git file pointing into the super-repo metadata, but the staged "
            "destination already has an embedded .git directory from an older image staging mode. "
            "Remove the stale staged image directory or use a fresh staging root, then rebuild."
        )


def _reset_git_metadata_staging_dir(staging_dir: str) -> None:
    if os.path.exists(staging_dir):
        logging.info(
            "Image requested full git metadata; removing previous generated staging "
            "sandbox before restaging: %s",
            staging_dir,
        )
        shutil.rmtree(staging_dir)


def _kind_nodes(kind_context: str) -> list[str]:
    proc = subprocess.run(
        ["kind", "get", "nodes", "--name", kind_context],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to enumerate kind nodes for cluster [{kind_context}]: {proc.stderr.strip()}"
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _kind_node_has_image(node_name: str, image_ref: str) -> bool:
    proc = subprocess.run(
        ["docker", "exec", node_name, "crictl", "images", "--output", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to inspect images on kind node [{node_name}]: {proc.stderr.strip()}"
        )

    payload = json.loads(proc.stdout or "{}")
    for image in payload.get("images", []):
        repo_tags = image.get("repoTags") or []
        if image_ref in repo_tags:
            return True
    return False


def kind_cluster_has_image(kind_context: str, image_name: str, tag: str) -> bool:
    image_ref = f"{image_name}:{tag}"
    nodes = _kind_nodes(kind_context)
    if not nodes:
        logging.info(f"No nodes found for kind cluster [{kind_context}].")
        return False

    missing_nodes = [node for node in nodes if not _kind_node_has_image(node, image_ref)]
    if missing_nodes:
        logging.info(
            f"kind cluster [{kind_context}] is missing image [{image_ref}] on nodes: {missing_nodes}"
        )
        return False

    logging.info(f"kind cluster [{kind_context}] already has image [{image_ref}] on all nodes.")
    return True


def replace_file(origin_path, origin_regex, destination_path, final_name):
    """
    Validates existence of origin_regex
    Removes old destination
    Copies target with final_name to destination

    :param origin_path:
    :param origin_regex: Origin file regex e.g. App*.zip (AppV1.zip, AppV2.zip ...)
    :param destination_path:
    :param final_name:
    :return:
    """

    target_file = async_cmd(f"find {origin_path} -name {origin_regex}")[0][:-1]

    logging.info(f'Regex "{origin_regex}"" is fount in origin_path:  {target_file}')

    if target_file == '':

        logging.warning(f"couldn't find {origin_path}/{origin_regex} please run: ")
        return

    logging.info(f"Found {target_file} in target")

    full_destination = f"{destination_path}/{final_name}"

    try:
        os.remove(full_destination)

    except Exception as e:
        logging.error(str(e))

    copytree(target_file, full_destination)

    logging.info(f"successfully replaced {full_destination}")


def replace_dir_contents(origin_path, origin_regex, destination_path, destination_dir_name='artifacts'):
    """
    Used to update executable code for docker image packing
    e.g. interpreted code and artifacts.
    Validates existence of directory.
    Validates existence of a file regex in the directory for sanity purposes.
    Removes old destination.
    Copies directory contents to destination under artifacts directory

    :param origin_path: path to directory containing executables to be packed into image
    :param origin_regex: Origin file regex e.g. App*.zip (AppV1.zip, AppV2.zip ...)
           to be found in path for sanity check
    :param destination_path: A destination directory
           where the content of the executable directory can be copied to
    :param destination_dir_name: the name of the destination directory defaults to: artifacts
    :return:
    """

    target_file = async_cmd(f"find {origin_path} -name '{origin_regex}*'")[0][:-1]

    logging.info(
        f'Search results for regex <{origin_regex}> in origin_path:  {origin_path}:\n'
        f'{target_file}'
    )

    if target_file == '':

        logging.error(f"couldn't find {origin_path}/{origin_regex}\nPlease make sure it exists in path")
        return

    logging.info(f"Found {target_file} in target")

    full_destination = f"{destination_path}/{destination_dir_name}"

    rmtree(full_destination, ignore_errors=True)

    copytree(origin_path, full_destination)

    logging.info(f"successfully replaced {full_destination}")

    return target_file


def gcp_push_image(gcp_conf, name, env, tag):

    gcp_name = f'{gcp_conf.image_repo_zone}/{gcp_conf.project}/{env}/{name}'

    os.system(
        f'docker tag {name}:{tag} {gcp_name}:latest;'
        f'gcloud docker -- push {gcp_name}:latest;'
        f'gcloud container images list --repository={gcp_name};'
    )


def push_image(cloud_conf, name, env, tag, cloud=CloudProvider.GCP.value, action: WieldAction = WieldAction.APPLY):

    if cloud == CloudProvider.GCP.value:
        gcp_push_image(cloud_conf, name, env, tag)
    elif cloud == CloudProvider.AWS.value:
        aws_push_image(cloud_conf, name, tag)
    elif cloud == CloudProvider.REGISTRY.value:
        registry_push_image(cloud_conf, name, tag, action=action)


def aws_push_image(aws_conf, name, tag):

    region = aws_conf.image_repo_zone

    repo = f'{aws_conf.account_id}.dkr.ecr.{region}.amazonaws.com'

    profile = aws_conf.cred_profile

    cred = f'aws ecr --profile {profile} get-login-password --region {region} | docker login --username AWS ' \
           f'--password-stdin {repo} '

    logging.info(f'Running:\n{cred}')
    os.system(cred)

    image_name = f'{repo}/{name}:{tag}'

    _cmd = f'docker tag {name}:{tag} {image_name};'

    logging.info(f'Running cmd:\n')
    os.system(_cmd)

    _cmd = f'docker push {image_name};'

    logging.info(f'Running cmd:\n')
    os.system(_cmd)

    logging.info(f'aws ecr --profile {profile} describe-images --repository-name  {name} --region {region};')


def registry_push_image(registry_conf, name, tag, action: WieldAction = WieldAction.APPLY):
    """
    Publish a locally built image to a plain registry authority using standard
    `docker tag` + `docker push`.

    This helper is intentionally generic. It is not specific to k3d. It works
    for any Kubernetes workflow that expects images to be pullable from a
    registry endpoint, provided the target cluster can resolve and reach the
    configured registry authority. That includes k3d and can also support kind
    or other local cluster topologies if they are configured to trust and reach
    the same registry.
    """
    local_image = f"{name}:{tag}"
    remote_image = f"{registry_conf.push_authority}/{name}:{tag}"

    if action != WieldAction.APPLY:
        logging.info(
            "WieldAction is PLAN. Dry-run registry publication for:\n"
            "  ------------------------------------------------------------------------\n"
            f"  docker tag {local_image} {remote_image}\n"
            f"  docker push {remote_image}\n"
            "  ------------------------------------------------------------------------"
        )
        return

    _cmd_check = f'docker images --format "{{{{.Repository}}}}:{{{{.Tag}}}}" | grep "^{local_image}$";'
    image_trace = async_cmd(_cmd_check)
    if not image_trace:
        raise RuntimeError(
            f"Cannot publish image because local source image [{local_image}] was not found in the Docker image store."
        )

    _run_shell(f"docker tag {local_image} {remote_image};")
    _run_shell(f"docker push {remote_image};")


def _resolve_registry_push_endpoint(registry_conf) -> tuple[str, int]:
    push_authority = str(registry_conf.push_authority)
    parsed = urlparse(push_authority if "://" in push_authority else f"//{push_authority}")
    if parsed.hostname is None or parsed.port is None:
        raise ValueError(
            f"Local registry push_authority [{push_authority}] must include a host and explicit port."
        )
    return parsed.hostname, parsed.port


def registry_push_endpoint_available(registry_conf) -> bool:
    host, port = _resolve_registry_push_endpoint(registry_conf)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError as exc:
        logging.warning(
            "Skipping local registry publication because registry push endpoint [%s:%s] "
            "is unavailable: %s",
            host,
            port,
            exc,
        )
        return False


def remote_registry_image_exists(registry_conf, image_name: str, tag: str) -> bool | None:
    if not registry_push_endpoint_available(registry_conf):
        return None

    manifest_url = f"http://{registry_conf.push_authority}/v2/{image_name}/manifests/{tag}"
    request = Request(
        manifest_url,
        headers={
            "Accept": (
                "application/vnd.docker.distribution.manifest.v2+json,"
                "application/vnd.oci.image.manifest.v1+json"
            )
        },
        method="HEAD",
    )
    try:
        with urlopen(request, timeout=2.0):
            return True
    except HTTPError as exc:
        if exc.code == 404:
            return False
        logging.warning(
            "Could not inspect registry image tag [%s:%s] at [%s]: HTTP %s",
            image_name,
            tag,
            registry_conf.push_authority,
            exc.code,
        )
        return None
    except URLError as exc:
        logging.warning(
            "Could not inspect registry image tag [%s:%s] at [%s]: %s",
            image_name,
            tag,
            registry_conf.push_authority,
            exc,
        )
        return None


def aws_ecr_image_exists(aws_conf, image_name: str, tag: str) -> bool | None:
    try:
        return AWSActions(aws_conf).ecr_image_exists(
            repository_name=image_name,
            image_tag=tag,
        )
    except Exception as exc:
        logging.warning(
            "Could not inspect AWS ECR image tag [%s:%s]; continuing without remote skip. Reason: %s",
            image_name,
            tag,
            exc,
        )
        return None


def gcp_artifact_registry_image_exists(image_ref: str, project_id: str) -> bool | None:
    proc = subprocess.run(
        [
            "gcloud",
            "artifacts",
            "docker",
            "images",
            "describe",
            image_ref,
            "--project",
            project_id,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return True

    stderr = proc.stderr or ""
    if "NOT_FOUND" in stderr or "not found" in stderr.lower():
        return False

    logging.warning(
        "Could not inspect GCP Artifact Registry image tag [%s]; continuing without remote skip. Reason: %s",
        image_ref,
        stderr.strip(),
    )
    return None


class ImageRegistryAccessor:
    def image_ref(self, image_name: str, tag: str) -> str:
        raise NotImplementedError(f"{self.__class__.__name__}.image_ref is not implemented.")

    def image_exists(self, image_name: str, tag: str) -> bool | None:
        raise NotImplementedError(f"{self.__class__.__name__}.image_exists is not implemented.")

    def push_image(self, image_name: str, tag: str, action: WieldAction = WieldAction.APPLY) -> None:
        raise NotImplementedError(f"{self.__class__.__name__}.push_image is not implemented.")

    def ensure_image(
        self,
        *,
        image_name: str,
        tag: str,
        action: WieldAction,
        build_callback: Callable[[], None] | None = None,
        mutation_actions: set[WieldAction] | None = None,
        expected_refs: set[str] | None = None,
        label: str = "image",
    ) -> bool:
        image_ref = self.image_ref(image_name=image_name, tag=tag)
        if expected_refs is not None and expected_refs != {image_ref}:
            raise ValueError(
                f"Image ensure for [{label}] resolves [{image_ref}], "
                f"but configured runtime images are {sorted(expected_refs)}."
            )

        exists = self.image_exists(image_name=image_name, tag=tag)
        if exists:
            logging.info("Image exists in configured registry: %s", image_ref)
            return False

        if exists is None:
            message = f"Could not verify configured registry image state for [{image_ref}]."
            if action in (mutation_actions or {WieldAction.APPLY, WieldAction.INIT, WieldAction.RUN}):
                raise RuntimeError(message)
            logging.warning(message)
            return False

        if action not in (mutation_actions or {WieldAction.APPLY, WieldAction.INIT, WieldAction.RUN}):
            logging.info("Image missing from configured registry and would be built on apply/run: %s", image_ref)
            return False

        if build_callback is None:
            raise RuntimeError(f"Image [{image_ref}] is missing and no build callback was supplied.")

        logging.info("Image missing from configured registry; building and publishing: %s", image_ref)
        build_callback()
        return True


class RemoteRegistryImageAccessor(ImageRegistryAccessor):
    def __init__(self, registry_conf):
        self.registry_conf = registry_conf

    def image_ref(self, image_name: str, tag: str) -> str:
        return f"{str(self.registry_conf.pull_authority).rstrip('/')}/{image_name}:{tag}"

    def image_exists(self, image_name: str, tag: str) -> bool | None:
        return remote_registry_image_exists(self.registry_conf, image_name=image_name, tag=tag)


class AWSECRImageAccessor(ImageRegistryAccessor):
    def __init__(self, aws_conf):
        self.aws_conf = aws_conf

    def image_ref(self, image_name: str, tag: str) -> str:
        return f"{str(self.aws_conf.registry_authority).rstrip('/')}/{image_name}:{tag}"

    def image_exists(self, image_name: str, tag: str) -> bool | None:
        return aws_ecr_image_exists(self.aws_conf.push, image_name=image_name, tag=tag)


class GCPArtifactRegistryImageAccessor(ImageRegistryAccessor):
    def __init__(self, registry_conf):
        self.registry_conf = registry_conf

    def remote_image_name(self, image_name: str) -> str:
        repository_prefix = f"{self.registry_conf.repository_id}/"
        if image_name.startswith(repository_prefix):
            return image_name[len(repository_prefix):]
        return image_name

    def image_ref(self, image_name: str, tag: str) -> str:
        return f"{str(self.registry_conf.registry_authority).rstrip('/')}/{self.remote_image_name(image_name)}:{tag}"

    def image_exists(self, image_name: str, tag: str) -> bool | None:
        return gcp_artifact_registry_image_exists(
            image_ref=self.image_ref(image_name=image_name, tag=tag),
            project_id=str(self.registry_conf.project_id),
        )

    def push_image(self, image_name: str, tag: str, action: WieldAction = WieldAction.APPLY) -> None:
        registry_host = str(self.registry_conf.registry_authority).split("/", 1)[0]
        local_image = f"{image_name}:{tag}"
        remote_image = self.image_ref(image_name=image_name, tag=tag)

        if action != WieldAction.APPLY:
            logging.info(
                "WieldAction is PLAN. Dry-run GCP Artifact Registry publication for:\n"
                "  ------------------------------------------------------------------------\n"
                f"  gcloud auth configure-docker {registry_host} --quiet\n"
                f"  docker tag {local_image} {remote_image}\n"
                f"  docker push {remote_image}\n"
                "  ------------------------------------------------------------------------"
            )
            return

        _run_command_with_logged_output(
            ["gcloud", "auth", "configure-docker", registry_host, "--quiet"],
            error_context=f"Failed to configure Docker auth for GCP Artifact Registry [{registry_host}]",
        )

        for command in (
            ["docker", "tag", local_image, remote_image],
            ["docker", "push", remote_image],
        ):
            _run_command_with_logged_output(
                command,
                error_context=(
                    f"Failed to publish image [{remote_image}] with command [{shlex.join(command)}]"
                )
            )


def _materialize_factory_value(value):
    return value() if callable(value) else value


def image_registry_accessor(
    registry_surface: ImageRegistrySurface | str,
    registry_conf: Any | Callable[[], Any],
) -> ImageRegistryAccessor:
    surface = (
        registry_surface
        if isinstance(registry_surface, ImageRegistrySurface)
        else ImageRegistrySurface(str(registry_surface))
    )
    materialized_registry_conf = _materialize_factory_value(registry_conf)

    if surface in {ImageRegistrySurface.KIND_REGISTRY, ImageRegistrySurface.K3D_REGISTRY}:
        return RemoteRegistryImageAccessor(materialized_registry_conf)

    if surface == ImageRegistrySurface.AWS_ECR:
        return AWSECRImageAccessor(materialized_registry_conf)

    if surface == ImageRegistrySurface.GCP_ARTIFACT_REGISTRY:
        return GCPArtifactRegistryImageAccessor(materialized_registry_conf)

    raise NotImplementedError(
        f"Image registry accessor is not implemented for registry surface [{surface.value}]."
    )


def configured_image_registry_accessor(
    conf,
) -> ImageRegistryAccessor:
    surface = ImageRegistrySurface(str(conf.image_registry_surface))
    match surface:
        case ImageRegistrySurface.KIND_REGISTRY:
            return image_registry_accessor(surface, conf.kind.registry)
        case ImageRegistrySurface.K3D_REGISTRY:
            return image_registry_accessor(surface, _get_k3d_surface_conf(conf).registry)
        case ImageRegistrySurface.AWS_ECR:
            return image_registry_accessor(surface, conf.aws.ecr)
        case ImageRegistrySurface.GCP_ARTIFACT_REGISTRY:
            return image_registry_accessor(surface, conf.gcp.artifact_registry)
        case _:
            raise NotImplementedError(
                f"Configured image registry accessor is not implemented for registry surface [{surface.value}]."
            )


def ensure_configured_registry_image(
    conf,
    *,
    image_name: str,
    tag: str,
    action: WieldAction | str,
    build_callback: Callable[[], None] | None = None,
    expected_refs: set[str] | None = None,
    label: str = "image",
    mutation_actions: set[WieldAction] | None = None,
) -> bool:
    resolved_action = action if isinstance(action, WieldAction) else WieldAction(str(action))
    return configured_image_registry_accessor(conf).ensure_image(
        image_name=image_name,
        tag=tag,
        action=resolved_action,
        build_callback=build_callback,
        expected_refs=expected_refs,
        label=label,
        mutation_actions=mutation_actions,
    )


def _build_current_image_version(
    *,
    force: bool,
    reuse_existing_version: bool | None,
) -> bool:
    if reuse_existing_version is not None:
        return not bool(reuse_existing_version)
    return bool(force)


def pack_image(
    image_root,
    name,
    image_name=None,
    force=False,
    reuse_existing_version: bool | None = None,
    tag='dev',
    build_surface: ImageBuildSurface | None = None,
    registry_surface: ImageRegistrySurface | None = None,
    runtime_surface: ImageRuntimeSurface | None = None,
    kind_context='kind',
    build_args=None,
):
    """

    :param build_args: formulated arguments for docker build command e.g. tag=dev
    :param kind_context:
    :param build_surface:
    :param registry_surface:
    :param runtime_surface:
    :param image_name:
    :param tag:
    :param name: The name of the directory in which all the necessary resources for packing the image reside
    usually the name of the service.
    :param force: legacy compatibility switch for rebuilding the current image version
    :param reuse_existing_version: skip rebuilding when the current image version already exists
    :param image_root:
    :return:
    """

    if image_name is None:
        image_name = name

    added_args = ''

    if build_args is not None:

        for build_arg in build_args:
            added_args = f'{added_args} --build-arg {build_arg}'

    _cmd = f'docker images --format "{{{{.Repository}}}}:{{{{.Tag}}}}" | grep "^{image_name}:{tag}$";'

    image_trace = async_cmd(
        _cmd
    )

    logging.info(f"{name} image_trace: {image_trace}")

    # Check if the list is empty
    if _build_current_image_version(force=force, reuse_existing_version=reuse_existing_version) or not image_trace:

        logging.info(f"attempting to create image {name}")

        prefix = 'docker build'

        if build_surface is None:
            raise NotImplementedError("pack_image requires an explicit build_surface.")
        if _requires_linux_amd64_build_platform(build_surface, runtime_surface):
                prefix = f'DOCKER_BUILDKIT=1 {prefix} --platform linux/amd64'

        _cmd = f'{prefix} -t {image_name}:{tag}{added_args} {image_root};'

        _run_shell(_cmd)

        _cmd = f'docker images --format "{{{{.Repository}}}}:{{{{.Tag}}}}" | grep "^{image_name}:{tag}$";'
        _run_shell(_cmd)

        if runtime_surface == ImageRuntimeSurface.KIND and not _uses_registry_distribution(registry_surface):
            if not kind_cluster_has_image(kind_context, image_name, tag):
                _cmd = f'kind load docker-image {image_name}:{tag} --name {kind_context}'
                _run_shell(_cmd)
            else:
                logging.info(
                    f"Skipping kind image load for [{image_name}:{tag}] because it is already present on all nodes."
                )


def pack_image_antifragile(
    image_context,
    image_root,
    name,
    staging_root,
    action=WieldAction.PLAN,
    image_name=None,
    force=False,
    reuse_existing_version: bool | None = None,
    tag='dev',
    build_surface: ImageBuildSurface | None = None,
    registry_surface: ImageRegistrySurface | None = None,
    runtime_surface: ImageRuntimeSurface | None = None,
    kind_context='kind',
    build_args=None,
    build_context_overlays=None,
    docker_context_ignore_patterns=None,
    include_git_metadata: bool = False,
    layered_super_repo_context=None,
    bulk_super_repo_context=None,
):
    """
    Antifragile Parallel Injection: Stages the execution bounds securely into an isolated sandbox 
    before building. Implements the Terraform pattern of WieldAction (PLAN/APPLY).
    """
    if image_name is None:
        image_name = name

    added_args = ''
    if build_args is not None:
        for build_arg in build_args:
            added_args = f'{added_args} --build-arg {build_arg}'

    _cmd_check = f'docker images --format "{{{{.Repository}}}}:{{{{.Tag}}}}" | grep "^{image_name}:{tag}$";'
    image_trace = async_cmd(_cmd_check)

    logging.info(f"{name} image_trace: {image_trace}")

    if _build_current_image_version(force=force, reuse_existing_version=reuse_existing_version) or not image_trace:
        logging.info(f"\nAntifragile Orchestration: Attempting to sandbox and bind image {image_name}:{tag}\n")
        logging.info(f"Resolved Staging Root:\n{staging_root}\n")

        prefix = 'docker build'
        if build_surface is None:
            raise NotImplementedError("pack_image_antifragile requires an explicit build_surface.")
        if _requires_linux_amd64_build_platform(build_surface, runtime_surface):
            prefix = f'DOCKER_BUILDKIT=1 {prefix} --platform linux/amd64'

        _cmd = f'{prefix} -t {image_name}:{tag}{added_args} .;'

        if action != WieldAction.APPLY:
            if not os.path.isdir(image_root):
                raise FileNotFoundError(f"Image root [{image_root}] does not exist.")

            if build_context_overlays is None:
                build_context_overlays = []

            for source_path, _relative_dest in build_context_overlays:
                if not os.path.exists(source_path):
                    raise FileNotFoundError(
                        f"Staged build overlay source [{source_path}] does not exist."
                    )

            logging.info(
                "WieldAction is PLAN. Skipping sandbox staging and dry-running image build:\n"
                "  ------------------------------------------------------------------------\n"
                f"  {_cmd}\n"
                "  ------------------------------------------------------------------------"
            )
            if runtime_surface == ImageRuntimeSurface.KIND and not _uses_registry_distribution(registry_surface):
                logging.info(
                    "WieldAction is PLAN. Dry-run kind image load:\n"
                    "  ------------------------------------------------------------------------\n"
                    f"  kind load docker-image {image_name}:{tag} --name {kind_context}\n"
                    "  ------------------------------------------------------------------------"
                )
            return
        
        # 1. Establish the Static Staging Area natively derived strictly from the explicit caller topology
        staging_dir = f"{staging_root}/{image_name}"
        
        logging.info(f"\nResolved Staging Path:\n{staging_dir}\n")
        logging.info(f"Cloning live execution bounds into isolated staging sandbox: {staging_dir}")
        if include_git_metadata:
            _reset_git_metadata_staging_dir(staging_dir)
        os.makedirs(staging_dir, exist_ok=True)
        
        try:
            dockerignore_lines, ignore_patterns = _docker_context_ignore_patterns(
                docker_context_ignore_patterns,
                include_git_metadata=include_git_metadata,
            )
            # 2. Replicate the required repositories natively via strict Git forensics tracking to ensure reproducible builds
            if include_git_metadata:
                logging.info(
                    "Image [%s] requested full git metadata in the Docker context. "
                    "Skipping the default per-repo git clones and relying on declared build-context overlays.",
                    name,
                )
            else:
                for repo in WGit(image_context).get_submodule_paths():
                    src_path = f"{image_context}/{repo}"
                    dst_path = f"{staging_dir}/{repo}"
                    if os.path.exists(src_path):
                        try:
                            wgit = WGit(src_path)
                            commit_sha = wgit.commit
                            logging.info(f"Locking {repo} strictly to commit hash: {commit_sha}")
                            clone_or_update(
                                source=src_path,
                                destination=dst_path,
                                name=repo,
                                commit_sha=commit_sha,
                                local=True
                            )
                        except Exception as e:
                            logging.error(f"Failed to cryptographically lock {repo} via git: {e}")
                            raise
            
            # 3. Natively overlay the App's specific execution payload deeply into the Sandbox Context
            image_root_items = os.listdir(image_root)
            ignored_image_root_items = ignore_patterns(image_root, image_root_items)
            for item in image_root_items:
                if item in ignored_image_root_items:
                    logging.info(f"Skipping ignored Docker context item: {image_root}/{item}")
                    continue
                s = os.path.join(image_root, item)
                d = os.path.join(staging_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, ignore=ignore_patterns, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

            bulk_super_repo_staged = _stage_bulk_super_repo_context(
                image_context=image_context,
                staging_dir=staging_dir,
                bulk_super_repo_context=bulk_super_repo_context,
                ignore_patterns=ignore_patterns,
            )

            layered_super_repo_modules = _stage_layered_super_repo_context(
                image_context=image_context,
                staging_dir=staging_dir,
                layered_super_repo_context=layered_super_repo_context,
                ignore_patterns=ignore_patterns,
            )
            if bulk_super_repo_staged and layered_super_repo_modules:
                raise RuntimeError(
                    "Image context requested both bulk and layered super-repo staging. "
                    "Choose one build-context strategy."
                )

            if build_context_overlays is None:
                build_context_overlays = []

            for source_path, relative_dest in build_context_overlays:
                if not os.path.exists(source_path):
                    raise FileNotFoundError(
                        f"Staged build overlay source [{source_path}] does not exist."
                    )

                destination_path = os.path.join(staging_dir, relative_dest)
                os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                if os.path.isdir(source_path):
                    if include_git_metadata:
                        _preflight_git_metadata_overlay(source_path, destination_path)
                    shutil.copytree(source_path, destination_path, ignore=ignore_patterns, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, destination_path)

            _inject_layered_super_repo_copy_instructions(
                staging_dir=staging_dir,
                layered_super_repo_context=layered_super_repo_context,
                modules=layered_super_repo_modules,
            )

            dockerignore_path = os.path.join(staging_dir, ".dockerignore")
            with open(dockerignore_path, "w") as f:
                f.write("\n".join(dockerignore_lines) + "\n")
            
            logging.info(
                "Executing fully isolated typographical build:\n"
                "  ------------------------------------------------------------------------\n"
                f"  {_cmd}\n"
                "  ------------------------------------------------------------------------"
            )
            
            with DirContext(staging_dir):
                if action == WieldAction.APPLY:
                    _run_shell(_cmd)
                    _run_shell(_cmd_check)
                    if runtime_surface == ImageRuntimeSurface.KIND and not _uses_registry_distribution(registry_surface):
                        if not kind_cluster_has_image(kind_context, image_name, tag):
                            _run_shell(f'kind load docker-image {image_name}:{tag} --name {kind_context}')
                        else:
                            logging.info(
                                f"Skipping kind image load for [{image_name}:{tag}] because it is already present on all nodes."
                            )
                else:
                    logging.info(
                        "WieldAction is PLAN. Dry-run sandboxing successful. Bypass execution of:\n"
                        "  ------------------------------------------------------------------------\n"
                        f"  {_cmd}\n"
                        "  ------------------------------------------------------------------------"
                    )
                    if runtime_surface == ImageRuntimeSurface.KIND and not _uses_registry_distribution(registry_surface):
                        logging.info(
                            "WieldAction is PLAN. Dry-run kind image load:\n"
                            "  ------------------------------------------------------------------------\n"
                            f"  kind load docker-image {image_name}:{tag} --name {kind_context}\n"
                            "  ------------------------------------------------------------------------"
                        )
            
        except Exception as e:
            logging.error(f"Sandbox isolation completely failed: {e}")
            raise e
        finally:
            logging.info(f"Sandbox retained for auditability at {staging_dir}")


def shallow(base, tag, host_path, host_target, image_dest):
    """
    Use with caution!!!
    This function builds another layer on an existing image.
    The base looks like this:
        ARG BASE
        ARG TAG
        ARG HOST_PATH
        ARG IMAGE_PATH

        FROM ${BASE}:${TAG}
        COPY ${TARGET} ${IMAGE_PATH}

    Intended use case is to change configuration on an existing image

    :param host_target: The file or directory to be added to the image
    :param base: image name
    :param tag: image tag
    :param host_path:
    :param image_dest:
    :return:
    """

    _cmd = f'docker build . -t {base}:{tag} ' \
           f'--build-arg BASE={base} ' \
           f'--build-arg TAG={tag} ' \
           f'--build-arg HOST_TARGET={host_target} ' \
           f'--build-arg IMAGE_DEST={image_dest} '

    logging.info(f'running command:\n{_cmd}')

    here = __file__
    i = here.rfind('/')
    here = here[:i]
    _shallow = f'{here}/shallow'

    logging.debug(f'shallow is:\n{_shallow}')

    copyfile(f'{_shallow}/Dockerfile',  f'{host_path}/Dockerfile')

    with DirContext(host_path):

        os.system('ls -la')
        os.system(_cmd)


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    logging.info('Poomba')
    logging.debug('Simba')
