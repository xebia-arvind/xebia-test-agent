from django.urls import path
from django.views.generic import RedirectView
from .views import (
    PlaywrightResultAPIView,
    TestAnalyticsSummaryAPIView,
    TestCaseResultDetailAPIView,
    TestAnalyticsDashboardView,
    TestAnalyticsLoginView,
    TestAnalyticsLogoutView,
)

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="test_analytics_dashboard", permanent=False)),
    path("login/", TestAnalyticsLoginView.as_view(), name="test_analytics_login"),
    path("logout/", TestAnalyticsLogoutView.as_view(), name="test_analytics_logout"),
    path("test-result/", PlaywrightResultAPIView.as_view(), name="test_result_create"),
    path("test-result/<int:id>/", TestCaseResultDetailAPIView.as_view(), name="test_result_detail"),
    path("summary/", TestAnalyticsSummaryAPIView.as_view(), name="test_analytics_summary"),
    path("dashboard/", TestAnalyticsDashboardView.as_view(), name="test_analytics_dashboard"),
]
