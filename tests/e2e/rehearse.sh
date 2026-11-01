#!/bin/sh
# Run the whole browser suite several times, and stop at the first run that is not clean.
runs="${1:-3}"
npm ci --no-audit --no-fund > /dev/null 2>&1 || { echo "Could not install the test tools"; exit 1; }
number=1
while [ "$number" -le "$runs" ]; do
  echo "Rehearsal $number of $runs"
  if ! npx playwright test --project=stage --reporter=list > "rehearsal-$number.log" 2>&1; then
    tail -25 "rehearsal-$number.log"
    echo "Rehearsal $number failed"
    exit 1
  fi
  tail -2 "rehearsal-$number.log"
  rm -f "rehearsal-$number.log"
  number=$((number + 1))
done
echo "All $runs rehearsals clean"
