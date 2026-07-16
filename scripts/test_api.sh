#!/usr/bin/env bash
# Quick smoke test for the Face Attendance API using curl.
#
# Usage:
#   REGISTER_API_KEY=... ./scripts/test_api.sh register NV015 /path/to/employee.jpg
#   ./scripts/test_api.sh verify /path/to/probe.jpg [latitude] [longitude]
#
# employee_id (e.g. "NV015") must match the employee's `barcode` field in Odoo.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ACTION="${1:-}"

case "$ACTION" in
  health)
    curl -s "${BASE_URL}/health" | python -m json.tool
    ;;

  register)
    EMPLOYEE_ID="${2:?employee_id (Odoo hr.employee.barcode) is required}"
    IMAGE_PATH="${3:?path to image is required}"
    curl -s -X POST "${BASE_URL}/register" \
      -H "X-API-Key: ${REGISTER_API_KEY:-}" \
      -F "employee_id=${EMPLOYEE_ID}" \
      -F "file=@${IMAGE_PATH}" \
      | python -m json.tool
    ;;

  verify)
    IMAGE_PATH="${2:?path to image is required}"
    LAT="${3:-}"
    LON="${4:-}"
    ARGS=(-F "file=@${IMAGE_PATH}")
    if [[ -n "$LAT" && -n "$LON" ]]; then
      ARGS+=(-F "latitude=${LAT}" -F "longitude=${LON}")
    fi
    curl -s -X POST "${BASE_URL}/verify" "${ARGS[@]}" | python -m json.tool
    ;;

  *)
    echo "Usage:"
    echo "  $0 health"
    echo "  REGISTER_API_KEY=... $0 register <employee_id (barcode)> <image_path>"
    echo "  $0 verify <image_path> [latitude] [longitude]"
    exit 1
    ;;
esac
