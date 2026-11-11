from app.shared import helper_value
from app.cycle_a import first_step


def second_step(items):
    """
    Process items by adding a helper value to the result of the first step.

    Args:
        items: The input data to be processed.

    Returns:
        The result of the first step incremented by the helper value.
    """
    return first_step(items) + helper_value