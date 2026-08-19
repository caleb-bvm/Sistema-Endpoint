from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.audits.models import ActivityLog, AuditCase

from .models import Organization


class DirectorEducationalCenterTests(TestCase):
    common_password = "UnaClaveDePrueba!2026"

    def setUp(self):
        self.audit_unit = Organization.objects.create(
            code="DAI",
            name="Dirección de Auditoría Interna",
            kind=Organization.Kind.MINISTRY_UNIT,
        )
        self.center = Organization.objects.create(
            code="CE-104",
            name="Instituto Nacional Central",
            kind=Organization.Kind.EDUCATIONAL_CENTER,
            department="San Salvador",
            municipality="San Salvador",
            is_active=False,
        )
        self.other_center = Organization.objects.create(
            code="CE-205",
            name="Centro Escolar Las Flores",
            kind=Organization.Kind.EDUCATIONAL_CENTER,
            department="La Libertad",
            municipality="Santa Tecla",
        )
        self.director = User.objects.create_user(
            username="directora",
            password=self.common_password,
            role=User.Role.AUDIT_MANAGER,
            organization=self.audit_unit,
            must_change_password=False,
        )
        self.auditor = User.objects.create_user(
            username="auditor",
            password=self.common_password,
            role=User.Role.AUDITOR,
            organization=self.audit_unit,
            must_change_password=False,
        )

    def test_director_can_search_centers_by_official_data(self):
        self.client.force_login(self.director)

        response = self.client.get(reverse("director_educational_centers"), {"q": "CE-104"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instituto Nacional Central")
        self.assertNotContains(response, "Centro Escolar Las Flores")
        self.assertContains(response, "Activar")

    def test_director_can_open_cases_filtered_by_center(self):
        center_case = AuditCase.objects.create(
            reference="IA-CENTRO-104",
            title="Expediente del centro seleccionado",
            audited_organization=self.center,
            status=AuditCase.Status.PUBLISHED,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        other_case = AuditCase.objects.create(
            reference="IA-CENTRO-205",
            title="Expediente de otro centro",
            audited_organization=self.other_center,
            status=AuditCase.Status.PUBLISHED,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.client.force_login(self.director)

        directory = self.client.get(reverse("director_educational_centers"))
        cases = self.client.get(reverse("case_list"), {"organization": self.center.pk})

        self.assertContains(
            directory,
            f'{reverse("case_list")}?organization={self.center.pk}',
        )
        listed_center = next(
            center for center in directory.context["centers"] if center.pk == self.center.pk
        )
        self.assertEqual(listed_center.case_count, 1)
        self.assertContains(cases, self.center.name)
        self.assertContains(cases, center_case.reference)
        self.assertNotContains(cases, other_case.reference)
        self.assertContains(cases, "Volver a centros")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("director_educational_centers"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('director_educational_centers')}",
        )

    def test_invalid_center_filter_does_not_crash_or_show_unfiltered_cases(self):
        AuditCase.objects.create(
            reference="IA-NO-DEBE-MOSTRARSE",
            title="Expediente fuera del filtro inválido",
            audited_organization=self.center,
            status=AuditCase.Status.PUBLISHED,
            assigned_auditor=self.auditor,
            created_by=self.auditor,
        )
        self.client.force_login(self.director)

        malformed = self.client.get(reverse("case_list"), {"organization": "centro-invalido"})
        missing = self.client.get(reverse("case_list"), {"organization": "999999"})

        for response in (malformed, missing):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "No se encontró el centro educativo")
            self.assertNotContains(response, "IA-NO-DEBE-MOSTRARSE")

    def test_center_list_and_activation_are_restricted_to_director(self):
        self.client.force_login(self.auditor)

        list_response = self.client.get(reverse("director_educational_centers"))
        activation_response = self.client.post(
            reverse("director_activate_educational_center", args=[self.center.pk])
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(activation_response.status_code, 403)
        self.assertFalse(
            User.objects.filter(
                organization=self.center,
                role=User.Role.INSTITUTION,
            ).exists()
        )

    def test_director_activates_center_with_common_credential_and_audit_log(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse("director_activate_educational_center", args=[self.center.pk])
        )

        self.assertRedirects(response, reverse("director_educational_centers"))
        account = User.objects.get(
            organization=self.center,
            role=User.Role.INSTITUTION,
        )
        self.assertEqual(account.username, "centro.ce-104")
        self.assertTrue(account.is_active)
        self.assertFalse(account.must_change_password)
        self.assertTrue(check_password(self.common_password, account.password))
        self.assertEqual(account.password, self.director.password)
        self.client.logout()
        self.assertTrue(
            self.client.login(username=account.username, password=self.common_password)
        )
        self.center.refresh_from_db()
        self.assertTrue(self.center.is_active)
        log = ActivityLog.objects.get(action="educational_center_activated")
        self.assertEqual(log.actor, self.director)
        self.assertEqual(log.target_id, str(self.center.pk))
        self.assertEqual(log.details["username"], "centro.ce-104")
        self.assertTrue(log.details["account_created"])

    def test_activation_reuses_suspended_account_without_creating_a_duplicate(self):
        account = User.objects.create_user(
            username="centro.existente",
            password="ClaveAnterior!2026",
            role=User.Role.INSTITUTION,
            organization=self.other_center,
            is_active=False,
            must_change_password=True,
        )
        self.client.force_login(self.director)

        self.client.post(
            reverse("director_activate_educational_center", args=[self.other_center.pk])
        )

        account.refresh_from_db()
        self.assertTrue(account.is_active)
        self.assertFalse(account.must_change_password)
        self.assertEqual(account.password, self.director.password)
        self.assertEqual(
            User.objects.filter(
                organization=self.other_center,
                role=User.Role.INSTITUTION,
            ).count(),
            1,
        )
