"""Named MiniMind model profiles for reproducible experiments."""

from model.model_minimind import MiniMindConfig


MODEL_PROFILES = {
    "forgemind64": {
        "hidden_size": 768,
        "num_hidden_layers": 8,
        "num_attention_heads": 8,
        "num_key_value_heads": 4,
        "intermediate_size": 2432,
        "vocab_size": 6400,
        "max_position_embeddings": 4096,
        "gradient_checkpointing": False,
    },
    "minimind3": {
        "hidden_size": 768,
        "num_hidden_layers": 8,
        "num_attention_heads": 8,
        "num_key_value_heads": 4,
        "vocab_size": 6400,
        "max_position_embeddings": 32768,
        "gradient_checkpointing": False,
    },
    "forge_1b": {
        "hidden_size": 2048,
        "num_hidden_layers": 24,
        "num_attention_heads": 16,
        "num_key_value_heads": 4,
        "intermediate_size": 5632,
        "vocab_size": 32768,
        "max_position_embeddings": 8192,
        "gradient_checkpointing": True,
    },
    "forge_7b": {
        "hidden_size": 4096,
        "num_hidden_layers": 32,
        "num_attention_heads": 32,
        "num_key_value_heads": 8,
        "intermediate_size": 14336,
        "vocab_size": 32768,
        "max_position_embeddings": 8192,
        "gradient_checkpointing": True,
    },
}


def create_model_config(profile="minimind3", **overrides):
    """Create a validated config; profile dimensions stay explicit in checkpoints."""
    try:
        values = dict(MODEL_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"Unknown model profile: {profile}") from exc
    values.update({key: value for key, value in overrides.items() if value is not None})
    hidden = values["hidden_size"]
    heads = values["num_attention_heads"]
    kv_heads = values["num_key_value_heads"]
    if hidden % heads or heads % kv_heads:
        raise ValueError("hidden_size must divide by attention heads; query heads must divide by KV heads")
    return MiniMindConfig(**values)


def estimate_parameters(config):
    """Approximate parameter count for the dense profiles, including tied embeddings."""
    dim = config.hidden_size
    head_dim = config.head_dim
    q_heads = config.num_attention_heads
    kv_heads = config.num_key_value_heads
    attention = 2 * dim * q_heads * head_dim + 2 * dim * kv_heads * head_dim
    feed_forward = 3 * dim * config.intermediate_size
    embeddings = config.vocab_size * dim
    if not config.tie_word_embeddings:
        embeddings *= 2
    norms = 2 * dim * config.num_hidden_layers + dim
    return config.num_hidden_layers * (attention + feed_forward + norms) + embeddings
