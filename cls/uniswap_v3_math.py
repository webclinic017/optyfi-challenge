from typing import Final

TICK_BASE: Final[float] = 1.0001
Q96: Final[int] = 2**96


def get_liquidity_0(x: float, sa: float, sb: float) -> float:
    return x * sa * sb / (sb - sa)


def get_liquidity_1(y: float, sa: float, sb: float) -> float:
    return y / (sb - sa)


def get_liquidity(x: float, y: float, p: float, a: float, b: float) -> float:
    sp: float = p**0.5
    sa: float = a**0.5
    sb: float = b**0.5

    if sp <= sa:
        liquidity: float = get_liquidity_0(x, sa, sb)
    elif sp < sb:
        liquidity0: float = get_liquidity_0(x, sp, sb)
        liquidity1: float = get_liquidity_1(y, sa, sp)
        liquidity: float = min(liquidity0, liquidity1)
    else:
        liquidity: float = get_liquidity_1(y, sa, sb)
    return liquidity


def calculate_fee(
    delta_liquidity: float,
    liquidity: float,
    volume: float,
    pool_fee_tier: float,
) -> float:
    fee_tier_percentage: float = get_tier_percentage(pool_fee_tier)
    liquidity_percentage: float = delta_liquidity / (liquidity + delta_liquidity)
    fee: float = fee_tier_percentage * volume * liquidity_percentage
    return fee


def get_tier_percentage(tier: float) -> float:
    if tier == 100:
        return 0.01 / 100.0
    elif tier == 500:
        return 0.05 / 100.0
    elif tier == 3000:
        return 0.3 / 100.0
    elif tier == 10000:
        return 1.0 / 100.0
    else:
        return 0.0


def fee_tier_to_tick_spacing(fee_tier) -> int:
    return {100: 1, 500: 10, 3000: 60, 10000: 200}.get(fee_tier, 60)


def get_token_amounts(
    tick: float,
    liquidity: float,
    token0_decimals: int,
    token1_decimals: int,
    fee_tier: int,
) -> tuple[float, float]:
    tick_spacing: int = fee_tier_to_tick_spacing(fee_tier)
    tick_a = (int(tick / tick_spacing)) * tick_spacing
    tick_b = tick_a + tick_spacing
    sqrt_b = TICK_BASE ** (tick_b / 2) * (2**96)
    sqrt_a = TICK_BASE ** (tick_a / 2) * (2**96)
    amount0: float = (
        liquidity * 2**96 * (sqrt_b - sqrt_a) / sqrt_b / sqrt_a
    ) / 10**token0_decimals
    amount1: float = liquidity * (sqrt_b - sqrt_a) / 2**96 / 10**token1_decimals
    return amount0, amount1


def tick_to_price(tick) -> float:
    """
    Convert Uniswap v3 tick to a price (i.e. the ratio between the amounts of tokens: token1/token0).

    :param tick:
    :return:
    """
    return TICK_BASE**tick


def get_token_amounts_from_deposit_amounts(
    price: float,
    price_lower_bound: float,
    price_upper_bound: float,
    price_usd_x: float,
    price_usd_y: float,
    target_amount: float,
) -> tuple[float, float]:

    delta_l: float = target_amount / (
        (price**0.5 - price_lower_bound**0.5) * price_usd_y
        + (1 / price**0.5 - 1 / price_upper_bound**0.5) * price_usd_x
    )

    delta_y: float = delta_l * (price**0.5 - price_lower_bound**0.5)
    if delta_y * price_usd_y < 0.0:
        delta_y: float = 0.0
    if delta_y * price_usd_y > target_amount:
        delta_y: float = target_amount / price_usd_y

    delta_x: float = delta_l * (1 / price**0.5 - 1 / price_upper_bound**0.5)
    if delta_x * price_usd_x < 0.0:
        delta_x: float = 0.0
    if delta_x * price_usd_x > target_amount:
        delta_x: float = target_amount / price_usd_x

    return delta_x, delta_y


def expand_decimals(number: float, exponent: int) -> float:
    return number * 10**exponent


def get_sqrt_price_x96(price: float, token0_decimal: int, token1_decimal: int) -> float:
    token0: float = expand_decimals(price, token0_decimal)
    token1: float = expand_decimals(1, token1_decimal)
    return (token0 / token1) ** 0.5 * 2**96


def mul_div(a: float, b: float, multiplier: float) -> float:
    return a * b / multiplier


def get_liquidity_for_amount0(
    sqrt_ratio_ax96: float, sqrt_ratio_bx96: float, amount0: float
) -> float:
    intermediate: float = mul_div(sqrt_ratio_bx96, sqrt_ratio_ax96, Q96)
    return mul_div(amount0, intermediate, sqrt_ratio_bx96 - sqrt_ratio_ax96)


def get_liquidity_for_amount1(
    sqrt_ratio_ax96: float, sqrt_ratio_bx96: float, amount1: float
) -> float:
    return mul_div(amount1, Q96, sqrt_ratio_bx96 - sqrt_ratio_ax96)


def get_liquidity_for_amounts(
    sqrt_ratio_x96: float,
    sqrt_ratio_ax96: float,
    sqrt_ratio_bx96: float,
    amount0: float,
    token0_decimals: int,
    amount1: float,
    token1_decimals: int,
) -> float:
    amount0: float = expand_decimals(amount0, token0_decimals)
    amount1: float = expand_decimals(amount1, token1_decimals)

    if sqrt_ratio_x96 <= sqrt_ratio_ax96:
        liquidity0: float = get_liquidity_for_amount0(
            sqrt_ratio_x96, sqrt_ratio_bx96, amount0
        )
        liquidity1: float = get_liquidity_for_amount1(
            sqrt_ratio_ax96, sqrt_ratio_x96, amount1
        )
        liquidity: float = min(liquidity0, liquidity1)
    else:
        liquidity: float = get_liquidity_for_amount1(
            sqrt_ratio_ax96, sqrt_ratio_bx96, amount1
        )

    return liquidity
