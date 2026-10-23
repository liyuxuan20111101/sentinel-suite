"""演示用「旧版本」：VIP 九折，满 100 再减 10。"""


def final_price(price: float, vip: bool) -> float:
    total = price * (0.9 if vip else 1.0)
    if total >= 100:
        total -= 10
    return round(total, 2)
