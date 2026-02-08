#!/bin/bash
# quick_test_validation.sh - Quick test of validation toolkit on fastapi/fastapi
# Use this to verify the validation system works before running full batch

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VALIDATION_SCRIPT="$SCRIPT_DIR/validate_repo.sh"

# Test repo: fastapi (known good, Python ecosystem, should have 4+ families)
TEST_OWNER="fastapi"
TEST_REPO="fastapi"

echo "========================================"
echo "Quick Test Validation"
echo "========================================"
echo "Testing validation toolkit on $TEST_OWNER/$TEST_REPO"
echo ""

# Check prerequisites
if ! command -v gh &> /dev/null; then
  echo "❌ ERROR: GitHub CLI (gh) not installed"
  echo "Install with: brew install gh"
  exit 1
fi

if ! gh auth status &> /dev/null; then
  echo "❌ ERROR: Not authenticated with GitHub CLI"
  echo "Run: gh auth login"
  exit 1
fi

if [ ! -f "$VALIDATION_SCRIPT" ]; then
  echo "❌ ERROR: Validation script not found at $VALIDATION_SCRIPT"
  exit 1
fi

if [ ! -x "$VALIDATION_SCRIPT" ]; then
  echo "Making validation script executable..."
  chmod +x "$VALIDATION_SCRIPT"
fi

echo "✅ Prerequisites check passed"
echo ""
echo "Running validation on $TEST_OWNER/$TEST_REPO..."
echo ""

# Run validation
"$VALIDATION_SCRIPT" "$TEST_OWNER" "$TEST_REPO"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo "========================================"
  echo "✅ Test validation successful!"
  echo "========================================"
  echo ""
  echo "The validation toolkit is working correctly."
  echo ""
  echo "Next steps:"
  echo "1. Review the output above to verify data quality"
  echo "2. Check that lockfile paths were found (requirements.txt expected)"
  echo "3. Run batch validation: ./validate_all_candidates.sh"
  echo "4. Or validate individual repos: ./validate_repo.sh OWNER REPO"
  echo ""
else
  echo "========================================"
  echo "❌ Test validation failed"
  echo "========================================"
  echo ""
  echo "Troubleshooting:"
  echo "- Check GitHub CLI authentication: gh auth status"
  echo "- Verify network connection"
  echo "- Check API rate limits: gh api rate_limit"
  echo ""
  exit 1
fi
