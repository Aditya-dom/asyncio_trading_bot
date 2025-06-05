import asyncio
import time
from typing import Callable, Any, Optional, Union
from functools import wraps
from core.models import OrderSide

def retry_async(max_retries: int = 3, delay: float = 1.0, backoff_factor: float = 2.0):
    """
    Decorator for retrying async functions with exponential backoff
    Converts unreliable sync/callback patterns to reliable async operations
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        sleep_time = delay * (backoff_factor ** attempt)
                        await asyncio.sleep(sleep_time)
                    continue
            raise last_exception
        return wrapper
    return decorator

def async_timeout(timeout_seconds: float):
    """Decorator to add timeout to async functions"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
        return wrapper
    return decorator

async def run_with_semaphore(semaphore: asyncio.Semaphore, coro):
    """Run coroutine with semaphore to limit concurrency"""
    async with semaphore:
        return await coro

async def gather_with_concurrency(max_concurrent: int, *coroutines):
    """Run coroutines with limited concurrency"""
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [run_with_semaphore(semaphore, coro) for coro in coroutines]
    return await asyncio.gather(*tasks)

# ==================== TRADING HELPERS ====================

def calculate_quantity(balance: float, price: float, percentage: float) -> float:
    """Calculate quantity based on balance and risk percentage"""
    return (balance * percentage) / price

def calculate_stop_loss(entry_price: float, percentage: float, side: Union[str, OrderSide]) -> float:
    """Calculate stop loss price"""
    side_str = side.value if isinstance(side, OrderSide) else side.upper()
    if side_str == "BUY":
        return entry_price * (1 - percentage)
    else:
        return entry_price * (1 + percentage)

def calculate_take_profit(entry_price: float, percentage: float, side: Union[str, OrderSide]) -> float:
    """Calculate take profit price"""
    side_str = side.value if isinstance(side, OrderSide) else side.upper()
    if side_str == "BUY":
        return entry_price * (1 + percentage)
    else:
        return entry_price * (1 - percentage)

def round_step_size(quantity: float, step_size: float) -> float:
    """Round quantity to exchange step size"""
    precision = len(str(step_size).split('.')[-1])
    return round(quantity, precision)

def format_price(price: float, tick_size: float) -> float:
    """Format price according to exchange tick size"""
    precision = len(str(tick_size).split('.')[-1])
    return round(price, precision)

def calculate_percentage_change(old_price: float, new_price: float) -> float:
    """Calculate percentage change between two prices"""
    return ((new_price - old_price) / old_price) * 100

# ==================== ASYNC UTILITIES ====================

class AsyncRateLimiter:
    """Async rate limiter for API calls"""
    
    def __init__(self, calls_per_second: float):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire rate limit token"""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.last_call = time.time()

class AsyncCache:
    """Simple async cache with TTL"""
    
    def __init__(self, ttl: float = 60.0):
        self.ttl = ttl
        self._cache = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: Any):
        """Set cached value"""
        async with self._lock:
            self._cache[key] = (value, time.time())
    
    async def clear(self):
        """Clear all cached values"""
        async with self._lock:
            self._cache.clear()

class AsyncEventEmitter:
    """Simple async event emitter for pub/sub patterns"""
    
    def __init__(self):
        self._listeners = {}
        self._lock = asyncio.Lock()
    
    async def on(self, event: str, callback: Callable):
        """Register event listener"""
        async with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)
    
    async def emit(self, event: str, *args, **kwargs):
        """Emit event to all listeners"""
        listeners = []
        async with self._lock:
            if event in self._listeners:
                listeners = self._listeners[event].copy()
        
        # Execute callbacks concurrently
        tasks = []
        for callback in listeners:
            if asyncio.iscoroutinefunction(callback):
                tasks.append(callback(*args, **kwargs))
            else:
                # Wrap sync callback in async
                tasks.append(asyncio.create_task(asyncio.to_thread(callback, *args, **kwargs)))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def remove_listener(self, event: str, callback: Callable):
        """Remove event listener"""
        async with self._lock:
            if event in self._listeners:
                try:
                    self._listeners[event].remove(callback)
                    if not self._listeners[event]:
                        del self._listeners[event]
                except ValueError:
                    pass

# ==================== CALLBACK TO ASYNC CONVERTERS ====================

def callback_to_async(func: Callable, *args, **kwargs):
    """Convert callback-based function to async"""
    future = asyncio.Future()
    
    def callback_wrapper(*cb_args, **cb_kwargs):
        if not future.done():
            # Assume first argument is error (if any), second is result
            if cb_args and isinstance(cb_args[0], Exception):
                future.set_exception(cb_args[0])
            else:
                future.set_result(cb_args[0] if cb_args else None)
    
    # Add callback to the original function call
    try:
        func(*args, callback=callback_wrapper, **kwargs)
    except Exception as e:
        future.set_exception(e)
    
    return future

class AsyncBrokerWrapper:
    """
    Generic wrapper to convert sync/callback broker APIs to async
    This is the core pattern for wrapping traditional broker APIs
    """
    
    def __init__(self, sync_client):
        self.sync_client = sync_client
        self._executor = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._executor:
            self._executor.shutdown(wait=True)
    
    async def run_sync(self, func: Callable, *args, **kwargs):
        """Run synchronous function in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args, **kwargs)
    
    async def convert_callback(self, func: Callable, *args, **kwargs):
        """Convert callback-based function to async"""
        return await callback_to_async(func, *args, **kwargs)
