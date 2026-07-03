"""
The FieldWorkModel Mesa model class. Handles all Mesa-specific model 
mechanisms such as agent interaction and movement.

Aaron Stace, 03/07/2026
"""
import mesa
from mesa.space import NetworkGrid
import numpy as np

from agents import FieldWorker, Household
from mapping import build_graph_from_shapefile, load_addresses, \
    snap_addresses_to_nodes, load_network_data, to_wgs84
from config import ADDRESSES_FILEPATH


class FieldWorkModel(mesa.Model):
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_workers, area):
        
        super().__init__(seed=seed)

        gdf = load_network_data()
        G = build_graph_from_shapefile(gdf)
        gdf_addresses = load_addresses(ADDRESSES_FILEPATH)

        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        address_nodes = snap_addresses_to_nodes(gdf_addresses, G)
        self.households = [
            Household(model=self, node=node) for node in address_nodes
        ]

        # Store true geographic positions of addresses (WGS84) for the
        # visualisation background layer. These are display-only and do not
        # affect the simulation.
        self.address_lons, self.address_lats = to_wgs84(
            gdf_addresses.geometry.x, gdf_addresses.geometry.y
        )


        self.workers = [FieldWorker(i, self.random_location(
                                            area)) for i in range(num_workers)]
        self.area = area

        self.field_staff = FieldWorker.create_agents(model=self, 
                                                    n=self.num_field_staff)
                                                    #also something about nodes) 

    def get_field_staff_positions(self):
        """
        Return the current WGS84 positions of all field staff agents.

        Reads each agent's current node (an (easting, northing) tuple in
        EPSG:27700) and converts to longitude/latitude for the Dash map layer.

        Returns
        -------
        lons, lats : tuple of lists
        """
        eastings = [agent.node[0] for agent in self.field_staff]
        northings = [agent.node[1] for agent in self.field_staff]
        return to_wgs84(eastings, northings)

    def step(self):
        self.field_staff.shuffle_do('step')
        # Probably needs a step for data collection as well
        # Could have a one-off end of day method that sends field staff back to one
        # or two houses that didn't answer