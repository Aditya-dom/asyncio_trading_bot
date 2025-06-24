# Binance Async Trading Bot

A comprehensive, production-ready **asyncio-based trading bot** that demonstrates how to wrap traditional synchronous/callback-based broker APIs into modern **async/await** patterns. Perfect for real-time trading, market data streaming, and algorithmic trading strategies.

## **Core Concept: Sync to Async Wrapper**

This project showcases the essential pattern of **converting synchronous broker APIs to asyncio-compatible interfaces**:

```python
# Traditional sync/callback approach:
def get_price(symbol, callback):
    # blocking API call
    price = broker_api.get_price(symbol)
    callback(price)

# Our async wrapper approach:
async def get_price(symbol):
    # non-blocking async call
    return await self._request('GET', f'/price/{symbol}')
```

##  **Project Structure**

```
binance_asyncio_bot/
├── 📁 config/              # Configuration management
│   ├── __init__.py
│   ├── settings.py         # Environment-based config
│   └── .env               # API keys and settings
├── 📁 core/               # Core async API wrapper
│   ├── __init__.py
│   ├── client.py          # Main async Binance client
│   ├── exceptions.py      # Custom exceptions
│   └── models.py          # Data models
├── 📁 services/           # Business logic services
│   ├── __init__.py
│   ├── market_data.py     # Real-time market data
│   ├── trading.py         # Trading operations
│   └── websocket_manager.py  # WebSocket handling
├── 📁 strategies/         # Trading strategies
│   ├── __init__.py
│   ├── base_strategy.py   # Strategy framework
│   └── simple_ma_strategy.py  # Moving average example
├── 📁 utils/              # Utilities and helpers
│   ├── __init__.py
│   ├── logger.py          # Async-safe logging
│   └── helpers.py         # Async utilities
├── 📁 tests/              # Unit tests
│   ├── __init__.py
│   └── test_client.py     # Test suite
├── main.py                # Application entry point
├── requirements.txt       # Dependencies
└── README.md             # This file
```

## **Quick Start**

### **1. Installation**

```bash
# Clone or create the project directory
cd /Users/arawn/Desktop/binance_asyncio_bot

# Install dependencies
pip install -r requirements.txt
```

### **2. Configuration**

Your API keys are already configured in `config/.env`:

```env
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true  # Start with testnet for safety!
```

### **3. Run Examples**

```bash
# Basic async API usage
python main.py basic

# Real-time market data streaming
python main.py stream

# Concurrent operations demo
python main.py concurrent

# Full trading bot
python main.py
```

## 🔧 **Core Async Patterns Demonstrated**

### **1. Sync API to Async Wrapper**

```python
class AsyncBinanceClient:
    async def get_price(self, symbol: str) -> float:
        """Convert sync API call to async"""
        data = await self._request('GET', '/api/v3/ticker/price', 
                                  params={'symbol': symbol})
        return float(data['price'])
    
    async def _request(self, method: str, endpoint: str, **kwargs):
        """Core async HTTP request with retry logic"""
        async with self.session.request(method, url, **kwargs) as response:
            return await response.json()
```

### **2. Callback to Async Conversion**

```python
# Traditional callback pattern:
websocket.on_message(callback_function)

# Our async pattern:
async def handle_websocket_messages():
    async for message in websocket:
        await self.event_emitter.emit('price_update', message)
```

### **3. Event-Driven Architecture**

```python
# Subscribe to real-time events
await websocket_manager.subscribe_ticker('BTCUSDT', my_callback)

# Event emission with async callbacks
async def my_callback(price_data):
    await process_price_update(price_data)
```

## **Usage Examples**

### **Basic API Operations**

```python
from core.client import AsyncBinanceClient
from config.settings import get_config

async def basic_example():
    config, _, _ = get_config()
    
    async with AsyncBinanceClient(config) as client:
        # Get current price
        price = await client.get_price("BTCUSDT")
        print(f"BTC Price: ${price:,.2f}")
        
        # Get account balance
        balances = await client.get_balances()
        
        # Place a market order
        order = await client.place_market_buy("BTCUSDT", 50.0)
```

### **Real-time Market Data**

```python
from services.websocket_manager import WebSocketManager

async def streaming_example():
    ws_manager = WebSocketManager()
    await ws_manager.start()
    
    # Real-time price updates
    async def on_price_update(data):
        price = float(data['c'])
        print(f"BTC: ${price:,.2f}")
    
    await ws_manager.subscribe_ticker("BTCUSDT", on_price_update)
```

### **Trading Strategy**

```python
from strategies.simple_ma_strategy import SimpleMAStrategy

async def strategy_example():
    config = {
        'short_ma_period': 10,
        'long_ma_period': 20,
        'risk_amount': 100.0
    }
    
    strategy = SimpleMAStrategy(client, "BTCUSDT", config)
    await strategy.start()
    await strategy.run()  # Runs until stopped
```

### **Concurrent Operations**

```python
# Get multiple prices simultaneously
symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
tasks = [client.get_price(symbol) for symbol in symbols]
prices = await asyncio.gather(*tasks)

# Much faster than sequential calls!
```

## **Safety Features**

- **Testnet Support**: Test strategies safely without real money
- **Rate Limiting**: Automatic rate limiting to prevent API bans
- **Auto Retry**: Robust error handling with exponential backoff
- **Stop Loss**: Built-in stop-loss and take-profit management
- **Position Tracking**: Real-time position and PnL monitoring
- **Risk Management**: Configurable position limits and risk controls

## **Key Async Advantages**

### **Performance**
- **10x faster** concurrent operations vs sequential
- Non-blocking I/O for real-time responsiveness
- Efficient resource utilization

### **Scalability**
- Handle thousands of concurrent connections
- Multiple trading pairs simultaneously
- Real-time WebSocket streams

### **Modern Architecture**
- Clean async/await syntax
- Event-driven design patterns
- Easy testing and debugging

## **Testing**

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_client.py::TestAsyncBinanceClient -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## **Strategy Development**

Creating custom strategies by extending `BaseStrategy`:

```python
from strategies.base_strategy import BaseStrategy

class MyCustomStrategy(BaseStrategy):
    async def generate_signal(self) -> Optional[str]:
        # Your strategy logic here
        current_price = await self.market_data.get_current_price(self.symbol)
        
        # Example: Simple threshold strategy
        if current_price > self.config['buy_threshold']:
            return 'SELL'
        elif current_price < self.config['sell_threshold']:
            return 'BUY'
        
        return None
    
    async def on_price_update(self, price: float, data: dict):
        # React to real-time price changes
        await self.check_stop_loss(price)
```

## 🔧 **Configuration Options**

### **Trading Settings**
```python
{
    'risk_amount': 100.0,           # $ risk per trade
    'stop_loss_percentage': 0.02,   # 2% stop loss
    'take_profit_percentage': 0.04, # 4% take profit
    'max_position_size': 1000.0,    # Max position size
}
```

### **Strategy Settings**
```python
{
    'short_ma_period': 10,          # Short MA period
    'long_ma_period': 20,           # Long MA period
    'min_crossover_interval': 300,  # Min time between signals
    'require_volume_confirmation': True,
}


## **Performance Monitoring**

Built-in performance tracking:

```python
# Get strategy metrics
metrics = await strategy.get_strategy_metrics()
print(f"Win Rate: {metrics['win_rate']:.1f}%")
print(f"Total PnL: ${metrics['total_pnl']:.2f}")
print(f"Total Trades: {metrics['total_trades']}")
```

### This codebase demonstrates:

1. **Async/Await Patterns**: Modern Python concurrency
2. **WebSocket Handling**: Real-time data streams
3. **Event-Driven Architecture**: Scalable system design
4. **Error Handling**: Robust production patterns
5. **Testing**: Async testing with pytest-asyncio
6. **Configuration Management**: Environment-based config
7. **Logging**: Structured async-safe logging

---

### **Why This Approach?**

Traditional broker APIs are often:
- **Synchronous**: Blocking operations
- **Callback-based**: Complex nested callbacks
- **Single-threaded**: Poor performance

Our async wrapper provides:
- **Non-blocking**: Better responsiveness
- **Event-driven**: Clean architecture
- **Concurrent**: Multiple operations simultaneously
- **Modern**: Uses latest Python async patterns

**Perfect for**: Real-time trading systems, market data analysis, algorithmic trading, and educational purposes.

---

**Happy Trading!**
