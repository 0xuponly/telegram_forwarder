#!/usr/bin/env python3
"""
Forward Telegram channel messages that contain certain keywords.

Only processes messages from broadcast channels (ignores chats and groups).
Requires user account credentials (API ID, API Hash from my.telegram.org).
"""

import asyncio
import difflib
import logging
import os
import re
import sys
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from typing import List, Tuple

# Dedupe 1: same (chat_id, message_id) never forwarded twice (handles duplicate Telegram events)
DEDUP_MAX_SIZE = 2000
_forwarded_ids: set = set()
_forwarded_ids_order: deque = deque()

# Dedupe 2: same text never forwarded twice to the same dest (different source channels, same content)
CONTENT_DEDUP_MAX_SIZE = 2000
_content_forwarded: set = set()  # (dest, content_hash)
_content_forwarded_order: deque = deque()
# Sample of text last forwarded per (dest, hash) — for filtered.log when exact duplicate
_exact_forwarded_sample: dict = {}

# Dedupe 3: near-duplicate wording (same story, paraphrased) per destination
NEAR_DUP_WINDOW = int(os.environ.get("TELEGRAM_NEAR_DUP_WINDOW", "80"))
NEAR_DUP_SEQ_RATIO = float(os.environ.get("TELEGRAM_NEAR_DUP_SEQ_RATIO", "0.82"))
NEAR_DUP_JACCARD = float(os.environ.get("TELEGRAM_NEAR_DUP_JACCARD", "0.68"))
NEAR_DUP_COMPARE_CHARS = int(os.environ.get("TELEGRAM_NEAR_DUP_COMPARE_CHARS", "1200"))
# Per dest: deque of (normalized_for_similarity, original_text_sample) from last forwards
_recent_text_by_dest: dict[str, deque] = defaultdict(
    lambda: deque(maxlen=NEAR_DUP_WINDOW)
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telethon import TelegramClient, events
from telethon.tl.types import Channel

# Configuration via environment variables
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_NAME = os.environ.get("TELEGRAM_SESSION", "epstein_coalition_alerts_session")
SESSION_PATH = os.path.join(SCRIPT_DIR, SESSION_NAME)

LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "forwarder.log")
FILTERED_LOG_FILE = os.path.join(LOG_DIR, "filtered.log")
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3
FILTERED_LOG_MAX_BYTES = int(os.environ.get("TELEGRAM_FILTERED_LOG_MAX_BYTES", str(10 * 1024 * 1024)))

# Setup logging
def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("epstein_coalition_tg_alerts")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # Also log to stdout when run interactively (e.g. for debugging)
    if sys.stdout.isatty():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

    return logger


def _setup_filtered_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    lg = logging.getLogger("epstein_coalition_filtered")
    lg.setLevel(logging.INFO)
    lg.handlers.clear()
    lg.propagate = False
    h = RotatingFileHandler(
        FILTERED_LOG_FILE,
        maxBytes=FILTERED_LOG_MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    h.setFormatter(
        logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    lg.addHandler(h)
    return lg


log = _setup_logging()
filter_log = _setup_filtered_logger()

CLIP = 4000


def _log_filtered(
    reason: str,
    dest: str,
    source_chat: str,
    filtered_body: str,
    matched_body: str,
) -> None:
    """Log a message that was not forwarded and the prior forward that caused it."""
    filter_log.info(
        "reason=%s | dest=%s | source=%s\n--- filtered (this message) ---\n%s\n--- matched (prior forward / basis) ---\n%s\n%s\n",
        reason,
        dest,
        source_chat,
        (filtered_body or "")[:CLIP],
        (matched_body or "")[:CLIP],
        "-" * 60,
    )


# Output channels: list of (destination, keywords_list)
# Channel 1: FORWARD_TO_1 + KEYWORDS_1, or legacy FORWARD_TO + KEYWORDS
# Channel 2: FORWARD_TO_2 + KEYWORDS_2
# Channel 3: FORWARD_TO_3 + KEYWORDS_3
def _parse_keywords(s: str) -> List[str]:
    return [k.strip() for k in (s or "").lower().split(",") if k.strip()]


def _get_output_channels() -> List[Tuple[str, List[str]]]:
    channels: List[Tuple[str, List[str]]] = []

    # Channel 1
    dest1 = os.environ.get("TELEGRAM_FORWARD_TO_1")
    kw1 = _parse_keywords(os.environ.get("TELEGRAM_KEYWORDS_1"))
    if dest1 and kw1:
        channels.append((dest1, kw1))

    # Channel 2
    dest2 = os.environ.get("TELEGRAM_FORWARD_TO_2")
    kw2 = _parse_keywords(os.environ.get("TELEGRAM_KEYWORDS_2", ""))
    if dest2 and kw2:
        channels.append((dest2, kw2))

    # Channel 3
    dest3 = os.environ.get("TELEGRAM_FORWARD_TO_3")
    kw3 = _parse_keywords(os.environ.get("TELEGRAM_KEYWORDS_3", ""))
    if dest3 and kw3:
        channels.append((dest3, kw3))

    return channels

# Set to True for case-insensitive matching
KEYWORDS_CASE_INSENSITIVE = os.environ.get("TELEGRAM_CASE_INSENSITIVE", "true").lower() == "true"


def _normalize_text_for_dedupe(text: str) -> str:
    """Normalize so same content from different sources hashes the same."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def _normalize_for_similarity(text: str) -> str:
    """Strip punctuation / noise so paraphrases compare better."""
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return " ".join(t.split())


def _similar_enough(a: str, b: str) -> bool:
    """True if two strings are likely the same story (wording may differ)."""
    if not a or not b:
        return False
    n = NEAR_DUP_COMPARE_CHARS
    a, b = a[:n], b[:n]
    if difflib.SequenceMatcher(None, a, b).ratio() >= NEAR_DUP_SEQ_RATIO:
        return True
    ta = set(re.findall(r"\w{2,}", a, flags=re.UNICODE))
    tb = set(re.findall(r"\w{2,}", b, flags=re.UNICODE))
    if len(ta) < 4 or len(tb) < 4:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    if union == 0:
        return False
    return (inter / union) >= NEAR_DUP_JACCARD


def message_contains_keywords(text: str, keywords: List[str]) -> bool:
    """Check if message text contains any of the given keywords."""
    if not text or not keywords:
        return False
    search_text = text.lower() if KEYWORDS_CASE_INSENSITIVE else text
    for keyword in keywords:
        pattern = rf"\b{re.escape(keyword.strip())}\b"
        if re.search(pattern, search_text, re.IGNORECASE if KEYWORDS_CASE_INSENSITIVE else 0):
            return True
    return False


async def run_client(client: TelegramClient, output_channels: List[Tuple[str, List[str]]]) -> None:
    """Run the client until disconnected."""
    await client.run_until_disconnected()


async def main() -> int:
    log.info("Connecting to Telegram...")
    if not API_ID or not API_HASH:
        log.error("Set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables.")
        log.error("Get them from https://my.telegram.org")
        return 1

    output_channels = _get_output_channels()
    if not output_channels:
        log.error(
            "Configure at least one output. Set TELEGRAM_FORWARD_TO + TELEGRAM_KEYWORDS "
            "(or TELEGRAM_FORWARD_TO_1 + TELEGRAM_KEYWORDS_1)."
        )
        return 1

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

    @client.on(events.NewMessage)
    async def handler(event):
        # Ignore outgoing messages (our own)
        if event.out:
            return

        chat = await event.get_chat()
        # Only process broadcast channels (not groups, not private chats)
        if not isinstance(chat, Channel) or not getattr(chat, "broadcast", False):
            return

        # Dedupe: skip if we already forwarded this exact message (handles duplicate events)
        dedupe_key = (event.chat_id, event.id)
        if dedupe_key in _forwarded_ids:
            _log_filtered(
                "duplicate_telegram_event",
                "(n/a — same message id, before dest loop)",
                getattr(chat, "title", "") or str(event.chat_id),
                event.text or "",
                "Same chat_id + message_id already processed once (duplicate Telegram update).",
            )
            return
        if len(_forwarded_ids) >= DEDUP_MAX_SIZE:
            _forwarded_ids.discard(_forwarded_ids_order.popleft())
        _forwarded_ids.add(dedupe_key)
        _forwarded_ids_order.append(dedupe_key)

        text = event.text or ""
        norm_exact = _normalize_text_for_dedupe(text)
        norm_similar = _normalize_for_similarity(text)
        content_hash = hash(norm_exact)

        for dest, keywords in output_channels:
            if not message_contains_keywords(text, keywords):
                continue
            # Per-dest exact text dedupe
            content_key = (dest, content_hash)
            if content_key in _content_forwarded:
                _log_filtered(
                    "exact_duplicate",
                    dest,
                    getattr(chat, "title", "") or str(event.chat_id),
                    text,
                    _exact_forwarded_sample.get(
                        content_key,
                        "(identical normalized text; sample evicted from cache)",
                    ),
                )
                continue
            # Per-dest near-duplicate (same story, different wording / source)
            matched_prior_sample = None
            for norm_prev, orig_sample in _recent_text_by_dest[dest]:
                if _similar_enough(norm_similar, norm_prev):
                    matched_prior_sample = orig_sample
                    break
            if matched_prior_sample is not None:
                _log_filtered(
                    "near_duplicate",
                    dest,
                    getattr(chat, "title", "") or str(event.chat_id),
                    text,
                    matched_prior_sample,
                )
                continue

            try:
                await event.forward_to(dest)
            except Exception as e:
                log.exception("Failed to forward to %s: %s", dest, e)
                continue
            if len(_content_forwarded) >= CONTENT_DEDUP_MAX_SIZE:
                old_key = _content_forwarded_order.popleft()
                _content_forwarded.discard(old_key)
                _exact_forwarded_sample.pop(old_key, None)
            _content_forwarded.add(content_key)
            _content_forwarded_order.append(content_key)
            _exact_forwarded_sample[content_key] = (text or norm_exact)[:CLIP]
            _recent_text_by_dest[dest].append((norm_similar, (text or norm_exact)[:CLIP]))
            log.info("Forwarded to %s from %s: %s...", dest, chat.title, (text or "")[:80])

    await client.start()
    for i, (dest, kw) in enumerate(output_channels, 1):
        log.info("Channel %d: forwarding to %s (keywords: %s)", i, dest, kw)
    log.info("Press Ctrl+C to stop.")

    # Reconnection loop with exponential backoff
    base_delay = 5
    max_delay = 300
    attempt = 0

    while True:
        try:
            await client.run_until_disconnected()
            # If we get here, client disconnected
            log.warning("Telegram client disconnected. Reconnecting in %ds...", base_delay)
            delay = base_delay
            attempt = 0
        except asyncio.CancelledError:
            log.info("Shutdown requested.")
            break
        except Exception as e:
            attempt += 1
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            log.exception("Client error (attempt %d): %s. Reconnecting in %ds...", attempt, e, delay)
            try:
                await client.disconnect()
            except Exception:
                pass

        await asyncio.sleep(delay)
        try:
            await client.connect()
        except Exception as e:
            log.exception("Reconnect failed: %s", e)
            await asyncio.sleep(delay)
            continue

    return 0


def _excepthook(exc_type, exc_val, exc_tb):
    """Log unhandled exceptions before exit."""
    log.critical("Unhandled exception: %s", exc_val, exc_info=(exc_type, exc_val, exc_tb))
    sys.__excepthook__(exc_type, exc_val, exc_tb)


if __name__ == "__main__":
    sys.excepthook = _excepthook
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        sys.exit(0)
    except Exception as e:
        log.exception("Fatal error: %s", e)
        sys.exit(1)
