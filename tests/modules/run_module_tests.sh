#!/bin/sh
# Run every module test vector against project.circ (or the file given).
#   tests/modules/run_module_tests.sh [project.circ]
DIR=$(cd "$(dirname "$0")" && pwd)
CIRC=${1:-$DIR/../../project.circ}
JAVA=${JAVA:-java}
JAR=${LOGISIM_JAR:-/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-4.1.0-all.jar}
fail=0
for vec in "$DIR"/*.vec; do
  name=$(basename "$vec" .vec)
  out=$("$JAVA" -jar "$JAR" --no-splash --test-vector "$name" "$vec" "$CIRC" 2>&1)
  summary=$(printf '%s\n' "$out" | grep -E '^Passed:' | tail -1)
  printf '%-20s %s\n' "$name" "${summary:-ERROR}"
  case "$summary" in
    *"Failed: 0"*) ;;
    *) fail=1; printf '%s\n' "$out" | grep -v '^\s*at ' | grep -A2 -E 'Error' | head -12 ;;
  esac
done
exit $fail
