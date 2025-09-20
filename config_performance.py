# Database connection pool settings for optimization
DATABASE_POOL_SIZE = 10
DATABASE_POOL_TIMEOUT = 30
DATABASE_POOL_RECYCLE = 3600
DATABASE_MAX_OVERFLOW = 20

# Query optimization settings  
ENABLE_QUERY_CACHE = True
CACHE_TTL = 300  # 5 minutes

# Background task settings
BACKGROUND_TASK_WORKERS = 4
BACKGROUND_TASK_QUEUE_SIZE = 100
