import axios from "axios";
import { getAccessToken, clearCachedToken } from "./auth";

export const apiClient = axios.create({
    baseURL: "http://127.0.0.1:8000/api",
    timeout: 20000,
    headers: {
        "Content-Type": "application/json",
    },
});

/**
 * Authenticated POST — ensures a valid token is set before sending.
 * Automatically logs in if no token is cached, and retries once on 401.
 */
export async function authenticatedPost<T>(
    url: string,
    data: unknown
): Promise<{ data: T }> {
    const token = await getAccessToken();

    try {
        const response = await apiClient.post<T>(url, data, {
            headers: { Authorization: `Bearer ${token}` },
        });
        return response;
    } catch (err: any) {
        // If the token was rejected, clear the cache and retry once with a fresh token
        if (err?.response?.status === 401) {
            console.warn("⚠️  Received 401 — token may have expired. Re-authenticating...");
            clearCachedToken();

            const freshToken = await getAccessToken();
            const retryResponse = await apiClient.post<T>(url, data, {
                headers: { Authorization: `Bearer ${freshToken}` },
            });
            return retryResponse;
        }
        if (err?.response) {
            const statusCode = err.response.status;
            const body = typeof err.response.data === "string"
                ? err.response.data
                : JSON.stringify(err.response.data);
            throw new Error(`Healer API error ${statusCode}: ${body}`);
        }
        throw err;
    }
}
