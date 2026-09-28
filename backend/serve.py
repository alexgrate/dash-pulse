import os

from waitress import serve

from config.wsgi import application

serve(
    application,
    listen=os.environ.get("PULSE_LISTEN", "127.0.0.1:8765"),
    threads=8,
    trusted_proxy="127.0.0.1",
    trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
    clear_untrusted_proxy_headers=True,
)
