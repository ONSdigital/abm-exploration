"""
An ABM modelling the movement of field workers around a neighbourhood, visiting
households.

Aaron Stace, 08/06/2026
"""
import numpy as np
import matplotlib.pyplot as plt
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


def load_road_data():
    """
    Load the road shapefile and detect the best road-name column.
    """
    data_path = Path(__file__).resolve().parent / "UoM_road_shapefiles" / "OpenRoads_UniOfManchester.shp"
    gdf = gpd.read_file(data_path)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # Identify the road name column used by the loaded dataset.
    name_col_candidates = ['roadName', 'name1', 'road_name', 'NAME', 'name']
    name_col = next((c for c in name_col_candidates if c in gdf.columns), None)
    if name_col is None:
        obj_cols = gdf.select_dtypes('object').columns
        name_col = obj_cols[0] if len(obj_cols) else None

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

    G = G.subgraph(max(nx.connected_components(G), key=len))

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

        # Remember to add something at the end of the day for them to 

    def arrive(self):
        """
        Governs the time a field worker spends between moving to an address and 
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

    def interaction(self):
        """
        Placeholder for the logic where a field worker interacts with a 
        household member.
        """

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
        # door to them during the day on their way back.

    def step(self):

        self.move()
        self.visit_household()


class Household():
    """
    MAYBE HAVE THESE AT THE HOUSE POINTS ON THE MAP. Might have to overlay the 
    road map with one containing house numbers or something, and then have the 
    field work agents visit each house.
    """


class FieldWorkModel():
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_workers, area):
        self.workers = [FieldWorker(i, self.random_location(
                                            area)) for i in range(num_workers)]
        self.area = area

    def step(self):
        # Placeholder for a method that updates the state of the model at each time step
        for worker in self.workers:
            worker.step()


    # Could have a one-off end of day method that sends field staff back to one
    # or two houses that didn't answer