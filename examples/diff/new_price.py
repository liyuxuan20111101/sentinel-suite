"""演示用「AI 改过的新版本」：看起来只是加了防御，实际改了负价订单的行为。"""


def final_price(price: float, vip: bool) -> float:
    if price <= 0:
        return 0.0  # AI "顺手"加的：负价直接抹零（改了对外行为！）
    total = price * (0.9 if vip else 1.0)
    if total >= 100:
        total -= 10
    return round(total, 2)
