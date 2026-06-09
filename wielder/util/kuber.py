import logging
import os
import shlex
import shutil
import subprocess
import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from time import monotonic, sleep
from typing import Any

import yaml
from wielder.util.commander import async_cmd
from wielder.util.credential_helper import (
    aws_mfa_cred_as_boto3_session_kwargs,
    aws_mfa_cred_as_subprocess_env,
    get_aws_mfa_cred_command,
)
from wielder.util.util import get_aws_session
from wielder.wield.deployer import get_pods
from wielder.wield.enumerator import WieldAction
from wielder.wield.kube_probe import get_kube_namespace_resources_by_type

K3D = "k3d"


@dataclass(frozen=True)
class KubeContextHandle:
    context_name: str
    provider: str
    runtime_surface: str
    cluster_name: str
    namespace_default: str = "default"
    region: str | None = None
    account_id: str | None = None
    capabilities: dict[str, bool] | None = None

    def can(self, capability: str) -> bool:
        return bool((self.capabilities or {}).get(capability, False))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KubernetesWorkloadReadiness:
    state: str
    ready: bool
    needs_apply: bool
    detail: str
    kube_context: str
    namespace: str
    api_resource: str
    resource_name: str
    desired_replicas: int | None = None
    ready_replicas: int | None = None
    available_replicas: int | None = None
    observed_generation: int | None = None
    generation: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def update_kubernetes_context(
    runtime_env,
    cred_profile,
    region,
    kube_cluster_name,
    context_alias: str | None = None,
    aws_cred_role: str | None = None,
):

    if runtime_env == 'aws':
        context_args = ["aws", "eks"]
        if cred_profile and not aws_cred_role:
            context_args.extend(["--profile", str(cred_profile)])
        context_args.extend(["--region", str(region), "update-kubeconfig", "--name", str(kube_cluster_name)])
        if context_alias:
            context_args.extend(["--alias", str(context_alias)])
        context_cmd = shlex.join(context_args)

        if aws_cred_role:
            context_cmd = f"{get_aws_mfa_cred_command(aws_cred_role)} {context_cmd}"

        logging.info(f'Running Kubernetes context change command:\n{context_cmd}')

        os.system(context_cmd)

    elif runtime_env == 'gcp':
        logging.warning("Gaining context for GCP hasn't been written")
    elif runtime_env == 'azure':
        logging.warning("Gaining context for Azure hasn't been written")


def _run_cmd(
    args: list[str],
    check: bool = True,
    capture_output: bool = True,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    logging.info("Running command:\n%s", " ".join(args))
    proc = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=capture_output,
        env=env,
        input=input_text,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {proc.returncode}: {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def ensure_kubernetes_namespace(
    kube_context: str,
    namespace: str,
    env: dict[str, str] | None = None,
) -> None:
    namespace_manifest = _run_cmd(
        [
            "kubectl",
            "--context",
            str(kube_context),
            "create",
            "namespace",
            str(namespace),
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        env=env,
    )
    _run_cmd(
        [
            "kubectl",
            "--context",
            str(kube_context),
            "apply",
            "-f",
            "-",
        ],
        env=env,
        input_text=namespace_manifest.stdout,
    )


def stream_kubernetes_logs(
    kube_context: str,
    namespace: str,
    resource: str,
    container_name: str | None = None,
    follow: bool = True,
) -> None:
    args = [
        "kubectl",
        "--context",
        str(kube_context),
        "-n",
        str(namespace),
        "logs",
    ]
    if follow:
        args.append("-f")
    args.append(str(resource))
    if container_name is not None:
        args.extend(["-c", str(container_name)])
    _run_cmd(args, capture_output=False)


def wait_for_kubernetes_rollout(
    kube_context: str,
    namespace: str,
    resource: str,
    timeout_seconds: int | None = None,
) -> None:
    args = [
        "kubectl",
        "--context",
        str(kube_context),
        "-n",
        str(namespace),
        "rollout",
        "status",
        str(resource),
    ]
    if timeout_seconds is not None:
        args.append(f"--timeout={int(timeout_seconds)}s")
    _run_cmd(args, capture_output=False)


def get_running_kubernetes_pod_name_by_label(
    kube_context: str,
    namespace: str,
    label_selector: str,
) -> str:
    result = _run_cmd(
        [
            "kubectl",
            "--context",
            str(kube_context),
            "-n",
            str(namespace),
            "get",
            "pod",
            "-l",
            str(label_selector),
            "-o",
            "json",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to locate Kubernetes pod by label "
            f"[{label_selector}] in namespace [{namespace}]: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    payload = json.loads(result.stdout or "{}")
    for pod in payload.get("items", []):
        if pod.get("status", {}).get("phase") == "Running":
            return pod["metadata"]["name"]

    raise RuntimeError(
        f"No running Kubernetes pod found in namespace [{namespace}] with label [{label_selector}]."
    )


def _assert_safe_pod_absolute_path(pod_path: str) -> str:
    normalized_path = str(pod_path).strip()
    if not normalized_path:
        raise ValueError("Refusing to delete an empty in-pod path.")
    if "\\" in normalized_path:
        raise ValueError(f"Refusing non-POSIX in-pod path [{pod_path}].")
    path = PurePosixPath(normalized_path)
    if not path.is_absolute():
        raise ValueError(f"Refusing relative in-pod path [{pod_path}].")
    if path.as_posix() == "/":
        raise ValueError("Refusing to delete the in-pod filesystem root.")
    if any(part == ".." for part in path.parts):
        raise ValueError(f"Refusing unsafe in-pod path [{pod_path}].")
    return path.as_posix()


def delete_kubernetes_pod_path_by_label(
    kube_context: str,
    namespace: str,
    label_selector: str,
    pod_path: str,
    container_name: str | None = None,
) -> str:
    safe_path = _assert_safe_pod_absolute_path(pod_path)
    pod_name = get_running_kubernetes_pod_name_by_label(
        kube_context=kube_context,
        namespace=namespace,
        label_selector=label_selector,
    )
    args = [
        "kubectl",
        "--context",
        str(kube_context),
        "-n",
        str(namespace),
        "exec",
        pod_name,
    ]
    if container_name is not None:
        args.extend(["-c", str(container_name)])
    args.extend(["--", "rm", "-rf", "--", safe_path])
    _run_cmd(args)
    logging.info(
        "Deleted in-pod path [%s] through pod [%s] selected by label [%s].",
        safe_path,
        pod_name,
        label_selector,
    )
    return pod_name


def kubernetes_resource_inspect_command(
    kube_context: str,
    namespace: str,
    api_resource: str,
    resource_name: str,
) -> str:
    return (
        f"kubectl --context {kube_context} -n {namespace} "
        f"get {api_resource} {resource_name}"
    )


def _running_inside_kubernetes() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST")) and os.path.exists(
        "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )


def _prefer_kubernetes_client() -> bool:
    return _running_inside_kubernetes() or shutil.which("kubectl") is None


def _normalize_api_resource(api_resource: str) -> str:
    normalized = str(api_resource).strip().lower()
    aliases = {
        "deploy": "deployment",
        "deploys": "deployment",
        "deployment": "deployment",
        "deployments": "deployment",
        "statefulset": "statefulset",
        "statefulsets": "statefulset",
        "sts": "statefulset",
        "pod": "pod",
        "pods": "pod",
        "job": "job",
        "jobs": "job",
        "daemonset": "daemonset",
        "daemonsets": "daemonset",
        "ds": "daemonset",
    }
    return aliases.get(normalized, normalized)


def _new_kubernetes_inspection_api_client(kube_context: str):
    from kubernetes import client, config

    if _running_inside_kubernetes():
        config.load_incluster_config()
        return client.ApiClient()

    context = str(kube_context or "").strip() or None
    return config.new_client_from_config(context=context)


def _kubernetes_api_exception_message(exc: Exception) -> str:
    status = getattr(exc, "status", None)
    reason = getattr(exc, "reason", None)
    body = getattr(exc, "body", None)
    prefix = f"Kubernetes API returned {status}" if status else "Kubernetes API failed"
    if reason:
        prefix = f"{prefix}: {reason}"
    if body:
        return f"{prefix}\n{body}"
    return f"{prefix}: {exc}"


def _sanitize_kubernetes_resource(api_client, resource) -> dict:
    return api_client.sanitize_for_serialization(resource)


def _read_kubernetes_resource_with_client(
    *,
    kube_context: str,
    namespace: str,
    api_resource: str,
    resource_name: str,
) -> tuple[dict | None, str]:
    from kubernetes import client
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException

    try:
        api_client = _new_kubernetes_inspection_api_client(kube_context)
    except ConfigException as exc:
        return None, f"Kubernetes client configuration failed: {exc}"

    resource = _normalize_api_resource(api_resource)
    try:
        if resource == "deployment":
            obj = client.AppsV1Api(api_client).read_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
            )
        elif resource == "statefulset":
            obj = client.AppsV1Api(api_client).read_namespaced_stateful_set(
                name=resource_name,
                namespace=namespace,
            )
        elif resource == "daemonset":
            obj = client.AppsV1Api(api_client).read_namespaced_daemon_set(
                name=resource_name,
                namespace=namespace,
            )
        elif resource == "pod":
            obj = client.CoreV1Api(api_client).read_namespaced_pod(
                name=resource_name,
                namespace=namespace,
            )
        elif resource == "job":
            obj = client.BatchV1Api(api_client).read_namespaced_job(
                name=resource_name,
                namespace=namespace,
            )
        else:
            return None, f"Kubernetes client does not support api_resource [{api_resource}]."
    except ApiException as exc:
        return None, _kubernetes_api_exception_message(exc)

    return _sanitize_kubernetes_resource(api_client, obj), ""


def _list_kubernetes_resources_with_client(
    *,
    kube_context: str,
    namespace: str,
    api_resource: str,
    label_selector: str | None = None,
) -> tuple[list[dict], str]:
    from kubernetes import client
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException

    try:
        api_client = _new_kubernetes_inspection_api_client(kube_context)
    except ConfigException as exc:
        return [], f"Kubernetes client configuration failed: {exc}"

    resource = _normalize_api_resource(api_resource)
    kwargs = {"namespace": namespace}
    if label_selector:
        kwargs["label_selector"] = label_selector

    try:
        if resource == "deployment":
            listing = client.AppsV1Api(api_client).list_namespaced_deployment(**kwargs)
        elif resource == "statefulset":
            listing = client.AppsV1Api(api_client).list_namespaced_stateful_set(**kwargs)
        elif resource == "daemonset":
            listing = client.AppsV1Api(api_client).list_namespaced_daemon_set(**kwargs)
        elif resource == "pod":
            listing = client.CoreV1Api(api_client).list_namespaced_pod(**kwargs)
        elif resource == "job":
            listing = client.BatchV1Api(api_client).list_namespaced_job(**kwargs)
        else:
            return [], f"Kubernetes client does not support api_resource [{api_resource}]."
    except ApiException as exc:
        return [], _kubernetes_api_exception_message(exc)

    return [
        _sanitize_kubernetes_resource(api_client, item)
        for item in list(getattr(listing, "items", []) or [])
    ], ""


def get_kubernetes_resource_json(
    kube_context: str,
    namespace: str,
    api_resource: str,
    resource_name: str,
    request_timeout_seconds: int = 10,
) -> tuple[dict | None, str]:
    if _prefer_kubernetes_client():
        payload, message = _read_kubernetes_resource_with_client(
            kube_context=kube_context,
            namespace=namespace,
            api_resource=api_resource,
            resource_name=resource_name,
        )
        if _running_inside_kubernetes() or payload is not None:
            return payload, message

    args = [
        "kubectl",
        "--context",
        str(kube_context),
        "-n",
        str(namespace),
        "get",
        str(api_resource),
        str(resource_name),
        "-o",
        "json",
        f"--request-timeout={int(request_timeout_seconds)}s",
    ]
    proc = _run_cmd(args, check=False)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        return None, message or f"kubectl exited with code {proc.returncode}"

    try:
        return json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return None, f"could not parse kubectl {api_resource} JSON: {exc}"


def get_kubernetes_resources_json(
    kube_context: str,
    namespace: str,
    api_resource: str,
    resource_name: str | None = None,
    label_selector: str | None = None,
    request_timeout_seconds: int = 10,
) -> tuple[list[dict], str]:
    if resource_name:
        payload, message = get_kubernetes_resource_json(
            kube_context=kube_context,
            namespace=namespace,
            api_resource=api_resource,
            resource_name=resource_name,
            request_timeout_seconds=request_timeout_seconds,
        )
        if payload is None:
            return [], message
        return [payload], ""

    if _prefer_kubernetes_client():
        resources, message = _list_kubernetes_resources_with_client(
            kube_context=kube_context,
            namespace=namespace,
            api_resource=api_resource,
            label_selector=label_selector,
        )
        if _running_inside_kubernetes() or resources:
            return resources, message

    args = [
        "kubectl",
        "--context",
        str(kube_context),
        "-n",
        str(namespace),
        "get",
        str(api_resource),
        "-o",
        "json",
        f"--request-timeout={int(request_timeout_seconds)}s",
    ]
    if label_selector:
        args.extend(["-l", str(label_selector)])

    proc = _run_cmd(args, check=False)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        return [], message or f"kubectl exited with code {proc.returncode}"

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return [], f"could not parse kubectl {api_resource} list JSON: {exc}"

    return list(payload.get("items", [])), ""


def _optional_positive_int(value) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _kubernetes_workload_replicas_status(resource: dict[str, Any]) -> tuple[int, int, int, int | None, int | None]:
    spec = resource.get("spec") or {}
    status = resource.get("status") or {}
    desired = _positive_int(spec.get("replicas", status.get("replicas")))
    ready = _positive_int(status.get("readyReplicas"))
    available = _positive_int(status.get("availableReplicas"))
    observed_generation = _optional_positive_int(status.get("observedGeneration"))
    generation = _optional_positive_int((resource.get("metadata") or {}).get("generation"))
    return desired, ready, available or ready, observed_generation, generation


def inspect_kubernetes_workload_readiness(
    *,
    kube_context: str,
    namespace: str,
    api_resource: str,
    resource_name: str,
    request_timeout_seconds: int = 10,
) -> KubernetesWorkloadReadiness:
    payload, message = get_kubernetes_resource_json(
        kube_context=kube_context,
        namespace=namespace,
        api_resource=api_resource,
        resource_name=resource_name,
        request_timeout_seconds=request_timeout_seconds,
    )
    if payload is None:
        not_found = "NotFound" in message or "not found" in message.lower()
        return KubernetesWorkloadReadiness(
            state="needs_apply" if not_found else "unknown",
            ready=False,
            needs_apply=True,
            detail=message or f"Kubernetes {api_resource}/{resource_name} is unavailable.",
            kube_context=str(kube_context),
            namespace=str(namespace),
            api_resource=str(api_resource),
            resource_name=str(resource_name),
        )

    desired, ready, available, observed_generation, generation = _kubernetes_workload_replicas_status(payload)
    generation_ready = observed_generation is None or generation is None or observed_generation >= generation
    is_ready = desired > 0 and ready >= desired and available >= desired and generation_ready
    if is_ready:
        state = "ready"
        needs_apply = False
        detail = f"{ready}/{desired} replica(s) ready."
    elif desired > 0:
        state = "processing"
        needs_apply = False
        detail = f"{ready}/{desired} replica(s) ready."
    else:
        state = "needs_apply"
        needs_apply = True
        detail = "No desired replicas are active."

    return KubernetesWorkloadReadiness(
        state=state,
        ready=is_ready,
        needs_apply=needs_apply,
        detail=detail,
        kube_context=str(kube_context),
        namespace=str(namespace),
        api_resource=str(api_resource),
        resource_name=str(resource_name),
        desired_replicas=desired,
        ready_replicas=ready,
        available_replicas=available,
        observed_generation=observed_generation,
        generation=generation,
    )


def get_kubernetes_ingress_address(
    kube_context: str,
    namespace: str,
    ingress_name: str,
    request_timeout_seconds: int = 10,
) -> tuple[str, str]:
    payload, message = get_kubernetes_resource_json(
        kube_context=kube_context,
        namespace=namespace,
        api_resource="ingress",
        resource_name=ingress_name,
        request_timeout_seconds=request_timeout_seconds,
    )
    if payload is None:
        return "", message

    ingress_entries = payload.get("status", {}).get("loadBalancer", {}).get("ingress", [])
    for entry in ingress_entries:
        address = entry.get("hostname") or entry.get("ip")
        if address:
            return str(address), ""

    return "", "ingress exists, but no load balancer hostname has been assigned yet"


def wait_for_kubernetes_ingress_address(
    kube_context: str,
    namespace: str,
    ingress_name: str,
    timeout_seconds: int = 600,
    poll_interval_seconds: int = 15,
    request_timeout_seconds: int = 10,
) -> tuple[str, str]:
    deadline = monotonic() + int(timeout_seconds)
    poll_interval_seconds = max(1, int(poll_interval_seconds))
    last_message = ""

    while True:
        address, message = get_kubernetes_ingress_address(
            kube_context=kube_context,
            namespace=namespace,
            ingress_name=ingress_name,
            request_timeout_seconds=request_timeout_seconds,
        )
        if address:
            return address, ""

        last_message = message
        if monotonic() >= deadline:
            return "", last_message
        sleep(poll_interval_seconds)


def _plain_mapping(mapping) -> dict[str, str]:
    if mapping is None:
        return {}
    if hasattr(mapping, "as_plain_ordered_dict"):
        mapping = mapping.as_plain_ordered_dict()
    return {str(key): str(value) for key, value in dict(mapping).items()}


def _positive_int(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _kubernetes_resource_ref(resource: dict[str, Any]) -> str:
    kind = str(resource.get("kind", "resource")).lower()
    name = str(resource.get("metadata", {}).get("name", "unknown"))
    namespace = str(resource.get("metadata", {}).get("namespace", "default"))
    return f"{kind}/{name} in namespace [{namespace}]"


def kubernetes_workload_compute_summary(resource: dict[str, Any]) -> tuple[bool, str]:
    ref = _kubernetes_resource_ref(resource)
    kind = str(resource.get("kind", "")).lower()
    spec = resource.get("spec", {}) or {}
    status = resource.get("status", {}) or {}

    if kind == "pod":
        phase = str(status.get("phase", "Unknown"))
        active = phase not in {"Succeeded", "Failed"}
        return active, f"{ref} phase={phase}"

    if kind == "job":
        active = _positive_int(status.get("active")) > 0
        succeeded = _positive_int(status.get("succeeded"))
        failed = _positive_int(status.get("failed"))
        return active, f"{ref} active={_positive_int(status.get('active'))} succeeded={succeeded} failed={failed}"

    if kind == "daemonset":
        desired = _positive_int(status.get("desiredNumberScheduled"))
        ready = _positive_int(status.get("numberReady"))
        current = _positive_int(status.get("currentNumberScheduled"))
        return desired > 0 or ready > 0 or current > 0, (
            f"{ref} desired={desired} current={current} ready={ready}"
        )

    desired = _positive_int(spec.get("replicas", status.get("replicas")))
    observed_counts = [
        _positive_int(status.get(key))
        for key in [
            "replicas",
            "readyReplicas",
            "availableReplicas",
            "currentReplicas",
            "updatedReplicas",
        ]
    ]
    active_count = max([desired, *observed_counts])
    if any(key in status for key in ["replicas", "readyReplicas", "availableReplicas", "currentReplicas", "updatedReplicas"]):
        return active_count > 0, (
            f"{ref} desired={desired} observed={max(observed_counts)}"
        )

    return False, f"{ref} has no compute replica status"


def is_kubernetes_compute_active(
    kube_context: str,
    workloads,
    request_timeout_seconds: int = 10,
) -> tuple[bool, list[str]]:
    active_reasons: list[str] = []
    observed_reasons: list[str] = []

    for workload in workloads:
        workload_conf = _plain_mapping(workload)
        namespace = workload_conf["namespace"]
        api_resource = workload_conf["api_resource"]
        resource_name = workload_conf.get("resource_name") or workload_conf.get("name") or ""
        label_selector = workload_conf.get("label_selector") or ""
        display_name = workload_conf.get("display_name") or resource_name or label_selector or api_resource

        resources, message = get_kubernetes_resources_json(
            kube_context=kube_context,
            namespace=namespace,
            api_resource=api_resource,
            resource_name=resource_name or None,
            label_selector=label_selector or None,
            request_timeout_seconds=request_timeout_seconds,
        )
        if not resources:
            observed_reasons.append(
                f"{display_name}: no {api_resource} resources found in namespace [{namespace}]"
                + (f" ({message})" if message else "")
            )
            continue

        for resource in resources:
            active, reason = kubernetes_workload_compute_summary(resource)
            observed_reasons.append(reason)
            if active:
                active_reasons.append(reason)

    return bool(active_reasons), active_reasons or observed_reasons


def _find_aws_elbv2_load_balancer_by_dns(elbv2, dns_name: str) -> dict[str, Any]:
    paginator = elbv2.get_paginator("describe_load_balancers")
    for page in paginator.paginate():
        for load_balancer in page.get("LoadBalancers", []):
            if load_balancer.get("DNSName") == dns_name:
                return load_balancer
    raise RuntimeError(f"Could not find ELBv2 load balancer with DNS name [{dns_name}].")


def _find_aws_elbv2_listener_by_port(elbv2, load_balancer_arn: str, listener_port: int) -> dict[str, Any]:
    paginator = elbv2.get_paginator("describe_listeners")
    for page in paginator.paginate(LoadBalancerArn=load_balancer_arn):
        for listener in page.get("Listeners", []):
            if int(listener.get("Port", 0)) == int(listener_port):
                return listener
    raise RuntimeError(f"Could not find ELBv2 listener on port [{listener_port}] for [{load_balancer_arn}].")


def _rule_condition_values(rule: dict[str, Any], field: str, config_key: str) -> list[str]:
    values = []
    for condition in rule.get("Conditions", []):
        if condition.get("Field") != field:
            continue
        values.extend(str(value) for value in condition.get("Values", []))
        values.extend(str(value) for value in condition.get(config_key, {}).get("Values", []))
    return sorted(set(values))


def _aws_elbv2_rule_matches_host_path(rule: dict[str, Any], host: str, path: str) -> bool:
    host_values = _rule_condition_values(rule, "host-header", "HostHeaderConfig")
    if host and str(host) not in host_values:
        return False

    requested_path = str(path or "/")
    path_values = _rule_condition_values(rule, "path-pattern", "PathPatternConfig")
    if requested_path == "/":
        return not path_values or "/" in path_values or "/*" in path_values
    return requested_path in path_values or f"{requested_path.rstrip('/')}/*" in path_values


def _find_aws_elbv2_auth_rule(elbv2, listener_arn: str, host: str, path: str) -> dict[str, Any]:
    paginator = elbv2.get_paginator("describe_rules")
    fallback_rule = None
    for page in paginator.paginate(ListenerArn=listener_arn):
        for rule in page.get("Rules", []):
            if rule.get("IsDefault"):
                continue
            if not any(action.get("Type") == "authenticate-cognito" for action in rule.get("Actions", [])):
                continue
            if fallback_rule is None:
                fallback_rule = rule
            if _aws_elbv2_rule_matches_host_path(rule, host, path):
                return rule
    if fallback_rule is not None and not host:
        return fallback_rule
    raise RuntimeError(f"Could not find ELBv2 authenticate-cognito rule for host [{host}] and path [{path}].")


def configure_aws_alb_cognito_auth_request_extra_params(
    conf,
    kube_context: str,
    namespace: str,
    ingress_name: str,
    host: str,
    path: str = "/",
    request_extra_params=None,
    listener_port: int = 443,
    timeout_seconds: int = 600,
    poll_interval_seconds: int = 15,
) -> dict[str, Any] | None:
    request_extra_params = _plain_mapping(request_extra_params)
    if not request_extra_params:
        logging.info("No ALB Cognito auth request extra params configured for ingress [%s].", ingress_name)
        return None

    _quiet_aws_sdk_wire_logs()
    load_balancer_dns, message = wait_for_kubernetes_ingress_address(
        kube_context=kube_context,
        namespace=namespace,
        ingress_name=ingress_name,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    if not load_balancer_dns:
        raise RuntimeError(
            f"Cannot configure ALB Cognito auth request extra params for ingress [{ingress_name}]: {message}"
        )

    session = get_aws_session(conf)
    elbv2 = session.client("elbv2", region_name=_aws_region_from_conf(conf))
    load_balancer = _find_aws_elbv2_load_balancer_by_dns(elbv2, load_balancer_dns)
    listener = _find_aws_elbv2_listener_by_port(
        elbv2,
        load_balancer_arn=str(load_balancer["LoadBalancerArn"]),
        listener_port=listener_port,
    )
    rule = _find_aws_elbv2_auth_rule(
        elbv2,
        listener_arn=str(listener["ListenerArn"]),
        host=str(host or ""),
        path=str(path or "/"),
    )

    actions = rule.get("Actions", [])
    patched = False
    for action in actions:
        if action.get("Type") != "authenticate-cognito":
            continue
        auth_conf = action.setdefault("AuthenticateCognitoConfig", {})
        current_params = _plain_mapping(auth_conf.get("AuthenticationRequestExtraParams"))
        if current_params != request_extra_params:
            auth_conf["AuthenticationRequestExtraParams"] = request_extra_params
            patched = True

    if not patched:
        logging.info(
            "ALB Cognito auth request extra params already configured for rule [%s]: %s",
            rule.get("RuleArn"),
            request_extra_params,
        )
        return rule

    elbv2.modify_rule(RuleArn=rule["RuleArn"], Actions=actions)
    logging.info(
        "Configured ALB Cognito auth request extra params for rule [%s]: %s",
        rule.get("RuleArn"),
        request_extra_params,
    )
    return {
        "load_balancer_dns": load_balancer_dns,
        "load_balancer_arn": load_balancer.get("LoadBalancerArn"),
        "listener_arn": listener.get("ListenerArn"),
        "rule_arn": rule.get("RuleArn"),
        "authentication_request_extra_params": request_extra_params,
    }


def is_k3d_context(conf) -> bool:
    try:
        _ = _get_k3d_surface_conf(conf).cluster_name
        return True
    except Exception:
        return False


def _require_command(command_name: str) -> None:
    if not shutil.which(command_name):
        raise FileNotFoundError(
            f"Required command [{command_name}] is not installed or not visible in PATH."
        )


def _k3d_managed_registry_name(registry_name: str) -> str:
    return f"k3d-{registry_name}"


def _k3d_cluster_exists(cluster_name: str) -> bool:
    proc = _run_cmd(["k3d", "cluster", "list", cluster_name, "-o", "json"], check=False)
    return proc.returncode == 0 and proc.stdout.strip() not in ("", "[]", "null")


def _get_k3d_cluster(cluster_name: str) -> dict | None:
    proc = _run_cmd(["k3d", "cluster", "list", cluster_name, "-o", "json"], check=False)
    clusters = _parse_json_output(proc)
    if not clusters:
        return None
    return clusters[0]


def _k3d_cluster_healthy(cluster_name: str) -> bool:
    cluster = _get_k3d_cluster(cluster_name)
    if not cluster:
        return False

    for node in cluster.get("nodes", []):
        role = node.get("role", "")
        if role not in {"server", "loadbalancer"}:
            continue
        state = node.get("State", {})
        if state.get("Status") != "running":
            logging.warning(
                "k3d cluster [%s] is not healthy: node [%s] role [%s] has status [%s].",
                cluster_name,
                node.get("name"),
                role,
                state.get("Status"),
            )
            return False

    generated_context = f"{K3D}-{cluster_name}"
    if _kube_context_exists(generated_context):
        proc = _run_cmd(
            ["kubectl", "--context", generated_context, "get", "nodes", "-o", "name"],
            check=False,
        )
        node_names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode != 0 or not node_names:
            logging.warning(
                "k3d cluster [%s] is not healthy: generated context [%s] has no registered nodes yet.",
                cluster_name,
                generated_context,
            )
            return False

    return True


def _parse_json_output(proc: subprocess.CompletedProcess):
    if proc.returncode != 0 or proc.stdout.strip() in ("", "[]", "null"):
        return None
    return json.loads(proc.stdout)


def _parse_aws_eks_context(context_name: str) -> dict[str, str] | None:
    parts = str(context_name).split(":", 5)
    if len(parts) != 6:
        return None
    arn, partition, service, region, account_id, resource = parts
    if arn != "arn" or service != "eks" or not resource.startswith("cluster/"):
        return None
    cluster_name = resource.split("/", 1)[1]
    if not region or not account_id or not cluster_name:
        return None
    return {
        "partition": partition,
        "region": region,
        "account_id": account_id,
        "cluster_name": cluster_name,
    }


def _arg_value(args: list[str], flag_name: str) -> str | None:
    for index, arg in enumerate(args):
        if arg == flag_name and index + 1 < len(args):
            return str(args[index + 1])
        prefix = f"{flag_name}="
        if arg.startswith(prefix):
            return str(arg[len(prefix):])
    return None


def _conf_get(conf, key: str, default=None):
    if conf is None:
        return default
    if hasattr(conf, "get"):
        return conf.get(key, default)
    return getattr(conf, key, default)


def _quiet_aws_sdk_wire_logs() -> None:
    for logger_name in ["boto3", "botocore", "s3transfer", "urllib3"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _read_kubeconfig_context_contract(context_name: str) -> dict[str, Any] | None:
    if not context_name:
        return None

    proc = _run_cmd(["kubectl", "config", "view", "--raw", "-o", "json"], check=False)
    payload = _parse_json_output(proc)
    if not payload:
        return None

    contexts = {
        str(item.get("name")): item.get("context", {})
        for item in payload.get("contexts", [])
    }
    context = contexts.get(str(context_name))
    if context is None:
        return None

    clusters = {
        str(item.get("name")): item.get("cluster", {})
        for item in payload.get("clusters", [])
    }
    users = {
        str(item.get("name")): item.get("user", {})
        for item in payload.get("users", [])
    }
    cluster_name = str(context.get("cluster", ""))
    user_name = str(context.get("user", ""))

    return {
        "context_name": str(context_name),
        "cluster_name": cluster_name,
        "user_name": user_name,
        "context": context,
        "cluster": clusters.get(cluster_name, {}),
        "user": users.get(user_name, {}),
    }


def _aws_eks_details_from_kubeconfig_contract(context_contract: dict[str, Any] | None) -> dict[str, str] | None:
    if not context_contract:
        return None

    user = context_contract.get("user", {})
    exec_conf = user.get("exec", {})
    command = os.path.basename(str(exec_conf.get("command", "")))
    args = [str(arg) for arg in exec_conf.get("args", [])]
    if command != "aws" or "eks" not in args or "get-token" not in args:
        return None

    cluster_name = _arg_value(args, "--cluster-name") or _arg_value(args, "--cluster-id")
    region = _arg_value(args, "--region")
    details = {"surface": "aws_eks"}
    if cluster_name:
        details["cluster_name"] = cluster_name
    if region:
        details["region"] = region
    return details


def _aws_eks_details_from_context(context_name: str) -> dict[str, str] | None:
    eks_context = _parse_aws_eks_context(context_name)
    if eks_context:
        return {
            "surface": "aws_eks",
            "region": eks_context["region"],
            "account_id": eks_context["account_id"],
            "cluster_name": eks_context["cluster_name"],
        }
    return _aws_eks_details_from_kubeconfig_contract(
        _read_kubeconfig_context_contract(context_name)
    )


def _infer_kubernetes_surface_from_context(context_name: str) -> str | None:
    if not context_name:
        return None

    if _parse_aws_eks_context(context_name):
        return "aws_eks"

    context_contract = _read_kubeconfig_context_contract(context_name)
    if _aws_eks_details_from_kubeconfig_contract(context_contract):
        return "aws_eks"

    context_tokens = [
        str(context_name),
        str((context_contract or {}).get("cluster_name", "")),
        str((context_contract or {}).get("user_name", "")),
    ]
    if any(token.startswith("k3d-") for token in context_tokens):
        return "k3d"
    if any(token.startswith("kind-") for token in context_tokens):
        return "kind"
    if any(token.startswith("gke_") for token in context_tokens):
        return "gke"

    return None


def _aws_region_from_conf(conf, region: str | None = None) -> str:
    eks_context = _aws_eks_details_from_context(str(_conf_get(conf, "kube_context", "")))
    resolved_region = (
        region
        or (eks_context["region"] if eks_context else None)
        or _conf_get(conf, "aws_region")
        or _conf_get(conf, "aws_zone")
        or _conf_get(conf, "aws.region")
    )
    if not resolved_region:
        raise ValueError("AWS Kubernetes discovery requires aws_region, aws_zone, or aws.region.")
    return str(resolved_region)


def _infer_kubernetes_surface(conf) -> str:
    explicit_surface = (
        _conf_get(conf, "kubernetes_surface")
        or _conf_get(conf, "kubernetes.surface")
        or _conf_get(conf, "cloud_kubernetes.surface")
    )
    if explicit_surface:
        return str(explicit_surface)

    kube_context = str(_conf_get(conf, "kube_context", ""))
    context_surface = _infer_kubernetes_surface_from_context(kube_context)
    if context_surface:
        return context_surface

    surface = str(_conf_get(conf, "surface", "")).lower()
    if surface == "aws":
        return "aws_eks"
    if surface:
        return surface

    raise ValueError(
        "Cannot infer Kubernetes surface. Set `kubernetes_surface`, "
        "`kubernetes.surface`, or pass surface explicitly."
    )


def _raise_kubernetes_surface_not_implemented(surface: str):
    raise NotImplementedError(
        f"Kubernetes surface [{surface}] is not implemented for this kuber contract yet. "
        "Only AWS EKS is currently implemented."
    )


def _context_default_namespace(context_contract: dict[str, Any] | None) -> str:
    namespace = (context_contract or {}).get("context", {}).get("namespace")
    return str(namespace or "default")


def _context_cluster_token(context_name: str, context_contract: dict[str, Any] | None) -> str:
    cluster_name = str((context_contract or {}).get("cluster_name", ""))
    return cluster_name or str(context_name)


def _local_context_cluster_name(
    context_name: str,
    provider: str,
    context_contract: dict[str, Any] | None = None,
    conf=None,
) -> str:
    token = _context_cluster_token(context_name, context_contract)
    prefix = f"{provider}-"
    if str(token).startswith(prefix):
        return str(token)[len(prefix):]
    if str(context_name).startswith(prefix):
        return str(context_name)[len(prefix):]
    provider_conf = _conf_get(conf, provider)
    if provider_conf is not None and _conf_get(provider_conf, "cluster_name") is not None:
        return str(_conf_get(provider_conf, "cluster_name"))
    return str(token)


def _kube_context_handle_capabilities(provider: str) -> dict[str, bool]:
    return {
        "delete_cluster": provider in {"aws_eks", "kind", "k3d"},
        "delete_kubernetes_ingresses": provider == "aws_eks",
        "delete_eks_nodegroups": provider == "aws_eks",
        "delete_vpc_load_balancers": provider == "aws_eks",
        "wait_for_public_load_balancers": provider == "aws_eks",
        "delete_orphan_security_groups": provider == "aws_eks",
    }


def resolve_kube_context(
    context_name: str,
    conf=None,
) -> KubeContextHandle:
    context_name = str(context_name or "")
    if not context_name:
        raise RuntimeError("Cannot resolve empty Kubernetes context.")

    eks_context = _parse_aws_eks_context(context_name)
    context_contract = None if eks_context else _read_kubeconfig_context_contract(context_name)
    if eks_context:
        eks_details = {
            "surface": "aws_eks",
            "region": eks_context["region"],
            "account_id": eks_context["account_id"],
            "cluster_name": eks_context["cluster_name"],
        }
    else:
        eks_details = _aws_eks_details_from_kubeconfig_contract(context_contract)
    if eks_details:
        return KubeContextHandle(
            context_name=context_name,
            provider="aws_eks",
            runtime_surface="eks",
            cluster_name=str(eks_details.get("cluster_name", context_name)),
            namespace_default=_context_default_namespace(context_contract),
            region=eks_details.get("region"),
            account_id=eks_details.get("account_id"),
            capabilities=_kube_context_handle_capabilities("aws_eks"),
        )

    context_tokens = [
        context_name,
        str((context_contract or {}).get("cluster_name", "")),
        str((context_contract or {}).get("user_name", "")),
    ]

    if any(token.startswith("kind-") for token in context_tokens):
        return KubeContextHandle(
            context_name=context_name,
            provider="kind",
            runtime_surface="kind",
            cluster_name=_local_context_cluster_name(context_name, "kind", context_contract, conf=conf),
            namespace_default=_context_default_namespace(context_contract),
            capabilities=_kube_context_handle_capabilities("kind"),
        )

    if context_name == "k3d" or any(token.startswith("k3d-") for token in context_tokens):
        return KubeContextHandle(
            context_name=context_name,
            provider="k3d",
            runtime_surface="k3d",
            cluster_name=_local_context_cluster_name(context_name, "k3d", context_contract, conf=conf),
            namespace_default=_context_default_namespace(context_contract),
            capabilities=_kube_context_handle_capabilities("k3d"),
        )

    if any(token.startswith("gke_") for token in context_tokens):
        raise NotImplementedError(
            f"Kubernetes context [{context_name}] resolved to GKE, but GKE cluster delete routing is not implemented."
        )

    raise RuntimeError(
        f"Cannot resolve Kubernetes context [{context_name}] to a supported provider. "
        "Refusing to infer cluster delete behavior from ecosystem naming."
    )


def describe_aws_eks_cluster_contract(
    conf=None,
    cluster_name: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    _quiet_aws_sdk_wire_logs()

    if conf is None:
        raise ValueError("AWS EKS discovery requires resolved config so Wielder can use get_aws_session(conf).")

    eks_context = _aws_eks_details_from_context(str(_conf_get(conf, "kube_context", "")))
    resolved_cluster_name = cluster_name or (eks_context["cluster_name"] if eks_context else None) or _conf_get(conf, "kube_cluster_name")
    if not resolved_cluster_name:
        raise ValueError("AWS EKS discovery requires kube_cluster_name or cluster_name.")

    session = get_aws_session(conf)
    eks = session.client("eks", region_name=_aws_region_from_conf(conf, region=region))
    cluster = eks.describe_cluster(name=str(resolved_cluster_name))["cluster"]
    resources_vpc_config = cluster.get("resourcesVpcConfig", {})

    return {
        "surface": "aws_eks",
        "name": str(cluster.get("name", resolved_cluster_name)),
        "arn": cluster.get("arn"),
        "endpoint": cluster.get("endpoint"),
        "kubernetes_version": cluster.get("version"),
        "platform_version": cluster.get("platformVersion"),
        "status": cluster.get("status"),
        "vpc": {
            "id": resources_vpc_config.get("vpcId"),
            "subnet_ids": resources_vpc_config.get("subnetIds", []),
            "security_group_ids": resources_vpc_config.get("securityGroupIds", []),
            "cluster_security_group_id": resources_vpc_config.get("clusterSecurityGroupId"),
            "endpoint_public_access": resources_vpc_config.get("endpointPublicAccess"),
            "endpoint_private_access": resources_vpc_config.get("endpointPrivateAccess"),
            "public_access_cidrs": resources_vpc_config.get("publicAccessCidrs", []),
        },
    }


def describe_kubernetes_cluster_contract(
    conf,
    surface: str | None = None,
) -> dict[str, Any]:
    selected_surface = str(surface or _infer_kubernetes_surface(conf))

    match selected_surface:
        case "aws" | "aws_eks":
            return describe_aws_eks_cluster_contract(conf)
        case _:
            _raise_kubernetes_surface_not_implemented(selected_surface)


def require_kubernetes_cluster_vpc_id(
    cluster_contract: dict[str, Any],
    cluster_name: str,
) -> str:
    vpc_id = cluster_contract.get("vpc", {}).get("id")
    if not vpc_id:
        raise RuntimeError(f"Kubernetes cluster [{cluster_name}] did not report a VPC ID.")
    return str(vpc_id)


def get_aws_eks_load_balancer_contract(
    conf=None,
    cluster_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_cluster_contract = cluster_contract or describe_aws_eks_cluster_contract(conf)
    vpc_id = require_kubernetes_cluster_vpc_id(
        resolved_cluster_contract,
        cluster_name=str(resolved_cluster_contract.get("name", _conf_get(conf, "kube_cluster_name", ""))),
    )
    return {
        "surface": "aws_eks",
        "cluster_name": resolved_cluster_contract.get("name"),
        "vpc_id": vpc_id,
        "vpc": resolved_cluster_contract.get("vpc", {}),
    }


def get_kubernetes_load_balancer_contract(
    conf,
    surface: str | None = None,
    cluster_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_surface = str(
        surface
        or (cluster_contract or {}).get("surface")
        or _infer_kubernetes_surface(conf)
    )

    match selected_surface:
        case "aws" | "aws_eks":
            return get_aws_eks_load_balancer_contract(
                conf=conf,
                cluster_contract=cluster_contract,
            )
        case _:
            _raise_kubernetes_surface_not_implemented(selected_surface)


def _cluster_delete_operations(
    handle: KubeContextHandle,
    delete_infrastructure: bool,
    delete_kube_cluster: bool,
    kube_delete_surface_available: bool = True,
) -> list[str]:
    if not delete_infrastructure:
        return []
    if not delete_kube_cluster:
        return []
    if not handle.can("delete_cluster"):
        return []

    match handle.provider:
        case "aws_eks":
            operations = []
            if kube_delete_surface_available and handle.can("delete_kubernetes_ingresses"):
                operations.append("delete_kubernetes_ingresses")
            if handle.can("delete_eks_nodegroups"):
                operations.append("delete_eks_nodegroups")
            if handle.can("delete_vpc_load_balancers"):
                operations.append("delete_vpc_load_balancers")
            if handle.can("wait_for_public_load_balancers"):
                operations.append("wait_for_public_load_balancers")
            if handle.can("delete_orphan_security_groups"):
                operations.append("delete_orphan_security_groups")
            return operations
        case "kind" | "k3d":
            return ["delegate_local_cluster_delete_to_provisioner"]
        case _:
            return []


def plan_delete_cluster(
    handle: KubeContextHandle,
    delete_infrastructure: bool,
    delete_kube_cluster: bool,
    kube_delete_surface_available: bool = True,
) -> list[str]:
    operations = _cluster_delete_operations(
        handle=handle,
        delete_infrastructure=delete_infrastructure,
        delete_kube_cluster=delete_kube_cluster,
        kube_delete_surface_available=kube_delete_surface_available,
    )
    logging.info("Resolved Kubernetes context handle for delete: %s", handle.to_dict())
    logging.info(
        "Kubernetes cluster delete plan for context [%s]: %s",
        handle.context_name,
        ", ".join(operations) if operations else "no provider-specific cluster delete operations",
    )
    return operations


def delete_cluster(
    handle: KubeContextHandle,
    delete_infrastructure: bool,
    delete_kube_cluster: bool,
    kube_delete_surface_available: bool = True,
    aws_cred_role: str | None = None,
    wait: bool = True,
    dry_run: bool = False,
) -> None:
    operations = plan_delete_cluster(
        handle=handle,
        delete_infrastructure=delete_infrastructure,
        delete_kube_cluster=delete_kube_cluster,
        kube_delete_surface_available=kube_delete_surface_available,
    )
    if dry_run or not operations:
        return

    if not handle.can("delete_cluster"):
        raise NotImplementedError(
            f"Kubernetes context provider [{handle.provider}] does not support cluster delete routing."
        )

    match handle.provider:
        case "kind" | "k3d":
            logging.info(
                "No provider-specific destroy preflight is required for local Kubernetes context [%s]. "
                "Cluster deletion remains delegated to the configured provisioner.",
                handle.context_name,
            )
            return
        case "aws_eks":
            _delete_aws_eks_cluster_preflight(
                handle=handle,
                kube_delete_surface_available=kube_delete_surface_available,
                aws_cred_role=aws_cred_role,
                wait=wait,
            )
            return
        case _:
            raise NotImplementedError(
                f"Kubernetes context provider [{handle.provider}] delete routing is not implemented."
            )


def _delete_aws_eks_cluster_preflight(
    handle: KubeContextHandle,
    kube_delete_surface_available: bool,
    aws_cred_role: str | None = None,
    wait: bool = True,
) -> None:
    logging.info(
        "Running AWS EKS cluster destroy preflight for kube context [%s].",
        handle.context_name,
    )

    if kube_delete_surface_available:
        ingresses_deleted = delete_kubernetes_ingresses_for_cluster_delete(
            kube_context=handle.context_name,
            aws_cred_role=aws_cred_role,
        )
        if not ingresses_deleted:
            raise RuntimeError("Cluster destroy preflight could not delete all Kubernetes ingresses.")
    else:
        logging.info(
            "Skipping cluster-blocking ingress delete because kube context [%s] is absent. "
            "Cluster-scoped resources are already gone or unreachable.",
            handle.context_name,
        )

    nodegroups_deleted = delete_aws_eks_nodegroups_for_cluster_delete(
        context_name=handle.context_name,
        aws_cred_role=aws_cred_role,
    )
    if not nodegroups_deleted:
        raise RuntimeError("Cluster destroy preflight could not delete all EKS nodegroups.")

    load_balancers_deleted = delete_aws_eks_cluster_vpc_load_balancers_for_cluster_delete(
        context_name=handle.context_name,
        aws_cred_role=aws_cred_role,
    )
    if not load_balancers_deleted:
        raise RuntimeError("Cluster destroy preflight could not delete all ELBv2 load balancers in the cluster VPC.")

    if wait:
        public_addresses_unmapped = wait_for_aws_eks_cluster_vpc_public_addresses_unmapped(
            context_name=handle.context_name,
            aws_cred_role=aws_cred_role,
        )
        if not public_addresses_unmapped:
            raise RuntimeError("Cluster destroy preflight timed out waiting for mapped public addresses to clear.")

    orphan_security_groups_deleted = delete_aws_eks_cluster_vpc_orphan_security_groups_for_cluster_delete(
        context_name=handle.context_name,
        aws_cred_role=aws_cred_role,
    )
    if not orphan_security_groups_deleted:
        raise RuntimeError("Cluster destroy preflight could not delete all orphan security groups in the cluster VPC.")


def _is_aws_resource_not_found(exc) -> bool:
    response = getattr(exc, "response", {})
    error_code = response.get("Error", {}).get("Code")
    return error_code in {
        "ResourceNotFoundException",
        "NoSuchEntity",
        "InvalidVpcID.NotFound",
        "InvalidGroup.NotFound",
        "LoadBalancerNotFound",
    }


def _aws_eks_cluster_exists(context_name: str, aws_cred_role: str | None = None) -> bool:
    eks_context = _parse_aws_eks_context(context_name)
    if not eks_context:
        return False

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        logging.info(
            "Cannot inspect AWS EKS context [%s] with boto3 because boto3/botocore is unavailable: %s",
            context_name,
            exc,
        )
        return False

    try:
        session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(aws_cred_role)
        session = boto3.Session(**session_kwargs, region_name=eks_context["region"])
        response = session.client("eks").describe_cluster(name=eks_context["cluster_name"])
    except (BotoCoreError, ClientError) as exc:
        logging.info(
            "AWS EKS cluster backing kube context [%s] was not found or is not accessible through boto3: %s",
            context_name,
            exc,
        )
        return False

    cluster = response.get("cluster", {})
    logging.info(
        "AWS EKS cluster backing kube context [%s] exists with status [%s].",
        context_name,
        cluster.get("status", "unknown"),
    )
    return True


def _refresh_aws_eks_kube_context(context_name: str, aws_cred_role: str | None = None) -> bool:
    eks_context = _parse_aws_eks_context(context_name)
    if not eks_context:
        return False
    if not _aws_eks_cluster_exists(context_name, aws_cred_role=aws_cred_role):
        return False
    if not shutil.which("aws"):
        logging.info(
            "AWS EKS cluster [%s] exists, but aws CLI is not available to refresh kubeconfig.",
            eks_context["cluster_name"],
        )
        return False

    proc = _run_cmd(
        [
            "aws",
            "eks",
            "update-kubeconfig",
            "--region",
            eks_context["region"],
            "--name",
            eks_context["cluster_name"],
            "--alias",
            context_name,
        ],
        check=False,
        env=aws_mfa_cred_as_subprocess_env(aws_cred_role),
    )
    if proc.returncode != 0:
        logging.info(
            "aws eks update-kubeconfig failed for EKS context [%s]. stdout=[%s] stderr=[%s]",
            context_name,
            proc.stdout.strip(),
            proc.stderr.strip(),
        )
        return False

    logging.info("Refreshed local kubeconfig context [%s] from AWS EKS.", context_name)
    return True


def _kubectl_env_for_context(context_name: str, aws_cred_role: str | None = None) -> dict[str, str] | None:
    if not _parse_aws_eks_context(context_name):
        return None
    return aws_mfa_cred_as_subprocess_env(aws_cred_role)


def _local_kube_contexts() -> list[str] | None:
    proc = _run_cmd(["kubectl", "config", "get-contexts", "-o", "name"], check=False)
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def delete_kubernetes_ingresses_for_cluster_delete(
    kube_context: str,
    aws_cred_role: str | None = None,
    timeout_seconds: int = 180,
    poll_interval_seconds: int = 10,
) -> bool:
    env = _kubectl_env_for_context(kube_context, aws_cred_role=aws_cred_role)
    delete_proc = _run_cmd(
        [
            "kubectl",
            "--context",
            str(kube_context),
            "delete",
            "ingress",
            "--all",
            "--all-namespaces",
            "--ignore-not-found=true",
            "--wait=false",
        ],
        check=False,
        env=env,
    )
    if delete_proc.returncode != 0:
        logging.warning(
            "Could not delete Kubernetes ingresses before cluster destroy. stdout=[%s] stderr=[%s]",
            delete_proc.stdout.strip(),
            delete_proc.stderr.strip(),
        )
        return False

    deadline = monotonic() + int(timeout_seconds)
    poll_interval_seconds = max(1, int(poll_interval_seconds))
    while True:
        list_proc = _run_cmd(
            [
                "kubectl",
                "--context",
                str(kube_context),
                "get",
                "ingress",
                "--all-namespaces",
                "-o",
                "json",
            ],
            check=False,
            env=env,
        )
        if list_proc.returncode != 0:
            logging.warning(
                "Could not list Kubernetes ingresses while waiting for cluster destroy cleanup. stdout=[%s] stderr=[%s]",
                list_proc.stdout.strip(),
                list_proc.stderr.strip(),
            )
            return False
        payload = json.loads(list_proc.stdout or "{}")
        items = payload.get("items", [])
        if not items:
            logging.info("All Kubernetes ingresses are deleted for context [%s].", kube_context)
            return True
        _remove_deleting_ingress_finalizers_for_cluster_delete(
            kube_context=kube_context,
            ingress_items=items,
            env=env,
        )
        if monotonic() >= deadline:
            remaining = [
                f"{item.get('metadata', {}).get('namespace')}/{item.get('metadata', {}).get('name')}"
                for item in items
            ]
            logging.warning(
                "Timed out waiting for Kubernetes ingresses to delete before cluster destroy. Remaining: %s",
                ", ".join(remaining),
            )
            return False
        sleep(poll_interval_seconds)


def _remove_deleting_ingress_finalizers_for_cluster_delete(
    kube_context: str,
    ingress_items: list[dict],
    env: dict[str, str] | None,
) -> None:
    for item in ingress_items:
        metadata = item.get("metadata", {})
        finalizers = metadata.get("finalizers") or []
        if not metadata.get("deletionTimestamp") or not finalizers:
            continue

        namespace = metadata.get("namespace")
        name = metadata.get("name")
        if not namespace or not name:
            continue

        logging.warning(
            "Removing finalizers from deleting ingress [%s/%s] during cluster destroy: %s",
            namespace,
            name,
            ", ".join(finalizers),
        )
        _run_cmd(
            [
                "kubectl",
                "--context",
                str(kube_context),
                "-n",
                str(namespace),
                "patch",
                "ingress",
                str(name),
                "--type=merge",
                "-p",
                '{"metadata":{"finalizers":null}}',
            ],
            check=False,
            env=env,
        )


def delete_aws_eks_nodegroups_for_cluster_delete(
    context_name: str,
    aws_cred_role: str | None = None,
    timeout_seconds: int = 900,
    poll_interval_seconds: int = 20,
) -> bool:
    eks_context = _parse_aws_eks_context(context_name)
    if not eks_context:
        return False

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, WaiterError
    except ImportError as exc:
        logging.warning("Cannot delete EKS nodegroups before cluster destroy; boto3/botocore unavailable: %s", exc)
        return False

    try:
        session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(aws_cred_role)
        session = boto3.Session(**session_kwargs, region_name=eks_context["region"])
        eks = session.client("eks")
        nodegroups = eks.list_nodegroups(clusterName=eks_context["cluster_name"]).get("nodegroups", [])
    except ClientError as exc:
        if _is_aws_resource_not_found(exc):
            logging.info(
                "EKS cluster [%s] is already absent; no nodegroups remain.",
                eks_context["cluster_name"],
            )
            return True
        logging.warning(
            "Could not list EKS nodegroups before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False
    except (BotoCoreError, ClientError) as exc:
        logging.warning(
            "Could not list EKS nodegroups before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False

    if not nodegroups:
        logging.info("No EKS nodegroups remain for cluster [%s].", eks_context["cluster_name"])
        return True

    for nodegroup in nodegroups:
        try:
            logging.info(
                "Deleting EKS nodegroup [%s] before destroying cluster [%s].",
                nodegroup,
                eks_context["cluster_name"],
            )
            eks.delete_nodegroup(clusterName=eks_context["cluster_name"], nodegroupName=nodegroup)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "ResourceNotFoundException":
                continue
            logging.warning(
                "Could not request EKS nodegroup [%s] delete before cluster destroy: %s",
                nodegroup,
                exc,
            )
            return False

    waiter = eks.get_waiter("nodegroup_deleted")
    for nodegroup in nodegroups:
        try:
            waiter.wait(
                clusterName=eks_context["cluster_name"],
                nodegroupName=nodegroup,
                WaiterConfig={
                    "Delay": max(1, int(poll_interval_seconds)),
                    "MaxAttempts": max(1, int(timeout_seconds) // max(1, int(poll_interval_seconds))),
                },
            )
            logging.info("EKS nodegroup [%s] is deleted.", nodegroup)
        except WaiterError as exc:
            logging.warning(
                "Timed out waiting for EKS nodegroup [%s] to delete before cluster destroy: %s",
                nodegroup,
                exc,
            )
            return False

    return True


def wait_for_aws_eks_cluster_vpc_public_addresses_unmapped(
    context_name: str,
    aws_cred_role: str | None = None,
    timeout_seconds: int = 600,
    poll_interval_seconds: int = 20,
) -> bool:
    eks_context = _parse_aws_eks_context(context_name)
    if not eks_context:
        return False

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        logging.warning("Cannot inspect VPC public address mappings before cluster destroy; boto3/botocore unavailable: %s", exc)
        return False

    try:
        session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(aws_cred_role)
        session = boto3.Session(**session_kwargs, region_name=eks_context["region"])
        eks = session.client("eks")
        ec2 = session.client("ec2")
        cluster = eks.describe_cluster(name=eks_context["cluster_name"]).get("cluster", {})
        vpc_id = cluster.get("resourcesVpcConfig", {}).get("vpcId")
    except ClientError as exc:
        if _is_aws_resource_not_found(exc):
            logging.info(
                "EKS cluster [%s] is already absent; no VPC public address mappings remain.",
                eks_context["cluster_name"],
            )
            return True
        logging.warning(
            "Could not inspect EKS cluster VPC before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False
    except (BotoCoreError, ClientError) as exc:
        logging.warning(
            "Could not inspect EKS cluster VPC before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False

    if not vpc_id:
        logging.info("EKS cluster [%s] has no VPC id to inspect.", eks_context["cluster_name"])
        return True

    deadline = monotonic() + int(timeout_seconds)
    poll_interval_seconds = max(1, int(poll_interval_seconds))
    while True:
        try:
            response = ec2.describe_network_interfaces(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
            )
        except (BotoCoreError, ClientError) as exc:
            logging.warning("Could not inspect VPC [%s] public address mappings: %s", vpc_id, exc)
            return False

        mapped_interfaces = []
        for interface in response.get("NetworkInterfaces", []):
            public_ip = interface.get("Association", {}).get("PublicIp")
            if public_ip:
                mapped_interfaces.append(f"{interface.get('NetworkInterfaceId')}={public_ip}")

        if not mapped_interfaces:
            logging.info("No mapped public addresses remain in VPC [%s].", vpc_id)
            return True

        if monotonic() >= deadline:
            logging.warning(
                "Timed out waiting for mapped public addresses to clear from VPC [%s]. Remaining: %s",
                vpc_id,
                ", ".join(mapped_interfaces),
            )
            return False
        sleep(poll_interval_seconds)


def delete_aws_eks_cluster_vpc_load_balancers_for_cluster_delete(
    context_name: str,
    aws_cred_role: str | None = None,
    timeout_seconds: int = 600,
    poll_interval_seconds: int = 20,
) -> bool:
    eks_context = _parse_aws_eks_context(context_name)
    if not eks_context:
        return False

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, WaiterError
    except ImportError as exc:
        logging.warning("Cannot inspect VPC load balancers before cluster destroy; boto3/botocore unavailable: %s", exc)
        return False

    try:
        session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(aws_cred_role)
        session = boto3.Session(**session_kwargs, region_name=eks_context["region"])
        eks = session.client("eks")
        elbv2 = session.client("elbv2")
        cluster = eks.describe_cluster(name=eks_context["cluster_name"]).get("cluster", {})
        vpc_id = cluster.get("resourcesVpcConfig", {}).get("vpcId")
    except ClientError as exc:
        if _is_aws_resource_not_found(exc):
            logging.info(
                "EKS cluster [%s] is already absent; no cluster VPC load balancers remain.",
                eks_context["cluster_name"],
            )
            return True
        logging.warning(
            "Could not inspect EKS cluster VPC load balancers before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False
    except (BotoCoreError, ClientError) as exc:
        logging.warning(
            "Could not inspect EKS cluster VPC load balancers before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False

    if not vpc_id:
        return True

    try:
        paginator = elbv2.get_paginator("describe_load_balancers")
        load_balancers = []
        for page in paginator.paginate():
            load_balancers.extend(
                lb for lb in page.get("LoadBalancers", []) if lb.get("VpcId") == vpc_id
            )
    except (BotoCoreError, ClientError) as exc:
        logging.warning("Could not list ELBv2 load balancers for VPC [%s]: %s", vpc_id, exc)
        return False

    if not load_balancers:
        logging.info("No ELBv2 load balancers remain in VPC [%s].", vpc_id)
        return True

    for load_balancer in load_balancers:
        arn = load_balancer.get("LoadBalancerArn")
        name = load_balancer.get("LoadBalancerName")
        if not arn:
            continue
        try:
            logging.info("Deleting ELBv2 load balancer [%s] in VPC [%s] before cluster destroy.", name, vpc_id)
            elbv2.delete_load_balancer(LoadBalancerArn=arn)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "LoadBalancerNotFound":
                continue
            logging.warning("Could not delete ELBv2 load balancer [%s]: %s", name, exc)
            return False

    waiter = elbv2.get_waiter("load_balancers_deleted")
    for load_balancer in load_balancers:
        arn = load_balancer.get("LoadBalancerArn")
        name = load_balancer.get("LoadBalancerName")
        if not arn:
            continue
        try:
            waiter.wait(
                LoadBalancerArns=[arn],
                WaiterConfig={
                    "Delay": max(1, int(poll_interval_seconds)),
                    "MaxAttempts": max(1, int(timeout_seconds) // max(1, int(poll_interval_seconds))),
                },
            )
            logging.info("ELBv2 load balancer [%s] is deleted.", name)
        except WaiterError as exc:
            logging.warning("Timed out waiting for ELBv2 load balancer [%s] to delete: %s", name, exc)
            return False

    return True


def _is_cluster_destroy_orphan_security_group(security_group: dict) -> bool:
    group_name = str(security_group.get("GroupName", ""))
    description = str(security_group.get("Description", ""))
    if group_name == "default":
        return False
    if group_name.startswith("k8s-") and "[k8s]" in description and "LoadBalancer" in description:
        return True
    if group_name in {"ElasticMapReduce-master", "ElasticMapReduce-slave"}:
        return True
    return False


def delete_aws_eks_cluster_vpc_orphan_security_groups_for_cluster_delete(
    context_name: str,
    aws_cred_role: str | None = None,
    timeout_seconds: int = 300,
    poll_interval_seconds: int = 10,
) -> bool:
    eks_context = _parse_aws_eks_context(context_name)
    if not eks_context:
        return False

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        logging.warning("Cannot inspect VPC security groups before cluster destroy; boto3/botocore unavailable: %s", exc)
        return False

    try:
        session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(aws_cred_role)
        session = boto3.Session(**session_kwargs, region_name=eks_context["region"])
        eks = session.client("eks")
        ec2 = session.client("ec2")
        cluster = eks.describe_cluster(name=eks_context["cluster_name"]).get("cluster", {})
        vpc_id = cluster.get("resourcesVpcConfig", {}).get("vpcId")
    except ClientError as exc:
        if _is_aws_resource_not_found(exc):
            logging.info(
                "EKS cluster [%s] is already absent; no cluster VPC orphan security groups remain.",
                eks_context["cluster_name"],
            )
            return True
        logging.warning(
            "Could not inspect EKS cluster VPC security groups before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False
    except (BotoCoreError, ClientError) as exc:
        logging.warning(
            "Could not inspect EKS cluster VPC security groups before cluster destroy for [%s]: %s",
            context_name,
            exc,
        )
        return False

    if not vpc_id:
        return True

    deadline = monotonic() + int(timeout_seconds)
    poll_interval_seconds = max(1, int(poll_interval_seconds))
    while True:
        try:
            response = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
        except (BotoCoreError, ClientError) as exc:
            logging.warning("Could not list security groups for VPC [%s]: %s", vpc_id, exc)
            return False

        security_groups = [
            security_group
            for security_group in response.get("SecurityGroups", [])
            if _is_cluster_destroy_orphan_security_group(security_group)
        ]
        if not security_groups:
            logging.info("No cluster-destroy orphan security groups remain in VPC [%s].", vpc_id)
            return True

        blocked = []
        for security_group in security_groups:
            group_id = security_group.get("GroupId")
            group_name = security_group.get("GroupName")
            if not group_id:
                continue
            ingress_permissions = security_group.get("IpPermissions", [])
            if ingress_permissions:
                try:
                    logging.info(
                        "Revoking ingress rules from orphan security group [%s/%s] before VPC destroy.",
                        group_name,
                        group_id,
                    )
                    ec2.revoke_security_group_ingress(
                        GroupId=group_id,
                        IpPermissions=ingress_permissions,
                    )
                except ClientError as exc:
                    error_code = exc.response.get("Error", {}).get("Code")
                    if error_code not in {"InvalidPermission.NotFound", "InvalidGroup.NotFound"}:
                        logging.warning(
                            "Could not revoke ingress rules from orphan security group [%s/%s]: %s",
                            group_name,
                            group_id,
                            exc,
                        )
                        blocked.append(f"{group_name}/{group_id}")
                        continue

            try:
                logging.info("Deleting orphan security group [%s/%s] before VPC destroy.", group_name, group_id)
                ec2.delete_security_group(GroupId=group_id)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code == "InvalidGroup.NotFound":
                    continue
                logging.warning(
                    "Could not delete orphan security group [%s/%s] before VPC destroy: %s",
                    group_name,
                    group_id,
                    exc,
                )
                blocked.append(f"{group_name}/{group_id}")

        if not blocked:
            continue

        if monotonic() >= deadline:
            logging.warning(
                "Timed out deleting orphan security groups from VPC [%s]. Remaining: %s",
                vpc_id,
                ", ".join(blocked),
            )
            return False
        sleep(poll_interval_seconds)


def _list_k3d_registries() -> list[dict]:
    proc = _run_cmd(["k3d", "registry", "list", "-o", "json"], check=False)
    registries = _parse_json_output(proc)
    return registries or []


def _get_k3d_registry(registry_name: str) -> dict | None:
    managed_registry_name = _k3d_managed_registry_name(registry_name)
    for registry in _list_k3d_registries():
        if registry["name"] in (registry_name, managed_registry_name):
            return registry
    return None


def _k3d_registry_exists(registry_name: str) -> bool:
    return _get_k3d_registry(registry_name) is not None


def _k3d_registry_runtime_name(registry_name: str) -> str:
    registry = _get_k3d_registry(registry_name)
    if registry:
        return registry["name"]
    return _k3d_managed_registry_name(registry_name)


def _k3d_cluster_network_name(cluster_name: str) -> str:
    return f"{K3D}-{cluster_name}"


def _get_k3d_surface_conf(conf):
    return conf.k3d


def _docker_image_exists(image_ref: str) -> bool:
    proc = _run_cmd(["docker", "image", "inspect", image_ref], check=False)
    return proc.returncode == 0


def _docker_network_contains_container(network_name: str, container_name: str) -> bool:
    proc = _run_cmd(
        ["docker", "network", "inspect", network_name, "--format", "{{json .Containers}}"],
        check=False,
    )
    containers = _parse_json_output(proc)
    if not containers:
        return False
    return any(container["Name"] == container_name for container in containers.values())


def _ensure_k3d_registry_connected_to_cluster(cluster_name: str, registry_name: str) -> None:
    registry_runtime_name = _k3d_registry_runtime_name(registry_name)
    cluster_network_name = _k3d_cluster_network_name(cluster_name)

    if _docker_network_contains_container(cluster_network_name, registry_runtime_name):
        return

    _run_cmd(["docker", "network", "connect", cluster_network_name, registry_runtime_name])


def _kube_context_exists(
    context_name: str,
    require_reachable_cluster: bool = False,
    probe_namespace: str = "kube-system",
    request_timeout_seconds: int = 5,
    aws_cred_role: str | None = None,
) -> bool:
    try:
        contexts = _local_kube_contexts()
    except FileNotFoundError:
        logging.info("kubectl is not installed or not on PATH; treating kube context [%s] as unavailable.", context_name)
        return False
    if contexts is None:
        logging.info(
            "Could not list local kube contexts. Checking whether AWS EKS can refresh [%s].",
            context_name,
        )
        if not _refresh_aws_eks_kube_context(context_name, aws_cred_role=aws_cred_role):
            return False
        contexts = _local_kube_contexts()
        if contexts is None or context_name not in contexts:
            return False

    if context_name not in contexts:
        logging.info(
            "Kube context [%s] is not present in local kubeconfig. Checking whether AWS EKS can refresh it.",
            context_name,
        )
        if not _refresh_aws_eks_kube_context(context_name, aws_cred_role=aws_cred_role):
            return False
        contexts = _local_kube_contexts()
        if contexts is None or context_name not in contexts:
            logging.info(
                "Kube context [%s] is still unavailable after AWS EKS kubeconfig refresh.",
                context_name,
            )
            return False

    if not require_reachable_cluster:
        return True

    reachability_probe = _run_cmd(
        [
            "kubectl",
            "--context",
            context_name,
            "get",
            "namespace",
            probe_namespace,
            f"--request-timeout={int(request_timeout_seconds)}s",
        ],
        check=False,
    )
    if reachability_probe.returncode != 0:
        logging.info(
            "Kube context [%s] exists locally but the cluster is unreachable.",
            context_name,
        )
        if _refresh_aws_eks_kube_context(context_name, aws_cred_role=aws_cred_role):
            reachability_probe = _run_cmd(
                [
                    "kubectl",
                    "--context",
                    context_name,
                    "get",
                    "namespace",
                    probe_namespace,
                    f"--request-timeout={int(request_timeout_seconds)}s",
                ],
                check=False,
            )
            if reachability_probe.returncode == 0:
                return True
        return False

    return True


def _ensure_k3d_kube_context(conf) -> None:
    surface_conf = _get_k3d_surface_conf(conf)
    generated_context = f"{K3D}-{surface_conf.cluster_name}"
    if not _kube_context_exists(generated_context):
        logging.info(
            "k3d cluster [%s] exists, but generated kube context [%s] is not merged into the default kubeconfig. "
            "Merging it without switching the current kubectl context.",
            surface_conf.cluster_name,
            generated_context,
        )
        _run_cmd(
            [
                "k3d",
                "kubeconfig",
                "merge",
                surface_conf.cluster_name,
                "--kubeconfig-merge-default",
                "--kubeconfig-switch-context=false",
            ]
        )
        if not _kube_context_exists(generated_context):
            raise RuntimeError(
                f"k3d cluster [{surface_conf.cluster_name}] exists, but generated kube context [{generated_context}] "
                "is still unavailable after kubeconfig merge."
            )
    logging.info(
        "k3d generated kube context [%s] is available. Leaving current kubectl context untouched.",
        generated_context,
    )


def ensure_k3d_cluster_registry(conf, action: WieldAction = WieldAction.PLAN) -> None:
    if not is_k3d_context(conf):
        return

    surface_conf = _get_k3d_surface_conf(conf)
    _require_command("docker")
    _require_command("kubectl")
    _require_command("k3d")

    cluster_name = surface_conf.cluster_name
    registry_name = surface_conf.registry.name
    registry_host_port = str(surface_conf.registry.host_port)
    registry_create_spec = f"{registry_name}:0.0.0.0:{registry_host_port}"

    cluster_exists = _k3d_cluster_exists(cluster_name)
    cluster_healthy = _k3d_cluster_healthy(cluster_name) if cluster_exists else False
    registry_exists = _k3d_registry_exists(registry_name)
    registry_runtime_name = _k3d_registry_runtime_name(registry_name)

    if cluster_exists and not cluster_healthy:
        if action != WieldAction.APPLY:
            logging.info(
                "Plan k3d recovery: cluster [%s] exists but is unhealthy and would be recreated.",
                cluster_name,
            )
            return

        logging.warning(
            "k3d cluster [%s] exists but is unhealthy. Deleting it before bootstrap recovery.",
            cluster_name,
        )
        _run_cmd(["k3d", "cluster", "delete", cluster_name])
        cluster_exists = False
        registry_exists = _k3d_registry_exists(registry_name)
        registry_runtime_name = _k3d_registry_runtime_name(registry_name)

    if cluster_exists and registry_exists and cluster_healthy:
        _ensure_k3d_registry_connected_to_cluster(cluster_name, registry_name)
        _ensure_k3d_kube_context(conf)
        logging.info(
            "Hello from Wielder Kuber: k3d cluster [%s] and registry [%s] already exist. "
            "Continuing without bootstrap.",
            cluster_name,
            registry_runtime_name,
        )
        return

    if action != WieldAction.APPLY:
        logging.info(
            "Plan k3d bootstrap for cluster [%s] with registry [%s] exposed on host port [%s].",
            cluster_name,
            registry_runtime_name,
            registry_host_port,
        )
        return

    if not cluster_exists:
        if registry_exists:
            cluster_create_args = [
                "k3d",
                "cluster",
                "create",
                cluster_name,
                "--registry-use",
                registry_runtime_name,
            ]
        else:
            cluster_create_args = [
                "k3d",
                "cluster",
                "create",
                cluster_name,
                "--registry-create",
                registry_create_spec,
            ]

        _run_cmd(cluster_create_args)
    elif not registry_exists:
        _run_cmd(["k3d", "registry", "create", registry_name, "--port", registry_host_port])

    _ensure_k3d_registry_connected_to_cluster(cluster_name, registry_name)

    _ensure_k3d_kube_context(conf)
    logging.info(
        "k3d bootstrap complete. Active cluster is [%s], generated kube context is [%s], registry pull authority is [%s].",
        cluster_name,
        f"{K3D}-{cluster_name}",
        surface_conf.registry.pull_authority,
    )


def delete_k3d_registry(conf) -> None:

    surface_conf = _get_k3d_surface_conf(conf)
    _require_command("k3d")

    cluster_name = surface_conf.cluster_name
    registry_name = surface_conf.registry.name
    delete_registry = conf.get("delete_k3_registry", False)

    if delete_registry and _k3d_registry_exists(registry_name):
        _run_cmd(["k3d", "registry", "delete", _k3d_registry_runtime_name(registry_name)])
        logging.info("Deleted k3d registry [%s].", _k3d_registry_runtime_name(registry_name))
    elif delete_registry:
        logging.info("k3d registry [%s] does not exist. Nothing to delete.", _k3d_registry_runtime_name(registry_name))
    else:
        logging.info("Skipping k3d registry delete because delete_k3_registry is false.")


def delete_k3d_cluster(conf) -> None:
    if not is_k3d_context(conf):
        return

    surface_conf = _get_k3d_surface_conf(conf)
    _require_command("k3d")

    cluster_name = surface_conf.cluster_name
    delete_cluster = conf.get("delete_k3_cluster", False)

    if delete_cluster and _k3d_cluster_exists(cluster_name):
        _run_cmd(["k3d", "cluster", "delete", cluster_name])
        logging.info("Deleted k3d cluster [%s].", cluster_name)
    elif delete_cluster:
        logging.info("k3d cluster [%s] does not exist. Nothing to delete.", cluster_name)
    else:
        logging.info("Skipping k3d cluster delete because delete_k3_cluster is false.")



def delete_pvcs(context, namespace, partial_name):

    pvcs = get_kube_namespace_resources_by_type(context, namespace, 'pvc')

    for pvc in pvcs['items']:

        pvc_name = pvc['metadata']['name']

        if partial_name in pvc_name:

            _cmd = f"kubectl --context {context} -n {namespace} delete pvc {pvc_name};"
            logging.info(f'Running cmd\n{_cmd}')
            os.system(_cmd)


def get_pod_env_var_value(context, namespace, pod, var_name):

    reply = async_cmd(f'kubectl --context {context} exec -it -n {namespace} {pod} printenv')

    for var in reply:

        tup = var.split('=')

        if len(tup) > 1:
            logging.debug(f'{tup[0]}  :  {tup[1]}')

            if tup[0] == var_name:

                return tup[1]


def get_pod_actions(context, namespace, pod_name):

    report_path = '/tmp/actions/actions_report.yaml'

    _cmd = f'kubectl --context {context} exec -it -n {namespace} {pod_name} -- cat {report_path}'

    logging.debug(f'command is is:\n{_cmd}')

    reply = async_cmd(_cmd)

    logging.debug(f'Kubectl reply is:\n{reply}')

    actions = {}

    for ac in reply:

        try:
            action = yaml.safe_load(ac)
            actions.update(action)
        except Exception as e:
            logging.debug(str(e))
            logging.warning(f"List value {ac} can't be parsed as yaml")

    logging.debug(actions)

    return actions


def block_for_action(context, namespace, pod, var_name, expected_value, slumber=5, _max=10):
    """
    This method is a primitive polling mechanism to make sure a pod has completed an assignment.
    It assumes the pod has written a Yaml action to a file and attempts to read it.
    :param context: Kubernetes context
    :param namespace: Pod namespace
    :type namespace: str
    :param pod: The pod name
    :type pod: str
    :param var_name: action name
    :type var_name: str
    :param expected_value: the expected action value
    :type expected_value: str
    :param slumber: time to sleep between polling tries, defaults to 5
    :type slumber: int
    :param _max: Max polling attempts
    :type _max: int
    :return: if the ction value was as expected
    :rtype: bool
    """

    for i in range(_max):

        try:
            actions = get_pod_actions(context, namespace, pod)

            var_value = actions[var_name]

            logging.debug(f'var_name {var_name} value is: {var_value}, expected value: {expected_value}')

            if var_value is not None and var_value == expected_value:
                return True
            else:
                logging.info(f'var_name is {var_name} var_value is {var_value}')

        except Exception as e:
            logging.error("Error getting action from pod", e)

        logging.debug(f'sleeping {i} of {_max} for {slumber}')
        sleep(slumber)

    return False


def copy_file_to_pod(pod, src, pod_dest, namespace, context):

    _cmd = f'kubectl --context {context} cp -n {namespace} {src} {pod.metadata.name}:{pod_dest}'
    logging.info(_cmd)
    os.system(_cmd)


def copy_from_pod(pod_name, dest, pod_src, namespace, context):

    _cmd = f'kubectl --context {context} cp -n {namespace} {pod_name}:{pod_src} {dest}'
    logging.info(_cmd)
    os.system(_cmd)


def copy_file_to_pods(pods, src, pod_dest, namespace, context):
    for pod in pods:
        copy_file_to_pod(pod, src, pod_dest, namespace, context)


def send_command_to_pod(namespace, pod_name, context, command):
    logging.info(f'running command:\n{command}')
    os.system(f'kubectl exec --context {context} -n {namespace} {pod_name} -- {command}')


def send_command_to_pods(namespace, pods, context, command):
    for pod in pods:
        send_command_to_pod(namespace, pod.metadata.name, context, command)


def export_aws_cred_to_svc_pods(conf, service):

    namespace = service.plan.namespace
    kube_context = conf.kube_context

    _cmd = get_aws_mfa_cred_command(conf.cred_role)

    _cmd = f"bash -c 'cat > /etc/profile.d/02-aws-env.sh << EOF\n{_cmd}'"

    pods = get_pods(service.name, kube_context, False, namespace)

    send_command_to_pods(
        namespace=namespace,
        pods=pods,
        context=kube_context,
        command=_cmd
    )
