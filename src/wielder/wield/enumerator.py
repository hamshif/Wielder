from enum import Enum


class KubeResType(Enum):
    DEPLOY = 'deploy'
    POD = 'pod'
    STATEFUL = 'stateful'
    SERVICE = 'service'
    PV = 'pv'
    PVC = 'pvc'
    STORAGE = 'storage'


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
