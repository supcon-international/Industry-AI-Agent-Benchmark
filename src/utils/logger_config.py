import logging
import os
from logging.handlers import RotatingFileHandler

class SimTimeFormatter(logging.Formatter):
    """
    A custom log formatter that produces a compact, simulation-focused output.
    It formats logs as '[sim_time] message'.
    """
    def format(self, record):
        """Overrides the default format method."""
        # Check if the custom 'sim_time' attribute exists on the log record
        if hasattr(record, 'sim_time'):
            # Create the custom format string, ensuring sim_time is formatted correctly
            message = f"[{record.sim_time:.2f}] {record.getMessage()}"
        else:
            # For logs without sim_time, fall back to a simple default
            message = f"[{record.levelname}] {record.getMessage()}"
        return message

def setup_logging(log_level=logging.INFO):
    """
    Set up logging for the application.

    This configures two main logging streams:
    1. A root logger for general application messages (e.g., MQTT, startup),
       which logs to the console and a file (`general.log`).
    2. A dedicated 'simulation' logger for simulation events, which uses a
       custom, compact format. Its console output is controlled by `log_level`.

    Args:
        log_level (int): The logging level for the console handlers.
                         Use logging.INFO for concise output and logging.DEBUG
                         for verbose simulation steps.
    """
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 1. --- Root Logger Configuration (for non-simulation messages) ---
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything at the root level
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Simplified formatter for general logs
    general_formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')

    # Console handler for general messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(general_formatter)
    # IMPORTANT: Filter to EXCLUDE simulation messages from this handler
    console_handler.addFilter(lambda record: not record.name.startswith('simulation'))
    root_logger.addHandler(console_handler)

    # File handler for general messages
    general_log_file = os.path.join(log_dir, 'general.log')
    file_handler = RotatingFileHandler(general_log_file, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')) # Keep detailed logs in file
    root_logger.addHandler(file_handler)

    # 2. --- Simulation Logger Configuration ---
    sim_logger = logging.getLogger('simulation')
    sim_logger.setLevel(logging.DEBUG)  # Always capture debug messages at the logger level
    sim_logger.propagate = False  # IMPORTANT: Stop sim logs from reaching the root logger

    # Console handler for simulation messages with custom format
    sim_console_handler = logging.StreamHandler()
    # The console's visibility is controlled by the user-defined log_level
    sim_console_handler.setLevel(log_level)
    sim_console_handler.setFormatter(SimTimeFormatter())
    sim_logger.addHandler(sim_console_handler)

    # File handler for detailed simulation logs (always logs at DEBUG level)
    sim_log_file = os.path.join(log_dir, 'simulation_details.log')
    sim_file_handler = RotatingFileHandler(sim_log_file, maxBytes=10*1024*1024, backupCount=5)
    sim_file_handler.setLevel(logging.DEBUG)
    # Use a more detailed formatter for the file for better debugging
    detailed_sim_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(sim_time)7.2f] - %(name)s - %(message)s')
    sim_file_handler.setFormatter(detailed_sim_formatter)
    # Only log records that have simulation time to this file
    sim_file_handler.addFilter(lambda record: hasattr(record, 'sim_time'))
    sim_logger.addHandler(sim_file_handler)


class SimLoggerAdapter(logging.LoggerAdapter):
    """
    A logger adapter to automatically inject simulation time into log records.
    """
    def process(self, msg, kwargs):
        """Adds the current simulation time from the environment to the log record's 'extra' dict."""
        if 'env' in self.extra:
            kwargs['extra'] = {'sim_time': self.extra['env'].now}
        return msg, kwargs

def get_sim_logger(env, name='simulation'):
    """
    Get a logger adapter for simulation events.

    This is the preferred way to get a logger for simulation entities, as it
    automatically includes the current simulation time in all log records.

    Args:
        env: The simpy.Environment object.
        name (str): The name of the logger (e.g., 'simulation.agv').

    Returns:
        SimLoggerAdapter: A logger adapter instance.
    """
    logger = logging.getLogger(name)
    return SimLoggerAdapter(logger, {'env': env})
