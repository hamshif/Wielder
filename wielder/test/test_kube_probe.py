from wielder.wield.enumerator import KubeResType
from wielder.wield.kube_probe import is_kube_set_ready


def test_is_kube_set_ready_accepts_ready_daemonset(monkeypatch):
    daemonset = {
        "metadata": {"name": "nvidia-device-plugin"},
        "status": {
            "desiredNumberScheduled": 1,
            "updatedNumberScheduled": 1,
            "numberReady": 1,
            "numberAvailable": 1,
        },
    }

    monkeypatch.setattr(
        "wielder.wield.kube_probe.get_kube_res_by_name",
        lambda context, namespace, kube_res, res_name: daemonset,
    )

    assert is_kube_set_ready(
        "k3d",
        "nvidia-device-plugin",
        KubeResType.DAEMON_SET.value,
        "nvidia-device-plugin",
    )


def test_is_kube_set_ready_rejects_incomplete_daemonset(monkeypatch):
    daemonset = {
        "metadata": {"name": "nvidia-device-plugin"},
        "status": {
            "desiredNumberScheduled": 1,
            "updatedNumberScheduled": 1,
            "numberReady": 0,
            "numberAvailable": 0,
        },
    }

    monkeypatch.setattr(
        "wielder.wield.kube_probe.get_kube_res_by_name",
        lambda context, namespace, kube_res, res_name: daemonset,
    )

    assert not is_kube_set_ready(
        "k3d",
        "nvidia-device-plugin",
        KubeResType.DAEMON_SET.value,
        "nvidia-device-plugin",
    )
