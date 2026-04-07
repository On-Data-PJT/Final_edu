from __future__ import annotations

from final_edu.config import get_settings


def main() -> None:
    try:
        from redis import Redis
        from rq import Worker
    except ImportError as exc:  # pragma: no cover - production installs these dependencies.
        raise RuntimeError("Worker 실행에는 redis 와 rq 패키지가 필요합니다.") from exc

    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("Worker 실행에는 REDIS_URL이 필요합니다.")

    connection = Redis.from_url(settings.redis_url)
    worker = Worker([settings.queue_name], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
