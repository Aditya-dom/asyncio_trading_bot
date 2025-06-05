import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.client import AsyncBinanceClient
from core.models import OrderSide
from services.market_data import MarketDataService
from services.trading import TradingService
from services.websocket_manager import WebSocketManager
from utils.logger import get_logger

class BaseStrategy(ABC):
    """
    Base class for trading strategies with async patterns
    Converts traditional sync/callback strategy patterns to async event-driven
    """
    
    def __init__(self, client: AsyncBinanceClient, symbol: str, config: Dict[str, Any]):
        self.client = client
        self.symbol = symbol.upper()
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        
        # Services - async wrappers for trading operations
        self.market_data = MarketDataService(client)
        self.trading = TradingService(client)
        self.websocket = WebSocketManager()
        
        # Strategy state
        self.is_running = False
        self.position_size = 0.0
        self.entry_price = 0.0
        self.last_signal = None
        self.signal_history: List[Dict] = []
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        self.start_time = None
        
        # Event handlers storage
        self._event_handlers = {}
    
    # ==================== LIFECYCLE METHODS ====================
    
    async def start(self):
        """Start the strategy with full async initialization"""
        self.is_running = True
        self.start_time = datetime.now()
        
        # Start all services
        await self.market_data.start()
        await self.trading.start()
        await self.websocket.start()
        
        # Setup WebSocket subscriptions
        await self._setup_websocket_subscriptions()
        
        # Call strategy-specific initialization
        await self.on_start()
        
        self.logger.info(f"Strategy started for {self.symbol}")
    
    async def stop(self):
        """Stop the strategy and cleanup resources"""
        self.is_running = False
        
        # Call strategy-specific cleanup
        await self.on_stop()
        
        # Stop all services
        await self.websocket.stop()
        await self.market_data.stop()
        await self.trading.stop()
        
        # Log performance summary
        await self._log_performance_summary()
        
        self.logger.info(f"Strategy stopped for {self.symbol}")
    
    async def _setup_websocket_subscriptions(self):
        """Setup WebSocket subscriptions for real-time data"""
        # Subscribe to price updates
        await self.websocket.subscribe_ticker(self.symbol, self._on_ticker_update)
        
        # Subscribe to kline updates
        kline_interval = self.config.get('kline_interval', '1m')
        await self.websocket.subscribe_kline(self.symbol, kline_interval, self._on_kline_update)
        
        # Subscribe to trade updates for volume analysis
        await self.websocket.subscribe_trade(self.symbol, self._on_trade_update)
    
    # ==================== ABSTRACT METHODS ====================
    
    @abstractmethod
    async def on_start(self):
        """Called when strategy starts - implement strategy-specific initialization"""
        pass
    
    @abstractmethod
    async def on_stop(self):
        """Called when strategy stops - implement strategy-specific cleanup"""
        pass
    
    @abstractmethod
    async def on_price_update(self, price: float, data: Dict[str, Any]):
        """Called when price is updated - implement price-based logic"""
        pass
    
    @abstractmethod
    async def on_kline_update(self, kline_data: Dict[str, Any]):
        """Called when kline is updated - implement candlestick-based logic"""
        pass
    
    @abstractmethod
    async def generate_signal(self) -> Optional[str]:
        """Generate trading signal ('BUY', 'SELL', or None)"""
        pass
    
    # ==================== EVENT HANDLERS ====================
    
    async def _on_ticker_update(self, data: Dict[str, Any]):
        """Handle ticker updates from WebSocket"""
        try:
            price = float(data['c'])  # Current price
            await self.on_price_update(price, data)
        except Exception as e:
            self.logger.error(f"Error processing ticker update: {e}")
    
    async def _on_kline_update(self, data: Dict[str, Any]):
        """Handle kline updates from WebSocket"""
        try:
            await self.on_kline_update(data)
        except Exception as e:
            self.logger.error(f"Error processing kline update: {e}")
    
    async def _on_trade_update(self, data: Dict[str, Any]):
        """Handle trade updates from WebSocket"""
        try:
            await self.on_trade_update(data)
        except Exception as e:
            self.logger.error(f"Error processing trade update: {e}")
    
    async def on_trade_update(self, data: Dict[str, Any]):
        """Override this method to handle trade updates"""
        pass
    
    # ==================== SIGNAL PROCESSING ====================
    
    async def execute_signal(self, signal: str):
        """
        Execute a trading signal with full async error handling
        Converts sync signal execution to async with proper risk management
        """
        try:
            current_price = await self.market_data.get_current_price(self.symbol)
            risk_amount = self.config.get('risk_amount', 100.0)
            stop_loss_pct = self.config.get('stop_loss_percentage', 0.02)
            take_profit_pct = self.config.get('take_profit_percentage', 0.04)
            
            # Record signal
            signal_record = {
                'signal': signal,
                'price': current_price,
                'timestamp': datetime.now(),
                'executed': False
            }
            
            if signal == 'BUY' and self.position_size <= 0:
                result = await self.trading.execute_strategy_order(
                    self.symbol, 
                    OrderSide.BUY, 
                    risk_amount, 
                    current_price, 
                    stop_loss_pct, 
                    take_profit_pct
                )
                
                self.position_size = result['executed_quantity']
                self.entry_price = current_price
                signal_record['executed'] = True
                signal_record['order_id'] = result['main_order'].order_id
                
                self.logger.info(f"BUY signal executed at ${current_price}")
                
            elif signal == 'SELL' and self.position_size >= 0:
                result = await self.trading.execute_strategy_order(
                    self.symbol, 
                    OrderSide.SELL, 
                    risk_amount, 
                    current_price, 
                    stop_loss_pct, 
                    take_profit_pct
                )
                
                # Calculate PnL if we had a position
                if self.position_size > 0:
                    pnl = (current_price - self.entry_price) * self.position_size
                    self.total_pnl += pnl
                    self.total_trades += 1
                    if pnl > 0:
                        self.winning_trades += 1
                
                self.position_size = -result['executed_quantity']
                self.entry_price = current_price
                signal_record['executed'] = True
                signal_record['order_id'] = result['main_order'].order_id
                
                self.logger.info(f"SELL signal executed at ${current_price}")
            
            self.signal_history.append(signal_record)
            
        except Exception as e:
            self.logger.error(f"Failed to execute signal {signal}: {e}")
            signal_record['error'] = str(e)
            self.signal_history.append(signal_record)
    
    async def run(self):
        """
        Main strategy loop with async event-driven architecture
        This replaces traditional sync polling with async event handling
        """
        self.logger.info(f"Starting strategy loop for {self.symbol}")
        
        # Main strategy loop
        while self.is_running:
            try:
                # Generate and execute signals
                signal = await self.generate_signal()
                
                if signal and signal != self.last_signal:
                    await self.execute_signal(signal)
                    self.last_signal = signal
                
                # Strategy loop interval
                await asyncio.sleep(self.config.get('loop_interval', 1.0))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in strategy loop: {e}")
                await asyncio.sleep(5)  # Error recovery delay
    
    # ==================== UTILITY METHODS ====================
    
    async def get_current_position(self) -> Dict[str, Any]:
        """Get current position information"""
        return await self.trading.get_position_info(self.symbol)
    
    async def cancel_all_orders(self) -> int:
        """Cancel all orders for this symbol"""
        return await self.trading.cancel_all_orders(self.symbol)
    
    async def get_balance(self, asset: str) -> Optional[float]:
        """Get balance for specific asset"""
        balance = await self.client.get_balance(asset)
        return balance.free if balance else 0.0
    
    async def calculate_position_risk(self) -> Dict[str, float]:
        """Calculate current position risk"""
        if self.position_size == 0:
            return {'risk': 0.0, 'percentage': 0.0}
        
        current_price = await self.market_data.get_current_price(self.symbol)
        stop_loss_pct = self.config.get('stop_loss_percentage', 0.02)
        
        if self.position_size > 0:  # Long position
            stop_price = self.entry_price * (1 - stop_loss_pct)
            risk = (self.entry_price - stop_price) * self.position_size
        else:  # Short position
            stop_price = self.entry_price * (1 + stop_loss_pct)
            risk = (stop_price - self.entry_price) * abs(self.position_size)
        
        portfolio_value = await self.trading.get_portfolio_value_usd()
        risk_percentage = (risk / portfolio_value * 100) if portfolio_value > 0 else 0
        
        return {
            'risk_amount': risk,
            'risk_percentage': risk_percentage,
            'stop_price': stop_price,
            'current_price': current_price
        }
    
    async def _log_performance_summary(self):
        """Log strategy performance summary"""
        if self.start_time:
            runtime = datetime.now() - self.start_time
            win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
            
            self.logger.info(f"=== Strategy Performance Summary ===")
            self.logger.info(f"Symbol: {self.symbol}")
            self.logger.info(f"Runtime: {runtime}")
            self.logger.info(f"Total Trades: {self.total_trades}")
            self.logger.info(f"Winning Trades: {self.winning_trades}")
            self.logger.info(f"Win Rate: {win_rate:.2f}%")
            self.logger.info(f"Total PnL: ${self.total_pnl:.2f}")
            self.logger.info(f"Signals Generated: {len(self.signal_history)}")
    
    # ==================== ADVANCED FEATURES ====================
    
    async def backtest_signal(self, signal: str, current_price: float) -> Dict[str, Any]:
        """Simulate signal execution for backtesting"""
        risk_amount = self.config.get('risk_amount', 100.0)
        stop_loss_pct = self.config.get('stop_loss_percentage', 0.02)
        take_profit_pct = self.config.get('take_profit_percentage', 0.04)
        
        if signal == 'BUY':
            quantity = risk_amount / current_price
            stop_price = current_price * (1 - stop_loss_pct)
            take_profit_price = current_price * (1 + take_profit_pct)
        else:
            quantity = risk_amount / current_price
            stop_price = current_price * (1 + stop_loss_pct)
            take_profit_price = current_price * (1 - take_profit_pct)
        
        return {
            'signal': signal,
            'entry_price': current_price,
            'quantity': quantity,
            'stop_price': stop_price,
            'take_profit_price': take_profit_price,
            'max_risk': risk_amount * stop_loss_pct,
            'max_profit': risk_amount * take_profit_pct
        }
    
    async def optimize_parameters(self, parameter_ranges: Dict[str, tuple]) -> Dict[str, Any]:
        """Optimize strategy parameters using historical data"""
        # This is a placeholder for parameter optimization
        # In a real implementation, you would run backtests with different parameters
        self.logger.info("Parameter optimization not implemented yet")
        return {}
    
    async def get_strategy_metrics(self) -> Dict[str, Any]:
        """Get comprehensive strategy metrics"""
        position_info = await self.get_current_position()
        risk_info = await self.calculate_position_risk()
        
        return {
            'symbol': self.symbol,
            'is_running': self.is_running,
            'position_size': self.position_size,
            'entry_price': self.entry_price,
            'last_signal': self.last_signal,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0,
            'total_pnl': self.total_pnl,
            'current_position': position_info,
            'current_risk': risk_info,
            'signals_generated': len(self.signal_history),
            'runtime': str(datetime.now() - self.start_time) if self.start_time else "0:00:00"
        }
