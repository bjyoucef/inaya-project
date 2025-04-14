def build_pairs(
    entries, exits_list, employee, current_date, next_day_records, next_date
):
    default_ref_start = (
        employee.reference_start if employee.reference_start else datetime_time(8, 0)
    )
    default_ref_end = (
        employee.reference_end if employee.reference_end else datetime_time(16, 0)
    )

    pairs = []
    entry_idx, exit_idx = 0, 0
    while entry_idx < len(entries):
        entry = entries[entry_idx]
        exit_time = None
        is_real_exit = False
        # Check current day's exits
        while exit_idx < len(exits_list):
            if exits_list[exit_idx] > entry:
                exit_time = exits_list[exit_idx]
                is_real_exit = True
                exit_idx += 1
                break
            exit_idx += 1
        # Check next day's attendances
        if not exit_time:
            for next_att in next_day_records:
                if (
                    next_att.check_time.date() == next_date
                    and next_att.check_time.time() < default_ref_start
                ):
                    exit_time = next_att.check_time
                    is_real_exit = True
                    break
        # Apply penalty if no exit found
        if not exit_time:
            if default_ref_end > default_ref_start:
                naive_exit = datetime.combine(
                    entry.date(), default_ref_end
                ) - timedelta(hours=4)
            else:
                naive_exit = (
                    datetime.combine(entry.date(), default_ref_end)
                    + timedelta(days=1)
                    - timedelta(hours=4)
                )
            exit_time = timezone.make_aware(naive_exit)
            is_real_exit = False
        pairs.append((entry, exit_time, is_real_exit))
        entry_idx += 1
    return pairs
