"""
The FieldWorkModel Mesa model class. Handles all Mesa-specific model 
mechanisms such as agent interaction and movement.

Aaron Stace, 03/07/2026
"""
import mesa
from mesa.space import NetworkGrid
from collections import defaultdict

from agents import FieldWorker, Household
from mapping import build_graph_from_shapefile, load_addresses, \
    snap_addresses_to_nodes, load_network_data, load_lsoa_geojson, to_wgs84
from config import ROADS_FILEPATH, PATHS_FILEPATH, ADDRESSES_FILEPATH, \
                LSOAS_FILEPATH, LSOA_CODE_COLUMN


class FieldWorkModel(mesa.Model):
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_field_staff):
        
        super().__init__()

        gdf = load_network_data(ROADS_FILEPATH, PATHS_FILEPATH)
        G = build_graph_from_shapefile(gdf)
        gdf_addresses = load_addresses(ADDRESSES_FILEPATH)

        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        address_nodes = snap_addresses_to_nodes(gdf_addresses, G)
        self.households = [
            Household(model=self, node=node, lsoa=lsoa)
            for node, lsoa in address_nodes
        ]

        # Build a node → [Household, ...] lookup for fast access in visit_household.
        self.node_to_households = defaultdict(list)
        for household in self.households:
            self.node_to_households[household.node].append(household)

        # Per-LSOA knock and interaction counters (cumulative across all steps).
        self.lsoa_stats = defaultdict(lambda: {'knocks': 0, 'interactions': 0})

        # One entry per step: {'step': N, 'lsoa_stats': {lsoa: {knocks, interactions}}}
        self.step_history = []

        # Store true geographic positions of addresses (WGS84) for the
        # visualisation background layer. These are display-only and do not
        # affect the simulation.
        self.address_lons, self.address_lats = to_wgs84(
            gdf_addresses.geometry.x, gdf_addresses.geometry.y
        )

        # LSOA polygon geometry for the live choropleth layer.
        self.lsoa_geojson, self.lsoa_ids = load_lsoa_geojson(
            LSOAS_FILEPATH, LSOA_CODE_COLUMN
        )

        self.field_staff = FieldWorker.create_agents(
            model=self,
            n=num_field_staff,
            node=[self.random.choice(self.node_list) for _ in range(num_field_staff)]
        )

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
        # Snapshot cumulative LSOA stats for this step (shallow copy per LSOA).
        self.step_history.append({
            'step': self.steps,
            'lsoa_stats': {
                lsoa: dict(counts)
                for lsoa, counts in self.lsoa_stats.items()
            }
        })
        # Could have a one-off end of day method that sends field staff back to one
        # or two houses that didn't answer