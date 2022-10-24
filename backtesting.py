import logging
from datetime import datetime

import backtrader as bt
import quantstats as qs
from backtrader import Cerebro
from backtrader_plotting import Bokeh

from cls.daily_data_feed import PandasDataFeedDaily
from strategies import Bonus1Strategy, Bonus2Strategy, SimpleStrategy
from cls.uniswap_v3 import UniswapV3
from cls.utils import KnownStrategyNames


class BacktestUniswapV3:
    """
    BacktestUniswapV3 class.
    """

    def __init__(
        self,
        token_ticker: str,
        lp_range: list[float],
        with_all_ranges: bool,
        strategy_names: list[str],
        start_day: str,
        end_day: str,
        u3_instance: UniswapV3,
        with_graphs: bool = True,
        starting_cash: float = 10_000.0,
        commission: float = 0.0,
    ) -> None:
        self._token_ticker: str = token_ticker
        self._lp_range: list[float] = lp_range
        self._with_all_ranges: bool = with_all_ranges
        self._strategy_names: list[str] = strategy_names
        self._start_day: str = start_day
        self._end_day: str = end_day
        self._u3: UniswapV3 = u3_instance
        self._with_graphs: bool = with_graphs
        self._starting_cash: float = starting_cash
        self._commission: float = commission
        self._backtest_name: str = "uniswap_v3"
        self._results: dict = {}

    def _backtest(self, strategy_name: str) -> dict:
        """
        Backtest strategy.

        :param strategy_name: Strategy name.
        :return: Aggregated strategy statistics.
        """
        # Init Cerebro engine.
        cerebro: Cerebro = bt.Cerebro()

        # Add the trading strategy.
        if strategy_name == KnownStrategyNames.SIMPLE.value:
            logging.info(f"Selecting {strategy_name} strategy (compounding).")
            cerebro.addstrategy(
                SimpleStrategy,
                self._lp_range,
                self._u3.pool_fee_tier,
                self._u3.token0_decimals,
                self._u3.token1_decimals,
                self._u3.gas_for_swap_event,
            )
        elif strategy_name == KnownStrategyNames.BONUS1.value:
            cerebro.addstrategy(
                Bonus1Strategy,
                self._lp_range,
                self._u3.pool_fee_tier,
                self._u3.token0_decimals,
                self._u3.token1_decimals,
                self._u3.gas_for_swap_event,
            )
        elif strategy_name == KnownStrategyNames.BONUS2.value:
            cerebro.addstrategy(
                Bonus2Strategy,
                self._lp_range,
                self._u3.pool_fee_tier,
                self._u3.token0_decimals,
                self._u3.token1_decimals,
                self._u3.gas_for_swap_event,
                self._u3.gas_for_mint_event,
                self._u3.gas_for_burn_event,
            )
        else:
            logging.error(f"Unknown strategy: {strategy_name}.")
            raise Exception(f"Unknown strategy: {strategy_name}.")

        # Add data.
        feed: bt.feeds.PandasData = PandasDataFeedDaily(
            dataname=self._u3.combined_data_prices
        )
        cerebro.adddata(feed, name=self._backtest_name)

        # Set cash.
        cerebro.broker.setcash(cash=self._starting_cash)

        # Set sizer.
        cerebro.addsizer(bt.sizers.PercentSizer, percents=100)

        # Set commission.
        cerebro.broker.setcommission(commission=self._commission)

        # Add observers that are used in plots.
        cerebro.addobserver(bt.observers.DrawDown)

        # Add preferred analyzers for generating performance metrics for the strategy.
        cerebro.addanalyzer(
            bt.analyzers.SharpeRatio,
            _name="SharpeRatio",
            riskfreerate=0,
            timeframe=bt.TimeFrame.Days,
            compression=1,
            factor=365,
            annualize=True,
        )
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="DrawDown")
        cerebro.addanalyzer(bt.analyzers.PyFolio, _name="PyFolio")
        cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="AnnualReturn")

        # Backtest!
        logging.info(f"Starting portfolio value: {cerebro.broker.getvalue()}")
        results = cerebro.run()
        strat = results[0]
        returns, positions, transactions, gross_lev = strat.analyzers.getbyname(
            "PyFolio"
        ).get_pf_items()
        returns.index = returns.index.tz_convert(None)
        logging.info(
            f"Final portfolio value: ${cerebro.broker.getvalue():.2f} "
            f"(starting value: ${self._starting_cash:.2f})"
        )

        # Build statistics.
        statistics: dict = {
            "strategy_name": strategy_name,
            "total_returns": strat.analyzers.getbyname("AnnualReturn").rets,
            "sharpe_ratio": strat.analyzers.getbyname("SharpeRatio").rets[
                "sharperatio"
            ],
            "max_draw_down": strat.analyzers.getbyname("DrawDown").rets["max"][
                "drawdown"
            ],
            "with_graphs": self._with_graphs,
            "cash": strat.broker.get_cash(),
            "lp_range": abs(self._lp_range[0]),
        }

        # Plot the result.
        if self._with_graphs:
            quantstats_report_path: str = (
                f"./reports/{str(datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))}_"
                f"{strategy_name}_strategy_lp_range_{int(abs(self._lp_range[0])*100.0)}_quantstat_report.html"
            )
            statistics["quantstats_report_path"] = quantstats_report_path

            # Backtrader report.
            if not self._with_all_ranges:
                b: Bokeh = Bokeh(style="bar", plot_mode="single")
                cerebro.plot(b)

            # Quantstat report.
            qs.reports.html(
                returns,
                output=quantstats_report_path,
                download_filename=quantstats_report_path,
                title=strategy_name,
                periods_per_year=365,
            )

        return statistics

    def backtest_strategies(self) -> dict:
        """
        Execute all backtests with selected strategies.

        :return: Aggregated results.
        """
        for strategy_name in self._strategy_names:
            self._results[strategy_name] = self._backtest(strategy_name=strategy_name)
            logging.debug(
                f"Statistics for '{strategy_name}' strategy: {self._results[strategy_name]}"
            )

        return self._results
