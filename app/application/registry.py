from app.domain.mapping import Mapping
from app.domain.mappings.creative import CreativeMapping
from app.domain.mappings.session import SessionMapping
from app.domain.mappings.viewer import ViewerMapping

REGISTRY: list[Mapping] = [
    ViewerMapping(),
    CreativeMapping(),
    SessionMapping(),
]
