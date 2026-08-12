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

from .models import (
    ActivityLog,
    AuditCase,
    CaseDecision,
    Evidence,
    Finding,
    Recommendation,
    Response,
    Review,
)


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="auditoria-test-")


class SeedDemoCommandTests(TestCase):
    def test_running_seed_again_preserves_existing_passwords(self):
        call_command("seed_demo", stdout=StringIO())
        original_passwords = dict(
            User.objects.filter(
                username__in=["auditor.demo", "directora.demo", "centro.10754"]
            )
            .values_list("username", "password")
        )

        output = StringIO()
        call_command("seed_demo", stdout=output)

        current_passwords = dict(
            User.objects.filter(
                username__in=["auditor.demo", "directora.demo", "centro.10754"]
            )
            .values_list("username", "password")
        )
        self.assertEqual(current_passwords, original_passwords)
        self.assertIn("se conservó la contraseña existente", output.getvalue())

    def test_passwords_can_be_reset_explicitly(self):
        call_command("seed_demo", stdout=StringIO())
        original_passwords = dict(
            User.objects.filter(
                username__in=["auditor.demo", "directora.demo", "centro.10754"]
            )
            .values_list("username", "password")
        )

        output = StringIO()
        call_command("seed_demo", reset_passwords=True, stdout=output)

        current_passwords = dict(
            User.objects.filter(
                username__in=["auditor.demo", "directora.demo", "centro.10754"]
            )
            .values_list("username", "password")
        )
        self.assertNotEqual(current_passwords, original_passwords)
        self.assertIn("Auditoría: auditor.demo /", output.getvalue())
        self.assertIn("Dirección: directora.demo /", output.getvalue())


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
        self.director = User.objects.create_user(
            username="directora",
            password="UnaClaveDePrueba!2026",
            role=User.Role.AUDIT_MANAGER,
            organization=self.audit_unit,
            must_change_password=False,
        )
        self.technical_admin = User.objects.create_user(
            username="tecnico",
            password="UnaClaveDePrueba!2026",
            role=User.Role.TECHNICAL_ADMIN,
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

    def test_auditor_can_build_and_director_can_approve_publication(self):
        self.client.force_login(self.auditor)
        create_response = self.client.post(
            reverse("case_create"),
            {
                "reference": "IA-NEW-001",
                "title": "Examen especial de prueba",
                "audited_organization": self.center.pk,
                "report_file": SimpleUploadedFile(
                    "informe.pdf",
                    b"%PDF-1.4\ninforme de prueba",
                    content_type="application/pdf",
                ),
                "report_date": date.today().isoformat(),
                "response_deadline": date.today().isoformat(),
                "assigned_auditor": self.other_user.pk,
            },
        )
        created_case = AuditCase.objects.get(reference="IA-NEW-001")
        self.assertRedirects(create_response, reverse("case_builder", args=[created_case.pk]))
        self.assertEqual(created_case.status, AuditCase.Status.DRAFT)
        self.assertEqual(created_case.assigned_auditor, self.auditor)
        self.assertEqual(created_case.created_by, self.auditor)

        finding_response = self.client.post(
            reverse("finding_create", args=[created_case.pk]),
            {
                "number": 1,
                "title": "Falta de conciliaciones",
                "risk_level": Finding.RiskLevel.HIGH,
                "condition": "No se prepararon conciliaciones mensuales.",
            },
        )
        self.assertRedirects(finding_response, reverse("case_builder", args=[created_case.pk]))
        created_finding = created_case.findings.get(number=1)

        recommendation_response = self.client.post(
            reverse("recommendation_create", args=[created_finding.pk]),
            {
                "number": 1,
                "text": "Prepare y apruebe las conciliaciones mensualmente.",
                "responsible_organization": self.center.pk,
                "deadline": date.today().isoformat(),
                "evidence_requirements": "Conciliaciones firmadas.",
            },
        )
        self.assertRedirects(
            recommendation_response,
            reverse("case_builder", args=[created_case.pk]),
        )

        publish_response = self.client.post(reverse("case_publish", args=[created_case.pk]))
        self.assertRedirects(publish_response, reverse("case_detail", args=[created_case.pk]))
        created_case.refresh_from_db()
        self.assertEqual(created_case.status, AuditCase.Status.PENDING_PUBLICATION)
        decision = CaseDecision.objects.get(case=created_case, kind=CaseDecision.Kind.PUBLICATION)
        self.assertTrue(
            ActivityLog.objects.filter(
                case=created_case, action="case_publication_requested"
            ).exists()
        )

        self.client.force_login(self.institution_user)
        hidden_response = self.client.get(reverse("case_detail", args=[created_case.pk]))
        self.assertEqual(hidden_response.status_code, 404)

        self.client.force_login(self.director)
        approval_response = self.client.post(
            reverse("director_decision_detail", args=[decision.pk]),
            {
                "action": "approve",
                "justification": "El expediente reúne los requisitos técnicos para su publicación.",
            },
        )
        self.assertRedirects(approval_response, reverse("director_decisions"))
        created_case.refresh_from_db()
        decision.refresh_from_db()
        self.assertEqual(created_case.status, AuditCase.Status.PUBLISHED)
        self.assertEqual(decision.status, CaseDecision.Status.APPROVED)
        self.assertEqual(decision.decided_by, self.director)

        self.client.force_login(self.institution_user)
        visible_response = self.client.get(reverse("case_detail", args=[created_case.pk]))
        self.assertEqual(visible_response.status_code, 200)

    def test_institution_cannot_create_or_view_draft_cases(self):
        draft_case = AuditCase.objects.create(
            reference="IA-DRAFT-001",
            title="Borrador reservado",
            audited_organization=self.center,
            status=AuditCase.Status.DRAFT,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.client.force_login(self.institution_user)
        create_response = self.client.get(reverse("case_create"))
        detail_response = self.client.get(reverse("case_detail", args=[draft_case.pk]))
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 404)

    def test_institution_cannot_respond_to_a_draft_recommendation_directly(self):
        draft_case = AuditCase.objects.create(
            reference="IA-DRAFT-DIRECT",
            title="Borrador con recomendación",
            audited_organization=self.center,
            status=AuditCase.Status.DRAFT,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        draft_finding = Finding.objects.create(
            case=draft_case,
            number=1,
            title="Hallazgo aún no publicado",
            risk_level=Finding.RiskLevel.MEDIUM,
        )
        draft_recommendation = Recommendation.objects.create(
            finding=draft_finding,
            number=1,
            text="Recomendación reservada.",
            responsible_organization=self.center,
            deadline=date.today(),
        )
        self.client.force_login(self.institution_user)
        result = self.client.get(reverse("respond_recommendation", args=[draft_recommendation.pk]))
        self.assertEqual(result.status_code, 404)

    def test_case_cannot_be_published_until_required_content_is_complete(self):
        draft_case = AuditCase.objects.create(
            reference="IA-DRAFT-002",
            title="Borrador incompleto",
            audited_organization=self.center,
            status=AuditCase.Status.DRAFT,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.client.force_login(self.auditor)
        result = self.client.post(reverse("case_publish", args=[draft_case.pk]))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Adjunte el informe final en formato PDF")
        draft_case.refresh_from_db()
        self.assertEqual(draft_case.status, AuditCase.Status.DRAFT)

    def test_unassigned_auditor_cannot_edit_a_draft(self):
        other_auditor = User.objects.create_user(
            username="auditor-sin-asignacion",
            password="UnaClaveDePrueba!2026",
            role=User.Role.AUDITOR,
            organization=self.audit_unit,
            must_change_password=False,
        )
        draft_case = AuditCase.objects.create(
            reference="IA-DRAFT-003",
            title="Borrador asignado",
            audited_organization=self.center,
            status=AuditCase.Status.DRAFT,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.client.force_login(other_auditor)
        result = self.client.get(reverse("case_builder", args=[draft_case.pk]))
        self.assertEqual(result.status_code, 403)

    def test_director_dashboard_is_restricted_to_director(self):
        self.client.force_login(self.director)
        result = self.client.get(reverse("director_dashboard"))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Resumen ejecutivo")

        self.client.force_login(self.auditor)
        forbidden = self.client.get(reverse("director_dashboard"))
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(self.technical_admin)
        forbidden = self.client.get(reverse("director_dashboard"))
        self.assertEqual(forbidden.status_code, 403)

    def test_director_can_return_publication_with_justification(self):
        draft_case = AuditCase.objects.create(
            reference="IA-RETURN-001",
            title="Borrador para devolución",
            audited_organization=self.center,
            report_file=SimpleUploadedFile(
                "informe.pdf", b"%PDF-1.4\ncontenido", content_type="application/pdf"
            ),
            report_date=date.today(),
            response_deadline=date.today(),
            status=AuditCase.Status.PENDING_PUBLICATION,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        decision = CaseDecision.objects.create(
            case=draft_case,
            kind=CaseDecision.Kind.PUBLICATION,
            requested_by=self.auditor,
            previous_case_status=AuditCase.Status.DRAFT,
        )
        self.client.force_login(self.director)
        result = self.client.post(
            reverse("director_decision_detail", args=[decision.pk]),
            {
                "action": "return",
                "justification": "Debe corregirse la identificación oficial del informe presentado.",
            },
        )
        self.assertRedirects(result, reverse("director_decisions"))
        draft_case.refresh_from_db()
        decision.refresh_from_db()
        self.assertEqual(draft_case.status, AuditCase.Status.DRAFT)
        self.assertEqual(decision.status, CaseDecision.Status.RETURNED)
        self.assertTrue(
            ActivityLog.objects.filter(
                case=draft_case, action="case_publication_returned"
            ).exists()
        )

    def test_director_decision_requires_justification(self):
        self.case.status = AuditCase.Status.PENDING_PUBLICATION
        self.case.save(update_fields=["status"])
        decision = CaseDecision.objects.create(
            case=self.case,
            kind=CaseDecision.Kind.PUBLICATION,
            requested_by=self.auditor,
            previous_case_status=AuditCase.Status.DRAFT,
        )
        self.client.force_login(self.director)
        result = self.client.post(
            reverse("director_decision_detail", args=[decision.pk]),
            {"action": "approve", "justification": "corto"},
        )
        self.assertEqual(result.status_code, 200)
        decision.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(decision.status, CaseDecision.Status.PENDING)
        self.assertEqual(self.case.status, AuditCase.Status.PENDING_PUBLICATION)

    def test_auditor_and_technical_admin_cannot_resolve_director_decision(self):
        self.case.status = AuditCase.Status.PENDING_PUBLICATION
        self.case.save(update_fields=["status"])
        decision = CaseDecision.objects.create(
            case=self.case,
            kind=CaseDecision.Kind.PUBLICATION,
            requested_by=self.auditor,
            previous_case_status=AuditCase.Status.DRAFT,
        )
        payload = {
            "action": "approve",
            "justification": "Intento de aprobación sin autoridad directiva suficiente.",
        }
        self.client.force_login(self.auditor)
        auditor_result = self.client.post(
            reverse("director_decision_detail", args=[decision.pk]), payload
        )
        self.assertEqual(auditor_result.status_code, 403)

        self.client.force_login(self.technical_admin)
        technical_result = self.client.post(
            reverse("director_decision_detail", args=[decision.pk]), payload
        )
        self.assertEqual(technical_result.status_code, 403)
        decision.refresh_from_db()
        self.assertEqual(decision.status, CaseDecision.Status.PENDING)

    def test_director_can_approve_case_closure(self):
        self.recommendation.status = Recommendation.Status.COMPLIED
        self.recommendation.save(update_fields=["status"])
        self.case.status = AuditCase.Status.UNDER_REVIEW
        self.case.save(update_fields=["status"])

        self.client.force_login(self.auditor)
        request_result = self.client.post(
            reverse("request_case_closure", args=[self.case.pk]),
            {
                "justification": (
                    "Todas las recomendaciones cuentan con un resultado definitivo documentado."
                )
            },
        )
        self.assertRedirects(request_result, reverse("case_detail", args=[self.case.pk]))
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, AuditCase.Status.PENDING_CLOSURE)
        decision = CaseDecision.objects.get(case=self.case, kind=CaseDecision.Kind.CLOSURE)

        self.client.force_login(self.director)
        approval_result = self.client.post(
            reverse("director_decision_detail", args=[decision.pk]),
            {
                "action": "approve",
                "justification": "Se verificó el resultado final y la trazabilidad del expediente.",
            },
        )
        self.assertRedirects(approval_result, reverse("director_decisions"))
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, AuditCase.Status.CLOSED)

    def test_closure_request_is_blocked_with_open_recommendations(self):
        self.client.force_login(self.auditor)
        result = self.client.post(
            reverse("request_case_closure", args=[self.case.pk]),
            {
                "justification": (
                    "Se solicita el cierre aunque todavía existe trabajo pendiente de revisión."
                )
            },
        )
        self.assertEqual(result.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, AuditCase.Status.PUBLISHED)
        self.assertFalse(
            CaseDecision.objects.filter(case=self.case, kind=CaseDecision.Kind.CLOSURE).exists()
        )

    def test_director_can_reassign_case_with_audit_log(self):
        replacement = User.objects.create_user(
            username="auditor-reemplazo",
            password="UnaClaveDePrueba!2026",
            role=User.Role.AUDITOR,
            organization=self.audit_unit,
            must_change_password=False,
        )
        self.client.force_login(self.director)
        result = self.client.post(
            reverse("director_reassign_case", args=[self.case.pk]),
            {
                "assigned_auditor": replacement.pk,
                "justification": "Se redistribuye la carga por disponibilidad operativa del equipo.",
            },
        )
        self.assertRedirects(result, reverse("case_detail", args=[self.case.pk]))
        self.case.refresh_from_db()
        self.assertEqual(self.case.assigned_auditor, replacement)
        log = ActivityLog.objects.get(case=self.case, action="case_reassigned")
        self.assertEqual(log.details["previous_auditor_id"], self.auditor.pk)
        self.assertEqual(log.details["new_auditor_id"], replacement.pk)

    def test_director_cannot_create_case_or_edit_auditor_draft(self):
        draft_case = AuditCase.objects.create(
            reference="IA-DIRECTOR-DRAFT",
            title="Borrador del auditor",
            audited_organization=self.center,
            status=AuditCase.Status.DRAFT,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.client.force_login(self.director)
        create_result = self.client.get(reverse("case_create"))
        edit_result = self.client.get(reverse("case_builder", args=[draft_case.pk]))
        self.assertEqual(create_result.status_code, 403)
        self.assertEqual(edit_result.status_code, 403)
