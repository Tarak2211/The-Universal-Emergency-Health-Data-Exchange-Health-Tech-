"""
Gunicorn config for production deployment.
Run: gunicorn app.main:app -c gunicorn.conf.py
"""
import multiprocessing

# Workers = (2 × CPU cores) + 1  — standard formula
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
timeout = 120           # seconds before killing a stuck worker
keepalive = 5           # keep connections alive for 5s
max_requests = 1000     # restart worker after 1000 requests (prevents memory leaks)
max_requests_jitter = 100
preload_app = True      # load app once, fork workers (saves memory)
accesslog = "-"         # stdout
errorlog  = "-"
loglevel  = "info"
