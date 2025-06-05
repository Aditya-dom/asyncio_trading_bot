import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.client import AsyncBinanceClient
from core.models import OrderSide, OrderType, Ticker
from core.exceptions import BinanceAPIError, RateLimitError
from config.settings import BinanceConfig

@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return BinanceConfig(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://testnet.binance.vision",
        testnet=True
    )

@pytest.fixture
async def client(mock_config):
    """Create test client"""
    client = AsyncBinanceClient(mock_config)
    yield client
    await client.close()

class TestAsyncBinanceClient:
    """Test cases for AsyncBinanceClient"""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, mock_config):
        """Test client initialization"""
        client = AsyncBinanceClient(mock_config)
        assert client.config == mock_config
        assert client.session is None
        assert not client._last_request_time
    
    @pytest.mark.asyncio
    async def test_connect_and_close(self, client):
        """Test connection lifecycle"""
        # Test connection
        await client.connect()
        assert client.session is not None
        
        # Test close
        await client.close()
        assert client.session is None
    
    @pytest.mark.asyncio
    async def test_signature_generation(self, client):
        """Test HMAC signature generation"""
        params = {'symbol': 'BTCUSDT', 'timestamp': 1234567890}
        signature = client._generate_signature(params)
        
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest length
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, client):
        """Test rate limiting functionality"""
        import time
        
        start_time = time.time()
        await client._rate_limit()
        await client._rate_limit()
        end_time = time.time()
        
        # Should take at least the rate limit delay
        assert end_time - start_time >= client.config.rate_limit_delay
    
    @pytest.mark.asyncio
    async def test_get_server_time_success(self, client):
        """Test successful server time request"""
        mock_response = {'serverTime': 1234567890}
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            server_time = await client.get_server_time()
            assert server_time == 1234567890
            mock_request.assert_called_once_with('GET', '/api/v3/time')
    
    @pytest.mark.asyncio
    async def test_get_ticker_success(self, client):
        """Test successful ticker request"""
        mock_response = {
            'symbol': 'BTCUSDT',
            'lastPrice': '50000.00',
            'priceChangePercent': '2.5',
            'volume': '1000.0',
            'closeTime': 1234567890000
        }
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            ticker = await client.get_ticker('BTCUSDT')
            
            assert isinstance(ticker, Ticker)
            assert ticker.symbol == 'BTCUSDT'
            assert ticker.price == 50000.0
            assert ticker.change_percent == 2.5
    
    @pytest.mark.asyncio
    async def test_get_price_success(self, client):
        """Test successful price request"""
        mock_response = {'price': '50000.00'}
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            price = await client.get_price('BTCUSDT')
            assert price == 50000.0
    
    @pytest.mark.asyncio
    async def test_place_market_buy_success(self, client):
        """Test successful market buy order"""
        mock_response = {
            'symbol': 'BTCUSDT',
            'orderId': 123456,
            'clientOrderId': 'test_order',
            'side': 'BUY',
            'type': 'MARKET',
            'status': 'FILLED',
            'origQty': '0.001',
            'price': '0.00000000',
            'executedQty': '0.001',
            'cummulativeQuoteQty': '50.00',
            'time': 1234567890000
        }
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            order = await client.place_market_buy('BTCUSDT', 50.0)
            
            assert order.symbol == 'BTCUSDT'
            assert order.side == OrderSide.BUY
            assert order.type == OrderType.MARKET
    
    @pytest.mark.asyncio
    async def test_place_limit_order_success(self, client):
        """Test successful limit order"""
        mock_response = {
            'symbol': 'BTCUSDT',
            'orderId': 123456,
            'clientOrderId': 'test_order',
            'side': 'BUY',
            'type': 'LIMIT',
            'status': 'NEW',
            'origQty': '0.001',
            'price': '49000.00',
            'executedQty': '0.000',
            'cummulativeQuoteQty': '0.00',
            'time': 1234567890000
        }
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            order = await client.place_limit_order('BTCUSDT', OrderSide.BUY, 0.001, 49000.0)
            
            assert order.symbol == 'BTCUSDT'
            assert order.side == OrderSide.BUY
            assert order.type == OrderType.LIMIT
            assert order.price == 49000.0
    
    @pytest.mark.asyncio
    async def test_error_handling(self, client):
        """Test error handling"""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = BinanceAPIError("Test error", 400)
            
            with pytest.raises(BinanceAPIError):
                await client.get_server_time()
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, client):
        """Test rate limit error handling"""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = RateLimitError("Rate limit exceeded")
            
            with pytest.raises(RateLimitError):
                await client.get_server_time()

class TestMarketDataService:
    """Test cases for MarketDataService"""
    
    @pytest.mark.asyncio
    async def test_price_monitoring(self, mock_config):
        """Test price monitoring functionality"""
        from services.market_data import MarketDataService
        
        # Mock client
        mock_client = AsyncMock()
        mock_client.get_price.return_value = 50000.0
        
        service = MarketDataService(mock_client)
        
        # Test callback
        price_updates = []
        
        async def price_callback(symbol, current_price, last_price):
            price_updates.append((symbol, current_price, last_price))
        
        # Subscribe to price updates
        await service.subscribe_to_price_updates('BTCUSDT', price_callback, 0.1)
        
        # Let it run briefly
        await asyncio.sleep(0.3)
        
        # Stop monitoring
        await service.stop()
        
        # Should have received some price updates
        assert len(price_updates) >= 1

class TestTradingService:
    """Test cases for TradingService"""
    
    @pytest.mark.asyncio
    async def test_balance_validation(self, mock_config):
        """Test balance validation"""
        from services.trading import TradingService
        from core.models import Balance
        
        # Mock client
        mock_client = AsyncMock()
        mock_balance = Balance(asset='USDT', free=100.0, locked=0.0)
        mock_client.get_balance.return_value = mock_balance
        
        service = TradingService(mock_client)
        
        # Test sufficient balance
        result = await service._validate_balance('BTCUSDT', OrderSide.BUY, quote_quantity=50.0)
        assert result is True
        
        # Test insufficient balance
        result = await service._validate_balance('BTCUSDT', OrderSide.BUY, quote_quantity=150.0)
        assert result is False

class TestWebSocketManager:
    """Test cases for WebSocketManager"""
    
    @pytest.mark.asyncio
    async def test_websocket_initialization(self):
        """Test WebSocket manager initialization"""
        from services.websocket_manager import WebSocketManager
        
        ws_manager = WebSocketManager()
        assert not ws_manager.running
        assert len(ws_manager.connections) == 0
        
        await ws_manager.start()
        assert ws_manager.running
        
        await ws_manager.stop()
        assert not ws_manager.running

class TestSimpleMAStrategy:
    """Test cases for SimpleMAStrategy"""
    
    @pytest.mark.asyncio
    async def test_strategy_initialization(self, mock_config):
        """Test strategy initialization"""
        from strategies.simple_ma_strategy import SimpleMAStrategy
        
        # Mock client
        mock_client = AsyncMock()
        
        config = {
            'short_ma_period': 5,
            'long_ma_period': 10,
            'risk_amount': 100.0
        }
        
        strategy = SimpleMAStrategy(mock_client, 'BTCUSDT', config)
        
        assert strategy.symbol == 'BTCUSDT'
        assert strategy.short_period == 5
        assert strategy.long_period == 10
        assert not strategy.is_running
    
    @pytest.mark.asyncio
    async def test_ma_calculation(self, mock_config):
        """Test moving average calculation"""
        from strategies.simple_ma_strategy import SimpleMAStrategy
        
        mock_client = AsyncMock()
        config = {'short_ma_period': 3, 'long_ma_period': 5}
        
        strategy = SimpleMAStrategy(mock_client, 'BTCUSDT', config)
        
        # Add test price history
        strategy.price_history = [100, 101, 102, 103, 104]
        
        await strategy._update_moving_averages()
        
        # Check MA calculations
        expected_short_ma = (102 + 103 + 104) / 3  # Last 3 prices
        expected_long_ma = (100 + 101 + 102 + 103 + 104) / 5  # All 5 prices
        
        assert abs(strategy.current_short_ma - expected_short_ma) < 0.001
        assert abs(strategy.current_long_ma - expected_long_ma) < 0.001

# Test fixtures and utilities
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
