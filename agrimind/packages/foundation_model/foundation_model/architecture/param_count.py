"""Exact parameter counting for KrishiMini decoder-only transformer (no torch required)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from foundation_model.architecture.config import ArchitectureCfg, KrishiMiniConfig


@dataclass
class ParamBreakdown:
    total_parameters: int
    trainable_parameters: int
    embedding_parameters: int
    attention_parameters: int
    ffn_parameters: int
    norm_parameters: int
    lm_head_parameters: int
    vocab_size: int
    layers: int
    hidden_size: int
    tied_embeddings: bool

    def to_dict(self) -> dict:
        return asdict(self)


def count_parameters(
    arch: ArchitectureCfg,
    *,
    vocab_size: int,
) -> ParamBreakdown:
    """
    Count parameters for a GQA decoder-only transformer with optional SwiGLU FFN.

    Attention (GQA, no bias):
      q: H * H
      k: H * (kv_heads * head_dim)
      v: H * (kv_heads * head_dim)
      o: H * H

    FFN SwiGLU (no bias): gate + up + down = 3 * H * I
    (standard SwiGLU uses two projections of size I and one down)

    Norms: RMSNorm ≈ H params per norm; 2 norms per layer + final norm
    Embeddings: V * H; LM head = 0 if tied else V * H
    """
    H = arch.hidden_size
    L = arch.layers
    V = vocab_size
    I = arch.ffn_hidden_size
    kv_dim = arch.kv_heads * arch.head_dim

    if arch.attention_heads * arch.head_dim != H:
        # allow non-matching if head_dim * heads != H only when intentional;
        # still compute with explicit dims
        pass

    # embeddings
    embedding = V * H
    lm_head = 0 if arch.tie_embeddings else V * H

    # per-layer attention
    attn_per = H * H + H * kv_dim + H * kv_dim + H * H  # q,k,v,o
    if arch.bias:
        attn_per += H + kv_dim + kv_dim + H

    # per-layer FFN (SwiGLU: w1,w2,w3)
    if arch.activation.lower() in ("swiglu", "silu", "swish"):
        ffn_per = 3 * H * I
        if arch.bias:
            ffn_per += 2 * I + H
    else:
        ffn_per = 2 * H * I
        if arch.bias:
            ffn_per += I + H

    # RMSNorm: weight only ≈ H; pre-attn + pre-ffn per layer
    norm_per = 2 * H
    final_norm = H

    attention = L * attn_per
    ffn = L * ffn_per
    norms = L * norm_per + final_norm

    total = embedding + lm_head + attention + ffn + norms
    return ParamBreakdown(
        total_parameters=total,
        trainable_parameters=total,
        embedding_parameters=embedding,
        attention_parameters=attention,
        ffn_parameters=ffn,
        norm_parameters=norms,
        lm_head_parameters=lm_head,
        vocab_size=V,
        layers=L,
        hidden_size=H,
        tied_embeddings=arch.tie_embeddings,
    )


def count_from_config(cfg: KrishiMiniConfig) -> ParamBreakdown:
    return count_parameters(cfg.architecture, vocab_size=cfg.tokenizer.vocab_size)
