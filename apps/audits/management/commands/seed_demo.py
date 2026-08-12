import secrets
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.institutions.models import Organization

from ...models import AuditCase, Finding, Recommendation


class Command(BaseCommand):
    help = "Crea un expediente y usuarios locales para demostrar el flujo inicial."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Genera y asigna nuevas contraseñas a los usuarios de demostración.",
        )

    def handle(self, *args, **options):
        reset_passwords = options["reset_passwords"]
        password = None
        center, _ = Organization.objects.update_or_create(
            code="10754",
            defaults={
                "name": "Instituto Nacional de Nahuizalco",
                "kind": Organization.Kind.EDUCATIONAL_CENTER,
                "department": "Sonsonate",
                "municipality": "Nahuizalco",
            },
        )
        departmental, _ = Organization.objects.update_or_create(
            code="DDE-SONSONATE",
            defaults={
                "name": "Dirección Departamental de Educación de Sonsonate",
                "kind": Organization.Kind.DEPARTMENTAL_OFFICE,
                "department": "Sonsonate",
            },
        )
        audit_unit, _ = Organization.objects.update_or_create(
            code="DAI-MINED",
            defaults={
                "name": "Dirección de Auditoría Interna",
                "kind": Organization.Kind.MINISTRY_UNIT,
                "department": "San Salvador",
            },
        )

        auditor, auditor_created = User.objects.update_or_create(
            username="auditor.demo",
            defaults={
                "first_name": "Sandra",
                "last_name": "Auditoría",
                "email": "auditor.demo@localhost",
                "role": User.Role.AUDITOR,
                "organization": audit_unit,
                "job_title": "Auditora",
                "is_staff": True,
                "must_change_password": False,
            },
        )

        institutional, institutional_created = User.objects.update_or_create(
            username="centro.10754",
            defaults={
                "first_name": "Responsable",
                "last_name": "Institucional",
                "email": "centro.10754@localhost",
                "role": User.Role.INSTITUTION,
                "organization": center,
                "job_title": "Dirección del centro educativo",
                "must_change_password": False,
            },
        )

        users_requiring_password = []
        if auditor_created or reset_passwords:
            users_requiring_password.append(auditor)
        if institutional_created or reset_passwords:
            users_requiring_password.append(institutional)

        if users_requiring_password:
            password = secrets.token_urlsafe(14)
            for user in users_requiring_password:
                user.set_password(password)
                user.save(update_fields=["password"])

        case, _ = AuditCase.objects.update_or_create(
            reference="IA/NA-010-2025",
            defaults={
                "title": "Examen especial a los otros ingresos del Instituto Nacional de Nahuizalco",
                "audited_organization": center,
                "report_date": date(2025, 10, 11),
                "period_start": date(2020, 1, 1),
                "period_end": date(2025, 3, 31),
                "response_deadline": date.today() + timedelta(days=10),
                "status": AuditCase.Status.PUBLISHED,
                "assigned_auditor": auditor,
                "created_by": auditor,
            },
        )
        finding, _ = Finding.objects.update_or_create(
            case=case,
            number=1,
            defaults={
                "title": "Debilidades en los controles de los otros ingresos",
                "risk_level": Finding.RiskLevel.HIGH,
                "condition": (
                    "Se identificaron operaciones de ingresos y gastos que no fueron registradas "
                    "oportunamente en los libros autorizados y carecen de documentación suficiente."
                ),
                "cause": "Falta de aplicación de los controles administrativos y financieros establecidos.",
                "effect": "Riesgo de falta de transparencia y de información financiera no verificable.",
            },
        )
        first_recommendation, _ = Recommendation.objects.update_or_create(
            finding=finding,
            number=1,
            defaults={
                "text": (
                    "Asegure la implementación de controles, registrando las operaciones de ingresos "
                    "y gastos en los libros respectivos y documentando oportunamente los gastos ejecutados."
                ),
                "responsible_organization": center,
                "deadline": date.today() + timedelta(days=10),
                "evidence_requirements": (
                    "Acta del Consejo Directivo Escolar.\n"
                    "Copia de los registros actualizados.\n"
                    "Recibos, facturas o documentación de respaldo."
                ),
                "status": Recommendation.Status.PENDING,
            },
        )
        if first_recommendation.responses.exists():
            first_recommendation.status = Recommendation.Status.SUBMITTED
            first_recommendation.save(update_fields=["status"])
        Recommendation.objects.update_or_create(
            finding=finding,
            number=2,
            defaults={
                "text": (
                    "Documente las acciones de monitoreo y supervisión implementadas en los centros "
                    "educativos respecto a la administración de los otros ingresos."
                ),
                "responsible_organization": departmental,
                "deadline": date.today() + timedelta(days=10),
                "evidence_requirements": "Informe de monitoreo, actas de visita y plan de seguimiento.",
                "status": Recommendation.Status.PENDING,
            },
        )
        Recommendation.objects.update_or_create(
            finding=finding,
            number=3,
            defaults={
                "text": (
                    "Deposite íntegramente los fondos de otros ingresos en la cuenta bancaria "
                    "correspondiente y elabore las conciliaciones bancarias mensuales."
                ),
                "responsible_organization": center,
                "deadline": date.today() + timedelta(days=10),
                "evidence_requirements": (
                    "Comprobantes de depósito.\n"
                    "Estado de cuenta bancario.\n"
                    "Conciliación bancaria firmada."
                ),
                "status": Recommendation.Status.PENDING,
            },
        )

        self.stdout.write(self.style.SUCCESS("Datos de demostración creados."))
        if auditor_created or reset_passwords:
            self.stdout.write(f"Auditoría: auditor.demo / {password}")
        else:
            self.stdout.write("Auditoría: se conservó la contraseña existente de auditor.demo.")
        if institutional_created or reset_passwords:
            self.stdout.write(f"Centro educativo: centro.10754 / {password}")
        else:
            self.stdout.write("Centro educativo: se conservó la contraseña existente de centro.10754.")
        if not users_requiring_password:
            self.stdout.write(
                "Para generar nuevas credenciales de forma explícita, use seed_demo --reset-passwords."
            )
        self.stdout.write("Estas credenciales son únicamente para desarrollo local.")
