import asyncio
from typing import Dict, List, Optional, Callable
from datetime import datetime

from core.client import AsyncBinanceClient
from core.models import Ticker, Kline
from utils.logger import get_logger
from utils.helpers import AsyncCache, retry_async

class MarketDataService:
    """
    Service for handling market data operations with async patterns
    Converts sync market data feeds to async streams
    """
    
    def __init__(self, client: AsyncBinanceClient):
        self.client = client
        self.logger = get_logger(__name__)
        self._price_cache = AsyncCache(ttl=5.0)  # 5 second cache
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._subscribers: Dict[str, List[Callable]] = {}
        self._running = False
        
    async def start(self):
        """Start market data service"""
        self._running = True
        self.logger.info("Market data service started")
    
    async def stop(self):
        """Stop market data service and cleanup"""
        self._running = False
        
        # Cancel all monitoring tasks
        for symbol, task in self._monitoring_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._monitoring_tasks.clear()
        self._subscribers.clear()
        await self._price_cache.clear()
        self.logger.info("Market data service stopped")
    
    async def subscribe_to_price_updates(self, symbol: str, callback: Callable, interval: float = 1.0):
        """
        Subscribe to price updates for a symbol
        Converts sync polling to async event-driven updates
        """
        if symbol not in self._subscribers:
            self._subscribers[symbol] = []
        
        self._subscribers[symbol].append(callback)
        
        # Start monitoring task if not already running
        if symbol not in self._monitoring_tasks:
            task = asyncio.create_task(self._monitor_price(symbol, interval))
            self._monitoring_tasks[symbol] = task
            self.logger.info(f"Started price monitoring for {symbol}")
    
    async def unsubscribe_from_price_updates(self, symbol: str, callback: Callable):
        """Unsubscribe from price updates"""
        if symbol in self._subscribers:
            try:
                self._subscribers[symbol].remove(callback)
                
                # Stop monitoring if no more subscribers
                if not self._subscribers[symbol] and symbol in self._monitoring_tasks:
                    self._monitoring_tasks[symbol].cancel()
                    del self._monitoring_tasks[symbol]
                    del self._subscribers[symbol]
                    self.logger.info(f"Stopped price monitoring for {symbol}")
            except ValueError:
                pass
    
    async def _monitor_price(self, symbol: str, interval: float):
        """Monitor price changes and notify subscribers"""
        last_price = None
        
        while self._running and symbol in self._subscribers:
            try:
                current_price = await self.get_current_price(symbol)
                
                if last_price is not None and current_price != last_price:
                    # Notify all subscribers of price change
                    callbacks = self._subscribers.get(symbol, [])
                    for callback in callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                asyncio.create_task(callback(symbol, current_price, last_price))
                            else:
                                callback(symbol, current_price, last_price)
                        except Exception as e:
                            self.logger.error(f"Error in price callback for {symbol}: {e}")
                
                last_price = current_price
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error monitoring price for {symbol}: {e}")
                await asyncio.sleep(interval)
    
    @retry_async(max_retries=3)
    async def get_current_price(self, symbol: str) -> float:
        """Get current price with caching"""
        # Try cache first
        cached_price = await self._price_cache.get(symbol)
        if cached_price is not None:
            return cached_price
        
        # Fetch from API
        price = await self.client.get_price(symbol)
        await self._price_cache.set(symbol, price)
        return price
    
    @retry_async(max_retries=3)
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker information"""
        return await self.client.get_ticker(symbol)
    
    @retry_async(max_retries=3)
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[Kline]:
        """Get candlestick data"""
        return await self.client.get_klines(symbol, interval, limit)
    
    async def get_multiple_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current prices for multiple symbols concurrently"""
        tasks = [self.get_current_price(symbol) for symbol in symbols]
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        
        result = {}
        for symbol, price in zip(symbols, prices):
            if isinstance(price, Exception):
                self.logger.error(f"Failed to get price for {symbol}: {price}")
            else:
                result[symbol] = price
        
        return result
    
    # ==================== TECHNICAL INDICATORS ====================
    
    async def calculate_sma(self, symbol: str, interval: str, period: int) -> float:
        """Calculate Simple Moving Average"""
        klines = await self.get_klines(symbol, interval, period)
        if len(klines) < period:
            raise ValueError(f"Not enough data points for SMA calculation")
        
        close_prices = [kline.close_price for kline in klines[-period:]]
        return sum(close_prices) / len(close_prices)
    
    async def calculate_ema(self, symbol: str, interval: str, period: int) -> float:
        """Calculate Exponential Moving Average"""
        klines = await self.get_klines(symbol, interval, period * 2)
        if len(klines) < period:
            raise ValueError(f"Not enough data points for EMA calculation")
        
        close_prices = [kline.close_price for kline in klines]
        multiplier = 2 / (period + 1)
        ema = close_prices[0]
        
        for price in close_prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    async def calculate_rsi(self, symbol: str, interval: str, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        klines = await self.get_klines(symbol, interval, period + 1)
        if len(klines) < period + 1:
            raise ValueError(f"Not enough data points for RSI calculation")
        
        close_prices = [kline.close_price for kline in klines]
        
        # Calculate price changes
        price_changes = []
        for i in range(1, len(close_prices)):
            price_changes.append(close_prices[i] - close_prices[i-1])
        
        # Separate gains and losses
        gains = [change if change > 0 else 0 for change in price_changes]
        losses = [-change if change < 0 else 0 for change in price_changes]
        
        # Calculate average gain and loss
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    async def calculate_bollinger_bands(self, symbol: str, interval: str, period: int = 20, std_dev: float = 2) -> Dict[str, float]:
        """Calculate Bollinger Bands"""
        klines = await self.get_klines(symbol, interval, period)
        if len(klines) < period:
            raise ValueError(f"Not enough data points for Bollinger Bands calculation")
        
        close_prices = [kline.close_price for kline in klines[-period:]]
        
        # Calculate SMA
        sma = sum(close_prices) / len(close_prices)
        
        # Calculate standard deviation
        variance = sum((price - sma) ** 2 for price in close_prices) / len(close_prices)
        std_deviation = variance ** 0.5
        
        upper_band = sma + (std_deviation * std_dev)
        lower_band = sma - (std_deviation * std_dev)
        
        return {
            'upper_band': upper_band,
            'middle_band': sma,
            'lower_band': lower_band
        }
    
    # ==================== MARKET ANALYSIS ====================
    
    async def get_market_summary(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get comprehensive market summary for multiple symbols"""
        tasks = []
        for symbol in symbols:
            tasks.append(self._get_symbol_summary(symbol))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        summary = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                self.logger.error(f"Failed to get summary for {symbol}: {result}")
                summary[symbol] = {'error': str(result)}
            else:
                summary[symbol] = result
        
        return summary
    
    async def _get_symbol_summary(self, symbol: str) -> Dict:
        """Get summary for a single symbol"""
        try:
            # Get basic ticker info
            ticker = await self.get_ticker(symbol)
            
            # Get technical indicators
            sma_20 = await self.calculate_sma(symbol, '1h', 20)
            rsi = await self.calculate_rsi(symbol, '1h', 14)
            bollinger = await self.calculate_bollinger_bands(symbol, '1h', 20)
            
            return {
                'price': ticker.price,
                'change_percent': ticker.change_percent,
                'volume': ticker.volume,
                'sma_20': sma_20,
                'rsi': rsi,
                'bollinger_upper': bollinger['upper_band'],
                'bollinger_lower': bollinger['lower_band'],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            raise Exception(f"Failed to get summary for {symbol}: {e}")
    
    async def detect_price_breakout(self, symbol: str, interval: str = '1h', 
                                  lookback_periods: int = 20, breakout_threshold: float = 0.02) -> Optional[str]:
        """Detect price breakouts (support/resistance breaks)"""
        try:
            klines = await self.get_klines(symbol, interval, lookback_periods + 1)
            if len(klines) < lookback_periods + 1:
                return None
            
            recent_highs = [kline.high_price for kline in klines[-lookback_periods:]]
            recent_lows = [kline.low_price for kline in klines[-lookback_periods:]]
            current_price = klines[-1].close_price
            
            resistance = max(recent_highs)
            support = min(recent_lows)
            
            # Check for breakout
            if current_price > resistance * (1 + breakout_threshold):
                return "BULLISH_BREAKOUT"
            elif current_price < support * (1 - breakout_threshold):
                return "BEARISH_BREAKOUT"
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error detecting breakout for {symbol}: {e}")
            return None
