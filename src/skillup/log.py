"""Log strutturati: una riga JSON per evento, con i millisecondi."""

import json
import logging
from typing import Any

logger = logging.getLogger("skillup")


def traccia(evento: str, **campi: Any) -> None:
    logger.info(json.dumps({"evento": evento, **campi}, ensure_ascii=False, default=str))


def configura_log() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # una riga per chiamata è rumore