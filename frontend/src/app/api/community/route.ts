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
        const pointerResponse = await fetch(ROOT + "/community-source.json", {
            next: { revalidate: 300 },
            signal: AbortSignal.timeout(20000),
        });
        let summaryUrl = ROOT + "/recent-activity.json";
        let stateUrl = ROOT + "/recent-activity-state.json.gz";
        let summaryHash: string | undefined;
        if (pointerResponse.status !== 404) {
            if (!pointerResponse.ok)
                throw new Error("Publication pointer unavailable.");
            const pointer = await pointerResponse.json();
            const base =
                "https://github.com/yash-rai-93/argo-data-platform/releases/download/";
            const valid = (url: unknown, filename: string) =>
                typeof url === "string" &&
                url.startsWith(base) &&
                new RegExp(
                    "^community-data-[0-9]+-[0-9]+/" +
                        filename.replaceAll(".", "\\."),
                ).test(url.slice(base.length)) &&
                url ===
                    base +
                        url.slice(base.length).split("/")[0] +
                        "/" +
                        filename;
            if (
                pointer.schema_version !== 1 ||
                !valid(pointer.summary_url, "recent-activity.json") ||
                !valid(pointer.state_url, "recent-activity-state.json.gz") ||
                !/^[a-f0-9]{64}$/.test(pointer.summary_sha256)
            )
                throw new Error("Invalid publication pointer.");
            summaryUrl = pointer.summary_url;
            stateUrl = pointer.state_url;
            summaryHash = pointer.summary_sha256;
        }
        const [summaryResponse, stateResponse] = await Promise.all([
            fetch(summaryUrl, {
                cache: "no-store",
                signal: AbortSignal.timeout(20000),
            }),
            fetch(stateUrl, {
                cache: "no-store",
                signal: AbortSignal.timeout(20000),
            }),
        ]);
        if (!summaryResponse.ok || !stateResponse.ok)
            throw new Error("Source checkpoint is unavailable.");
        const summaryBytes = Buffer.from(await summaryResponse.arrayBuffer());
        if (
            summaryHash &&
            createHash("sha256").update(summaryBytes).digest("hex") !==
                summaryHash
        )
            throw new Error("Published summary checksum mismatch.");
        const snapshot = JSON.parse(summaryBytes.toString("utf8")) as Snapshot;
        snapshot.summary_url = summaryUrl;
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
