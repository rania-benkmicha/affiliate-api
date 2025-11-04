#!/bin/bash

BASE_URL="http://localhost:5000"
WEBHOOK_SECRET="randomWord"
EDITOR_ID=42
ADVERTISER_ID=1

#---------------------------------------------

echo " Shutting down the containers"
docker compose down --volumes --remove-orphans

echo " Starting fresh Docker containers..."
docker compose up --build -d

# Wait a few seconds for Redis to be ready
echo "Waiting for Redis to start..."
sleep 3

echo "Flushing Redis ..."
docker compose exec -T redis redis-cli FLUSHALL

# ----------------- Health Check -----------------
echo "1 Health Check"
res=$(curl -s -w "%{http_code}" "$BASE_URL/")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "200" ]; then
    echo "Health OK"
else
    echo "Health failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"
echo -e "\n"

# ----------------- GET /advertisers -----------------
echo "2 GET /advertisers"
res=$(curl -s -w "%{http_code}" "$BASE_URL/advertisers?editor_id=$EDITOR_ID")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "200" ]; then
    echo "GET /advertisers OK"
else
    echo "GET /advertisers failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"
echo -e "\n"

# ----------------- GET /advertisers/<id> -----------------
echo "2b GET /advertisers/$ADVERTISER_ID"
res=$(curl -s -w "%{http_code}" "$BASE_URL/advertisers/$ADVERTISER_ID?editor_id=$EDITOR_ID")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "200" ]; then
    echo "GET /advertisers/$ADVERTISER_ID OK"
else
    echo "GET /advertisers/$ADVERTISER_ID failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"
echo -e "\n"

# ----------------- POST /applications -----------------
echo "3 POST /applications"
res=$(curl -s -w "%{http_code}" -X POST "$BASE_URL/applications" \
     -H "Content-Type: application/json" \
     -d "{\"advertiser_id\":$ADVERTISER_ID,\"editor_id\":$EDITOR_ID}")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "202" ]; then
    echo "POST /applications OK"
else
    echo "POST /applications failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"

# Extract job_id from response
job_id=$(echo "$body" | jq -r '.job_id')

echo "Waiting for worker to process job $job_id..."
while true; do
    status=$(docker compose exec -T redis redis-cli HGET "rq:job:$job_id" "status")
    if [[ "$status" == "finished" ]]; then
        echo "Job finished"
        break
    elif [[ "$status" == "failed" ]]; then
        echo "Job failed "
        break
    fi
    sleep 0.5
done





# ----------------- GET /applications (check updated status) -----------------
echo "3b GET /applications"
res=$(curl -s -w "%{http_code}" "$BASE_URL/applications")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "200" ]; then
    echo "GET /applications OK"
else
    echo "GET /applications failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"
echo -e "\n"


# ----------------- POST /webhook/orders -----------------
echo "4 POST /webhook/orders"
payload="{\"order_id\":\"ORD1001\",\"advertiser_id\":1,\"user_id\":$EDITOR_ID,\"amount\":120.5,\"commission\":6.2}"
signature=$(echo -n "$payload" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | sed 's/^.* //')
res=$(curl -s -w "%{http_code}" -X POST "$BASE_URL/webhook/orders" \
     -H "Content-Type: application/json" \
     -H "X-Partner-Signature: $signature" \
     --data-raw "$payload")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "200" ]; then
    echo "POST /webhook/orders OK"
else
    echo "POST /webhook/orders failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"
echo -e "\n"

# ----------------- GET /orders -----------------
echo "5 GET /orders"
res=$(curl -s -w "%{http_code}" "$BASE_URL/orders")
http_code="${res: -3}"
body="${res::-3}"
if [ "$http_code" == "200" ]; then
    echo "GET /orders OK"
else
    echo "GET /orders failed (HTTP $http_code)"
fi
echo "$body" | jq . 2>/dev/null || echo "$body"
echo -e "\n"

echo "All tests completed!"
