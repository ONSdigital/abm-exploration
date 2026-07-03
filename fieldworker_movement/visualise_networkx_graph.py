"""
Quick standalone visualisation of the road/path NetworkX graph.
Run with:  python visualise_networkx_graph.py

Plots all edges colour-coded by type (road/path/connector) and prints
connectivity diagnostics so you can verify the two networks are joined.
Also plots location of addresses, denoted by orange squares.
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
import networkx as nx
from pathlib import Path

from fieldwork_movement import load_network_data, build_graph_from_shapefile, \
                                connect_components, load_addresses
from fieldwork_movement import ADDRESSES_FILEPATH, ROADS_FILEPATH, PATHS_FILEPATH

EDGE_COLOURS = {
    'road':      '#4a90d9',   # blue
    'path':      '#4caf50',   # green
    'connector': '#e74c3c',   # red  – should be rare; flags synthetic joins
}

def main():
    print("Loading network data...")
    gdf = load_network_data(roads_file = ROADS_FILEPATH, 
                            paths_file = PATHS_FILEPATH)
    print(f"  Combined GDF rows: {len(gdf)}, types:"
          f" {gdf['type'].value_counts().to_dict()}")

    print("\nBuilding graph...")
    G = build_graph_from_shapefile(gdf)

    print("\nConnecting components...")
    G = connect_components(G, tolerance=5.0)

    # ── Diagnostics ──────────────────────────────────────────────────────────
    print(f"\nFinal graph  —  nodes: {G.number_of_nodes():,}, "
          f"edges: {G.number_of_edges():,}")
    print(f"Connected components: {nx.number_connected_components(G)}")

    edge_type_counts = {}
    for _, _, data in G.edges(data=True):
        t = data.get('type', 'unknown')
        edge_type_counts[t] = edge_type_counts.get(t, 0) + 1
    print("Edge counts by type:", edge_type_counts)

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 12))
    ax.set_aspect('equal')
    ax.set_title('Newcastle road + path network', fontsize=14)

    # Draw edges grouped by type for efficiency

    segments_by_type = {t: [] for t in EDGE_COLOURS}
    for u, v, data in G.edges(data=True):
        t = data.get('type', 'road')
        segments_by_type.setdefault(t, []).append([u, v])

    for edge_type, segments in segments_by_type.items():
        if not segments:
            continue
        colour = EDGE_COLOURS.get(edge_type, '#999999')
        lc = LineCollection(
            segments,
            colors=colour,
            linewidths=0.8 if edge_type == 'road' else 0.5,
            alpha=0.7,
            zorder=2 if edge_type == 'connector' else 1,
        )
        ax.add_collection(lc)

    address_df = load_addresses(ADDRESSES_FILEPATH)

    ax.scatter(
        address_df['ai_easting'],
        address_df['ai_northing'],
        s=10, color='orange', marker='s', zorder=3, label='Addresses'
    )

    # Fit axes to the node coordinates
    xs = [n[0] for n in G.nodes()]
    ys = [n[1] for n in G.nodes()]
    margin_x = (max(xs) - min(xs)) * 0.02
    margin_y = (max(ys) - min(ys)) * 0.02
    ax.set_xlim(min(xs) - margin_x, max(xs) + margin_x)
    ax.set_ylim(min(ys) - margin_y, max(ys) + margin_y)

    # Legend
    legend_handles = [
        mpatches.Patch(color=c, label=t.capitalize())
        for t, c in EDGE_COLOURS.items()
        if t in edge_type_counts
    ]
    ax.legend(handles=legend_handles, loc='upper right')

    ax.set_xlabel('Easting (m)')
    ax.set_ylabel('Northing (m)')
    plt.tight_layout()
    output_dir = Path(__file__).resolve().parent / "network_graphs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "network_graph.png"
    plt.savefig(output_path, dpi=150)
    print(f"\nSaved to {output_path}")
    plt.show()


if __name__ == '__main__':
    main()
