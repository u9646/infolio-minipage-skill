#!/usr/bin/env python3
"""Validate and package an offline infolio MiniPage template."""

import argparse
import datetime as dt
from html.parser import HTMLParser
from html import unescape
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile
from urllib.parse import urlsplit, unquote


KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
LOCALE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z")
TEMPLATE_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
APP_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
TYPES = {"text", "url", "number", "boolean", "date", "attachment", "json"}
MIMES = {
    ".html": "text/html", ".htm": "text/html", ".css": "text/css",
    ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
    ".avif": "image/avif", ".ico": "image/x-icon", ".woff": "font/woff",
    ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    ".wasm": "application/wasm", ".txt": "text/plain",
}
TEXT_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs", ".svg"}
FORBIDDEN_RUNTIME_NAMES = {
    "design.md", "readme", "readme.md", "package.json", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "vite.config.js", "vite.config.ts",
    "webpack.config.js", "webpack.config.ts", "tsconfig.json",
}
NETWORK_URL = re.compile(
    r"(?i)(?:https?://[^\s'\"<>]+|(?<!:)//[a-z0-9.-]+\.[a-z]{2,}[^\s'\"<>]*)"
)
CSS_REFERENCE = re.compile(
    r"(?i)(?:url\(\s*(['\"]?)([^)'\"]+)\1\s*\)|@import\s+(?:url\(\s*)?(['\"])([^'\"]+)\3)"
)
JS_IMPORT = re.compile(
    r"(?m)(?:\bimport\s+(?:[^'\"]+?\s+from\s+)?|\bexport\s+[^'\"]+?\s+from\s+|\bimport\s*\()(['\"])([^'\"]+)\1"
)
SVG_REFERENCE = re.compile(r"(?i)\b(?:href|xlink:href)\s*=\s*(['\"])([^'\"]+)\1")
HTML_ATTRIBUTE = re.compile(
    r'''(?P<name>[\w:-]+)\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))'''
)
FORBIDDEN_JS = {
    "fetch": re.compile(r"\bfetch\s*\("),
    "XMLHttpRequest": re.compile(r"\bXMLHttpRequest\b"),
    "WebSocket": re.compile(r"\bWebSocket\b"),
    "EventSource": re.compile(r"\bEventSource\b"),
    "sendBeacon": re.compile(r"\bsendBeacon\s*\("),
    "WebRTC": re.compile(r"\b(?:RTCPeerConnection|webkitRTCPeerConnection|mozRTCPeerConnection)\b"),
    "Worker": re.compile(r"\b(?:Worker|SharedWorker)\s*\("),
    "Service Worker": re.compile(r"\bserviceWorker\b"),
    "importScripts": re.compile(r"\bimportScripts\s*\("),
    "window.open": re.compile(r"\bwindow\.open\s*\("),
    "location navigation": re.compile(
        r"\b(?:window\.|document\.)?location\s*(?:\.|=)|\blocation\.(?:assign|replace)\s*\("
    ),
    "localStorage": re.compile(r"\blocalStorage\b"),
    "sessionStorage": re.compile(r"\bsessionStorage\b"),
    "IndexedDB": re.compile(r"\bindexedDB\b", re.IGNORECASE),
}


class TemplateHTMLParser(HTMLParser):
    def __init__(self, source=""):
        super().__init__(convert_charrefs=True)
        self.doctype = False
        self.charset = False
        self.viewport = False
        self.resources = []
        self.errors = []
        self.labels = set()
        self.controls = []
        self.images = []
        self.picture_depth = 0
        self.image_url_ranges = []
        self.line_offsets = [0, *(match.end() for match in re.finditer("\n", source))]

    def handle_decl(self, decl):
        if decl.lower() == "doctype html":
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        lower = tag.lower()
        if lower == "picture":
            self.picture_depth += 1
        image_attributes = ({"src", "srcset"} if lower == "img" else
                            {"srcset"} if lower == "source" and self.picture_depth else set())
        if image_attributes:
            line, column = self.getpos()
            start = self.line_offsets[line - 1] + column
            for match in HTML_ATTRIBUTE.finditer(self.get_starttag_text()):
                attribute = match.group("name").lower()
                if attribute not in image_attributes:
                    continue
                group = next(key for key in ("double", "single", "bare")
                             if match.group(key) is not None)
                value = unescape(match.group(group))
                candidates = srcset_references(value) if attribute == "srcset" else [value]
                if (any(is_https_image_reference(candidate) for candidate in candidates) and
                        all(is_https_image_reference(candidate) or is_local_reference(candidate)
                            for candidate in candidates)):
                    self.image_url_ranges.append((start + match.start(group), start + match.end(group)))
        if lower == "meta":
            if values.get("charset", "").lower() == "utf-8":
                self.charset = True
            if values.get("name", "").lower() == "viewport":
                content = values.get("content", "").replace(" ", "").lower()
                self.viewport = "width=device-width" in content
        for attribute in ("src", "href", "poster"):
            if values.get(attribute):
                self.resources.append((lower, attribute, values[attribute], attribute in image_attributes))
        for candidate in srcset_references(values.get("srcset", "")):
            self.resources.append((lower, "srcset", candidate, "srcset" in image_attributes))
        if lower == "form" and values.get("action"):
            self.resources.append((lower, "action", values["action"], False))
        if lower == "label" and values.get("for"):
            self.labels.add(values["for"])
        if lower in {"button", "input", "textarea", "select"}:
            self.controls.append((lower, values))
        if lower == "img":
            self.images.append(values)
        if lower in {"iframe", "object", "embed"}:
            self.errors.append(f"Forbidden HTML element: <{lower}>")
        if any(name.lower().startswith("on") for name, _ in attrs):
            self.errors.append(f"Inline event handler is not allowed on <{lower}>")

    def handle_endtag(self, tag):
        if tag.lower() == "picture":
            self.picture_depth = max(0, self.picture_depth - 1)


def decode_text(raw, name):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{name} must be UTF-8 text") from error


def is_local_reference(value):
    cleaned = value.strip()
    if not cleaned or cleaned.startswith(("#", "data:", "blob:")):
        return True
    if NETWORK_URL.match(cleaned) or cleaned.startswith(("mailto:", "tel:", "javascript:", "/")):
        return False
    return True


def srcset_references(value):
    # Commas can be part of image URLs (CDN transformations and data URLs).
    # A candidate's URL ends at ASCII whitespace; descriptors end at a comma.
    whitespace = " \t\n\r\f"
    references = []
    position = 0
    while position < len(value):
        while position < len(value) and value[position] in whitespace + ",":
            position += 1
        start = position
        while position < len(value) and value[position] not in whitespace:
            position += 1
        url = value[start:position]
        if not url:
            break
        references.append(url.rstrip(","))
        if url.endswith(","):
            continue
        parentheses = 0
        while position < len(value):
            character = value[position]
            position += 1
            if character == "(":
                parentheses += 1
            elif character == ")":
                parentheses = max(0, parentheses - 1)
            elif character == "," and parentheses == 0:
                break
    return references


def is_https_image_reference(value):
    try:
        parsed = urlsplit(value.strip())
        return (parsed.scheme == "https" and bool(parsed.hostname) and
                not parsed.username and not parsed.password and
                not any(ord(character) < 32 for character in value) and
                "\\" not in value and (parsed.port is None or 0 < parsed.port <= 65535))
    except ValueError:
        return False


def validate_resource_reference(owner, value, files, label):
    require(is_local_reference(value), f"{owner}: external {label} is forbidden: {value}")
    target = resolve_reference(owner, value)
    if target is not None:
        require(target in files, f"{owner}: missing local resource: {value}")


def resolve_reference(owner, value):
    clean = value.split("#", 1)[0].split("?", 1)[0]
    if not clean or clean.startswith(("data:", "blob:")):
        return None
    parts = [*Path(owner).parent.parts, *Path(clean).parts]
    normalized = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            require(normalized, f"Resource escapes package root: {owner} -> {value}")
            normalized.pop()
        else:
            normalized.append(part)
    return Path(*normalized).as_posix()


def validate_html(name, raw, files):
    source = decode_text(raw, name)
    parser = TemplateHTMLParser(source)
    parser.feed(source)
    require(parser.doctype, f"{name}: missing <!doctype html>")
    require(parser.charset, f"{name}: missing <meta charset=\"UTF-8\">")
    require(parser.viewport, f"{name}: viewport must include width=device-width")
    require(not parser.errors, f"{name}: {'; '.join(parser.errors)}")
    for tag, attributes in parser.controls:
        if tag == "button":
            require(attributes.get("type") in {"button", "submit", "reset"},
                    f"{name}: every button needs an explicit type")
        if tag in {"input", "textarea", "select"}:
            if tag == "input" and attributes.get("type", "text").lower() == "hidden":
                continue
            accessible = (attributes.get("id") in parser.labels or
                          bool(attributes.get("aria-label")) or
                          bool(attributes.get("aria-labelledby")))
            require(accessible, f"{name}: <{tag}> needs a label or ARIA name")
    for attributes in parser.images:
        require("alt" in attributes, f"{name}: every image needs an alt attribute")
    for tag, attribute, value, is_image in parser.resources:
        if is_image and is_https_image_reference(value):
            continue
        validate_resource_reference(name, value, files, f"{tag} {attribute}")


def validate_runtime_sources(files, entry):
    for name, raw in files.items():
        if Path(name).suffix.lower() not in TEXT_SUFFIXES:
            continue
        source = decode_text(raw, name)
        network_source = source
        if Path(name).suffix.lower() in {".html", ".htm"}:
            parser = TemplateHTMLParser(source)
            parser.feed(source)
            # Exempt only parsed HTTPS image attributes, not matching URLs in
            # scripts, styles, navigation, or other attributes of the same tag.
            for start, end in reversed(parser.image_url_ranges):
                network_source = network_source[:start] + " " * (end - start) + network_source[end:]
        if Path(name).suffix.lower() == ".svg":
            network_source = network_source.replace("http://www.w3.org/2000/svg", "")
            network_source = network_source.replace("http://www.w3.org/1999/xlink", "")
        match = NETWORK_URL.search(network_source)
        if match:
            raise ValueError(f"{name}: external network URL is forbidden: {match.group(0)}")
        if Path(name).suffix.lower() in {".js", ".mjs"}:
            for label, pattern in FORBIDDEN_JS.items():
                require(not pattern.search(source), f"{name}: forbidden runtime API: {label}")
            for match in JS_IMPORT.finditer(source):
                value = match.group(2)
                validate_resource_reference(name, value, files, "module import")
        if Path(name).suffix.lower() == ".css":
            for match in CSS_REFERENCE.finditer(source):
                value = match.group(2) or match.group(4)
                validate_resource_reference(name, value, files, "CSS resource")
        if Path(name).suffix.lower() == ".svg":
            for match in SVG_REFERENCE.finditer(source):
                validate_resource_reference(name, match.group(2), files, "SVG resource")
    validate_html(entry, files[entry], files)
    css = "\n".join(
        decode_text(raw, name)
        for name, raw in files.items()
        if Path(name).suffix.lower() == ".css"
    )
    require(
        len(
            re.findall(
                r"@media\s*\([^)]*(?:min|max)-width",
                css,
                re.IGNORECASE,
            )
        )
        >= 2,
        "CSS must include responsive media rules for multiple viewport ranges",
    )
    require("prefers-reduced-motion" in css, "CSS must respect prefers-reduced-motion")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def json_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Not a finite JSON number: {value}")


def parse_json(raw, name):
    try:
        return json.loads(raw, object_pairs_hook=json_object, parse_constant=reject_constant)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f"{name}: {error}") from error


def parse_locale_bundle(source):
    match = re.fullmatch(
        r"\s*(?://[^\n]*\n)?window\.MINIPAGE_MESSAGES\s*=\s*(\{.*\})\s*;\s*",
        source,
        re.DOTALL,
    )
    require(match is not None, "i18n.js must only assign window.MINIPAGE_MESSAGES")
    return parse_json(match.group(1), "i18n.js")


def relative_path(value):
    require(text(value), "File paths must be nonempty strings")
    require(not any(c in value for c in "\\:?#"), f"Use a relative package path: {value}")
    require(not any(ord(c) < 32 for c in value), "Control characters in a file path")
    require(all(part not in ("", ".", "..") for part in value.split("/")),
            f"Use a normalized relative package path: {value}")
    return value


def validate_default(field, location):
    if "default" not in field:
        return
    value, kind = field["default"], field["type"]
    if field.get("required", False):
        require(value is not None and value != "" and value != [] and value != {},
                f"{location}: required field default must be nonempty")
    if value is None:
        return
    valid = {
        "text": isinstance(value, str), "url": isinstance(value, str),
        "number": type(value) in (int, float) and math.isfinite(value),
        "boolean": type(value) is bool, "date": isinstance(value, str),
        "attachment": isinstance(value, list) and all(isinstance(v, dict) for v in value),
        "json": True,
    }[kind]
    require(valid, f"{location}: default does not match {kind}")
    if kind == "date":
        try:
            if field.get("options", {}).get("dateFormat", "date") == "date":
                require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), "Use YYYY-MM-DD")
                dt.date.fromisoformat(value)
            else:
                require(bool(re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                    value)), "Use an ISO 8601 datetime with timezone")
                dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{location}: invalid date default ({error})") from error


def validate_schema(schema):
    require(isinstance(schema, dict), "dataSchema must be an object")
    count = 0
    for name, member in schema.items():
        require(bool(KEY.fullmatch(name)), f"Invalid dataSchema member key: {name}")
        require(isinstance(member, dict), f"dataSchema.{name} must be an object")
        kind = member.get("type")
        if kind == "json":
            require(set(member) <= {"type", "default"}, f"Unsupported JSON declaration: {name}")
            continue
        require(kind == "collection", f"Unknown dataSchema member type: {name}")
        count += 1
        require(set(member) <= {"type", "version", "fields"},
                f"Collection {name} only accepts type, version and fields (no default)")
        require(type(member.get("version")) is int and member["version"] >= 1,
                f"{name}.version must be a positive integer")
        fields = member.get("fields")
        require(isinstance(fields, list), f"{name}.fields must be an array")
        keys = set()
        for field in fields:
            require(isinstance(field, dict), f"{name}: field definition must be an object")
            key = field.get("key")
            require(isinstance(key, str) and KEY.fullmatch(key), f"{name}: invalid field key")
            require(key not in keys, f"{name}: duplicate field key {key}")
            keys.add(key)
            require(set(field) <= {"key", "type", "required", "default", "labelKey", "options"},
                    f"{name}.{key}: unsupported field declaration property")
            require(field.get("type") in TYPES, f"{name}.{key}: unsupported field type")
            require(type(field.get("required", False)) is bool, f"{name}.{key}: required must be boolean")
            if "labelKey" in field:
                require(text(field["labelKey"]), f"{name}.{key}: labelKey must be nonempty")
            if "options" in field:
                options = field["options"]
                require(field["type"] == "date" and isinstance(options, dict)
                        and set(options) == {"dateFormat"}
                        and options["dateFormat"] in ("date", "datetime"),
                        f"{name}.{key}: options only supports dateFormat on date fields")
            validate_default(field, f"{name}.{key}")
    require(count == 1, "dataSchema must declare exactly one collection")


def validate_network(manifest):
    if "network" not in manifest:
        return
    network = manifest["network"]
    require(isinstance(network, dict) and set(network) == {"endpoints"} and
            isinstance(network["endpoints"], list), "network must contain an endpoints list")
    ids = set()
    allowed_methods = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
    for endpoint in network["endpoints"]:
        require(isinstance(endpoint, dict) and
                set(endpoint) == {"id", "url", "match", "methods"},
                "network endpoint needs id, url, match and methods")
        ident, url, match, methods = (endpoint[k] for k in ("id", "url", "match", "methods"))
        require(isinstance(ident, str) and
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", ident) and ident not in ids,
                "network endpoint id must be valid and unique")
        ids.add(ident)
        require(match in ("exact", "prefix"), "network match must be exact or prefix")
        require(isinstance(methods, list) and methods and
                all(isinstance(method, str) and method in allowed_methods for method in methods) and
                len(set(methods)) == len(methods), "network methods must be explicit and unique")
        require(isinstance(url, str) and url.startswith("https://") and
                not re.search(r"[\\\x00-\x20\x7f?#]", url),
                "network URL must be HTTPS without whitespace, query or fragment")
        parsed = urlsplit(url)
        require(parsed.hostname and not re.search(r"[@%]", parsed.netloc) and
                parsed.username is None and parsed.password is None and
                0 < (parsed.port if parsed.port is not None else 443) <= 65535,
                "network URL must have a host and valid port, without credentials")
        host = parsed.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            require(len(host) <= 253 and all(re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")),
                "network host must be an IP address or ASCII DNS name")
        path = parsed.path
        require("//" not in path and
                not re.search(r"%(?![a-fA-F0-9]{2})|%(?:25|2f|5c|00|0[ad])", path, re.I),
                "network path contains ambiguous encoding or separators")
        decoded = unquote(path, encoding="utf-8", errors="strict")
        require(not re.search(r"[\\\x00-\x1f\x7f]", decoded) and
                all(part not in (".", "..") for part in decoded.split("/")),
                "network path must not contain dot segments or control characters")
        require(match != "prefix" or path.endswith("/"),
                "network prefix URL must end with /")


def validate_manifest(manifest, files, source):
    require(isinstance(manifest, dict), "manifest.json must contain an object")
    require(type(manifest.get("manifestVersion")) is int and manifest["manifestVersion"] == 1,
            "manifestVersion must be 1")
    for key in ("templateId", "version", "sdkApiVersion", "title", "description", "defaultLocale"):
        require(text(manifest.get(key)), f"{key} must be a nonempty string")
    require(manifest["templateId"] != "replace-with-template-id",
            "Replace the starter templateId before packaging")
    require(bool(TEMPLATE_VERSION.fullmatch(manifest["version"])),
            "version must contain two numeric parts, such as 1.0 or 2.0")
    mini_version = manifest.get("miniVersion", "0.0.0")
    require(isinstance(mini_version, str) and len(mini_version) <= 50
            and bool(APP_VERSION.fullmatch(mini_version))
            and all(int(part) <= 9007199254740991 for part in mini_version.split(".")),
            "miniVersion must contain three App version parts, such as 1.3.1")
    for key, value in manifest.items():
        if key.startswith(("title_", "description_")):
            locale = key.split("_", 1)[1].replace("_", "-")
            require(LOCALE.fullmatch(locale) and text(value), f"Invalid localized display field: {key}")
    locales = manifest.get("locales")
    require(isinstance(locales, dict) and manifest["defaultLocale"] in locales,
            "locales must include defaultLocale")
    for locale, path in locales.items():
        require(bool(LOCALE.fullmatch(locale)), f"Invalid locale tag: {locale}")
        relative_path(path)
        require(path in files and Path(path).suffix.lower() == ".json", f"Missing locale JSON: {path}")
        require(isinstance(parse_json(files[path], path), dict), f"{path} must contain a JSON object")
    for key in ("entry", "cover"):
        path = relative_path(manifest.get(key))
        require(path in files, f"Missing {key} file: {path}")
    require(Path(manifest["entry"]).suffix.lower() in (".html", ".htm"), "entry must be HTML")
    cover, suffix = files[manifest["cover"]], Path(manifest["cover"]).suffix.lower()
    require((suffix == ".png" and cover.startswith(b"\x89PNG\r\n\x1a\n"))
            or (suffix in (".jpg", ".jpeg") and cover.startswith(b"\xff\xd8\xff"))
            or (suffix == ".webp" and cover[:4] == b"RIFF" and cover[8:12] == b"WEBP"),
            "cover must have a PNG, JPEG or WebP extension and matching signature")
    validate_network(manifest)
    validate_schema(manifest.get("dataSchema"))
    validate_runtime_sources(files, manifest["entry"])
    expected_i18n = Path(__file__).with_name("compile_locales.py")
    require(expected_i18n.is_file(), "compile_locales.py is missing from the skill")
    from compile_locales import compile_locales
    generated = compile_locales(source)
    require("i18n.js" in files, "Missing generated locale bundle: i18n.js")
    expected_messages = parse_locale_bundle(generated)
    actual_messages = parse_locale_bundle(decode_text(files["i18n.js"], "i18n.js"))
    require(actual_messages == expected_messages,
            "i18n.js does not match manifest locales; run compile_locales.py")


def package(source, output=None, force=False, check_only=False):
    require(source.is_dir() and not source.is_symlink(), "SOURCE_DIR must be a real directory")
    source = source.resolve()
    if not check_only:
        require(output is not None, "OUTPUT_ZIP is required unless --check-only is used")
        output = output.absolute()
        require(not output.is_symlink(), "Output must not be a symlink")
        resolved_output = output.resolve()
        require(source not in resolved_output.parents, "Output ZIP must be outside SOURCE_DIR")
        require(output.suffix.lower() == ".zip", "Output filename must end in .zip")
        require(force or not output.exists(), "Output exists; use --force to replace it")
    files = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source).as_posix()
        require(not path.is_symlink(), f"Symlinks are not supported: {relative}")
        require(not any(part.startswith(".") for part in relative.split("/")),
                f"Remove hidden build/source entries before packaging: {relative}")
        if path.is_dir():
            continue
        require(Path(relative).name.lower() not in FORBIDDEN_RUNTIME_NAMES,
                f"Remove development-only file from runtime package: {relative}")
        require(stat.S_ISREG(path.stat().st_mode), f"Unsupported source entry: {relative}")
        relative_path(relative)
        files[relative] = path.read_bytes()
    require("manifest.json" in files, "SOURCE_DIR must contain manifest.json")
    manifest = parse_json(files.pop("manifest.json"), "manifest.json")
    validate_manifest(manifest, files, source)
    manifest["files"] = [
        {"path": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
         "mimeType": MIMES.get(Path(name).suffix.lower(), "application/octet-stream")}
        for name, raw in sorted(files.items())
    ]
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                         indent=2, allow_nan=False) + "\n").encode("utf-8")
    if check_only:
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, raw in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        if force:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)  # Do not overwrite an output created during packaging.
    finally:
        temporary.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_zip", type=Path, nargs="?")
    parser.add_argument("--force", action="store_true", help="Replace an existing output ZIP")
    parser.add_argument("--check-only", action="store_true", help="Validate without writing a ZIP")
    args = parser.parse_args()
    try:
        if args.check_only and args.output_zip is not None:
            parser.error("OUTPUT_ZIP cannot be used with --check-only")
        output = package(args.source_dir, args.output_zip, args.force, args.check_only)
    except (ValueError, OSError, TypeError, OverflowError) as error:
        print(f"Packaging failed: {error}", file=sys.stderr)
        return 1
    if args.check_only:
        print(f"Template is valid: {args.source_dir.resolve()}")
    else:
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        print(f"Created {output}\nSize: {output.stat().st_size} bytes\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
