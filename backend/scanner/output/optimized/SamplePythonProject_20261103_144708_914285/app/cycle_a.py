from app.cycle_b import helper_value


def first_step(items):
    """
    Calculate the total by multiplying each item by 4 and adding the helper value.

    Args:
        items (list): A list of numbers to process.

    Returns:
        int: The calculated total sum.
    """
    total = 0
    for item in items:
        total += item * 4
    return total + helper_value