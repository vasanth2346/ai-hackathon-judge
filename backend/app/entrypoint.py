import logging
import os
import signal
import subprocess
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("proof.entrypoint")
shutdown_requested = False


def request_shutdown(_signal_number, _frame):
    global shutdown_requested
    shutdown_requested = True


def stop_process(process: subprocess.Popen | None):
    if not process or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    worker_enabled = os.getenv("START_JUDGE_WORKER", "true").strip().lower() not in {"0", "false", "no", "off"}
    concurrency = max(1, int(os.getenv("JUDGE_WORKER_CONCURRENCY", "2")))
    port = os.getenv("PORT", "8000")
    api = None
    worker = None
    restart_delay = 2
    worker_started_at = None
    try:
        if worker_enabled:
            worker = subprocess.Popen([
                "celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO",
                f"--concurrency={concurrency}",
            ])
            worker_started_at = time.monotonic()
            logger.info("Started judge worker with concurrency=%s", concurrency)

        api = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port,
        ])
        logger.info("Started API on port %s", port)

        while api.poll() is None and not shutdown_requested:
            if worker_enabled and worker and worker.poll() is not None:
                logger.error("Judge worker exited with code %s; restarting in %s seconds", worker.returncode, restart_delay)
                time.sleep(restart_delay)
                if shutdown_requested:
                    break
                worker = subprocess.Popen([
                    "celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO",
                    f"--concurrency={concurrency}",
                ])
                worker_started_at = time.monotonic()
                restart_delay = min(restart_delay * 2, 60)
            elif worker_enabled and worker and worker_started_at and time.monotonic() - worker_started_at >= 60:
                restart_delay = 2
            time.sleep(1)
        return api.returncode or 0
    finally:
        stop_process(api)
        stop_process(worker)


if __name__ == "__main__":
    raise SystemExit(main())
