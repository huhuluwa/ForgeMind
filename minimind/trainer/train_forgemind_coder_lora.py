"""Train a small ForgeMind-Coder LoRA adapter on a local SFT JSONL file."""

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from model.lora_adapter import inject_lora, load_adapter, save_adapter


DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
DEFAULT_TARGET_MODULES = ("q_proj", "v_proj")
ALLOWED_TARGET_MODULES = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fit_conversation(messages, tokenizer, max_length):
    """Fit a complete assistant target while preserving the original task request."""
    if len(messages) < 2 or messages[-1].get("role") != "assistant":
        return None

    def encode(candidate):
        prefix = tokenizer.apply_chat_template(candidate[:-1], tokenize=True, add_generation_prompt=True)
        full = tokenizer.apply_chat_template(candidate, tokenize=True, add_generation_prompt=False)
        if full[:len(prefix)] != prefix:
            raise ValueError("Chat template prefix mismatch")
        return prefix, full[len(prefix):]

    prefix, target = encode(messages)
    if not target:
        return None
    if len(prefix) + len(target) <= max_length:
        return prefix, target, False

    base_end = 2 if (len(messages) > 2 and messages[0].get("role") == "system"
                     and messages[1].get("role") == "user") else 1
    base = messages[:base_end]
    base_prefix, base_target = encode(base + [messages[-1]])
    if len(base_prefix) + len(base_target) > max_length:
        return None

    history = messages[base_end:-1]
    units = []
    index = 0
    while index < len(history):
        end = index + 1
        if (history[index].get("role") == "assistant" and history[index].get("tool_calls")
                and end < len(history) and history[end].get("role") == "tool"):
            end += 1
        units.append(history[index:end])
        index = end

    selected = []
    for unit in reversed(units):
        candidate = base + [message for group in [unit] + selected for message in group] + [messages[-1]]
        candidate_prefix, candidate_target = encode(candidate)
        if len(candidate_prefix) + len(candidate_target) <= max_length:
            selected.insert(0, unit)
    compact = base + [message for group in selected for message in group] + [messages[-1]]
    compact_prefix, compact_target = encode(compact)
    return compact_prefix, compact_target, True


def read_rows(path, tokenizer, max_length):
    rows = []
    seen = compacted = dropped_for_length = 0
    with open(path, encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                messages = row["conversations"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"Invalid conversations JSONL at line {line_no}") from exc
            user_text = "\n".join(message.get("content", "") for message in messages
                                    if message.get("role") == "user")
            if not user_text.strip():
                continue
            group_id = hashlib.sha256(user_text.encode("utf-8")).hexdigest()
            if len(messages) < 2 or messages[-1].get("role") != "assistant":
                continue
            seen += 1
            fitted = fit_conversation(messages, tokenizer, max_length)
            if fitted is None:
                dropped_for_length += 1
                continue
            prefix, target, was_compacted = fitted
            compacted += int(was_compacted)
            input_ids = prefix + target
            labels = [-100] * len(prefix) + target
            rows.append((input_ids, labels, group_id))
    print("data_fit_audit=" + json.dumps({"trainable_rows": len(rows), "rows_seen": seen,
          "context_compacted": compacted, "dropped_to_preserve_request_and_target": dropped_for_length,
          "max_length": max_length}, ensure_ascii=False), flush=True)
    if not rows:
        raise ValueError("No trainable examples fit without truncating the task request or assistant target")
    return rows


def split_by_task_group(rows, validation_fraction, seed):
    """Keep every trajectory derived from one user request in a single split."""
    if not 0.05 <= validation_fraction < 0.5:
        raise ValueError("validation_fraction must be in [0.05, 0.5)")
    groups = {}
    for row in rows:
        groups.setdefault(row[2], []).append(row)
    group_ids = list(groups)
    if len(group_ids) < 2:
        raise ValueError("At least two distinct user tasks are required for a leakage-safe validation split")
    rng = random.Random(seed)
    rng.shuffle(group_ids)
    target = max(1, int(len(rows) * validation_fraction))
    validation_ids, validation_size = set(), 0
    for group_id in group_ids:
        if validation_size >= target:
            break
        group_size = len(groups[group_id])
        if len(rows) - validation_size - group_size < 1:
            continue
        validation_ids.add(group_id)
        validation_size += group_size
    train_rows = [row for row in rows if row[2] not in validation_ids]
    validation_rows = [row for row in rows if row[2] in validation_ids]
    train_ids = {row[2] for row in train_rows}
    heldout_ids = {row[2] for row in validation_rows}
    if train_ids & heldout_ids:
        raise AssertionError("user-task leakage detected across training and validation")
    if not train_rows or not validation_rows:
        raise ValueError("Could not create non-empty training and validation groups")
    return train_rows, validation_rows, len(train_ids), len(heldout_ids)


def evaluate_loss(model, rows, device, limit):
    was_training = model.training
    model.eval()
    values = []
    sample_count = min(limit, len(rows))
    with torch.inference_mode():
        for index, (input_ids, labels, _group_id) in enumerate(rows[:limit], start=1):
            inputs = torch.tensor([input_ids], dtype=torch.long, device=device)
            targets = torch.tensor([labels], dtype=torch.long, device=device)
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                result = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=targets)
            if not torch.isfinite(result.loss):
                raise FloatingPointError("Non-finite validation loss")
            values.append(float(result.loss.float().cpu()))
            if index % 8 == 0 or index == sample_count:
                print(f"validation_progress={index}/{sample_count}", flush=True)
    if was_training:
        model.train()
    return sum(values) / len(values) if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="SFT JSONL with conversations")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-model", default=DEFAULT_MODEL)
    parser.add_argument("--base-model-id", default=DEFAULT_MODEL, help="Canonical Hub ID recorded for deployment")
    parser.add_argument("--model-name", default="", help="Public ForgeMind model name recorded in adapter metadata")
    parser.add_argument("--base-revision", default="", help="Pinned base-model commit SHA; resolved when omitted")
    parser.add_argument("--data-manifest", default="", help="Optional JSON manifest for the SFT data")
    parser.add_argument("--max-rows", type=int, default=128, help="Deterministic random subset; 0 uses all rows")
    parser.add_argument("--max-steps", type=int, default=64, help="0 means train the selected subset for one epoch")
    parser.add_argument("--epochs", type=int, default=1, help="Pass over the selected training rows; max-steps still caps total microsteps")
    parser.add_argument("--validation-fraction", type=float, default=0.1)
    parser.add_argument("--validation-rows", type=int, default=32)
    parser.add_argument("--eval-every", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--rank", type=int, default=8)
    parser.add_argument("--target-modules", default=",".join(DEFAULT_TARGET_MODULES),
                        help="Comma-separated Linear layer suffixes (Qwen-style q/k/v/o/gate/up/down projections)")
    parser.add_argument("--alpha", type=int, default=16)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--accumulation-steps", type=int, default=8)
    parser.add_argument("--quantization", choices=["none", "nf4"], default="none",
                        help="Use NF4 QLoRA for lower VRAM; adapter output remains compatible with the full-precision base")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--resume-adapter", default="", help="Load LoRA weights from a prior adapter checkpoint")
    parser.add_argument("--resume-state", default="", help="Restore optimizer and progress from trainer_state.pt")
    args = parser.parse_args()
    target_modules = tuple(dict.fromkeys(name.strip() for name in args.target_modules.split(",") if name.strip()))
    if not target_modules or set(target_modules) - ALLOWED_TARGET_MODULES:
        parser.error(f"--target-modules must be a non-empty subset of {sorted(ALLOWED_TARGET_MODULES)}")
    if args.resume_state and not args.resume_adapter:
        parser.error("--resume-state requires --resume-adapter from the same checkpoint")
    if args.resume_adapter and not Path(args.resume_adapter).is_dir():
        parser.error(f"Resume adapter directory does not exist: {args.resume_adapter}")
    if args.resume_state and not Path(args.resume_state).is_file():
        parser.error(f"Resume state file does not exist: {args.resume_state}")
    if args.max_rows < 0 or args.max_steps < 0 or args.epochs < 1 or args.max_length < 64 or args.rank < 1 or args.accumulation_steps < 1:
        parser.error("Invalid training limits; epochs/rank/accumulation must be positive and max-length must be >=64")
    if not torch.cuda.is_available():
        parser.error("This pilot is configured for a CUDA GPU; use the MiniMind CPU smoke path for CPU-only systems")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda:0")
    base_revision = args.base_revision
    model_source = args.base_model
    if not Path(args.base_model).exists() and not base_revision:
        from huggingface_hub import HfApi
        base_revision = HfApi().model_info(args.base_model).sha

    tokenizer = AutoTokenizer.from_pretrained(model_source, revision=base_revision or None)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    if args.quantization == "nf4":
        from transformers import BitsAndBytesConfig
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_source, revision=base_revision or None, dtype=torch.float16,
            quantization_config=quantization_config,
            device_map={"": torch.cuda.current_device()},
            low_cpu_mem_usage=True,
        )
        for module in model.modules():
            if "norm" in module.__class__.__name__.lower() and getattr(module, "weight", None) is not None:
                module.to(dtype=torch.float32)
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_source, revision=base_revision or None, dtype=torch.float16
        ).to(device)
    model.config.use_cache = False
    try:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    except TypeError:
        model.gradient_checkpointing_enable()
    resume_config = None
    if args.resume_adapter:
        resume_config = load_adapter(model, args.resume_adapter)
        expected = {
            "base_model": args.base_model_id,
            "rank": args.rank,
            "alpha": args.alpha,
            "dropout": args.dropout,
            "learning_rate": args.learning_rate,
            "max_length": args.max_length,
            "quantization": args.quantization,
            "target_modules": list(target_modules),
            "dataset_sha256": sha256_file(args.data),
        }
        for key, value in expected.items():
            if resume_config.get(key) != value:
                parser.error(f"Resume adapter mismatch for {key}: {resume_config.get(key)!r} != {value!r}")
        if "seed" in resume_config and resume_config["seed"] != args.seed:
            parser.error(f"Resume adapter mismatch for seed: {resume_config['seed']!r} != {args.seed!r}")
        for module in model.modules():
            if hasattr(module, "lora_A") and hasattr(module, "dropout"):
                module.dropout = torch.nn.Dropout(args.dropout).to(module.lora_A.device) if args.dropout else torch.nn.Identity()
    else:
        inject_lora(model, target_modules, rank=args.rank, alpha=args.alpha, dropout=args.dropout)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate, weight_decay=0.01)
    scaler = torch.amp.GradScaler("cuda", enabled=True)

    rows = read_rows(args.data, tokenizer, args.max_length)
    if len(rows) < 2 or not 0.05 <= args.validation_fraction < 0.5 or args.validation_rows < 1 or args.eval_every < 1:
        parser.error("Need at least two examples, validation-fraction in [0.05, 0.5), and positive eval limits")
    training_rows, validation_rows, training_groups, validation_groups = split_by_task_group(
        rows, args.validation_fraction, args.seed
    )
    rng = random.Random(args.seed)
    rng.shuffle(training_rows)
    rng.shuffle(validation_rows)
    if args.max_rows:
        training_rows = rng.sample(training_rows, min(args.max_rows, len(training_rows)))
    training_groups = len({row[2] for row in training_rows})
    epoch_steps = len(training_rows) * args.epochs
    planned_steps = min(args.max_steps, epoch_steps) if args.max_steps else epoch_steps
    optimizer_updates = (planned_steps + args.accumulation_steps - 1) // args.accumulation_steps
    if planned_steps < 1:
        parser.error("No optimization steps were requested")

    start_step = int(resume_config.get("training_step", resume_config.get("best_step", 0))) if resume_config else 0
    if start_step < 0 or start_step >= planned_steps:
        parser.error(f"Resume step {start_step} must be below planned max steps {planned_steps}")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    start = time.perf_counter()
    recent_losses = []
    loss_sum = 0.0
    loss_count = 0
    skipped_optimizer_updates = 0
    validation_sample = validation_rows[:args.validation_rows]
    validation_history = []
    initial_validation_loss = evaluate_loss(model, validation_sample, device, args.validation_rows)
    validation_history.append({"step": start_step, "loss": initial_validation_loss})
    best_validation_loss = float(resume_config.get("best_validation_loss", initial_validation_loss)) if resume_config else initial_validation_loss
    best_step = start_step if resume_config else 0
    best_adapter = {name: parameter.detach().cpu().clone() for name, parameter in model.named_parameters()
                    if name.endswith(".lora_A") or name.endswith(".lora_B")}
    if args.resume_state:
        state_path = Path(args.resume_state)
        if not state_path.is_file():
            parser.error(f"Resume state does not exist: {state_path}")
        state = torch.load(state_path, map_location="cpu", weights_only=False)
        if state.get("dataset_sha256") != sha256_file(args.data) or state.get("planned_steps") != planned_steps:
            parser.error("Resume state data hash or planned step count differs from this run")
        if int(state.get("step", -1)) != int(resume_config.get("training_step", -2)):
            parser.error("Resume adapter and optimizer state are from different training steps")
        optimizer.load_state_dict(state["optimizer"])
        scaler.load_state_dict(state["scaler"])
        start_step = int(state["step"])
        loss_sum = float(state.get("loss_sum", 0.0))
        loss_count = int(state.get("loss_count", 0))
        skipped_optimizer_updates = int(state.get("skipped_optimizer_updates", 0))
        best_validation_loss = float(state["best_validation_loss"])
        best_step = int(state["best_step"])
        best_adapter = state["best_adapter"]
        validation_history = state.get("validation_history", validation_history)
        random.setstate(state["python_rng_state"])
        torch.set_rng_state(state["torch_rng_state"])
        torch.cuda.set_rng_state_all(state["cuda_rng_state"])
        if start_step < 0 or start_step >= planned_steps:
            parser.error(f"Resume state step {start_step} must be below planned max steps {planned_steps}")
        print(f"resumed_training_state step={start_step}", flush=True)
    for step in range(start_step, planned_steps):
        input_ids, labels, _group_id = training_rows[step % len(training_rows)]
        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=device)
        label_tensor = torch.tensor([labels], dtype=torch.long, device=device)
        attention_mask = torch.ones_like(input_tensor)
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            result = model(input_ids=input_tensor, attention_mask=attention_mask, labels=label_tensor)
            loss = result.loss
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Non-finite LoRA loss at step {step + 1}")
        (scaler.scale(loss / args.accumulation_steps)).backward()
        loss_value = float(loss.detach().float().cpu())
        recent_losses.append(loss_value)
        loss_sum += loss_value
        loss_count += 1
        update_now = (step + 1) % args.accumulation_steps == 0 or step + 1 == planned_steps
        if update_now:
            scaler.unscale_(optimizer)
            tail = (step + 1) % args.accumulation_steps
            if tail:
                factor = args.accumulation_steps / tail
                for parameter in trainable:
                    if parameter.grad is not None:
                        parameter.grad.mul_(factor)
            # GradScaler detects non-finite unscaled gradients and skips the optimizer
            # update. Raising here would abort before scaler.step()/update() could lower
            # the scale and recover, leaving the run without its best checkpoint.
            scale_before = scaler.get_scale()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0, error_if_nonfinite=False)
            scaler.step(optimizer)
            scaler.update()
            if scaler.get_scale() < scale_before:
                skipped_optimizer_updates += 1
                print(f"warning=nonfinite_gradient_update_skipped step={step + 1} scaler={scale_before}->{scaler.get_scale()}", flush=True)
            optimizer.zero_grad(set_to_none=True)
        if (step + 1) % args.log_every == 0 or step + 1 == planned_steps:
            recent_losses = recent_losses[-args.log_every:]
            print(f"step={step + 1}/{planned_steps} loss={loss_value:.4f} avg_loss={sum(recent_losses) / len(recent_losses):.4f}", flush=True)
        del input_tensor, label_tensor, attention_mask, result, loss
        if (step + 1) % args.eval_every == 0 or step + 1 == planned_steps:
            validation_loss = evaluate_loss(model, validation_sample, device, args.validation_rows)
            validation_history.append({"step": step + 1, "loss": validation_loss})
            print(f"validation_step={step + 1} val_loss={validation_loss:.4f}", flush=True)
            if validation_loss < best_validation_loss:
                best_validation_loss = validation_loss
                best_step = step + 1
                best_adapter = {name: parameter.detach().cpu().clone() for name, parameter in model.named_parameters()
                                if name.endswith(".lora_A") or name.endswith(".lora_B")}
                checkpoint_dir = Path(args.output_dir) / "best_checkpoint"
                checkpoint_metadata = {
                    "model_name": args.model_name or "ForgeMind-Coder-training-checkpoint",
                    "base_model": args.base_model_id,
                    "base_revision": base_revision or "local-unpinned",
                    "dataset": f"intermediate checkpoint for {Path(args.data).name}",
                    "dataset_sha256": sha256_file(args.data),
                    "best_step": best_step,
                    "best_validation_loss": best_validation_loss,
                    "max_length": args.max_length,
                    "rank": args.rank,
                    "alpha": args.alpha,
                    "dropout": args.dropout,
                    "learning_rate": args.learning_rate,
                    "seed": args.seed,
                    "target_modules": list(target_modules),
                    "quantization": args.quantization,
                }
                save_adapter(model, checkpoint_dir, checkpoint_metadata)
                print(f"best_checkpoint_saved={checkpoint_dir} step={best_step}", flush=True)
            latest_dir = Path(args.output_dir) / "latest_checkpoint"
            latest_metadata = {
                "model_name": args.model_name or "ForgeMind-Coder-training-resume",
                "base_model": args.base_model_id,
                "base_revision": base_revision or "local-unpinned",
                "dataset": Path(args.data).name,
                "dataset_sha256": sha256_file(args.data),
                "training_step": step + 1,
                "best_step": best_step,
                "best_validation_loss": best_validation_loss,
                "max_length": args.max_length,
                "rank": args.rank,
                "alpha": args.alpha,
                "dropout": args.dropout,
                "learning_rate": args.learning_rate,
                "seed": args.seed,
                "target_modules": list(target_modules),
                "quantization": args.quantization,
            }
            save_adapter(model, latest_dir, latest_metadata)
            trainer_state = {
                "step": step + 1,
                "planned_steps": planned_steps,
                "dataset_sha256": sha256_file(args.data),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "python_rng_state": random.getstate(),
                "torch_rng_state": torch.get_rng_state(),
                "cuda_rng_state": torch.cuda.get_rng_state_all(),
                "loss_sum": loss_sum,
                "loss_count": loss_count,
                "skipped_optimizer_updates": skipped_optimizer_updates,
                "best_validation_loss": best_validation_loss,
                "best_step": best_step,
                "best_adapter": best_adapter,
                "validation_history": validation_history,
            }
            state_tmp = latest_dir / "trainer_state.pt.tmp"
            torch.save(trainer_state, state_tmp)
            state_tmp.replace(latest_dir / "trainer_state.pt")
            print(f"training_checkpoint_saved={latest_dir} step={step + 1}", flush=True)
    for name, parameter in model.named_parameters():
        if name in best_adapter:
            parameter.data.copy_(best_adapter[name].to(device=parameter.device, dtype=parameter.dtype))
    model.eval()

    manifest_path = Path(args.data_manifest) if args.data_manifest else Path(args.data + ".manifest.json")
    data_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    suffix = args.base_model_id.split("Coder-", 1)[-1].split("-Instruct", 1)[0]
    metadata = {
        "model_name": args.model_name or f"ForgeMind-Coder-{suffix}-LoRA",
        "base_model": args.base_model_id,
        "base_revision": base_revision or "local-unpinned",
        "base_license": "Apache-2.0 (official Qwen model card)",
        "dataset": data_manifest.get("dataset") if data_manifest else "local-jsonl",
        "dataset_revision": data_manifest.get("dataset_revision") if data_manifest else None,
        "dataset_license_note": data_manifest.get("declared_license") if data_manifest else "user-provided; review before use",
        "dataset_sha256": sha256_file(args.data),
        "dataset_manifest_sha256": sha256_file(manifest_path) if manifest_path.exists() else None,
        "rows_in_subset": len(training_rows),
        "training_examples_seen": planned_steps,
        "epochs_requested": args.epochs,
        "epochs_completed": round(planned_steps / len(training_rows), 6),
        "steps": planned_steps,
        "microsteps": planned_steps,
        "optimizer_updates": optimizer_updates,
        "skipped_optimizer_updates": skipped_optimizer_updates,
        "mean_loss": loss_sum / max(loss_count, 1),
        "mean_loss_scope": "resumed_segment" if resume_config else "full_run",
        "final_loss": loss_value,
        "validation_rows": len(validation_sample),
        "training_task_groups": training_groups,
        "validation_task_groups": validation_groups,
        "initial_validation_loss": initial_validation_loss,
        "best_validation_loss": best_validation_loss,
        "best_step": best_step,
        "validation_history": validation_history,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "seed": args.seed,
        "max_length": args.max_length,
        "rank": args.rank,
        "alpha": args.alpha,
        "dropout": args.dropout,
        "learning_rate": args.learning_rate,
        "accumulation_steps": args.accumulation_steps,
        "target_modules": list(target_modules),
        "quantization": args.quantization,
        "resumed_from_step": int(resume_config.get("training_step", resume_config.get("best_step", 0))) if resume_config else 0,
        "optimizer_reset_on_resume": bool(resume_config and not args.resume_state),
        "trainable_parameters": sum(p.numel() for p in trainable),
        "total_parameters": sum(p.numel() for p in model.parameters()),
        "gpu": torch.cuda.get_device_name(device),
        "torch_version": torch.__version__,
        "transformers_version": __import__("transformers").__version__,
    }
    save_adapter(model, args.output_dir, metadata)
    print(json.dumps({"output_dir": args.output_dir, "microsteps": planned_steps,
                      "optimizer_updates": optimizer_updates, "final_loss": loss_value,
                      "elapsed_seconds": metadata["elapsed_seconds"], "gpu": metadata["gpu"]}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
