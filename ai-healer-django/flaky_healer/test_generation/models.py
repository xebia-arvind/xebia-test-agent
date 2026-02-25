from django.db import models
from abstract.models import Common
import uuid


class GenerationJob(Common):
    COVERAGE_SMOKE_NEGATIVE = "SMOKE_NEGATIVE"
    COVERAGE_CHOICES = [
        (COVERAGE_SMOKE_NEGATIVE, "Smoke + Negative"),
    ]

    STATE_DRAFTING = "DRAFTING"
    STATE_DRAFT_READY = "DRAFT_READY"
    STATE_APPROVED = "APPROVED"
    STATE_MATERIALIZED = "MATERIALIZED"
    STATE_REJECTED = "REJECTED"
    STATE_FAILED = "FAILED"
    STATE_CHOICES = [
        (STATE_DRAFTING, "Drafting"),
        (STATE_DRAFT_READY, "Draft Ready"),
        (STATE_APPROVED, "Approved"),
        (STATE_MATERIALIZED, "Materialized"),
        (STATE_REJECTED, "Rejected"),
        (STATE_FAILED, "Failed"),
    ]

    job_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    feature_name = models.CharField(max_length=255)
    feature_description = models.TextField()
    seed_urls = models.JSONField(default=list, blank=True)
    intent_hints = models.JSONField(default=list, blank=True)
    coverage_mode = models.CharField(
        max_length=32,
        choices=COVERAGE_CHOICES,
        default=COVERAGE_SMOKE_NEGATIVE,
    )
    max_scenarios = models.PositiveIntegerField(default=8)
    max_routes = models.PositiveIntegerField(default=20)
    base_url = models.URLField(default="http://localhost:3000")
    job_status = models.CharField(
        max_length=32,
        choices=STATE_CHOICES,
        default=STATE_DRAFTING,
        db_index=True,
    )
    llm_model = models.CharField(max_length=128, default="qwen2.5:7b")
    llm_temperature = models.FloatField(default=0.0)
    crawl_summary = models.JSONField(default=dict, blank=True)
    feature_summary = models.TextField(blank=True, default="")
    llm_notes = models.JSONField(default=list, blank=True)
    validation_summary = models.JSONField(default=dict, blank=True)
    materialized_manifest = models.JSONField(default=list, blank=True)
    approved_by = models.CharField(max_length=255, blank=True, default="")
    approved_notes = models.TextField(blank=True, default="")
    rejected_reason = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_by = models.CharField(max_length=255, blank=True, default="")
    drafting_started_on = models.DateTimeField(null=True, blank=True)
    drafting_finished_on = models.DateTimeField(null=True, blank=True)
    materialized_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "test_generation_generationjob"

    def __str__(self):
        return f"{self.feature_name} | {self.job_id}"


class GenerationScenario(Common):
    TYPE_SMOKE = "SMOKE"
    TYPE_NEGATIVE = "NEGATIVE"
    TYPE_CHOICES = [
        (TYPE_SMOKE, "Smoke"),
        (TYPE_NEGATIVE, "Negative"),
    ]

    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="scenarios",
    )
    scenario_id = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255)
    scenario_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=TYPE_SMOKE)
    priority = models.PositiveIntegerField(default=1)
    preconditions = models.JSONField(default=list, blank=True)
    steps = models.JSONField(default=list, blank=True)
    expected_assertions = models.JSONField(default=list, blank=True)
    selected_for_materialization = models.BooleanField(default=True)

    class Meta:
        db_table = "test_generation_generationscenario"
        unique_together = ("job", "scenario_id")

    def __str__(self):
        return f"{self.job_id} | {self.scenario_id}"


class GeneratedArtifact(Common):
    TYPE_PAGE_OBJECT = "PAGE_OBJECT"
    TYPE_SPEC = "SPEC"
    TYPE_CHOICES = [
        (TYPE_PAGE_OBJECT, "Page Object"),
        (TYPE_SPEC, "Spec"),
    ]

    VALID = "VALID"
    INVALID = "INVALID"
    VALIDATION_CHOICES = [
        (VALID, "Valid"),
        (INVALID, "Invalid"),
    ]

    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    artifact_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    relative_path = models.CharField(max_length=512)
    content_draft = models.TextField(default="", blank=True)
    content_final = models.TextField(default="", blank=True)
    checksum = models.CharField(max_length=64, blank=True, default="")
    validation_status = models.CharField(
        max_length=16,
        choices=VALIDATION_CHOICES,
        default=VALID,
    )
    validation_errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "test_generation_generatedartifact"
        unique_together = ("job", "relative_path")

    def __str__(self):
        return f"{self.artifact_type} | {self.relative_path}"


class GenerationExecutionLink(Common):
    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.CASCADE,
        related_name="execution_links",
    )
    test_run = models.ForeignKey(
        "test_analytics.TestRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generation_links",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "test_generation_generationexecutionlink"

    def __str__(self):
        return f"{self.job_id} -> {self.test_run_id or 'NA'}"
