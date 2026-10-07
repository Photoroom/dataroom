"""The trainable part: a query head reading a frozen DINOv2's token sequence.

The head is the dino-bench "R2" recipe: ``n_queries`` learned queries attend
over the tokens, their outputs are concatenated and merged back to ``dim``,
and a half-width MLP scores the result. The model record stores ``Config``
as JSON (``asdict``) and apply rebuilds the head from it.
"""

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class Config:
    dim: int = 64
    n_blocks: int = 0
    n_heads: int = 2
    n_queries: int = 4
    dropout: float = 0.1
    image_size: int = 518


class RMSNorm(nn.Module):
    def __init__(self, dim: int) -> None:
        super().__init__()
        self.scale = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x_dtype = x.dtype
        x = x.float()
        rrms = torch.rsqrt(torch.mean(x**2, dim=-1, keepdim=True) + 1e-6)
        return (x * rrms).to(dtype=x_dtype) * self.scale


class SelfAttention(nn.Module):
    def __init__(self, dim: int, n_heads: int = 4, dropout: float = 0.1):
        super().__init__()
        assert dim % n_heads == 0
        self.dim = dim
        self.n_heads = n_heads
        self.dim_heads = dim // n_heads
        self.qkv = nn.Linear(dim, 3 * dim, bias=False)
        self.q_norm = RMSNorm(dim)
        self.k_norm = RMSNorm(dim)
        self.proj = nn.Linear(dim, dim, bias=False)
        self.dropout = dropout

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        query, key, value = self.qkv(x).chunk(3, dim=-1)
        query, key = self.q_norm(query), self.k_norm(key)
        B, L, D = query.shape

        query = query.view(B, L, self.n_heads, self.dim_heads).transpose(1, 2)
        key = key.view(B, L, self.n_heads, self.dim_heads).transpose(1, 2)
        value = value.view(B, L, self.n_heads, self.dim_heads).transpose(1, 2)

        attn = F.scaled_dot_product_attention(
            query,
            key,
            value,
            dropout_p=self.dropout if self.training else 0.0,
        )
        attn = attn.transpose(1, 2).contiguous().view(B, L, D)

        return self.proj(attn)


class SelfAttentionBlock(nn.Module):
    def __init__(self, dim: int, n_heads: int = 4, dropout: float = 0.1):
        super().__init__()
        self.self_attn = SelfAttention(dim, n_heads, dropout)
        self.ffn = nn.Sequential(nn.Linear(dim, dim, bias=False), nn.SiLU(), nn.Linear(dim, dim, bias=False))
        self.norm1 = RMSNorm(dim)
        self.norm2 = RMSNorm(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.self_attn(self.norm1(x))
        x = x + self.ffn(self.norm2(x))
        return x


class QueryHead(nn.Module):
    def __init__(self, backbone_dim: int, config: Config):
        super().__init__()

        self.in_proj = nn.Linear(backbone_dim, config.dim)
        blocks = []
        for _ in range(config.n_blocks):
            block = SelfAttentionBlock(config.dim, n_heads=config.n_heads, dropout=config.dropout)
            blocks.append(block)
        self.blocks = nn.ModuleList(blocks)

        self.dropout = config.dropout
        self.scale = config.dim**-0.5
        self.query = nn.Parameter(torch.randn(1, config.n_queries, config.dim) * 0.02)
        self.q_norm = RMSNorm(config.dim)
        self.k_norm = RMSNorm(config.dim)
        self.mlp = nn.Sequential(
            RMSNorm(config.dim),
            nn.Linear(config.dim, config.dim),
            nn.GELU(),
            nn.Linear(config.dim, 1),
        )
        qmerge = None
        if config.n_queries > 1:
            qmerge = nn.Linear(config.n_queries * config.dim, config.dim)
        self.qmerge = qmerge

    def pool(self, backbone_feats: torch.Tensor) -> torch.Tensor:
        """Return pooled query features [B, n_queries, dim] before the MLP head."""
        B = backbone_feats.shape[0]

        x = self.in_proj(F.dropout(backbone_feats, p=self.dropout, training=self.training))

        for block in self.blocks:
            x = block(x)

        query = self.q_norm(self.query).expand(B, -1, -1)
        key = self.k_norm(x)
        attn = F.scaled_dot_product_attention(query, key, x, scale=self.scale)
        return attn

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(x).flatten(1)
        if self.qmerge is not None:
            x = self.qmerge(x)
        out = self.mlp(x)
        return out
