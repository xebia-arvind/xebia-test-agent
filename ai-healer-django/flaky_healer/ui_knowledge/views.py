from django.shortcuts import render

# Create your views here.
# ui_knowledge/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from .models import *
from .serializers import UISnapshotSerializer
from .change_detection_service import compare_snapshots, detect_ui_change_for_healing
from urllib.parse import urlparse


def _normalize_route(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return parsed.path or "/"
    except Exception:
        pass
    if raw.startswith("/"):
        return raw
    return f"/{raw}"


class UISnapshotCreateAPI(APIView):

    def post(self, request):

        serializer = UISnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # ------------------------------------------------
        # PAGE
        # ------------------------------------------------
        page, _ = UIPage.objects.get_or_create(
            route=data["route"],
            defaults={
                "title": data.get("title", ""),
                "feature_name": data.get("feature_name", ""),
            }
        )
        # Keep page metadata in sync for existing routes as well.
        updated_fields = []
        incoming_title = data.get("title")
        incoming_feature_name = data.get("feature_name")
        if incoming_title is not None and incoming_title != page.title:
            page.title = incoming_title
            updated_fields.append("title")
        if incoming_feature_name is not None and incoming_feature_name != page.feature_name:
            page.feature_name = incoming_feature_name
            updated_fields.append("feature_name")
        if updated_fields:
            page.save(update_fields=updated_fields + ["updated_on"])

        # mark old snapshot non-current
        page.snapshots.filter(is_current=True).update(is_current=False)

        # ------------------------------------------------
        # SNAPSHOT
        # ------------------------------------------------
        snapshot = UIRouteSnapshot.objects.create(
            page=page,
            snapshot_type=data["snapshot_type"],
            dom_hash=data["dom_hash"],
            snapshot_json=data["snapshot_json"],
            is_current=True,
            version=page.snapshots.count() + 1
        )

        # =====================================================
        # Baseline/current change detection
        # =====================================================
        if data["snapshot_type"] != "BASELINE":
            baseline = page.snapshots.filter(
                snapshot_type="BASELINE"
            ).exclude(id=snapshot.id).first()

            if baseline:
                diff = compare_snapshots(baseline, snapshot)
                UIChangeLog.objects.create(
                    page=page,
                    baseline_snapshot=baseline,
                    new_snapshot=snapshot,
                    change_type=diff.get("change_type") or "MINOR",
                    added_selectors=diff.get("added_selectors") or [],
                    removed_selectors=diff.get("removed_selectors") or [],
                )

        # ------------------------------------------------
        # SCREENSHOT
        # ------------------------------------------------
        if data.get("screenshot_path"):
            UIScreenshot.objects.create(
                snapshot=snapshot,
                image_path=data["screenshot_path"]
            )

        # ------------------------------------------------
        # ELEMENTS (FAST BULK INSERT)
        # ------------------------------------------------
        rows = []

        for el in data["elements"]:
            rows.append(
                UIElement(
                    snapshot=snapshot,
                    selector=el["selector"],
                    tag=el.get("tag", ""),
                    role=el.get("role", ""),
                    text=el.get("text", ""),
                    test_id=el.get("test_id", ""),
                    intent_key=el.get("intent_key", "generic"),
                )
            )

        UIElement.objects.bulk_create(rows)

        return Response({
            "status": "stored",
            "snapshot_id": snapshot.id,
            "elements": len(rows)
        })


class UIChangeStatusAPIView(APIView):
    """
    GET /ui-knowledge/change-status/?route=/cart
    Optional:
      - failed_selector
      - use_of_selector
    """

    def get(self, request):
        route = str(request.query_params.get("route") or "").strip()
        if not route:
            return Response({"error": "Missing required query param: route"}, status=400)

        failed_selector = str(request.query_params.get("failed_selector") or "")
        use_of_selector = str(request.query_params.get("use_of_selector") or "")

        route_path = _normalize_route(route)
        page = UIPage.objects.filter(route=route, is_active=True).first()
        if not page:
            page = UIPage.objects.filter(route=route_path, is_active=True).first()
        if not page:
            page = UIPage.objects.filter(route__endswith=route_path, is_active=True).order_by("-updated_on").first()

        if not page:
            detection = detect_ui_change_for_healing(
                page_url=route,
                failed_selector=failed_selector,
                use_of_selector=use_of_selector,
            )
            return Response(
                {
                    "status": "not_found",
                    "route": route,
                    "detection": detection,
                },
                status=404,
            )

        baseline = page.snapshots.filter(snapshot_type="BASELINE").order_by("-version", "-created_on").first()
        current = page.snapshots.filter(is_current=True).order_by("-version", "-created_on").first()
        if not current:
            current = page.snapshots.order_by("-version", "-created_on").first()

        detection = detect_ui_change_for_healing(
            page_url=page.route,
            failed_selector=failed_selector,
            use_of_selector=use_of_selector,
        )

        diff = None
        if baseline and current and baseline.id != current.id:
            diff = compare_snapshots(baseline, current)

        latest_log = (
            UIChangeLog.objects.filter(page=page)
            .order_by("-created_on")
            .first()
        )

        return Response(
            {
                "status": "ok",
                "route": page.route,
                "page_id": page.id,
                "baseline_snapshot_id": baseline.id if baseline else None,
                "current_snapshot_id": current.id if current else None,
                "latest_change_log": {
                    "id": latest_log.id,
                    "change_type": latest_log.change_type,
                    "created_on": latest_log.created_on,
                    "added_selectors_count": len(latest_log.added_selectors or []),
                    "removed_selectors_count": len(latest_log.removed_selectors or []),
                } if latest_log else None,
                "detection": detection,
                "computed_diff": diff,
            }
        )
