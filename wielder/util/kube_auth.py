from kubernetes import config


def new_kubernetes_api_client(context: str):
    api_client = config.new_client_from_config(context=context)
    _normalize_bearer_token(api_client)
    return api_client


def _normalize_bearer_token(api_client) -> None:
    configuration = api_client.configuration
    authorization = configuration.api_key.get("authorization")
    if not authorization or "BearerToken" in configuration.api_key:
        return

    token = authorization.removeprefix("Bearer ")
    configuration.api_key["BearerToken"] = token
    configuration.api_key_prefix["BearerToken"] = "Bearer"
