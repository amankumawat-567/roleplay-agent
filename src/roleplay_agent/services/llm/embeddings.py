from langchain_ollama import OllamaEmbeddings


def build_embeddings(model: str) -> OllamaEmbeddings:
    # Deliberately always Ollama, unlike the multi-provider chat models in
    # registry.py - no hosted-embedding equivalent is wired up (or asked
    # for), and this runs through the same local daemon everything else
    # already talks to.
    return OllamaEmbeddings(model=model)
