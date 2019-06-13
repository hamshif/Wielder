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