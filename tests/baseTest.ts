// tests/baseTest.ts

import { test as base, expect } from "@playwright/test";
import { sendToDjango } from "./utils/sendToDjango";
import {
    clearFailureContext,
    getFailureContext,
    parseFailureFromError
} from "./utils/failureContext";

export const test = base;
export { expect };

const generatedRunId = `RUN_${new Date()
    .toISOString()
    .replace(/[-:.TZ]/g, "")
    .slice(0, 14)}_${Math.random().toString(36).slice(2, 8)}`;

const generatedBuildId = `BUILD_${new Date()
    .toISOString()
    .replace(/[-:.TZ]/g, "")
    .slice(0, 14)}`;

const commitSha =
    process.env.GITHUB_SHA?.trim().slice(0, 8) ||
    process.env.CI_COMMIT_SHA?.trim().slice(0, 8) ||
    process.env.BUILD_COMMIT?.trim().slice(0, 8);

const RUN_ID = process.env.RUN_ID?.trim() || generatedRunId;
const BUILD_ID = process.env.BUILD_ID?.trim() ||
    (commitSha ? `BUILD_${commitSha}` : generatedBuildId);
const SAVE_ONLY_FAILED = (process.env.SAVE_ONLY_FAILED ?? "false").toLowerCase() === "true";

test.afterEach(async ({ page }, testInfo) => {

    const failed = testInfo.status !== testInfo.expectedStatus;
    if (SAVE_ONLY_FAILED && !failed) return;

    const html = page.isClosed() ? "" : await page.content();
    const screenshot = testInfo.attachments.find(a =>
        a.name.includes("screenshot")
    )?.path;

    const video = testInfo.attachments.find(a =>
        a.name.includes("video")
    )?.path;

    const trace = testInfo.attachments.find(a =>
        a.name.includes("trace")
    )?.path;

    const trackedFailure = getFailureContext(testInfo) || {};
    const parsedFailure = parseFailureFromError(testInfo.error?.message);
    const mergedFailure = {
        failedSelector: trackedFailure.failedSelector || parsedFailure.failedSelector || "",
        failureReason: trackedFailure.failureReason || parsedFailure.failureReason || "unknown",
        pageUrl: trackedFailure.pageUrl || (page.isClosed() ? "" : page.url()),
        healingAttempted: trackedFailure.healingAttempted ?? false,
        healingOutcome: trackedFailure.healingOutcome || "NOT_ATTEMPTED",
        healedSelector: trackedFailure.healedSelector || "",
        healingConfidence: trackedFailure.healingConfidence ?? null,
        validationStatus: trackedFailure.validationStatus || "",
        uiChangeLevel: trackedFailure.uiChangeLevel || "",
        historyAssisted: trackedFailure.historyAssisted ?? false,
        historyHits: trackedFailure.historyHits ?? 0,
        rootCause: trackedFailure.rootCause || parsedFailure.failureReason || "unknown",
        stepEvents: trackedFailure.stepEvents || [],
    };

    const payload = {
        run_id: RUN_ID,
        environment: "staging",
        build_id: BUILD_ID,
        run_execution_time: testInfo.duration,

        test_name: testInfo.title,
        status: failed ? "FAILED" : "PASSED",

        error_message: testInfo.error?.message,
        stack_trace: testInfo.error?.stack,

        page_url: mergedFailure.pageUrl,
        failed_selector: mergedFailure.failedSelector,
        failure_reason: mergedFailure.failureReason,
        healing_attempted: mergedFailure.healingAttempted,
        healing_outcome: mergedFailure.healingOutcome,
        healed_selector: mergedFailure.healedSelector,
        healing_confidence: mergedFailure.healingConfidence,
        validation_status: mergedFailure.validationStatus,
        ui_change_level: mergedFailure.uiChangeLevel,
        history_assisted: mergedFailure.historyAssisted,
        history_hits: mergedFailure.historyHits,
        root_cause: mergedFailure.rootCause,
        step_events: mergedFailure.stepEvents,

        html: html,

        screenshot_path: screenshot,
        video_path: video,
        trace_path: trace,
    };

    try {
        await sendToDjango(payload);
    } finally {
        clearFailureContext(testInfo);
    }
});
