import logging
import sys
from typing import Optional
from datetime import datetime

def get_logger(name: str, level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """Get configured logger instance with async-safe formatting"""
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper()))
    
    # Custom formatter with async context
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create file handler: {e}")
    
    return logger

class AsyncLogger:
    """Async-aware logger wrapper for better performance"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def debug(self, msg: str, *args, **kwargs):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        if self.logger.isEnabledFor(logging.WARNING):
            self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        if self.logger.isEnabledFor(logging.ERROR):
            self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        if self.logger.isEnabledFor(logging.CRITICAL):
            self.logger.critical(msg, *args, **kwargs)

def get_async_logger(name: str, level: str = "INFO", log_file: Optional[str] = None) -> AsyncLogger:
    """Get async-aware logger instance"""
    logger = get_logger(name, level, log_file)
    return AsyncLogger(logger)
