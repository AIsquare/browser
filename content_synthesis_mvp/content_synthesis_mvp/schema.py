from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import json

@dataclass
class DiscoveryMetadata:
    keywords: list[str] = field(default_factory=list)
    tfidf_vector: list[float] = field(default_factory=list)
    semantic_embedding: list[float] = field(default_factory=list)
    topic_cluster: int | None = None

@dataclass
class SourceMetadata:
    url: str
    title: str = ""
    author: Optional[str] = None
    published_date: Optional[str] = None
    language: Optional[str] = None


@dataclass
class Content:
    markdown: str
    headings: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)


@dataclass
class DiscoveryFeatures:
    keywords: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    topic_cluster: Optional[int] = None
    discovered_topic: Optional[str] = None


@dataclass
class DocumentAnalysis:
    topic: Optional[str] = None
    subtopics: list[str] = field(default_factory=list)
    relevance: Optional[int] = None
    coverage: Optional[int] = None
    depth: Optional[int] = None
    explanatory_quality: Optional[int] = None
    intent: Optional[str] = None
    content_classes: list[str] = field(default_factory=list)
    narrative_roles: list[str] = field(default_factory=list)
    possible_exclusions: list[dict[str, str]] = field(default_factory=list)
    key_concepts: list[str] = field(default_factory=list)


@dataclass
class Document:
    document_id: str
    source: SourceMetadata
    content: Content
    fetched_at: Optional[str] = None
    content_hash: Optional[str] = None
    discovery: DiscoveryFeatures = field(default_factory=DiscoveryFeatures)
    analysis: DocumentAnalysis = field(default_factory=DocumentAnalysis)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
