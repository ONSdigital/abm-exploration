"""
This agent-based model attempts to represent the spread of sentiment towards a 
census in a student hall of residence, with varying numbers of student 
ambassadors that have a positive influence on sentiment.
"""
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
import networkx as nx
import solara

import mesa
from mesa.space import NetworkGrid
from mesa.visualization import SolaraViz, make_plot_component
from mesa.visualization.utils import update_counter
from matplotlib.collections import LineCollection

gdf = gpd.read_file("C:\\Users\\stacea\\abm-exploration\\UoM_road_shapefiles\\OpenRoads_UniOfManchester.shp")
gdf = gdf.explode(index_parts=False).reset_index(drop=True) # Explode MultiLineStrings into LineStrings
print(gdf.geom_type.value_counts()) # Should be 'LineString'
print(gdf.crs) # Checks coordinate system
print(f"Shapefile columns: {gdf.columns.tolist()}")

# Identify the road name column — OS OpenRoads SHP files use 'roadName';
# GeoPackage versions sometimes use 'name1'. Fall back to the first text column.
_NAME_COL_CANDIDATES = ['roadName', 'name1', 'road_name', 'NAME', 'name']
_NAME_COL = next((c for c in _NAME_COL_CANDIDATES if c in gdf.columns), None)
if _NAME_COL is None:
    _obj_cols = gdf.select_dtypes('object').columns
    _NAME_COL = _obj_cols[0] if len(_obj_cols) else None
if _NAME_COL:
    road_names = sorted(gdf[_NAME_COL].dropna().unique().tolist())
    print(f"Using '{_NAME_COL}' as road name column — {len(road_names)} named "
          f"roads found. Pass one of these as home_road= in HallOfResidence().")
    print(road_names)
else:
    road_names = []
    print("Warning: no road name column found — home_road spawning unavailable.")


def get_road_nodes(G, road_name):
    """
    Returns all nodes in the road graph that lie on roads whose name contains 
    road_name.
    """
    matches = gdf[gdf[_NAME_COL].str.contains(road_name, case=False, na=False)]
    nodes = set()
    for _, row in matches.iterrows():
        for coord in row.geometry.coords:
            if coord in G.nodes:
                nodes.add(coord)
    return list(nodes)


# Building a graph, where LineStrings are edges and endpoints are nodes
def build_graph_from_shapefile(gdf):
    """
    Builds a graph that matches the road layout on the shapefile. Made out of
    'nodes' and 'edges'. Edges are LineStrings, and nodes are their endpoints.
    """
    G = nx.Graph()
    for _, row in gdf.iterrows():
        coords = list(row.geometry.coords)
        for start, end in zip(coords[:-1], coords[1:]):
            G.add_node(start, pos=start)
            G.add_node(end, pos=end)
            G.add_edge(start, end, length=row.geometry.length)

    G = G.subgraph(max(nx.connected_components(G), key=len))

    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
    print(f"Connected components: {nx.number_connected_components(G)}")

    return G


class Student(mesa.Agent):
    """
    A student with an initial sentiment towards the census between 0 and 1. The 
    student can be influenced by other students, and by student ambassadors, to 
    change their sentiment.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.prev_node = None
        self.sentiment = self.random.uniform(0, 1)
        model.grid.place_agent(self, node)

    def move(self):
        """
        Student moves to a neighbouring node, biased towards continuing
        in the current direction of travel. The strength of the bias is
        controlled by model.straight_bias: 0 is fully random, higher
        values increasingly favour going straight.
        """
        neighbors = list(self.model.graph.neighbors(self.node))
        if not neighbors:
            return

        bias = self.model.straight_bias
        if self.prev_node is None or bias == 0 or len(neighbors) == 1:
            new_node = self.random.choice(neighbors)
        else:
            dx = self.node[0] - self.prev_node[0]
            dy = self.node[1] - self.prev_node[1]
            fwd_len = (dx ** 2 + dy ** 2) ** 0.5

            if fwd_len == 0:
                new_node = self.random.choice(neighbors)
            else:
                weights = []
                for nb in neighbors:
                    ndx = nb[0] - self.node[0]
                    ndy = nb[1] - self.node[1]
                    nb_len = (ndx ** 2 + ndy ** 2) ** 0.5
                    cos_sim = (dx * ndx + dy * ndy) / (fwd_len * nb_len) if nb_len else 0.0
                    weights.append(max(0.01, 1.0 + cos_sim * bias))

                total = sum(weights)
                r = self.random.random() * total
                cumulative = 0.0
                new_node = neighbors[-1]
                for nb, w in zip(neighbors, weights):
                    cumulative += w
                    if r <= cumulative:
                        new_node = nb
                        break

        self.prev_node = self.node
        self.model.grid.move_agent(self, new_node)
        self.node = new_node


    def interaction(self):
        """
        Student interacts with a random other student, and their sentiment 
        becomes the average sentiment of the two students. If the other student 
        is an ambassador, the sentiment is increased by a fixed amount.

        Sentiment only transferred to another student/ambassador in the same
        node.
        """
        other_person = [a for a in self.model.grid.get_cell_list_contents([
            self.node]) if a is not self]

        if other_person:
            person = self.random.choice(other_person)
            if isinstance(person, Ambassador):
                self.sentiment = min(1, self.sentiment + 0.25)
            else:
                self.sentiment = (self.sentiment + person.sentiment) / 2

    
    def step(self):
        self.move()
        self.interaction()


class Ambassador(mesa.Agent):
    """
    A student ambassador on the UoM campus, with a positive sentiment towards 
    the census. The ambassador can influence other students to increase their 
    sentiment.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.sentiment = 0.9

        model.grid.place_agent(self, node)


class HallOfResidence(mesa.Model):
    """
    A university hall of residence, with a certain number of students and 
    ambassadors.
    """
    def __init__(self, n_stu, n_amb, straight_bias=2.0, home_road='', 
                 home_road_weight=20.0, amb_road=None, seed=None):
        """
        Initialises the spatial hall of residence model.

        Args:
            n_stu: Number of students in the hall of residence.
            n_amb: Number of ambassadors in the hall of residence.
            straight_bias: How strongly agents prefer to continue in their
                current direction of travel. 0 = fully random, higher
                values = stronger preference for going straight.
            home_road: Name (or partial name) of the road where students spawn.
                Nodes on this road receive home_road_weight times more
                spawn probability than all other nodes. Empty string disables.
            home_road_weight: Relative spawn weight for home_road nodes vs
                the rest of the network.
            amb_road: List of road names (or partial names) where ambassadors
                spawn exclusively, e.g. ['Oxford Road', 'Wilmslow Road'].
                Nodes from all listed roads are pooled together. None or empty
                list falls back to the same spawn weights as students.
            seed: Random seed for reproducibility.
        """
        
        super().__init__(seed=seed)

        G = build_graph_from_shapefile(gdf)
        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        self.num_students = n_stu
        self.num_ambassadors = n_amb
        self.straight_bias = straight_bias

        # Build spawn weights biased towards home_road if specified
        spawn_weights = None
        if home_road:
            road_nodes = set(get_road_nodes(G, home_road))
            if road_nodes:
                spawn_weights = [
                    home_road_weight if n in road_nodes else 1.0
                    for n in self.node_list
                ]
                print(f"Spawning on '{home_road}': {len(road_nodes)} nodes "
                      f"(weight {home_road_weight}x vs rest of network)")
            else:
                print(f"Warning: no nodes found for road '{home_road}', "
                      f"spawning randomly.")

        self.students = Student.create_agents(model=self, n=self.num_students,
                    node=self.random.choices(self.node_list,
                    weights=spawn_weights, k=self.num_students))

        # Ambassadors spawn exclusively on amb_road roads if specified;
        # otherwise they use the same spawn weights as students.
        if amb_road:
            # Accept a bare string for convenience, normalise to list
            if isinstance(amb_road, str):
                amb_road = [amb_road]
            amb_nodes = list({
                node
                for road in amb_road
                for node in get_road_nodes(G, road)
            })
            if amb_nodes:
                print(f"Ambassador roads {amb_road}: {len(amb_nodes)} "
                      f"nodes total.")
                amb_spawn = self.random.choices(amb_nodes, 
                                                k=self.num_ambassadors)
            else:
                print(f"Warning: no nodes found for amb_road {amb_road}, "
                      f"falling back to student spawn weights.")
                amb_spawn = self.random.choices(self.node_list,
                    weights=spawn_weights, k=self.num_ambassadors)
        else:
            amb_spawn = self.random.choices(self.node_list,
                    weights=spawn_weights, k=self.num_ambassadors)

        self.ambassadors = Ambassador.create_agents(model=self,
                    n=self.num_ambassadors,
                    node=amb_spawn)

        self.datacollector = mesa.DataCollector(
            model_reporters={'Mean Sentiment': lambda m: np.mean([a.sentiment for a in m.students])},
            agent_reporters={'sentiment': 'sentiment'})
        self.datacollector.collect(self)

    def step(self):
        self.students.shuffle_do('step')
        self.ambassadors.shuffle_do('step')
        self.datacollector.collect(self)


@solara.component
def NetworkPlot(model):
    update_counter.value  # Subscribe to Mesa's step counter to re-render on each step

    G = model.graph

    # Cache edge segments — the road network never changes between steps
    edge_segments = solara.use_memo(
        lambda: [[(u[0], u[1]), (v[0], v[1])] for u, v in G.edges()],
        dependencies=[]
    )

    fig, ax = plt.subplots(figsize=(10, 8))

    # Draw all edges in a single LineCollection instead of one ax.plot() per edge
    lc = LineCollection(edge_segments, colors='gray', linewidths=0.5, zorder=1)
    ax.add_collection(lc)

    # Draw all agents in a single scatter call
    xs = [a.node[0] for a in model.agents]
    ys = [a.node[1] for a in model.agents]
    colors = [
        'black' if isinstance(a, Ambassador)
        else 'red' if a.sentiment < 0.25
        else 'green' if a.sentiment > 0.75
        else 'orange'
        for a in model.agents
    ]
    ax.scatter(xs, ys, c=colors, s=20, zorder=2)

    ax.set_aspect('equal')
    ax.autoscale()  # Required after add_collection to fit the axes to the data
    ax.axis('off')
    solara.FigureMatplotlib(fig)
    plt.close(fig)


model_params = {
    'n_stu': {
        'type': 'SliderInt',
        'value': 50,
        'label': 'Number of students',
        'min': 10,
        'max': 500,
        'step': 1,
    },
    'n_amb': {
        'type': 'SliderInt',
        'value': 1,
        'label': 'Number of ambassadors',
        'min': 0,
        'max': 10,
        'step': 1,
    },
    'straight_bias': {
        'type': 'SliderFloat',
        'value': 2.0,
        'label': 'Straight-line bias',
        'min': 0.0,
        'max': 10.0,
        'step': 0.5,
    },
    'home_road_weight': {
        'type': 'SliderFloat',
        'value': 20.0,
        'label': 'Home road spawn weight',
        'min': 1.0,
        'max': 100.0,
        'step': 1.0,
    },
    # Fixed value (no widget) — Mesa passes this directly to the constructor
    # on every reset. Change the string here to switch the home road.
    'home_road': 'Oxford Road',
    # Road where ambassadors spawn exclusively. Use a list for multiple roads,
    # e.g. ['Oxford Road', 'Wilmslow Road']. None = same as students.
    'amb_road': ['Oxford Road', 'Lime Grove', 'Burlington Street'],
}

model = HallOfResidence(n_stu=50, 
                        n_amb=1, 
                        straight_bias=2.0, 
                        seed=None,
                        home_road='Oxford Road')

print('Model has finished running.')

page = SolaraViz(model=model,
                 components=[NetworkPlot, make_plot_component('Mean Sentiment')],
                 model_params=model_params,
                 name='Uni of Manchester ABM'
)
