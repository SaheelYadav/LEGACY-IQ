"""Wave 2.2 — Deterministic API Intelligence Extractor (OpenAPI/Swagger, Source REST Controllers, GraphQL Schemas & Auth Metadata)."""

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


@dataclass
class ExtractedApiEndpoint:
    service_name: str
    protocol: str  # REST | GRAPHQL | GRPC | SOAP | MESSAGE_CONSUMER
    base_path: str | None
    http_method: str  # GET | POST | PUT | DELETE | PATCH | RPC | SUB
    route_pattern: str
    handler_qualified_name: str | None = None
    handler_name: str | None = None
    auth_required_inferred: bool | None = None
    request_schema_json: dict[str, Any] | None = None
    response_schema_json: dict[str, Any] | None = None
    start_line: int = 1
    end_line: int = 1
    snippet: str = ""


@dataclass
class ApiExtractionResult:
    endpoints: list[ExtractedApiEndpoint] = field(default_factory=list)


def _normalize_route(prefix: str | None, route: str) -> str:
    r = route.strip().strip("\"'`")
    if not r.startswith("/"):
        r = "/" + r
    if prefix:
        p = prefix.strip().strip("\"'`")
        if p and p != "/":
            if not p.startswith("/"):
                p = "/" + p
            r = p.rstrip("/") + "/" + r.lstrip("/")
    return re.sub(r"//+", "/", r)


def _find_line_number(text: str, needle: str) -> int:
    idx = text.find(needle)
    if idx < 0:
        return 1
    return text.count("\n", 0, idx) + 1


def parse_openapi_or_swagger(raw_text: str, relative_path: str) -> ApiExtractionResult:
    """Parse OpenAPI 3.x or Swagger 2.0 JSON/YAML specifications into services and endpoints."""
    result = ApiExtractionResult()
    parsed: Any = None
    stripped = raw_text.lstrip()
    try:
        if stripped.startswith("{"):
            parsed = json.loads(raw_text)
        elif yaml is not None:
            parsed = yaml.safe_load(raw_text)
    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        return result

    is_openapi = "openapi" in parsed or "swagger" in parsed
    if not is_openapi or "paths" not in parsed or not isinstance(parsed.get("paths"), dict):
        return result

    info = parsed.get("info") if isinstance(parsed.get("info"), dict) else {}
    service_name = str(info.get("title") or posixpath.basename(relative_path)).strip()[:255]

    base_path: str | None = None
    if isinstance(parsed.get("basePath"), str):
        base_path = parsed["basePath"]
    elif isinstance(parsed.get("servers"), list) and parsed["servers"]:
        first_srv = parsed["servers"][0]
        if isinstance(first_srv, dict) and isinstance(first_srv.get("url"), str):
            base_path = first_srv["url"]

    global_security = bool(parsed.get("security"))

    http_verbs = {"get", "post", "put", "delete", "patch", "options", "head"}
    for path_key, path_item in parsed["paths"].items():
        if not isinstance(path_item, dict):
            continue
        line_no = _find_line_number(raw_text, str(path_key))
        for verb, op_spec in path_item.items():
            if verb.lower() not in http_verbs or not isinstance(op_spec, dict):
                continue
            method = verb.upper()
            op_security = op_spec.get("security")
            if op_security == []:
                auth_req = False
            elif op_security is not None:
                auth_req = bool(op_security)
            else:
                auth_req = global_security

            req_schema: dict[str, Any] = {}
            if isinstance(op_spec.get("requestBody"), dict):
                req_schema["requestBody"] = op_spec["requestBody"]
            if isinstance(op_spec.get("parameters"), list):
                req_schema["parameters"] = op_spec["parameters"]

            resp_schema: dict[str, Any] = {}
            if isinstance(op_spec.get("responses"), dict):
                resp_schema["responses"] = op_spec["responses"]

            op_id = op_spec.get("operationId")
            result.endpoints.append(
                ExtractedApiEndpoint(
                    service_name=service_name,
                    protocol="REST",
                    base_path=base_path,
                    http_method=method,
                    route_pattern=str(path_key),
                    handler_name=str(op_id) if op_id else None,
                    auth_required_inferred=auth_req,
                    request_schema_json=req_schema or None,
                    response_schema_json=resp_schema or None,
                    start_line=line_no,
                    end_line=min(line_no + 15, max(1, raw_text.count("\n") + 1)),
                    snippet=f"{method} {path_key}: {json.dumps(op_spec)[:600]}",
                )
            )
    return result


_GRAPHQL_TYPE_BLOCK_RE = re.compile(
    r"type\s+(Query|Mutation|Subscription)\s*\{([^}]*)\}",
    re.MULTILINE | re.DOTALL,
)
_GRAPHQL_FIELD_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s*:\s*([A-Za-z0-9_\[\]!]+)",
    re.MULTILINE,
)


def parse_graphql_schema(raw_text: str, relative_path: str) -> ApiExtractionResult:
    """Extract GraphQL Query, Mutation, and Subscription operations from `.graphql`/`.gql` SDL files."""
    result = ApiExtractionResult()
    service_name = f"graphql:{posixpath.basename(relative_path)}"
    for tmatch in _GRAPHQL_TYPE_BLOCK_RE.finditer(raw_text):
        root_type = tmatch.group(1)  # Query | Mutation | Subscription
        body = tmatch.group(2)
        block_start_line = raw_text.count("\n", 0, tmatch.start()) + 1
        http_method = "SUB" if root_type == "Subscription" else "RPC"
        for fmatch in _GRAPHQL_FIELD_RE.finditer(body):
            field_name = fmatch.group(1)
            args_raw = (fmatch.group(2) or "").strip()
            return_type = fmatch.group(3).strip()
            line_no = block_start_line + body.count("\n", 0, fmatch.start())
            directive_chunk = body[fmatch.end() : fmatch.end() + 120]
            auth_req = bool(
                re.search(r"@(?:auth|authenticated|hasRole|authorize)", directive_chunk, re.IGNORECASE)
            )
            result.endpoints.append(
                ExtractedApiEndpoint(
                    service_name=service_name,
                    protocol="GRAPHQL",
                    base_path="/graphql",
                    http_method=http_method,
                    route_pattern=f"{root_type}.{field_name}",
                    handler_name=field_name,
                    auth_required_inferred=auth_req,
                    request_schema_json={"arguments": args_raw} if args_raw else None,
                    response_schema_json={"return_type": return_type},
                    start_line=line_no,
                    end_line=line_no,
                    snippet=fmatch.group(0).strip()[:400],
                )
            )
    return result


def extract_api_endpoints_from_code(
    source_text: str,
    language: str,
    module_name: str,
    relative_path: str,
) -> ApiExtractionResult:
    """
    Deterministically discover REST API endpoints, handler symbols, request/response schemas,
    and authentication metadata from source code across Python, Java, JS/TS, and PHP.
    """
    result = ApiExtractionResult()
    service_name = module_name.split(".")[0] if "." in module_name else module_name

    # 1. Python (FastAPI / APIRouter / Flask)
    if language == "python":
        prefix_match = re.search(
            r"APIRouter\s*\([^)]*?prefix\s*=\s*['\"]([^'\"]+)['\"]", source_text
        )
        router_prefix = prefix_match.group(1) if prefix_match else None

        py_route_re = re.compile(
            r"@([A-Za-z_][A-Za-z0-9_]*)\.(get|post|put|delete|patch|route)\s*\(\s*['\"]([^'\"]+)['\"]([^)]*)\)\s*"
            r"(?:@[^\n]+\n\s*)*"
            r"(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)(?:\s*->\s*([^\n:]+))?\s*:",
            re.IGNORECASE | re.DOTALL,
        )
        for m in py_route_re.finditer(source_text):
            verb_raw = m.group(2).upper()
            raw_path = m.group(3)
            decorator_kwargs = m.group(4) or ""
            func_name = m.group(5)
            func_args = m.group(6) or ""
            return_annotation = (m.group(7) or "").strip()

            if verb_raw == "ROUTE":
                methods_m = re.search(r"methods\s*=\s*\[([^\]]+)\]", decorator_kwargs)
                method = (
                    methods_m.group(1).split(",")[0].strip().strip("\"'").upper()
                    if methods_m
                    else "GET"
                )
            else:
                method = verb_raw

            route_pattern = _normalize_route(router_prefix, raw_path)
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1

            # Check auth inference in decorator or function signature
            combined_sig = f"{decorator_kwargs} {func_args}"
            auth_req = any(
                kw in combined_sig.lower()
                for kw in (
                    "current_user",
                    "require_permission",
                    "require_auth",
                    "jwt",
                    "oauth2",
                    "security",
                    "login_required",
                    "auth",
                    "token",
                )
            )

            resp_model_m = re.search(r"response_model\s*=\s*([A-Za-z0-9_\[\].]+)", decorator_kwargs)
            resp_type = resp_model_m.group(1) if resp_model_m else (return_annotation or None)

            req_params = [
                p.strip()
                for p in func_args.split(",")
                if p.strip()
                and not p.strip().startswith(("session", "db", "request", "self", "cls"))
            ]

            result.endpoints.append(
                ExtractedApiEndpoint(
                    service_name=f"{service_name}-http",
                    protocol="REST",
                    base_path=router_prefix,
                    http_method=method[:16],
                    route_pattern=route_pattern,
                    handler_qualified_name=f"{module_name}.{func_name}",
                    handler_name=func_name,
                    auth_required_inferred=auth_req,
                    request_schema_json={"parameters": req_params[:12]} if req_params else None,
                    response_schema_json={"response_model": resp_type} if resp_type else None,
                    start_line=sline,
                    end_line=eline,
                    snippet=m.group(0)[:600],
                )
            )

    # 2. Java (Spring Boot @RestController / @RequestMapping / @GetMapping / @PostMapping)
    elif language == "java":
        cls_map_m = re.search(
            r"@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]+)\"\s*\)",
            source_text,
        )
        base_prefix = cls_map_m.group(1) if cls_map_m else None
        cls_name_m = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", source_text)
        cls_name = cls_name_m.group(1) if cls_name_m else "Controller"

        java_ep_re = re.compile(
            r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*"
            r"(?:\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"[^)]*\))?\s*"
            r"((?:@\w+(?:\((?:[^()]*|\([^()]*\))*\))?\s*)*)"
            r"(?:public|protected|private)\s+(?!class\b|interface\b)([A-Za-z0-9_<>?,\[\]]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)",
            re.DOTALL,
        )
        verb_map = {
            "GetMapping": "GET",
            "PostMapping": "POST",
            "PutMapping": "PUT",
            "DeleteMapping": "DELETE",
            "PatchMapping": "PATCH",
            "RequestMapping": "GET",
        }
        for m in java_ep_re.finditer(source_text):
            ann = m.group(1)
            sub_path = m.group(2) or ""
            extra_anns = m.group(3) or ""
            ret_type = m.group(4).strip()
            method_name = m.group(5)
            params = m.group(6).strip()
            http_method = verb_map.get(ann, "GET")
            route_pattern = _normalize_route(base_prefix, sub_path)
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1
            auth_req = bool(
                re.search(
                    r"@(?:PreAuthorize|Secured|RolesAllowed|RequiresPermissions)",
                    extra_anns,
                )
            )
            result.endpoints.append(
                ExtractedApiEndpoint(
                    service_name=f"{cls_name}",
                    protocol="REST",
                    base_path=base_prefix,
                    http_method=http_method,
                    route_pattern=route_pattern,
                    handler_qualified_name=f"{module_name}.{cls_name}.{method_name}",
                    handler_name=method_name,
                    auth_required_inferred=auth_req,
                    request_schema_json={"parameters": params} if params else None,
                    response_schema_json={"return_type": ret_type},
                    start_line=sline,
                    end_line=eline,
                    snippet=m.group(0)[:600],
                )
            )

    # 3. JavaScript / TypeScript (Express / Fastify / NestJS)
    elif language in ("javascript", "typescript"):
        js_route_re = re.compile(
            r"\b(?:app|router|server)\.(get|post|put|delete|patch)\s*\(\s*['\"`]([^'\"`]+)['\"`]\s*,\s*([^\n;]+)",
            re.IGNORECASE,
        )
        for m in js_route_re.finditer(source_text):
            method = m.group(1).upper()
            route_pattern = _normalize_route(None, m.group(2))
            rest_args = m.group(3)
            sline = source_text.count("\n", 0, m.start()) + 1
            auth_req = any(
                kw in rest_args.lower()
                for kw in ("auth", "jwt", "requirelogin", "verifytoken", "guard", "protect")
            )
            result.endpoints.append(
                ExtractedApiEndpoint(
                    service_name=f"{service_name}-express",
                    protocol="REST",
                    base_path=None,
                    http_method=method,
                    route_pattern=route_pattern,
                    handler_qualified_name=None,
                    handler_name=None,
                    auth_required_inferred=auth_req,
                    start_line=sline,
                    end_line=sline + 3,
                    snippet=m.group(0)[:400],
                )
            )

    # 4. PHP (Laravel `Route::get('/orders', ...)`)
    elif language == "php":
        php_route_re = re.compile(
            r"Route::(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^\n;]+)",
            re.IGNORECASE,
        )
        for m in php_route_re.finditer(source_text):
            method = m.group(1).upper()
            route_pattern = _normalize_route(None, m.group(2))
            handler_part = m.group(3)
            sline = source_text.count("\n", 0, m.start()) + 1
            auth_req = "auth" in handler_part.lower() or "sanctum" in handler_part.lower()
            result.endpoints.append(
                ExtractedApiEndpoint(
                    service_name=f"{service_name}-laravel",
                    protocol="REST",
                    base_path=None,
                    http_method=method,
                    route_pattern=route_pattern,
                    handler_qualified_name=None,
                    handler_name=None,
                    auth_required_inferred=auth_req,
                    start_line=sline,
                    end_line=sline + 1,
                    snippet=m.group(0)[:400],
                )
            )

    return result