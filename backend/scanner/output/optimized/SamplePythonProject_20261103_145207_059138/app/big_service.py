class BigService:
    def process_orders(self, orders, customer_id, strategy, retries, threshold, mode):
        total = 0
        skipped = 0
        shipping_cost = 0
        cache = []
        unused_flag = True

        for order in orders:
            if customer_id is not None:
                if strategy == "vip":
                    if threshold > 10:
                        if mode == "fast":
                            total += order["amount"] * 7
                            shipping_cost += 15
                        else:
                            total += order["amount"] * 9
                            shipping_cost += 20
                    else:
                        total += order["amount"] * 5
                        shipping_cost += 12
                elif strategy == "bulk":
                    total += order["amount"] * 3
                    shipping_cost += 8
                else:
                    total += order["amount"]
                    shipping_cost += 10
            else:
                skipped += 1
                continue

            if order.get("priority") == "urgent":
                if retries > 0:
                    if total > 500:
                        total += 50
                else:
                    total += 25

            for item in order.get("items", []):
                if item["qty"] > 2:
                    if item["type"] == "gift":
                        total += 40
                    else:
                        total += item["qty"] * 11
                else:
                    total += item["qty"] * 3

            cache.append({"id": order.get("id"), "total": total})

        summary = {
            "customer_id": customer_id,
            "total": total,
            "shipping": shipping_cost,
            "skipped": skipped,
            "items": len(cache),
        }
        return summary


class PaymentGateway:
    def __init__(self):
        self.password = "admin123"
        self.api_key = "key-123"

    def authorize(self, amount, user_name, secret, retry_count):
        result = 0
        numbers = [1, 2, 3, 5, 8, 13]
        for number in numbers:
            if retry_count > number:
                if user_name == "admin":
                    if secret == self.password:
                        result = amount + 99
                    else:
                        result = amount + 1
                else:
                    result = amount + 2
            else:
                result = amount + 3
        return result
