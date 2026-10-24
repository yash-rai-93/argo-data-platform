set -euo pipefail
# Refuse publication from a stale dispatch or after another pointer was promoted.
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
latest_main=$(git ls-remote origin refs/heads/main | cut -f1)
test "$latest_main" = "$GITHUB_SHA" || {
  echo "Main advanced; start a fresh run. No pointer branch published."; exit 1;
}
tag="community-data-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
branch="data/community-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
export COMMUNITY_TAG="$tag"
gh release create "$tag" --target "$GITHUB_SHA" --prerelease --title "Community data $tag" --notes "Verified public GitHub activity snapshot. Private GCS originals are unchanged. Publication audit attached." data/generated/community/recent-activity.json data/generated/community/recent-activity-state.json.gz data/generated/community/publication-audit.json
uv run python - <<'PY'
import json
import os
from pathlib import Path
audit = json.loads(Path("data/generated/community/publication-audit.json").read_text())
base = "https://github.com/yash-rai-93/argo-data-platform/releases/download/" + os.environ["COMMUNITY_TAG"]
pointer = {
    "schema_version": 1,
    "summary_url": base + "/recent-activity.json",
    "state_url": base + "/recent-activity-state.json.gz",
    "summary_sha256": audit["summary_sha256"],
}
Path("data/community-source.json").write_text(json.dumps(pointer, indent=2) + "\n")
PY
git switch -c "$branch"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data/community-source.json
git commit -m "data: publish verified community snapshot"
git push origin "$branch"
{
  echo '### Verified community snapshot ready'
  echo 'Open this comparison, create a PR, and merge after CI to switch the live report:'
  echo "https://github.com/$GITHUB_REPOSITORY/compare/main...$branch?expand=1"
  cat data/generated/community/publication-audit.json
} >> "$GITHUB_STEP_SUMMARY"
