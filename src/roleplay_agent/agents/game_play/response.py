import time

from roleplay_agent.components.observability.metrics import log_chat_turn


class StreamingReply:
    """Wraps a LangGraph astream_events run: yields text pieces as they
    arrive and collects timing/stats for structured logging, keeping that
    bookkeeping out of the API route handler."""

    def __init__(self, session_id: str, model: str):
        self.session_id = session_id
        self.model = model
        self._chunks: list[str] = []
        self._t_start = time.monotonic()
        self._t_first_token: float | None = None
        self._stats: dict = {}

    async def consume(self, graph, initial_state):
        async for event in graph.astream_events(initial_state, version="v2"):
            if event["event"] == "on_chat_model_stream":
                piece = event["data"]["chunk"].content
                if piece:
                    if self._t_first_token is None:
                        self._t_first_token = time.monotonic()
                    self._chunks.append(piece)
                    yield piece
            elif event["event"] == "on_chat_model_end":
                self._stats = event["data"]["output"].response_metadata

    @property
    def full_text(self) -> str:
        return "".join(self._chunks)

    def log(self) -> None:
        log_chat_turn(
            session_id=self.session_id,
            model=self.model,
            ttft_s=(self._t_first_token - self._t_start) if self._t_first_token else None,
            total_s=time.monotonic() - self._t_start,
            reply_chars=len(self.full_text),
            stats=self._stats,
        )
