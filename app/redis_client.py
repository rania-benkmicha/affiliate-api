from redis import Redis

# Single Redis connection instance, used by API + worker + queue

redis_client = Redis(host="redis", port=6379, db=0, decode_responses=False)
