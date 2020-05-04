from enum import Enum


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
