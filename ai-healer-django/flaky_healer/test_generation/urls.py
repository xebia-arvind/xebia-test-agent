from django.urls import path

from .views import (
    GenerationJobApproveAPIView,
    GenerationJobCreateAPIView,
    GenerationJobDetailAPIView,
    GenerationJobLinkRunAPIView,
    GenerationJobMaterializeAPIView,
    GenerationJobRejectAPIView,
)

urlpatterns = [
    path("jobs/", GenerationJobCreateAPIView.as_view(), name="generation_job_create"),
    path("jobs/<uuid:job_id>/", GenerationJobDetailAPIView.as_view(), name="generation_job_detail"),
    path("jobs/<uuid:job_id>/approve/", GenerationJobApproveAPIView.as_view(), name="generation_job_approve"),
    path("jobs/<uuid:job_id>/materialize/", GenerationJobMaterializeAPIView.as_view(), name="generation_job_materialize"),
    path("jobs/<uuid:job_id>/reject/", GenerationJobRejectAPIView.as_view(), name="generation_job_reject"),
    path("jobs/<uuid:job_id>/link-run/", GenerationJobLinkRunAPIView.as_view(), name="generation_job_link_run"),
]
