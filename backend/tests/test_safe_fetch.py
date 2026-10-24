import asyncio

import httpx
import pytest

from app.services.safe_fetch import FetchError, fetch_url, is_public_ip, parse_url, resolve_public

DNS = {
    "docs.exemplo.com": ["93.184.216.34"],
    "outro.exemplo.com": ["93.184.216.35"],
    "interno.exemplo.com": ["10.0.0.5"],
    # Um nome com um IP público e outro privado também é bloqueado.
    "misto.exemplo.com": ["93.184.216.36", "192.168.0.10"],
}


async def fake_resolver(host: str, port: int) -> list[str]:
    if host not in DNS:
        raise OSError("nome não encontrado")
    return DNS[host]


def fetch(url: str, handler, **kwargs):
    return fetch_url(
        url,
        max_bytes=kwargs.pop("max_bytes", 1024),
        time_limit=kwargs.pop("time_limit", 5),
        resolver=fake_resolver,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1",
        "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "nao-e-ip",
    ],
)  # fmt: skip
def test_private_and_special_addresses_are_not_public(address):
    assert not is_public_ip(address)


def test_public_addresses():
    assert is_public_ip("93.184.216.34") and is_public_ip("2606:2800:220:1:248:1893:25c8:1946")


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://exemplo.com/a.pdf", "http"),
        ("file:///etc/passwd", "http"),
        ("javascript:alert(1)", "http"),
        ("https://user:senha@exemplo.com/", "usuário"),
        ("https:///sem-host", "endereço"),
        ("http://exemplo.com:99999/", "válido"),
    ],
)
def test_parse_url_rejects_unsafe_links(url, message):
    with pytest.raises(FetchError, match=message):
        parse_url(url)


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "localhost", "interno.exemplo.com", "misto.exemplo.com", "::1"]
)
async def test_resolve_public_blocks_internal_hosts(host):
    async def resolver(name, port):
        return ["127.0.0.1"] if name == "localhost" else await fake_resolver(name, port)

    with pytest.raises(FetchError, match="interno"):
        await resolve_public(host, 80, resolver)


async def test_fetch_connects_to_validated_ip_with_original_host():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=ISO-8859-1"},
            content=b"<p>oi</p>",
        )

    result = await fetch("https://docs.exemplo.com/editais/edital.html?v=2", handler)
    assert result.content_type == "text/html" and result.charset == "ISO-8859-1"
    assert result.filename == "edital.html" and result.data == b"<p>oi</p>"
    request = seen[0]
    assert request.url.host == "93.184.216.34" and request.url.query == b"v=2"
    assert request.headers["host"] == "docs.exemplo.com"
    assert request.extensions["sni_hostname"] == "docs.exemplo.com"


async def test_redirects_are_revalidated():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "docs.exemplo.com":
            return httpx.Response(302, headers={"location": "http://interno.exemplo.com/admin"})
        return httpx.Response(200, content=b"segredo")

    with pytest.raises(FetchError, match="interno"):
        await fetch("https://docs.exemplo.com/a", handler)


async def test_relative_redirect_and_redirect_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/final.pdf":
            return httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=b"%PDF-"
            )
        return httpx.Response(301, headers={"location": "/final.pdf"})

    result = await fetch("https://docs.exemplo.com/inicio", handler)
    assert result.final_url == "https://docs.exemplo.com/final.pdf"

    def loop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/de-novo"})

    with pytest.raises(FetchError, match="redirecionou mais"):
        await fetch("https://docs.exemplo.com/", loop)


async def test_size_limit_with_and_without_content_length():
    def declared(request):
        return httpx.Response(200, headers={"content-length": "999999"}, content=b"x")

    with pytest.raises(FetchError, match="limite"):
        await fetch("https://docs.exemplo.com/", declared)

    def streamed(request):
        return httpx.Response(200, content=b"x" * 5000)

    with pytest.raises(FetchError, match="limite"):
        await fetch("https://docs.exemplo.com/", streamed, max_bytes=1000)


@pytest.mark.parametrize(
    ("status", "message"), [(404, "404"), (403, "recusou"), (503, "problemas"), (418, "418")]
)
async def test_http_errors_have_clear_messages(status, message):
    with pytest.raises(FetchError, match=message):
        await fetch("https://docs.exemplo.com/", lambda r: httpx.Response(status))


async def test_unknown_host_and_connection_errors():
    with pytest.raises(FetchError, match="Não encontrei o site"):
        await fetch("https://nao-existe.exemplo.com/", lambda r: httpx.Response(200))

    def refuse(request):
        raise httpx.ConnectError("recusado")

    with pytest.raises(FetchError, match="conectar"):
        await fetch("https://docs.exemplo.com/", refuse)


async def test_total_time_limit():
    async def slow(request):
        await asyncio.sleep(2)
        return httpx.Response(200)

    with pytest.raises(FetchError, match="demorou"):
        await fetch("https://docs.exemplo.com/", slow, time_limit=0.2)
