    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = ConfigDate.objects.get(user=self.request.user, page="pointage")

        # Si end_date n'est pas défini, on le force à start_date ou à la date d'aujourd'hui
        if not config.end_date:
            config.end_date = config.start_date or date.today()
            config.save()
        start_date, end_date = self.get_date_range(config)
        work_days = self.get_work_days(start_date, end_date)

        # Récupère les employés présents dans le queryset (afin d'éviter les doublons)
        employee_ids = self.get_queryset().values_list("employee", flat=True).distinct()
        employees = Employee.objects.filter(id__in=employee_ids).prefetch_related(
            "attendances"
        )
        report = []
        for employee in employees:
            # On travaille sur tous les pointages de l'employé dans la plage demandée
            days = self.calculate_working_hours(
                employee.attendances.all(), employee, start_date, end_date
            )
            totals = self.calculate_totals(days)
            report.append(
                {
                    "employee": employee,
                    "days": days,
                    "totals": {
                        "hours": totals["total_work"],
                        "overtime": totals["total_overtime"],
                        "late": totals["total_late"],
                        "absence": len(work_days - totals["work_days"]),
                    },
                }
            )
        context.update(
            {
                "report": report,
                "config": config,
                "date_range": f"{start_date} - {end_date}",
                "employees": Employee.objects.all(),  # Pour alimenter le sélecteur dans le template
            }
        )
        return context
