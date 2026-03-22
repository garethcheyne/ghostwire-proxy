from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TrafficLogResponse(BaseModel):
    id: str
    proxy_host_id: str
    host_name: Optional[str] = None  # Virtual host domain name

    timestamp: datetime
    client_ip: str

    request_method: str
    request_uri: str
    query_string: Optional[str]

    status: int
    response_time: Optional[int]
    bytes_sent: Optional[int]
    bytes_received: Optional[int]

    upstream_addr: Optional[str]
    upstream_response_time: Optional[int]

    ssl_protocol: Optional[str]
    ssl_cipher: Optional[str]

    user_agent: Optional[str]
    referer: Optional[str]

    country_code: Optional[str]
    country_name: Optional[str] = None
    auth_user: Optional[str]

    class Config:
        from_attributes = True


class TrafficStatsResponse(BaseModel):
    total_requests: int
    requests_today: int
    requests_this_week: int
    requests_by_status: dict[str, int]  # {"2xx": 100, "4xx": 20, ...}
    requests_by_method: dict[str, int]  # {"GET": 100, "POST": 20, ...}
    avg_response_time: Optional[float]
    total_bytes_sent: int
    total_bytes_received: int
    top_ips: list[dict]  # [{"ip": "1.2.3.4", "count": 100}, ...]
    top_hosts: list[dict]  # [{"host_id": "...", "name": "...", "count": 100}, ...]


class TrafficQueryParams(BaseModel):
    proxy_host_id: Optional[str] = None
    client_ip: Optional[str] = None
    status_min: Optional[int] = None
    status_max: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    skip: int = 0
    limit: int = 50
