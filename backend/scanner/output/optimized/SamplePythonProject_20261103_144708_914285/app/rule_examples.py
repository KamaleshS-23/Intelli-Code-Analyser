def process_items(items, target_list):
    target_set = set(target_list)
    for item in items:
        if item in target_set:
            print(f"Found: {item}")