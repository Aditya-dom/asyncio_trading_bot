import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class BinanceConfig:
    """Binance API configuration"""
    api_key: str
    api_secret: str
    base_url: str = "https://api.binance.com"
    testnet_url: str = "https://testnet.binance.vision"
    testnet: bool = False
    max_retries: int = 3
    timeout: int = 30
    rate_limit_delay: float = 0.1

@dataclass
class TradingConfig:
    """Trading configuration"""
    default_symbol: str = "BTCUSDT"
    max_position_size: float = 1000.0
    risk_percentage: float = 0.02
    stop_loss_percentage: float = 0.02
    take_profit_percentage: float = 0.04

@dataclass
class AppConfig:
    """Application configuration"""
    debug: bool = False
    log_level: str = "INFO"
    log_file: str = "trading_bot.log"

def get_config() -> tuple[BinanceConfig, TradingConfig, AppConfig]:
    """Get configuration from environment variables"""
    binance_config = BinanceConfig(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "false").lower() == "true"
    )
    
    # Use testnet URL if testnet is enabled
    if binance_config.testnet:
        binance_config.base_url = binance_config.testnet_url
    
    trading_config = TradingConfig(
        default_symbol=os.getenv("DEFAULT_SYMBOL", "BTCUSDT"),
        max_position_size=float(os.getenv("MAX_POSITION_SIZE", "1000.0")),
        risk_percentage=float(os.getenv("RISK_PERCENTAGE", "0.02"))
    )
    
    app_config = AppConfig(
        debug=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE", "trading_bot.log")
    )
    
    return binance_config, trading_config, app_config
