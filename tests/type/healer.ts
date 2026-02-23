export interface HealerCandidate {
    selector: string;
    score: number;
    base_score: number;
    attribute_score: number;
    tag: string;
    text: string;
    xpath: string;
}

export interface HealerDebug {
    total_candidates: number;
    engine: string;
    processing_time_ms: number;
    vision_analyzed: boolean;
    validation_status?: "VALID" | "NO_SAFE_MATCH" | string;
    validation_reason?: string;
    history_assisted?: boolean;
    history_hits?: number;
    dom_fingerprint?: string;
    ui_change_level?: "UNKNOWN" | "UNCHANGED" | "MINOR_CHANGE" | "MAJOR_CHANGE" | "ELEMENT_REMOVED" | string;
}

export interface HealResponse {
    message: string;
    chosen: string | null;
    validation_status?: "VALID" | "NO_SAFE_MATCH" | string;
    validation_reason?: string;
    llm_used?: boolean;
    history_assisted?: boolean;
    history_hits?: number;
    dom_fingerprint?: string;
    ui_change_level?: "UNKNOWN" | "UNCHANGED" | "MINOR_CHANGE" | "MAJOR_CHANGE" | "ELEMENT_REMOVED" | string;
    candidates: HealerCandidate[];
    debug: HealerDebug;
    id: number;
    batch_id: number;
}
