import logging
import logging.handlers

from roleplay_agent.config.settings import PROJECT_ROOT

logger = logging.getLogger("roleplay_agent")

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Same cwd-based PROJECT_ROOT as config/settings.py (see that file's comment
# on why cwd, not __file__) - logs/ sits alongside data/ and configs/ at the
# project root rather than inside the installed package.
LOGS_DIR = PROJECT_ROOT / "logs"


def setup_logging(level: str = "INFO") -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOGS_DIR / "roleplay_agent.log", when="midnight", backupCount=14
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=resolved_level, format=LOG_FORMAT, handlers=[logging.StreamHandler(), file_handler])
