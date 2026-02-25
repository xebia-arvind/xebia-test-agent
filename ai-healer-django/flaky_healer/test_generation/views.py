import os

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from test_analytics.models import TestRun

from .models import GenerationJob, GenerationExecutionLink
from .serializers import (
    GenerationJobApproveSerializer,
    GenerationJobCreateSerializer,
    GenerationJobDetailSerializer,
    GenerationJobLinkRunSerializer,
    GenerationJobMaterializeSerializer,
    GenerationJobRejectSerializer,
)
from .generation_service import (
    apply_approval_selection,
    generate_job_draft,
    materialize_job,
)


class GenerationJobCreateAPIView(APIView):
    def post(self, request):
        serializer = GenerationJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        job = GenerationJob.objects.create(
            feature_name=data["feature_name"],
            feature_description=data["feature_description"],
            seed_urls=data.get("seed_urls") or [],
            intent_hints=data.get("intent_hints") or [],
            coverage_mode=data.get("coverage_mode", GenerationJob.COVERAGE_SMOKE_NEGATIVE),
            max_scenarios=data.get("max_scenarios", 8),
            max_routes=data.get("max_routes", 20),
            base_url=data.get("base_url", "http://localhost:3000"),
            created_by=data.get("created_by", ""),
            llm_model=os.getenv("TEST_GEN_LLM_MODEL", "qwen2.5:7b"),
            llm_temperature=0.0,
            job_status=GenerationJob.STATE_DRAFTING,
        )

        job = generate_job_draft(job)
        return Response(
            {
                "job_id": str(job.job_id),
                "status": job.job_status,
                "created_on": job.created_on,
            },
            status=status.HTTP_201_CREATED,
        )


class GenerationJobDetailAPIView(APIView):
    def get(self, request, job_id):
        job = get_object_or_404(
            GenerationJob.objects.prefetch_related("scenarios", "artifacts", "execution_links__test_run"),
            job_id=job_id,
        )
        payload = GenerationJobDetailSerializer(job).data
        payload["status"] = job.job_status
        return Response(payload, status=status.HTTP_200_OK)


class GenerationJobApproveAPIView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, job_id=job_id)
        serializer = GenerationJobApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if job.job_status not in {GenerationJob.STATE_DRAFT_READY, GenerationJob.STATE_APPROVED}:
            return Response(
                {"error": f"Cannot approve from state={job.job_status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        apply_approval_selection(
            job=job,
            include_scenario_ids=data.get("include_scenario_ids"),
            exclude_scenario_ids=data.get("exclude_scenario_ids"),
        )

        job.approved_by = data["approved_by"]
        job.approved_notes = data.get("notes", "")
        job.job_status = GenerationJob.STATE_APPROVED
        job.save(update_fields=["approved_by", "approved_notes", "job_status", "last_modified"])
        return Response({"status": job.job_status}, status=status.HTTP_200_OK)


class GenerationJobMaterializeAPIView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, job_id=job_id)
        serializer = GenerationJobMaterializeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allow_overwrite = serializer.validated_data.get("allow_overwrite", False)

        if job.job_status not in {GenerationJob.STATE_APPROVED, GenerationJob.STATE_MATERIALIZED}:
            return Response(
                {"error": f"Cannot materialize from state={job.job_status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = materialize_job(job, allow_overwrite=allow_overwrite)
        if not result.ok:
            return Response(
                {
                    "status": job.job_status,
                    "written_files": result.written_files,
                    "write_report": {
                        "conflicts": result.conflicts,
                        "errors": result.errors,
                    },
                },
                status=status.HTTP_409_CONFLICT if result.conflicts else status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": job.job_status,
                "written_files": result.written_files,
                "write_report": {
                    "conflicts": [],
                    "errors": [],
                },
            },
            status=status.HTTP_200_OK,
        )


class GenerationJobRejectAPIView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, job_id=job_id)
        serializer = GenerationJobRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        if job.job_status == GenerationJob.STATE_MATERIALIZED:
            return Response(
                {"error": "Cannot reject a materialized job"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.rejected_reason = reason
        job.job_status = GenerationJob.STATE_REJECTED
        job.save(update_fields=["rejected_reason", "job_status", "last_modified"])
        return Response({"status": job.job_status}, status=status.HTTP_200_OK)


class GenerationJobLinkRunAPIView(APIView):
    def post(self, request, job_id):
        job = get_object_or_404(GenerationJob, job_id=job_id)
        serializer = GenerationJobLinkRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run_id = serializer.validated_data["run_id"]
        notes = serializer.validated_data.get("notes", "")

        test_run = get_object_or_404(TestRun, run_id=run_id)
        link, _ = GenerationExecutionLink.objects.get_or_create(
            job=job,
            test_run=test_run,
            defaults={"notes": notes},
        )
        if notes and link.notes != notes:
            link.notes = notes
            link.save(update_fields=["notes", "last_modified"])

        return Response(
            {
                "status": "LINKED",
                "job_id": str(job.job_id),
                "run_id": test_run.run_id,
                "link_id": link.id,
            },
            status=status.HTTP_200_OK,
        )
