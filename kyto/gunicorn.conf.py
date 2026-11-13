import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))   # keep 1 unless REDIS_URL is set (rate limits live in memory)
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = "*"   # we sit behind the host's proxy; set TRUSTED_PROXY_COUNT=1 in the environment too
