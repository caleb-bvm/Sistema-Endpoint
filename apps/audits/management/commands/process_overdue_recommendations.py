from django.core.management.base import BaseCommand

from apps.audits.services import mark_overdue_recommendations


class Command(BaseCommand):
    help = "Marca como no cumplidas las recomendaciones sin respuesta cuyo plazo ya venció."

    def handle(self, *args, **options):
        count = mark_overdue_recommendations()
        result = (
            "1 recomendación marcada como no cumplida."
            if count == 1
            else f"{count} recomendaciones marcadas como no cumplidas."
        )
        self.stdout.write(self.style.SUCCESS(f"Proceso completado: {result}"))
