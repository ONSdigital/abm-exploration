"""
This agent-based model attempts to represent the spread of sentiment towards a 
census in a student hall of residence, with varying numbers of student 
ambassadors that have a positive influence on sentiment.
"""
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
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

# Building a graph, where LineStrings are edges and endpoints are nodes
def build_graph_from_shapefile(gdf):
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
    A student, living in a university hall of residence, with an initial 
    sentiment towards the census between 0 and 1. The student can be influenced 
    by other students, and by student ambassadors, to change their sentiment.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.sentiment = self.random.uniform(0, 1)
        model.grid.place_agent(self, node)

    def move(self):
        """
        Student moves to a random neighbouring node.
        """
        neighbors = list(self.model.graph.neighbors(self.node))
        if neighbors:
            new_node = self.random.choice(neighbors)
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
    def __init__(self, n_stu, n_amb, seed=None):
        """
        Initialises the spatial hall of residence model.

        Args:
            n_stu: Number of students in the hall of residence.
            n_amb: Number of ambassadors in the hall of residence.
            seed: Random seed for reproducibility.
        """
        
        super().__init__(seed=seed)

        G = build_graph_from_shapefile(gdf)
        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        self.num_students = n_stu
        self.num_ambassadors = n_amb

        self.students = Student.create_agents(model=self, n=self.num_students, 
                    node=self.random.choices(self.node_list, 
                    k=self.num_students))
        self.ambassadors = Ambassador.create_agents(model=self, 
                    n=self.num_ambassadors, 
                    node=self.random.choices(self.node_list, 
                    k=self.num_ambassadors))

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
}

model = HallOfResidence(n_stu=50, n_amb=1, seed=None)

print('Model has finished running.')

page = SolaraViz(model=model,
                 components=[NetworkPlot, make_plot_component('Mean Sentiment')],
                 model_params=model_params,
                 name='Uni of Manchester ABM'
)
