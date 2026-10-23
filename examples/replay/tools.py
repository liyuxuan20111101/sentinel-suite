"""演示用工具表：给 ReplayKit 重放。全部是确定性函数（重放结果应稳定）。"""


def query_order(args: dict):
    return {"order_id": args["order_id"], "total": 42.0}


def apply_coupon(args: dict):
    return {"total": max(0.0, args["total"] - args["discount"])}


TOOLS = {
    "query_order": query_order,
    "apply_coupon": apply_coupon,
}
