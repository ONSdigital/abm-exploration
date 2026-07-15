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
    snap_addresses_to_nodes, load_network_data, load_lsoa_geojson, to_wgs84, \
    load_lsoa_completion_rates, connect_components
from config import ROADS_FILEPATH, PATHS_FILEPATH, ADDRESSES_FILEPATH, \
                LSOAS_FILEPATH, LSOA_CODE_COLUMN, \
                LSOA_COMPLETION_FILEPATH, INITIAL_COMPLETION_COLUMN, \
                ONGOING_COMPLETION_COLUMN, DEFAULT_INITIAL_COMPLETION_RATE, \
                DEFAULT_ONGOING_COMPLETION_RATE, \
                DEFAULT_HOUSEHOLD_RESPONSE_CHANCE


class FieldWorkModel(mesa.Model):
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_field_staff):
        
        super().__init__()

        gdf = load_network_data(ROADS_FILEPATH, PATHS_FILEPATH)
        G = build_graph_from_shapefile(gdf)
        G = connect_components(G)
        gdf_addresses = load_addresses(ADDRESSES_FILEPATH)
        self.lsoa_completion_rates = load_lsoa_completion_rates(
            LSOA_COMPLETION_FILEPATH
        )

        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        self.lsoa_stats = defaultdict(lambda: {
            'knocks': 0,
            'interactions': 0,
            'questionnaire_completions': 0,
            'initial_questionnaire_completions': 0,
            'ongoing_questionnaire_completions': 0,
            'remaining_households': 0,
            'total_households': 0,
        })

        address_nodes = snap_addresses_to_nodes(gdf_addresses, G)
        self.households = []
        for node, lsoa in address_nodes:
            completion_rates = self.get_lsoa_completion_rates(lsoa)
            survey_completed = (
                self.random.random() < completion_rates[INITIAL_COMPLETION_COLUMN]
            )
            household = Household(
                model=self,
                node=node,
                lsoa=lsoa,
                response_chance=DEFAULT_HOUSEHOLD_RESPONSE_CHANCE,
                initial_completion_rate=completion_rates[INITIAL_COMPLETION_COLUMN],
                ongoing_completion_rate=completion_rates[ONGOING_COMPLETION_COLUMN],
                survey_completed=survey_completed,
            )
            self.households.append(household)
            self.lsoa_stats[lsoa]['total_households'] += 1
            self.lsoa_stats[lsoa]['remaining_households'] += 1
            if survey_completed:
                self.register_completion(household, source='initial', step_number=0)

        # Build a node → [Household, ...] lookup for fast access in visit_household.
        self.node_to_households = defaultdict(list)
        for household in self.households:
            self.node_to_households[household.node].append(household)

        # One entry per step: {'step': N, 'lsoa_stats': {lsoa: {knocks, interactions}}}
        self.step_history = []

        # Storing display-only true geographic positions of addresses (WGS84) 
        # for the visualisation background layer.
        self.address_lons, self.address_lats = to_wgs84(
            gdf_addresses.geometry.x, gdf_addresses.geometry.y
        )

        # LSOA polygon geometry for the live choropleth layer.
        self.lsoa_geojson, self.lsoa_ids, self.lsoa_names = load_lsoa_geojson(
            LSOAS_FILEPATH, LSOA_CODE_COLUMN
        )

        self.field_staff = FieldWorker.create_agents(
            model=self,
            n=num_field_staff,
            node=[self.random.choice(self.node_list) for _ in range(num_field_staff)]
        )

    def get_lsoa_completion_rates(self, lsoa_code):
        """
        Return completion-rate settings for an LSOA with defaults.
        """
        return self.lsoa_completion_rates.get(str(lsoa_code), {
            INITIAL_COMPLETION_COLUMN: DEFAULT_INITIAL_COMPLETION_RATE,
            ONGOING_COMPLETION_COLUMN: DEFAULT_ONGOING_COMPLETION_RATE,
        })

    def register_completion(self, household, source, step_number):
        """
        Update LSOA completion counters when a household completes a Census
        questionnaire.
        """
        if source not in {'initial', 'ongoing'}:
            raise ValueError(f"Unknown completion source: {source}")

        if not household.survey_completed:
            completed_now = household.complete_survey(step_number, source)
            if not completed_now:
                return False
        elif household.completion_source != source and household.completion_step != step_number:
            return False

        stats = self.lsoa_stats[household.lsoa]
        stats['questionnaire_completions'] += 1
        stats[f'{source}_questionnaire_completions'] += 1
        stats['remaining_households'] -= 1
        return True

    def advance_electronic_completions(self):
        """
        Allow incomplete households to complete electronically this step.
        """
        for household in self.households:
            if household.survey_completed:
                continue
            if self.random.random() < household.ongoing_completion_rate:
                self.register_completion(
                    household,
                    source='ongoing',
                    step_number=self.steps + 1,
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
        self.advance_electronic_completions()
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