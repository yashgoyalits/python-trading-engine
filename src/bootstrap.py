import os
from dotenv import load_dotenv

class BootstrapError(Exception):
    pass

_REQUIRED_ENV_VARS = (
    "CLIENT_ID",
    "FYERS_ACCESS_TOKEN",
)

def bootstrap() -> None:
    load_dotenv()

    env = _validate_env()
    _validate_credentials_format(env)


def _validate_env() -> dict[str, str]:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]

    if missing:
        raise BootstrapError(f"Missing environment variables: {missing}")

    return {v: os.getenv(v) for v in _REQUIRED_ENV_VARS}


def _validate_credentials_format(env: dict[str, str]) -> None:
    client_id = env["CLIENT_ID"]
    token = env["FYERS_ACCESS_TOKEN"]

    if " " in client_id:
        raise BootstrapError("CLIENT_ID format is invalid.")

    if len(token) < 100 or token.count(".") < 2:
        raise BootstrapError("FYERS_ACCESS_TOKEN format is invalid.")