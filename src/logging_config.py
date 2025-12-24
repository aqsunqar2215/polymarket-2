from __future__ import annotations

import logging
import sys
from typing import Literal
import structlog

# ANSI цвета для терминала
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[101m"

def colored_log_formatter(logger, method_name, event_dict):
    """Форматер для КОНСОЛИ (с цветами)"""
    # Создаем копию, чтобы не портить данные для других процессоров
    event_dict_copy = event_dict.copy()
    
    timestamp = event_dict_copy.pop("timestamp", "")
    level = event_dict_copy.pop("level", "info").upper()
    message = event_dict_copy.pop("event", "") # В structlog сообщение обычно в ключе 'event'
    logger_name = event_dict_copy.pop("logger", "").split(".")[-1]
    
    # Выбор цвета по уровню
    if level == "ERROR":
        level_color = Colors.BG_RED + Colors.WHITE
    elif level == "WARNING":
        level_color = Colors.YELLOW
    elif level == "INFO":
        level_color = Colors.GREEN
    elif level == "DEBUG":
        level_color = Colors.CYAN
    else:
        level_color = Colors.WHITE
    
    formatted = (
        f"{Colors.CYAN}{timestamp}{Colors.RESET} "
        f"{level_color}[{level}]{Colors.RESET} "
        f"{Colors.BLUE}{logger_name}{Colors.RESET} "
        f"{Colors.WHITE}{message}{Colors.RESET}"
    )
    
    if event_dict_copy:
        formatted += "\n"
        for key, value in event_dict_copy.items():
            formatted += f"  {Colors.MAGENTA}{key}{Colors.RESET}={Colors.YELLOW}{value}{Colors.RESET}\n"
    
    return formatted

def configure_logging(level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO") -> None:
    # 1. Настройка стандартного логгера
    # StreamHandler — для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    
    # FileHandler — для записи в файл (без цветов)
    file_handler = logging.FileHandler("bot.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[console_handler, file_handler]
    )

    # 2. Настройка structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Этот процессор делает лог цветным только для консоли
            colored_log_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )