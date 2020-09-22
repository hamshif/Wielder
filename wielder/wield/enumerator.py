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
    DELETE = 'delete'
    INIT = 'init'
    DESTROY = 'destroy'
    SHOW = 'show'


def wield_to_terraform(action):

    converted = TerraformAction.PLAN
    if action == WieldAction.APPLY:
        converted = TerraformAction.APPLY
    if action == WieldAction.DELETE:
        converted = TerraformAction.DESTROY

    return converted


