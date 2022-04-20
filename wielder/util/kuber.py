import logging
import os
from time import sleep

import yaml
from wielder.util.commander import async_cmd
from wielder.util.credential_helper import get_aws_mfa_cred_command
from wielder.wield.deployer import get_pods
from wielder.wield.kube_probe import get_kube_namespace_resources_by_type


def update_eks_context(runtime_env, cred_profile, region, kube_cluster_name):

    if runtime_env == 'aws':
        context_cmd = f'aws eks --profile {cred_profile} --region {region} ' \
                      f'update-kubeconfig --name {kube_cluster_name};'

        logging.info(f'Running Kubernetes context change command:\n{context_cmd}')

        os.system(context_cmd)

    elif runtime_env == 'gcp':
        logging.warning("Gaining context for GCP hasn't been written")
    elif runtime_env == 'azure':
        logging.warning("Gaining context for Azure hasn't been written")


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
