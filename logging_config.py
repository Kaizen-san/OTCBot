import logging
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')

LOGGING_CONFIG = {
    "version": 1,

    # we still want to receive any warnings or errors from discord or other libs
    "disable_existing_loggers": False,

    "formatters": {
        "detailed": {
            "format": "%(name)s | %(asctime)s.%(msecs)03d | %(levelname)s | %(module)s - %(funcName)s | %(message)s",
            "datefmt": "%d-%m-%Y %H:%M:%S"
        }
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            # this includes errors too
            "stream": "ext://sys.stdout",
            "filters": ["stdout_filter"]
        },
        "err_console": {
            "class": "logging.StreamHandler",
            "level": "WARNING",
            "formatter": "detailed",
            # this only includes errors
            "stream": "ext://sys.stderr",
            "filters": ["stderr_filter"]
        },
        "json_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "filename": "logs/debug_log.log",
            "formatter": "detailed",
            "maxBytes": 10000000,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8"
        }
    },

    "filters": {
        "stderr_filter": {
            "()": "logging_config.StderrFilter",
        },
        "stdout_filter": {
            "()": "logging_config.StdoutFilter",
        }
    },

    "loggers": {
        "walrus": {
            "level": "DEBUG",
            "handlers": ["console", "err_console", "json_file"],
            # we don't want this to reach the root logger - that will be used for messages from other libs
            "propagate": False
        },
        "root": {
            # for other library logs we only want to see warnings and errors
            "level": "WARNING",
            "handlers": ["console", "err_console", "json_file"]
        }
    }
}

class StdoutFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO

class StderrFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno > logging.INFO
