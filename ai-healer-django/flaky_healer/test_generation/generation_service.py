import hashlib
import json
import logging
import os
import re
import socket
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from django.utils import timezone

from .models import GeneratedArtifact, GenerationJob, GenerationScenario

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    # .../ecommerce-app/ai-healer-django/flaky_healer/test_generation/generation_service.py
    return Path(__file__).resolve().parents[3]


def _default_test_gen_model() -> str:
    return os.getenv("TEST_GEN_LLM_MODEL", os.getenv("LLM_VALIDATION_MODEL", "qwen2.5:7b"))


def _llm_url() -> str:
    return os.getenv("TEST_GEN_LLM_URL", "http://127.0.0.1:11434/api/generate").strip()


def _llm_timeout() -> int:
    try:
        return int(os.getenv("TEST_GEN_TIMEOUT_SECONDS", "120"))
    except ValueError:
        return 120


def _effective_llm_timeout(base_timeout: int, num_predict: int) -> int:
    # Local Ollama on laptop/CPU can be slow on first load; keep generous floor.
    if num_predict >= 2400:
        return max(base_timeout, 240)
    if num_predict >= 1200:
        return max(base_timeout, 180)
    return max(base_timeout, 120)


def _max_scenarios_default() -> int:
    return int(os.getenv("TEST_GEN_MAX_SCENARIOS", "8"))


def _max_routes_default() -> int:
    return int(os.getenv("TEST_GEN_MAX_ROUTES", "20"))


def _test_gen_enabled() -> bool:
    return os.getenv("USE_TEST_GEN", "true").lower() == "true"


def _runtime_selector_validation_enabled() -> bool:
    return os.getenv("TEST_GEN_RUNTIME_SELECTOR_VALIDATION", "true").lower() == "true"


def _feature_presence_required() -> bool:
    return os.getenv("TEST_GEN_REQUIRE_FEATURE_PRESENCE", "true").lower() == "true"


def _feature_presence_min_score() -> float:
    try:
        return float(os.getenv("TEST_GEN_FEATURE_PRESENCE_MIN_SCORE", "0.40"))
    except ValueError:
        return 0.40


def _safe_json(value: Any, fallback: Any):
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return fallback


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


@lru_cache(maxsize=1)
def _available_intent_keys() -> List[str]:
    config_path = (
        Path(__file__).resolve().parents[1]
        / "curertestai"
        / "config"
        / "intent_policies.json"
    )
    keys = []
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            keys = [str(k).strip().lower() for k in payload.keys() if str(k).strip()]
    except Exception:
        keys = []
    if "generic" not in keys:
        keys.append("generic")
    return sorted(set(keys))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-") or "feature"


def _camel(text: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", text or "")
    merged = "".join(p.capitalize() for p in parts if p)
    if not merged:
        return "Generated"
    if merged[0].isdigit():
        return f"F{merged}"
    return merged


def _sha256(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _normalize_scenario_type(value: str) -> str:
    norm = (value or "").strip().upper()
    if "NEG" in norm:
        return GenerationScenario.TYPE_NEGATIVE
    return GenerationScenario.TYPE_SMOKE


def _render_step_name(step: Dict[str, Any], fallback: str) -> str:
    name = (step.get("action") or step.get("name") or fallback or "").strip()
    return name or "perform action"


def _render_failed_selector(step: Dict[str, Any]) -> str:
    preferred = step.get("failed_selector") or step.get("selector") or step.get("locator") or ""
    if preferred:
        return str(preferred)
    return 'button:has-text("Action")'


def _render_intent_key(step: Dict[str, Any]) -> str:
    allowed = _available_intent_keys()
    key = (step.get("intent_key") or "").strip().lower()
    if key in allowed:
        return key
    text_blob = " ".join(
        [
            str(step.get("action") or ""),
            str(step.get("name") or ""),
            str(step.get("selector") or ""),
            str(step.get("locator") or ""),
            str(step.get("hint") or ""),
        ]
    ).lower()
    # Intent mapping is config-driven: pick best token-overlap with known keys.
    tokenized_blob = set(re.split(r"[^a-z0-9]+", text_blob))
    best_key = "generic"
    best_score = 0
    for intent in allowed:
        parts = set(p for p in intent.split("_") if p)
        if not parts:
            continue
        overlap = len(parts & tokenized_blob)
        if overlap > best_score:
            best_score = overlap
            best_key = intent
    if best_score > 0:
        return best_key
    return "generic"


def _interactable_selector_candidates(node: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    test_id = str(node.get("test_id") or "").strip()
    role = str(node.get("role") or "").strip()
    text = str(node.get("text") or "").strip()
    aria = str(node.get("aria_label") or "").strip()
    element_id = str(node.get("id") or "").strip()
    tag = str(node.get("tag") or "").strip() or "button"

    if test_id:
        candidates.append(f'[data-testid="{test_id}"]')
    if role and text:
        short_text = text.replace('"', '\\"')[:40]
        candidates.append(f'{tag}[role="{role}"]:has-text("{short_text}")')
    if aria:
        aria_escaped = aria.replace('"', '\\"')
        candidates.append(f'{tag}[aria-label="{aria_escaped}"]')
    if element_id:
        candidates.append(f'#{element_id}')
    if text:
        short_text = text.replace('"', '\\"')[:40]
        candidates.append(f'{tag}:has-text("{short_text}")')
    for hint in node.get("selector_hints") or []:
        h = str(hint).strip()
        if h:
            candidates.append(h)
    # Deduplicate while preserving order.
    out: List[str] = []
    seen = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out[:8]


def _collect_interactables(crawl_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for route in crawl_summary.get("routes") or []:
        route_url = route.get("url") or ""
        for node in (route.get("interactables") or [])[:200]:
            rows.append(
                {
                    "route_url": route_url,
                    "node": node,
                }
            )
    return rows

def _build_selector_map(crawl_summary: Dict[str, Any]) -> Dict[str, str]:
    """
    Compress crawl output into deterministic selector map.
    This massively improves local LLM stability.
    """
    selector_map: Dict[str, str] = {}

    for route in crawl_summary.get("routes") or []:
        for node in route.get("interactables") or []:

            key_parts = []

            if node.get("test_id"):
                key_parts.append(str(node["test_id"]).lower())

            if node.get("text"):
                key_parts.append(
                    str(node["text"]).lower().replace(" ", "_")[:30]
                )

            if node.get("id"):
                key_parts.append(str(node["id"]).lower())

            if not key_parts:
                continue

            key = "_".join(key_parts[:2])

            candidates = _interactable_selector_candidates(node)
            if candidates and key not in selector_map:
                selector_map[key] = candidates[0]

    return selector_map



def _pick_best_selector(crawl_summary: Dict[str, Any], hints: List[str], default_selector: str) -> str:
    rows = _collect_interactables(crawl_summary)[:300]
    if not rows:
        return default_selector
    hint_tokens = set()
    for h in hints:
        hint_tokens.update(_tokenize(str(h)))
    if not hint_tokens:
        hint_tokens.update(_tokenize(default_selector))

    best_score = -1
    best_selector = default_selector
    for row in rows:
        node = row["node"]
        blob_parts = [
            str(node.get("text") or ""),
            str(node.get("aria_label") or ""),
            str(node.get("test_id") or ""),
            str(node.get("id") or ""),
            str(node.get("role") or ""),
            str(node.get("href") or ""),
        ]
        tokens = set(_tokenize(" ".join(blob_parts)))
        overlap = len(tokens & hint_tokens)
        candidates = _interactable_selector_candidates(node)
        if not candidates:
            continue
        if overlap > best_score:
            best_score = overlap
            best_selector = candidates[0]
    return best_selector


def _render_assertion_lines(scenario: Dict[str, Any], crawl_summary: Dict[str, Any], fallback_selector: str) -> List[str]:
    assertion_items = scenario.get("assertions") or []
    if not assertion_items:
        return ["  await expect(page.locator('body')).toBeVisible();"]

    lines: List[str] = []
    for item in assertion_items[:3]:
        if isinstance(item, dict):
            a_type = str(item.get("type") or "").strip().lower()
            target = item.get("target") or {}
            if a_type == "url_contains":
                value = str(item.get("value") or target.get("value") or "").strip().replace("/", "\\/")
                if value:
                    lines.append(f"  await expect(page).toHaveURL(/{value}/);")
                    continue
            if a_type == "visible":
                strategy = str(target.get("strategy") or "").strip().lower()
                value = str(target.get("value") or "").strip()
                if strategy == "testid" and value:
                    lines.append(f"  await expect(page.locator('[data-testid=\"{value}\"]')).toBeVisible();")
                    continue
                if strategy == "selector" and value:
                    escaped = value.replace("'", "\\'")
                    lines.append(f"  await expect(page.locator('{escaped}')).toBeVisible();")
                    continue
        # string assertion fallback + selector ranking
        text = str(item).strip()
        if not text:
            continue
        if "url" in text.lower() and "/" in text:
            path = "/" + text.split("/")[-1].strip()
            path_regex = path.replace("/", "\\/")
            lines.append(f"  await expect(page).toHaveURL(/{path_regex}/);")
            continue
        selector = _pick_best_selector(crawl_summary, [text], fallback_selector)
        escaped = selector.replace("'", "\\'")
        lines.append(f"  await expect(page.locator('{escaped}')).toBeVisible();")

    return lines or ["  await expect(page.locator('body')).toBeVisible();"]


def _extract_selector_literals_from_text(text: str) -> List[str]:
    values: List[str] = []
    # view.primaryAction('selector')
    for match in re.finditer(r"primaryAction\('([^']+)'\)", text):
        values.append(match.group(1))
    # page.locator('selector')
    for match in re.finditer(r"page\.locator\('([^']+)'\)", text):
        values.append(match.group(1))
    # selfHealingClick failed selector literal (3rd arg)
    for match in re.finditer(r"selfHealingClick\(\s*[\s\S]*?,\s*[\s\S]*?,\s*'([^']+)'", text):
        values.append(match.group(1))
    out: List[str] = []
    seen = set()
    for v in values:
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _extract_feature_keywords(job: GenerationJob) -> List[str]:
    blob = f"{job.feature_name} {job.feature_description}"
    tokens = [t.strip().lower() for t in re.split(r"[^a-z0-9]+", blob) if len(t.strip()) >= 4]
    # Keep meaningful unique words for feature-presence checks.
    ignored = {"user", "with", "from", "page", "flow", "item", "feature", "see", "validation"}
    out = []
    for token in tokens:
        if token in ignored:
            continue
        if token not in out:
            out.append(token)
    return out[:8]


def _feature_presence_report(job: GenerationJob, crawl_summary: Dict[str, Any]) -> Dict[str, Any]:
    keywords = _extract_feature_keywords(job)
    primary_feature = (job.feature_name or "").strip().lower()
    primary_tokens = [t for t in re.split(r"[^a-z0-9]+", primary_feature) if len(t) >= 4]
    min_score = _feature_presence_min_score()
    routes = crawl_summary.get("routes") or []
    if not keywords:
        return {
            "keywords": [],
            "matched_keywords": [],
            "coverage_score": 0.0,
            "required_min_score": min_score,
            "primary_tokens": primary_tokens,
            "primary_feature_matched": False,
            "feature_likely_present": False,
        }
    corpus_parts = []
    for route in routes:
        corpus_parts.append(str(route.get("url") or ""))
        corpus_parts.append(str(route.get("title") or ""))
        for node in (route.get("interactables") or [])[:200]:
            corpus_parts.append(str(node.get("text") or ""))
            corpus_parts.append(str(node.get("aria_label") or ""))
            corpus_parts.append(str(node.get("test_id") or ""))
            corpus_parts.append(str(node.get("id") or ""))
    corpus = " ".join(corpus_parts).lower()
    matched = [kw for kw in keywords if kw in corpus]
    score = round((len(matched) / max(len(keywords), 1)), 3)
    primary_match = any(token in corpus for token in primary_tokens) if primary_tokens else False
    likely_present = (score >= min_score) or primary_match
    return {
        "keywords": keywords,
        "matched_keywords": matched,
        "coverage_score": score,
        "required_min_score": min_score,
        "primary_tokens": primary_tokens,
        "primary_feature_matched": primary_match,
        "feature_likely_present": likely_present,
    }


def _call_ollama_json(
    *,
    prompt: str,
    model: str,
    temperature: float,
    timeout_seconds: int,
    num_predict: int,
) -> Dict[str, Any]:
    effective_timeout = _effective_llm_timeout(timeout_seconds, num_predict)

    def _post_json(url: str) -> str:
        req = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        logger.info("TEST_GEN_LLM request started url=%s model=%s timeout=%s", url, model, effective_timeout)
        with urllib_request.urlopen(req, timeout=effective_timeout) as response:
            raw_bytes = response.read()
            logger.info(
                "TEST_GEN_LLM response received url=%s status=%s bytes=%s",
                url,
                getattr(response, "status", "NA"),
                len(raw_bytes or b""),
            )
            return raw_bytes.decode("utf-8")

    def _extract_json_fragment(text: str) -> str:
        raw_text = (text or "").strip()
        if not raw_text:
            return ""
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)

        # Attempt to capture first balanced JSON object.
        start = raw_text.find("{")
        if start < 0:
            return ""
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(raw_text)):
            ch = raw_text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return raw_text[start : idx + 1]
        return ""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    print("llm payload",payload)
    llm_url = _llm_url()
    alt_url = llm_url.rstrip("/") if llm_url.endswith("/") else f"{llm_url}/"
    raw = ""
    last_exc: Exception | None = None
    attempt_errors: List[str] = []
    for candidate_url in [llm_url, alt_url]:
        try:
            raw = _post_json(candidate_url)
            print("llm raw json",raw)
            last_exc = None
            break
        except HTTPError as exc:
            body = ""
            try:
                body = (exc.read() or b"").decode("utf-8", errors="replace")[:500]
            except Exception:
                body = ""
            message = f"url={candidate_url} http={exc.code} reason={exc.reason} body={body}"
            attempt_errors.append(message)
            logger.exception("TEST_GEN_LLM HTTP error: %s", message)
            last_exc = exc
            continue
        except (URLError, TimeoutError, socket.timeout) as exc:
            message = f"url={candidate_url} error={str(exc)}"
            attempt_errors.append(message)
            logger.exception("TEST_GEN_LLM network/timeout error: %s", message)
            last_exc = exc
            continue
        except Exception as exc:
            message = f"url={candidate_url} unexpected={type(exc).__name__}:{str(exc)}"
            attempt_errors.append(message)
            logger.exception("TEST_GEN_LLM unexpected error: %s", message)
            last_exc = exc
            continue
    if last_exc:
        joined = " | ".join(attempt_errors)[:1200]
        raise ValueError(f"LLM request failed for all URL attempts. {joined}")

    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise ValueError("LLM response envelope is not a JSON object")
    if parsed.get("error"):
        raise ValueError(f"LLM returned error: {str(parsed.get('error'))}")

    if isinstance(parsed.get("response"), dict):
        return parsed["response"]

    # Ollama /api/generate commonly returns a JSON string in `response`.
    candidates: List[str] = []
    if isinstance(parsed.get("response"), str):
        candidates.append(parsed["response"])
    message = parsed.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        candidates.append(message["content"])
    for key in ("output", "text", "content"):
        value = parsed.get(key)
        if isinstance(value, str):
            candidates.append(value)

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            decoded = json.loads(candidate)
            if isinstance(decoded, dict):
                return decoded
        except json.JSONDecodeError:
            fragment = _extract_json_fragment(candidate)
            if fragment:
                try:
                    decoded = json.loads(fragment)
                    if isinstance(decoded, dict):
                        return decoded
                except json.JSONDecodeError:
                    pass

    # As a final fallback, if envelope itself looks like expected object, return it.
    if "scenarios" in parsed or "page_objects" in parsed or "specs" in parsed:
        return parsed

    snippet = (raw or "")[:600]
    raise ValueError(f"LLM response does not contain valid JSON payload. raw={snippet}")


def _normalize_planning_payload(planning: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(planning, dict):
        return {}
    normalized = dict(planning)
    scenarios = normalized.get("scenarios")
    if not isinstance(scenarios, list):
        for alias in ("test_scenarios", "cases", "test_cases", "scenario_list", "flows"):
            candidate = normalized.get(alias)
            if isinstance(candidate, list):
                scenarios = candidate
                break
    if isinstance(scenarios, list):
        normalized["scenarios"] = scenarios
    else:
        normalized["scenarios"] = []
    if not isinstance(normalized.get("notes"), list):
        normalized["notes"] = []
    if not isinstance(normalized.get("feature_summary"), str):
        normalized["feature_summary"] = str(normalized.get("feature_summary") or "")
    return normalized


def _normalize_codegen_payload(codegen: Dict[str, Any]) -> Dict[str, Any]:
    print("Codegen>>>>>>:",type(codegen))
    if not isinstance(codegen, dict):
        return {"page_objects": [], "specs": [], "notes": []}
    print("Codegen>>>>>>return:",codegen)
    normalized: Dict[str, Any] = dict(codegen)
    page_objects = normalized.get("page_objects")
    specs = normalized.get("specs")
    notes = normalized.get("notes")

    if not isinstance(page_objects, list):
        page_objects = []
    if not isinstance(specs, list):
        specs = []
    if not isinstance(notes, list):
        notes = []

    # Common alternative keys returned by LLMs.
    if not page_objects:
        alt_po = normalized.get("pageObjects") or normalized.get("pages")
        if isinstance(alt_po, list):
            page_objects = alt_po
    if not specs:
        alt_specs = normalized.get("tests") or normalized.get("test_specs")
        if isinstance(alt_specs, list):
            specs = alt_specs

    # Generic artifact list support.
    artifacts = normalized.get("artifacts")
    if isinstance(artifacts, list):
        for art in artifacts:
            if not isinstance(art, dict):
                continue
            kind = str(art.get("type") or art.get("artifact_type") or "").strip().lower()
            path = str(art.get("path") or art.get("relative_path") or "").strip()
            content = str(art.get("content") or art.get("code") or "").strip()
            row = {"path": path, "content": content}
            if kind in {"spec", "test", "test_spec"}:
                specs.append(row)
            elif kind in {"page_object", "page", "po"}:
                page_objects.append(row)
            elif path.endswith(".spec.ts"):
                specs.append(row)
            elif path.endswith(".ts"):
                page_objects.append(row)

    # files map support: {"tests/generated/a.spec.ts":"...","tests/pages/generated/A.ts":"..."}
    files = normalized.get("files")
    if isinstance(files, dict):
        for path, content in files.items():
            path_str = str(path or "").strip()
            content_str = str(content or "")
            if not path_str:
                continue
            row = {"path": path_str, "content": content_str}
            if path_str.endswith(".spec.ts"):
                specs.append(row)
            elif path_str.endswith(".ts"):
                page_objects.append(row)

    # Single-file fallback shapes.
    single_path = str(normalized.get("path") or normalized.get("relative_path") or "").strip()
    single_content = str(normalized.get("content") or normalized.get("code") or "").strip()
    if single_path and single_content:
        row = {"path": single_path, "content": single_content}
        if single_path.endswith(".spec.ts"):
            specs.append(row)
        elif single_path.endswith(".ts"):
            page_objects.append(row)

    def _unique_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for r in rows:
            path = str(r.get("path") or "").strip()
            content = str(r.get("content") or "")
            if not path or not content:
                continue
            key = (path, content[:120])
            if key in seen:
                continue
            seen.add(key)
            out.append({"path": path, "content": content})
        return out

    return {
        "page_objects": _unique_rows(page_objects),
        "specs": _unique_rows(specs),
        "notes": [str(n) for n in notes[:30]],
    }


def _run_crawl_context(
    *,
    base_url: str,
    seed_urls: List[str],
    max_routes: int,
) -> Dict[str, Any]:
    repo_root = _repo_root()
    script_path = repo_root / "tests" / "utils" / "crawlContext.mjs"
    if not script_path.exists():
        return {
            "base_url": base_url,
            "seed_urls": seed_urls,
            "routes": [],
            "warnings": [f"Crawl script missing at {script_path}"],
        }

    cmd = [
        "node",
        str(script_path),
        "--base-url",
        base_url,
        "--seed-urls",
        json.dumps(seed_urls),
        "--max-routes",
        str(max_routes),
        "--max-depth",
        "2",
        "--max-interactables",
        "200",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception as exc:
        return {
            "base_url": base_url,
            "seed_urls": seed_urls,
            "routes": [],
            "warnings": [f"crawl subprocess failed: {str(exc)}"],
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {
            "base_url": base_url,
            "seed_urls": seed_urls,
            "routes": [],
            "warnings": [f"crawl failed rc={proc.returncode}", stderr[:1000]],
        }
    try:
        parsed = json.loads(stdout) if stdout else {}
        if isinstance(parsed, dict):
            if stderr:
                warnings = parsed.get("warnings") or []
                warnings.append(stderr[:1000])
                parsed["warnings"] = warnings
            return parsed
    except json.JSONDecodeError:
        pass
    return {
        "base_url": base_url,
        "seed_urls": seed_urls,
        "routes": [],
        "warnings": [f"crawl returned non-json output: {stdout[:1000]}"],
    }


def _fallback_scenarios(job: GenerationJob, crawl_summary: Dict[str, Any]) -> Dict[str, Any]:
    feature = job.feature_name or "Generated Feature"
    routes = crawl_summary.get("routes") or []
    first_route = routes[0] if routes else {}
    first_nodes = (first_route.get("interactables") or [])[:20]
    primary = first_nodes[0] if first_nodes else {}
    primary_selector_hints = primary.get("selector_hints") or []
    primary_selector = primary_selector_hints[0] if primary_selector_hints else 'button:has-text("Continue")'
    primary_label = (primary.get("text") or primary.get("aria_label") or "primary action").strip() or "primary action"
    feature_presence = _feature_presence_report(job, crawl_summary)
    notes = ["Fallback scenarios used because LLM planning was unavailable or invalid."]
    if not feature_presence.get("feature_likely_present"):
        notes.append(
            "Requested feature keywords were not found strongly in crawled UI. "
            "Generated draft may be low-confidence until feature is implemented."
        )
    return {
        "feature_summary": f"Auto-generated baseline scenarios for {feature} (generic mode)",
        "scenarios": [
            {
                "id": "smoke_1",
                "title": f"{feature} smoke flow",
                "type": "SMOKE",
                "preconditions": [f"Open {job.base_url}"],
                "steps": [
                    {"action": "navigate to seed page", "selector": (first_route.get("url") or "/")},
                    {"action": f"perform {primary_label}", "selector": primary_selector, "intent_key": "generic"},
                ],
                "assertions": ["Primary flow action is reachable without runtime error"],
            },
            {
                "id": "negative_1",
                "title": f"{feature} negative validation flow",
                "type": "NEGATIVE",
                "preconditions": [f"Open {job.base_url}"],
                "steps": [
                    {"action": "trigger negative path for same action context", "selector": primary_selector, "intent_key": "generic"},
                ],
                "assertions": ["Validation, guard message, or safe failure signal appears"],
            },
        ],
        "notes": notes,
        "crawl_routes_seen": len(crawl_summary.get("routes") or []),
        "feature_presence": feature_presence,
    }


# def _build_planning_prompt(job: GenerationJob, crawl_summary: Dict[str, Any]) -> str:
#     intent_catalog = _available_intent_keys()
#     feature_presence = _feature_presence_report(job, crawl_summary)
#     return (
#         "You are a senior QA automation architect.\n"
#         "Return STRICT JSON only. No markdown, no prose.\n"
#         "Schema:\n"
#         "{\n"
#         '  "feature_summary": "string",\n'
#         '  "scenarios": [\n'
#         "    {\n"
#         '      "id": "string_short_unique",\n'
#         '      "title": "string",\n'
#         '      "type": "SMOKE|NEGATIVE",\n'
#         '      "preconditions": ["string"],\n'
#         '      "steps": [{"action":"string","selector":"string","intent_key":"string"}],\n'
#         '      "assertions": ["string"]\n'
#         "    }\n"
#         "  ],\n"
#         '  "notes": ["string"]\n'
#         "}\n"
#         f"Feature name: {job.feature_name}\n"
#         f"Feature description: {job.feature_description}\n"
#         f"Coverage mode: {job.coverage_mode}\n"
#         f"Intent hints: {json.dumps(job.intent_hints or [])}\n"
#         f"Allowed intent keys: {json.dumps(intent_catalog)}\n"
#         f"Max scenarios: {job.max_scenarios}\n"
#         f"Crawl summary: {json.dumps(crawl_summary)}\n"
#         f"Feature presence report: {json.dumps(feature_presence)}\n"
#         "Constraints:\n"
#         "- Include at least one SMOKE and one NEGATIVE scenario.\n"
#         "- Keep scenarios practical for Playwright UI tests.\n"
#         "- Keep selectors semantic and stable where possible.\n"
#         "- intent_key should come from allowed intent keys. Use 'generic' if unsure.\n"
#         "- If feature presence is weak, add a clear note and avoid inventing non-existent UI.\n"
#     )

def _build_planning_prompt(job: GenerationJob, crawl_summary: Dict[str, Any]) -> str:
    intent_catalog = _available_intent_keys()
    feature_presence = _feature_presence_report(job, crawl_summary)

    selector_map = _build_selector_map(crawl_summary)

    return (
        "You are a senior QA automation architect.\n"
        "Return STRICT JSON only.\n"
        "Schema:\n"
        "{"
        '"feature_summary":"string",'
        '"scenarios":[{'
        '"id":"string",'
        '"title":"string",'
        '"type":"SMOKE|NEGATIVE",'
        '"preconditions":["string"],'
        '"steps":[{"action":"string","selector":"string","intent_key":"string"}],'
        '"assertions":["string"]'
        "}],"
        '"notes":["string"]'
        "}\n"
        f"Feature name: {job.feature_name}\n"
        f"Feature description: {job.feature_description}\n"
        f"Allowed intent keys: {json.dumps(intent_catalog)}\n"
        f"Selector map: {json.dumps(selector_map)}\n"
        f"Feature presence: {json.dumps(feature_presence)}\n"
        "Rules:\n"
        "- DO NOT invent selectors.\n"
        "- Use selectors from selector map.\n"
        "- Include ALL scenarios.\n"
        "- At least one SMOKE and one NEGATIVE.\n"
    )


def _scenario_to_comment_lines(scenario: Dict[str, Any]) -> str:
    lines = []
    for idx, step in enumerate(scenario.get("steps") or [], start=1):
        lines.append(f"  console.log('Generated step {idx}: {_render_step_name(step, 'action')}');")
    return "\n".join(lines) if lines else "  console.log('Generated scenario execution');"


def _build_template_artifacts(
    job: GenerationJob,
    planning: Dict[str, Any],
    crawl_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    def _ident(text: str, prefix: str) -> str:
        parts = [p for p in re.split(r"[^a-zA-Z0-9]+", (text or "").strip()) if p]
        if not parts:
            return prefix
        first = parts[0].lower()
        rest = "".join(p[:1].upper() + p[1:] for p in parts[1:])
        out = f"{first}{rest}"
        if out[0].isdigit():
            return f"{prefix}{out.capitalize()}"
        return out

    def _method_name(text: str, prefix: str) -> str:
        base = _ident(text, prefix)
        if not base.startswith(prefix):
            return f"{prefix}{base[:1].upper()}{base[1:]}"
        return base

    feature_slug = _slug(job.feature_name)
    page_class = f"{_camel(job.feature_name)}Page"
    page_path = f"tests/pages/generated/{page_class}.ts"
    spec_path = f"tests/generated/{feature_slug}.spec.ts"
    scenarios = (planning.get("scenarios") or [])[: job.max_scenarios]

    selector_to_field: Dict[str, str] = {}
    field_to_selector: Dict[str, str] = {}
    action_methods: Dict[Tuple[int, int], Dict[str, str]] = {}
    assertion_methods: Dict[Tuple[int, int], str] = {}
    used_names: set[str] = set()

    for s_idx, scenario in enumerate(scenarios):
        for st_idx, step in enumerate(scenario.get("steps") or []):
            raw_selector = _render_failed_selector(step)
            hints = [
                str(step.get("action") or ""),
                str(step.get("name") or ""),
                str(step.get("selector") or ""),
                str(step.get("locator") or ""),
                str(scenario.get("title") or ""),
                str(job.feature_name or ""),
            ]
            selector = _pick_best_selector(crawl_summary, hints, raw_selector)
            if selector not in selector_to_field:
                field_name = _ident(step.get("action") or f"action {len(selector_to_field)+1}", "actionSelector")
                if not field_name.endswith("Selector"):
                    field_name = f"{field_name}Selector"
                base_name = field_name
                counter = 2
                while field_name in used_names:
                    field_name = f"{base_name}{counter}"
                    counter += 1
                used_names.add(field_name)
                selector_to_field[selector] = field_name
                field_to_selector[field_name] = selector
            method_name = _method_name(step.get("action") or f"run step {st_idx + 1}", "do")
            base_method = method_name
            counter = 2
            while method_name in used_names:
                method_name = f"{base_method}{counter}"
                counter += 1
            used_names.add(method_name)
            action_methods[(s_idx, st_idx)] = {
                "method_name": method_name,
                "field_name": selector_to_field[selector],
                "selector": selector,
                "intent_key": _render_intent_key(step),
                "use_of_selector": _render_step_name(step, "click on generated action"),
            }

        for a_idx, assertion in enumerate(scenario.get("assertions") or []):
            assertion_text = str(assertion if not isinstance(assertion, dict) else assertion.get("type") or "assertion")
            method_name = _method_name(assertion_text or f"assertion {a_idx + 1}", "verify")
            base_method = method_name
            counter = 2
            while method_name in used_names:
                method_name = f"{base_method}{counter}"
                counter += 1
            used_names.add(method_name)
            assertion_methods[(s_idx, a_idx)] = method_name

    locator_lines: List[str] = []
    for field_name, selector in field_to_selector.items():
        selector_escaped = selector.replace("'", "\\'")
        locator_lines.append(f"  {field_name} = '{selector_escaped}';")
    if not locator_lines:
        locator_lines = ["  primaryActionSelector = 'button:has-text(\"Continue\")';"]
        field_to_selector["primaryActionSelector"] = 'button:has-text("Continue")'

    action_method_lines = [
        "  async openHomePage() {",
        f"    await this.page.goto('{job.base_url.rstrip('/')}/');",
        "  }",
        "",
        "  actionLocator(selector: string): Locator {",
        "    return this.page.locator(selector).first();",
        "  }",
        "",
    ]
    for s_idx, scenario in enumerate(scenarios):
        for st_idx, step in enumerate(scenario.get("steps") or []):
            meta = action_methods.get((s_idx, st_idx))
            if not meta:
                continue
            action_method_lines.extend(
                [
                    f"  async {meta['method_name']}() {{",
                    f"    await this.page.click(this.{meta['field_name']});",
                    "  }",
                    "",
                ]
            )

    assertion_method_lines = []
    for s_idx, scenario in enumerate(scenarios):
        for a_idx, _ in enumerate(scenario.get("assertions") or []):
            method_name = assertion_methods.get((s_idx, a_idx))
            if not method_name:
                continue
            first_selector = next(iter(field_to_selector.values()))
            assertion_lines = _render_assertion_lines(scenario, crawl_summary, first_selector)
            body = []
            for line in assertion_lines[:1]:
                body.append(line.replace("page.", "this.page.").replace("  await", "    await"))
            if not body:
                body = ["    await expect(this.page.locator('body')).toBeVisible();"]
            assertion_method_lines.extend(
                [
                    f"  async {method_name}() {{",
                    *body,
                    "  }",
                    "",
                ]
            )

    if not assertion_method_lines:
        assertion_method_lines = [
            "  async verifyPageLoaded() {",
            "    await expect(this.page.locator('body')).toBeVisible();",
            "  }",
            "",
        ]

    page_content = f"""import {{ Page, Locator, expect }} from '@playwright/test';

export class {page_class} {{
  readonly page: Page;

  constructor(page: Page) {{
    this.page = page;
  }}

  // ===== Locators =====
{os.linesep.join(locator_lines)}

  // ===== Actions =====
{os.linesep.join(action_method_lines)}
  // ===== Assertions =====
{os.linesep.join(assertion_method_lines)}
}}
"""

    test_blocks: List[str] = []
    for s_idx, scenario in enumerate(scenarios):
        scenario_type = str(scenario.get("type") or "SMOKE").upper()
        title = str(scenario.get("title") or "Generated scenario")
        full_title = f"{scenario_type} - {title}"
        lines = [
            f"  test('{full_title}', async ({{ page }}, testInfo) => {{",
            f"    const flow = new {page_class}(page);",
            "    await flow.openHomePage();",
            "",
        ]
        for st_idx, step in enumerate(scenario.get("steps") or [], start=1):
            meta = action_methods.get((s_idx, st_idx - 1))
            if not meta:
                continue
            failed_selector = meta["selector"].replace("'", "\\'")
            use_of_selector = meta["use_of_selector"].replace("'", "\\'")
            lines.extend(
                [
                    f"    // Step {st_idx}: {_render_step_name(step, 'perform action')}",
                    "    await selfHealingClick(",
                    "      page,",
                    f"      flow.actionLocator(flow.{meta['field_name']}),",
                    f"      '{failed_selector}',",
                    "      testInfo,",
                    "      {",
                    f"        use_of_selector: '{use_of_selector}',",
                    "        selector_type: 'generated',",
                    f"        intent_key: '{meta['intent_key']}',",
                    "      }",
                    "    );",
                    "",
                ]
            )
        scenario_assertions = scenario.get("assertions") or []
        for a_idx, assertion in enumerate(scenario_assertions):
            method_name = assertion_methods.get((s_idx, a_idx))
            if method_name:
                lines.append(f"    await flow.{method_name}();")

        # 🔥 safety assertion for validator + runtime stability
        lines.append("    await expect(page.locator('body')).toBeVisible();")
        lines.extend(["  });", ""])
        test_blocks.append(os.linesep.join(lines))

    spec_content = f"""import {{ test, expect }} from '../baseTest';
import {{ selfHealingClick }} from '../utils/selfHealing';
import {{ {page_class} }} from '../pages/generated/{page_class}';

test.describe('{job.feature_name} Feature', () => {{
{os.linesep.join(test_blocks)}
}});
"""

    return [
        {"artifact_type": GeneratedArtifact.TYPE_PAGE_OBJECT, "relative_path": page_path, "content": page_content},
        {"artifact_type": GeneratedArtifact.TYPE_SPEC, "relative_path": spec_path, "content": spec_content},
    ]


# def _build_codegen_prompt(job: GenerationJob, planning: Dict[str, Any], crawl_summary: Dict[str, Any]) -> str:
#     intent_catalog = _available_intent_keys()
#     return (
#         "You generate Playwright TypeScript test files.\n"
#         "Return STRICT JSON only.\n"
#         "Schema:\n"
#         "{\n"
#         '  "page_objects": [{"path":"tests/pages/generated/Name.ts","content":"..."}],\n'
#         '  "specs": [{"path":"tests/generated/name.spec.ts","content":"..."}],\n'
#         '  "notes": ["string"]\n'
#         "}\n"
#         f"Feature: {job.feature_name}\n"
#         f"Feature Description: {job.feature_description}\n"
#         f"Planning: {json.dumps(planning)}\n"
#         f"Crawl summary: {json.dumps(crawl_summary)}\n"
#         f"Allowed intent keys: {json.dumps(intent_catalog)}\n"
#         "Mandatory constraints:\n"
#         "- spec files must import: test, expect from '../baseTest'\n"
#         "- spec files must import selfHealingClick from '../utils/selfHealing'\n"
#         "- use intent_key in selfHealingClick options from allowed intent keys or generic\n"
#         "- avoid waitForTimeout/setTimeout/test.only\n"
#         "- output paths strictly under tests/generated or tests/pages/generated\n"
#         "- keep output application-agnostic; do not assume ecommerce-only entities unless crawl supports it\n"
#     )

def _build_codegen_prompt(job: GenerationJob, planning: Dict[str, Any], crawl_summary: Dict[str, Any]) -> str:

    intent_catalog = _available_intent_keys()
    selector_map = _build_selector_map(crawl_summary)

    return (
        "You generate Playwright TypeScript test files.\n"
        "Return STRICT JSON ONLY.\n"
        "Schema:\n"
        "{"
        '"page_objects":[{"path":"tests/pages/generated/X.ts","content":"..."}],'
        '"specs":[{"path":"tests/generated/X.spec.ts","content":"..."}],'
        '"notes":["string"]'
        "}\n"
        f"Feature: {job.feature_name}\n"
        f"Planning: {json.dumps(planning)}\n"
        f"Selector map: {json.dumps(selector_map)}\n"
        f"Allowed intent keys: {json.dumps(intent_catalog)}\n"
        "Rules:\n"
        "- NEVER invent selectors.\n"
        "- Use ONLY selector map values.\n"
        "- import test, expect from '../baseTest'\n"
        "- import selfHealingClick from '../utils/selfHealing'\n"
        "- include intent_key in healing options\n"
        "- avoid waitForTimeout/setTimeout/test.only\n"
        "- DO NOT skip any scenario or step.\n"
    )


def _build_codegen_retry_prompt(job: GenerationJob, planning: Dict[str, Any],crawl_summary: Dict[str, Any]) -> str:
    intent_catalog = _available_intent_keys()
    return (
        "Return STRICT JSON only.\n"
        "Do not return empty arrays.\n"
        "Schema exactly:\n"
        "{\n"
        '  "page_objects": [{"path":"tests/pages/generated/Name.ts","content":"typescript code"}],\n'
        '  "specs": [{"path":"tests/generated/name.spec.ts","content":"typescript code"}],\n'
        '  "notes": ["short note"]\n'
        "}\n"
        "Constraints:\n"
        "- At least one page object and one spec are mandatory.\n"
        "- Spec must import `test, expect` from `../baseTest`.\n"
        "- Spec must use `selfHealingClick` and include `intent_key`.\n"
        "- Paths must be under tests/generated and tests/pages/generated.\n"
        f"Feature name: {job.feature_name}\n"
        f"Feature Description: {job.feature_description}\n"
        f"Planning: {json.dumps(planning)}\n"
        f"Crawl summary: {json.dumps(crawl_summary)}\n"
        f"Allowed intent keys: {json.dumps(intent_catalog)}\n"
    )


def _is_codegen_empty(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return True
    return not (payload.get("page_objects") or payload.get("specs"))


def _extract_codegen_artifacts(
    job: GenerationJob,
    codegen_json: Dict[str, Any],
    planning: Dict[str, Any],
    crawl_summary: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    notes = [str(n) for n in (codegen_json.get("notes") or [])[:20]]
    artifacts: List[Dict[str, Any]] = []
    for po in codegen_json.get("page_objects") or []:
        artifacts.append(
            {
                "artifact_type": GeneratedArtifact.TYPE_PAGE_OBJECT,
                "relative_path": str(po.get("path") or ""),
                "content": str(po.get("content") or ""),
            }
        )
    for spec in codegen_json.get("specs") or []:
        artifacts.append(
            {
                "artifact_type": GeneratedArtifact.TYPE_SPEC,
                "relative_path": str(spec.get("path") or ""),
                "content": str(spec.get("content") or ""),
            }
        )

    valid_artifacts = [a for a in artifacts if a["relative_path"] and a["content"]]
    
    if not valid_artifacts:
        valid_artifacts = _build_template_artifacts(job, planning, crawl_summary)
        notes.append("Fallback code templates used because LLM codegen output was empty/invalid.")
    return valid_artifacts, notes


def _runtime_validate_selectors(
    validated_artifacts: List[Dict[str, Any]],
    *,
    base_url: str,
    crawl_summary: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not _runtime_selector_validation_enabled():
        return validated_artifacts, {
            "enabled": False,
            "checked_selectors": 0,
            "missing_selectors": 0,
            "warnings": [],
        }

    repo_root = _repo_root()
    validator_script = repo_root / "tests" / "utils" / "validateSelectors.mjs"
    if not validator_script.exists():
        return validated_artifacts, {
            "enabled": True,
            "checked_selectors": 0,
            "missing_selectors": 0,
            "warnings": [f"Selector validator script missing at {validator_script}"],
        }

    all_selectors: List[str] = []
    for artifact in validated_artifacts:
        if artifact.get("artifact_type") != GeneratedArtifact.TYPE_SPEC:
            continue
        for selector in _extract_selector_literals_from_text(str(artifact.get("content") or "")):
            if selector and selector not in all_selectors:
                all_selectors.append(selector)

    if not all_selectors:
        return validated_artifacts, {
            "enabled": True,
            "checked_selectors": 0,
            "missing_selectors": 0,
            "warnings": [],
        }

    route_urls = [str(r.get("url") or "").strip() for r in (crawl_summary.get("routes") or []) if r.get("url")]
    if not route_urls:
        route_urls = [base_url]
    route_urls = route_urls[:30]

    cmd = [
        "node",
        str(validator_script),
        "--base-url",
        base_url,
        "--urls",
        json.dumps(route_urls),
        "--selectors",
        json.dumps(all_selectors),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        warning = f"Runtime selector validation failed to run: {str(exc)}"
        return validated_artifacts, {
            "enabled": True,
            "checked_selectors": len(all_selectors),
            "missing_selectors": 0,
            "warnings": [warning],
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        warning = f"Runtime selector validation rc={proc.returncode}: {(stderr or stdout)[:500]}"
        return validated_artifacts, {
            "enabled": True,
            "checked_selectors": len(all_selectors),
            "missing_selectors": 0,
            "warnings": [warning],
        }

    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return validated_artifacts, {
            "enabled": True,
            "checked_selectors": len(all_selectors),
            "missing_selectors": 0,
            "warnings": [f"Runtime selector validation returned non-JSON: {stdout[:500]}"],
        }

    result_rows = parsed.get("results") or []
    missing_map: Dict[str, str] = {}
    for row in result_rows:
        selector = str(row.get("selector") or "").strip()
        if not selector:
            continue
        if not bool(row.get("matched")):
            error_text = str(row.get("error") or "selector not found on crawled routes").strip()
            missing_map[selector] = error_text

    if not missing_map:
        return validated_artifacts, {
            "enabled": True,
            "checked_selectors": len(all_selectors),
            "missing_selectors": 0,
            "warnings": [],
        }

    updated: List[Dict[str, Any]] = []
    for artifact in validated_artifacts:
        content = str(artifact.get("content") or "")
        selectors_here = _extract_selector_literals_from_text(content)
        missing_here = [s for s in selectors_here if s in missing_map]
        if not missing_here:
            updated.append(artifact)
            continue

        existing_errors = list(artifact.get("validation_errors") or [])
        existing_warnings = list(artifact.get("warnings") or [])
        failure_line = (
            "Runtime selector validation failed for selector(s): "
            + ", ".join(missing_here[:10])
        )
        existing_errors.append(failure_line)
        for selector in missing_here[:10]:
            existing_warnings.append(f"{selector}: {missing_map.get(selector, 'not found')}")

        artifact["validation_errors"] = existing_errors
        artifact["warnings"] = existing_warnings
        artifact["validation_status"] = GeneratedArtifact.INVALID
        updated.append(artifact)

    return updated, {
        "enabled": True,
        "checked_selectors": len(all_selectors),
        "missing_selectors": len(missing_map),
        "warnings": [],
    }


def _validate_relative_path(relative_path: str) -> List[str]:
    errors: List[str] = []
    rp = (relative_path or "").replace("\\", "/").strip()
    if not rp:
        return ["Missing relative_path"]
    if rp.startswith("/") or ".." in Path(rp).parts:
        errors.append("Path traversal or absolute path is not allowed")
    allowed_prefixes = ("tests/generated/", "tests/pages/generated/")
    if not rp.startswith(allowed_prefixes):
        errors.append("Path must be under tests/generated or tests/pages/generated")
    if not (rp.endswith(".ts") or rp.endswith(".spec.ts")):
        errors.append("Generated files must be TypeScript (.ts / .spec.ts)")
    return errors


def _validate_artifact_content(artifact_type: str, content: str) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    text = content or ""

    forbidden_patterns = [
        (r"\bwaitForTimeout\s*\(", "Forbidden waitForTimeout usage"),
        (r"\bsetTimeout\s*\(", "Forbidden setTimeout usage"),
        (r"\btest\.only\s*\(", "Forbidden test.only usage"),
        (r"\bprocess\.exit\s*\(", "Forbidden process.exit usage"),
        (r"\.nth\(\d+\)", "Avoid brittle nth(index) selectors"),
    ]
    for pattern, message in forbidden_patterns:
        if re.search(pattern, text):
            if "Avoid brittle" in message:
                warnings.append(message)
            else:
                errors.append(message)

    if artifact_type == GeneratedArtifact.TYPE_SPEC:
        required = [
            ("from '../baseTest'", "Spec must import from ../baseTest"),
            ("selfHealingClick", "Spec must use/import selfHealingClick"),
            ("intent_key", "Spec must include intent_key in healing options"),
            ("expect(", "Spec must include assertion"),
        ]
        for needle, msg in required:
            if needle not in text:
                errors.append(msg)
    if artifact_type == GeneratedArtifact.TYPE_PAGE_OBJECT:
        if "class " not in text:
            errors.append("Page object file must define a class")
        if "constructor(" not in text:
            errors.append("Page object class must define constructor")

    return errors, warnings


def _typescript_parse_check(relative_path: str, content: str) -> List[str]:
    repo_root = _repo_root()
    script = (
        "const fs=require('fs');"
        "let ts;"
        "try{ts=require('typescript');}catch(e){console.log('__TS_MISSING__');process.exit(0)}"
        "const file=process.argv[1];"
        "const src=fs.readFileSync(file,'utf8');"
        "const out=ts.transpileModule(src,{compilerOptions:{target:'ES2020',module:'CommonJS'}});"
        "const diags=out.diagnostics||[];"
        "if(diags.length){"
        "console.log(JSON.stringify(diags.slice(0,5).map(d=>ts.flattenDiagnosticMessageText(d.messageText,' '))))"
        "}"
    )
    tmp_dir = repo_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / f"gen_validate_{_slug(relative_path)}"
    tmp_file = tmp_file.with_suffix(".ts")
    tmp_file.write_text(content, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["node", "-e", script, str(tmp_file)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except Exception as exc:
        return [f"TypeScript parse check failed to run: {str(exc)}"]
    finally:
        try:
            tmp_file.unlink(missing_ok=True)
        except Exception:
            pass

    stdout = (proc.stdout or "").strip()
    if stdout == "__TS_MISSING__":
        return []
    if not stdout:
        return []
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        return [stdout[:500]]
    return []


def _validate_artifacts(artifacts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    validated: List[Dict[str, Any]] = []
    invalid_count = 0
    warnings_count = 0

    for artifact in artifacts:
        artifact_type = artifact.get("artifact_type") or GeneratedArtifact.TYPE_SPEC
        relative_path = str(artifact.get("relative_path") or "")
        content = str(artifact.get("content") or "")

        errors = _validate_relative_path(relative_path)
        content_errors, content_warnings = _validate_artifact_content(artifact_type, content)
        errors.extend(content_errors)
        warnings = content_warnings
        ts_errors = _typescript_parse_check(relative_path, content)
        errors.extend(ts_errors)

        is_valid = len(errors) == 0
        if not is_valid:
            invalid_count += 1
        warnings_count += len(warnings)

        validated.append(
            {
                "artifact_type": artifact_type,
                "relative_path": relative_path,
                "content": content,
                "checksum": _sha256(content),
                "validation_status": GeneratedArtifact.VALID if is_valid else GeneratedArtifact.INVALID,
                "validation_errors": errors,
                "warnings": warnings,
            }
        )

    summary = {
        "total_artifacts": len(validated),
        "invalid_artifacts": invalid_count,
        "warnings": warnings_count,
        "valid_artifacts": len(validated) - invalid_count,
    }
    return validated, summary


def _sanitize_scenarios(raw_scenarios: List[Dict[str, Any]], max_scenarios: int) -> List[Dict[str, Any]]:
    scenarios: List[Dict[str, Any]] = []
    seen_titles = set()
    for idx, item in enumerate(raw_scenarios[:max_scenarios], start=1):
        title = (item.get("title") or f"Generated Scenario {idx}").strip()
        if title.lower() in seen_titles:
            title = f"{title} #{idx}"
        seen_titles.add(title.lower())
        scenarios.append(
            {
                "id": (item.get("id") or f"scenario_{idx}").strip(),
                "title": title,
                "type": _normalize_scenario_type(item.get("type") or "SMOKE"),
                "preconditions": _safe_json(item.get("preconditions") or [], []),
                "steps": _safe_json(item.get("steps") or [], []),
                "assertions": _safe_json(item.get("assertions") or [], []),
            }
        )
    # Ensure at least one smoke and one negative.
    types = {s["type"] for s in scenarios}
    if GenerationScenario.TYPE_SMOKE not in types:
        scenarios.insert(
            0,
            {
                "id": "smoke_auto",
                "title": "Auto-added smoke scenario",
                "type": GenerationScenario.TYPE_SMOKE,
                "preconditions": [],
                "steps": [{"action": "open feature page", "selector": "/", "intent_key": "generic"}],
                "assertions": ["Page renders without errors"],
            },
        )
    if GenerationScenario.TYPE_NEGATIVE not in types:
        scenarios.append(
            {
                "id": "negative_auto",
                "title": "Auto-added negative scenario",
                "type": GenerationScenario.TYPE_NEGATIVE,
                "preconditions": [],
                "steps": [{"action": "trigger invalid action", "selector": "text=Submit", "intent_key": "generic"}],
                "assertions": ["Validation message appears"],
            }
        )
    return scenarios[:max_scenarios]


def generate_job_draft(job: GenerationJob) -> GenerationJob:
    job.job_status = GenerationJob.STATE_DRAFTING
    job.error_message = ""
    job.drafting_started_on = timezone.now()
    job.max_scenarios = job.max_scenarios or _max_scenarios_default()
    job.max_routes = job.max_routes or _max_routes_default()
    if not job.llm_model:
        job.llm_model = _default_test_gen_model()
    job.save(
        update_fields=[
            "job_status",
            "error_message",
            "drafting_started_on",
            "max_scenarios",
            "max_routes",
            "llm_model",
            "last_modified",
        ]
    )

    try:
        crawl_summary = _run_crawl_context(
            base_url=job.base_url,
            seed_urls=job.seed_urls or [],
            max_routes=job.max_routes,
        )
        feature_presence = _feature_presence_report(job, crawl_summary)
        crawl_summary["feature_presence"] = feature_presence
        if not feature_presence.get("feature_likely_present"):
            warnings = crawl_summary.get("warnings") or []
            warnings.append(
                "Requested feature appears weakly represented in current UI crawl. "
                "Implement feature first or provide correct seed URLs before generation."
            )
            crawl_summary["warnings"] = warnings
            if _feature_presence_required():
                job.crawl_summary = crawl_summary
                job.feature_summary = (
                    "Draft blocked: requested feature not detected in current application crawl."
                )
                job.llm_notes = [
                    "Strict feature presence gate enabled.",
                    "Generation aborted to avoid irrelevant artifacts.",
                ]
                job.validation_summary = {
                    "total_artifacts": 0,
                    "valid_artifacts": 0,
                    "invalid_artifacts": 0,
                    "warnings": len(warnings),
                    "blocked_by_feature_presence": True,
                }
                job.job_status = GenerationJob.STATE_FAILED
                job.error_message = (
                    "Feature presence gate failed. Add/enable requested feature in app "
                    "or provide accurate seed_urls, then retry generation."
                )
                job.drafting_finished_on = timezone.now()
                job.save(
                    update_fields=[
                        "crawl_summary",
                        "feature_summary",
                        "llm_notes",
                        "validation_summary",
                        "job_status",
                        "error_message",
                        "drafting_finished_on",
                        "last_modified",
                    ]
                )
                return job
        planning = None
        if _test_gen_enabled():
            try:
                planning_prompt = _build_planning_prompt(job, crawl_summary)
                planning = _call_ollama_json(
                    prompt=planning_prompt,
                    model=job.llm_model or _default_test_gen_model(),
                    temperature=float(job.llm_temperature or 0.0),
                    timeout_seconds=_llm_timeout(),
                    num_predict=900,
                )
                planning = _normalize_planning_payload(planning)
            except (URLError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
                planning = None
                crawl_warnings = crawl_summary.get("warnings") or []
                crawl_warnings.append(f"Planning LLM fallback: {str(exc)}")
                crawl_summary["warnings"] = crawl_warnings
        if planning and not isinstance(planning.get("scenarios"), list):
            crawl_warnings = crawl_summary.get("warnings") or []
            crawl_warnings.append("Planning output missing `scenarios` list. Using fallback scenarios.")
            crawl_summary["warnings"] = crawl_warnings
            planning = None
        if planning and len(planning.get("scenarios") or []) == 0:
            crawl_warnings = crawl_summary.get("warnings") or []
            crawl_warnings.append("Planning output contained zero scenarios. Using fallback scenarios.")
            crawl_summary["warnings"] = crawl_warnings
            planning = None
        if not planning:
            planning = _fallback_scenarios(job, crawl_summary)
        
        scenarios = _sanitize_scenarios(planning.get("scenarios") or [], job.max_scenarios)
        codegen_json = None
        llm_notes: List[str] = [str(n) for n in planning.get("notes") or []]
        if _test_gen_enabled():
            try: 
                codegen_json = None
                llm_notes.append("Using template-based artifact generation (LLM codegen skipped).")
                # codegen_prompt = _build_codegen_prompt(job, planning, crawl_summary)
                
                # codegen_json = _call_ollama_json(
                #     prompt=codegen_prompt,
                #     model=job.llm_model or _default_test_gen_model(),
                #     temperature=float(job.llm_temperature or 0.0),
                #     timeout_seconds=_llm_timeout(),
                #     num_predict=800,
                # )
                # print("llm code json",codegen_json)
                # codegen_json = _normalize_codegen_payload(codegen_json)
                # if _is_codegen_empty(codegen_json):
                #     llm_notes.append("LLM returned empty codegen → using template fallback.")
                #     codegen_json = {}
                # print("normalized Codegen Json>>>>>>:",json.dumps(codegen_json,indent=4))
                # if _is_codegen_empty(codegen_json):
                #     llm_notes.append("Primary codegen returned empty artifacts. Retrying with compact prompt.")
                #     retry_prompt = _build_codegen_retry_prompt(job, planning, crawl_summary)
                #     codegen_retry_json = _call_ollama_json(
                #         prompt=retry_prompt,
                #         model=job.llm_model or _default_test_gen_model(),
                #         temperature=float(job.llm_temperature or 0.0),
                #         timeout_seconds=_llm_timeout(),
                #         num_predict=1400,
                #     )
                #     codegen_json = _normalize_codegen_payload(codegen_retry_json)
                #     print("Codegen Retry Json>>>>>>:",json.dumps(codegen_json,indent=4))
                # llm_notes.append(
                #     "Codegen payload stats: "
                #     f"page_objects={len(codegen_json.get('page_objects') or [])}, "
                #     f"specs={len(codegen_json.get('specs') or [])}"
                # )
            except (URLError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
                llm_notes.append(f"Codegen LLM fallback: {str(exc)}")
                codegen_json = None

        print("Codegen Json final>>>>>>:",json.dumps(codegen_json,indent=4))
        artifacts, notes = _extract_codegen_artifacts(
            job,
            codegen_json or {},
            {"scenarios": scenarios},
            crawl_summary,
        )
        llm_notes.extend(notes)
        validated_artifacts, validation_summary = _validate_artifacts(artifacts)
        validated_artifacts, runtime_selector_summary = _runtime_validate_selectors(
            validated_artifacts,
            base_url=job.base_url,
            crawl_summary=crawl_summary,
        )
        invalid_artifacts = sum(
            1 for artifact in validated_artifacts if artifact.get("validation_status") != GeneratedArtifact.VALID
        )
        validation_summary = {
            **validation_summary,
            "invalid_artifacts": invalid_artifacts,
            "valid_artifacts": len(validated_artifacts) - invalid_artifacts,
            "runtime_selector_validation": runtime_selector_summary,
            "runtime_selector_checked_count": runtime_selector_summary.get("checked_selectors", 0),
            "runtime_selector_missing_count": runtime_selector_summary.get("missing_selectors", 0),
        }

        job.scenarios.all().delete()
        job.artifacts.all().delete()

        scenario_rows = []
        for index, sc in enumerate(scenarios, start=1):
            scenario_rows.append(
                GenerationScenario(
                    job=job,
                    scenario_id=sc["id"],
                    title=sc["title"],
                    scenario_type=sc["type"],
                    priority=index,
                    preconditions=sc.get("preconditions") or [],
                    steps=sc.get("steps") or [],
                    expected_assertions=sc.get("assertions") or [],
                    selected_for_materialization=True,
                )
            )
        GenerationScenario.objects.bulk_create(scenario_rows)

        artifact_rows = []
        for art in validated_artifacts:
            artifact_rows.append(
                GeneratedArtifact(
                    job=job,
                    artifact_type=art["artifact_type"],
                    relative_path=art["relative_path"],
                    content_draft=art["content"],
                    content_final=art["content"],
                    checksum=art["checksum"],
                    validation_status=art["validation_status"],
                    validation_errors=art["validation_errors"],
                    warnings=art["warnings"],
                )
            )
        GeneratedArtifact.objects.bulk_create(artifact_rows)

        job.crawl_summary = crawl_summary
        job.feature_summary = str(planning.get("feature_summary") or "")
        job.llm_notes = llm_notes[:100]
        job.validation_summary = validation_summary
        job.drafting_finished_on = timezone.now()
        job.job_status = (
            GenerationJob.STATE_DRAFT_READY
            if validation_summary.get("valid_artifacts", 0) > 0
            else GenerationJob.STATE_FAILED
        )
        if job.job_status == GenerationJob.STATE_FAILED:
            job.error_message = "No valid artifacts were generated."
        job.save(
            update_fields=[
                "crawl_summary",
                "feature_summary",
                "llm_notes",
                "validation_summary",
                "drafting_finished_on",
                "job_status",
                "error_message",
                "last_modified",
            ]
        )
        return job
    except Exception as exc:
        job.job_status = GenerationJob.STATE_FAILED
        job.error_message = str(exc)
        job.drafting_finished_on = timezone.now()
        job.save(update_fields=["job_status", "error_message", "drafting_finished_on", "last_modified"])
        return job


def apply_approval_selection(
    *,
    job: GenerationJob,
    include_scenario_ids: List[str] | None,
    exclude_scenario_ids: List[str] | None,
) -> None:
    include_set = set(include_scenario_ids or [])
    exclude_set = set(exclude_scenario_ids or [])
    if not include_set and not exclude_set:
        return
    for scenario in job.scenarios.all():
        selected = True
        if include_set:
            selected = scenario.scenario_id in include_set
        if scenario.scenario_id in exclude_set:
            selected = False
        scenario.selected_for_materialization = selected
        scenario.save(update_fields=["selected_for_materialization", "last_modified"])


@dataclass
class MaterializationResult:
    written_files: List[str]
    conflicts: List[str]
    errors: List[str]

    @property
    def ok(self) -> bool:
        return not self.conflicts and not self.errors


def materialize_job(job: GenerationJob, *, allow_overwrite: bool = False) -> MaterializationResult:
    repo_root = _repo_root()
    artifacts = job.artifacts.filter(validation_status=GeneratedArtifact.VALID).order_by("relative_path")
    written_files: List[str] = []
    conflicts: List[str] = []
    errors: List[str] = []
    manifest: List[Dict[str, Any]] = []

    for artifact in artifacts:
        rp = (artifact.relative_path or "").replace("\\", "/").strip()
        path_errors = _validate_relative_path(rp)
        if path_errors:
            errors.append(f"{rp}: {'; '.join(path_errors)}")
            continue

        target = (repo_root / rp).resolve()
        try:
            target.relative_to(repo_root.resolve())
        except ValueError:
            errors.append(f"{rp}: resolved outside repository root")
            continue

        if target.exists() and not allow_overwrite:
            conflicts.append(rp)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        content = artifact.content_final or artifact.content_draft or ""
        target.write_text(content, encoding="utf-8")
        checksum = _sha256(content)
        artifact.checksum = checksum
        artifact.content_final = content
        artifact.save(update_fields=["checksum", "content_final", "last_modified"])
        written_files.append(rp)
        manifest.append(
            {
                "path": rp,
                "checksum": checksum,
                "artifact_type": artifact.artifact_type,
            }
        )

    if not conflicts and not errors:
        job.job_status = GenerationJob.STATE_MATERIALIZED
        job.materialized_on = timezone.now()
        job.materialized_manifest = manifest
        job.save(update_fields=["job_status", "materialized_on", "materialized_manifest", "last_modified"])

    return MaterializationResult(
        written_files=written_files,
        conflicts=conflicts,
        errors=errors,
    )
