import time
import uuid
import logging
from typing import Dict, Any, Optional, List

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from curertestai.serializers import (
    HealRequestSerializer,
    BatchHealRequestSerializer,
    HealResponseSerializer,
    BatchHealResponseSerializer
)
from curertestai.models import HealerRequest, HealerRequestBatch, SuggestedSelector
from curertestai.dom_extractor import DOMExtractor
from curertestai.matching_engine import MatchingEngine
from curertestai.validation_engine import select_validated_candidate
from curertestai.fingerprint import (
    build_dom_signature_tokens,
    generate_dom_fingerprint,
    jaccard_similarity,
)
from clients.models import Clients
from django.contrib.auth import get_user_model
User = get_user_model()

# Setup logger
logger = logging.getLogger(__name__)


class HealAPIView(APIView):
    """
    POST /heal/
    Heal a single failing selector
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Handle single heal request"""
        start_time = time.time()
        request_id = str(uuid.uuid4())
        user = request.user
        client_secret = request.auth.get('client_id')
        try:
            client = Clients.objects.get(secret_key=client_secret)
        except Clients.DoesNotExist:
            # Handle error scenario if needed
            raise ValueError("Invalid Client ID in token")
        # Validate incoming data
        serializer = HealRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"Validation failed | request_id={request_id} | errors={serializer.errors}")
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        
        try:
            # Process heal request
            result = self._process_heal_request(
                validated_data,
                request_id,
                start_time
            )
            
            # Save to database (batch_instance=None for single requests)
            healer_request = self._save_heal_request(validated_data, result, start_time, batch_instance=None,user=user,client=client)
            
            # Inject IDs into response
            result['id'] = healer_request.id
            result['batch_id'] = None # or 0, or omitted if not relevant for single request, but serializer expects integer? 
            # Wait, user added batch_id to global response serializer? 
            # If HealerRequest has nullable batch_id, we can return None or 0.
            # But serializer says IntegerField. So maybe 0 is safer if null is not allowed by serializer.
            # Let's check user changes... "batch_id = serializers.IntegerField()" implies required integer.
            # I will return 0 if null.
            result['batch_id'] = 0 
            
            logger.info(
                f"Heal successful | request_id={request_id} | "
                f"selector={validated_data.get('failed_selector')} | "
                f"chosen={result.get('chosen')}"
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                f"Healing failed | request_id={request_id} | "
                f"selector={validated_data.get('failed_selector')} | "
                f"error={str(e)}",
                exc_info=True
            )
            return Response(
                {"error": "Healing failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_heal_request(
        self,
        validated_data: Dict[str, Any],
        request_id: str,
        start_time: float
    ) -> Dict[str, Any]:
        """Process a single heal request and return response"""
        
        # Prepare DOM data for processing
        html_content = validated_data.get('html', '')
        
        if validated_data.get('semantic_dom') and isinstance(validated_data.get('semantic_dom'), dict):
            # Use provided semantic DOM
            dom_data = validated_data['semantic_dom']
        elif html_content:
            # Fallback to extraction if not provided but HTML is
            extractor = DOMExtractor(html_content)
            dom_data = extractor.extract_semantic_dom(full_coverage=True)
        else:
            raise ValueError("No DOM source provided")

        current_elements = dom_data.get("elements", [])
        dom_fingerprint = generate_dom_fingerprint(current_elements)
        ui_change_level = self._detect_ui_change_level(validated_data, current_elements)

        # Initialize matching engine
        engine = MatchingEngine(current_elements)
        
        # Rank and find best selectors
        results = engine.rank(
            validated_data['failed_selector'],
            validated_data['use_of_selector'],
            top_k=5
        )
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Build response
        response = self._build_heal_response(
            engine_results=results,
            failed_selector=validated_data["failed_selector"],
            use_of_selector=validated_data["use_of_selector"],
            page_url=validated_data.get("page_url", ""),
            intent_key=validated_data.get("intent_key", ""),
            dom_fingerprint=dom_fingerprint,
            ui_change_level=ui_change_level,
            request_id=request_id,
            processing_time=processing_time
        )
        
        return response
    
    def _build_heal_response(
        self,
        engine_results: list,
        failed_selector: str,
        use_of_selector: str,
        page_url: str,
        intent_key: str,
        dom_fingerprint: str,
        ui_change_level: str,
        request_id: str,
        processing_time: float,
        vision_analyzed: bool = False,
        vision_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build heal response from engine results"""
        
        candidates = []
        
        for r in engine_results:
            el = r["element"]
            candidates.append({
                "selector": r["suggested"],
                "score": round(float(r["score"]), 4),
                "base_score": round(float(r["base"]), 4),
                "attribute_score": round(float(r["attr"]), 4),
                "tag": el.get("tag"),
                "text": el.get("text") or el.get("accessible_name"),
                "xpath": el.get("xpath"),
            })
        
        debug_info = {
            "total_candidates": len(candidates),
            "engine": "matching_engine_faiss",
            "processing_time_ms": round(processing_time, 2),
            "vision_analyzed": vision_analyzed,
        }
        
        if vision_analyzed and vision_analysis:
            debug_info["vision_model"] = vision_analysis.get("model_used")
            debug_info["vision_success"] = vision_analysis.get("success", False)

        selection = select_validated_candidate(
            candidates=candidates,
            failed_selector=failed_selector,
            use_of_selector=use_of_selector,
            page_url=page_url,
            intent_key=intent_key,
        )
        debug_info["validation_status"] = selection["validation_status"]
        debug_info["validation_reason"] = selection["validation_reason"]
        debug_info["history_assisted"] = selection["history_assisted"]
        debug_info["history_hits"] = selection["history_hits"]
        debug_info["dom_fingerprint"] = dom_fingerprint
        debug_info["ui_change_level"] = ui_change_level

        return {
            "message": "Success",
            "chosen": selection["chosen"],
            "validation_status": selection["validation_status"],
            "validation_reason": selection["validation_reason"],
            "llm_used": selection["llm_used"],
            "history_assisted": selection["history_assisted"],
            "history_hits": selection["history_hits"],
            "dom_fingerprint": dom_fingerprint,
            "ui_change_level": ui_change_level,
            "candidates": candidates,
            "debug": debug_info
        }
    
    def _save_heal_request(
        self,
        validated_data: Dict[str, Any],
        result: Dict[str, Any],
        start_time: float,
        batch_instance: Optional[HealerRequestBatch] = None,
        user: Optional[User] = None,
        client: Optional[Clients] = None
    ):
        """Save heal request and results to database"""
        
        processing_time_ms = int(result['debug']['processing_time_ms'])
        chosen_selector = result.get('chosen', '')
        candidates = result.get('candidates', [])
        
        # Create HealerRequest
        healer_request = HealerRequest.objects.create(
            user_id=user,
            client_id=client,
            batch_id=batch_instance,  # Assign ForeignKey instance or None
            failed_selector=validated_data['failed_selector'],
            html=validated_data.get('html', ''),
            use_of_selector=validated_data['use_of_selector'],
            selector_type=validated_data.get('selector_type', 'css'),
            url=validated_data.get('page_url', ''),
            healed_selector=chosen_selector or '',
            confidence=candidates[0]['score'] if candidates else 0.0,
            success=bool(chosen_selector),
            processing_time_ms=processing_time_ms,
            llm_used=bool(result.get("llm_used", False)),
            screenshot_analyzed=False,
            intent_key=validated_data.get("intent_key", ""),
            validation_status=result.get("validation_status"),
            validation_reason=result.get("validation_reason"),
            dom_fingerprint=result.get("dom_fingerprint"),
            candidate_snapshot=candidates[:5] if candidates else [],
            history_assisted=bool(result.get("history_assisted", False)),
            history_hits=int(result.get("history_hits", 0) or 0),
            ui_change_level=result.get("ui_change_level"),
        )
        
        # Create SuggestedSelector entries for all candidates
        for candidate in candidates[:5]:  # Save top 5
            SuggestedSelector.objects.create(
                healer_request=healer_request,
                selector=candidate['selector'],
                score=candidate['score'],
                base_score=candidate['base_score'],
                attribute_score=candidate['attribute_score'],
                tag=candidate.get('tag', ''),
                text=candidate.get('text', ''),
                xpath=candidate.get('xpath', '')
            )
        
        return healer_request

    def _detect_ui_change_level(
        self,
        validated_data: Dict[str, Any],
        current_elements: List[Dict[str, Any]],
    ) -> str:
        page_url = validated_data.get("page_url", "") or ""
        use_of_selector = validated_data.get("use_of_selector", "") or ""
        intent_key = validated_data.get("intent_key", "") or ""

        base_query = HealerRequest.objects.filter(
            url=page_url,
            use_of_selector=use_of_selector,
            success=True,
        ).exclude(html__isnull=True).exclude(html__exact="")

        previous = None
        if intent_key:
            previous = base_query.filter(intent_key=intent_key).order_by("-created_on").first()
        if not previous:
            previous = base_query.order_by("-created_on").first()

        if not previous:
            return "UNKNOWN"

        try:
            extractor = DOMExtractor(previous.html)
            previous_dom = extractor.extract_semantic_dom(full_coverage=True)
            previous_elements = previous_dom.get("elements", [])
        except Exception:
            return "UNKNOWN"

        prev_tokens = build_dom_signature_tokens(previous_elements)
        curr_tokens = build_dom_signature_tokens(current_elements)
        similarity = jaccard_similarity(prev_tokens, curr_tokens)

        if similarity >= 0.90:
            return "UNCHANGED"
        if similarity >= 0.70:
            return "MINOR_CHANGE"

        intent_text = (intent_key or validated_data.get("use_of_selector", "") or "").lower()
        if "add_to_cart" in intent_text or ("add" in intent_text and "cart" in intent_text):
            prev_has_add_cart = any("text:add to cart" in t or "text:add" in t for t in prev_tokens)
            curr_has_add_cart = any("text:add to cart" in t or "text:add" in t for t in curr_tokens)
            if prev_has_add_cart and not curr_has_add_cart:
                return "ELEMENT_REMOVED"

        return "MAJOR_CHANGE"


class BatchHealAPIView(APIView):
    """
    POST /heal/batch/
    Heal multiple failing selectors in a batch
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Handle batch heal request"""
        batch_start_time = time.time()
        request_id = str(uuid.uuid4())
        user = request.user
        client_secret = request.auth.get('client_id')
        try:
            client = Clients.objects.get(secret_key=client_secret)
        except Clients.DoesNotExist:
            # Handle error scenario if needed
            raise ValueError("Invalid Client ID in token")
        
        # Validate incoming data
        serializer = BatchHealRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"Batch validation failed | request_id={request_id} | errors={serializer.errors}")
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        selectors_to_heal = validated_data['selectors']
        
        results = []
        success_count = 0
        fail_count = 0
        
        # Create Batch Instance FIRST
        batch_instance = HealerRequestBatch.objects.create(
            total_requests=len(selectors_to_heal),
            success=0,
            failure=0,
            processing_time_ms=0
        )
        
        # Create HealAPIView instance to reuse logic
        heal_view = HealAPIView()
        
        logger.info(f"Batch heal started | request_id={request_id} | count={len(selectors_to_heal)}")
        
        for idx, selector_data in enumerate(selectors_to_heal):
            try:
                item_start_time = time.time()
                item_request_id = f"{request_id}-{idx}"
                
                # Process individual heal request
                result = heal_view._process_heal_request(
                    selector_data,
                    item_request_id,
                    item_start_time
                )
                
                # Save to database linked to batch_instance
                healer_request = heal_view._save_heal_request(
                    selector_data,
                    result,
                    item_start_time,
                    batch_instance=batch_instance,
                    user=user,
                    client=client
                )
                
                # Inject IDs
                result['id'] = healer_request.id
                result['batch_id'] = batch_instance.id
                
                results.append(result)
                success_count += 1
                
            except Exception as e:
                logger.error(
                    f"Batch item failed | request_id={request_id} | "
                    f"item={idx} | selector={selector_data.get('failed_selector')} | "
                    f"error={str(e)}"
                )
                fail_count += 1
                
                # Add failed response
                results.append({
                    "id": 0, # Placeholder for failed
                    "batch_id": batch_instance.id,
                    "message": f"Failed: {str(e)}",
                    "chosen": None,
                    "candidates": [],
                    "debug": {}
                })
        
        # Calculate total processing time
        total_time = (time.time() - batch_start_time) * 1000
        
        # Update batch summary
        batch_instance.success = success_count
        batch_instance.failure = fail_count
        batch_instance.processing_time_ms = int(total_time)
        batch_instance.save()
        
        logger.info(
            f"Batch heal completed | request_id={request_id} | "
            f"success={success_count} | failed={fail_count}"
        )
        
        return Response(
            {
                "id": batch_instance.id,
                "results": results,
                "total_processed": len(selectors_to_heal),
                "total_succeeded": success_count,
                "total_failed": fail_count,
                "processing_time_ms": total_time
            },
            status=status.HTTP_200_OK
        )
