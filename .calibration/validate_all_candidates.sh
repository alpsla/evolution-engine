#!/bin/bash
# validate_all_candidates.sh - Batch validation for all 8 candidate repositories
# Outputs results to repo_validation.md with timestamps

set -euo pipefail

CANDIDATES=(
  "fastapi/fastapi"
  "gin-gonic/gin"
  "strapi/strapi"
  "hashicorp/terraform"
  "kubernetes/kubernetes"
  "rails/rails"
  "spring-projects/spring-boot"
  "vercel/next.js"
)

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VALIDATION_SCRIPT="$SCRIPT_DIR/validate_repo.sh"
OUTPUT_FILE="$SCRIPT_DIR/validation_results_$(date +%Y%m%d_%H%M%S).txt"

# Check if validation script exists
if [ ! -f "$VALIDATION_SCRIPT" ]; then
  echo "ERROR: Validation script not found at $VALIDATION_SCRIPT"
  exit 1
fi

# Check if validation script is executable
if [ ! -x "$VALIDATION_SCRIPT" ]; then
  echo "Making validation script executable..."
  chmod +x "$VALIDATION_SCRIPT"
fi

echo "========================================"
echo "Batch Repository Validation"
echo "========================================"
echo "Date: $(date)"
echo "Candidates: ${#CANDIDATES[@]}"
echo "Output: $OUTPUT_FILE"
echo ""

# Create output file with header
cat > "$OUTPUT_FILE" <<EOF
# Batch Validation Results
Date: $(date)
Candidates: ${#CANDIDATES[@]}

---

EOF

VALIDATED=0
FAILED=0

for repo in "${CANDIDATES[@]}"; do
  IFS='/' read -r owner name <<< "$repo"
  
  echo "----------------------------------------"
  echo "[$((VALIDATED + FAILED + 1))/${#CANDIDATES[@]}] Validating $owner/$name..."
  echo "----------------------------------------"
  
  # Run validation and capture output
  if "$VALIDATION_SCRIPT" "$owner" "$name" >> "$OUTPUT_FILE" 2>&1; then
    echo "✅ $owner/$name validation complete"
    ((VALIDATED++))
  else
    echo "❌ $owner/$name validation failed"
    ((FAILED++))
    echo "" >> "$OUTPUT_FILE"
    echo "ERROR: Validation failed for $owner/$name" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
  fi
  
  # Add separator to output
  echo "" >> "$OUTPUT_FILE"
  echo "========================================" >> "$OUTPUT_FILE"
  echo "" >> "$OUTPUT_FILE"
  
  # Brief pause to avoid rate limiting
  if [ "$((VALIDATED + FAILED))" -lt "${#CANDIDATES[@]}" ]; then
    echo "Pausing 3 seconds to avoid rate limits..."
    sleep 3
  fi
done

# Summary
echo ""
echo "========================================"
echo "Validation Complete"
echo "========================================"
echo "Total candidates: ${#CANDIDATES[@]}"
echo "Successfully validated: $VALIDATED"
echo "Failed: $FAILED"
echo ""
echo "Results saved to: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "1. Review $OUTPUT_FILE"
echo "2. Update repo_validation.md with findings"
echo "3. Rank repos by family coverage"
echo "4. Select top 5 for calibration"
echo ""

# Generate summary table
cat >> "$OUTPUT_FILE" <<EOF

---

## Validation Summary

Total Candidates: ${#CANDIDATES[@]}
Successfully Validated: $VALIDATED
Failed: $FAILED

### Next Steps

1. Review detailed validation results above
2. Update .calibration/repo_validation.md with:
   - Family coverage counts
   - Lockfile paths
   - Git History Walker configs
3. Rank repositories by family coverage (target: 4+/8 families)
4. Select top 5 for multi-family calibration runs
5. Proceed to adapter implementation (Git History Walker, GitHub API)

EOF

echo "Batch validation complete. See $OUTPUT_FILE for details."
