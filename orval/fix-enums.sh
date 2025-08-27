#!/bin/bash

# Script to add @ts-ignore TS2450 comments above enum spreading lines
# Usage: ./fix-enums.sh <file1> <file2> ...

for file in "$@"; do
  if [[ -f "$file" ]]; then
    echo "Processing: $file"
    
    # Use sed to add @ts-ignore TS2450 before lines that spread enums
    # Pattern: export const X = {...SomeEnum,...AnotherEnum,...} as const
    # More specific: enums end with "Enum"
    sed -i '' '/^export const .* = {.*Enum.*} as const$/s/^/\/\/ @ts-ignore TS2450\
/' "$file"
    
    echo "Fixed enum spreading in: $file"
  else
    echo "File not found: $file"
  fi
done