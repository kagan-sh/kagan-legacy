#!/usr/bin/env bash
# scenarios.sh — Docker-based end-to-end validation of the DoctorModal / install-UX
# feature (Growth Bet 1, commit 32dcf1e on main).
#
# Validates the shipped feature works on cold Linux installs without touching
# macOS or Windows. Does NOT commit or push anything.
#
# Requirements: docker, jq, sqlite3
# Usage: cd tests/e2e/docker && ./scenarios.sh [--no-build]
#
# Exit codes: 0 = all scenarios passed, 1 = one or more scenarios failed.

set -uo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DOCKER_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_BASE="kagan-e2e-base"
IMAGE_DEFAULT="kagan-e2e-default-installed"
BUILD_CONTEXT="${REPO_ROOT}"
NO_BUILD=false

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass()   { echo -e "${GREEN}[PASS]${NC} $*"; }
fail()   { echo -e "${RED}[FAIL]${NC} $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $*"; }
info()   { echo -e "${CYAN}[INFO]${NC} $*"; }
header() { echo -e "\n${BOLD}${CYAN}=== $* ===${NC}\n"; }

for arg in "$@"; do
  case "$arg" in
    --no-build) NO_BUILD=true ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

for cmd in docker jq sqlite3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' is required but not found."
    exit 1
  fi
done

if [[ "$NO_BUILD" == false ]]; then
  header "Building Docker images"

  info "Building ${IMAGE_BASE} ..."
  docker build -f "${DOCKER_DIR}/Dockerfile.base" -t "${IMAGE_BASE}" "${BUILD_CONTEXT}" 2>&1 | tail -5
  info "Built ${IMAGE_BASE}"

  info "Building ${IMAGE_DEFAULT} ..."
  docker build -f "${DOCKER_DIR}/Dockerfile.default-installed" -t "${IMAGE_DEFAULT}" "${BUILD_CONTEXT}" 2>&1 | tail -5
  info "Built ${IMAGE_DEFAULT}"
fi

# kagan doctor --json exits 1 when there are failures — capture output without aborting
run_doctor_json() {
  local image="$1"
  docker run --rm -e KAGAN_DB_PATH=/tmp/kagan-e2e.db "${image}" \
    kagan doctor --json 2>/dev/null || true
}

SCENARIO_RESULTS=()
SCENARIO_NAMES=()
OVERALL_EXIT=0

record_result() {
  local name="$1" result="$2"
  SCENARIO_NAMES+=("$name")
  SCENARIO_RESULTS+=("$result")
  [[ "$result" == "PASS" ]] || OVERALL_EXIT=1
}

# ─────────────────────────────────────────────────────────────────────────────
# Scenario A — Zero-ready: no backends installed
# ─────────────────────────────────────────────────────────────────────────────
header "Scenario A — Zero-ready (no backends installed)"
RESULT_A="FAIL"

DOCTOR_JSON_A=$(run_doctor_json "${IMAGE_BASE}")

if [[ -z "${DOCTOR_JSON_A}" ]]; then
  fail "A: kagan doctor --json produced no output"
  record_result "Scenario A" "FAIL"
else
  info "JSON length (chars): ${#DOCTOR_JSON_A}"

  # The default backend detail row name is "backend: claude-code (default)"
  DEFAULT_STATUS=$(echo "${DOCTOR_JSON_A}" | jq -r '.[] | select(.name == "backend: claude-code (default)") | .status' 2>/dev/null | head -1)

  # Summary row
  SUMMARY_STATUS=$(echo "${DOCTOR_JSON_A}" | jq -r '.[] | select(.name == "agent backends") | .status' 2>/dev/null | head -1)

  # Warn count across backend category
  WARN_COUNT=$(echo "${DOCTOR_JSON_A}" | jq '[.[] | select(.category == "backend" and .status == "warn")] | length' 2>/dev/null)

  # Empty fix_hint for any failing/warning backend entry
  EMPTY_FIX=$(echo "${DOCTOR_JSON_A}" | jq '[.[] | select(.category == "backend" and .status != "pass" and (.fix_hint == "" or .fix_hint == null))] | length' 2>/dev/null)

  TOTAL=$(echo "${DOCTOR_JSON_A}" | jq 'length' 2>/dev/null)

  info "claude-code (default) detail row status: '${DEFAULT_STATUS}'"
  info "Summary 'agent backends' row status: '${SUMMARY_STATUS}'"
  info "Backend entries with status=warn: ${WARN_COUNT}"
  info "Backend entries with empty fix_hint: ${EMPTY_FIX}"
  info "Total checks in JSON: ${TOTAL}"

  echo ""
  info "Backend entries (name + status):"
  echo "${DOCTOR_JSON_A}" | jq -r '.[] | select(.category == "backend") | "\(.status | ascii_upcase)  \(.name)"' 2>/dev/null

  echo ""
  info "Sample fix_hints (failing/warning backends, first 3):"
  echo "${DOCTOR_JSON_A}" | jq -r '.[] | select(.category == "backend" and .status != "pass") | .fix_hint' 2>/dev/null | head -3

  A_PASS=true

  # A1: default detail row should show fail when zero backends installed
  if [[ "${DEFAULT_STATUS}" == "fail" ]]; then
    pass "A1: claude-code detail row status=fail (correct)"
  else
    fail "A1: Expected claude-code status=fail (zero-ready Rule 1), got '${DEFAULT_STATUS}'"
    fail "    BUG: _collect_doctor_checks passes the executable ('claude') not the backend"
    fail "    name ('claude-code') to client.preflight(). check_agent_backends() treats"
    fail "    'claude' as the default slot, creating a ghost entry. 'claude-code' is then"
    fail "    treated as a non-default backend and gets WARN instead of FAIL."
    A_PASS=false
  fi

  # A2: summary row should show fail (triggers DoctorModal)
  if [[ "${SUMMARY_STATUS}" == "fail" ]]; then
    pass "A2: Summary 'agent backends' row status=fail (DoctorModal will block)"
  else
    fail "A2: Expected summary status=fail, got '${SUMMARY_STATUS}'"
    fail "    CONSEQUENCE: DoctorModal MAY NOT block on fresh install (depends on ghost entry)."
    fail "    TUI uses any(c.status=='fail') so ghost 'backend: claude' entry still triggers modal."
    fail "    But the summary row label reads 'warn' which is confusing and incorrect."
    A_PASS=false
  fi

  # A3: at least 13 non-default backends show warn
  if [[ "${WARN_COUNT}" -ge 13 ]]; then
    pass "A3: >=13 non-default backend entries have status=warn (got ${WARN_COUNT})"
  else
    fail "A3: Expected >=13 warn entries, got ${WARN_COUNT}"
    A_PASS=false
  fi

  # A4: no backend entry lacks fix_hint (install guidance present for all)
  if [[ "${EMPTY_FIX}" -eq 0 ]]; then
    pass "A4: All failing/warning backend entries have a non-empty fix_hint"
    warn "A4: NOTE: Non-default backend fix_hints only say \"Install 'X' to enable the 'Y' backend\""
    warn "    They do NOT include the actual install command (e.g. npm install -g @openai/codex)."
    warn "    The actual commands are only in the default backend's fix_hint."
  else
    fail "A4: ${EMPTY_FIX} backend entries have empty fix_hint"
    A_PASS=false
  fi

  if [[ "${TOTAL}" -ge 16 ]]; then
    pass "A5: JSON output has ${TOTAL} checks (expected >=16)"
  else
    warn "A5: Only ${TOTAL} checks — may indicate missing checks"
  fi

  [[ "${A_PASS}" == true ]] && RESULT_A="PASS"
fi

record_result "Scenario A" "${RESULT_A}"
[[ "${RESULT_A}" == "PASS" ]] && pass "Scenario A: PASS" || fail "Scenario A: FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Scenario B — Default backend installed, 13 others absent (Rule 3)
# ─────────────────────────────────────────────────────────────────────────────
header "Scenario B — Default backend installed, others absent (Rule 3)"
RESULT_B="FAIL"

DOCTOR_JSON_B=$(run_doctor_json "${IMAGE_DEFAULT}")

if [[ -z "${DOCTOR_JSON_B}" ]]; then
  fail "B: kagan doctor --json produced no output"
  record_result "Scenario B" "FAIL"
else
  info "JSON length (chars): ${#DOCTOR_JSON_B}"

  DEFAULT_STATUS_B=$(echo "${DOCTOR_JSON_B}" | jq -r '.[] | select(.name == "backend: claude-code (default)") | .status' 2>/dev/null | head -1)
  SUMMARY_STATUS_B=$(echo "${DOCTOR_JSON_B}" | jq -r '.[] | select(.name == "agent backends") | .status' 2>/dev/null | head -1)
  FAIL_COUNT_B=$(echo "${DOCTOR_JSON_B}" | jq '[.[] | select(.category == "backend" and .status == "fail")] | length' 2>/dev/null)
  WARN_COUNT_B=$(echo "${DOCTOR_JSON_B}" | jq '[.[] | select(.category == "backend" and .status == "warn")] | length' 2>/dev/null)

  info "claude-code (default) detail row status: '${DEFAULT_STATUS_B}'"
  info "Summary 'agent backends' row status: '${SUMMARY_STATUS_B}'"
  info "Backend entries with status=fail: ${FAIL_COUNT_B}"
  info "Backend entries with status=warn: ${WARN_COUNT_B}"

  echo ""
  info "Backend entries (name + status):"
  echo "${DOCTOR_JSON_B}" | jq -r '.[] | select(.category == "backend") | "\(.status | ascii_upcase)  \(.name)"' 2>/dev/null

  B_PASS=true

  if [[ "${DEFAULT_STATUS_B}" == "pass" ]]; then
    pass "B1: claude-code detail row status=pass (Rule 3 correct)"
  else
    fail "B1: Expected claude-code status=pass (Rule 3), got '${DEFAULT_STATUS_B}'"
    B_PASS=false
  fi

  if [[ "${SUMMARY_STATUS_B}" == "pass" ]]; then
    pass "B2: Summary 'agent backends' row status=pass — no DoctorModal (Rule 3 correct)"
  else
    fail "B2: Expected summary status=pass (Rule 3 no-block), got '${SUMMARY_STATUS_B}'"
    B_PASS=false
  fi

  # Rule 3 says no FAIL entries — but the ghost "backend: claude" creates a spurious fail
  if [[ "${FAIL_COUNT_B}" -eq 0 ]]; then
    pass "B3: No backend entries have status=fail (Rule 3 clean)"
  else
    fail "B3: ${FAIL_COUNT_B} backend entries have status=fail — Rule 3 violation"
    fail "    BUG: Ghost 'backend: claude' entry (alias as default slot) shows FAIL"
    fail "    even though the actual claude-code backend is installed and passing."
    fail "    The TUI doctor_has_failures() returns True due to this ghost entry,"
    fail "    which would trigger DoctorModal even when the default IS installed."
    B_PASS=false
  fi

  if [[ "${WARN_COUNT_B}" -ge 13 ]]; then
    pass "B4: >=13 non-default backend entries have status=warn (got ${WARN_COUNT_B})"
  else
    fail "B4: Expected >=13 warn entries, got ${WARN_COUNT_B}"
    B_PASS=false
  fi

  [[ "${B_PASS}" == true ]] && RESULT_B="PASS"
fi

record_result "Scenario B" "${RESULT_B}"
[[ "${RESULT_B}" == "PASS" ]] && pass "Scenario B: PASS" || fail "Scenario B: FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Scenario C — Real install of codex (npm), recheck, telemetry verification
# ─────────────────────────────────────────────────────────────────────────────
header "Scenario C — Real install + recheck (codex via npm)"
RESULT_C="FAIL"

INTERNET_AVAILABLE=false
if docker run --rm kagan-e2e-base bash -c 'curl -fsSL --max-time 5 https://registry.npmjs.org/ >/dev/null 2>&1'; then
  INTERNET_AVAILABLE=true
  info "Internet access confirmed (npm registry reachable)"
else
  warn "npm registry not reachable — skipping Scenario C"
fi

if [[ "${INTERNET_AVAILABLE}" == true ]]; then
  # Run the full scenario in one container invocation via inline script.
  # NOTE: kagan doctor exits 1 when there are failures — we suppress that with || true.
  SCENARIO_C_OUTPUT=$(docker run --rm \
    -e KAGAN_DB_PATH=/tmp/kagan-e2e.db \
    kagan-e2e-base \
    bash -c '
export KAGAN_DB_PATH=/tmp/kagan-e2e.db
printf "FIRST_RUN_START\n"
kagan doctor --json 2>/dev/null || true
printf "\nFIRST_RUN_END\n"
printf "INSTALL_START\n"
apt-get update -qq 2>&1 | tail -1
apt-get install -y -qq --no-install-recommends nodejs npm 2>&1 | tail -2
npm install -g @openai/codex 2>&1 | tail -3
printf "INSTALL_END\n"
printf "WHICH_START\n"
which codex 2>/dev/null || printf "NOT_FOUND\n"
printf "WHICH_END\n"
printf "SECOND_RUN_START\n"
kagan doctor --json 2>/dev/null || true
printf "\nSECOND_RUN_END\n"
printf "TELEMETRY_START\n"
sqlite3 /root/.local/share/kagan/kagan.db "SELECT event_type FROM telemetry_events;" 2>/dev/null || printf "NO_DB\n"
printf "TELEMETRY_END\n"
' 2>&1) || true

  # Parse each section using awk
  FIRST_JSON=$(echo "${SCENARIO_C_OUTPUT}" | awk '/^FIRST_RUN_START/{found=1;next} /^FIRST_RUN_END/{found=0} found{print}')
  INSTALL_OUT=$(echo "${SCENARIO_C_OUTPUT}" | awk '/^INSTALL_START/{found=1;next} /^INSTALL_END/{found=0} found{print}')
  WHICH_OUT=$(echo "${SCENARIO_C_OUTPUT}" | awk '/^WHICH_START/{found=1;next} /^WHICH_END/{found=0} found{print}')
  SECOND_JSON=$(echo "${SCENARIO_C_OUTPUT}" | awk '/^SECOND_RUN_START/{found=1;next} /^SECOND_RUN_END/{found=0} found{print}')
  TELEMETRY_OUT=$(echo "${SCENARIO_C_OUTPUT}" | awk '/^TELEMETRY_START/{found=1;next} /^TELEMETRY_END/{found=0} found{print}')

  info "Install output: ${INSTALL_OUT}"
  info "Which codex output: ${WHICH_OUT}"

  CODEX_STATUS_FIRST=$(echo "${FIRST_JSON}" | jq -r '.[] | select(.name == "backend: codex") | .status' 2>/dev/null | head -1)
  CODEX_STATUS_SECOND=$(echo "${SECOND_JSON}" | jq -r '.[] | select(.name == "backend: codex") | .status' 2>/dev/null | head -1)
  CODEX_ON_PATH=false
  echo "${WHICH_OUT}" | grep -qv "NOT_FOUND" && CODEX_ON_PATH=true || true
  DOCTOR_WARNED_COUNT=$(echo "${TELEMETRY_OUT}" | grep -c "DOCTOR_WARNED" 2>/dev/null || true)
  AUTO_PROMOTED_COUNT=$(echo "${TELEMETRY_OUT}" | grep -c "BACKEND_AUTO_PROMOTED" 2>/dev/null || true)
  DOCTOR_WARNED_COUNT="${DOCTOR_WARNED_COUNT:-0}"
  AUTO_PROMOTED_COUNT="${AUTO_PROMOTED_COUNT:-0}"

  info "Codex status before install: '${CODEX_STATUS_FIRST}'"
  info "Codex status after install:  '${CODEX_STATUS_SECOND}'"
  info "Codex binary on PATH: ${CODEX_ON_PATH}"
  info "DOCTOR_WARNED telemetry rows: ${DOCTOR_WARNED_COUNT}"
  info "BACKEND_AUTO_PROMOTED telemetry rows: ${AUTO_PROMOTED_COUNT}"

  C_PASS=true

  if [[ "${CODEX_STATUS_FIRST}" == "warn" ]]; then
    pass "C1: codex initially shows status=warn (not installed, non-default)"
  else
    fail "C1: Expected codex status=warn before install, got '${CODEX_STATUS_FIRST}'"
    C_PASS=false
  fi

  if [[ "${CODEX_ON_PATH}" == true ]]; then
    pass "C2: codex binary found on PATH after npm install (/usr/local/bin/codex)"
    info "    npm installs to /usr/local/bin on Debian (default prefix) — on PATH already."
  else
    fail "C2: codex binary NOT found on PATH after install"
    warn "    npm global bin may not be on container PATH. Recheck: npm prefix --global"
    C_PASS=false
  fi

  if [[ "${CODEX_STATUS_SECOND}" == "pass" ]]; then
    pass "C3: codex status flipped warn->pass after install (shutil.which found it)"
  else
    fail "C3: Expected codex status=pass after install, got '${CODEX_STATUS_SECOND}'"
    C_PASS=false
  fi

  if [[ "${DOCTOR_WARNED_COUNT}" -ge 1 ]]; then
    pass "C4: DOCTOR_WARNED telemetry emitted on CLI doctor path (${DOCTOR_WARNED_COUNT} rows)"
  else
    fail "C4: DOCTOR_WARNED telemetry NOT found in SQLite DB"
    C_PASS=false
  fi

  if [[ "${AUTO_PROMOTED_COUNT}" -eq 0 ]]; then
    pass "C5: BACKEND_AUTO_PROMOTED NOT emitted on CLI path (expected — TUI modal path only)"
    info "    Auto-promote requires DoctorModal._auto_promote_backend() in the TUI."
    info "    The CLI doctor path (cli/doctor.py) does not call auto-promote. By design."
  else
    warn "C5: BACKEND_AUTO_PROMOTED found in CLI path (${AUTO_PROMOTED_COUNT} rows) — unexpected"
  fi

  [[ "${C_PASS}" == true ]] && RESULT_C="PASS"
else
  warn "Scenario C: SKIP — npm registry unreachable"
  RESULT_C="SKIP"
fi

record_result "Scenario C" "${RESULT_C}"
case "${RESULT_C}" in
  PASS) pass "Scenario C: PASS" ;;
  SKIP) warn "Scenario C: SKIP (no internet)" ;;
  *)    fail "Scenario C: FAIL" ;;
esac

# ── Summary ───────────────────────────────────────────────────────────────────
header "Results Summary"
for i in "${!SCENARIO_NAMES[@]}"; do
  name="${SCENARIO_NAMES[$i]}"
  result="${SCENARIO_RESULTS[$i]}"
  case "${result}" in
    PASS) echo -e "  ${GREEN}PASS${NC}  ${name}" ;;
    SKIP) echo -e "  ${YELLOW}SKIP${NC}  ${name}" ;;
    *)    echo -e "  ${RED}FAIL${NC}  ${name}" ;;
  esac
done

echo ""
if [[ "${OVERALL_EXIT}" -eq 0 ]]; then
  pass "All scenarios passed."
else
  fail "One or more scenarios failed. See output above for details."
fi

exit "${OVERALL_EXIT}"
