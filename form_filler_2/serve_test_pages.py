import argparse
import contextlib
import logging
import socket
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def _find_free_port(requested: int) -> int:
    if requested:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_server(directory: Path, host: str, port: int, duration: int) -> None:
    directory = directory.resolve()
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )

    httpd = ThreadingHTTPServer((host, port), handler)

    logging.info("Serving %s on http://%s:%d (auto-shutdown in %ss)", directory, host, port, duration)

    # Stop the server after `duration` seconds to avoid running forever
    timer = threading.Timer(duration, httpd.shutdown)
    timer.daemon = True
    timer.start()

    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logging.info("Received Ctrl+C, shutting down...")
    finally:
        with contextlib.suppress(Exception):
            httpd.server_close()
        logging.info("Server stopped")


def main():
    parser = argparse.ArgumentParser(description="Serve local test HTML files with an auto-shutdown timer.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/IP to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="Port to bind (0 = auto)")
    parser.add_argument(
        "--duration",
        type=int,
        default=600,
        help="Seconds before auto-shutdown to avoid long-running server (default: 600)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "form_filler_bot" / "test_pages",
        help="Directory to serve (default: form_filler_bot/test_pages)",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    port = _find_free_port(args.port)

    # Helpful hint for the Datadog page
    candidate = args.dir / "datadog_job_7073137_app.html"
    if candidate.exists():
        logging.info("Example URL: http://%s:%d/%s", args.host, port, candidate.name)
    else:
        logging.warning("Expected file not found: %s", candidate)

    run_server(args.dir, args.host, port, args.duration)


if __name__ == "__main__":
    main()

