"""Application orchestration for hotkey recording and transcription."""

import logging
import sys

from sttc.runtime import RuntimeController
from sttc.settings import Settings

logger = logging.getLogger(__name__)


def _print_banner(settings: Settings) -> None:
    logger.info("=" * 60)
    logger.info("sttc - Speech to Text Clipboard")
    logger.info("=" * 60)
    if settings.stt_model:
        logger.info("Mode               : CLOUD (%s)", settings.stt_model)
    else:
        logger.info("Mode               : LOCAL (%s)", settings.stt_whisper_model)
    logger.info("Chunk duration     : %s s", settings.stt_chunk_seconds)
    logger.info("Target sample rate : %s Hz", settings.sample_rate_target)
    logger.info("Channels           : %s", settings.channels)
    logger.info("Recording mode     : %s", settings.recording_mode)
    logger.info("Recording hotkey   : %s", settings.recording_hotkey)
    logger.info("Quit hotkey        : %s", settings.quit_hotkey)
    logger.info("")
    if settings.recording_mode == "toggle":
        logger.info(
            "Press %s to start, press again to stop, use %s to quit.",
            settings.recording_hotkey,
            settings.quit_hotkey,
        )
    else:
        logger.info(
            "Press & hold %s to record, release to stop, use %s to quit.",
            settings.recording_hotkey,
            settings.quit_hotkey,
        )
    logger.info("=" * 60)
    logger.info("")


def run(settings: Settings) -> None:
    """Run the interactive hotkey-based transcription app."""
    _print_banner(settings)

    controller = RuntimeController(settings)
    controller.start()

    try:
        controller.wait_for_stop_signal()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        logger.info("Goodbye!")
        sys.exit(0)
