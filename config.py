import logging

from starlette.config import Config
from starlette.datastructures import Secret

config: Config = Config(".env")

# Logging configurations.
LOGGING_DEBUG: bool = config("LOGGING_DEBUG", cast=bool, default=False)
LOG_TO_FILE: bool = config("LOG_TO_FILE", cast=bool, default=True)
LOGGING_LEVEL: int = logging.DEBUG if LOGGING_DEBUG else logging.INFO

# Network configurations.
ETH_TESTNET: bool = config("ETH_TESTNET", cast=bool, default=False)

# Infura configurations.
if ETH_TESTNET:
    INFURA_API_KEY: Secret = config("INFURA_API_KEY_TEST", cast=Secret)
    INFURA_URL: str = f"https://ropsten.infura.io/v3/{str(INFURA_API_KEY)}"
else:
    INFURA_API_KEY: Secret = config("INFURA_API_KEY", cast=Secret)
    INFURA_URL: str = f"https://mainnet.infura.io/v3/{str(INFURA_API_KEY)}"

# Etherscan configurations.
ETHERSCAN_API_KEY: Secret = config("ETHERSCAN_API_KEY", cast=Secret)
