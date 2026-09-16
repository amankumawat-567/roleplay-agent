from roleplay_agent.components.observability.logging import logger


def ns_to_ms(ns) -> float | None:
    return round(ns / 1e6, 1) if ns is not None else None


def log_chat_turn(*, session_id: str, model: str, ttft_s, total_s: float, reply_chars: int, stats: dict) -> None:
    logger.info(
        "chat turn session=%s model=%s ttft=%ss total=%ss reply_chars=%d "
        "prompt_tokens=%s output_tokens=%s load_ms=%s prompt_eval_ms=%s eval_ms=%s",
        session_id,
        model,
        round(ttft_s, 2) if ttft_s is not None else None,
        round(total_s, 2),
        reply_chars,
        stats.get("prompt_eval_count"),
        stats.get("eval_count"),
        ns_to_ms(stats.get("load_duration")),
        ns_to_ms(stats.get("prompt_eval_duration")),
        ns_to_ms(stats.get("eval_duration")),
    )


def log_background_fold(*, session_id: str, took_s: float) -> None:
    logger.info("background summary fold session=%s took=%ss", session_id, round(took_s, 2))


def log_background_fold_failed(session_id: str) -> None:
    logger.exception("background summary fold failed for session=%s", session_id)


def log_followup_delivered(*, session_id: str) -> None:
    logger.info("followup delivered session=%s", session_id)


def log_followup_failed(session_id: str) -> None:
    logger.exception("followup delivery failed for session=%s", session_id)
