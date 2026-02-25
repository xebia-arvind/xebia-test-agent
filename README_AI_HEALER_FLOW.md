# AI Healer Flow Guide

## Purpose
This document explains how your Playwright self-healing framework and Django analytics platform work together end-to-end.

## High-Level Architecture
1. Playwright test execution layer (`tests/`)
2. Healer API and validation layer (`curertestai/`)
3. Test analytics persistence layer (`test_analytics/`)
4. Dashboard visualization layer (`/test-analytics/dashboard/`)

---

## 1. Test Execution Layer (Playwright)

### Entry points
- `tests/baseTest.ts`
- `tests/utils/selfHealing.ts`
- `tests/utils/failureContext.ts`
- `tests/utils/sendToDjango.ts`

### Runtime flow
1. Test runs normally with Playwright.
2. Critical interactions use `selfHealingClick(...)`.
3. If original locator works:
   - Step event logged as `PASSED`.
4. If original locator fails:
   - Healer API `/api/heal/` is called.
   - Response is validated and used (or blocked).
5. In `afterEach` (`baseTest.ts`), full result payload is built and posted to:
   - `POST /test-analytics/test-result/`

### Key payload fields sent to analytics
- `run_id`, `build_id`, `environment`
- `test_name`, `status`, `error_message`
- `failed_selector`, `healed_selector`
- `healing_attempted`, `healing_outcome`, `healing_confidence`
- `validation_status`, `ui_change_level`
- `history_assisted`, `history_hits`
- `step_events` (timeline)

---

## 2. Healer Service Layer (`curertestai`)

### Main API
- `POST /api/heal/`
- Core file: `curertestai/views.py`

### Processing stages
1. Parse request and DOM input.
2. Extract semantic DOM (`DOMExtractor`).
3. Generate candidate selectors (`MatchingEngine`).
4. Validate candidates (`validation_engine.select_validated_candidate`) using:
   - intent policy rules
   - history boost from prior records
   - optional LLM score (`_llm_score`)
5. Return either:
   - `validation_status=VALID` with `chosen` selector, or
   - `validation_status=NO_SAFE_MATCH`

### Saved healer metadata (`HealerRequest`)
- `intent_key`
- `validation_status`, `validation_reason`
- `dom_fingerprint`
- `candidate_snapshot`
- `history_assisted`, `history_hits`
- `ui_change_level`
- `confidence`, `success`

---

## 3. Failure Analytics Layer (`test_analytics`)

### APIs
- `POST /test-analytics/test-result/` (save per test)
- `GET /test-analytics/summary/` (dashboard aggregates)
- `GET /test-analytics/test-result/<id>/` (single result detail)

### Models
- `TestRun` (group by run)
- `TestCaseResult` (per test result + timeline + healing metadata)

### Classification logic
- `test_analytics/classifier.py` enriches:
  - `failure_category`
  - `healing_outcome` normalization

---

## 4. Dashboard Layer

### URL
- `/test-analytics/dashboard/`
- Base redirect also supported at `/test-analytics/`

### UI components
1. KPI cards (total/passed/failed/healing stats)
2. Failure category chart
3. Healing outcome chart
4. History assist impact chart
5. Top failed selectors
6. Recent failures table
7. Interactive test result timeline (human-readable)
8. Optional raw JSON toggle

### Admin access
- Model links inside `TestRun` and `TestCaseResult`
- Admin shortcut route: `/admin/test-analytics-dashboard/`
- Menu entry: `Analytics Dashboard` (proxy model)

---

## 5. Data Flow (End-to-End)
1. Playwright step fails selector.
2. Healer API receives DOM + selector context.
3. Healer returns validated selector or no-safe-match.
4. Test continues (healed/pass/fail).
5. `afterEach` sends final test analytics payload.
6. Django stores result in `TestCaseResult`.
7. Dashboard reads aggregates and per-test timeline.

---

## 6. Meaning of Important Fields
- `healing_attempted`: healer was called or not.
- `healing_outcome`: `SUCCESS`, `FAILED`, `NOT_ATTEMPTED`.
- `validation_status`: `VALID` or `NO_SAFE_MATCH`.
- `ui_change_level`: `UNCHANGED`, `MINOR_CHANGE`, `MAJOR_CHANGE`, `ELEMENT_REMOVED`, `UNKNOWN`.
- `history_assisted`: whether historical evidence influenced scoring.
- `history_hits`: count of relevant historical matches used in scoring.
- `step_events`: per-step execution timeline used in detailed analysis.

---

## 7. Demo Run Playbook
1. Ensure migrations are applied.
2. Run tests with unique `RUN_ID`.
3. Open dashboard and filter by run.
4. Show:
   - failed selector to healed selector path
   - validation status
   - history impact
   - timeline of step-level events

Example test command:
```bash
RUN_ID=RUN_DEMO_001 npx playwright test tests/product/add-to-cart.spec.ts
```

---

## 8. Operational Notes
- `test_analytics` uses the `playwright` DB via router.
- If new fields are added in models, run migrations on the correct DB.
- For stable LLM validation, keep deterministic model settings (`temperature=0`) and suitable timeout.

---

## 9. Current Status vs Roadmap
### Completed (MVP)
- Failure analytics capture
- Validation-gated healing
- Historical influence (`history_hits` / `history_assisted`)
- Dashboard visualization and timeline

### Pending for full historical RAG
- Dedicated versioned DOM snapshot store
- Embedding retrieval over historical snapshots
- Retrieval provenance in response (top-k evidence)
- Offline evaluation benchmark for retrieval quality

---

## 10. Phase 2: Auto Test Generation

### New endpoints
- `POST /test-generation/jobs/`
- `GET /test-generation/jobs/<job_id>/`
- `POST /test-generation/jobs/<job_id>/approve/`
- `POST /test-generation/jobs/<job_id>/materialize/`
- `POST /test-generation/jobs/<job_id>/reject/`
- `POST /test-generation/jobs/<job_id>/link-run/`

### Flow
1. Create generation job with feature description + seed URLs.
2. Django calls a Playwright crawl runner to capture route/DOM context.
3. Local LLM (Ollama) plans scenarios and drafts page/spec files.
4. Guardrails validate generated code before draft is marked ready.
5. User approves and materializes files under:
   - `tests/generated/`
   - `tests/pages/generated/`
6. After test execution, link `run_id` to generation job for analytics correlation.
