import ipaddress
import http.client
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from .models import AICredentialError, UserAISettings


class AIServiceError(Exception):
    """Raised for safe-to-handle upstream AI failures."""


class _Bulkhead:
    """A no-queue executor whose slot is released only when work truly ends."""

    def __init__(self, workers, name):
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix=name,
        )
        self._slots = threading.BoundedSemaphore(workers)

    def run(self, function, timeout, *, busy_message, timeout_message):
        if not self._slots.acquire(blocking=False):
            raise AIServiceError(busy_message)
        try:
            future = self._executor.submit(function)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _future: self._slots.release())
        try:
            return future.result(timeout=max(0.001, float(timeout)))
        except FutureTimeoutError as exc:
            # Do not release here: the callback owns the slot and only releases
            # it after the timed-out operation has actually stopped.
            raise AIServiceError(timeout_message) from exc


def _worker_setting(name, default):
    return max(1, min(int(getattr(settings, name, default)), 16))


_DNS_BULKHEAD = _Bulkhead(
    _worker_setting("AI_DNS_MAX_CONCURRENCY", 2),
    "ai-dns",
)
_CUSTOM_PROVIDER_BULKHEAD = _Bulkhead(
    _worker_setting("AI_CUSTOM_MAX_CONCURRENCY", 4),
    "ai-custom",
)
_OFFICIAL_PROVIDER_BULKHEAD = _Bulkhead(
    _worker_setting("AI_OFFICIAL_MAX_CONCURRENCY", 4),
    "ai-official",
)


@dataclass(frozen=True)
class AIConfig:
    api_key: str = field(repr=False)
    endpoint: str
    model: str
    provider: str
    timeout: int
    max_output_length: int
    resolved_addresses: tuple = field(default=(), repr=False)


_NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL_USE = ipaddress.ip_network("64:ff9b:1::/48")


def _address_is_public(address):
    """Apply explicit public-address checks, including transition tunnels."""
    if any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    ) or not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return True

    embedded = []
    if address.ipv4_mapped is not None:
        embedded.append(address.ipv4_mapped)
    if address.sixtofour is not None:
        embedded.append(address.sixtofour)
    if address.teredo is not None:
        embedded.extend(address.teredo)
    numeric = int(address)
    if address in _NAT64_WELL_KNOWN:
        embedded.append(ipaddress.IPv4Address(numeric & 0xFFFFFFFF))
    if address in _NAT64_LOCAL_USE:
        embedded.append(ipaddress.IPv4Address((numeric >> 48) & 0xFFFFFFFF))
    return all(_address_is_public(item) for item in embedded)


def _parsed_https_url(base_url):
    try:
        parsed = urlsplit((base_url or "").strip())
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise AIServiceError("API 地址格式无效") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise AIServiceError("API 地址必须是有效的 HTTPS 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AIServiceError("API 地址不能包含账号、查询参数或片段")
    if port is not None and not 1 <= port <= 65535:
        raise AIServiceError("API 地址端口无效")
    return parsed


def _reject_non_public_host(hostname, port=443, *, resolve_dns):
    hostname = hostname.rstrip(".").lower()
    blocked_suffixes = (
        ".localhost",
        ".local",
        ".internal",
        ".lan",
        ".home.arpa",
    )
    if hostname == "localhost" or hostname.endswith(blocked_suffixes):
        raise AIServiceError("API 地址不能指向本机或内网")
    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        literal_address = None
    if literal_address is not None:
        if not _address_is_public(literal_address):
            raise AIServiceError("API 地址不能指向本机或内网")
        family = socket.AF_INET6 if literal_address.version == 6 else socket.AF_INET
        sockaddr = (
            (str(literal_address), port, 0, 0)
            if family == socket.AF_INET6
            else (str(literal_address), port)
        )
        return ((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, sockaddr),)
    if not resolve_dns:
        return ()

    def resolve():
        return socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)

    try:
        records = _DNS_BULKHEAD.run(
            resolve,
            min(
                max(0.1, float(getattr(settings, "AI_DNS_TIMEOUT", 5))),
                30.0,
            ),
            busy_message="API 地址解析服务繁忙",
            timeout_message="API 地址解析超时",
        )
    except AIServiceError:
        raise
    except (socket.gaierror, OSError) as exc:
        raise AIServiceError("API 地址无法解析") from exc
    if not records:
        raise AIServiceError("API 地址无法解析")
    validated = []
    seen = set()
    for record in records:
        raw_address = record[4][0].split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise AIServiceError("API 地址解析结果无效") from exc
        if not _address_is_public(address):
            raise AIServiceError("API 地址解析到了本机或内网")
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        sockaddr = (
            (str(address), port, 0, 0)
            if family == socket.AF_INET6
            else (str(address), port)
        )
        normalized = (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, sockaddr)
        key = (family, sockaddr)
        if key not in seen:
            seen.add(key)
            validated.append(normalized)
    return tuple(validated)


def _validated_custom_target(base_url, *, resolve_dns=True):
    parsed = _parsed_https_url(base_url)
    records = _reject_non_public_host(
        parsed.hostname,
        parsed.port or 443,
        resolve_dns=resolve_dns,
    )
    normalized = urlunsplit(
        ("https", parsed.netloc, parsed.path.rstrip("/"), "", "")
    )
    return normalized, records


def validate_custom_api_base(base_url, *, resolve_dns=True):
    """Validate and normalize an untrusted user-provided provider base URL."""
    normalized, _records = _validated_custom_target(
        base_url,
        resolve_dns=resolve_dns,
    )
    return normalized


def normalized_api_origin(base_url):
    """Return a canonical HTTPS origin for credential-boundary checks."""
    parsed = _parsed_https_url(base_url)
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise AIServiceError("API 地址主机名无效") from exc
    else:
        hostname = str(literal)
    return ("https", hostname, parsed.port or 443)


def _endpoint_from_parsed(parsed):
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions"
    return urlunsplit(("https", parsed.netloc, path, "", ""))


def _validated_endpoint(base_url):
    parsed = _parsed_https_url(base_url)
    _reject_non_public_host(
        parsed.hostname,
        parsed.port or 443,
        resolve_dns=False,
    )
    return _endpoint_from_parsed(parsed)


def _limits():
    timeout = max(1, min(int(getattr(settings, "AI_API_TIMEOUT", 60)), 180))
    output = max(
        256,
        min(int(getattr(settings, "AI_MAX_OUTPUT_LENGTH", 12000)), 50000),
    )
    return timeout, output


def _user_settings(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    try:
        return UserAISettings.objects.filter(user=user).first()
    except (TypeError, ValueError):
        return None


@sensitive_variables()
def get_ai_config(user=None):
    timeout, max_output_length = _limits()
    preference = _user_settings(user)
    if preference and preference.mode == UserAISettings.Mode.CUSTOM:
        try:
            api_key = preference.get_api_key()
        except AICredentialError as exc:
            raise AIServiceError("自定义模型凭据不可用") from exc
        if not api_key or not preference.custom_model:
            raise AIServiceError("自定义模型尚未配置完整")
        normalized_base, resolved_addresses = _validated_custom_target(
            preference.custom_api_base,
            resolve_dns=True,
        )
        return AIConfig(
            api_key=api_key,
            endpoint=_endpoint_from_parsed(urlsplit(normalized_base)),
            model=preference.custom_model,
            provider="custom",
            timeout=timeout,
            max_output_length=max_output_length,
            resolved_addresses=resolved_addresses,
        )

    api_key = str(getattr(settings, "AI_API_KEY", "") or "")
    model = str(getattr(settings, "AI_MODEL", "") or "")
    if not api_key or not model:
        raise AIServiceError("官方模型尚未配置")
    return AIConfig(
        api_key=api_key,
        endpoint=_validated_endpoint(getattr(settings, "AI_API_BASE", "")),
        model=model,
        provider="official",
        timeout=timeout,
        max_output_length=max_output_length,
    )


def ai_is_configured(user=None):
    preference = _user_settings(user)
    if not preference or preference.mode == UserAISettings.Mode.OFFICIAL:
        # The operator-controlled official endpoint is treated as configured
        # when credentials exist. A malformed/unreachable official endpoint
        # is reported as an upstream fallback, matching existing chat UX.
        return bool(
            getattr(settings, "AI_API_KEY", "")
            and getattr(settings, "AI_MODEL", "")
        )
    try:
        get_ai_config(user)
    except AIServiceError:
        return False
    return True


@sensitive_variables()
def get_ai_status(user=None):
    selection = get_ai_selection(user)
    provider = selection["provider"]
    try:
        config = get_ai_config(user)
    except AIServiceError:
        model = (
            selection["model"]
        )
        return {"configured": False, "provider": provider, "model": model or None}
    return {
        "configured": True,
        "provider": config.provider,
        "model": config.model,
    }


def get_ai_selection(user=None):
    """Return non-secret local selection metadata without DNS or decryption."""
    preference = _user_settings(user)
    if preference and preference.mode == UserAISettings.Mode.CUSTOM:
        return {"provider": "custom", "model": preference.custom_model or None}
    return {
        "provider": "official",
        "model": str(getattr(settings, "AI_MODEL", "") or "") or None,
    }


@sensitive_variables()
def _request(config, system_prompt, messages, *, stream):
    if not config.api_key or not config.model:
        raise AIServiceError("AI 服务尚未配置")
    if any(not 0x21 <= ord(character) <= 0x7E for character in str(config.api_key)):
        # Defend against legacy/corrupted encrypted values before they reach
        # urllib/http.client header handling, whose ValueError includes input.
        raise AIServiceError("AI 服务凭据格式无效")
    # Keep to the smallest common OpenAI-compatible payload. Some reasoning
    # models reject optional temperature/max_tokens parameters.
    payload = {
        "model": config.model,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        "stream": stream,
    }
    return Request(
        config.endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        },
        method="POST",
    )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated address with hostname TLS SNI."""

    def __init__(self, hostname, port, address_record, *, timeout):
        super().__init__(hostname, port=port, timeout=timeout)
        self._address_record = address_record

    def connect(self):
        if self._tunnel_host:
            raise AIServiceError("自定义模型不允许代理隧道")
        family, socktype, proto, sockaddr = self._address_record
        raw_socket = socket.socket(family, socktype, proto)
        try:
            raw_socket.settimeout(self.timeout)
            if self.source_address:
                raw_socket.bind(self.source_address)
            raw_socket.connect(sockaddr)
            # self.host is the original provider hostname, not the pinned IP.
            # The default HTTPSConnection SSLContext verifies its certificate.
            self.sock = self._context.wrap_socket(
                raw_socket,
                server_hostname=self.host,
            )
        except BaseException:
            raw_socket.close()
            raise


class _PinnedResponse:
    def __init__(self, response, connection):
        self._response = response
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._response, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            self._response.close()
        finally:
            self._connection.close()
        return False


@sensitive_variables()
def _open_connection(request, config):
    if config.provider != "custom":
        try:
            return urlopen(request, timeout=config.timeout)
        except (ValueError, UnicodeError):
            raise AIServiceError("AI 请求格式无效") from None
    if not config.resolved_addresses:
        raise AIServiceError("自定义模型地址尚未安全解析")
    parsed = urlsplit(config.endpoint)
    connection = _PinnedHTTPSConnection(
        parsed.hostname,
        parsed.port or 443,
        config.resolved_addresses[0],
        timeout=config.timeout,
    )
    path = parsed.path or "/"
    headers = dict(request.header_items())
    try:
        # http.client sets Host from connection.host (the original hostname),
        # while connect() uses only the pinned sockaddr. It never follows 30x.
        connection.request(
            request.get_method(),
            path,
            body=request.data,
            headers=headers,
        )
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            response.close()
            connection.close()
            raise AIServiceError("AI 服务暂时不可用")
        return _PinnedResponse(response, connection)
    except (ValueError, UnicodeError):
        connection.close()
        raise AIServiceError("AI 请求格式无效") from None
    except BaseException:
        connection.close()
        raise


def _remaining_time(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AIServiceError("AI 服务响应超时")
    return remaining


def _set_response_timeout(response, remaining):
    """Cap the next socket read by the remaining wall-clock budget."""
    for attributes in (
        ("fp", "raw", "_sock"),
        ("fp", "_sock"),
        ("raw", "_sock"),
        ("_sock",),
    ):
        candidate = response
        try:
            for attribute in attributes:
                candidate = getattr(candidate, attribute)
        except (AttributeError, ValueError):
            continue
        setter = getattr(candidate, "settimeout", None)
        if setter:
            try:
                setter(max(0.001, remaining))
            except OSError:
                pass
            return


def _read_limited_body(response, limit, deadline):
    reader = getattr(response, "read1", None)
    if reader is None:
        remaining = _remaining_time(deadline)
        _set_response_timeout(response, remaining)
        raw = response.read(limit + 1)
        _remaining_time(deadline)
        return raw

    chunks = []
    size = 0
    while True:
        remaining = _remaining_time(deadline)
        _set_response_timeout(response, remaining)
        chunk = reader(min(8192, limit + 1 - size))
        _remaining_time(deadline)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            return b"".join(chunks)


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item["text"]
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


def _provider_bulkhead(config):
    return (
        _CUSTOM_PROVIDER_BULKHEAD
        if config.provider == "custom"
        else _OFFICIAL_PROVIDER_BULKHEAD
    )


@sensitive_variables()
def call_ai(system_prompt, messages, *, user=None, config=None):
    config = config or get_ai_config(user)
    return _provider_bulkhead(config).run(
        lambda: _call_ai_sync(system_prompt, messages, config),
        config.timeout,
        busy_message="AI 服务繁忙，请稍后再试",
        timeout_message="AI 服务响应超时",
    )


@sensitive_variables()
def _call_ai_sync(system_prompt, messages, config):
    request = _request(config, system_prompt, messages, stream=False)
    response_limit = max(65536, config.max_output_length * 8)
    deadline = time.monotonic() + config.timeout
    try:
        with _open_connection(request, config) as response:
            _remaining_time(deadline)
            raw = _read_limited_body(response, response_limit, deadline)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        AttributeError,
    ) as exc:
        raise AIServiceError("AI 服务暂时不可用") from exc
    except http.client.HTTPException:
        raise AIServiceError("AI 服务返回了无效 HTTP 响应") from None
    except (ValueError, UnicodeError):
        raise AIServiceError("AI 请求格式无效") from None
    if len(raw) > response_limit:
        raise AIServiceError("AI 服务响应过大")
    try:
        data = json.loads(raw.decode("utf-8"))
        content = _content_text(data["choices"][0]["message"]["content"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        raise AIServiceError("AI 服务返回了无效响应") from None
    if not content.strip():
        raise AIServiceError("AI 服务未返回有效内容")
    if config.api_key in content:
        raise AIServiceError("AI 服务返回了不安全的内容")
    return content.strip()[: config.max_output_length]


@sensitive_variables()
def stream_ai(system_prompt, messages, *, user=None, config=None):
    config = config or get_ai_config(user)
    chunks = _provider_bulkhead(config).run(
        lambda: tuple(_stream_ai_sync(system_prompt, messages, config)),
        config.timeout,
        busy_message="AI 服务繁忙，请稍后再试",
        timeout_message="AI 服务响应超时",
    )
    if config.api_key in "".join(chunks):
        raise AIServiceError("AI 服务返回了不安全的内容")
    return iter(chunks)


@sensitive_variables()
def _stream_ai_sync(system_prompt, messages, config):
    request = _request(config, system_prompt, messages, stream=True)
    emitted = 0
    deadline = time.monotonic() + config.timeout
    raw_limit = max(65536, config.max_output_length * 8)
    raw_received = 0

    def parse_line(line):
        if len(line) > 65536:
            raise AIServiceError("AI 服务流式响应行过大")
        try:
            line_text = line.decode("utf-8").strip()
        except UnicodeDecodeError:
            return False, ""
        if not line_text.startswith("data:"):
            return False, ""
        event = line_text[5:].strip()
        if event == "[DONE]":
            return True, ""
        try:
            data = json.loads(event)
            content = _content_text(
                data["choices"][0]["delta"].get("content", "")
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return False, ""
        return False, content

    try:
        with _open_connection(request, config) as response:
            chunk_reader = getattr(response, "read1", None)
            if chunk_reader is None:
                while True:
                    remaining_time = _remaining_time(deadline)
                    _set_response_timeout(response, remaining_time)
                    line = response.readline(65537)
                    _remaining_time(deadline)
                    if not line:
                        break
                    raw_received += len(line)
                    if raw_received > raw_limit:
                        raise AIServiceError("AI 服务流式响应过大")
                    done, content = parse_line(line)
                    if done:
                        return
                    if content:
                        remaining_output = config.max_output_length - emitted
                        if remaining_output <= 0:
                            return
                        output = content[:remaining_output]
                        emitted += len(output)
                        yield output
                return

            buffer = bytearray()
            while True:
                remaining_time = _remaining_time(deadline)
                _set_response_timeout(response, remaining_time)
                incoming = chunk_reader(8192)
                _remaining_time(deadline)
                eof = not incoming
                if incoming:
                    raw_received += len(incoming)
                    if raw_received > raw_limit:
                        raise AIServiceError("AI 服务流式响应过大")
                    buffer.extend(incoming)
                elif buffer:
                    # Treat a final non-newline-terminated event as one line.
                    buffer.extend(b"\n")

                start = 0
                while True:
                    newline = buffer.find(b"\n", start)
                    if newline < 0:
                        break
                    line = bytes(buffer[start:newline])
                    start = newline + 1
                    done, content = parse_line(line)
                    if done:
                        return
                    if not content:
                        continue
                    remaining_output = config.max_output_length - emitted
                    if remaining_output <= 0:
                        return
                    output = content[:remaining_output]
                    emitted += len(output)
                    yield output
                if start:
                    del buffer[:start]
                if len(buffer) > 65536:
                    raise AIServiceError("AI 服务流式响应行过大")
                if eof:
                    return
    except AIServiceError:
        raise
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise AIServiceError("AI 服务暂时不可用") from exc
    except http.client.HTTPException:
        raise AIServiceError("AI 服务返回了无效 HTTP 响应") from None
    except (ValueError, UnicodeError):
        raise AIServiceError("AI 请求格式无效") from None
