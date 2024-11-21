import time

"""
Rate limiting implementation module.
Provides rate limiting functionality to prevent API abuse and ensure
compliance with external service limits.

"""

class RateLimiter:
    def __init__(self, max_calls, time_frame):
        self.max_calls = max_calls
        self.time_frame = time_frame
        self.calls = []

    def try_acquire(self):
        now = time.time()
        self.calls = [call for call in self.calls if now - call < self.time_frame]
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

async def rate_limited_request(method, *args, **kwargs):
    while not rate_limiter.try_acquire():
        await asyncio.sleep(0.1)
    return await method(*args, **kwargs)

rate_limiter = RateLimiter(max_calls=30, time_frame=1)  # 30 calls per second