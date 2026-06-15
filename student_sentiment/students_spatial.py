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
import traceback
from pathlib import Path

from mesa.space import NetworkGrid
from mesa.visualization import SolaraViz, make_plot_component
from mesa.visualization.utils import update_counter
from matplotlib.collections import LineCollection

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
        'max': 50,
        'step': 1,
    },
    'interaction_chance_amb': {
        'type': 'SliderFloat',
        'value': 0.20,
        'label': 'Prob: stu-amb interaction',
        'min': 0.0,
        'max': 1.0,
        'step': 0.05,
    },
    'interaction_chance_stu': {
        'type': 'SliderFloat',
        'value': 0.10,
        'label': 'Prob: stu-stu interaction',
        'min': 0.0,
        'max': 1.0,
        'step': 0.05,
    },
    'amb_sentiment': {
        'type': 'SliderFloat',
        'value': 0.9,
        'label': 'Ambassador sentiment',
        'min': 0.0,
        'max': 1.0,
        'step': 0.05,
    },
    'amb_large_increase': {
        'type': 'SliderFloat',
        'value': 0.25,
        'label': 'Amb. boost: low sentiment student',
        'min': 0.2,
        'max': 0.5,
        'step': 0.05,
    },
    'amb_medium_increase': {
        'type': 'SliderFloat',
        'value': 0.15,
        'label': 'Amb. boost: medium sentiment student',
        'min': 0.1,
        'max': 0.3,
        'step': 0.05,
    },
    'amb_small_increase': {
        'type': 'SliderFloat',
        'value': 0.05,
        'label': 'Amb. boost: high sentiment student',
        'min': 0.0,
        'max': 0.2,
        'step': 0.05,
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
    # Road where student spawn bias is centralised.
    'home_road': 'Oxford Road',
    # Road where ambassadors spawn exclusively. Use a list for multiple roads,
    # e.g. ['Oxford Road', 'Wilmslow Road']. None = same as students.
    'amb_road': ['Oxford Road', 'Lime Grove', 'Burlington Street'],
}

def load_road_data():
    """
    Load the road shapefile and detect the best road-name column.
    """
    data_path = Path(__file__).resolve().parent / "UoM_road_shapefiles" / "OpenRoads_UniOfManchester.shp"
    print(f"Loading shapefile from: {data_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"Shapefile not found: {data_path}")
    gdf = gpd.read_file(data_path)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # Identify the road name column used by the loaded dataset.
    name_col_candidates = ['roadName', 'name1', 'road_name', 'NAME', 'name']
    name_col = next((c for c in name_col_candidates if c in gdf.columns), None)
    if name_col is None:
        obj_cols = gdf.select_dtypes('object').columns
        name_col = obj_cols[0] if len(obj_cols) else None

    if name_col is None:
        print("Warning: no road name column found — home_road and amb_road "
              "spawning will be unavailable. Available columns: "
              f"{gdf.columns.tolist()}")
    else:
        print(f"Road name column: '{name_col}'")

    return gdf, name_col


def get_road_nodes(G, road_name, gdf, name_col):
    """
    Returns all nodes in the road graph that lie on roads whose name contains 
    road_name.
    """
    matches = gdf[gdf[name_col].str.contains(road_name, case=False, na=False)]
    nodes = set()
    for _, row in matches.iterrows():
        for coord in row.geometry.coords:
            if coord in G.nodes:
                nodes.add(coord)
    return list(nodes)


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

    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()

    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
    print(f"Connected components: {nx.number_connected_components(G)}")

    return G


# Road data and graph loaded once at module level to avoid repeated disk reads
# on each model reset (e.g. when Solara rebuilds the model from slider changes).
try:
    _CACHED_GDF, _CACHED_NAME_COL = load_road_data()
    _CACHED_GRAPH = build_graph_from_shapefile(_CACHED_GDF)
except Exception as _e:
    print(f"FATAL: Failed to load road data at startup: "
          f"{type(_e).__name__}: {_e}")
    raise


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
        self.sentiment = min(1, max(0, self.random.gauss(0.5, sigma=0.1)))
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
        node. There is a 10% chance of interacting with another student and a
        20% chance of interacting with an ambassador.
        """
        other_people = [a for a in self.model.grid.get_cell_list_contents([
            self.node]) if a is not self]

        if other_people:
            person = self.random.choice(other_people)
            if isinstance(person, Ambassador):
                if self.random.random() < self.model.interaction_chance_amb:
                    if self.sentiment <= 0.5:
                        self.sentiment = min(1, self.sentiment + 
                                            self.model.amb_large_increase)
                    if 0.5 < self.sentiment <= 0.75:
                        self.sentiment = min(1, self.sentiment + 
                                            self.model.amb_medium_increase)
                    if 0.75 < self.sentiment <= 1:
                        self.sentiment = min(1, self.sentiment + 
                                            self.model.amb_small_increase)
            else:
                if self.random.random() < self.model.interaction_chance_stu:
                    avg = (self.sentiment + person.sentiment) / 2
                    self.sentiment = avg
                    person.sentiment = avg

    def sentiment_decay(self):
        """
        Student sentiment decays over time, very gradually decreasing.
        """
        self.sentiment = self.sentiment * 0.99

    def step(self):
        self.move()
        self.interaction()
        self.sentiment_decay()


class Ambassador(mesa.Agent):
    """
    A student ambassador on the UoM campus, with a positive sentiment towards 
    the census. The ambassador can influence other students to increase their 
    sentiment.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.sentiment = self.model.amb_sentiment

        model.grid.place_agent(self, node)


class HallOfResidence(mesa.Model):
    """
    A university hall of residence, with a certain number of students and 
    ambassadors.
    """
    def __init__(self, n_stu, n_amb, amb_sentiment=0.9, amb_large_increase=0.25,
                 amb_medium_increase=0.15, amb_small_increase=0.05,
                 interaction_chance_amb=0.20, interaction_chance_stu=0.10,
                 straight_bias=2.0, home_road='', 
                 home_road_weight=20.0, amb_road=None, seed=None, gdf=None, 
                 _NAME_COL=None):
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
            gdf: Optional GeoDataFrame containing the road data. If None, it will
                be loaded from the default shapefile.
            _NAME_COL: Optional name of the column in gdf that contains road names.
                 If None, it will be auto-detected from common candidates or any
                 object-type column.
        """
        
        super().__init__(seed=seed)

        if gdf is None:
            gdf = _CACHED_GDF
            _NAME_COL = _CACHED_NAME_COL

        G = _CACHED_GRAPH if gdf is _CACHED_GDF else build_graph_from_shapefile(gdf)
        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        self.num_students = n_stu
        self.num_ambassadors = n_amb
        self.amb_sentiment = amb_sentiment
        self.amb_large_increase = amb_large_increase
        self.amb_medium_increase = amb_medium_increase
        self.amb_small_increase = amb_small_increase
        self.interaction_chance_amb = interaction_chance_amb
        self.interaction_chance_stu = interaction_chance_stu
        self.straight_bias = straight_bias

        self.gdf = gdf
        self._NAME_COL = _NAME_COL

        # Build spawn weights biased towards home_road if specified
        spawn_weights = None
        if home_road:
            road_nodes = set(get_road_nodes(G, home_road, gdf, _NAME_COL))
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
                for node in get_road_nodes(G, road, gdf, _NAME_COL)
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
        self.datacollector.collect(self)


@solara.component
def NetworkPlot(model):
    update_counter.value  # Subscribe to Mesa's step counter to re-render on each step

    G = model.graph

    # Cache edge segments — the road network doesn't reload between steps
    edge_segments = solara.use_memo(
        lambda: [[(u[0], u[1]), (v[0], v[1])] for u, v in G.edges()],
        dependencies=[]
    )

    fig, ax = plt.subplots(figsize=(10, 8))

    # Draw all edges in a single LineCollection instead of one ax.plot() per edge
    lc = LineCollection(edge_segments, colors='gray', linewidths=0.5, zorder=1)
    ax.add_collection(lc)

    # Draw all agents in a single scatter call
    xs, ys, colors = zip(*[
        (a.node[0], a.node[1],
         'black' if isinstance(a, Ambassador)
         else 'red' if a.sentiment < 0.25
         else 'green' if a.sentiment > 0.75
         else 'orange')
        for a in model.agents
    ])
    ax.scatter(xs, ys, c=colors, s=20, zorder=2)

    ax.set_aspect('equal')
    ax.autoscale()  # Required after add_collection to fit the axes to the data
    ax.axis('off')
    solara.FigureMatplotlib(fig)
    plt.close(fig)


@solara.component
def Page():
    model = solara.use_reactive(None)
    init_error = solara.use_reactive(None)

    def init_model():
        try:
            m = HallOfResidence(n_stu=50,
                                n_amb=1,
                                straight_bias=2.0,
                                home_road='Oxford Road',
                                seed=None)

            model.value = m
            init_error.value = None
        except Exception as exc:
            init_error.value = f"{type(exc).__name__}: {exc}"
            print("Model initialization failed:")
            print(traceback.format_exc())

    solara.use_effect(init_model, dependencies=[])

    if init_error.value is not None:
        return solara.Markdown(f"Initialization failed: `{init_error.value}`")

    if model.value is None:
        return solara.HTML("Initializing model...")

    solara.Style(".v-navigation-drawer { min-width: 380px !important; width: 380px !important; }")
    return SolaraViz(model=model.value,
                     components=[NetworkPlot, 
                                 make_plot_component('Mean Sentiment')],
                     model_params=model_params,
                        name='Uni of Manchester ABM')

page = Page