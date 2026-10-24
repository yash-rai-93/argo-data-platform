import { createHash } from "node:crypto";
import { gunzipSync } from "node:zlib";
import {
    buildCommunityReport,
    FilterError,
    resolveFilters,
    validateCheckpoint,
    type Checkpoint,
    type Snapshot,
} from "@/lib/community";

export const runtime = "nodejs";
const ROOT =
    "https://raw.githubusercontent.com/yash-rai-93/argo-data-platform/main/data";
type Source = { state: Checkpoint; snapshot: Snapshot };
let source: { value: Promise<Source>; until: number } | undefined;

async function loadSource(): Promise<Source> {
    if (source && source.until > Date.now()) return source.value;
    const value = (async () => {
        const [summaryResponse, stateResponse] = await Promise.all([
            fetch(ROOT + "/recent-activity.json", {
                next: { revalidate: 300 },
                signal: AbortSignal.timeout(20000),
            }),
            fetch(ROOT + "/recent-activity-state.json.gz", {
                next: { revalidate: 300 },
                signal: AbortSignal.timeout(20000),
            }),
        ]);
        if (!summaryResponse.ok || !stateResponse.ok)
            throw new Error("Source checkpoint is unavailable.");
        const snapshot = (await summaryResponse.json()) as Snapshot;
        const packed = Buffer.from(await stateResponse.arrayBuffer());
        if (
            packed.byteLength > 64 * 1024 * 1024 ||
            createHash("sha256").update(packed).digest("hex") !==
                snapshot.state_sha256
        )
            throw new Error(
                "Checkpoint integrity verification failed. Retry after publication completes.",
            );
        const state = JSON.parse(
            gunzipSync(packed, { maxOutputLength: 64 * 1024 * 1024 }).toString(
                "utf8",
            ),
        ) as Checkpoint;
        validateCheckpoint(state, snapshot);
        return { state, snapshot };
    })();
    source = { value, until: Date.now() + 300000 };
    value.catch(() => {
        if (source?.value === value) source = undefined;
    });
    return value;
}
export async function GET(request: Request) {
    try {
        const { state, snapshot } = await loadSource();
        const filters = resolveFilters(
            new URL(request.url).searchParams,
            state,
        );
        return Response.json(buildCommunityReport(state, snapshot, filters));
    } catch (error) {
        if (error instanceof FilterError)
            return Response.json({ error: error.message }, { status: 400 });
        console.error("Community report unavailable:", error);
        return Response.json(
            {
                error: "The approved community checkpoint could not be verified. Please retry shortly.",
            },
            { status: 503 },
        );
    }
}
