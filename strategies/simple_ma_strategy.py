from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from strategies.base_strategy import BaseStrategy
from core.models import OrderSide
from utils.helpers import AsyncCache

class SimpleMAStrategy(BaseStrategy):
    """
    Simple Moving Average Crossover Strategy with async implementation
    Demonstrates how to convert traditional sync MA strategies to async
    """
    
    def __init__(self, client, symbol: str, config: Dict[str, Any]):
        super().__init__(client, symbol, config)
        
        # MA Configuration
        self.short_period = config.get('short_ma_period', 10)
        self.long_period = config.get('long_ma_period', 20)
        
        # MA Values
        self.last_short_ma = 0.0
        self.last_long_ma = 0.0
        self.current_short_ma = 0.0
        self.current_long_ma = 0.0
        
        # Price history for MA calculation
        self.price_history: List[float] = []
        self.max_history = max(self.short_period, self.long_period) * 2
        
        # Caching for performance
        self._ma_cache = AsyncCache(ttl=10.0)  # 10 second cache
        
        # Strategy state
        self.crossover_detected = False
        self.last_crossover_time = None
        self.min_crossover_interval = config.get('min_crossover_interval', 300)  # 5 minutes
    
    async def on_start(self):
        """Initialize strategy with historical data"""
        self.logger.info(f"Starting Simple MA Strategy - Short: {self.short_period}, Long: {self.long_period}")
        
        # Load initial price history
        await self._load_initial_history()
        
        # Calculate initial MAs
        await self._update_moving_averages()
        
        self.logger.info(f"Initial Short MA: {self.current_short_ma:.4f}, Long MA: {self.current_long_ma:.4f}")
    
    async def on_stop(self):
        """Cleanup strategy"""
        await self._ma_cache.clear()
        self.logger.info("Simple MA Strategy stopped")
    
    async def on_price_update(self, price: float, data: Dict[str, Any]):
        """
        Process real-time price updates
        Converts sync price polling to async event-driven updates
        """
        # Add new price to history
        self.price_history.append(price)
        
        # Keep only necessary history
        if len(self.price_history) > self.max_history:
            self.price_history = self.price_history[-self.max_history:]
        
        # Update moving averages if we have enough data
        if len(self.price_history) >= self.long_period:
            await self._update_moving_averages()
    
    async def on_kline_update(self, kline_data: Dict[str, Any]):
        """Process kline updates for more precise timing"""
        try:
            kline = kline_data.get('k', {})
            if kline.get('x'):  # Kline is closed
                close_price = float(kline['c'])
                await self.on_price_update(close_price, kline_data)
        except Exception as e:
            self.logger.error(f"Error processing kline update: {e}")
    
    async def generate_signal(self) -> Optional[str]:
        """
        Generate MA crossover signals with async pattern
        Converts traditional sync signal generation to async
        """
        if len(self.price_history) < self.long_period:
            return None
        
        # Check for crossover with rate limiting
        if await self._check_crossover_rate_limit():
            return None
        
        signal = None
        
        # Golden Cross - Short MA crosses above Long MA (Bullish)
        if (self.last_short_ma <= self.last_long_ma and 
            self.current_short_ma > self.current_long_ma and 
            self.last_short_ma > 0):
            
            signal = 'BUY'
            self.crossover_detected = True
            self.last_crossover_time = datetime.now()
            
            await self._log_crossover_signal("Golden Cross", signal)
        
        # Death Cross - Short MA crosses below Long MA (Bearish)
        elif (self.last_short_ma >= self.last_long_ma and 
              self.current_short_ma < self.current_long_ma and 
              self.last_short_ma > 0):
            
            signal = 'SELL'
            self.crossover_detected = True
            self.last_crossover_time = datetime.now()
            
            await self._log_crossover_signal("Death Cross", signal)
        
        # Additional confirmation filters
        if signal:
            confirmed_signal = await self._confirm_signal(signal)
            return confirmed_signal
        
        return None
    
    # ==================== PRIVATE HELPER METHODS ====================
    
    async def _load_initial_history(self):
        """Load initial price history from API"""
        try:
            # Get historical klines
            klines = await self.client.get_klines(
                self.symbol, 
                self.config.get('kline_interval', '1m'), 
                self.max_history
            )
            
            # Extract close prices
            self.price_history = [kline.close_price for kline in klines]
            self.logger.info(f"Loaded {len(self.price_history)} historical prices")
            
        except Exception as e:
            self.logger.error(f"Error loading initial history: {e}")
            # Fallback to current price
            current_price = await self.market_data.get_current_price(self.symbol)
            self.price_history = [current_price] * self.long_period
    
    async def _update_moving_averages(self):
        """Update moving averages with caching"""
        cache_key = f"ma_{len(self.price_history)}"
        cached_mas = await self._ma_cache.get(cache_key)
        
        if cached_mas:
            self.last_short_ma = self.current_short_ma
            self.last_long_ma = self.current_long_ma
            self.current_short_ma, self.current_long_ma = cached_mas
            return
        
        # Store previous values
        self.last_short_ma = self.current_short_ma
        self.last_long_ma = self.current_long_ma
        
        # Calculate new MAs
        if len(self.price_history) >= self.short_period:
            self.current_short_ma = sum(self.price_history[-self.short_period:]) / self.short_period
        
        if len(self.price_history) >= self.long_period:
            self.current_long_ma = sum(self.price_history[-self.long_period:]) / self.long_period
        
        # Cache the results
        await self._ma_cache.set(cache_key, (self.current_short_ma, self.current_long_ma))
    
    async def _check_crossover_rate_limit(self) -> bool:
        """Check if enough time has passed since last crossover"""
        if not self.last_crossover_time:
            return False
        
        time_since_crossover = (datetime.now() - self.last_crossover_time).total_seconds()
        return time_since_crossover < self.min_crossover_interval
    
    async def _confirm_signal(self, signal: str) -> Optional[str]:
        """Apply additional confirmation filters to signals"""
        try:
            # Volume confirmation
            if self.config.get('require_volume_confirmation', False):
                if not await self._check_volume_confirmation():
                    self.logger.info(f"Signal {signal} rejected due to insufficient volume")
                    return None
            
            # Trend confirmation
            if self.config.get('require_trend_confirmation', False):
                if not await self._check_trend_confirmation(signal):
                    self.logger.info(f"Signal {signal} rejected due to trend disagreement")
                    return None
            
            # Price action confirmation
            if self.config.get('require_price_action_confirmation', False):
                if not await self._check_price_action_confirmation(signal):
                    self.logger.info(f"Signal {signal} rejected due to weak price action")
                    return None
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error in signal confirmation: {e}")
            return None
    
    async def _check_volume_confirmation(self) -> bool:
        """Check if current volume supports the signal"""
        try:
            ticker = await self.client.get_ticker(self.symbol)
            
            # Get average volume (simplified - could use rolling average)
            volume_threshold = self.config.get('volume_threshold_multiplier', 1.2)
            
            # For simplicity, we'll assume current volume is adequate
            # In a real implementation, you'd compare against historical volume
            return ticker.volume > 0
            
        except Exception as e:
            self.logger.error(f"Error checking volume confirmation: {e}")
            return True  # Default to allowing signal
    
    async def _check_trend_confirmation(self, signal: str) -> bool:
        """Check if longer-term trend supports the signal"""
        try:
            # Use longer period MA for trend confirmation
            trend_period = self.config.get('trend_confirmation_period', 50)
            
            if len(self.price_history) < trend_period:
                return True  # Not enough data, allow signal
            
            trend_ma = sum(self.price_history[-trend_period:]) / trend_period
            current_price = self.price_history[-1]
            
            if signal == 'BUY':
                return current_price > trend_ma  # Price above long-term MA
            else:
                return current_price < trend_ma  # Price below long-term MA
                
        except Exception as e:
            self.logger.error(f"Error checking trend confirmation: {e}")
            return True
    
    async def _check_price_action_confirmation(self, signal: str) -> bool:
        """Check price action patterns for signal confirmation"""
        try:
            if len(self.price_history) < 3:
                return True
            
            # Simple momentum check
            recent_prices = self.price_history[-3:]
            
            if signal == 'BUY':
                # Check for upward momentum
                return recent_prices[-1] > recent_prices[-2] > recent_prices[-3]
            else:
                # Check for downward momentum
                return recent_prices[-1] < recent_prices[-2] < recent_prices[-3]
                
        except Exception as e:
            self.logger.error(f"Error checking price action: {e}")
            return True
    
    async def _log_crossover_signal(self, crossover_type: str, signal: str):
        """Log crossover signal with detailed information"""
        current_price = self.price_history[-1] if self.price_history else 0
        
        self.logger.info(f"🚨 {crossover_type} detected!")
        self.logger.info(f"Signal: {signal}")
        self.logger.info(f"Current Price: ${current_price:.4f}")
        self.logger.info(f"Short MA ({self.short_period}): {self.current_short_ma:.4f}")
        self.logger.info(f"Long MA ({self.long_period}): {self.current_long_ma:.4f}")
        self.logger.info(f"MA Difference: {abs(self.current_short_ma - self.current_long_ma):.4f}")
    
    # ==================== STRATEGY SPECIFIC METHODS ====================
    
    async def get_ma_status(self) -> Dict[str, Any]:
        """Get current moving average status"""
        return {
            'short_ma': self.current_short_ma,
            'long_ma': self.current_long_ma,
            'short_period': self.short_period,
            'long_period': self.long_period,
            'crossover_detected': self.crossover_detected,
            'last_crossover_time': self.last_crossover_time.isoformat() if self.last_crossover_time else None,
            'price_history_length': len(self.price_history),
            'ma_spread': abs(self.current_short_ma - self.current_long_ma),
            'ma_spread_percent': (abs(self.current_short_ma - self.current_long_ma) / self.current_long_ma * 100) if self.current_long_ma > 0 else 0
        }
    
    async def calculate_ema(self, period: int) -> float:
        """Calculate Exponential Moving Average for comparison"""
        if len(self.price_history) < period:
            return 0.0
        
        multiplier = 2 / (period + 1)
        ema = self.price_history[-period]  # Start with SMA
        
        for price in self.price_history[-period + 1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    async def get_strategy_health(self) -> Dict[str, Any]:
        """Get strategy health metrics"""
        ma_status = await self.get_ma_status()
        
        # Calculate strategy health score
        health_score = 100
        
        # Reduce score if not enough data
        if len(self.price_history) < self.long_period:
            health_score -= 30
        
        # Reduce score if MAs are too close (choppy market)
        if ma_status['ma_spread_percent'] < 0.1:
            health_score -= 20
        
        # Reduce score if no recent activity
        if self.last_crossover_time:
            hours_since_crossover = (datetime.now() - self.last_crossover_time).total_seconds() / 3600
            if hours_since_crossover > 24:
                health_score -= 15
        
        return {
            'health_score': max(0, health_score),
            'data_quality': 'Good' if len(self.price_history) >= self.long_period else 'Insufficient',
            'market_condition': 'Trending' if ma_status['ma_spread_percent'] > 0.5 else 'Choppy',
            'signal_frequency': len([s for s in self.signal_history if s['executed']]),
            'last_activity': self.last_crossover_time.isoformat() if self.last_crossover_time else 'None'
        }
    
    async def optimize_ma_parameters(self) -> Dict[str, Any]:
        """Simple parameter optimization (placeholder)"""
        self.logger.info("MA parameter optimization would analyze historical performance")
        
        # This is a simplified version - real optimization would:
        # 1. Test different MA periods
        # 2. Calculate performance metrics for each combination
        # 3. Return optimal parameters
        
        return {
            'current_short_period': self.short_period,
            'current_long_period': self.long_period,
            'suggested_short_period': self.short_period,
            'suggested_long_period': self.long_period,
            'optimization_status': 'Not implemented'
        }
