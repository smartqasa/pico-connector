#!/usr/bin/env bash

set -euo pipefail

readonly REPO_EXPECTED="smartqasa/pico-link"
readonly SOURCE_BRANCH="beta"
readonly TARGET_BRANCH="main"
readonly INTEGRATION_PATH="custom_components/pico_link"

original_branch=""

restore_branch() {
    if [[ -n "${original_branch}" ]]; then
        git switch "${original_branch}" >/dev/null 2>&1 || true
    fi
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

echo "Promoting ${SOURCE_BRANCH} → ${TARGET_BRANCH} for ${REPO_EXPECTED}..."

# ================================================================
# REPOSITORY VALIDATION
# ================================================================

git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    fail "Not inside a Git repository."

original_branch=$(git branch --show-current)

if [[ -z "${original_branch}" ]]; then
    fail "Detached HEAD is not supported."
fi

trap restore_branch EXIT

remote_url=$(git remote get-url origin 2>/dev/null || true)

if [[ -z "${remote_url}" ]]; then
    fail "No 'origin' remote is configured."
fi

if [[ "${remote_url}" != *"${REPO_EXPECTED}"* ]]; then
    fail "Expected repository ${REPO_EXPECTED}, found origin ${remote_url}."
fi

if [[ -n "$(git status --porcelain)" ]]; then
    fail "Working tree is not clean. Commit or stash changes first."
fi

if [[ ! -d "${INTEGRATION_PATH}" ]]; then
    fail "Integration directory ${INTEGRATION_PATH} was not found."
fi

# ================================================================
# UPDATE REMOTE REFERENCES
# ================================================================

echo "Fetching latest remote branches..."
git fetch --prune origin

git show-ref --verify --quiet "refs/remotes/origin/${SOURCE_BRANCH}" ||
    fail "origin/${SOURCE_BRANCH} does not exist."

git show-ref --verify --quiet "refs/remotes/origin/${TARGET_BRANCH}" ||
    fail "origin/${TARGET_BRANCH} does not exist."

# ================================================================
# UPDATE LOCAL BETA
# ================================================================

if ! git show-ref --verify --quiet "refs/heads/${SOURCE_BRANCH}"; then
    echo "Creating local ${SOURCE_BRANCH} from origin/${SOURCE_BRANCH}..."
    git branch \
        --track \
        "${SOURCE_BRANCH}" \
        "origin/${SOURCE_BRANCH}"
fi

echo "Updating local ${SOURCE_BRANCH}..."
git switch "${SOURCE_BRANCH}"
git pull --ff-only origin "${SOURCE_BRANCH}"

# Confirm the working tree remains clean after updating.
if [[ -n "$(git status --porcelain)" ]]; then
    fail "Working tree changed after updating ${SOURCE_BRANCH}."
fi

# ================================================================
# VALIDATION
# ================================================================

echo "Checking Python syntax..."
python -m compileall \
    -q \
    "${INTEGRATION_PATH}"

echo "Validating JSON files..."
python -m json.tool \
    "${INTEGRATION_PATH}/manifest.json" \
    >/dev/null

if [[ -f "hacs.json" ]]; then
    python -m json.tool \
        "hacs.json" \
        >/dev/null
fi

if command -v ruff >/dev/null 2>&1; then
    echo "Running Ruff..."
    ruff check "${INTEGRATION_PATH}"
else
    echo "Ruff is not installed; skipping lint checks."
fi

# Remove compileall cache directories so validation does not leave
# untracked files in the working tree.
find "${INTEGRATION_PATH}" \
    -type d \
    -name "__pycache__" \
    -prune \
    -exec rm -rf {} +

if [[ -n "$(git status --porcelain)" ]]; then
    fail "Validation left unexpected working-tree changes."
fi

# ================================================================
# PROMOTION
# ================================================================

if ! git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH}"; then
    echo "Creating local ${TARGET_BRANCH} from origin/${TARGET_BRANCH}..."
    git branch \
        --track \
        "${TARGET_BRANCH}" \
        "origin/${TARGET_BRANCH}"
fi

source_commit=$(git rev-parse "origin/${SOURCE_BRANCH}")
target_commit=$(git rev-parse "origin/${TARGET_BRANCH}")

if [[ "${source_commit}" == "${target_commit}" ]]; then
    echo "${TARGET_BRANCH} already matches ${SOURCE_BRANCH}."
    exit 0
fi

echo "Switching to ${TARGET_BRANCH}..."
git switch "${TARGET_BRANCH}"

echo "Resetting ${TARGET_BRANCH} to origin/${SOURCE_BRANCH}..."
git reset --hard "origin/${SOURCE_BRANCH}"

echo "Pushing ${TARGET_BRANCH}..."
git push \
    --force-with-lease="refs/heads/${TARGET_BRANCH}:${target_commit}" \
    origin \
    "${TARGET_BRANCH}:${TARGET_BRANCH}"

# ================================================================
# COMPLETION
# ================================================================

git switch "${SOURCE_BRANCH}"
original_branch="${SOURCE_BRANCH}"

echo "Promotion complete."
echo "${TARGET_BRANCH} now points to ${source_commit}."
echo "Current branch: ${SOURCE_BRANCH}"