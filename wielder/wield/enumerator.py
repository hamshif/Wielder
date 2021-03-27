from enum import Enum


class CloudProvider(Enum):
    GCP = 'gcp'
    AWS = 'aws'
    AZURE = 'azure'


class KubeResType(Enum):

    GENERAL = 'general'
    DEPLOY = 'deploy'
    POD = 'pod'
    STATEFUL_SET = 'statefulsets'
    SERVICE = 'service'
    PV = 'pv'
    PVC = 'pvc'
    STORAGE = 'storageclasses'


class PlanType(Enum):
    YAML = 'yaml'
    JSON = 'json'


class WieldAction(Enum):
    APPLY = 'apply'
    PLAN = 'plan'
    DELETE = 'delete'
    PROBE = 'probe'
    SHOW = 'show'


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
    INSTALL = 'install'
    UNINSTALL = 'uninstall'


class CredType(Enum):

    AWS_MFA = "aws_mfa"


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

    return converted


