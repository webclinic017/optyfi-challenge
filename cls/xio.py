import json
import logging
import os
import uuid
from typing import Any, Optional


class ConfigLoader:
    """
    Class for loading configuration.
    """

    @staticmethod
    def load(config_path: str) -> dict[Any, Any]:
        """
        Load configuration.

        :param config_path: Path to the .json configuration file.
        :return: Dict with configuration.
        """
        if not os.path.isfile(config_path):
            logging.error(f"'{config_path}' does not exist.")

        if not config_path.endswith(".json"):
            logging.error(f"The file '{config_path}' does not have .json extension.")

        data: dict[Any, Any] = dict()
        try:
            with open(config_path) as f:
                data = json.load(f)
        except Exception as error:
            logging.error(
                f"Can not read configuration file: '{config_path}'. Error: {error}"
            )
        else:
            # lowercase strings
            data = {k.lower(): v for k, v in data.items()}

            # add uuid to loaded configuration
            data["id"] = str(uuid.uuid4())
            data["publisher_name"] = "from_file"
        return data


class ABILoader:
    """
    Class for loading ABI files.
    """

    def __init__(self, erc20_abi_path: str) -> None:
        """
        Constructor.

        :param erc20_abi_path: Path to an erc20_abi.json.
        """
        if not os.path.isfile(erc20_abi_path):
            logging.error(f"'{erc20_abi_path}' does not exist.")

        if not erc20_abi_path.endswith(".json"):
            logging.error(
                f"The ABI file '{erc20_abi_path}' does not have .json extension."
            )

        try:
            with open(erc20_abi_path) as f:
                self._erc20_abi = json.load(f)
        except Exception as error:
            logging.error(
                f"Can not read ERC20 ABI from file: '{erc20_abi_path}'. Error: {error}"
            )

    @property
    def erc20_abi(self):
        return self._erc20_abi

    @staticmethod
    def load(abi_path: str) -> Optional[dict[Any, Any]]:
        """
        Loads ABI file.

        :param abi_path: Path of an ABI file.
        :return: Returns loaded data in dictionary.
        """
        if not os.path.isfile(abi_path):
            logging.error(f"'{abi_path}' does not exist.")

        if not abi_path.endswith(".json"):
            logging.error(f"The ABI file '{abi_path}' does not have .json extension.")
        data: Optional[dict[Any, Any]] = None
        try:
            with open(abi_path) as f:
                data = json.load(f)
        except Exception as error:
            logging.error(f"Can not read ABI from file: '{abi_path}'. Error: {error}")

        return data
