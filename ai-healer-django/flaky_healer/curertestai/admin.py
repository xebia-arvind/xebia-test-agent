from django.contrib import admin
from curertestai.models import HealerRequest, HealerRequestBatch, SuggestedSelector, DomSnapshot
# Register your models here.

class SuggestedSelectorInline(admin.TabularInline):
    model = SuggestedSelector
    extra = 0

class HealerRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'batch_id',
        'failed_selector',
        'use_of_selector',
        'intent_key',
        'selector_type',
        'url',
        'healed_selector',
        'validation_status',
        'ui_change_level',
        'history_assisted',
        'history_hits',
        'confidence',
        'success',
        'processing_time_ms',
        'llm_used',
        'screenshot_analyzed',
        'created_on',
    )
    list_filter = (
        'batch_id',
        'success',
        'validation_status',
        'ui_change_level',
        'history_assisted',
        'llm_used',
        'screenshot_analyzed',
    )
    inlines = [SuggestedSelectorInline]
   
admin.site.register(HealerRequest, HealerRequestAdmin)



class HealerRequestBatchAdmin(admin.ModelAdmin):
    list_display = ('id','total_requests', 'success', 'failure', 'processing_time_ms', 'created_on')
    list_filter = ('total_requests', 'success', 'failure', 'processing_time_ms')
   
admin.site.register(HealerRequestBatch, HealerRequestBatchAdmin)


class DomSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "page_url",
        "intent_key",
        "use_of_selector",
        "healed_selector",
        "validation_status",
        "success",
        "confidence",
        "source_request",
    )
    list_filter = ("success", "validation_status", "intent_key")
    search_fields = ("page_url", "use_of_selector", "failed_selector", "healed_selector", "dom_fingerprint")
    ordering = ("-created_on",)


admin.site.register(DomSnapshot, DomSnapshotAdmin)
