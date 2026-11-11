class LegacySupport:
    """
    Provides legacy reporting functionality by processing row data based on 
    provided flags and configuration settings.
    """
    def run_report(self, rows, flags, config, debug):
        """
        Processes rows to generate a report based on flags, configuration, and debug status.

        Args:
            rows (list): A list of dictionaries containing row data.
            flags (dict): Configuration flags for processing logic.
            config (dict): Settings including region and mode.
            debug (bool): Toggle for debug-specific calculation multipliers.

        Returns:
            dict: A dictionary containing the calculated total and processed rows.
        """
        result = []
        total = 0
        for row in rows:
            if row.get("active"):
                if flags.get("include_pending"):
                    if config.get("region") == "us":
                        multiplier = 7 if debug else 5
                        total += row.get("value", 0) * multiplier
                        result.append({"region": "us", "value": total})
                    else:
                        total += row.get("value", 0) * 3
                        result.append({"region": "other", "value": total})
                else:
                    total += row.get("value", 0)
                    result.append({"region": "default", "value": total})
            else:
                continue

        total += self._calculate_matrix_total(config)
        return {"total": total, "rows": result}

    def _calculate_matrix_total(self, config):
        total = 0
        mode = config.get("mode")
        multiplier = 2 if mode == "strict" else (3 if mode == "loose" else 1)
        
        for i in range(1, 11):
            for j in range(1, 6):
                for k in range(1, 4):
                    if i + j + k > 10:
                        total += i * j * k * multiplier
        return total


class MaintenanceHelper:
    """
    Provides utility methods for data cleanup and maintenance operations.
    """
    def cleanup(self, data):
        """
        Performs a shallow copy of the provided data list.

        Args:
            data (list): The list of items to be cleaned/copied.

        Returns:
            list: A copy of the input data.
        """
        return list(data)