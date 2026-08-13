"""Discovery — scan .claude/ agents, skills, and commands into a node catalog.

The catalog is the composable-node source of truth the pipeline builder reads
from and the command_agent writes into.
"""

from discovery.models import NodeKind, CatalogNode, Diagnostic, Catalog
from discovery.frontmatter import parse_frontmatter
from discovery.scanner import scan
from discovery.writer import delete_node, write_node

__all__ = [
    "NodeKind",
    "CatalogNode",
    "Diagnostic",
    "Catalog",
    "parse_frontmatter",
    "scan",
    "delete_node",
    "write_node",
]
