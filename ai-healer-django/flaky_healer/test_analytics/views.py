from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Count, Case, When, Value, CharField
from django.views.generic import TemplateView

from .models import (
    TestRun,
    TestCaseResult,
)
from .serializers import TestCaseResultSerializer
from .classifier import classify_failure
from test_generation.models import GenerationJob


class PlaywrightResultAPIView(APIView):

    def post(self, request):
        data = request.data.copy()

        # 🔥 Create or get TestRun
        test_run, _ = TestRun.objects.get_or_create(
            run_id=data.get("run_id"),
            defaults={
                "environment": data.get("environment"),
                "build_id": data.get("build_id"),
                "execution_time": data.get("run_execution_time"),
            }
        )

        # Inject FK automatically
        data["test_run"] = test_run.id
        data["execution_time"] = data.get("execution_time") or data.get("run_execution_time")

        # Enrich payload with analytics classification
        data.update(classify_failure(data))

        serializer = TestCaseResultSerializer(data=data)

        if serializer.is_valid():
            instance = serializer.save()
            return Response(
                {
                    "message": "Saved successfully",
                    "id": instance.id,
                    "failure_category": instance.failure_category,
                    "healing_outcome": instance.healing_outcome,
                },
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=400)


class TestAnalyticsSummaryAPIView(APIView):
    """
    GET /test-analytics/summary/
    Optional filters:
      - run_id
      - build_id
      - environment
    """

    def get(self, request):
        run_id = request.query_params.get("run_id")
        build_id = request.query_params.get("build_id")
        environment = request.query_params.get("environment")

        qs = TestCaseResult.objects.select_related("test_run").all()

        if run_id:
            qs = qs.filter(test_run__run_id=run_id)
        if build_id:
            qs = qs.filter(test_run__build_id=build_id)
        if environment:
            qs = qs.filter(test_run__environment=environment)

        total_tests = qs.count()
        passed = qs.filter(status="PASSED").count()
        failed = qs.filter(status="FAILED").count()
        skipped = qs.filter(status="SKIPPED").count()

        failure_breakdown = list(
            qs.filter(status="FAILED")
            .values("failure_category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        healing_attempted = qs.filter(healing_attempted=True).count()
        healing_success = qs.filter(healing_outcome="SUCCESS").count()
        healing_failed = qs.filter(healing_outcome="FAILED").count()
        healing_not_attempted = qs.filter(
            healing_outcome__in=[None, "", "NOT_ATTEMPTED"]
        ).count()
        healing_false_positive = qs.filter(
            failure_category="HEALING_FALSE_POSITIVE"
        ).count()
        cache_hits = qs.filter(cache_hit=True).count()
        cache_fallback_to_fresh = qs.filter(cache_fallback_to_fresh=True).count()
        cache_misses = qs.filter(healing_attempted=True, cache_hit=False).count()

        healing_qs = qs.filter(healing_attempted=True)
        assisted_qs = healing_qs.filter(history_assisted=True)
        non_assisted_qs = healing_qs.filter(history_assisted=False)
        assisted_attempts = assisted_qs.count()
        assisted_success = assisted_qs.filter(healing_outcome="SUCCESS").count()
        non_assisted_attempts = non_assisted_qs.count()
        non_assisted_success = non_assisted_qs.filter(healing_outcome="SUCCESS").count()

        def _rate(success: int, attempts: int) -> float:
            if attempts == 0:
                return 0.0
            return round((success * 100.0) / attempts, 2)

        history_bucketed = list(
            healing_qs.annotate(
                history_bucket=Case(
                    When(history_hits=0, then=Value("0")),
                    When(history_hits=1, then=Value("1")),
                    When(history_hits__gte=2, history_hits__lte=3, then=Value("2-3")),
                    When(history_hits__gte=4, then=Value("4+")),
                    default=Value("0"),
                    output_field=CharField(),
                )
            )
            .values("history_bucket")
            .annotate(
                attempts=Count("id"),
                success=Count(Case(When(healing_outcome="SUCCESS", then=1))),
            )
            .order_by("history_bucket")
        )

        history_effectiveness = []
        for row in history_bucketed:
            attempts = row["attempts"] or 0
            success_count = row["success"] or 0
            history_effectiveness.append(
                {
                    "history_bucket": row["history_bucket"],
                    "attempts": attempts,
                    "success": success_count,
                    "success_rate": _rate(success_count, attempts),
                }
            )

        top_failed_selectors = list(
            qs.filter(status="FAILED")
            .exclude(failed_selector__isnull=True)
            .exclude(failed_selector__exact="")
            .values("failed_selector")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        recent_failures = list(
            qs.filter(status="FAILED")
            .order_by("-created_on")
            .values(
                "id",
                "test_name",
                "failure_category",
                "healing_outcome",
                "failed_selector",
                "healed_selector",
                "validation_status",
                "ui_change_level",
                "history_assisted",
                "history_hits",
                "healing_confidence",
                "created_on",
                "test_run__run_id",
            )[:10]
        )

        generation_jobs_qs = GenerationJob.objects.all()
        if run_id:
            generation_jobs_qs = generation_jobs_qs.filter(
                execution_links__test_run__run_id=run_id
            ).distinct()
        if build_id:
            generation_jobs_qs = generation_jobs_qs.filter(
                execution_links__test_run__build_id=build_id
            ).distinct()
        if environment:
            generation_jobs_qs = generation_jobs_qs.filter(
                execution_links__test_run__environment=environment
            ).distinct()

        job_status_counts = list(
            generation_jobs_qs.values("job_status").annotate(count=Count("id")).order_by("job_status")
        )
        total_jobs = generation_jobs_qs.count()
        approved_jobs = generation_jobs_qs.filter(job_status=GenerationJob.STATE_APPROVED).count()
        materialized_jobs = generation_jobs_qs.filter(job_status=GenerationJob.STATE_MATERIALIZED).count()
        generated_execution = (
            TestCaseResult.objects.filter(test_run__generation_links__isnull=False)
            .values("status")
            .annotate(count=Count("id"))
        )
        generated_total = sum(row["count"] for row in generated_execution)
        generated_passed = next((row["count"] for row in generated_execution if row["status"] == "PASSED"), 0)
        generated_failed = next((row["count"] for row in generated_execution if row["status"] == "FAILED"), 0)
        generated_healing_attempted = TestCaseResult.objects.filter(
            test_run__generation_links__isnull=False,
            healing_attempted=True,
        ).count()
        generated_healing_success = TestCaseResult.objects.filter(
            test_run__generation_links__isnull=False,
            healing_outcome="SUCCESS",
        ).count()

        return Response(
            {
                "filters": {
                    "run_id": run_id,
                    "build_id": build_id,
                    "environment": environment,
                },
                "totals": {
                    "total_tests": total_tests,
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                },
                "failure_breakdown": failure_breakdown,
                "healing_summary": {
                    "attempted": healing_attempted,
                    "success": healing_success,
                    "failed": healing_failed,
                    "not_attempted": healing_not_attempted,
                    "false_positive": healing_false_positive,
                },
                "cache_summary": {
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "cache_fallback_to_fresh": cache_fallback_to_fresh,
                },
                "history_summary": {
                    "assisted_attempts": assisted_attempts,
                    "assisted_success": assisted_success,
                    "assisted_success_rate": _rate(assisted_success, assisted_attempts),
                    "non_assisted_attempts": non_assisted_attempts,
                    "non_assisted_success": non_assisted_success,
                    "non_assisted_success_rate": _rate(non_assisted_success, non_assisted_attempts),
                    "buckets": history_effectiveness,
                },
                "top_failed_selectors": top_failed_selectors,
                "recent_failures": recent_failures,
                "generation_summary": {
                    "total_jobs": total_jobs,
                    "job_status_breakdown": job_status_counts,
                    "approved_jobs": approved_jobs,
                    "materialized_jobs": materialized_jobs,
                    "approval_ratio": round((approved_jobs * 100.0 / total_jobs), 2) if total_jobs else 0.0,
                    "materialization_ratio": round((materialized_jobs * 100.0 / total_jobs), 2) if total_jobs else 0.0,
                    "generated_test_results": {
                        "total": generated_total,
                        "passed": generated_passed,
                        "failed": generated_failed,
                        "pass_rate": round((generated_passed * 100.0 / generated_total), 2) if generated_total else 0.0,
                        "healing_attempted": generated_healing_attempted,
                        "healing_success": generated_healing_success,
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class TestCaseResultDetailAPIView(APIView):
    """
    GET /test-analytics/test-result/<id>/
    Returns full test result details including step_events timeline.
    """

    def get(self, request, id: int):
        instance = get_object_or_404(
            TestCaseResult.objects.select_related("test_run"),
            id=id
        )

        serializer = TestCaseResultSerializer(instance)
        data = serializer.data
        data["run_id"] = instance.test_run.run_id
        data["build_id"] = instance.test_run.build_id
        data["environment"] = instance.test_run.environment

        return Response(data, status=status.HTTP_200_OK)


class TestAnalyticsDashboardView(TemplateView):
    """
    HTML dashboard for demo/analysis.
    Data is fetched client-side from existing summary/detail APIs.
    """

    template_name = "test_analytics/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_run_id"] = self.request.GET.get("run_id", "")
        context["selected_build_id"] = self.request.GET.get("build_id", "")
        context["selected_environment"] = self.request.GET.get("environment", "")

        runs = (
            TestRun.objects
            .values("run_id", "build_id", "environment")
            .order_by("-created_on")[:200]
        )
        context["runs"] = list(runs)
        return context
