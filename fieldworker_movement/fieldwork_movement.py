"""
An ABM modelling the movement of field workers around a neighbourhood, visiting
households.

Aaron Stace, 08/06/2026
"""
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd
import network as nx
import solara
import mesa
import traceback
from pathlib import Path

from shapely.ops import nearest_points
from mesa.space import NetworkGrid
from mesa.visualization import SolaraViz, make_plot_component
from mesa.visualization.utils import update_counter
from matplotlib.collections import LineCollection


model_params = {
    'n_field_staff': {
        'type': 'SliderInt',
        'value': 5,
        'label': 'No. of field staff',
        'min': 1,
        'max': 20,
        'step': 1,
    },
    'hh_response_chance': {
        'type': 'SliderInt',
        'value': 0.5,
        'label': 'P(household responds to knock)',
        'min': 0,
        'max': 1,
    },
    'walking_speed': {
        'type'
    }
}


def load_network_data():
    """
    Load the Newcastle road and path geopackage files, tag each with a 'type'
    edge attribute ('road' or 'path'), and return them as a single combined
    GeoDataFrame.
    """
    base_path = Path(__file__).resolve().parent / "newcastle_upon_tyne_shapefiles"

    gdf_roads = gpd.read_file(base_path / "Roads" / "Newcastle_Upon_Tyne_Roads.gpkg")
    gdf_roads['type'] = 'road'

    gdf_paths = gpd.read_file(base_path / "Paths" / "Newcastle_Upon_Tyne_Paths.gpkg")
    gdf_paths['type'] = 'path'

    gdf = pd.concat([gdf_roads, gdf_paths], ignore_index=True)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    return gdf


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

    edge_list = []
    for row in gdf.itertuples(index=False):
        coords = list(row.geometry.coords)
        edge_len = row.geometry.length
        edge_type = row.type
        edge_list.extend(
            (start, end, {'length': edge_len, 'type': edge_type})
            for start, end in zip(coords[:-1], coords[1:])
        )

    G.add_edges_from(edge_list)
    nx.set_node_attributes(G, {node: node for node in G.nodes}, 'pos')

    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()

    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
    print(f"Connected components: {nx.number_connected_components(G)}")

    return G


class FieldWorker(mesa.Agent):
    """
    An agent representing a field worker. They move around the road network, 
    visiting households.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.prev_node = None
        model.grid.place_agent(self, node)

    def move(self):
        """
        Placeholder for movement logic.
        """
        # Field worker should move to the next unoccupied house - check copilot
        # for advice on how to do this. 


    # Maybe not necessary to include this
    def arrive(self):
        """
        Governs the time a field worker spends between getting to an address and 
        actually knocking on the door. Could include checking address, walking
        up to the door, etc.
        """
        # This distribution should have a long tail, and a peak at about 0-20
        # seconds.
        arrival_rng = np.random.Generator
        arrival_time = arrival_rng.lognormal(mean=5, sigma=20)
        # This time is in SECONDS, might have to change later on. 
        return arrival_time

    def knock(self):
        """
        Placeholder for the logic where a field worker knocks on a household's
        door. They may or may not answer.
        """
        # Include some sort of probability of someone in the house answering
        # the door.
        # We presumably have some data regarding what proportion of people 
        # answer the door to field staff?
        # If not in, put in a postcard. Does this prompt a response? Does it 
        # annoy them? 

    def interaction(self):
        """
        Placeholder for the logic where a field worker interacts with a 
        household member.
        """
        # Longer could mean higher P of success

    def visit_household(self):
        """
        Whole process of a field worker visiting a household: knocking, waiting
        for a response, then interacting if someone opens the door.
        """
        self.arrive()
        answered = self.knock()

        if answered:
            self.interaction()

    def back_home(self):
        """
        Field staff travel back home (assign some random direction to them, or
        back to some nearby car park/train station from where they finished 
        would be very clever.
        """
        # Field worker should visit a couple of houses that didn't answer the 
        # door to them during the day on their way back. Undecided as to how
        # this should be implemented.
        # Will vary depending on location, e.g. Westminster vs rural.

    def step(self):

        self.move()
        self.visit_household()


class NoOfHours(FieldWorker):
    """
    A subclass of the FieldWorker class that represents a certain number of
    hours per day that this type of field worker will do.
    """
    # Will need more than one of these eventually
    def __init__(self, model, node, hours_per_day):
        super().__init__(model, node)


class Household(mesa.Agent):
    """
    MAYBE HAVE THESE AT THE HOUSE POINTS ON THE MAP. Might have to overlay the 
    road map with one containing house numbers or something, and then have the 
    field work agents visit each house.
    """
    # Start with one type of household. Maybe have another household class that inherits later on?
    def __init__(self, model):

        super().__init__(model)

        self.hh_sentiment = hh_sent
        self.response_chance = response_chance


class FieldWorkModel(mesa.Model):
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_workers, area):
        
        super().__init__(seed=seed)

        self.workers = [FieldWorker(i, self.random_location(
                                            area)) for i in range(num_workers)]
        self.area = area

        self.field_staff = FieldWorker.create_agents(model=self, 
                                                    n=self.num_field_staff)
                                                    #also something about nodes) 

    def step(self):
        self.field_staff.shuffle_do('step')
        # Probably needs a step for data collection as well
        # Could have a one-off end of day method that sends field staff back to one
        # or two houses that didn't answer