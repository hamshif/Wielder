#!/usr/bin/env python
import json
import os
from os.path import expanduser
from datetime import datetime, timezone


class AwsMfaCredentialsMissingError(RuntimeError):
    pass


def _parse_aws_cli_cache_expiration(raw_expiration: str) -> datetime:
    try:
        return datetime.strptime(raw_expiration, "%Y-%m-%dT%H:%M:%SUTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromisoformat(raw_expiration.replace("Z", "+00:00")).astimezone(timezone.utc)


def cred_as_export_cmd(prop_dict):

    a = ''

    for key, value in prop_dict.items():
        a = a + f'export {key}="{value}";\n'

    return a


def _aws_mfa_cred_session_keys(env_cred: dict) -> dict:
    return {
        "AWS_ACCESS_KEY_ID": env_cred["AWS_ACCESS_KEY_ID"],
        "AWS_SECRET_ACCESS_KEY": env_cred["AWS_SECRET_ACCESS_KEY"],
        "AWS_SESSION_TOKEN": env_cred["AWS_SESSION_TOKEN"],
        "AWS_SECURITY_TOKEN": env_cred["AWS_SECURITY_TOKEN"],
    }


def aws_mfa_cred_as_subprocess_env(role_name: str | None, base_env: dict | None = None) -> dict | None:
    """
    Return a subprocess environment using cached AWS MFA role credentials.

    The returned environment deliberately removes AWS_PROFILE/AWS_DEFAULT_PROFILE
    so subprocesses do not re-enter the MFA profile chain when explicit session
    credentials are already available.
    """
    if not role_name:
        return None

    env_cred = get_aws_mfa_cred(role_name)
    if not env_cred:
        return None

    env = dict(os.environ if base_env is None else base_env)
    env.pop("AWS_PROFILE", None)
    env.pop("AWS_DEFAULT_PROFILE", None)
    env.update(_aws_mfa_cred_session_keys(env_cred))
    return env


def aws_mfa_cred_as_boto3_session_kwargs(role_name: str | None) -> dict:
    """
    Return boto3.Session keyword arguments for cached AWS MFA role credentials.
    """
    if not role_name:
        return {}

    env_cred = get_aws_mfa_cred(role_name)
    if not env_cred:
        return {}

    return {
        "aws_access_key_id": env_cred["AWS_ACCESS_KEY_ID"],
        "aws_secret_access_key": env_cred["AWS_SECRET_ACCESS_KEY"],
        "aws_session_token": env_cred["AWS_SESSION_TOKEN"],
    }


def get_aws_mfa_cred(role_name):
    """
    Looks for aws MFA session credentials file,
    extracts env variables necessary for running terraform
    :param role_name: role name to check against CLI MFA cache.
    :return: returns env credential shell command or empty string.
    """

    home = expanduser("~")
    dir_path = f"{home}/.aws/cli/cache"

    best_match = None
    for subdir, dirs, files in os.walk(dir_path):

        for f in files:
            if not f.endswith('.json'):
                continue

            with open(f'{dir_path}/{f}') as json_file:
                data = json.load(json_file)

                cred = data["Credentials"]

                if "AssumedRoleUser" in data.keys():

                    if "Arn" in data["AssumedRoleUser"].keys():

                        if f'/{role_name}/' not in data["AssumedRoleUser"]["Arn"]:
                            continue

                        expiration = _parse_aws_cli_cache_expiration(cred["Expiration"])
                        now = datetime.now(timezone.utc)

                        if expiration <= now:
                            continue

                        if best_match is None or expiration > best_match["expiration"]:
                            best_match = {
                                "expiration": expiration,
                                "env_cred": {
                                    "ASSUMED_ROLE": data["AssumedRoleUser"]["AssumedRoleId"],
                                    "AWS_ACCESS_KEY_ID": cred["AccessKeyId"],
                                    "AWS_SECRET_ACCESS_KEY": cred["SecretAccessKey"],
                                    "AWS_SESSION_TOKEN": cred["SessionToken"],
                                    "AWS_SECURITY_TOKEN": cred["SessionToken"],
                                },
                            }

    if best_match is not None:
        return best_match["env_cred"]

    return {}


def require_aws_mfa_cred(role_name):
    env_cred = get_aws_mfa_cred(role_name)
    if env_cred:
        return env_cred

    home = expanduser("~")
    dir_path = f"{home}/.aws/cli/cache"
    expired_matches = []

    for _subdir, _dirs, files in os.walk(dir_path):
        for f in files:
            if not f.endswith('.json'):
                continue

            with open(f'{dir_path}/{f}') as json_file:
                data = json.load(json_file)

            if "AssumedRoleUser" not in data or "Arn" not in data["AssumedRoleUser"]:
                continue

            if f'/{role_name}/' not in data["AssumedRoleUser"]["Arn"]:
                continue

            cred = data["Credentials"]
            expired_matches.append(_parse_aws_cli_cache_expiration(cred["Expiration"]))

    latest_expired = max(expired_matches).isoformat() if expired_matches else "none"
    raise AwsMfaCredentialsMissingError(
        "No valid cached AWS MFA credentials found for role "
        f"[{role_name}]. Checked [{dir_path}]. Latest expired credential: [{latest_expired}]. "
        "Refresh authentication with your normal AWS MFA profile flow, then rerun the Wielder entrypoint."
    )


def get_aws_mfa_cred_command(role_name):
    """
    Looks for aws MFA session credentials file,
    extracts env variables necessary for running terraform
    :param role_name: role name to check against CLI MFA cache.
    :return: returns env credential shell command or empty string.
    """

    env_cred = require_aws_mfa_cred(role_name)
    profile_sanitizer = "unset AWS_PROFILE;\nunset AWS_DEFAULT_PROFILE;\n"
    return profile_sanitizer + cred_as_export_cmd(env_cred)
