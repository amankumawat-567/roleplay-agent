from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from roleplay_agent.config.settings import AppConfig
from roleplay_agent.schema.game_builder import BuilderMessage, GameDraft
from roleplay_agent.services.llm.registry import build_llm

BUILDER_SYSTEM_PROMPT = """You are a creative collaborator helping someone design a persona/character for \
a roleplay chat app. Your job is to ask focused questions and help them think through:
- Who the AI's character is: name, personality, speech style, tone
- Who the user plays in the scene, and their relationship to the character
- The scene's background and a loose arc/beats it might move through

Ask ONE focused question at a time - never a checklist. Once you have enough to describe a compelling \
persona, tell them they can click "Generate draft" to turn the conversation into one - don't try to \
write the persona yourself in the chat, that happens as a separate step."""

DRAFT_PROMPT = (
    "Based on this conversation, propose a detailed roleplay persona. Write full descriptive "
    "paragraphs for persona, user_role, and script - not short labels or placeholders.\n\n{convo}"
)

# Same GameDraft schema and structured-output call as DRAFT_PROMPT above,
# just seeded with a transcript instead of a conversation (see
# docs/ARCHITECTURE.md's "Three ways to create a persona" for why the
# Field descriptions on GameDraft matter more than this prompt wording).
TRANSCRIPT_DRAFT_PROMPT = (
    "Below is a transcript of a video. Propose a detailed roleplay persona inspired by the "
    "character(s), setting, or scenario it describes. Write full descriptive paragraphs for "
    "persona, user_role, and script - not short labels or placeholders.\n\n{transcript}"
)


def _to_lc_messages(messages: list[BuilderMessage]) -> list[BaseMessage]:
    lc_messages: list[BaseMessage] = [SystemMessage(content=BUILDER_SYSTEM_PROMPT)]
    for m in messages:
        cls = HumanMessage if m.role == "user" else AIMessage
        lc_messages.append(cls(content=m.content))
    return lc_messages


async def stream_builder_reply(messages: list[BuilderMessage], app_config: AppConfig) -> AsyncGenerator[str, None]:
    llm = build_llm(
        app_config.builder_provider,
        app_config.builder_model,
        app_config.default_num_ctx,
        app_config.keep_alive,
        reasoning=True,
    )
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content


def generate_draft(messages: list[BuilderMessage], app_config: AppConfig) -> GameDraft:
    llm = build_llm(
        app_config.builder_provider,
        app_config.builder_model,
        app_config.default_num_ctx,
        app_config.keep_alive,
        reasoning=True,
    )
    convo = "\n".join(f"{m.role}: {m.content}" for m in messages)
    structured_llm = llm.with_structured_output(GameDraft)
    return structured_llm.invoke(DRAFT_PROMPT.format(convo=convo))


def generate_draft_from_transcript(transcript: str, app_config: AppConfig) -> GameDraft:
    llm = build_llm(
        app_config.builder_provider,
        app_config.builder_model,
        app_config.default_num_ctx,
        app_config.keep_alive,
        reasoning=True,
    )
    structured_llm = llm.with_structured_output(GameDraft)
    return structured_llm.invoke(TRANSCRIPT_DRAFT_PROMPT.format(transcript=transcript))
