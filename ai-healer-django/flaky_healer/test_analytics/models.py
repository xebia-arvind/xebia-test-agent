from django.db import models
from abstract.models import Common


class TestRun(Common):

    run_id = models.CharField(max_length=100, unique=True)
    environment = models.CharField(max_length=50)
    build_id = models.CharField(max_length=100)
    execution_time = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.run_id


class TestCaseResult(Common):

    test_run = models.ForeignKey(
        TestRun,
        on_delete=models.CASCADE,
        related_name="test_cases"
    )

    test_name = models.CharField(max_length=255)

    STATUS_CHOICES = [
        ("PASSED", "Passed"),
        ("FAILED", "Failed"),
        ("SKIPPED", "Skipped"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="FAILED"
    )

    screenshot_path = models.TextField(null=True, blank=True)
    video_path = models.TextField(null=True, blank=True)
    trace_path = models.TextField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    stack_trace = models.TextField(null=True, blank=True)
    html = models.TextField()
    symentic_dom = models.TextField(null=True, blank=True)
    page_url = models.TextField(null=True, blank=True)
    failed_selector = models.TextField(null=True, blank=True)
    execution_time = models.FloatField(null=True, blank=True)
    embedding = models.JSONField(null=True, blank=True)
    failure_category = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    healing_attempted = models.BooleanField(default=False)
    healing_outcome = models.CharField(max_length=32, null=True, blank=True)
    healed_selector = models.TextField(null=True, blank=True)
    healing_confidence = models.FloatField(null=True, blank=True)
    validation_status = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    ui_change_level = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    history_assisted = models.BooleanField(default=False)
    history_hits = models.IntegerField(default=0)
    cache_hit = models.BooleanField(default=False)
    cache_fallback_to_fresh = models.BooleanField(default=False)
    root_cause = models.TextField(null=True, blank=True)
    step_events = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.test_name


class AnalyticsDashboardLink(TestRun):
    """
    Proxy model used only to expose a dashboard entry inside Django admin menu.
    """

    class Meta:
        proxy = True
        verbose_name = "Analytics Dashboard"
        verbose_name_plural = "Analytics Dashboard"
