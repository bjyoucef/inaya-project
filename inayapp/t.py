def rapport_pointage(request):
    # ... (code existant jusqu'à holidays_set = set(holidays))

    report = []
    for personnel in personnels_qs:
        employee = personnel.employee
        ref_start = employee.reference_start or time(8, 0)
        ref_end = employee.reference_end or time(16, 0)
        dur_ref_sec = (
            datetime.combine(date.today(), ref_end)
            - datetime.combine(date.today(), ref_start)
        ).total_seconds()
        journalier_hours_ref = Decimal(dur_ref_sec) / Decimal(3600)

        emp_data = {
            "personnel": personnel,
            "days": [],
            "totals": {
                # ... (autres totaux existants)
                "total_working_days_heures": 0,
                "taux_horaire": Decimal(0),
                "jours_ouvrables": 0,
                "jours_travailles": 0,
            },
            "salaire": {
                "salaire_base": Decimal(0),
                "salaire_brut": Decimal(0),
                "salaire_net": Decimal(0),
                "indemnites": {"repas": Decimal(0), "transport": Decimal(0)},
                "deductions": {"irg": Decimal(0), "cnas": Decimal(0)},
            },
        }

        current_date = start_date
        while current_date <= end_date:
            # ... (code existant de traitement journalier)

            # Calcul des indicateurs de jour
            is_worked_day = len(entries) > 0
            is_working_day = not is_weekend and not is_holiday

            if is_working_day:
                emp_data["totals"]["jours_ouvrables"] += 1
                if is_worked_day:
                    emp_data["totals"]["jours_travailles"] += 1

            # ... (code existant de traitement des pointages)
        # Calculate total worked hours, late, early leave, overtime
        total_worked_hours = emp_data["totals"]["hours"]
        total_late = emp_data["totals"]["late"]  # in minutes
        total_early_leave = emp_data["totals"]["early_leave"]  # in minutes
        total_overtime = emp_data["totals"]["overtime"]  # in hours
        # Calculs finaux après traitement de tous les jours
        try:
            config = GlobalSalaryConfig.get_latest_config()

            # 1. Calcul des heures de référence totales
            total_ref_hours = (
                emp_data["totals"]["jours_ouvrables"] * journalier_hours_ref
            )
            emp_data["totals"]["total_working_days_heures"] = total_ref_hours

            # 2. Calcul du taux horaire
            if total_ref_hours > 0:
                emp_data["totals"]["taux_horaire"] = (
                    Decimal(personnel.salaire) / total_ref_hours
                )
            else:
                emp_data["totals"]["taux_horaire"] = Decimal(0)

            # 3. Calcul des indemnités
            emp_data["salaire"]["indemnites"]["repas"] = calculer_repas(
                emp_data["totals"]["jours_travailles"]
            )
            emp_data["salaire"]["indemnites"]["transport"] = calculer_transport(
                emp_data["totals"]["jours_travailles"]
            )

            # 4. Calcul du salaire de base
            base_salary = emp_data["totals"]["taux_horaire"] * total_ref_hours
            emp_data["salaire"]["salaire_base"] = base_salary

            # 5. Calcul des heures supplémentaires
            regular_overtime_amount = (
                emp_data["totals"]["regular_overtime"]
                * config.overtime_hourly_rate
                * Decimal(1.5)
            )
            public_holiday_amount = (
                emp_data["totals"]["public_holiday_overtime"]
                * config.overtime_hourly_rate
                * Decimal(2)
            )
            total_overtime = regular_overtime_amount + public_holiday_amount

            # 6. Salaire brut
            brut = (
                base_salary
                + emp_data["salaire"]["indemnites"]["repas"]
                + emp_data["salaire"]["indemnites"]["transport"]
                + total_overtime
            )
            emp_data["salaire"]["salaire_brut"] = brut

            # 7. Déductions
            emp_data["salaire"]["deductions"]["irg"] = calculer_irg(brut)
            emp_data["salaire"]["deductions"]["cnas"] = calculer_cnas_employee(brut)

            # 8. Salaire net
            net = (
                brut
                - emp_data["salaire"]["deductions"]["irg"]
                - emp_data["salaire"]["deductions"]["cnas"]
                - emp_data["totals"]["penalites"]
            )
            emp_data["salaire"]["salaire_net"] = net

        except Exception as e:
            logger.error(f"Erreur calcul salaire: {str(e)}")

        report.append(emp_data)

    # ... (code existant de retour)
