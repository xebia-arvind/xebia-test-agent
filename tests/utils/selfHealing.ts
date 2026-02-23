import { Page, Locator, TestInfo } from "@playwright/test";
import { authenticatedPost } from "./apiClient";
import { HealResponse } from "../type/healer";
import { addStepEvent, setFailureContext } from "./failureContext";
import chalk from "chalk";

type HealingOptions = {
    use_of_selector: string;
    selector_type: string;
    intent_key?: string;
};

export async function selfHealingClick(
    page: Page,
    locator: Locator,
    failedSelector: string,
    testInfo: TestInfo,
    options: HealingOptions
) {
    setFailureContext(testInfo, {
        failedSelector,
        failureReason: options.use_of_selector,
        selectorType: options.selector_type,
        pageUrl: page.url(),
        healingAttempted: false,
        healingOutcome: "NOT_ATTEMPTED",
        healingConfidence: null,
    });

    try {
        // Try original Playwright locator
        await locator.click({ timeout: 3000 });

        addStepEvent(testInfo, {
            step_name: options.use_of_selector,
            step_type: "action",
            status: "PASSED",
            failed_selector: failedSelector,
            message: "Original locator worked",
        });

        console.log(chalk.bold.hex("#39FF14")("✔ Original locator worked"));

    } catch (error) {
        setFailureContext(testInfo, {
            failedSelector,
            failureReason: options.use_of_selector,
            selectorType: options.selector_type,
            pageUrl: page.url(),
            healingAttempted: true,
            healingOutcome: "FAILED",
            rootCause: "Original locator failed, attempting healer fallback",
        });

        console.log(
            chalk.bold.hex("#FF3131")("Locator failed. Sending to healer...")
        )
        const html = await page.content();

        const screenshotBuffer = await page.screenshot();
        const screenshot = screenshotBuffer.toString("base64");

        // authenticatedPost auto-logs in if no token is cached, and retries on 401
        const response = await authenticatedPost<HealResponse>(
            "/heal/",
            {
                test_name: testInfo.title,
                failed_selector: failedSelector,
                html,
                screenshot,
                page_url: page.url(),
                use_of_selector: options.use_of_selector,
                selector_type: options.selector_type,
                intent_key: options.intent_key,
            }
        );

        const healedSelector = response.data.chosen;
        const healedConfidence = response.data.candidates?.[0]?.score ?? null;
        const validationStatus = response.data.validation_status || response.data.debug?.validation_status;
        const validationReason = response.data.validation_reason || response.data.debug?.validation_reason;
        const historyAssisted = response.data.history_assisted ?? response.data.debug?.history_assisted ?? false;
        const historyHits = response.data.history_hits ?? response.data.debug?.history_hits ?? 0;
        const uiChangeLevel = response.data.ui_change_level || response.data.debug?.ui_change_level || "UNKNOWN";

        if (validationStatus === "NO_SAFE_MATCH") {
            addStepEvent(testInfo, {
                step_name: options.use_of_selector,
                step_type: "action",
                status: "FAILED",
                failed_selector: failedSelector,
                message: `Validation rejected healing: ${validationReason || "No safe match"}`,
            });

            setFailureContext(testInfo, {
                failedSelector,
                failureReason: options.use_of_selector,
                selectorType: options.selector_type,
                pageUrl: page.url(),
                healingAttempted: true,
                healingOutcome: "FAILED",
                healingConfidence: healedConfidence,
                validationStatus,
                uiChangeLevel,
                historyAssisted,
                historyHits,
                rootCause: `Validation rejected healing: ${validationReason || "No safe match"}`,
            });

            throw new Error(`Healing blocked by validation gate: ${validationReason || "No safe match"}`);
        }

        if (!healedSelector) {
            addStepEvent(testInfo, {
                step_name: options.use_of_selector,
                step_type: "action",
                status: "FAILED",
                failed_selector: failedSelector,
                healing_confidence: healedConfidence,
                message: "Healer returned no selector",
            });

            setFailureContext(testInfo, {
                failedSelector,
                failureReason: options.use_of_selector,
                selectorType: options.selector_type,
                pageUrl: page.url(),
                healingAttempted: true,
                healingOutcome: "FAILED",
                healingConfidence: healedConfidence,
                validationStatus,
                uiChangeLevel,
                historyAssisted,
                historyHits,
                rootCause: "Healer returned no selector",
            });
            throw new Error("Healing failed: no selector returned");
        }

        console.log(
            chalk.hex("#bc13fe")("Using healed selector:"),
            chalk.bold.hex("#bc13fe")(healedSelector)
        );

        // Retry using healed selector
        await page.locator(healedSelector).click();

        addStepEvent(testInfo, {
            step_name: options.use_of_selector,
            step_type: "action",
            status: "HEALED",
            failed_selector: failedSelector,
            healed_selector: healedSelector,
            healing_confidence: healedConfidence,
            message: "Healed selector click succeeded",
        });

        setFailureContext(testInfo, {
            failedSelector,
            failureReason: options.use_of_selector,
            selectorType: options.selector_type,
            pageUrl: page.url(),
            healingAttempted: true,
            healingOutcome: "SUCCESS",
            healedSelector,
            healingConfidence: healedConfidence,
            validationStatus,
            uiChangeLevel,
            historyAssisted,
            historyHits,
            rootCause: "Original locator failed but healed selector click succeeded",
        });

        console.log(chalk.bold.hex("#bc13fe")("Click succeeded with healed selector"));
    }
}
