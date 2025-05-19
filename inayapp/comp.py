def traiter_jour(current_date, employee, holidays):
    is_holiday = current_date in holidays
    is_weekend = current_date.weekday() in [4, 5]

    ref_start = employee.reference_start or datetime_time(8, 0)
    ref_end = employee.reference_end or datetime_time(16, 0)

    attendances = Pointage.objects.filter(
        employee=employee, check_time__date=current_date
    ).order_by("check_time")
    next_day_att = Pointage.objects.filter(
        employee=employee, check_time__date=current_date + timedelta(days=1)
    ).order_by("check_time")

    entries, exits = classify_attendances(attendances, employee, current_date)
    pairs = build_pairs(
        entries,
        exits,
        employee,
        current_date,
        next_day_att,
        current_date + timedelta(days=1),
    )

    validated_overtime = non_validated_overtime = 0
    for entry, exit_point in pairs:
        entry_dt = entry.check_time
        exit_dt = get_dt(exit_point)
        dur = (exit_dt - entry_dt).total_seconds()
        if entry.ov_validated or getattr(exit_point, "ov_validated", False):
            validated_overtime += dur
        else:
            non_validated_overtime += dur

    # calcul des heures de référence vs overtime
    if is_holiday or is_weekend:
        total_sec_w = 0
        overtime_sec = sum(
            (get_dt(exit_p) - entry.check_time).total_seconds()
            for entry, exit_p in pairs
            if exit_p
        )
    else:
        total_sec_w = calculer_heures_reference(pairs, employee, current_date)
        # early / late overtime hors référence
        early = late = 0
        if entries and entries[0].check_time.time() < ref_start:
            early = (
                datetime.combine(current_date, ref_start) - entries[0].check_time
            ).total_seconds()
        if exits and exits[-1].check_time.time() > ref_end:
            late = (
                exits[-1].check_time - datetime.combine(current_date, ref_end)
            ).total_seconds()
        overtime_sec = early + late

    return {
        "date": current_date,
        "is_holiday": is_holiday,
        "is_weekend": is_weekend,
        "pairs": pairs,
        "total_seconds_w": total_sec_w,
        "overtime_seconds": overtime_sec,
        "validated_overtime": validated_overtime,
        "non_validated_overtime": non_validated_overtime,
        # … (le reste de votre dict reste inchangé)
    }
