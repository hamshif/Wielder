#!/usr/bin/env python
import json
import logging
import os
import random
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from wielder.util.commander import async_cmd, subprocess_cmd as _cmd, subprocess_cmd
from wielder.util.kuber import update_kubernetes_context
from wielder.util.log_util import setup_logging
from wielder.util.templater import config_to_terraform
from wielder.util.credential_helper import (
    aws_mfa_cred_as_boto3_session_kwargs,
    get_aws_mfa_cred_command,
)
from wielder.util.util import DirContext
from wielder.wield.enumerator import TerraformAction, TerraformReplyType, CredType, WieldAction, wield_to_terraform


class WrapTerraform:

    def __init__(self, root_path, run_dir, conf):
        """
        Wraps terraform commands in context (directory, credentials ....),
        Its tightly coupled with hocon configuration tree
        This is a work in progress, use with caution in complex situations
        :param root_path: The path to the terraform root
        :type root_path: str
        :param conf config tree
        :type conf: hocon config
        """

        self.root_path = root_path
        self.run_dir = run_dir
        self.run_path = f'{root_path}/{run_dir}'
        self.conf = conf

        self.backend_root = conf.backend_root
        self.backend_name = conf.backend_name
        self.backend_tree = conf.backend
        self.tfvars = conf.tfvars
        self._initial_tfvars_aws_profile = self._get_conf_string(self.tfvars, "aws_profile")
        self.state_backend_bootstrap_run_dir = getattr(conf, "state_backend_bootstrap_run_dir", None)
        self.state_backend_bootstrap_conf = getattr(conf, "state_backend_bootstrap_conf", None)

        self.verbose = conf.verbose

        cred_type = None

        try:
            cred_type = CredType(conf.cred_type)
            self.cred_role = conf.cred_role
        except Exception as e:
            logging.warning(f"{e}\nno CLI credential type is being used")

        self.cred_type = cred_type
        self._backend_backup_paths = []

    @staticmethod
    def _get_conf_string(conf, key: str, default: str = "") -> str:
        if conf is None:
            return default
        try:
            if key in conf:
                return str(conf[key])
        except Exception:
            pass
        value = getattr(conf, key, default)
        return default if value is None else str(value)

    def _terraform_aws_profile(self) -> str:
        cred_profile = self._get_conf_string(self.conf, "cred_profile")
        if cred_profile:
            return cred_profile
        current_tfvars_profile = self._get_conf_string(self.tfvars, "aws_profile")
        if current_tfvars_profile:
            return current_tfvars_profile
        return self._initial_tfvars_aws_profile

    def _terraform_provisions_aws_eks(self) -> bool:
        if self._get_conf_string(self.conf, "runtime_env") != "aws":
            return False
        if self.tfvars is None:
            return False
        try:
            if "create_eks" in self.tfvars:
                return bool(self.tfvars.create_eks)
        except Exception:
            pass
        try:
            if "provision_resources" in self.tfvars:
                return "eks" in {str(resource) for resource in self.tfvars.provision_resources}
        except Exception:
            pass
        return False

    def _update_kubernetes_context_after_eks_apply(self) -> None:
        if not self._terraform_provisions_aws_eks():
            return

        region = self._get_conf_string(self.tfvars, "aws_region")
        kube_cluster_name = self._get_conf_string(self.conf, "kube_cluster_name")
        if not kube_cluster_name:
            kube_cluster_name = self._get_conf_string(self.tfvars, "cluster_name")
        if not region or not kube_cluster_name:
            raise RuntimeError("Cannot update EKS kube context without aws_region and kube_cluster_name.")

        aws_cred_role = self.cred_role if self.cred_type == CredType.AWS_MFA else None
        update_kubernetes_context(
            "aws",
            self._terraform_aws_profile(),
            region,
            kube_cluster_name,
            context_alias=self._get_conf_string(self.conf, "kube_context"),
            aws_cred_role=aws_cred_role,
        )

    def _terraform_env_prefix(self) -> str:
        tfenv_root = Path(os.environ.get("TFENV_ROOT", str(Path.home() / ".tfenv")))
        if not (tfenv_root / "bin" / "terraform").exists() and not (tfenv_root / "bin" / "tfenv").exists():
            return ""
        return f'export TFENV_ROOT="{tfenv_root}";\nexport PATH="$TFENV_ROOT/bin:$PATH";\n'

    def _aws_default_env_prefix(self) -> str:
        if self.cred_type != CredType.AWS_DEFAULT:
            return ""
        if self.tfvars is None or "aws_profile" not in self.tfvars:
            return ""

        aws_profile = str(self.tfvars.aws_profile).strip()
        if not aws_profile:
            return ""

        quoted_profile = shlex.quote(aws_profile)
        return (
            f"export AWS_PROFILE={quoted_profile};\n"
            f"export AWS_DEFAULT_PROFILE={quoted_profile};\n"
        )

    def _require_terraform_binary(self, t_cmd: str) -> None:
        if "terraform" not in str(t_cmd).split():
            return
        if shutil.which("terraform"):
            return
        raise RuntimeError(
            "Terraform is required for this Wielder infrastructure action but was not found on PATH.\n"
            "Install it with:\n"
            "  <workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only terraform\n"
            "Then verify with:\n"
            "  terraform version"
        )

    def _backend_bucket_exists(self):
        if self.backend_tree is None or "bucket" not in self.backend_tree:
            return True

        bucket_name = str(self.backend_tree.bucket)
        t_cmd = f'aws s3api head-bucket --bucket "{bucket_name}"'
        log_cmd = t_cmd

        if self.cred_type == CredType.AWS_MFA:
            cmd_prefix = get_aws_mfa_cred_command(self.cred_role)
            t_cmd = f"{cmd_prefix} {t_cmd}"
            log_cmd = f'[AWS_MFA env creds redacted for role {self.cred_role}] aws s3api head-bucket --bucket "{bucket_name}"'
        else:
            aws_env_prefix = self._aws_default_env_prefix()
            if aws_env_prefix:
                t_cmd = f"{aws_env_prefix} {t_cmd}"
                log_cmd = f'[AWS_PROFILE from resolved aws_profile] aws s3api head-bucket --bucket "{bucket_name}"'

        logging.info(f"Checking Terraform backend bucket existence:\n{log_cmd}\n")
        proc = subprocess.run(
            t_cmd,
            shell=True,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0

    def _ensure_state_backend(self):
        if self.state_backend_bootstrap_run_dir is None or self.state_backend_bootstrap_conf is None:
            return

        if self._backend_bucket_exists():
            logging.info(f'Terraform backend bucket [{self.backend_tree.bucket}] already exists.')
            return

        logging.info(
            f'Terraform backend bucket [{self.backend_tree.bucket}] is missing. '
            f'Bootstrapping state backend module [{self.state_backend_bootstrap_run_dir}] before continuing.'
        )
        bootstrap_terraform = WrapTerraform(
            root_path=self.root_path,
            run_dir=str(self.state_backend_bootstrap_run_dir),
            conf=self.state_backend_bootstrap_conf,
        )
        bootstrap_terraform.wield_protocol(TerraformAction.APPLY)

    def _strip_backend_blocks_for_local_plan(self):
        self._backend_backup_paths = []
        backend_line_pattern = re.compile(r'^\s*backend\s+"[^"]+"\s*\{\s*\}\s*$')

        for tf_path in Path(self.run_path).glob("*.tf"):
            original_text = tf_path.read_text()
            updated_lines = []
            changed = False

            for line in original_text.splitlines(keepends=True):
                if backend_line_pattern.match(line.rstrip("\n")):
                    changed = True
                    continue
                updated_lines.append(line)

            if not changed:
                continue

            backup_path = tf_path.with_suffix(tf_path.suffix + ".wielder-backup")
            backup_path.write_text(original_text)
            tf_path.write_text("".join(updated_lines))
            self._backend_backup_paths.append((tf_path, backup_path))

    def _restore_backend_blocks_after_local_plan(self):
        for tf_path, backup_path in self._backend_backup_paths:
            if backup_path.exists():
                tf_path.write_text(backup_path.read_text())
                backup_path.unlink()
        self._backend_backup_paths = []

    def run_cmd_in_repo(self, t_cmd, get_reply, reply_type):

        with DirContext(self.run_path):
            self._require_terraform_binary(t_cmd)

            log_cmd = t_cmd
            env_prefix = self._terraform_env_prefix() + self._aws_default_env_prefix()
            if self.cred_type == CredType.AWS_MFA:
                cmd_prefix = get_aws_mfa_cred_command(self.cred_role)
                t_cmd = f'{env_prefix}{cmd_prefix} {t_cmd}'
                log_cmd = f'[AWS_MFA env creds redacted for role {self.cred_role}] {t_cmd.split(";")[-1].strip()}'
            elif env_prefix:
                t_cmd = f'{env_prefix}{t_cmd}'

            logging.info(f"Running:\n{log_cmd}\nin: {self.run_path}\n")

            if get_reply:
                logging.info(f"Waiting for reply, this is happening in another process and might take a lot of time.")
                state_bytes = subprocess_cmd(t_cmd, verbose=self.verbose)

                reply = state_bytes.decode('utf8')

                if state_bytes == b'\x1b[0m\x1b[0m\x1b[0m':
                    reply = json.dumps({"reply": "warning reply is empty"})
                else:

                    logging.info(f'Terraform reply:\n{reply}')

                    if reply_type is TerraformReplyType.JSON:
                        try:
                            reply = json.loads(reply)

                            if self.verbose:
                                s = json.dumps(reply, indent=4, sort_keys=True)
                                logging.debug(s)
                        except Exception as e:
                            logging.error(e)
                            reply = json.dumps({"reply": "warning couldn't get reply as json"})

                return reply

            else:
                logging.info("Not sending reply, note that terraform can take some time to respond")
                exit_code = os.system(t_cmd)
                if exit_code != 0:
                    raise RuntimeError(
                        f"Terraform command failed with exit code [{exit_code}] in [{self.run_path}]: {log_cmd}"
                    )
                return 'Command run and finished without collecting reply'

    def run_cmd_lines_in_repo(self, t_cmd, strict=False):

        with DirContext(self.run_path):
            self._require_terraform_binary(t_cmd)

            log_cmd = t_cmd
            env_prefix = self._terraform_env_prefix() + self._aws_default_env_prefix()
            if self.cred_type == CredType.AWS_MFA:
                cmd_prefix = get_aws_mfa_cred_command(self.cred_role)
                t_cmd = f'{env_prefix}{cmd_prefix} {t_cmd}'
                log_cmd = f'[AWS_MFA env creds redacted for role {self.cred_role}] {t_cmd.split(";")[-1].strip()}'
            elif env_prefix:
                t_cmd = f'{env_prefix}{t_cmd}'

            logging.info(f"Running:\n{log_cmd}\nin: {self.run_path}\n")
            return async_cmd(t_cmd, verbose=self.verbose, strict=strict)

    def read_state_addresses(self):
        try:
            state_list_reply = self.run_cmd_in_repo(
                t_cmd="terraform state list",
                get_reply=True,
                reply_type=TerraformReplyType.TEXT,
            )
            return {
                line.strip()
                for line in str(state_list_reply).splitlines()
                if line.strip()
            }
        except Exception as exc:
            logging.warning("Unable to inspect Terraform state in [%s]: %s", self.run_path, exc)
            return None

    def import_existing_resources(self):
        if 'import_existing' not in self.conf:
            return

        state_addresses = self.read_state_addresses()

        for import_item in self.conf.import_existing:
            address = str(import_item.address)
            import_id = self._resolve_import_id(import_item)

            if state_addresses is not None and address in state_addresses:
                logging.info("Skipping Terraform import for already-managed address [%s].", address)
                continue
            if import_id is None:
                logging.info("Skipping Terraform import for unresolved existing resource [%s].", address)
                continue

            tf_cmd = f"terraform import '{address}' '{import_id}'"
            try:
                self.run_cmd_lines_in_repo(t_cmd=tf_cmd, strict=True)
                logging.info("Imported existing Terraform resource [%s] with id [%s].", address, import_id)
            except RuntimeError as exc:
                exc_text = str(exc)
                if (
                    "Cannot import non-existent remote object" in exc_text
                    or "no object exists with the given id" in exc_text
                    or "NoSuchBucket" in exc_text
                    or "NotFound" in exc_text
                    or "ResourceNotFoundException" in exc_text
                ):
                    logging.info("Skipping Terraform import for absent remote object [%s] with id [%s].", address, import_id)
                    continue
                raise

    def _resolve_import_id(self, import_item):
        if "id" in import_item:
            return str(import_item.id)
        if "id_from" not in import_item:
            raise RuntimeError(f"Terraform import item for [{import_item.address}] must define id or id_from.")

        resolver = import_item.id_from
        resolver_kind = str(resolver.kind)
        if resolver_kind == "aws_eks_pod_identity_association":
            return self._resolve_aws_eks_pod_identity_association_import_id(resolver)

        raise RuntimeError(f"Unsupported Terraform import id resolver kind [{resolver_kind}].")

    def _boto3_session(self, region_name: str | None = None):
        import boto3

        if self.cred_type == CredType.AWS_MFA:
            session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(self.cred_role)
            return boto3.Session(**session_kwargs, region_name=region_name)

        profile_name = self._terraform_aws_profile().strip()
        if profile_name:
            return boto3.Session(profile_name=profile_name, region_name=region_name)
        return boto3.Session(region_name=region_name)

    def _resolve_aws_eks_pod_identity_association_import_id(self, resolver):
        cluster_name = str(resolver.cluster_name)
        namespace = str(resolver.namespace)
        service_account = str(resolver.service_account)
        region = self._get_conf_string(resolver, "region") or self._get_conf_string(self.tfvars, "aws_region")

        session = self._boto3_session(region_name=region or None)
        eks = session.client("eks", region_name=region or None)

        associations = []
        request = {
            "clusterName": cluster_name,
            "namespace": namespace,
            "serviceAccount": service_account,
        }
        while True:
            response = eks.list_pod_identity_associations(**request)
            associations.extend(response.get("associations", []))
            next_token = response.get("nextToken")
            if not next_token:
                break
            request["nextToken"] = next_token

        if not associations:
            logging.info(
                "No EKS pod identity association exists for cluster [%s], namespace [%s], service account [%s].",
                cluster_name,
                namespace,
                service_account,
            )
            return None
        if len(associations) > 1:
            raise RuntimeError(
                "Multiple EKS pod identity associations found for "
                f"cluster [{cluster_name}], namespace [{namespace}], service account [{service_account}]."
            )

        association_id = associations[0]["associationId"]
        return f"{cluster_name},{association_id}"

    def remove_state_addresses(self, addresses):
        state_addresses = self.read_state_addresses()

        for address in addresses:
            if state_addresses is not None and address not in state_addresses:
                logging.info("Skipping Terraform state cleanup for absent address [%s].", address)
                continue

            tf_cmd = f"terraform state rm '{address}'"
            logging.info(f'running terraform command:\n{tf_cmd}')
            try:
                self.run_cmd_in_repo(t_cmd=tf_cmd, get_reply=False, reply_type=TerraformReplyType.TEXT)
            except RuntimeError as exc:
                if "No matching objects found" in str(exc):
                    logging.info("Skipping Terraform state cleanup for absent address [%s].", address)
                    continue
                raise

    # TODO this is quick and dirty, create access functions in the SDK to better wrap Terraform
    def terraform_cmd(self, terraform_action=TerraformAction.PLAN, auto_approve=True, apply_targets=None):
        """
        This is in development and not thoroughly tested!!!
        :param apply_targets: List of modules to target in apply
        :param terraform_action: Basic Terraform command
        :param auto_approve: For destroy and apply auto approval
        :return: terraform CLI output if applicable
        """

        get_reply = False
        reply_type = TerraformReplyType.TEXT

        t_cmd = f'terraform {terraform_action.value}'

        def target_arg(target_name):
            target = str(target_name)
            if "." not in target:
                target = f"module.{target}"
            return f' --target={shlex.quote(target)}'

        if terraform_action == TerraformAction.SHOW:

            get_reply = True
            reply_type = TerraformReplyType.JSON

        elif terraform_action == TerraformAction.INIT:

            if 'use_backend' in self.conf and not self.conf.use_backend:
                terraform_metadata_dir = Path(self.run_path) / ".terraform"
                if terraform_metadata_dir.exists():
                    shutil.rmtree(terraform_metadata_dir)
                t_cmd = f'{t_cmd} -backend=false'
            elif self.backend_name is not None:
                t_cmd = f'{t_cmd} -upgrade -reconfigure -backend-config "{self.backend_root}/{self.backend_name}.tf"'

        elif terraform_action == TerraformAction.PLAN:

            if apply_targets is not None:

                for module in apply_targets:

                    t_cmd += target_arg(module)

        elif terraform_action == TerraformAction.APPLY:

            if apply_targets is not None:

                for module in apply_targets:

                    t_cmd += target_arg(module)

            if auto_approve:
                t_cmd = f'{t_cmd} -auto-approve'

        elif terraform_action == TerraformAction.DESTROY:

            if auto_approve:
                t_cmd = f'{t_cmd} -auto-approve'

            if self.conf.destroy_protocol.partial:

                for module in self.conf.destroy_protocol.partial_modules:

                    t_cmd += target_arg(module)

            t_cmd = f'{t_cmd} -refresh=true'

        if terraform_action == TerraformAction.APPLY:
            t_cmd = f'{t_cmd} -parallelism={self.conf.parallelism}'

        reply = self.run_cmd_in_repo(
            t_cmd=t_cmd,
            get_reply=get_reply,
            reply_type=reply_type
        )

        if get_reply:
            return reply

    def configure_tfvars(self, new_state=False):
        """
        Converts a Hocon configuration to Terraform in the path
        :param new_state:
        :type new_state: bool
        :return:
        :rtype:
        """
        module_path = Path(self.run_path)
        if not module_path.exists():
            raise FileNotFoundError(
                f"Terraform module path [{self.run_path}] does not exist. "
                f"This usually means the staged provision repo does not contain that module yet."
            )

        if not list(module_path.glob("*.tf")):
            raise FileNotFoundError(
                f"Terraform module path [{self.run_path}] contains no Terraform configuration files. "
                f"This usually means the provision repo checkout is stale or the module has not been committed yet."
            )

        if new_state:
            logging.debug("Trying to remove local terraform state files if they exist")
            r = random.randint(3, 10000)
            full = f'{self.run_path}/terraform.tfstate'
            _cmd(f"mv {full} {full}.{r}.copy")

        self._prepare_tfvars_for_execution()

        config_to_terraform(
            tree=self.tfvars,
            destination=self.run_path,
            print_vars=True
        )

        if self.backend_tree is not None and self.backend_name is not None:
            backend_full_path = f'{self.root_path}/backends_tf'
            Path(backend_full_path).mkdir(parents=True, exist_ok=True)

            config_to_terraform(
                tree=self.backend_tree,
                destination=backend_full_path,
                name=f'{self.backend_name}.tf',
                print_vars=True
            )

    def _prepare_tfvars_for_execution(self):
        if self.cred_type != CredType.AWS_MFA:
            return
        if self.tfvars is None or "aws_profile" not in self.tfvars:
            return
        if str(self.tfvars.aws_profile).strip() == "":
            return

        logging.info(
            "Clearing Terraform provider aws_profile because Wielder is injecting AWS_MFA session credentials."
        )
        self.tfvars.put("aws_profile", "")

    def read_output(self):

        t_cmd = 'terraform output -json'

        output = self.run_cmd_in_repo(t_cmd, True, TerraformReplyType.JSON)

        return output

    # TODO remove these ugly AWS specific actions (Inherit Terraformer with AWSTerraformer & create factory method)
    def ugly_precursor_to_eks_destroy(self):

        logging.info("In preparation for destroying EKS destroying some auth resources")
        self.remove_state_addresses([
            "module.eks[0].kubernetes_config_map.aws_auth",
            "module.eks[0].kubernetes_config_map_v1_data.aws_auth",
        ])

    def wield_protocol(self, action):
        use_backend = not ('use_backend' in self.conf and not self.conf.use_backend)

        if not use_backend:
            self._strip_backend_blocks_for_local_plan()

        try:
            self.configure_tfvars(new_state=False)

            conf = self.conf

            if use_backend:
                self._ensure_state_backend()

            if conf.init:
                self.terraform_cmd(terraform_action=TerraformAction.INIT)

            if action in {TerraformAction.PLAN, TerraformAction.APPLY} and 'state_cleanup_addresses' in conf:
                self.remove_state_addresses([str(address) for address in conf.state_cleanup_addresses])

            if action == TerraformAction.PLAN and 'import_existing_on_plan' in conf and conf.import_existing_on_plan:
                self.import_existing_resources()

            if action == TerraformAction.APPLY:
                self.import_existing_resources()

            partial_modules = None
            if conf.partial:
                partial_modules = conf.partial_modules

            if action == TerraformAction.APPLY and self._terraform_provisions_aws_eks():

                self.ugly_precursor_to_eks_destroy()

            self.terraform_cmd(terraform_action=action, apply_targets=partial_modules)

            logging.info('finished deploying Terraform resources')

            if action == TerraformAction.PLAN and not conf.init:
                logging.info("Skipping terraform output read because [init = false] for plan mode.")
                return {"reply": "skipped terraform output because init=false"}

            if action == TerraformAction.APPLY:
                self._update_kubernetes_context_after_eks_apply()

            out = self.read_output()
            logging.info(out)

            return out
        finally:
            if not use_backend:
                self._restore_backend_blocks_after_local_plan()

    def destroy_protocol(self):

        use_backend = not ('use_backend' in self.conf and not self.conf.use_backend)

        if not use_backend:
            self._strip_backend_blocks_for_local_plan()

        try:
            destroy_protocol = self.conf.destroy_protocol

            if 'destroy_eks' in destroy_protocol and destroy_protocol.destroy_eks:

                self.ugly_precursor_to_eks_destroy()

            self.configure_tfvars(new_state=False)
            if self.conf.init:
                self.terraform_cmd(terraform_action=TerraformAction.INIT)

            if 'preserve_state_addresses' in destroy_protocol:
                self.remove_state_addresses([str(address) for address in destroy_protocol.preserve_state_addresses])

            self.terraform_cmd(terraform_action=TerraformAction.REFRESH)
            terraform_action = wield_to_terraform(WieldAction.DELETE)

            partial_modules = None
            if destroy_protocol.partial:
                partial_modules = destroy_protocol.partial_modules

            # TODO parse and react to reply
            terraform_reply = self.terraform_cmd(terraform_action=terraform_action, apply_targets=partial_modules)

            out = self.read_output()
            logging.info(out)
            logging.info('finished destroying Terraform resources.')

            if 'destroy_eks' in destroy_protocol and destroy_protocol.destroy_eks:

                context_cmd = f'kubectl config use-context {destroy_protocol.default_kube_context}'
                logging.info(f'Switching Kubernetes context:\n{context_cmd}')
                os.system(context_cmd)

                kube_context = self.conf.kube_context
                context_cmd = f'kubectl config delete-context {kube_context}'

                logging.info(f'Deleting Kubernetes context:\n{context_cmd}')
                os.system(context_cmd)

            return out
        finally:
            if not use_backend:
                self._restore_backend_blocks_after_local_plan()






if __name__ == "__main__":
    setup_logging(log_level=logging.DEBUG)
