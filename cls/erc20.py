import json
import logging
from typing import Any, Final, Optional

from eth_typing.evm import ChecksumAddress
from requests import get
from web3 import Web3

from xio import ABILoader

ERC20_ABI: Final[list] = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_from", "type": "address"},
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "_from", "type": "address"},
            {"indexed": True, "name": "_to", "type": "address"},
            {"indexed": False, "name": "_value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "_owner", "type": "address"},
            {"indexed": True, "name": "_spender", "type": "address"},
            {"indexed": False, "name": "_value", "type": "uint256"},
        ],
        "name": "Approval",
        "type": "event",
    },
]


class ERC20:
    """
    Class that encapsulates usage of basic ERC20 functions.
    """

    def __init__(self, infura_url: str, abi: list[Any]) -> None:
        """
        Constructor.

        :param infura_url: Infura URL.
        :param abi: ABI data (list).
        """
        self._w3 = Web3(Web3.HTTPProvider(infura_url))
        self._abi = abi
        logging.debug(f"Infura URL is: {infura_url}")
        logging.debug(f"Used ABI: {self._abi}")

    @property
    def abi(self) -> list[Any]:
        return self._abi

    @classmethod
    def erc20_from_smart_contract_address(
        cls, infura_url: str, etherscan_api_key: str, smart_contract_address: str
    ):
        """
        Overloaded constructor.

        :param infura_url: Infura URL.
        :param etherscan_api_key: Etherscan API key.
        :param smart_contract_address: Smart contract address of an ERC20 token.
        :return: ERC20 object instance.
        """
        try:
            url = (
                f"https://api.etherscan.io/api?module=contract&action=getabi&"
                f"address={smart_contract_address}&apikey={etherscan_api_key}"
            )
            response = get(url)
            abi = json.loads(response.json()["result"])
        except Exception as error:
            logging.error(
                f"Can not load the ABI from Etherscan for smart contract address: "
                f"'{smart_contract_address}'. Error: {error}"
            )
        else:
            return cls(infura_url, abi)

    @classmethod
    def erc20_from_abi_file(cls, infura_url: str, erc20_abi_path: str):
        """
        Overloaded constructor.

        :param infura_url: Infura URL.
        :param erc20_abi_path: Path to the ABI .json file.
        :return: ERC20 object instance.
        """
        abi_loader = ABILoader(erc20_abi_path)
        return cls(infura_url, abi_loader.erc20_abi)

    @classmethod
    def erc20_from_abi_data(cls, infura_url: str, abi_data: Optional[list[Any]] = None):
        """
        Overloaded constructor.

        :param infura_url: Infura URL.
        :param abi_data: ABI data (list).
        :return: ERC20 object instance.
        """
        if abi_data is None:
            abi_data = ERC20_ABI
        return cls(infura_url, abi_data)

    def to_checksum_address(self, address: str) -> ChecksumAddress:
        """
        Transforms address to checksum address:
        e.g.: from 0x6b175474e89094c44da98b954eedeac495271d0f to 0x6B175474E89094C44Da98b954EedeAC495271d0F

        :param address: Input address to be transformed to checksum address.
        :return: Checksum address.
        """
        checksum_address = self._w3.toChecksumAddress(address)
        return checksum_address

    def get_erc20_balance(
        self, wallet_address: str, asset_contract_address: str, in_decimals: bool = True
    ) -> float:
        """
        Returns balance of an assets.

        :param wallet_address: Wallet address "0x..." what you want to get the balance of asset.
        :param asset_contract_address: Asset contract "0x..." you want to get balance in your wallet_address.
        :param in_decimals: It will return value like 1.23455666.
        :return: Balance of asset_contract_address asset in wallet_address.
        """
        wallet_address = self.to_checksum_address(wallet_address)
        asset_contract_address = self.to_checksum_address(asset_contract_address)

        erc20 = self._w3.eth.contract(address=asset_contract_address, abi=self._abi)
        balance = erc20.functions.balanceOf(wallet_address).call()

        if in_decimals:
            decimals = erc20.functions.decimals().call()
            balance = balance / 10**decimals

        logging.debug(
            f"Wallet '{wallet_address}' has {balance} {erc20.functions.symbol().call()}."
        )
        return float(balance)

    def get_erc20_symbol(self, asset_contract_address: str) -> str:
        """
        Retrieve ERC20 symbol for input smart contract asset's address.

        :param asset_contract_address: Smart contract asset's address.
        :return: Symbol of underlying smart contract.
        """
        asset_contract_address = self.to_checksum_address(asset_contract_address)
        erc20 = self._w3.eth.contract(address=asset_contract_address, abi=self._abi)
        symbol = erc20.functions.symbol().call()
        logging.debug(f"Symbol of '{asset_contract_address}' is {symbol}.")
        return symbol

    def get_erc20_name(self, asset_contract_address: str) -> str:
        """
        Retrieve ERC20 name for input smart contract asset's address.

        :param asset_contract_address: Smart contract asset's address.
        :return: Name of underlying smart contract.
        """
        asset_contract_address = self.to_checksum_address(asset_contract_address)
        erc20 = self._w3.eth.contract(address=asset_contract_address, abi=self._abi)
        name = erc20.functions.name().call()
        logging.debug(f"Name of '{asset_contract_address}' is {name}.")
        return name

    def get_erc20_decimals(self, asset_contract_address: str) -> int:
        """
        Retrieve number of ERC20 decimals for input smart contract asset's address.

        :param asset_contract_address: Smart contract asset's address.
        :return: Number of decimals of underlying smart contract.
        """
        asset_contract_address = self.to_checksum_address(asset_contract_address)
        erc20 = self._w3.eth.contract(address=asset_contract_address, abi=self._abi)
        decimals = erc20.functions.decimals().call()
        logging.debug(f"'{asset_contract_address}' has {decimals} decimal places.")
        return decimals

    def get_erc20_total_supply(
        self, asset_contract_address: str, in_decimals: bool = True
    ) -> float:
        """
        Retrieve total supply for input smart contract asset's address.

        :param asset_contract_address: Smart contract asset's address.
        :param in_decimals: It will return value like 1.23455666.
        :return: Total supply of underlying smart contract.
        """
        asset_contract_address = self.to_checksum_address(asset_contract_address)
        erc20 = self._w3.eth.contract(address=asset_contract_address, abi=self._abi)
        total_supply = erc20.functions.totalSupply().call()

        if in_decimals:
            decimals = erc20.functions.decimals().call()
            total_supply = total_supply / 10**decimals

        if in_decimals:
            logging.debug(
                f"Total supply of '{asset_contract_address}' is "
                f"{total_supply} {erc20.functions.symbol().call().upper()}."
            )
        else:
            logging.debug(
                f"Total supply of '{asset_contract_address}' is {total_supply}."
            )

        return total_supply
