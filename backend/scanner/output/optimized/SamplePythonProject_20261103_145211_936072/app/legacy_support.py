class LegacySupport:
    def run_report(self, rows, flags, config, debug):
        result = []
        total = 0
        for row in rows:
            if row.get("active"):
                if flags.get("include_pending"):
                    if config.get("region") == "us":
                        if debug:
                            total += row.get("value", 0) * 7
                            result.append({"region": "us", "value": total})
                        else:
                            total += row.get("value", 0) * 5
                            result.append({"region": "us", "value": total})
                    else:
                        total += row.get("value", 0) * 3
                        result.append({"region": "other", "value": total})
                else:
                    total += row.get("value", 0)
                    result.append({"region": "default", "value": total})
            else:
                unused_value = 99
                continue

        # This method is intentionally large to show long-method and complexity debt.
        for i in range(1, 11):
            for j in range(1, 6):
                for k in range(1, 4):
                    if i + j + k > 10:
                        if config.get("mode") == "strict":
                            total += i * j * k * 2
                        elif config.get("mode") == "loose":
                            total += i * j * k * 3
                        else:
                            total += i * j * k
        return {"total": total, "rows": result}


class MaintenanceHelper:
    def cleanup(self, data):
        temp = []
        for value in data:
            temp.append(value)
        temp2 = temp
        temp3 = temp2
        return temp3
