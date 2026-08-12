from django.urls import path

from . import views


urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("expedientes/", views.CaseListView.as_view(), name="case_list"),
    path("expedientes/<int:pk>/", views.case_detail, name="case_detail"),
    path("recomendaciones/<int:pk>/responder/", views.respond_recommendation, name="respond_recommendation"),
    path("respuestas/<int:pk>/revisar/", views.review_response, name="review_response"),
    path("respuestas/<int:pk>/constancia/", views.response_receipt, name="response_receipt"),
    path("evidencias/<int:pk>/descargar/", views.download_evidence, name="download_evidence"),
]
