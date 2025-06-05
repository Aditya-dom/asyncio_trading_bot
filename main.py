import asyncio
import signal
import sys
from datetime import datetime

# Add current directory to path for imports
sys.path.append('.')

from config.settings import get_config
from core.client import AsyncBinanceClient
from strategies.simple_ma_strategy import SimpleMAStrategy
from utils.logger import get_logger

class TradingBot:
    """
    Main trading bot application with full async architecture
    Demonstrates complete async wrapper for broker API integration
    """
    
    def __init__(self):
        # Load configuration
        self.binance_config, self.trading_config, self.app_config = get_config()
        self.logger = get_logger(__name__, self.app_config.log_level, self.app_config.log_file)
        
        # Core components
        self.client = None
        self.strategy = None
        self.running = False
        
        # Performance tracking
        self.start_time = None
        self.total_runtime = None
    
    async def start(self):
        """
        Start the trading bot with full async initialization
        This demonstrates the async wrapper pattern for broker APIs
        """
        try:
            self.start_time = datetime.now()
            self.logger.info("🚀 Starting Async Trading Bot...")
            
            # Validate configuration
            if not self.binance_config.api_key or not self.binance_config.api_secret:
                raise ValueError("API credentials not configured. Check your .env file.")
            
            # Initialize async Binance client (wrapper around sync/callback API)
            self.client = AsyncBinanceClient(self.binance_config)
            await self.client.connect()
            
            # Test connection and log account info
            await self._test_connection()
            
            # Initialize and start strategy
            await self._initialize_strategy()
            
            self.running = True
            self.logger.info("✅ Trading Bot started successfully")
            
            # Start main bot loop
            await self._run_main_loop()
            
        except Exception as e:
            self.logger.error(f"❌ Error starting trading bot: {e}")
            await self.stop()
            raise
    
    async def _test_connection(self):
        """Test API connection and log account information"""
        try:
            # Test basic connectivity
            if not await self.client.ping():
                raise ConnectionError("Cannot ping Binance API")
            
            # Get server time to verify connection
            server_time = await self.client.get_server_time()
            self.logger.info(f"📡 Connected to Binance API (Server time: {server_time})")
            
            # Get account information
            account_info = await self.client.get_account_info()
            account_type = account_info.get('accountType', 'Unknown')
            
            if self.binance_config.testnet:
                self.logger.info("🧪 Using TESTNET - No real money will be used")
            
            self.logger.info(f"👤 Account Type: {account_type}")
            
            # Get and log balances
            balances = await self.client.get_balances()
            significant_balances = [b for b in balances if b.total > 0.001]
            
            if significant_balances:
                self.logger.info("💰 Account Balances:")
                for balance in significant_balances[:5]:  # Show top 5
                    self.logger.info(f"   {balance.asset}: {balance.free:.6f} (locked: {balance.locked:.6f})")
            else:
                self.logger.warning("⚠️  No significant balances found")
            
            # Test market data access
            ticker = await self.client.get_ticker(self.trading_config.default_symbol)
            self.logger.info(f"📊 {ticker.symbol} Price: ${ticker.price:.2f} ({ticker.change_percent:+.2f}%)")
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            raise
    
    async def _initialize_strategy(self):
        """Initialize and configure trading strategy"""
        try:
            # Strategy configuration
            strategy_config = {
                # Moving Average settings
                'short_ma_period': 10,
                'long_ma_period': 20,
                'kline_interval': '1m',
                
                # Risk management
                'risk_amount': 50.0,  # Risk $50 per trade
                'stop_loss_percentage': 0.02,  # 2% stop loss
                'take_profit_percentage': 0.04,  # 4% take profit
                
                # Signal filters
                'require_volume_confirmation': False,
                'require_trend_confirmation': True,
                'require_price_action_confirmation': False,
                'min_crossover_interval': 300,  # 5 minutes between signals
                
                # Performance settings
                'loop_interval': 1.0,  # 1 second strategy loop
            }
            
            # Create strategy instance
            self.strategy = SimpleMAStrategy(
                self.client,
                self.trading_config.default_symbol,
                strategy_config
            )
            
            # Start strategy
            await self.strategy.start()
            
            # Log strategy status
            ma_status = await self.strategy.get_ma_status()
            self.logger.info(f"📈 Strategy initialized:")
            self.logger.info(f"   Symbol: {self.strategy.symbol}")
            self.logger.info(f"   Short MA ({ma_status['short_period']}): {ma_status['short_ma']:.4f}")
            self.logger.info(f"   Long MA ({ma_status['long_period']}): {ma_status['long_ma']:.4f}")
            self.logger.info(f"   Risk per trade: ${strategy_config['risk_amount']}")
            
        except Exception as e:
            self.logger.error(f"Strategy initialization failed: {e}")
            raise
    
    async def _run_main_loop(self):
        """
        Main bot loop - coordinates all async operations
        This is the heart of the async wrapper pattern
        """
        self.logger.info("🔄 Starting main bot loop...")
        
        # Start strategy in background
        strategy_task = asyncio.create_task(self.strategy.run())
        
        # Start monitoring tasks
        monitor_task = asyncio.create_task(self._monitor_performance())
        status_task = asyncio.create_task(self._periodic_status_update())
        
        try:
            # Wait for any task to complete (which should be never in normal operation)
            done, pending = await asyncio.wait(
                [strategy_task, monitor_task, status_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
        except asyncio.CancelledError:
            self.logger.info("Main loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
        finally:
            # Ensure all tasks are cleaned up
            for task in [strategy_task, monitor_task, status_task]:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
    
    async def _monitor_performance(self):
        """Monitor bot performance and log metrics"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Update every 5 minutes
                
                if self.strategy:
                    metrics = await self.strategy.get_strategy_metrics()
                    
                    self.logger.info(f"📊 Performance Update:")
                    self.logger.info(f"   Runtime: {metrics['runtime']}")
                    self.logger.info(f"   Total Trades: {metrics['total_trades']}")
                    self.logger.info(f"   Win Rate: {metrics['win_rate']:.1f}%")
                    self.logger.info(f"   Total PnL: ${metrics['total_pnl']:.2f}")
                    self.logger.info(f"   Position: {metrics['position_size']:.6f}")
                    self.logger.info(f"   Signals Generated: {metrics['signals_generated']}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _periodic_status_update(self):
        """Periodic status updates and health checks"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Update every minute
                
                # Get current price
                current_price = await self.client.get_price(self.trading_config.default_symbol)
                
                # Get strategy health
                if self.strategy:
                    health = await self.strategy.get_strategy_health()
                    ma_status = await self.strategy.get_ma_status()
                    
                    self.logger.debug(f"💚 Status: {self.trading_config.default_symbol} @ ${current_price:.2f} | "
                                    f"Health: {health['health_score']}/100 | "
                                    f"MA Spread: {ma_status['ma_spread_percent']:.2f}%")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in status update: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def stop(self):
        """
        Stop the trading bot gracefully
        Demonstrates proper async cleanup patterns
        """
        self.logger.info("🛑 Stopping Trading Bot...")
        self.running = False
        
        try:
            # Stop strategy first
            if self.strategy:
                await self.strategy.stop()
                self.logger.info("✅ Strategy stopped")
            
            # Close client connection
            if self.client:
                await self.client.close()
                self.logger.info("✅ API connection closed")
            
            # Calculate total runtime
            if self.start_time:
                self.total_runtime = datetime.now() - self.start_time
                self.logger.info(f"📈 Total runtime: {self.total_runtime}")
            
            self.logger.info("✅ Trading Bot stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def run(self):
        """
        Run the trading bot with graceful shutdown handling
        This is the main entry point demonstrating async patterns
        """
        # Setup signal handlers for graceful shutdown
        def signal_handler():
            self.logger.info("📡 Received shutdown signal")
            asyncio.create_task(self.stop())
        
        # Register signal handlers
        if sys.platform != 'win32':  # Unix-like systems
            signal.signal(signal.SIGINT, lambda s, f: signal_handler())
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
        
        try:
            await self.start()
        except KeyboardInterrupt:
            self.logger.info("🔄 KeyboardInterrupt received")
            await self.stop()
        except Exception as e:
            self.logger.error(f"💥 Unexpected error: {e}")
            await self.stop()
            raise

# ==================== STANDALONE EXAMPLES ====================

async def example_basic_api_usage():
    """Example of basic async API usage"""
    print("🔗 Basic Async API Usage Example")
    
    # Load config
    binance_config, _, _ = get_config()
    
    # Use async context manager for automatic cleanup
    async with AsyncBinanceClient(binance_config) as client:
        # Get server time
        server_time = await client.get_server_time()
        print(f"Server time: {server_time}")
        
        # Get current price
        price = await client.get_price("BTCUSDT")
        print(f"BTC Price: ${price:,.2f}")
        
        # Get account balances
        balances = await client.get_balances()
        print(f"Found {len(balances)} assets with balance")
        
        # Get ticker information
        ticker = await client.get_ticker("BTCUSDT")
        print(f"BTC 24h Change: {ticker.change_percent:+.2f}%")

async def example_market_data_streaming():
    """Example of real-time market data streaming"""
    print("📊 Market Data Streaming Example")
    
    from services.websocket_manager import WebSocketManager
    
    ws_manager = WebSocketManager()
    await ws_manager.start()
    
    # Price update handler
    async def on_price_update(data):
        symbol = data.get('s')
        price = float(data.get('c', 0))
        change = float(data.get('P', 0))
        print(f"{symbol}: ${price:,.2f} ({change:+.2f}%)")
    
    # Subscribe to ticker updates
    await ws_manager.subscribe_ticker("BTCUSDT", on_price_update)
    
    # Let it run for 10 seconds
    await asyncio.sleep(10)
    
    await ws_manager.stop()

async def example_concurrent_operations():
    """Example of concurrent async operations"""
    print("⚡ Concurrent Operations Example")
    
    binance_config, _, _ = get_config()
    
    async with AsyncBinanceClient(binance_config) as client:
        # Get multiple prices concurrently
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT"]
        
        # Traditional sequential approach would be slow:
        # for symbol in symbols:
        #     price = await client.get_price(symbol)
        
        # Async concurrent approach is much faster:
        tasks = [client.get_price(symbol) for symbol in symbols]
        prices = await asyncio.gather(*tasks)
        
        for symbol, price in zip(symbols, prices):
            print(f"{symbol}: ${price:,.2f}")

# ==================== MAIN ENTRY POINT ====================

async def main():
    """Main async entry point"""
    print("🚀 Binance Async Trading Bot")
    print("=" * 50)
    
    # Check if we should run examples or the full bot
    if len(sys.argv) > 1:
        example = sys.argv[1]
        
        if example == "basic":
            await example_basic_api_usage()
        elif example == "stream":
            await example_market_data_streaming()
        elif example == "concurrent":
            await example_concurrent_operations()
        else:
            print(f"Unknown example: {example}")
            print("Available examples: basic, stream, concurrent")
    else:
        # Run the full trading bot
        bot = TradingBot()
        await bot.run()

if __name__ == "__main__":
    try:
        # Run the async main function
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutdown completed")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)
