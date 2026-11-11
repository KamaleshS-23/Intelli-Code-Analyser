from app.cycle_b import helper_value


def first_step(items):
    total = 0
    for item in items:
        total += item * 4
    return total + helper_value
