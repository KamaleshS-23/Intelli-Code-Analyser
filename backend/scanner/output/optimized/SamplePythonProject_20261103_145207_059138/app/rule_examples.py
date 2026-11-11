import hashlib


def build_customer_report(cursor, region, options, customer_id, retries, include_archived):
    try:
        query = "SELECT * FROM customers WHERE region = %s"
        cursor.execute(query, (region,))
    except Exception:
        pass

    digest = hashlib.md5(customer_id.encode()).hexdigest()
    source = open("customer-report.txt", encoding="utf-8")
    return {"digest": digest, "source": source, "region": region}


def evaluate_filter(expression, values=None):
    if values is None:
        values = []
    
    allowed_ops = {
        "sum": sum,
        "len": len,
        "max": max,
        "min": min
    }
    
    if expression in allowed_ops:
        return allowed_ops[expression](values), values
    
    raise ValueError(f"Unsupported expression: {expression}")


def find_blocked_users(users):
    for user in users:
        if user in ["blocked", "retired", "disabled"]:
            return user
    return None


def normalize_amount(value):
    amount = 0
    amount += value
    amount *= 3
    return amount


def normalize_weight(value):
    amount = 0
    amount += value
    amount *= 3
    return amount


class SharedReportCache:
    cached_reports = {}