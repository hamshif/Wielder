import logging
import os

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
