# References
## Backtrader
- matplotlib bug -> poetry: build from GIT master branch
- reports: https://github.com/verybadsoldier/backtrader_plotting
- Escape from OHLC Land: https://www.backtrader.com/blog/posts/2016-03-08-escape-from-ohlc-land/escape-from-ohlc-land/

## Uniswap v3
- Whitepaper: https://uniswap.org/whitepaper-v3.pdf
- Fee simulator: https://www.metacrypt.org/tools/uniswap-v3-calculator-simulator/?network=ethereum&token0=0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2&token1=0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48&feeTier=3000
- Strategy simulator: https://defi-lab.xyz/uniswapv3simulator
- Staking optimisation for investors with Themis: https://blog.themis.exchange/how-to-earn-398-apy-on-usdc-eth-using-uniswap-v3-themis-9797c05a28f3
- When Uniswap v3 returns more fees for passive LPs: https://uniswap.org/SuperiorReturnsForLiquidityProviders.pdf
- Liquidity math: http://atiselsts.github.io/pdfs/uniswap-v3-liquidity-math.pdf
- Liquidity formula explained: https://atiselsts.medium.com/uniswap-v3-liquidity-formula-explained-de8bd42afc3c
- https://medium.com/coinmonks/a-real-world-framework-for-backtesting-uniswap-v3-strategies-88825abdcd17

## Task
Please create a program that will (crudely) backtest a simple Uniswap V3 strategy with real data.
Our objective is to backtest how different trading ranges perform historically when invested
 (singlesided) USDC into the UNIV3-ETH-USDC pool.

# Simple strategy
Specifically, assume your investment asset is USDC and you invested  in the UniV3 USDC-ETH pool
(i.e. you swapped half your USDC balance for ETH and deposited the two tokens into UniV3-ETH-USDC).
You set an LP range (such as +/- 10%)  at the beginning of each rebalance window,
your range is reset based on the ETH price at the beginning of the rebalance window.

A possible function call for the backtest could be

backTestUniv3(asset=’USDC’, pools=[‘eth-usdc’], range=[-0.10, 0.10], from=startBlock, to=endBlock]

This function should return:
Return series (plotted)
Total Returns
Sharp Ratio
Max Draw Down

# Bonus1 strategy
Now assume that each rebalance window we can choose one of two strategies:

STRATEGY 2:
- Invest in the UNIV3-ETH-USDC (by swapping half USDC to ETH) based on the range defined
- HODL USDC

The decision algorithm is simple.
If ETH price went up (in USDC) in previous rebalance window, then HODL (i.e. Strategy 2). Otherwise Strategy 1.


# Bonus2 strategy
Add gas and slippage costs. The starting USDC balance becomes an input to the backtest.

Please let us know if you have any questions