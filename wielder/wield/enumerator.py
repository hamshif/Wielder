from enum import Enum


class RuntimeEnv(Enum):
    """
    This class bears the same name as wielder enum, here it encompasses the differences between the local hardware and it's GUI.
    """

    LOCAL = 'local'
    MAC = 'mac'
    UBUNTU = 'ubuntu'
    DOCKER = 'docker'
    KIND = 'kind'
    AWS = 'aws'
    GCP = 'gcp'
    AZURE = 'azure'
    ON_PREM = 'on-prem'
    MINIKUBE = 'minikube'

    # TODO deprecate
    EXDOCKER = 'exdocker'


def get_runtime_by_value(value):
    for member in RuntimeEnv:
        if member.value == value:
            return member
    raise ValueError(f"No enum member with value {value} found.")


class CloudProvider(Enum):
    GCP = 'gcp'
    AWS = 'aws'
    AZURE = 'azure'


local_kubes = ['docker', 'kind', 'minikube']
local_runs = ['mac', 'ubuntu', 'exdocker']
local_deployments = local_runs + local_kubes + ['local']


class KubeResType(Enum):

    GENERAL = 'general'
    DEPLOY = 'deploy'
    POD = 'pod'
    STATEFUL_SET = 'statefulsets'
    SERVICE = 'service'
    PV = 'pv'
    PVC = 'pvc'
    STORAGE = 'storageclasses'
    JOBS = 'jobs'


class PlanType(Enum):
    YAML = 'yaml'
    JSON = 'json'


class WieldAction(Enum):
    APPLY = 'apply'
    PLAN = 'plan'
    DELETE = 'delete'
    PROBE = 'probe'
    SHOW = 'show'
    UPDATE = 'update'
    INIT = 'init'
    REFRESH = 'refresh'


class CodeLanguage(Enum):
    PYTHON = 'PYTHON'
    JAVA = 'JAVA'
    SCALA = 'SCALA'
    PERL = 'PERL'


class LanguageFramework(Enum):
    FLASK = 'FLASK'
    DJANGO = 'DJANGO'
    TORNADO = 'TORNADO'
    BOOT = 'BOOT'
    PLAY = 'PLAY'
    LAGOM = 'LAGOM'


class TerraformAction(Enum):
    APPLY = 'apply'
    PLAN = 'plan'
    INIT = 'init'
    DESTROY = 'destroy'
    SHOW = 'show'
    REFRESH = 'refresh'
    OUTPUT = 'output'


class TerraformReplyType(Enum):
    TEXT = 'text'
    JSON = 'json'


class HelmCommand(Enum):
    INIT_REPO = 'rep add'
    INSTALL = 'install'
    UNINSTALL = 'uninstall'
    UPGRADE = 'upgrade'
    NOTES = 'get notes'


class CredType(Enum):
    AWS_MFA = "aws_mfa"


class KubeJobStatus(Enum):
    COMPLETE = 'Complete'
    FAILED = 'Failed'


def wield_to_terraform(action):
    converted = None
    if action == WieldAction.PLAN:
        converted = TerraformAction.PLAN
    elif action == WieldAction.APPLY:
        converted = TerraformAction.APPLY
    elif action == WieldAction.DELETE:
        converted = TerraformAction.DESTROY
    elif action == WieldAction.PROBE:
        converted = TerraformAction.OUTPUT
    elif action == WieldAction.SHOW:
        converted = TerraformAction.SHOW
    elif action == WieldAction.INIT:
        converted = TerraformAction.INIT
    elif action == WieldAction.REFRESH:
        converted = TerraformAction.REFRESH

    return converted


def wield_to_helm(action):
    # todo add match-case
    converted = None
    if action == WieldAction.PLAN:
        converted = HelmCommand.NOTES
    elif action == WieldAction.APPLY:
        converted = HelmCommand.INSTALL
    elif action == WieldAction.DELETE:
        converted = HelmCommand.UNINSTALL
    elif action == WieldAction.UPDATE:
        converted = HelmCommand.UPGRADE
    elif action == WieldAction.INIT:
        converted = HelmCommand.INIT_REPO
    elif action == WieldAction.PROBE:
        # TODO
        pass
    elif action == WieldAction.SHOW:
        # TODO
        pass

    return converted
