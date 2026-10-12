"""Small dependency-light LoRA utilities for a local Transformers causal LM."""

import json
import math
from contextlib import contextmanager
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


class LoRALinear(nn.Module):
    def __init__(self, base, rank=8, alpha=16, dropout=0.05):
        super().__init__()
        if not isinstance(base, nn.Linear):
            try:
                from bitsandbytes.nn import Linear4bit
            except (ImportError, RuntimeError):
                Linear4bit = None
            if Linear4bit is None or not isinstance(base, Linear4bit):
                raise TypeError("LoRA targets must be torch.nn.Linear or bitsandbytes Linear4bit modules")
        self.base = base
        self.base.requires_grad_(False)
        self.rank = int(rank)
        self.scaling = float(alpha) / self.rank
        self.enabled = True
        self.dropout = nn.Dropout(float(dropout)) if dropout else nn.Identity()
        self.lora_A = nn.Parameter(torch.empty(self.rank, base.in_features, device=base.weight.device, dtype=torch.float32))
        self.lora_B = nn.Parameter(torch.zeros(base.out_features, self.rank, device=base.weight.device, dtype=torch.float32))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))

    def forward(self, inputs):
        output = self.base(inputs)
        if not self.enabled:
            return output
        adapter_input = self.dropout(inputs).to(self.lora_A.dtype)
        update = F.linear(F.linear(adapter_input, self.lora_A), self.lora_B) * self.scaling
        return output + update.to(output.dtype)


def inject_lora(model, target_suffixes=("q_proj", "v_proj"), rank=8, alpha=16, dropout=0.05):
    """Freeze a causal LM and replace selected Linear layers with LoRA wrappers."""
    model.requires_grad_(False)
    linear_types = [nn.Linear]
    try:
        from bitsandbytes.nn import Linear4bit
        linear_types.append(Linear4bit)
    except (ImportError, RuntimeError):
        pass
    targets = []
    for name, module in list(model.named_modules()):
        if name and name.rsplit(".", 1)[-1] in target_suffixes and isinstance(module, tuple(linear_types)):
            targets.append(name)
    if not targets:
        raise ValueError(f"No Linear modules found with suffixes {tuple(target_suffixes)}")
    for name in targets:
        parent = model
        parts = name.split(".")
        for part in parts[:-1]:
            parent = getattr(parent, part)
        child_name = parts[-1]
        setattr(parent, child_name, LoRALinear(getattr(parent, child_name), rank, alpha, dropout))
    return targets


@contextmanager
def adapter_mode(model, enabled):
    """Temporarily enable or bypass every injected LoRA update."""
    walk = getattr(model, "modules", None)
    modules = [module for module in walk() if isinstance(module, LoRALinear)] if callable(walk) else []
    previous = [module.enabled for module in modules]
    for module in modules:
        module.enabled = bool(enabled)
    try:
        yield bool(modules)
    finally:
        for module, state in zip(modules, previous):
            module.enabled = state


def save_adapter(model, output_dir, metadata):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = {
        key: value.detach().cpu().contiguous()
        for key, value in model.state_dict().items()
        if key.endswith(".lora_A") or key.endswith(".lora_B")
    }
    if not adapter:
        raise RuntimeError("No LoRA weights found to save")
    tmp_path = output_dir / "adapter_model.pt.tmp"
    torch.save(adapter, tmp_path)
    tmp_path.replace(output_dir / "adapter_model.pt")
    config = {**metadata, "adapter_file": "adapter_model.pt", "adapter_tensor_count": len(adapter)}
    (output_dir / "adapter_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_adapter(model, adapter_dir):
    adapter_dir = Path(adapter_dir)
    config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    inject_lora(
        model,
        target_suffixes=tuple(config["target_modules"]),
        rank=config["rank"],
        alpha=config["alpha"],
        dropout=0.0,
    )
    weights = torch.load(adapter_dir / config.get("adapter_file", "adapter_model.pt"), map_location="cpu", weights_only=True)
    missing, unexpected = model.load_state_dict(weights, strict=False)
    expected_count = config.get("adapter_tensor_count", len(weights))
    loaded = len(weights) - len(unexpected)
    if unexpected or loaded != expected_count or any(not (key.endswith(".lora_A") or key.endswith(".lora_B")) for key in unexpected):
        raise RuntimeError(f"Adapter load mismatch: loaded={loaded}, unexpected={len(unexpected)}")
    return config
