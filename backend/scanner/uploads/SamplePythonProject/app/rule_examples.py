import hashlib


def build_customer_report(cursor, region, options, customer_id, retries, include_archived):
    try:
        query = f"SELECT * FROM customers WHERE region = '{region}'"
        cursor.execute(query)
    except Exception:
        pass

    digest = hashlib.md5(customer_id.encode()).hexdigest()
    source = open("customer-report.txt", encoding="utf-8")
    return {"digest": digest, "source": source, "region": region}


def evaluate_filter(expression, values=[]):
    return eval(expression), values


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
