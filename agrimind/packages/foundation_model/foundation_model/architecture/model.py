"""Decoder-Only Transformer implementation for KrishiMini-20M (P0.2/P0.4)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    torch = None  # type: ignore
    nn = None     # type: ignore
    F = None      # type: ignore
    HAS_TORCH = False

from foundation_model.architecture.config import ArchitectureCfg, KrishiMiniConfig, load_config
from foundation_model.architecture.validation import validate_architecture


if HAS_TORCH:
    class RMSNorm(nn.Module):
        def __init__(self, dim: int, eps: float = 1e-6) -> None:
            super().__init__()
            self.eps = eps
            self.weight = nn.Parameter(torch.ones(dim))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            variance = x.pow(2).mean(-1, keepdim=True)
            return x * torch.rsqrt(variance + self.eps) * self.weight

    def apply_rope(x: torch.Tensor, seq_len: int) -> torch.Tensor:
        """Apply Rotary Position Embedding (RoPE) to q/k tensor."""
        batch_size, n_heads, seq_len, head_dim = x.shape
        device = x.device
        dim_half = head_dim // 2
        inv_freq = 1.0 / (10000 ** (torch.arange(0, dim_half, dtype=torch.float32, device=device) / dim_half))
        t = torch.arange(seq_len, dtype=torch.float32, device=device)
        freqs = torch.outer(t, inv_freq)
        emb = torch.cat((freqs, freqs), dim=-1)
        
        cos = emb.cos()[None, None, :, :]
        sin = emb.sin()[None, None, :, :]
        
        x1 = x[..., :dim_half]
        x2 = x[..., dim_half:]
        x_rot = torch.cat((-x2, x1), dim=-1)
        return x * cos + x_rot * sin

    class GroupedQueryAttention(nn.Module):
        def __init__(self, cfg: ArchitectureCfg) -> None:
            super().__init__()
            self.n_heads = cfg.attention_heads
            self.n_kv_heads = cfg.kv_heads
            self.head_dim = cfg.head_dim
            self.hidden_size = cfg.hidden_size
            self.num_rep = self.n_heads // self.n_kv_heads

            self.q_proj = nn.Linear(self.hidden_size, self.n_heads * self.head_dim, bias=cfg.bias)
            self.k_proj = nn.Linear(self.hidden_size, self.n_kv_heads * self.head_dim, bias=cfg.bias)
            self.v_proj = nn.Linear(self.hidden_size, self.n_kv_heads * self.head_dim, bias=cfg.bias)
            self.o_proj = nn.Linear(self.n_heads * self.head_dim, self.hidden_size, bias=cfg.bias)

        def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
            b_sz, seq_len, _ = x.shape
            q = self.q_proj(x).view(b_sz, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
            k = self.k_proj(x).view(b_sz, seq_len, self.n_kv_heads, self.head_dim).transpose(1, 2)
            v = self.v_proj(x).view(b_sz, seq_len, self.n_kv_heads, self.head_dim).transpose(1, 2)

            q = apply_rope(q, seq_len)
            k = apply_rope(k, seq_len)

            if self.num_rep > 1:
                k = k.repeat_interleave(self.num_rep, dim=1)
                v = v.repeat_interleave(self.num_rep, dim=1)

            scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
            if mask is not None:
                scores = scores + mask
            attn = F.softmax(scores, dim=-1)
            output = torch.matmul(attn, v)
            output = output.transpose(1, 2).contiguous().view(b_sz, seq_len, -1)
            return self.o_proj(output)

    class SwiGLUFFN(nn.Module):
        def __init__(self, cfg: ArchitectureCfg) -> None:
            super().__init__()
            self.w1 = nn.Linear(cfg.hidden_size, cfg.ffn_hidden_size, bias=cfg.bias)  # gate
            self.w2 = nn.Linear(cfg.ffn_hidden_size, cfg.hidden_size, bias=cfg.bias)  # down
            self.w3 = nn.Linear(cfg.hidden_size, cfg.ffn_hidden_size, bias=cfg.bias)  # up

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.w2(F.silu(self.w1(x)) * self.w3(x))

    class TransformerBlock(nn.Module):
        def __init__(self, cfg: ArchitectureCfg) -> None:
            super().__init__()
            self.attn_norm = RMSNorm(cfg.hidden_size)
            self.attn = GroupedQueryAttention(cfg)
            self.ffn_norm = RMSNorm(cfg.hidden_size)
            self.ffn = SwiGLUFFN(cfg)

        def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
            h = x + self.attn(self.attn_norm(x), mask=mask)
            out = h + self.ffn(self.ffn_norm(h))
            return out

    class KrishiMiniTransformer(nn.Module):
        """Canonical KrishiMini decoder-only transformer model."""

        def __init__(self, cfg: KrishiMiniConfig) -> None:
            super().__init__()
            self.cfg = cfg
            arch = cfg.architecture
            self.vocab_size = cfg.tokenizer.vocab_size

            self.tok_embeddings = nn.Embedding(self.vocab_size, arch.hidden_size)
            self.layers = nn.ModuleList([TransformerBlock(arch) for _ in range(arch.layers)])
            self.norm = RMSNorm(arch.hidden_size)
            
            self.lm_head = nn.Linear(arch.hidden_size, self.vocab_size, bias=False)
            if arch.tie_embeddings:
                self.lm_head.weight = self.tok_embeddings.weight

            self.apply(self._init_weights)

        def _init_weights(self, module: nn.Module) -> None:
            if isinstance(module, nn.Linear):
                torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    torch.nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

        def forward(self, input_ids: torch.Tensor, labels: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
            b_sz, seq_len = input_ids.shape
            h = self.tok_embeddings(input_ids)

            mask = torch.full((seq_len, seq_len), float("-inf"), device=input_ids.device)
            mask = torch.triu(mask, diagonal=1)[None, None, :, :]

            for layer in self.layers:
                h = layer(h, mask=mask)
            h = self.norm(h)
            logits = self.lm_head(h)

            loss = None
            if labels is not None:
                shift_logits = logits[..., :-1, :].contiguous()
                shift_labels = labels[..., 1:].contiguous()
                loss = F.cross_entropy(shift_logits.view(-1, self.vocab_size), shift_labels.view(-1))

            return {"logits": logits, "loss": loss}
else:
    class KrishiMiniTransformer:  # type: ignore
        def __init__(self, cfg: KrishiMiniConfig) -> None:
            raise NotImplementedError("PyTorch is required to instantiate KrishiMiniTransformer.")


@dataclass
class ScratchModelSpec:
    config: KrishiMiniConfig
    training_mode: str
    base_checkpoint: None
    param_total: int
    init: str = "from_scratch"

    def to_manifest_fields(self) -> dict[str, Any]:
        return {
            "model_id": self.config.model_id,
            "model_family": self.config.model_family,
            "training_mode": "scratch",
            "base_checkpoint": None,
            "target_parameters": self.config.target_parameters,
            "total_parameters": self.param_total,
            "vocab_size": self.config.tokenizer.vocab_size,
            "architecture": self.config.architecture.model_dump(),
        }


def build_scratch_model_spec(cfg: KrishiMiniConfig | None = None) -> ScratchModelSpec:
    cfg = cfg or load_config()
    result = validate_architecture(cfg)
    result.raise_if_invalid()
    return ScratchModelSpec(
        config=cfg,
        training_mode="scratch",
        base_checkpoint=None,
        param_total=result.breakdown.total_parameters,
    )
