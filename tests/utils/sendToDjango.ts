export async function sendToDjango(payload: any) {
    try {

        const response = await fetch("http://127.0.0.1:8000/test-analytics/test-result/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        const rawBody = await response.text();
        let parsedBody: unknown = rawBody;

        try {
            parsedBody = rawBody ? JSON.parse(rawBody) : {};
        } catch {
            // Keep raw text when response is not JSON
        }
        console.log("✔ Data sent to Django", {
            status: response.status,
            response: parsedBody,
        });
        if (!response.ok) {
            throw new Error(
                `Django API request failed: ${response.status} ${response.statusText} | body=${JSON.stringify(parsedBody)}`
            );
        }

        console.log("✔ Data sent to Django", {
            status: response.status,
            response: parsedBody,
        });
    } catch (error) {
        console.error("❌ Failed to send data:", error);
        throw error;
    }
}
