from typing import Optional

class BinanceAPIError(Exception):
    """Base exception for Binance API errors"""
    def __init__(self, message: str, error_code: Optional[int] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class RateLimitError(BinanceAPIError):
    """Raised when rate limit is exceeded"""
    pass

class InsufficientBalanceError(BinanceAPIError):
    """Raised when account has insufficient balance"""
    pass

class InvalidSymbolError(BinanceAPIError):
    """Raised when symbol is invalid"""
    pass

class OrderError(BinanceAPIError):
    """Raised when order operation fails"""
    pass

class ConnectionError(BinanceAPIError):
    """Raised when connection fails"""
    pass

class AuthenticationError(BinanceAPIError):
    """Raised when authentication fails"""
    pass
