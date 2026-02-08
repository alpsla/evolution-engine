#!/bin/bash
# search_repos.sh - Shell-based repository search (avoids Python subprocess TLS issues)

set -euo pipefail

MIN_STARS=${1:-1000}
MAX_PER_LANG=${2:-20}
OUTPUT_FILE=${3:-"repos_found.json"}

echo "🔍 Searching GitHub repositories..."
echo "Min stars: $MIN_STARS"
echo "Max per language: $MAX_PER_LANG"
echo ""

TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Search each language
LANGUAGES=("Python" "Go" "TypeScript" "JavaScript" "Java" "Ruby" "Rust" "C++")
ALL_REPOS="$TEMP_DIR/all_repos.json"
echo "[]" > "$ALL_REPOS"

for lang in "${LANGUAGES[@]}"; do
    echo "Searching $lang repositories..."
    
    RESULTS=$(gh search repos \
        --language "$lang" \
        --stars ">=$MIN_STARS" \
        --archived=false \
        --limit $MAX_PER_LANG \
        --sort stars \
        --json name,owner,stargazersCount,forksCount,language,updatedAt)
    
    if [ $? -ne 0 ]; then
        echo "  Warning: Search failed for $lang"
        echo "  Error: $RESULTS"
        continue
    fi
    
    # Merge results
    echo "$RESULTS" | jq '. // []' > "$TEMP_DIR/${lang}_repos.json"
    jq -s 'add' "$ALL_REPOS" "$TEMP_DIR/${lang}_repos.json" > "$TEMP_DIR/merged.json"
    mv "$TEMP_DIR/merged.json" "$ALL_REPOS"
    
    COUNT=$(echo "$RESULTS" | jq 'length')
    echo "  Found: $COUNT repos"
    sleep 2
done

# Save results
cp "$ALL_REPOS" "$OUTPUT_FILE"
TOTAL=$(jq 'length' "$OUTPUT_FILE")

echo ""
echo "✅ Total repositories found: $TOTAL"
echo "📄 Saved to: $OUTPUT_FILE"
echo ""
echo "Next: Run validation on these repositories"
