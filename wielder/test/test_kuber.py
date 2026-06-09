import sys
from types import SimpleNamespace

import pytest

from wielder.util import kuber


def test_get_kubernetes_resource_json_builds_generic_get(monkeypatch):
    calls = []

    def fake_run_cmd(args, check=True, capture_output=True):
        calls.append((args, check, capture_output))
        return SimpleNamespace(
            returncode=0,
            stdout='{"kind":"Ingress","metadata":{"name":"workflow-wielder"}}',
            stderr="",
        )

    monkeypatch.setattr(kuber, "_run_cmd", fake_run_cmd)

    payload, message = kuber.get_kubernetes_resource_json(
        kube_context="ctx",
        namespace="workflow-wielder",
        api_resource="ingress",
        resource_name="workflow-wielder",
        request_timeout_seconds=7,
    )

    assert message == ""
    assert payload["kind"] == "Ingress"
    assert calls == [
        (
            [
                "kubectl",
                "--context",
                "ctx",
                "-n",
                "workflow-wielder",
                "get",
                "ingress",
                "workflow-wielder",
                "-o",
                "json",
                "--request-timeout=7s",
            ],
            False,
            True,
        )
    ]


def test_get_kubernetes_resource_json_uses_client_inside_cluster(monkeypatch):
    calls = []

    def fake_read_with_client(**kwargs):
        calls.append(kwargs)
        return (
            {
                "kind": "Deployment",
                "metadata": {"name": "model-binding"},
            },
            "",
        )

    monkeypatch.setattr(kuber, "_prefer_kubernetes_client", lambda: True)
    monkeypatch.setattr(kuber, "_running_inside_kubernetes", lambda: True)
    monkeypatch.setattr(kuber, "_read_kubernetes_resource_with_client", fake_read_with_client)
    monkeypatch.setattr(kuber, "_run_cmd", lambda *args, **kwargs: pytest.fail("kubectl should not run"))

    payload, message = kuber.get_kubernetes_resource_json(
        kube_context="arn:aws:eks:us-east-2:123:cluster/dev-webapps-core",
        namespace="model-binding",
        api_resource="deploy",
        resource_name="model-binding",
    )

    assert message == ""
    assert payload["kind"] == "Deployment"
    assert calls == [
        {
            "kube_context": "arn:aws:eks:us-east-2:123:cluster/dev-webapps-core",
            "namespace": "model-binding",
            "api_resource": "deploy",
            "resource_name": "model-binding",
        }
    ]


def test_kubernetes_client_resource_aliases_cover_runtime_workloads():
    assert kuber._normalize_api_resource("deploy") == "deployment"
    assert kuber._normalize_api_resource("deployments") == "deployment"
    assert kuber._normalize_api_resource("sts") == "statefulset"
    assert kuber._normalize_api_resource("statefulsets") == "statefulset"
    assert kuber._normalize_api_resource("pods") == "pod"
    assert kuber._normalize_api_resource("jobs") == "job"
    assert kuber._normalize_api_resource("daemonsets") == "daemonset"


def test_ensure_kubernetes_namespace_applies_dry_run_manifest(monkeypatch):
    calls = []

    def fake_run_cmd(args, check=True, capture_output=True, env=None, input_text=None):
        calls.append((args, check, capture_output, env, input_text))
        if args[3:5] == ["create", "namespace"]:
            return SimpleNamespace(returncode=0, stdout="kind: Namespace\nmetadata:\n  name: workflow-wielder\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(kuber, "_run_cmd", fake_run_cmd)

    kuber.ensure_kubernetes_namespace(
        kube_context="ctx",
        namespace="workflow-wielder",
        env={"KUBECONFIG": "/tmp/kubeconfig"},
    )

    assert calls == [
        (
            [
                "kubectl",
                "--context",
                "ctx",
                "create",
                "namespace",
                "workflow-wielder",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            True,
            True,
            {"KUBECONFIG": "/tmp/kubeconfig"},
            None,
        ),
        (
            [
                "kubectl",
                "--context",
                "ctx",
                "apply",
                "-f",
                "-",
            ],
            True,
            True,
            {"KUBECONFIG": "/tmp/kubeconfig"},
            "kind: Namespace\nmetadata:\n  name: workflow-wielder\n",
        ),
    ]


def test_delete_kubernetes_pod_path_by_label_execs_running_pod(monkeypatch):
    calls = []

    def fake_run_cmd(args, check=True, capture_output=True, env=None, input_text=None):
        calls.append((args, check, capture_output))
        if args[5:7] == ["get", "pod"]:
            return SimpleNamespace(
                returncode=0,
                stdout='{"items":[{"metadata":{"name":"pod-1"},"status":{"phase":"Running"}}]}',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(kuber, "_run_cmd", fake_run_cmd)

    pod_name = kuber.delete_kubernetes_pod_path_by_label(
        kube_context="ctx",
        namespace="ns",
        label_selector="app=worker",
        pod_path="/mnt/bucket/prefix",
    )

    assert pod_name == "pod-1"
    assert calls == [
        (
            [
                "kubectl",
                "--context",
                "ctx",
                "-n",
                "ns",
                "get",
                "pod",
                "-l",
                "app=worker",
                "-o",
                "json",
            ],
            False,
            True,
        ),
        (
            [
                "kubectl",
                "--context",
                "ctx",
                "-n",
                "ns",
                "exec",
                "pod-1",
                "--",
                "rm",
                "-rf",
                "--",
                "/mnt/bucket/prefix",
            ],
            True,
            True,
        ),
    ]


@pytest.mark.parametrize("pod_path", ["", "/", "relative/path", "/mnt/../etc/passwd", "\\bad"])
def test_delete_kubernetes_pod_path_by_label_rejects_unsafe_path(monkeypatch, pod_path):
    monkeypatch.setattr(kuber, "_run_cmd", lambda *args, **kwargs: pytest.fail("kubectl should not run"))

    with pytest.raises(ValueError):
        kuber.delete_kubernetes_pod_path_by_label(
            kube_context="ctx",
            namespace="ns",
            label_selector="app=worker",
            pod_path=pod_path,
        )


def test_get_kubernetes_ingress_address_reads_hostname(monkeypatch):
    def fake_resource_json(**kwargs):
        return (
            {
                "status": {
                    "loadBalancer": {
                        "ingress": [
                            {
                                "hostname": "example-alb.us-east-1.elb.amazonaws.com",
                            }
                        ]
                    }
                }
            },
            "",
        )

    monkeypatch.setattr(kuber, "get_kubernetes_resource_json", fake_resource_json)

    address, message = kuber.get_kubernetes_ingress_address(
        kube_context="ctx",
        namespace="workflow-wielder",
        ingress_name="workflow-wielder",
    )

    assert message == ""
    assert address == "example-alb.us-east-1.elb.amazonaws.com"


def test_kubernetes_workload_compute_summary_detects_active_deployment():
    active, reason = kuber.kubernetes_workload_compute_summary(
        {
            "kind": "Deployment",
            "metadata": {"name": "model-binding", "namespace": "model-binding"},
            "spec": {"replicas": 1},
            "status": {"replicas": 1, "readyReplicas": 1},
        }
    )

    assert active is True
    assert "deployment/model-binding" in reason
    assert "desired=1" in reason


def test_kubernetes_workload_compute_summary_treats_scaled_down_statefulset_as_inactive():
    active, reason = kuber.kubernetes_workload_compute_summary(
        {
            "kind": "StatefulSet",
            "metadata": {"name": "mmseqs-sequence-alignment-deploy", "namespace": "model-binding"},
            "spec": {"replicas": 0},
            "status": {"replicas": 0, "readyReplicas": 0},
        }
    )

    assert active is False
    assert "statefulset/mmseqs-sequence-alignment-deploy" in reason


def test_inspect_kubernetes_workload_readiness_detects_ready_rollout(monkeypatch):
    monkeypatch.setattr(
        kuber,
        "get_kubernetes_resource_json",
        lambda **kwargs: (
            {
                "metadata": {"generation": 3},
                "spec": {"replicas": 1},
                "status": {
                    "observedGeneration": 3,
                    "readyReplicas": 1,
                    "availableReplicas": 1,
                },
            },
            "",
        ),
    )

    readiness = kuber.inspect_kubernetes_workload_readiness(
        kube_context="ctx",
        namespace="model-binding",
        api_resource="statefulset",
        resource_name="mmseqs-sequence-alignment-deploy",
        request_timeout_seconds=5,
    )

    assert readiness.state == "ready"
    assert readiness.ready is True
    assert readiness.needs_apply is False
    assert readiness.desired_replicas == 1
    assert readiness.ready_replicas == 1
    assert readiness.detail == "1/1 replica(s) ready."


def test_inspect_kubernetes_workload_readiness_marks_missing_resource_as_needs_apply(monkeypatch):
    monkeypatch.setattr(
        kuber,
        "get_kubernetes_resource_json",
        lambda **kwargs: (None, 'Error from server (NotFound): statefulsets.apps "worker" not found'),
    )

    readiness = kuber.inspect_kubernetes_workload_readiness(
        kube_context="ctx",
        namespace="model-binding",
        api_resource="statefulset",
        resource_name="worker",
    )

    assert readiness.state == "needs_apply"
    assert readiness.ready is False
    assert readiness.needs_apply is True
    assert "not found" in readiness.detail


def test_wait_for_kubernetes_ingress_address_returns_last_pending_message(monkeypatch):
    calls = []

    def fake_ingress_address(**kwargs):
        calls.append(kwargs)
        return "", "ingress exists, but no load balancer hostname has been assigned yet"

    monkeypatch.setattr(kuber, "get_kubernetes_ingress_address", fake_ingress_address)
    monkeypatch.setattr(kuber, "sleep", lambda seconds: None)
    monkeypatch.setattr(kuber, "monotonic", iter([0, 2]).__next__)

    address, message = kuber.wait_for_kubernetes_ingress_address(
        kube_context="ctx",
        namespace="workflow-wielder",
        ingress_name="workflow-wielder",
        timeout_seconds=1,
        poll_interval_seconds=1,
    )

    assert address == ""
    assert message == "ingress exists, but no load balancer hostname has been assigned yet"
    assert len(calls) == 1


def test_configure_aws_alb_cognito_auth_request_extra_params_patches_rule(monkeypatch):
    calls = []

    class FakePaginator:
        def __init__(self, service_name):
            self.service_name = service_name

        def paginate(self, **kwargs):
            calls.append(("paginate", self.service_name, kwargs))
            if self.service_name == "describe_load_balancers":
                return [
                    {
                        "LoadBalancers": [
                            {
                                "DNSName": "alb.example.elb.amazonaws.com",
                                "LoadBalancerArn": "lb-arn",
                            }
                        ]
                    }
                ]
            if self.service_name == "describe_listeners":
                return [
                    {
                        "Listeners": [
                            {
                                "Port": 443,
                                "ListenerArn": "listener-arn",
                            }
                        ]
                    }
                ]
            if self.service_name == "describe_rules":
                return [
                    {
                        "Rules": [
                            {
                                "RuleArn": "rule-arn",
                                "IsDefault": False,
                                "Conditions": [
                                    {
                                        "Field": "host-header",
                                        "HostHeaderConfig": {"Values": ["dev.internal.example.com"]},
                                    },
                                    {
                                        "Field": "path-pattern",
                                        "PathPatternConfig": {"Values": ["/*"]},
                                    },
                                ],
                                "Actions": [
                                    {
                                        "Type": "authenticate-cognito",
                                        "Order": 1,
                                        "AuthenticateCognitoConfig": {
                                            "UserPoolArn": "pool-arn",
                                            "UserPoolClientId": "client-id",
                                            "UserPoolDomain": "domain",
                                        },
                                    },
                                    {
                                        "Type": "forward",
                                        "Order": 2,
                                        "TargetGroupArn": "tg-arn",
                                    },
                                ],
                            }
                        ]
                    }
                ]
            raise AssertionError(self.service_name)

    class FakeElbv2:
        def get_paginator(self, service_name):
            return FakePaginator(service_name)

        def modify_rule(self, **kwargs):
            calls.append(("modify_rule", kwargs))

    class FakeSession:
        def client(self, service_name, region_name=None):
            calls.append(("client", service_name, region_name))
            assert service_name == "elbv2"
            return FakeElbv2()

    monkeypatch.setattr(
        kuber,
        "wait_for_kubernetes_ingress_address",
        lambda **kwargs: ("alb.example.elb.amazonaws.com", ""),
    )
    monkeypatch.setattr(kuber, "get_aws_session", lambda conf: FakeSession())

    result = kuber.configure_aws_alb_cognito_auth_request_extra_params(
        conf=SimpleNamespace(kube_context="arn:aws:eks:us-east-2:123:cluster/dev"),
        kube_context="arn:aws:eks:us-east-2:123:cluster/dev",
        namespace="webapps",
        ingress_name="domain-datalake-web",
        host="dev.internal.example.com",
        request_extra_params={"prompt": "login"},
    )

    assert result["rule_arn"] == "rule-arn"
    assert ("client", "elbv2", "us-east-2") in calls
    modify_calls = [call for call in calls if call[0] == "modify_rule"]
    assert len(modify_calls) == 1
    auth_action = modify_calls[0][1]["Actions"][0]
    assert auth_action["AuthenticateCognitoConfig"]["AuthenticationRequestExtraParams"] == {
        "prompt": "login"
    }


def test_parse_aws_eks_context_reads_cluster_arn():
    parsed = kuber._parse_aws_eks_context(
        "arn:aws:eks:us-east-2:123456789012:cluster/dev--aws_model_binding--gid--default_conf--0"
    )

    assert parsed == {
        "partition": "aws",
        "region": "us-east-2",
        "account_id": "123456789012",
        "cluster_name": "dev--aws_model_binding--gid--default_conf--0",
    }


def test_describe_kubernetes_cluster_contract_switches_to_aws_eks(monkeypatch):
    calls = []

    def fake_aws_eks_contract(conf):
        calls.append(conf)
        return {
            "surface": "aws_eks",
            "name": "cluster-a",
            "vpc": {
                "id": "vpc-123",
            },
        }

    monkeypatch.setattr(kuber, "describe_aws_eks_cluster_contract", fake_aws_eks_contract)

    contract = kuber.describe_kubernetes_cluster_contract(SimpleNamespace(surface="aws"))

    assert contract["surface"] == "aws_eks"
    assert contract["vpc"]["id"] == "vpc-123"
    assert len(calls) == 1


def test_kubernetes_surface_prefers_kube_context_over_surface(monkeypatch):
    calls = []

    def fake_aws_eks_contract(conf):
        calls.append(conf)
        return {
            "surface": "aws_eks",
            "name": "cluster-from-context",
            "vpc": {
                "id": "vpc-123",
            },
        }

    monkeypatch.setattr(kuber, "describe_aws_eks_cluster_contract", fake_aws_eks_contract)

    contract = kuber.describe_kubernetes_cluster_contract(
        SimpleNamespace(
            surface="docker",
            kube_context="arn:aws:eks:us-east-2:123:cluster/cluster-from-context",
        )
    )

    assert contract["surface"] == "aws_eks"
    assert len(calls) == 1


def test_kubernetes_surface_infers_aws_eks_from_kubeconfig_exec(monkeypatch):
    calls = []

    def fake_aws_eks_contract(conf):
        calls.append(conf)
        return {
            "surface": "aws_eks",
            "name": "cluster-from-exec",
            "vpc": {
                "id": "vpc-123",
            },
        }

    monkeypatch.setattr(kuber, "describe_aws_eks_cluster_contract", fake_aws_eks_contract)
    monkeypatch.setattr(
        kuber,
        "_read_kubeconfig_context_contract",
        lambda context_name: {
            "context_name": context_name,
            "cluster_name": "cluster-from-exec",
            "user_name": "cluster-from-exec",
            "user": {
                "exec": {
                    "command": "aws",
                    "args": [
                        "eks",
                        "get-token",
                        "--region",
                        "us-east-2",
                        "--cluster-name",
                        "cluster-from-exec",
                    ],
                }
            },
        },
    )

    contract = kuber.describe_kubernetes_cluster_contract(
        SimpleNamespace(
            surface="docker",
            kube_context="cluster-alias",
        )
    )

    assert contract["surface"] == "aws_eks"
    assert len(calls) == 1


def test_describe_aws_eks_cluster_contract_reads_vpc_contract(monkeypatch):
    calls = []

    class FakeEks:
        def describe_cluster(self, name):
            calls.append(("describe_cluster", name))
            return {
                "cluster": {
                    "name": name,
                    "arn": "arn:aws:eks:us-east-2:123:cluster/cluster-a",
                    "endpoint": "https://example.eks.amazonaws.com",
                    "version": "1.33",
                    "platformVersion": "eks.38",
                    "status": "ACTIVE",
                    "resourcesVpcConfig": {
                        "vpcId": "vpc-123",
                        "subnetIds": ["subnet-1"],
                        "securityGroupIds": ["sg-1"],
                        "clusterSecurityGroupId": "sg-cluster",
                        "endpointPublicAccess": True,
                        "endpointPrivateAccess": False,
                        "publicAccessCidrs": ["0.0.0.0/0"],
                    },
                }
            }

    class FakeSession:
        def client(self, service_name, region_name=None):
            calls.append(("client", service_name, region_name))
            return FakeEks()

    monkeypatch.setattr(
        kuber,
        "get_aws_session",
        lambda conf: FakeSession(),
    )

    contract = kuber.describe_aws_eks_cluster_contract(
        SimpleNamespace(
            kube_cluster_name="cluster-a",
            aws_region="us-east-2",
        )
    )

    assert contract["surface"] == "aws_eks"
    assert contract["name"] == "cluster-a"
    assert contract["vpc"]["id"] == "vpc-123"
    assert contract["vpc"]["subnet_ids"] == ["subnet-1"]
    assert kuber.require_kubernetes_cluster_vpc_id(contract, cluster_name="cluster-a") == "vpc-123"
    assert calls == [
        ("client", "eks", "us-east-2"),
        ("describe_cluster", "cluster-a"),
    ]


def test_describe_aws_eks_cluster_contract_reads_region_and_name_from_context(monkeypatch):
    calls = []

    class FakeEks:
        def describe_cluster(self, name):
            calls.append(("describe_cluster", name))
            return {
                "cluster": {
                    "name": name,
                    "resourcesVpcConfig": {
                        "vpcId": "vpc-123",
                    },
                }
            }

    class FakeSession:
        def client(self, service_name, region_name=None):
            calls.append(("client", service_name, region_name))
            return FakeEks()

    monkeypatch.setattr(kuber, "get_aws_session", lambda conf: FakeSession())

    contract = kuber.describe_aws_eks_cluster_contract(
        SimpleNamespace(
            aws_region="us-east-1",
            kube_context="arn:aws:eks:us-east-2:123:cluster/cluster-from-context",
        )
    )

    assert contract["name"] == "cluster-from-context"
    assert contract["vpc"]["id"] == "vpc-123"
    assert calls == [
        ("client", "eks", "us-east-2"),
        ("describe_cluster", "cluster-from-context"),
    ]


def test_describe_aws_eks_cluster_contract_reads_region_and_name_from_kubeconfig_exec(monkeypatch):
    calls = []

    class FakeEks:
        def describe_cluster(self, name):
            calls.append(("describe_cluster", name))
            return {
                "cluster": {
                    "name": name,
                    "resourcesVpcConfig": {
                        "vpcId": "vpc-123",
                    },
                }
            }

    class FakeSession:
        def client(self, service_name, region_name=None):
            calls.append(("client", service_name, region_name))
            return FakeEks()

    monkeypatch.setattr(kuber, "get_aws_session", lambda conf: FakeSession())
    monkeypatch.setattr(
        kuber,
        "_read_kubeconfig_context_contract",
        lambda context_name: {
            "context_name": context_name,
            "cluster_name": "cluster-from-exec",
            "user_name": "cluster-from-exec",
            "user": {
                "exec": {
                    "command": "/usr/bin/aws",
                    "args": [
                        "eks",
                        "get-token",
                        "--region=us-east-2",
                        "--cluster-name=cluster-from-exec",
                    ],
                }
            },
        },
    )

    contract = kuber.describe_aws_eks_cluster_contract(
        SimpleNamespace(
            aws_region="us-east-1",
            kube_context="cluster-alias",
        )
    )

    assert contract["name"] == "cluster-from-exec"
    assert contract["vpc"]["id"] == "vpc-123"
    assert calls == [
        ("client", "eks", "us-east-2"),
        ("describe_cluster", "cluster-from-exec"),
    ]


def test_get_kubernetes_load_balancer_contract_reuses_cluster_contract():
    contract = kuber.get_kubernetes_load_balancer_contract(
        SimpleNamespace(surface="aws"),
        cluster_contract={
            "surface": "aws_eks",
            "name": "cluster-a",
            "vpc": {
                "id": "vpc-123",
                "subnet_ids": ["subnet-1"],
            },
        },
    )

    assert contract == {
        "surface": "aws_eks",
        "cluster_name": "cluster-a",
        "vpc_id": "vpc-123",
        "vpc": {
            "id": "vpc-123",
            "subnet_ids": ["subnet-1"],
        },
    }


def test_kubernetes_cluster_contract_is_not_implemented_for_non_eks_surfaces():
    with pytest.raises(NotImplementedError, match="Only AWS EKS"):
        kuber.describe_kubernetes_cluster_contract(SimpleNamespace(surface="k3d"))

    with pytest.raises(NotImplementedError, match="Only AWS EKS"):
        kuber.get_kubernetes_load_balancer_contract(SimpleNamespace(surface="kind"))


def test_resolve_kube_context_identifies_kind_context(monkeypatch):
    monkeypatch.setattr(kuber, "_read_kubeconfig_context_contract", lambda context_name: None)

    handle = kuber.resolve_kube_context("kind-kind-hybrid")

    assert handle.provider == "kind"
    assert handle.runtime_surface == "kind"
    assert handle.cluster_name == "kind-hybrid"
    assert handle.can("delete_cluster") is True
    assert handle.can("delete_eks_nodegroups") is False


def test_resolve_kube_context_identifies_aws_eks_context(monkeypatch):
    monkeypatch.setattr(kuber, "_read_kubeconfig_context_contract", lambda context_name: None)

    handle = kuber.resolve_kube_context(
        "arn:aws:eks:us-east-2:123456789012:cluster/dev-cluster"
    )

    assert handle.provider == "aws_eks"
    assert handle.runtime_surface == "eks"
    assert handle.cluster_name == "dev-cluster"
    assert handle.region == "us-east-2"
    assert handle.account_id == "123456789012"
    assert handle.can("delete_eks_nodegroups") is True


def test_resolve_kube_context_unknown_fails_closed(monkeypatch):
    monkeypatch.setattr(kuber, "_read_kubeconfig_context_contract", lambda context_name: None)

    with pytest.raises(RuntimeError, match="Refusing to infer cluster delete behavior"):
        kuber.resolve_kube_context("mystery-context")


def test_delete_cluster_kind_never_calls_eks_cleanup(monkeypatch):
    def fail_eks_cleanup(**_kwargs):
        raise AssertionError("kind delete routing must not call EKS cleanup")

    monkeypatch.setattr(kuber, "delete_kubernetes_ingresses_for_cluster_delete", fail_eks_cleanup)
    monkeypatch.setattr(kuber, "delete_aws_eks_nodegroups_for_cluster_delete", fail_eks_cleanup)
    monkeypatch.setattr(kuber, "delete_aws_eks_cluster_vpc_load_balancers_for_cluster_delete", fail_eks_cleanup)
    monkeypatch.setattr(kuber, "wait_for_aws_eks_cluster_vpc_public_addresses_unmapped", fail_eks_cleanup)
    monkeypatch.setattr(kuber, "delete_aws_eks_cluster_vpc_orphan_security_groups_for_cluster_delete", fail_eks_cleanup)

    kuber.delete_cluster(
        handle=kuber.KubeContextHandle(
            context_name="kind-kind-hybrid",
            provider="kind",
            runtime_surface="kind",
            cluster_name="kind-hybrid",
            capabilities={
                "delete_cluster": True,
                "delete_eks_nodegroups": False,
            },
        ),
        delete_infrastructure=True,
        delete_kube_cluster=True,
    )


def test_delete_cluster_eks_runs_eks_preflight(monkeypatch):
    calls = []

    def fake_ingress(**kwargs):
        calls.append(("ingress", kwargs["kube_context"], kwargs["aws_cred_role"]))
        return True

    def fake_nodegroups(**kwargs):
        calls.append(("nodegroups", kwargs["context_name"], kwargs["aws_cred_role"]))
        return True

    def fake_load_balancers(**kwargs):
        calls.append(("load_balancers", kwargs["context_name"], kwargs["aws_cred_role"]))
        return True

    def fake_public_addresses(**kwargs):
        calls.append(("public_addresses", kwargs["context_name"], kwargs["aws_cred_role"]))
        return True

    def fake_security_groups(**kwargs):
        calls.append(("security_groups", kwargs["context_name"], kwargs["aws_cred_role"]))
        return True

    monkeypatch.setattr(kuber, "delete_kubernetes_ingresses_for_cluster_delete", fake_ingress)
    monkeypatch.setattr(kuber, "delete_aws_eks_nodegroups_for_cluster_delete", fake_nodegroups)
    monkeypatch.setattr(kuber, "delete_aws_eks_cluster_vpc_load_balancers_for_cluster_delete", fake_load_balancers)
    monkeypatch.setattr(kuber, "wait_for_aws_eks_cluster_vpc_public_addresses_unmapped", fake_public_addresses)
    monkeypatch.setattr(kuber, "delete_aws_eks_cluster_vpc_orphan_security_groups_for_cluster_delete", fake_security_groups)

    context_name = "arn:aws:eks:us-east-2:123456789012:cluster/dev-cluster"
    kuber.delete_cluster(
        handle=kuber.KubeContextHandle(
            context_name=context_name,
            provider="aws_eks",
            runtime_surface="eks",
            cluster_name="dev-cluster",
            region="us-east-2",
            account_id="123456789012",
            capabilities={
                "delete_cluster": True,
                "delete_kubernetes_ingresses": True,
                "delete_eks_nodegroups": True,
                "delete_vpc_load_balancers": True,
                "wait_for_public_load_balancers": True,
                "delete_orphan_security_groups": True,
            },
        ),
        delete_infrastructure=True,
        delete_kube_cluster=True,
        aws_cred_role="cli-mfa-role",
    )

    assert calls == [
        ("ingress", context_name, "cli-mfa-role"),
        ("nodegroups", context_name, "cli-mfa-role"),
        ("load_balancers", context_name, "cli-mfa-role"),
        ("public_addresses", context_name, "cli-mfa-role"),
        ("security_groups", context_name, "cli-mfa-role"),
    ]


def test_kube_context_exists_refreshes_missing_aws_eks_context(monkeypatch):
    context_name = "arn:aws:eks:us-east-2:123456789012:cluster/dev-cluster"
    local_context_calls = []
    refreshed = []

    def fake_local_contexts():
        local_context_calls.append(True)
        if len(local_context_calls) == 1:
            return ["kind-kind"]
        return ["kind-kind", context_name]

    def fake_refresh(missing_context_name, aws_cred_role=None):
        refreshed.append(missing_context_name)
        return True

    monkeypatch.setattr(kuber, "_local_kube_contexts", fake_local_contexts)
    monkeypatch.setattr(kuber, "_refresh_aws_eks_kube_context", fake_refresh)

    assert kuber._kube_context_exists(context_name) is True
    assert refreshed == [context_name]
    assert len(local_context_calls) == 2


def test_kube_context_exists_refreshes_unreachable_aws_eks_context(monkeypatch):
    context_name = "arn:aws:eks:us-east-2:123456789012:cluster/dev-cluster"
    refresh_calls = []
    run_calls = []

    def fake_run_cmd(args, check=True, capture_output=True):
        run_calls.append(args)
        if len(run_calls) == 1:
            return SimpleNamespace(returncode=1, stdout="", stderr="stale endpoint")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_refresh(missing_context_name, aws_cred_role=None):
        refresh_calls.append(missing_context_name)
        return True

    monkeypatch.setattr(kuber, "_local_kube_contexts", lambda: [context_name])
    monkeypatch.setattr(kuber, "_refresh_aws_eks_kube_context", fake_refresh)
    monkeypatch.setattr(kuber, "_run_cmd", fake_run_cmd)

    assert kuber._kube_context_exists(context_name, require_reachable_cluster=True) is True
    assert refresh_calls == [context_name]
    assert len(run_calls) == 2


def test_delete_kubernetes_ingresses_for_cluster_delete_deletes_all_namespaces(monkeypatch):
    calls = []

    def fake_run_cmd(args, check=True, capture_output=True, env=None):
        calls.append((args, check, capture_output, env))
        if args[3:6] == ["delete", "ingress", "--all"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout='{"items":[]}', stderr="")

    monkeypatch.setattr(kuber, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(kuber, "_kubectl_env_for_context", lambda context_name, aws_cred_role=None: {"AWS_ACCESS_KEY_ID": "x"})

    assert kuber.delete_kubernetes_ingresses_for_cluster_delete(
        kube_context="arn:aws:eks:us-east-2:123:cluster/dev",
        aws_cred_role="cli-mfa-role",
    )

    assert calls[0][0] == [
        "kubectl",
        "--context",
        "arn:aws:eks:us-east-2:123:cluster/dev",
        "delete",
        "ingress",
        "--all",
        "--all-namespaces",
        "--ignore-not-found=true",
        "--wait=false",
    ]
    assert calls[1][0] == [
        "kubectl",
        "--context",
        "arn:aws:eks:us-east-2:123:cluster/dev",
        "get",
        "ingress",
        "--all-namespaces",
        "-o",
        "json",
    ]
    assert calls[0][3] == {"AWS_ACCESS_KEY_ID": "x"}


def test_delete_kubernetes_ingresses_for_cluster_delete_removes_deleting_finalizers(monkeypatch):
    calls = []
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(
                returncode=0,
                stdout=(
                    '{"items":[{"metadata":{"namespace":"workflow-wielder","name":"workflow-wielder",'
                    '"deletionTimestamp":"2026-05-28T19:49:55Z","finalizers":["ingress.k8s.aws/resources"]}}]}'
                ),
                stderr="",
            ),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout='{"items":[]}', stderr=""),
        ]
    )

    def fake_run_cmd(args, check=True, capture_output=True, env=None):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(kuber, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(kuber, "sleep", lambda seconds: None)

    assert kuber.delete_kubernetes_ingresses_for_cluster_delete(kube_context="ctx")
    assert [
        "kubectl",
        "--context",
        "ctx",
        "-n",
        "workflow-wielder",
        "patch",
        "ingress",
        "workflow-wielder",
        "--type=merge",
        "-p",
        '{"metadata":{"finalizers":null}}',
    ] in calls


def test_delete_aws_eks_nodegroups_for_cluster_delete_deletes_and_waits(monkeypatch):
    calls = []

    class FakeWaiter:
        def wait(self, **kwargs):
            calls.append(("wait", kwargs))

    class FakeEks:
        def list_nodegroups(self, clusterName):
            calls.append(("list", clusterName))
            return {"nodegroups": ["ng-a", "ng-b"]}

        def delete_nodegroup(self, clusterName, nodegroupName):
            calls.append(("delete", clusterName, nodegroupName))

        def get_waiter(self, waiter_name):
            calls.append(("waiter", waiter_name))
            return FakeWaiter()

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("session", kwargs))

        def client(self, service_name):
            calls.append(("client", service_name))
            return FakeEks()

    monkeypatch.setattr(kuber, "aws_mfa_cred_as_boto3_session_kwargs", lambda role: {"aws_access_key_id": "x"})
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=FakeSession))

    assert kuber.delete_aws_eks_nodegroups_for_cluster_delete(
        context_name="arn:aws:eks:us-east-2:123:cluster/dev",
        aws_cred_role="cli-mfa-role",
        timeout_seconds=40,
        poll_interval_seconds=20,
    )

    assert calls == [
        ("session", {"aws_access_key_id": "x", "region_name": "us-east-2"}),
        ("client", "eks"),
        ("list", "dev"),
        ("delete", "dev", "ng-a"),
        ("delete", "dev", "ng-b"),
        ("waiter", "nodegroup_deleted"),
        (
            "wait",
            {
                "clusterName": "dev",
                "nodegroupName": "ng-a",
                "WaiterConfig": {"Delay": 20, "MaxAttempts": 2},
            },
        ),
        (
            "wait",
            {
                "clusterName": "dev",
                "nodegroupName": "ng-b",
                "WaiterConfig": {"Delay": 20, "MaxAttempts": 2},
            },
        ),
    ]


def test_wait_for_aws_eks_cluster_vpc_public_addresses_unmapped(monkeypatch):
    calls = []

    class FakeEks:
        def describe_cluster(self, name):
            calls.append(("describe_cluster", name))
            return {"cluster": {"resourcesVpcConfig": {"vpcId": "vpc-123"}}}

    class FakeEc2:
        def describe_network_interfaces(self, Filters):
            calls.append(("describe_network_interfaces", Filters))
            return {"NetworkInterfaces": [{"NetworkInterfaceId": "eni-1"}]}

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("session", kwargs))

        def client(self, service_name):
            calls.append(("client", service_name))
            if service_name == "eks":
                return FakeEks()
            if service_name == "ec2":
                return FakeEc2()
            raise AssertionError(service_name)

    monkeypatch.setattr(kuber, "aws_mfa_cred_as_boto3_session_kwargs", lambda role: {"aws_access_key_id": "x"})
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=FakeSession))

    assert kuber.wait_for_aws_eks_cluster_vpc_public_addresses_unmapped(
        context_name="arn:aws:eks:us-east-2:123:cluster/dev",
        aws_cred_role="cli-mfa-role",
        timeout_seconds=1,
    )

    assert calls == [
        ("session", {"aws_access_key_id": "x", "region_name": "us-east-2"}),
        ("client", "eks"),
        ("client", "ec2"),
        ("describe_cluster", "dev"),
        ("describe_network_interfaces", [{"Name": "vpc-id", "Values": ["vpc-123"]}]),
    ]


def test_delete_aws_eks_cluster_vpc_orphan_security_groups_revokes_and_deletes(monkeypatch):
    calls = []
    emr_ingress = [
        {
            "IpProtocol": "tcp",
            "FromPort": 0,
            "ToPort": 65535,
            "UserIdGroupPairs": [{"GroupId": "sg-emr-master"}],
        }
    ]

    class FakeEks:
        def describe_cluster(self, name):
            calls.append(("describe_cluster", name))
            return {"cluster": {"resourcesVpcConfig": {"vpcId": "vpc-123"}}}

    class FakeEc2:
        def __init__(self):
            self.describe_calls = 0

        def describe_security_groups(self, Filters):
            calls.append(("describe_security_groups", Filters))
            self.describe_calls += 1
            if self.describe_calls > 1:
                return {"SecurityGroups": [{"GroupId": "sg-default", "GroupName": "default"}]}
            return {
                "SecurityGroups": [
                    {"GroupId": "sg-default", "GroupName": "default"},
                    {
                        "GroupId": "sg-k8s",
                        "GroupName": "k8s-workspace",
                        "Description": "[k8s] Managed SecurityGroup for LoadBalancer",
                        "IpPermissions": [],
                    },
                    {
                        "GroupId": "sg-emr-master",
                        "GroupName": "ElasticMapReduce-master",
                        "Description": "Master group for Elastic MapReduce",
                        "IpPermissions": emr_ingress,
                    },
                ]
            }

        def revoke_security_group_ingress(self, **kwargs):
            calls.append(("revoke", kwargs))

        def delete_security_group(self, **kwargs):
            calls.append(("delete", kwargs))

    fake_ec2 = FakeEc2()

    class FakeSession:
        def __init__(self, **kwargs):
            calls.append(("session", kwargs))

        def client(self, service_name):
            calls.append(("client", service_name))
            if service_name == "eks":
                return FakeEks()
            if service_name == "ec2":
                return fake_ec2
            raise AssertionError(service_name)

    monkeypatch.setattr(kuber, "aws_mfa_cred_as_boto3_session_kwargs", lambda role: {"aws_access_key_id": "x"})
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=FakeSession))

    assert kuber.delete_aws_eks_cluster_vpc_orphan_security_groups_for_cluster_delete(
        context_name="arn:aws:eks:us-east-2:123:cluster/dev",
        aws_cred_role="cli-mfa-role",
    )

    assert ("delete", {"GroupId": "sg-k8s"}) in calls
    assert ("revoke", {"GroupId": "sg-emr-master", "IpPermissions": emr_ingress}) in calls
    assert ("delete", {"GroupId": "sg-emr-master"}) in calls
