#!/usr/bin/env python3

"""
Launch script for the Binance Async Trading Bot
Handles proper module imports and provides examples
"""

import sys
import os
import asyncio

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def main():
    """Main entry point with proper import handling"""
    
    # Import modules after path setup
    from config.settings import get_config
    from core.client import AsyncBinanceClient
    from strategies.simple_ma_strategy import SimpleMAStrategy
    from utils.logger import get_logger
    
    print("🚀 Binance Async Trading Bot")
    print("=" * 50)
    
    # Check command line arguments
    if len(sys.argv) > 1:
        example = sys.argv[1].lower()
        
        if example == "basic":
            await example_basic_api_usage()
        elif example == "stream":
            await example_market_data_streaming()
        elif example == "concurrent":
            await example_concurrent_operations()
        elif example == "test":
            await test_connection()
        else:
            print(f"❌ Unknown example: {example}")
            print("📖 Available examples:")
            print("   python run.py basic      - Basic API usage")
            print("   python run.py stream     - WebSocket streaming")
            print("   python run.py concurrent - Concurrent operations")
            print("   python run.py test       - Test connection")
            print("   python run.py           - Full trading bot")
    else:
        # Run the full trading bot
        await run_full_bot()

async def test_connection():
    """Test basic connection to Binance API"""
    print("🔍 Testing Binance API Connection...")
    
    try:
        from config.settings import get_config
        from core.client import AsyncBinanceClient
        
        binance_config, _, _ = get_config()
        
        async with AsyncBinanceClient(binance_config) as client:
            # Test ping
            if await client.ping():
                print("✅ API Ping: Success")
            else:
                print("❌ API Ping: Failed")
                return
            
            # Test server time
            server_time = await client.get_server_time()
            print(f"✅ Server Time: {server_time}")
            
            # Test price fetch
            price = await client.get_price("BTCUSDT")
            print(f"✅ BTC Price: ${price:,.2f}")
            
            print("🎉 Connection test successful!")
            
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Check your internet connection")
        print("2. Verify API keys in config/.env")
        print("3. Make sure you're using testnet (BINANCE_TESTNET=true)")

async def example_basic_api_usage():
    """Example of basic async API usage"""
    print("🔗 Basic Async API Usage Example")
    print("-" * 30)
    
    try:
        from config.settings import get_config
        from core.client import AsyncBinanceClient
        
        binance_config, _, _ = get_config()
        
        async with AsyncBinanceClient(binance_config) as client:
            print("📡 Getting server time...")
            server_time = await client.get_server_time()
            print(f"   Server time: {server_time}")
            
            print("💰 Getting BTC price...")
            price = await client.get_price("BTCUSDT")
            print(f"   BTC Price: ${price:,.2f}")
            
            print("📊 Getting ticker information...")
            ticker = await client.get_ticker("BTCUSDT")
            print(f"   BTC 24h Change: {ticker.change_percent:+.2f}%")
            print(f"   Volume: {ticker.volume:,.0f}")
            
            print("💳 Getting account balances...")
            balances = await client.get_balances()
            print(f"   Found {len(balances)} assets with balance")
            
            if balances:
                for balance in balances[:3]:  # Show first 3
                    print(f"   {balance.asset}: {balance.free:.6f}")
            
        print("✅ Basic API example completed!")
        
    except Exception as e:
        print(f"❌ Error in basic example: {e}")

async def example_market_data_streaming():
    """Example of real-time market data streaming"""
    print("📊 Market Data Streaming Example")
    print("-" * 30)
    
    try:
        from services.websocket_manager import WebSocketManager
        
        ws_manager = WebSocketManager()
        await ws_manager.start()
        
        print("🔄 Starting real-time price stream for 10 seconds...")
        
        # Price update counter
        update_count = 0
        
        async def on_price_update(data):
            nonlocal update_count
            update_count += 1
            
            symbol = data.get('s')
            price = float(data.get('c', 0))
            change = float(data.get('P', 0))
            
            print(f"   #{update_count}: {symbol}: ${price:,.2f} ({change:+.2f}%)")
        
        # Subscribe to ticker updates
        await ws_manager.subscribe_ticker("BTCUSDT", on_price_update)
        
        # Let it run for 10 seconds
        await asyncio.sleep(10)
        
        await ws_manager.stop()
        print(f"✅ Streaming completed! Received {update_count} price updates")
        
    except Exception as e:
        print(f"❌ Error in streaming example: {e}")

async def example_concurrent_operations():
    """Example of concurrent async operations"""
    print("⚡ Concurrent Operations Example")
    print("-" * 30)
    
    try:
        from config.settings import get_config
        from core.client import AsyncBinanceClient
        import time
        
        binance_config, _, _ = get_config()
        
        async with AsyncBinanceClient(binance_config) as client:
            symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
            
            print(f"🚀 Getting prices for {len(symbols)} symbols concurrently...")
            
            # Measure time for concurrent approach
            start_time = time.time()
            
            # Get all prices concurrently
            tasks = [client.get_price(symbol) for symbol in symbols]
            prices = await asyncio.gather(*tasks)
            
            concurrent_time = time.time() - start_time
            
            print("💰 Results:")
            for symbol, price in zip(symbols, prices):
                print(f"   {symbol}: ${price:,.2f}")
            
            print(f"⚡ Concurrent fetch took: {concurrent_time:.2f} seconds")
            print(f"📈 That's ~{len(symbols)/concurrent_time:.1f} requests per second!")
            
            # Compare with sequential approach (simulation)
            estimated_sequential = len(symbols) * 0.2  # Assume 200ms per request
            print(f"🐌 Sequential would take ~{estimated_sequential:.1f} seconds")
            print(f"🚀 Speedup: {estimated_sequential/concurrent_time:.1f}x faster!")
        
        print("✅ Concurrent operations example completed!")
        
    except Exception as e:
        print(f"❌ Error in concurrent example: {e}")

async def run_full_bot():
    """Run the full trading bot"""
    print("🤖 Starting Full Trading Bot")
    print("-" * 30)
    
    try:
        # Import the full bot class
        from main import TradingBot
        
        print("⚠️  WARNING: This will start a live trading bot!")
        print("📝 Make sure BINANCE_TESTNET=true in your config/.env file")
        
        # Ask for confirmation
        if len(sys.argv) <= 1:
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                print("👋 Bot startup cancelled")
                return
        
        bot = TradingBot()
        await bot.run()
        
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running full bot: {e}")

class TradingBot:
    """Simplified bot class for the launcher"""
    
    def __init__(self):
        from config.settings import get_config
        from utils.logger import get_logger
        
        self.binance_config, self.trading_config, self.app_config = get_config()
        self.logger = get_logger(__name__, self.app_config.log_level)
        self.client = None
        self.strategy = None
        self.running = False
    
    async def run(self):
        """Run a simplified version of the bot"""
        from core.client import AsyncBinanceClient
        from strategies.simple_ma_strategy import SimpleMAStrategy
        
        try:
            print("🚀 Initializing trading bot...")
            
            # Initialize client
            self.client = AsyncBinanceClient(self.binance_config)
            await self.client.connect()
            
            # Test connection
            price = await self.client.get_price(self.trading_config.default_symbol)
            print(f"📊 {self.trading_config.default_symbol}: ${price:,.2f}")
            
            # Initialize strategy
            strategy_config = {
                'short_ma_period': 5,
                'long_ma_period': 10,
                'risk_amount': 10.0,  # Small risk for testing
                'stop_loss_percentage': 0.02,
                'take_profit_percentage': 0.04,
                'loop_interval': 5.0,  # 5 second intervals
            }
            
            self.strategy = SimpleMAStrategy(
                self.client,
                self.trading_config.default_symbol,
                strategy_config
            )
            
            await self.strategy.start()
            print("✅ Strategy started successfully!")
            
            print("🔄 Running strategy (Ctrl+C to stop)...")
            print("📈 Monitoring for MA crossover signals...")
            
            # Run for a limited time or until interrupted
            self.running = True
            
            # Create tasks
            strategy_task = asyncio.create_task(self.strategy.run())
            monitor_task = asyncio.create_task(self._monitor_loop())
            
            # Wait for interruption
            try:
                await asyncio.gather(strategy_task, monitor_task)
            except KeyboardInterrupt:
                print("\n🛑 Stopping bot...")
                self.running = False
                
                # Cancel tasks
                strategy_task.cancel()
                monitor_task.cancel()
                
                try:
                    await asyncio.gather(strategy_task, monitor_task, return_exceptions=True)
                except:
                    pass
            
        finally:
            if self.strategy:
                await self.strategy.stop()
            if self.client:
                await self.client.close()
            print("✅ Bot stopped gracefully")
    
    async def _monitor_loop(self):
        """Simple monitoring loop"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                
                if self.strategy:
                    metrics = await self.strategy.get_strategy_metrics()
                    ma_status = await self.strategy.get_ma_status()
                    
                    print(f"📊 Status: Signals: {metrics['signals_generated']} | "
                          f"MA Spread: {ma_status['ma_spread_percent']:.2f}% | "
                          f"Runtime: {metrics['runtime']}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️  Monitor error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)
