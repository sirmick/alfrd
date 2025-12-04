#!/bin/bash
# Test script for Files feature workflow

echo "======================================"
echo "Testing Files Feature Workflow"
echo "======================================"
echo ""

API_URL="http://localhost:8000"

echo "Step 1: Check available documents with tags"
echo "--------------------------------------"
curl -s "$API_URL/api/v1/documents?limit=10" | jq '.documents[] | {id, document_type, tags}' || echo "No documents found"
echo ""
echo ""

echo "Step 2: Create a file for 'bill' documents tagged 'pge'"
echo "--------------------------------------"
FILE_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/files/create?document_type=bill&tags=pge" \
  -H "Content-Type: application/json")

echo "$FILE_RESPONSE" | jq '.'

FILE_ID=$(echo "$FILE_RESPONSE" | jq -r '.file.id')
echo ""
echo "Created File ID: $FILE_ID"
echo ""
echo ""

echo "Step 3: Check file status (should be 'pending')"
echo "--------------------------------------"
curl -s "$API_URL/api/v1/files/$FILE_ID" | jq '{file: .file | {id, document_type, tags, status, document_count}, document_count: (.documents | length)}'
echo ""
echo ""

echo "Step 4: Wait for FileGeneratorWorker to process..."
echo "--------------------------------------"
echo "Polling every 3 seconds (max 30 seconds)..."
for i in {1..10}; do
  echo -n "Poll #$i: "
  STATUS=$(curl -s "$API_URL/api/v1/files/$FILE_ID" | jq -r '.file.status')
  echo "Status = $STATUS"
  
  if [ "$STATUS" = "generated" ]; then
    echo "✓ File generated!"
    break
  fi
  
  if [ $i -lt 10 ]; then
    sleep 3
  fi
done
echo ""
echo ""

echo "Step 5: View generated file summary"
echo "--------------------------------------"
curl -s "$API_URL/api/v1/files/$FILE_ID" | jq '{
  file: .file | {
    id,
    document_type,
    tags,
    status,
    document_count,
    summary_text,
    summary_metadata
  },
  documents: .documents | length
}'
echo ""
echo ""

echo "Step 6: List all files"
echo "--------------------------------------"
curl -s "$API_URL/api/v1/files" | jq '.files[] | {id, document_type, tags, status, document_count}'
echo ""
echo ""

echo "======================================"
echo "Test Complete!"
echo "======================================"