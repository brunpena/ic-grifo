"""Download de arquivos por URL, com proteção contra SSRF.

- Só http e https, sem usuário e senha na URL.
- O nome é resolvido aqui, e todos os IPs precisam ser públicos (`is_global`): ficam de
  fora loopback, redes privadas, link-local (inclusive 169.254.169.254, de metadados da
  nuvem), CGNAT, multicast e reservados, também na forma IPv4 mapeada em IPv6.
- A conexão vai direto ao IP validado (o cabeçalho Host e o SNI levam o nome original,
  e o certificado continua sendo conferido contra ele). Assim um DNS que muda de
  resposta entre a checagem e a conexão (DNS rebinding) não leva a um IP interno.
- Redirecionamentos são seguidos à mão, validando cada destino, até MAX_REDIRECTS.
- Tempo total e tamanho limitados; proxies do ambiente são ignorados.
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.message import Message
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import httpx

MAX_REDIRECTS = 3
USER_AGENT = "IC-Grifo/0.1 (leitor de documentos)"
REDIRECT_STATUS = {301, 302, 303, 307, 308}

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]


class FetchError(Exception):
    """O link não pôde ser baixado. A mensagem, em português, vai para a pessoa."""


@dataclass
class FetchedFile:
    data: bytes
    content_type: str | None
    charset: str | None
    filename: str | None
    final_url: str


@dataclass
class _Target:
    url: str
    scheme: str
    host: str
    port: int


def parse_url(url: str) -> _Target:
    url = url.strip()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise FetchError("O link não é válido.") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchError("Use um link que comece com http:// ou https://.")
    if parts.username or parts.password:
        raise FetchError("Links com usuário e senha não são aceitos.")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise FetchError("O link não tem um endereço de site.")
    return _Target(url, scheme, host, port or (443 if scheme == "https" else 80))


def is_public_ip(address: str) -> bool:
    try:
        ip: IpAddress = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def _system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


async def resolve_public(host: str, port: int, resolver: Resolver = _system_resolver) -> str:
    """Primeiro IP do nome, desde que todos os IPs dele sejam públicos."""
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = await resolver(host, port)
        except (OSError, UnicodeError) as exc:
            raise FetchError(f"Não encontrei o site “{host}”. Confira o link.") from exc
    if not addresses:
        raise FetchError(f"Não encontrei o site “{host}”. Confira o link.")
    if not all(is_public_ip(a) for a in addresses):
        raise FetchError("Este link aponta para um endereço interno ou privado e foi bloqueado.")
    return addresses[0]


def _pinned_url(target: _Target, ip: str) -> str:
    """A mesma URL, com o IP no lugar do nome."""
    parts = urlsplit(target.url)
    host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host}:{target.port}"
    path = parts.path or "/"
    return f"{target.scheme}://{netloc}{path}" + (f"?{parts.query}" if parts.query else "")


def _host_header(target: _Target) -> str:
    host = f"[{target.host}]" if ":" in target.host else target.host
    default = 443 if target.scheme == "https" else 80
    return host if target.port == default else f"{host}:{target.port}"


def _content_type(header: str | None) -> tuple[str | None, str | None]:
    if not header:
        return None, None
    message = Message()
    message["content-type"] = header
    charset = message.get_param("charset")
    return message.get_content_type().lower(), str(charset) if isinstance(charset, str) else None


def _filename(disposition: str | None, url: str) -> str | None:
    if disposition:
        match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition, re.IGNORECASE)
        if match:
            return unquote(match.group(1)).strip()[:200] or None
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    return name[:200] or None


def _status_error(status: int) -> FetchError:
    if status == 404:
        return FetchError("A página não foi encontrada (erro 404). Confira o link.")
    if status in (401, 403):
        return FetchError(
            "O site recusou o acesso (exige login ou bloqueia downloads). "
            "Baixe o arquivo e envie pelo botão de arquivo."
        )
    if status == 429:
        return FetchError("O site limitou os acessos agora. Tente de novo em alguns minutos.")
    if status >= 500:
        return FetchError(f"O site está com problemas (erro {status}). Tente de novo mais tarde.")
    return FetchError(f"O site respondeu com erro {status}.")


async def fetch_url(
    url: str,
    *,
    max_bytes: int,
    time_limit: float,
    resolver: Resolver = _system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedFile:
    """Baixa o arquivo do link. `resolver` e `transport` existem para os testes."""
    try:
        async with asyncio.timeout(time_limit):
            return await _fetch(url, max_bytes, time_limit, resolver, transport)
    except TimeoutError as exc:
        raise FetchError(f"O site demorou mais de {time_limit:.0f} s para responder.") from exc


async def _fetch(
    url: str,
    max_bytes: int,
    time_limit: float,
    resolver: Resolver,
    transport: httpx.AsyncBaseTransport | None,
) -> FetchedFile:
    limit_mb = max_bytes // (1024 * 1024)
    too_big = FetchError(f"O arquivo do link passa do limite de {limit_mb} MB.")
    async with httpx.AsyncClient(
        transport=transport, trust_env=False, follow_redirects=False, timeout=time_limit
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            target = parse_url(url)
            ip = await resolve_public(target.host, target.port, resolver)
            extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
            request = client.build_request(
                "GET",
                _pinned_url(target, ip),
                headers={"Host": _host_header(target), "User-Agent": USER_AGENT, "Accept": "*/*"},
                extensions=extensions,
            )
            try:
                response = await client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise FetchError(
                    f"O site demorou mais de {time_limit:.0f} s para responder."
                ) from exc
            except httpx.HTTPError as exc:
                raise FetchError("Não foi possível conectar ao site do link.") from exc
            try:
                if response.status_code in REDIRECT_STATUS:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("O site redirecionou para um endereço inválido.")
                    url = urljoin(target.url, location)
                    continue
                if response.status_code != 200:
                    raise _status_error(response.status_code)
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > max_bytes:
                    raise too_big
                chunks: list[bytes] = []
                size = 0
                try:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise too_big
                        chunks.append(chunk)
                except httpx.HTTPError as exc:
                    raise FetchError("A conexão com o site caiu durante o download.") from exc
                content_type, charset = _content_type(response.headers.get("content-type"))
                return FetchedFile(
                    data=b"".join(chunks),
                    content_type=content_type,
                    charset=charset,
                    filename=_filename(response.headers.get("content-disposition"), target.url),
                    final_url=target.url,
                )
            finally:
                await response.aclose()
    raise FetchError(f"O link redirecionou mais de {MAX_REDIRECTS} vezes.")
