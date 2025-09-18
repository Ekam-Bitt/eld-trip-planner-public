#!/bin/bash

# Test script for ELD log tracking functionality
# Make sure Docker containers are running first

echo "=== ELD Log Tracking Test Script ==="
echo

# Get auth token
echo "1. Getting auth token..."
AUTH_RESPONSE=$(curl -s -X POST http://localhost:8000/api/drivers/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test123!"}')

ACCESS_TOKEN=$(echo $AUTH_RESPONSE | grep -o '"access":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Failed to get auth token. Make sure you have a user with email 'test@example.com'"
  echo "Response: $AUTH_RESPONSE"
  exit 1
fi

echo "✅ Got auth token"

echo
# Optionally set Mapbox token on profile if provided
if [ -n "$MAPBOX_TOKEN" ]; then
  echo "1b. Setting Mapbox token on profile..."
  PROFILE_RESP=$(curl -s -X PUT http://localhost:8000/api/drivers/profile/ \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"mapbox_api_key\": \"$MAPBOX_TOKEN\"}")
  echo "$PROFILE_RESP" | jq '.' 2>/dev/null || echo "$PROFILE_RESP"
fi

# Use provided TRIP_ID, else get or create
if [ -n "$TRIP_ID" ]; then
  echo "2. Using provided TRIP_ID=$TRIP_ID"
else
  echo "2. Getting trips..."
  TRIPS_RESPONSE=$(curl -s -X GET http://localhost:8000/api/trips/ \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  TRIP_ID=$(echo $TRIPS_RESPONSE | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)

  if [ -z "$TRIP_ID" ]; then
    echo "Creating a test trip..."
    TRIP_RESPONSE=$(curl -s -X POST http://localhost:8000/api/trips/ \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "current_location": "-118.2437,34.0522",
        "pickup_location": "-115.1398,36.1699", 
        "dropoff_location": "-104.9903,39.7392",
        "current_cycle_used_hrs": 0
      }')
    
    TRIP_ID=$(echo $TRIP_RESPONSE | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)
  fi
fi

if [ -z "$TRIP_ID" ]; then
  echo "❌ Failed to get/create trip"
  echo "Response: ${TRIP_RESPONSE:-$TRIPS_RESPONSE}"
  exit 1
fi

echo "✅ Using trip ID: $TRIP_ID"

# Test log events
echo
echo "3. Testing log events (realistic day timeline)..."

DAY=$(date -u +"%Y-%m-%d")

post_event() {
  local status="$1"
  local hhmm="$2" # e.g., 06:30
  local ts="${DAY}T${hhmm}:00Z"
  echo "  - ${status} at ${ts}"
  local payload
  payload=$(jq -n \
    --argjson trip_id "$TRIP_ID" \
    --arg timestamp "$ts" \
    --arg status "$status" \
    '{trip_id: $trip_id, timestamp: $timestamp, status: $status}')
  curl -s -X POST http://localhost:8000/api/logs/ \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    --data-raw "$payload" | jq '.'
}

echo "Creating realistic sequence for ${DAY}..."
# Start OFF at midnight (implicitly assumed by graph, but we create explicitly)
post_event OFF 00:00
# Pre-trip inspection
post_event ON_DUTY 06:30
# Start driving morning
post_event DRIVING 07:00
# Lunch/fuel break
post_event ON_DUTY 12:00
# Back to driving afternoon
post_event DRIVING 12:30
# Post-trip/on duty
post_event ON_DUTY 15:00
# End of day off
post_event OFF 18:00

echo
echo "4. Retrieving all log events for trip $TRIP_ID..."
curl -s -X GET http://localhost:8000/api/logs/$TRIP_ID/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'

echo
echo "✅ Test completed! Check the trip view in your browser to see the graph."
echo "   Trip ID: $TRIP_ID"
echo "   URL: http://localhost:5173/trips"
