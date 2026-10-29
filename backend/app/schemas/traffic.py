from datetime import datetime

from pydantic import BaseModel


class TrafficLogResponse(BaseModel):
    id: str
    proxy_host_id: str
    host_name: str | None = None  # Virtual host domain name

    timestamp: datetime
    client_ip: str

    request_method: str
    request_uri: str
    query_string: str | None

    status: int
    response_time: int | None
    bytes_sent: int | None
    bytes_received: int | None

    upstream_addr: str | None
    upstream_response_time: int | None

    ssl_protocol: str | None
    ssl_cipher: str | None

    user_agent: str | None
    referer: str | None

    country_code: str | None
    country_name: str | None = None
    city: str | None = None
    auth_user: str | None
    is_bot: bool | None = None
    is_streaming: bool | None = None

    class Config:
        from_attributes = True


class TrafficStatsResponse(BaseModel):
    total_requests: int
    requests_today: int
    requests_this_week: int
    requests_by_status: dict[str, int]  # {"2xx": 100, "4xx": 20, ...}
    requests_by_method: dict[str, int]  # {"GET": 100, "POST": 20, ...}
    avg_response_time: float | None
    total_bytes_sent: int
    total_bytes_received: int
    top_ips: list[dict]  # [{"ip": "1.2.3.4", "count": 100}, ...]
    top_hosts: list[dict]  # [{"host_id": "...", "name": "...", "count": 100}, ...]


class TrafficQueryParams(BaseModel):
    proxy_host_id: str | None = None
    client_ip: str | None = None
    status_min: int | None = None
    status_max: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    skip: int = 0
    limit: int = 50
