import shutil
import tempfile
from datetime import date
from io import StringIO

from django.contrib.auth.hashers import identify_hasher
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.core.validators import validate_evidence_file
from apps.institutions.models import Organization

from .models import AuditCase, Evidence, Finding, Recommendation, Response, Review


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="auditoria-test-")


class SeedDemoCommandTests(TestCase):
    def test_running_seed_again_preserves_existing_passwords(self):
        call_command("seed_demo", stdout=StringIO())
        original_passwords = dict(
            User.objects.filter(username__in=["auditor.demo", "centro.10754"])
            .values_list("username", "password")
        )

        output = StringIO()
        call_command("seed_demo", stdout=output)

        current_passwords = dict(
            User.objects.filter(username__in=["auditor.demo", "centro.10754"])
            .values_list("username", "password")
        )
        self.assertEqual(current_passwords, original_passwords)
        self.assertIn("se conservó la contraseña existente", output.getvalue())

    def test_passwords_can_be_reset_explicitly(self):
        call_command("seed_demo", stdout=StringIO())
        original_passwords = dict(
            User.objects.filter(username__in=["auditor.demo", "centro.10754"])
            .values_list("username", "password")
        )

        output = StringIO()
        call_command("seed_demo", reset_passwords=True, stdout=output)

        current_passwords = dict(
            User.objects.filter(username__in=["auditor.demo", "centro.10754"])
            .values_list("username", "password")
        )
        self.assertNotEqual(current_passwords, original_passwords)
        self.assertIn("Auditoría: auditor.demo /", output.getvalue())


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, FILE_SCAN_REQUIRED=False)
class AccessAndWorkflowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.center = Organization.objects.create(
            code="CE-1", name="Centro Uno", kind=Organization.Kind.EDUCATIONAL_CENTER
        )
        self.other_center = Organization.objects.create(
            code="CE-2", name="Centro Dos", kind=Organization.Kind.EDUCATIONAL_CENTER
        )
        self.audit_unit = Organization.objects.create(
            code="DAI", name="Auditoría Interna", kind=Organization.Kind.MINISTRY_UNIT
        )
        self.auditor = User.objects.create_user(
            username="auditor",
            password="UnaClaveDePrueba!2026",
            role=User.Role.AUDITOR,
            organization=self.audit_unit,
            must_change_password=False,
        )
        self.institution_user = User.objects.create_user(
            username="centro1",
            password="UnaClaveDePrueba!2026",
            role=User.Role.INSTITUTION,
            organization=self.center,
            must_change_password=False,
        )
        self.other_user = User.objects.create_user(
            username="centro2",
            password="UnaClaveDePrueba!2026",
            role=User.Role.INSTITUTION,
            organization=self.other_center,
            must_change_password=False,
        )
        self.case = AuditCase.objects.create(
            reference="IA-001",
            title="Auditoría de prueba",
            audited_organization=self.center,
            status=AuditCase.Status.PUBLISHED,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.finding = Finding.objects.create(
            case=self.case, number=1, title="Hallazgo de prueba", risk_level=Finding.RiskLevel.HIGH
        )
        self.recommendation = Recommendation.objects.create(
            finding=self.finding,
            number=1,
            text="Registrar y documentar las operaciones.",
            responsible_organization=self.center,
            deadline=date.today(),
            evidence_requirements="Acta y registro actualizado.",
        )

    def test_password_is_hashed_with_argon2(self):
        self.assertEqual(identify_hasher(self.institution_user.password).algorithm, "argon2")

    def test_user_cannot_open_another_organizations_case(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("case_detail", args=[self.case.pk]))
        self.assertEqual(response.status_code, 404)

    def test_responsible_organization_can_open_case_detail(self):
        self.client.force_login(self.institution_user)
        response = self.client.get(reverse("case_detail", args=[self.case.pk]))
        self.assertContains(response, "Presentar respuesta")

    def test_responsible_organization_can_submit_response_and_evidence(self):
        self.client.force_login(self.institution_user)
        evidence = SimpleUploadedFile("acta.pdf", b"%PDF-1.4\ncontenido de prueba", content_type="application/pdf")
        response = self.client.post(
            reverse("respond_recommendation", args=[self.recommendation.pk]),
            {
                "declared_status": Response.DeclaredStatus.COMPLETED,
                "action_description": "Se actualizaron los registros.",
                "action_date": date.today().isoformat(),
                "responsible_name": "Responsable Uno",
                "responsible_job_title": "Director",
                "accuracy_declaration": "on",
                "evidence_category": Evidence.Category.MINUTES,
                "evidence_description": "Acta que acredita el acuerdo.",
                "files": evidence,
            },
        )
        self.assertRedirects(response, reverse("case_detail", args=[self.case.pk]))
        created = Response.objects.get(recommendation=self.recommendation)
        self.assertEqual(created.version, 1)
        self.assertEqual(created.evidence.count(), 1)
        self.recommendation.refresh_from_db()
        self.assertEqual(self.recommendation.status, Recommendation.Status.SUBMITTED)

    def test_other_organization_cannot_submit_response(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("respond_recommendation", args=[self.recommendation.pk]))
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_review_response(self):
        response_record = Response.objects.create(
            recommendation=self.recommendation,
            version=1,
            declared_status=Response.DeclaredStatus.IN_PROGRESS,
            action_description="Acciones iniciales.",
            responsible_name="Responsable",
            responsible_job_title="Director",
            accuracy_declaration=True,
            submitted_by=self.institution_user,
        )
        self.client.force_login(self.auditor)
        response = self.client.post(
            reverse("review_response", args=[response_record.pk]),
            {"outcome": Review.Outcome.CORRECTION_REQUIRED, "comments": "Adjunte el acta completa."},
        )
        self.assertRedirects(response, reverse("case_detail", args=[self.case.pk]))
        self.assertEqual(response_record.review.outcome, Review.Outcome.CORRECTION_REQUIRED)
        self.recommendation.refresh_from_db()
        self.assertEqual(self.recommendation.status, Recommendation.Status.CORRECTION_REQUIRED)

    def test_invalid_file_signature_is_rejected(self):
        upload = SimpleUploadedFile("documento.pdf", b"esto no es un pdf")
        with self.assertRaisesMessage(ValidationError, "no corresponde a un archivo PDF"):
            validate_evidence_file(upload)

    def test_unassigned_auditor_cannot_open_case(self):
        other_auditor = User.objects.create_user(
            username="otro-auditor",
            password="UnaClaveDePrueba!2026",
            role=User.Role.AUDITOR,
            organization=self.audit_unit,
            must_change_password=False,
        )
        self.client.force_login(other_auditor)
        response = self.client.get(reverse("case_detail", args=[self.case.pk]))
        self.assertEqual(response.status_code, 404)

    def test_response_receipt_is_a_pdf(self):
        response_record = Response.objects.create(
            recommendation=self.recommendation,
            version=1,
            declared_status=Response.DeclaredStatus.IN_PROGRESS,
            action_description="Se inició la actualización de los registros.",
            responsible_name="Responsable",
            responsible_job_title="Director",
            accuracy_declaration=True,
            submitted_by=self.institution_user,
        )
        self.client.force_login(self.institution_user)
        result = self.client.get(reverse("response_receipt", args=[response_record.pk]))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["Content-Type"], "application/pdf")
        content = b"".join(result.streaming_content)
        self.assertTrue(content.startswith(b"%PDF-"))
