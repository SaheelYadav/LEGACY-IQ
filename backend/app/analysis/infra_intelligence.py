"""Wave 2.3 — Deterministic Infrastructure Intelligence Extractor (Dockerfile, Docker Compose, Kubernetes, Terraform, CloudFormation & Env Configs)."""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    yaml = None

SECRET_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
)


def sanitize_config_value(key: str, value: Any) -> Any:
    """Redact potential secret values while preserving key names and safe structural metadata."""
    lower_k = key.lower()
    if any(s in lower_k for s in SECRET_KEY_SUBSTRINGS):
        return "[REDACTED]"
    if isinstance(value, str) and len(value) > 8:
        if re.match(r"^(?:sk-|ghp_|xox[baprs]-|AIza)[A-Za-z0-9_\-]{12,}$", value.strip()):
            return "[REDACTED]"
    return value


@dataclass
class ExtractedInfraResource:
    iac_tool: str  # DOCKERFILE | DOCKER_COMPOSE | KUBERNETES | TERRAFORM | CLOUDFORMATION
    resource_type: str  # container_image, compose_service, k8s_deployment, aws_db_instance, etc.
    resource_name: str
    configuration_attributes: dict[str, Any] = field(default_factory=dict)
    depends_on_names: list[str] = field(default_factory=list)
    start_line: int = 1
    end_line: int = 1
    snippet: str = ""


@dataclass
class InfraExtractionResult:
    resources: list[ExtractedInfraResource] = field(default_factory=list)


def parse_dockerfile(raw_text: str, relative_path: str) -> InfraExtractionResult:
    """Parse a Dockerfile into base images, exposed ports, env keys, and runtime directives."""
    result = InfraExtractionResult()
    lines = raw_text.splitlines()
    base_images: list[str] = []
    exposed_ports: list[str] = []
    env_keys: list[str] = []
    has_healthcheck = False
    runs_as_non_root = False
    workdir: str | None = None
    entrypoint: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        upper = stripped.upper()
        if upper.startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                base_images.append(parts[1])
        elif upper.startswith("EXPOSE "):
            exposed_ports.extend(stripped.split()[1:])
        elif upper.startswith("ENV "):
            env_body = stripped[4:].strip()
            key = env_body.split("=", 1)[0].split()[0].strip()
            if key:
                env_keys.append(key)
        elif upper.startswith("HEALTHCHECK "):
            has_healthcheck = True
        elif upper.startswith("USER "):
            usr = stripped[5:].strip().lower()
            if usr not in ("root", "0"):
                runs_as_non_root = True
        elif upper.startswith("WORKDIR "):
            workdir = stripped[8:].strip()
        elif upper.startswith(("ENTRYPOINT ", "CMD ")):
            entrypoint = stripped

    if base_images:
        res_name = posixpath.basename(posixpath.dirname(relative_path)) or posixpath.basename(
            relative_path
        )
        result.resources.append(
            ExtractedInfraResource(
                iac_tool="DOCKERFILE",
                resource_type="container_image",
                resource_name=res_name,
                configuration_attributes={
                    "base_images": base_images,
                    "exposed_ports": exposed_ports,
                    "env_keys": sorted(set(env_keys)),
                    "has_healthcheck": has_healthcheck,
                    "runs_as_non_root": runs_as_non_root,
                    "workdir": workdir,
                    "entrypoint": entrypoint,
                },
                depends_on_names=[],
                start_line=1,
                end_line=max(1, len(lines)),
                snippet=raw_text[:800],
            )
        )
    return result


def parse_yaml_or_json_iac(raw_text: str, relative_path: str) -> InfraExtractionResult:
    """
    Inspect YAML/JSON manifests for Docker Compose (`services:`), Kubernetes (`apiVersion` + `kind`),
    or AWS CloudFormation (`AWSTemplateFormatVersion` / `Resources:`).
    """
    result = InfraExtractionResult()
    if yaml is None:
        return result

    docs: list[Any] = []
    try:
        if raw_text.lstrip().startswith("{"):
            docs = [json.loads(raw_text)]
        else:
            docs = list(yaml.safe_load_all(raw_text))
    except Exception:
        return result

    total_lines = max(1, raw_text.count("\n") + 1)

    for doc in docs:
        if not isinstance(doc, dict):
            continue

        # 1. Docker Compose (`services:`)
        if isinstance(doc.get("services"), dict) and "apiVersion" not in doc:
            for svc_name, svc_cfg in doc["services"].items():
                if not isinstance(svc_cfg, dict):
                    continue
                idx = raw_text.find(f"{svc_name}:")
                sline = raw_text.count("\n", 0, idx) + 1 if idx >= 0 else 1

                deps_raw = svc_cfg.get("depends_on")
                deps: list[str] = []
                if isinstance(deps_raw, list):
                    deps = [str(d) for d in deps_raw]
                elif isinstance(deps_raw, dict):
                    deps = [str(k) for k in deps_raw.keys()]

                env_raw = svc_cfg.get("environment")
                env_keys: list[str] = []
                if isinstance(env_raw, dict):
                    env_keys = [str(k) for k in env_raw.keys()]
                elif isinstance(env_raw, list):
                    env_keys = [str(item).split("=", 1)[0] for item in env_raw]

                ports_raw = svc_cfg.get("ports")
                ports = [str(p) for p in ports_raw] if isinstance(ports_raw, list) else []

                result.resources.append(
                    ExtractedInfraResource(
                        iac_tool="DOCKER_COMPOSE",
                        resource_type="compose_service",
                        resource_name=str(svc_name),
                        configuration_attributes={
                            "image": svc_cfg.get("image"),
                            "build": svc_cfg.get("build"),
                            "ports": ports,
                            "env_keys": sorted(set(env_keys)),
                            "depends_on": deps,
                            "privileged": bool(svc_cfg.get("privileged", False)),
                            "has_healthcheck": "healthcheck" in svc_cfg,
                        },
                        depends_on_names=deps,
                        start_line=sline,
                        end_line=min(total_lines, sline + 25),
                        snippet=f"{svc_name}: {json.dumps(svc_cfg, default=str)[:600]}",
                    )
                )

        # 2. Kubernetes Manifest (`apiVersion` and `kind`)
        elif "apiVersion" in doc and "kind" in doc:
            kind = str(doc.get("kind"))
            metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            res_name = str(metadata.get("name") or posixpath.basename(relative_path))
            namespace = str(metadata.get("namespace") or "default")
            spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}

            containers_info: list[dict[str, Any]] = []
            pod_spec = spec.get("template", {}).get("spec", {}) if isinstance(spec.get("template"), dict) else spec
            if isinstance(pod_spec, dict) and isinstance(pod_spec.get("containers"), list):
                for c in pod_spec["containers"]:
                    if isinstance(c, dict):
                        c_envs = [
                            str(e.get("name"))
                            for e in (c.get("env") or [])
                            if isinstance(e, dict) and e.get("name")
                        ]
                        containers_info.append(
                            {
                                "name": c.get("name"),
                                "image": c.get("image"),
                                "env_keys": c_envs,
                            }
                        )

            result.resources.append(
                ExtractedInfraResource(
                    iac_tool="KUBERNETES",
                    resource_type=f"k8s_{kind.lower()}",
                    resource_name=res_name,
                    configuration_attributes={
                        "apiVersion": doc.get("apiVersion"),
                        "kind": kind,
                        "namespace": namespace,
                        "replicas": spec.get("replicas"),
                        "containers": containers_info,
                    },
                    depends_on_names=[],
                    start_line=1,
                    end_line=total_lines,
                    snippet=raw_text[:800],
                )
            )

        # 3. AWS CloudFormation (`AWSTemplateFormatVersion` or `Resources` with `Type: AWS::...`)
        elif isinstance(doc.get("Resources"), dict):
            for logical_id, res_def in doc["Resources"].items():
                if not isinstance(res_def, dict) or "Type" not in res_def:
                    continue
                res_type = str(res_def["Type"])
                props = res_def.get("Properties") if isinstance(res_def.get("Properties"), dict) else {}
                sanitized_props = {
                    str(k): sanitize_config_value(str(k), v) for k, v in list(props.items())[:20]
                }
                deps_raw = res_def.get("DependsOn")
                deps = (
                    [str(deps_raw)]
                    if isinstance(deps_raw, str)
                    else ([str(d) for d in deps_raw] if isinstance(deps_raw, list) else [])
                )
                idx = raw_text.find(str(logical_id))
                sline = raw_text.count("\n", 0, idx) + 1 if idx >= 0 else 1
                result.resources.append(
                    ExtractedInfraResource(
                        iac_tool="CLOUDFORMATION",
                        resource_type=res_type[:128],
                        resource_name=str(logical_id)[:255],
                        configuration_attributes={
                            "properties": sanitized_props,
                            "depends_on": deps,
                        },
                        depends_on_names=deps,
                        start_line=sline,
                        end_line=min(total_lines, sline + 20),
                        snippet=f"{logical_id} ({res_type}): {json.dumps(sanitized_props, default=str)[:500]}",
                    )
                )

    return result


_TF_RESOURCE_RE = re.compile(
    r"(resource|module|data)\s+\"([^\"]+)\"(?:\s+\"([^\"]+)\")?\s*\{([^}]*)\}",
    re.MULTILINE | re.DOTALL,
)
_TF_KV_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+)$", re.MULTILINE)


def parse_terraform_hcl(raw_text: str, relative_path: str) -> InfraExtractionResult:
    """Parse Terraform `.tf` HCL blocks into infrastructure resources and dependencies."""
    result = InfraExtractionResult()
    for match in _TF_RESOURCE_RE.finditer(raw_text):
        block_kind = match.group(1)
        first_label = match.group(2)
        second_label = match.group(3)
        body = match.group(4)
        sline = raw_text.count("\n", 0, match.start()) + 1
        eline = raw_text.count("\n", 0, match.end()) + 1

        if block_kind == "module":
            res_type = "terraform_module"
            res_name = first_label
        elif block_kind == "data":
            res_type = f"data.{first_label}"
            res_name = second_label or first_label
        else:
            res_type = first_label
            res_name = second_label or first_label

        attrs: dict[str, Any] = {}
        for kvm in _TF_KV_RE.finditer(body):
            k = kvm.group(1).strip()
            v = kvm.group(2).strip().strip("\"")
            attrs[k] = sanitize_config_value(k, v)

        # Detect explicit references to other Terraform resources
        deps = re.findall(r"\b(aws_[a-z0-9_]+\.[a-z0-9_]+|google_[a-z0-9_]+\.[a-z0-9_]+|azurerm_[a-z0-9_]+\.[a-z0-9_]+)\b", body)
        attrs["referenced_resources"] = sorted(set(deps))

        result.resources.append(
            ExtractedInfraResource(
                iac_tool="TERRAFORM",
                resource_type=res_type[:128],
                resource_name=res_name[:255],
                configuration_attributes=attrs,
                depends_on_names=sorted(set(deps)),
                start_line=sline,
                end_line=eline,
                snippet=match.group(0)[:700],
            )
        )
    return result

