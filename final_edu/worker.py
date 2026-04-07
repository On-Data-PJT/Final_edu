from __future__ import annotations

from final_edu.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError("Worker 실행에는 REDIS_URL이 필요합니다.")

    try:
        from redis import Redis
        from rq import Worker
    except ImportError as exc:  # pragma: no cover - production installs these dependencies.
        raise RuntimeError("Worker 실행에는 redis 와 rq 패키지가 필요합니다.") from exc
    except Exception as exc:  # pragma: no cover - platform-specific worker import failures.
        if "cannot find context for 'fork'" in str(exc):
            raise RuntimeError(
                "현재 설치된 rq 버전은 Windows에서 `fork` 컨텍스트를 요구해 worker를 시작할 수 없습니다. "
                "로컬 웹 실행은 REDIS_URL 없이 inline/local fallback 을 사용하고, 별도 worker 는 WSL/Linux 환경에서 실행해 주세요."
            ) from exc
        raise RuntimeError("Worker 실행에 필요한 redis/rq 초기화에 실패했습니다.") from exc

    connection = Redis.from_url(settings.redis_url)
    worker = Worker([settings.queue_name], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
