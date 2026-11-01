"""NetworkX dependency and architecture graph builder foundation."""

import networkx as nx


class DependencyGraphBuilder:
    """Builds directed module and symbol dependency graphs using NetworkX."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()

    def add_module_node(self, module_id: str, language: str) -> None:
        self.graph.add_node(module_id, kind="module", language=language)

    def add_dependency_edge(self, source_id: str, target_id: str, relation: str = "imports") -> None:
        self.graph.add_edge(source_id, target_id, relation=relation)

    def to_summary_dict(self) -> dict[str, int]:
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
        }

