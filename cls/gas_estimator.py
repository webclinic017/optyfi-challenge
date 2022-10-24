import logging
from typing import Union

from config import ETHERSCAN_API_KEY, INFURA_URL
from eth_abi.codec import ABICodec
from eth_typing.evm import ChecksumAddress
from erc20 import ERC20
from web3 import Web3

try:
    from web3.utils.events import get_event_data
    from web3.utils.filters import construct_event_filter_params
except ImportError:
    from web3._utils.events import get_event_data
    from web3._utils.filters import construct_event_filter_params


class GasEstimator:
    """
    Gas estimator class.
    """

    def __init__(
        self,
        smart_contract_address: Union[str, ChecksumAddress],
        abi: list = None,
        max_days: int = None,
        min_transaction_count: int = None,
        max_transaction_count: int = None,
    ) -> None:
        """
        Constructor.

        :param smart_contract_address: Address of a smart contract.
        :param abi: ABI of smart contract.
        :param max_days: Maximum days to look into the history.
        :param min_transaction_count: Minimum number of transactions required to be collected for calculating average.
        :param max_transaction_count: Maximum number of transactions required to be collected for calculating average.
        """
        self._smart_contract_address = Web3.toChecksumAddress(smart_contract_address)
        self._w3 = Web3(Web3.HTTPProvider(INFURA_URL))
        if abi:
            self._abi = abi
        else:
            self._abi = ERC20.erc20_from_smart_contract_address(
                INFURA_URL, str(ETHERSCAN_API_KEY), self._smart_contract_address
            ).abi
        self._contract = self._w3.eth.contract(
            address=self._smart_contract_address, abi=self._abi
        )
        self._average_number_of_eth_blocks_per_day = 6400
        self._known_gas_amounts = dict()
        self._week_in_days = 7
        self._max_halving_attempts: int = 20
        self._max_days = max_days if max_days else 90
        self._min_transaction_count = (
            min_transaction_count if min_transaction_count else 4
        )
        self._max_transaction_count = (
            max_transaction_count if max_transaction_count else 30
        )
        if self._min_transaction_count >= self._max_transaction_count:
            logging.error(
                f"min_transaction_count >= max_transaction_count "
                f"({self._min_transaction_count} >= {self._max_transaction_count})"
            )
            raise Exception(
                f"min_transaction_count >= max_transaction_count "
                f"({self._min_transaction_count} >= {self._max_transaction_count})"
            )

    def _get_last_block_number(self) -> int:
        """
        Returns number of the last ETH block.

        :return: Number of the last ETH block.
        """
        block = self._w3.eth.get_block("latest")
        return block["number"]

    def _get_logs(self, event, from_block: int, to_block: int = None) -> list:
        """
        Get events using eth.get_logs API. This is a stateless method, as opposite to createFilter.
        It can be safely called against nodes which do not provide eth.new_filter API, like Infura.

        :param event: Event object.
        :param from_block: Starting block.
        :param to_block: Ending block.
        :return: List of found logs.
        """
        if not to_block:
            to_block = self._get_last_block_number()

        argument_filters = dict()
        _filters = dict(**argument_filters)
        codec: ABICodec = self._w3.codec
        abi = event._get_event_abi()

        # Create event filter parameters.
        data_filter_set, event_filter_params = construct_event_filter_params(
            event_abi=abi,
            abi_codec=codec,
            contract_address=self._smart_contract_address,
            argument_filters=_filters,
            fromBlock=from_block,
            toBlock=to_block,
        )

        # Call JSON-RPC API get_logs.
        logs = self._w3.eth.get_logs(event_filter_params)

        # Convert raw binary data to Python proxy objects as described by ABI.
        all_events = []
        for log in logs:
            # Convert raw JSON-RPC log result to human readable event by using ABI data
            # More information how processLog works here
            # https://github.com/ethereum/web3.py/blob/fbaf1ad11b0c7fac09ba34baff2c256cffe0a148/web3/_utils/events.py#L200
            evt = get_event_data(codec, abi, log)
            # Note: This was originally yield,
            # but deferring the timeout exception caused the throttle logic not to work
            all_events.append(evt)
        return all_events

    def get_average_gas(self, event_name: str) -> int:  # noqa: C901
        """
        Gets average gas for the specific function in smart contract.

        :param event_name: Event name.
        :return: Average gas used for specific event_name.
        """
        if "_" in event_name:
            function_name_parts = event_name.split("_")
            function_name_parts = [part.capitalize() for part in function_name_parts]
            fx_name: str = ""
            for part in function_name_parts:
                fx_name += part
            event_name: str = fx_name

        logging.info(
            f"Estimating GAS for event '{event_name}' ({self._smart_contract_address})."
        )

        if event_name in self._known_gas_amounts:
            return self._known_gas_amounts[event_name]

        event = self._contract.events[event_name]()
        end_block: int = self._get_last_block_number()
        n_days: int = 1
        attempt: int = 0

        if event_name == "Swapped":
            # Swapped (1inch) has too many transactions -> start with 1 hour of number of transactions.
            start_block: int = end_block - int(
                self._average_number_of_eth_blocks_per_day / 24
            )
        else:
            # Start with 1 day of transactions.
            start_block: int = end_block - self._average_number_of_eth_blocks_per_day

        while True:
            try:
                logs: list = self._get_logs(
                    event=event, from_block=start_block, to_block=end_block
                )
            except Exception as error:
                # Too many results -> decreasing # of blocks to the half.
                logging.warning(f"Too many results. Error: {error}.")
                start_block: int = int((end_block - start_block) / 2)

                if attempt < self._max_halving_attempts:
                    attempt += 1
                else:
                    logging.error(
                        f"Can not estimate gas. Probably too many event entries. "
                        f"Tried {attempt + 1} times halved the 1 day of transactions. "
                        f"But still too many events in the last {end_block - start_block} blocks."
                    )
                    raise Exception(
                        f"Can not estimate gas. Probably too many event entries. "
                        f"Tried {attempt + 1} times halved the 1 day of transactions. "
                        f"But still too many events in the last {end_block - start_block} blocks."
                    )

            else:
                # It did not find anything -> increasing # of blocks by 1 week.
                if len(logs) > self._min_transaction_count:
                    break
                elif n_days >= self._max_days:
                    logging.error(
                        f"Can not find any '{event_name}' event in the last {self._max_days} days."
                    )
                    raise Exception(
                        f"Can not find any '{event_name}' event in the last {self._max_days} days."
                    )
                else:
                    n_days += self._week_in_days
                    start_block: int = end_block - (
                        self._average_number_of_eth_blocks_per_day * n_days
                    )

        # Get gas used for the last N transactions.
        gas_used: list = list()

        # Cap number of results for calculating average.
        if len(logs) > self._max_transaction_count:
            logs = logs[: self._max_transaction_count]

        [
            gas_used.append(
                self._w3.eth.get_transaction_receipt(log["transactionHash"])["gasUsed"]
            )
            for log in logs
        ]

        average_gas: int = int(sum(gas_used) / len(gas_used))
        self._known_gas_amounts[event_name] = average_gas
        logging.info(f"Estimated GAS for event '{event_name}' is {average_gas} GAS.")
        return average_gas
