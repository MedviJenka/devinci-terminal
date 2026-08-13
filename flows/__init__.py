"""Flows — user-designed, reusable pipelines over discovered catalog nodes.

A Flow is an immutable DAG of FlowNodes (topo.py orders it into parallel layers;
store.py saves/loads it as YAML). The executor walks it and runs each node
through runtime.runner.
"""

from flows.author import Completion, author_flow
from flows.builder import GraphBuilder
from flows.executor import NodeEvent, NodeStatus, RunReport, execute
from flows.graph import Edge, EdgeKind, Graph, GraphNode, validate_graph
from flows.graph_store import list_graphs, load_graph, save_graph
from flows.interpreter import GraphReport, run_graph
from flows.models import Flow, FlowNode
from flows.parsing import parse_flow_mapping
from flows.store import list_flows, load, save
from flows.topo import topo_layers

__all__ = [
    "Flow",
    "FlowNode",
    "topo_layers",
    "parse_flow_mapping",
    "save",
    "load",
    "list_flows",
    "save_graph",
    "load_graph",
    "list_graphs",
    "execute",
    "NodeEvent",
    "NodeStatus",
    "RunReport",
    "author_flow",
    "Completion",
    "Edge",
    "EdgeKind",
    "Graph",
    "GraphNode",
    "GraphBuilder",
    "validate_graph",
    "GraphReport",
    "run_graph",
]
