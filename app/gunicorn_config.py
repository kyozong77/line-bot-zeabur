bind = "0.0.0.0:5000"
workers = 4
threads = 2
worker_class = "sync"
timeout = 120
keepalive = 2

# Logging
accesslog = "/app/logs/access.log"
errorlog = "/app/logs/error.log"
loglevel = "info"
