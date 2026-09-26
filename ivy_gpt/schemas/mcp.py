from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class MCPServerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    transport: str = Field(min_length=1, max_length=40)
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned_headers = {}

        for key, header_value in value.items():
            cleaned_key = key.strip()

            if not cleaned_key:
                raise ValueError("Header names cannot be empty.")

            cleaned_headers[cleaned_key] = str(header_value)

        return cleaned_headers

    @model_validator(mode="after")
    def validate_transport_fields(self):
        transport = self.transport.strip().lower()

        if transport == "stdio" and not self.command:
            raise ValueError("command is required for stdio MCP servers.")

        http_transports = {
            "streamable-http",
            "streamable_http",
            "httpstream",
            "httpstreams",
            "http-stream",
            "http-streams",
            "sse",
        }

        if transport in http_transports and not self.url:
            raise ValueError("url is required for HTTP MCP servers.")

        return self


class MCPOAuthStartRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return MCPServerCreateRequest.validate_headers(value)


class MCPOAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class MCPServerResponse(BaseModel):
    id: str
    name: str
    transport: str
    command: str | None = None
    args: list[str]
    url: str | None = None
    headers: dict[str, str]
    tool_specs: list[dict] = Field(default_factory=list)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MCPServerListResponse(BaseModel):
    servers: list[MCPServerResponse]
