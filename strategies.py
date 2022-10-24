import logging
from typing import Optional

import backtrader as bt
from backtrader import Strategy
from backtrader.indicators import MovingAverageSimple
from web3 import Web3

from cls.uniswap_v3_math import (
    calculate_fee,
    get_liquidity_for_amounts,
    get_sqrt_price_x96,
    get_tier_percentage,
    get_token_amounts_from_deposit_amounts,
    tick_to_price,
)


class SimpleStrategy(Strategy):
    def __init__(
        self,
        lp_range: list[float],
        pool_fee_tier: int,
        token0_decimals: int,
        token1_decimals: int,
        gas_for_swap_event: int,
    ) -> None:
        """
        Keep a reference to the "close" line in the data[0] data series.
        """
        self.log("Initializing SimpleStrategy.")

        # Holding period (rebalancing window) - heuristic approach based on LP range.
        # See: https://twitter.com/guil_lambert/status/1564988772713992193
        # 1 day [0, 12]%
        # 1 week (12, 25]%
        # 1 month (25, inf)%
        self.lp_range: list[float] = lp_range
        if abs(self.lp_range[0]) <= 0.12:
            self.holding_period: int = 1
        elif 0.12 < abs(self.lp_range[0]) <= 0.25:
            self.holding_period: int = 7
        else:
            self.holding_period: int = 30
        self.log(f"Heuristic approach for holding period:")
        self.log(f"    LP range <= 12% -> holding period = 1 day.")
        self.log(f"    12% < LP range <= 25% -> holding period = 7 days.")
        self.log(f"    25% < LP range <= inf% -> holding period = 30 days.")
        self.log(
            f"Current LP range: ({self.lp_range[0]}, {self.lp_range[1]}) -> "
            f"holding period: {self.holding_period} days."
        )

        self.pool_fee_tier: int = pool_fee_tier
        self.pool_fee_tier_percentage: float = get_tier_percentage(tier=pool_fee_tier)
        self.token0_decimals: int = token0_decimals
        self.token1_decimals: int = token1_decimals
        self.gas_for_swap_event: int = gas_for_swap_event

        # Store data.
        self.calculated_fees: list = []
        self.cumulative_fees: list = []
        self.bar_executed: int = 0
        self.order = None

        # Data from data feed.
        self.data_id: int = 0
        self.data_open = self.datas[self.data_id].open
        self.data_low = self.datas[self.data_id].low
        self.data_high = self.datas[self.data_id].high
        self.data_close = self.datas[self.data_id].close
        self.data_volume = self.datas[self.data_id].volume
        self.data_tvl = self.datas[self.data_id].tvl
        self.data_fees = self.datas[self.data_id].fees
        self.data_liquidity = self.datas[self.data_id].liquidity
        self.data_token0_price = self.datas[self.data_id].token0_price
        self.data_token1_price = self.datas[self.data_id].token1_price
        self.data_tick = self.datas[self.data_id].tick
        self.gas_price_in_wei = self.datas[self.data_id].wei
        self.gas_price_in_gwei = self.datas[self.data_id].gwei

    def log(self, txt, dt=None) -> None:
        """
        Logging function.

        :param txt:
        :param dt:
        :return: None.
        """
        dt = dt or self.datas[0].datetime.date(0)
        logging.info(f"{dt.isoformat()}: {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            self.log(f"ORDER ACCEPTED/SUBMITTED", dt=order.created.dt)
            self.order = order
            return

        if order.status in [order.Expired]:
            self.log("BUY EXPIRED")

        # Check if an order has been completed.
        # Attention: broker could reject order if not enough cash.
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"BUY EXECUTED, price: {order.executed.price:.2f}, "
                    f"cost: {order.executed.value:.2f}, "
                    f"comm: {order.executed.comm:.2f}."
                )
            elif order.issell():
                self.log(
                    f"SELL EXECUTED, price: {order.executed.price:.2f}, "
                    f"cost: {order.executed.value:.2f}, "
                    f"comm: {order.executed.comm:.2f}."
                )

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        # None pending order -> new order is allowed.
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def start(self):
        # For swapping 50% of USD(C) -> (W)ETH
        initial_swap_cost: float = (self.gas_for_swap_event * float(Web3.fromWei(self.gas_price_in_wei[0], "ether"))) * self.data_token1_price[0]
        self.broker.add_cash(-round(initial_swap_cost, 2))

    def next(self):
        # Target amount = available cash.
        target_amount: float = self.broker.get_cash()

        # Price assumption value.
        p: float = 1 / (
            tick_to_price(self.data_tick[0])
            / (10 ** (self.token1_decimals - self.token0_decimals))
        )
        # Price lower bound.
        pl: float = p * (1 - abs(self.lp_range[0]))
        # Price upper bound.
        pu: float = p * (1 + abs(self.lp_range[1]))
        # Price of X (token1) in USD.
        price_usd_x: float = self.data_token1_price[0]
        # Price of Y (token0) in USD.
        price_usd_y: float = self.data_token0_price[0]

        # Estimated amounts of token1 and token0.
        amount0, amount1 = get_token_amounts_from_deposit_amounts(
            price=p,
            price_lower_bound=pl,
            price_upper_bound=pu,
            price_usd_x=price_usd_x,
            price_usd_y=price_usd_y,
            target_amount=target_amount,
        )

        sqrt_ratio_x96: float = get_sqrt_price_x96(
            price=p,
            token0_decimal=self.token0_decimals,
            token1_decimal=self.token1_decimals,
        )
        sqrt_ratio_ax96: float = get_sqrt_price_x96(
            price=pl,
            token0_decimal=self.token0_decimals,
            token1_decimal=self.token1_decimals,
        )
        sqrt_ratio_bx96: float = get_sqrt_price_x96(
            price=pu,
            token0_decimal=self.token0_decimals,
            token1_decimal=self.token1_decimals,
        )

        delta_liquidity: float = get_liquidity_for_amounts(
            sqrt_ratio_x96=sqrt_ratio_x96,
            sqrt_ratio_ax96=sqrt_ratio_ax96,
            sqrt_ratio_bx96=sqrt_ratio_bx96,
            amount0=amount0,
            token0_decimals=self.token1_decimals,
            amount1=amount1,
            token1_decimals=self.token0_decimals,
        )

        fee: float = calculate_fee(
            delta_liquidity=delta_liquidity,
            liquidity=self.data_liquidity[0],
            volume=self.data_volume[0],
            pool_fee_tier=self.pool_fee_tier,
        )

        self.calculated_fees.append(fee)

        self.bar_executed += 1

        if self.bar_executed == self.holding_period:
            if self.bar_executed == 1:
                cumulated_fees: float = fee
            else:
                cumulated_fees: float = sum(self.calculated_fees[-self.bar_executed :])

            # Add fee to cash.
            self.broker.add_cash(cash=cumulated_fees)
            self.bar_executed: int = 0

        # Log some values for the reference.
        self.log(
            f"Close: ${self.data_close[0]:.2f}, "
            f"DrawDown: {self.stats.drawdown.drawdown[0]:.2f}, "
            f"MaxDrawDown: {self.stats.drawdown.maxdrawdown[0]:.2f}, "
            f"Fee: ${self.calculated_fees[-1]:.2f}, "
            f"Cash: ${self.broker.get_cash():.2f}"
        )


class Bonus1Strategy(Strategy):
    def __init__(
        self,
        lp_range: list[float],
        pool_fee_tier: int,
        token0_decimals: int,
        token1_decimals: int,
        gas_for_swap_event: int,
    ) -> None:
        """
        Keep a reference to the "close" line in the data[0] data series.
        """
        self.log("Initializing Bonus1Strategy.")

        # Holding period (rebalancing window) - heuristic approach based on LP range.
        # See: https://twitter.com/guil_lambert/status/1564988772713992193
        # 1 day [0, 12]%
        # 1 week (12, 25]%
        # 1 month (25, inf)%
        self.lp_range: list[float] = lp_range
        if abs(self.lp_range[0]) <= 0.12:
            self.holding_period: int = 1
        elif 0.12 < abs(self.lp_range[0]) <= 0.25:
            self.holding_period: int = 7
        else:
            self.holding_period: int = 30
        self.log(f"Heuristic approach for holding period:")
        self.log(f"    LP range <= 12% -> holding period = 1 day.")
        self.log(f"    12% < LP range <= 25% -> holding period = 7 days.")
        self.log(f"    25% < LP range <= inf% -> holding period = 30 days.")
        self.log(
            f"Current LP range: ({self.lp_range[0]}, {self.lp_range[1]}) -> "
            f"holding period: {self.holding_period} days."
        )

        self.pool_fee_tier: int = pool_fee_tier
        self.pool_fee_tier_percentage: float = get_tier_percentage(tier=pool_fee_tier)
        self.token0_decimals: int = token0_decimals
        self.token1_decimals: int = token1_decimals
        self.gas_for_swap_event: int = gas_for_swap_event

        # Store data.
        self.calculated_fees: list = []
        self.cumulative_fees: list = []
        self.bar_executed: int = 0
        self.order = None
        self.last_hp_price: float = 1e20

        # Data from data feed.
        self.data_id: int = 0
        self.data_open = self.datas[self.data_id].open
        self.data_low = self.datas[self.data_id].low
        self.data_high = self.datas[self.data_id].high
        self.data_close = self.datas[self.data_id].close
        self.data_volume = self.datas[self.data_id].volume
        self.data_tvl = self.datas[self.data_id].tvl
        self.data_fees = self.datas[self.data_id].fees
        self.data_liquidity = self.datas[self.data_id].liquidity
        self.data_token0_price = self.datas[self.data_id].token0_price
        self.data_token1_price = self.datas[self.data_id].token1_price
        self.data_tick = self.datas[self.data_id].tick
        self.gas_price_in_wei = self.datas[self.data_id].wei
        self.gas_price_in_gwei = self.datas[self.data_id].gwei

    def log(self, txt, dt=None) -> None:
        """
        Logging function.

        :param txt:
        :param dt:
        :return: None.
        """
        dt = dt or self.datas[0].datetime.date(0)
        logging.info(f"{dt.isoformat()}: {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            self.log(f"ORDER ACCEPTED/SUBMITTED", dt=order.created.dt)
            self.order = order
            return

        if order.status in [order.Expired]:
            self.log("BUY EXPIRED")

        # Check if an order has been completed.
        # Attention: broker could reject order if not enough cash.
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"BUY EXECUTED, price: {order.executed.price:.2f}, "
                    f"cost: {order.executed.value:.2f}, "
                    f"comm: {order.executed.comm:.2f}."
                )
            elif order.issell():
                self.log(
                    f"SELL EXECUTED, price: {order.executed.price:.2f}, "
                    f"cost: {order.executed.value:.2f}, "
                    f"comm: {order.executed.comm:.2f}."
                )

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        # None pending order -> new order is allowed.
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def start(self):
        # For swapping 50% of USD(C) -> (W)ETH
        initial_swap_cost: float = (self.gas_for_swap_event * float(Web3.fromWei(self.gas_price_in_wei[0], "ether"))) * self.data_token1_price[0]
        self.broker.add_cash(-round(initial_swap_cost, 2))

    def next(self):
        fee: Optional[float] = None

        # Target amount = available cash.
        target_amount: float = self.broker.get_cash()

        # Price assumption value.
        p: float = 1 / (
            tick_to_price(self.data_tick[0])
            / (10 ** (self.token1_decimals - self.token0_decimals))
        )
        # Price lower bound.
        pl: float = p * (1 - abs(self.lp_range[0]))
        # Price upper bound.
        pu: float = p * (1 + abs(self.lp_range[1]))
        # Price of X (token1) in USD.
        price_usd_x: float = self.data_token1_price[0]
        # Price of Y (token0) in USD.
        price_usd_y: float = self.data_token0_price[0]

        # TODO: Assume token1 is ETH(WETH) and token0 is USDC - this will break generalisation for now.
        # Check if ETH is increasing.
        if self.data_token1_price[0] > self.last_hp_price:
            # ETH trend is up -> hold USD / USDC / cash.
            pass

        # Stake in the pool.
        else:
            # Estimated amounts of token1 and token0.
            amount0, amount1 = get_token_amounts_from_deposit_amounts(
                price=p,
                price_lower_bound=pl,
                price_upper_bound=pu,
                price_usd_x=price_usd_x,
                price_usd_y=price_usd_y,
                target_amount=target_amount,
            )

            sqrt_ratio_x96: float = get_sqrt_price_x96(
                price=p,
                token0_decimal=self.token0_decimals,
                token1_decimal=self.token1_decimals,
            )
            sqrt_ratio_ax96: float = get_sqrt_price_x96(
                price=pl,
                token0_decimal=self.token0_decimals,
                token1_decimal=self.token1_decimals,
            )
            sqrt_ratio_bx96: float = get_sqrt_price_x96(
                price=pu,
                token0_decimal=self.token0_decimals,
                token1_decimal=self.token1_decimals,
            )

            delta_liquidity: float = get_liquidity_for_amounts(
                sqrt_ratio_x96=sqrt_ratio_x96,
                sqrt_ratio_ax96=sqrt_ratio_ax96,
                sqrt_ratio_bx96=sqrt_ratio_bx96,
                amount0=amount0,
                token0_decimals=self.token1_decimals,
                amount1=amount1,
                token1_decimals=self.token0_decimals,
            )

            fee: float = calculate_fee(
                delta_liquidity=delta_liquidity,
                liquidity=self.data_liquidity[0],
                volume=self.data_volume[0],
                pool_fee_tier=self.pool_fee_tier,
            )

            self.calculated_fees.append(fee)

        self.bar_executed += 1

        if self.bar_executed == self.holding_period:

            if self.data_token1_price[0] > self.last_hp_price:
                pass
            else:
                if self.bar_executed == 1:
                    cumulated_fees: float = fee
                else:
                    cumulated_fees: float = sum(
                        self.calculated_fees[-self.bar_executed :]
                    )

                # Add fee to cash.
                self.broker.add_cash(cash=cumulated_fees)

            self.last_hp_price: float = self.data_token1_price[0]
            self.bar_executed: int = 0

        # Log some values for the reference.
        self.log(
            f"Close: ${self.data_close[0]:.2f}, "
            f"DrawDown: {self.stats.drawdown.drawdown[0]:.2f}, "
            f"MaxDrawDown: {self.stats.drawdown.maxdrawdown[0]:.2f}"
            f"{f', Fee: ${self.calculated_fees[-1]:.2f}, ' if fee else ', '}"
            f"Cash: ${self.broker.get_cash():.2f}"
        )


class Bonus2Strategy(Strategy):
    def __init__(
        self,
        lp_range: list[float],
        pool_fee_tier: int,
        token0_decimals: int,
        token1_decimals: int,
        gas_for_swap_event: int,
        gas_for_mint_event: int,
        gas_for_burn_event: int,
    ) -> None:
        """
        Keep a reference to the "close" line in the data[0] data series.
        """
        self.log("Initializing Bonus1Strategy.")

        # Holding period (rebalancing window) - heuristic approach based on LP range.
        # See: https://twitter.com/guil_lambert/status/1564988772713992193
        # 1 day [0, 12]%
        # 1 week (12, 25]%
        # 1 month (25, inf)%
        self.lp_range: list[float] = lp_range
        if abs(self.lp_range[0]) <= 0.12:
            self.holding_period: int = 1
        elif 0.12 < abs(self.lp_range[0]) <= 0.25:
            self.holding_period: int = 7
        else:
            self.holding_period: int = 30
        self.log(f"Heuristic approach for holding period:")
        self.log(f"    LP range <= 12% -> holding period = 1 day.")
        self.log(f"    12% < LP range <= 25% -> holding period = 7 days.")
        self.log(f"    25% < LP range <= inf% -> holding period = 30 days.")
        self.log(
            f"Current LP range: ({self.lp_range[0]}, {self.lp_range[1]}) -> "
            f"holding period: {self.holding_period} days."
        )

        self.pool_fee_tier: int = pool_fee_tier
        self.pool_fee_tier_percentage: float = get_tier_percentage(tier=pool_fee_tier)
        self.token0_decimals: int = token0_decimals
        self.token1_decimals: int = token1_decimals
        self.gas_for_swap_event: int = gas_for_swap_event
        self.gas_for_mint_event: int = gas_for_mint_event
        self.gas_for_burn_event: int = gas_for_burn_event

        # Store data.
        self.calculated_fees: list = []
        self.cumulative_fees: list = []
        self.bar_executed: int = 0
        self.order = None
        self.last_hp_price: float = 1e20

        # Data from data feed.
        self.data_id: int = 0
        self.data_open = self.datas[self.data_id].open
        self.data_low = self.datas[self.data_id].low
        self.data_high = self.datas[self.data_id].high
        self.data_close = self.datas[self.data_id].close
        self.data_volume = self.datas[self.data_id].volume
        self.data_tvl = self.datas[self.data_id].tvl
        self.data_fees = self.datas[self.data_id].fees
        self.data_liquidity = self.datas[self.data_id].liquidity
        self.data_token0_price = self.datas[self.data_id].token0_price
        self.data_token1_price = self.datas[self.data_id].token1_price
        self.data_tick = self.datas[self.data_id].tick
        self.gas_price_in_wei = self.datas[self.data_id].wei
        self.gas_price_in_gwei = self.datas[self.data_id].gwei

    def log(self, txt, dt=None) -> None:
        """
        Logging function.

        :param txt:
        :param dt:
        :return: None.
        """
        dt = dt or self.datas[0].datetime.date(0)
        logging.info(f"{dt.isoformat()}: {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            self.log(f"ORDER ACCEPTED/SUBMITTED", dt=order.created.dt)
            self.order = order
            return

        if order.status in [order.Expired]:
            self.log("BUY EXPIRED")

        # Check if an order has been completed.
        # Attention: broker could reject order if not enough cash.
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"BUY EXECUTED, price: {order.executed.price:.2f}, "
                    f"cost: {order.executed.value:.2f}, "
                    f"comm: {order.executed.comm:.2f}."
                )
            elif order.issell():
                self.log(
                    f"SELL EXECUTED, price: {order.executed.price:.2f}, "
                    f"cost: {order.executed.value:.2f}, "
                    f"comm: {order.executed.comm:.2f}."
                )

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        # None pending order -> new order is allowed.
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def start(self):
        # For swapping 50% of USD(C) -> (W)ETH
        initial_swap_cost: float = (self.gas_for_swap_event * float(Web3.fromWei(self.gas_price_in_wei[0], "ether"))) * self.data_token1_price[0]
        self.broker.add_cash(-round(initial_swap_cost, 2))

    def next(self):
        fee: Optional[float] = None

        # Price assumption value.
        p: float = 1 / (
            tick_to_price(self.data_tick[0])
            / (10 ** (self.token1_decimals - self.token0_decimals))
        )
        # Price lower bound.
        pl: float = p * (1 - abs(self.lp_range[0]))
        # Price upper bound.
        pu: float = p * (1 + abs(self.lp_range[1]))
        # Price of X (token1) in USD.
        price_usd_x: float = self.data_token1_price[0]
        # Price of Y (token0) in USD.
        price_usd_y: float = self.data_token0_price[0]

        # TODO: Assume token1 is ETH(WETH) and token0 is USDC - this will break generalisation for now.
        # Check if ETH is increasing.
        if self.data_token1_price[0] > self.last_hp_price:
            # ETH trend is up -> hold USD / USDC / cash.
            mint_price: float = 0.0
            burn_price: float = 0.0

        # Stake in the pool.
        else:
            # Calc Mint & Burn costs.
            mint_price: float = (self.gas_for_mint_event * float(
                Web3.fromWei(self.gas_price_in_wei[0], "ether"))) * self.data_token1_price[0]
            burn_price: float = (self.gas_for_burn_event * float(
                Web3.fromWei(self.gas_price_in_wei[0], "ether"))) * self.data_token1_price[0]

            # Target amount = available cash.
            target_amount: float = self.broker.get_cash()

            # Estimated amounts of token1 and token0.
            amount0, amount1 = get_token_amounts_from_deposit_amounts(
                price=p,
                price_lower_bound=pl,
                price_upper_bound=pu,
                price_usd_x=price_usd_x,
                price_usd_y=price_usd_y,
                target_amount=target_amount,
            )

            sqrt_ratio_x96: float = get_sqrt_price_x96(
                price=p,
                token0_decimal=self.token0_decimals,
                token1_decimal=self.token1_decimals,
            )
            sqrt_ratio_ax96: float = get_sqrt_price_x96(
                price=pl,
                token0_decimal=self.token0_decimals,
                token1_decimal=self.token1_decimals,
            )
            sqrt_ratio_bx96: float = get_sqrt_price_x96(
                price=pu,
                token0_decimal=self.token0_decimals,
                token1_decimal=self.token1_decimals,
            )

            delta_liquidity: float = get_liquidity_for_amounts(
                sqrt_ratio_x96=sqrt_ratio_x96,
                sqrt_ratio_ax96=sqrt_ratio_ax96,
                sqrt_ratio_bx96=sqrt_ratio_bx96,
                amount0=amount0,
                token0_decimals=self.token1_decimals,
                amount1=amount1,
                token1_decimals=self.token0_decimals,
            )

            fee: float = calculate_fee(
                delta_liquidity=delta_liquidity,
                liquidity=self.data_liquidity[0],
                volume=self.data_volume[0],
                pool_fee_tier=self.pool_fee_tier,
            )

            self.calculated_fees.append(fee)

        self.bar_executed += 1

        if self.bar_executed == self.holding_period:

            if self.data_token1_price[0] > self.last_hp_price:
                pass
            else:
                if self.bar_executed == 1:
                    cumulated_fees: float = fee
                else:
                    cumulated_fees: float = sum(
                        self.calculated_fees[-self.bar_executed :]
                    )

                # Add fee to cash.
                self.broker.add_cash(cash=cumulated_fees - mint_price - burn_price)

            self.last_hp_price: float = self.data_token1_price[0]
            self.bar_executed: int = 0

        # Log some values for the reference.
        self.log(
            f"Close: ${self.data_close[0]:.2f}, "
            f"DrawDown: {self.stats.drawdown.drawdown[0]:.2f}, "
            f"MaxDrawDown: {self.stats.drawdown.maxdrawdown[0]:.2f}"
            f"{f', Fee: ${self.calculated_fees[-1]:.2f}, ' if fee else ', '}"
            f"Cash: ${self.broker.get_cash():.2f}"
        )


class TestStrategy(Strategy):
    params = (("maperiod", 15),)

    def log(self, txt, dt=None) -> None:
        """
        Logging function.

        :param txt:
        :param dt:
        :return: None.
        """
        dt = dt or self.datas[0].datetime.date(0)
        logging.info(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """
        Keep a reference to the "close" line in the data[0] data series.
        """
        self.data_close = self.datas[0].close

        # To keep track of pending orders
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # Add a MovingAverageSimple indicator
        self.sma = MovingAverageSimple(self.datas[0], period=self.params.maperiod)

        # Indicators for the plotting show
        bt.indicators.ExponentialMovingAverage(self.datas[0], period=25)
        bt.indicators.WeightedMovingAverage(self.datas[0], period=25, subplot=True)
        bt.indicators.StochasticSlow(self.datas[0])
        bt.indicators.MACDHisto(self.datas[0])
        rsi = bt.indicators.RSI(self.datas[0])
        bt.indicators.SmoothedMovingAverage(rsi, period=10)
        bt.indicators.ATR(self.datas[0], plot=False)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY EXECUTED: {order.executed.price:.2f}")
            elif order.issell():
                self.log(f"SELL EXECUTED: {order.executed.price:.2f}")

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        # Write down: no pending order
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def next(self):
        # Simply log the closing price of the series from the reference
        self.log(
            f"Close: {self.data_close[0]:.2f}, "
            f"DrawDown: {self.stats.drawdown.drawdown[-1]:.2f}, "
            f"MaxDrawDown: {self.stats.drawdown.maxdrawdown[-1]:.2f}"
        )

        # Check if an order is pending ... if yes, we cannot send a 2nd one
        if self.order:
            return

        # Check if we are in the market
        if not self.position:

            # Not yet ... we MIGHT BUY if ...
            if self.data_close[0] > self.sma[0]:

                # BUY, BUY, BUY!!! (with all possible default parameters)
                self.log(f"BUY CREATE: {self.data_close[0]:.2f}")

                # Keep track of the created order to avoid a 2nd order
                self.order = self.buy()

        else:
            # Already in the market ... we might sell
            if self.data_close[0] < self.sma[0]:
                # SELL, SELL, SELL!!! (with all possible default parameters)
                self.log(f"SELL CREATE: {self.data_close[0]:.2f}")

                # Keep track of the created order to avoid a 2nd order
                self.order = self.sell()
