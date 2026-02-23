from django.contrib import admin
from curertestai.models import HealerRequest, HealerRequestBatch, SuggestedSelector
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
    list_display = ('id','total_requests', 'success', 'failure', 'processing_time_ms')
    list_filter = ('total_requests', 'success', 'failure', 'processing_time_ms')
   
admin.site.register(HealerRequestBatch, HealerRequestBatchAdmin)
