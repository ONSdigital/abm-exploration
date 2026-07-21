"""
An ABM modelling the movement of field workers around a local authority, 
visiting households.

Aaron Stace, 08/06/2026
"""
import mesa
import networkx as nx

from config import hh_interaction_mean, hh_interaction_std


class Household(mesa.Agent):
    """
    Household agents, located in the model at the nearest road/path node to 
    their actual geographical location.
    """
    # Start with one type of household. Maybe have another household class that 
    # inherits later on?
    def __init__(self, model, node, lsoa, response_chance=0.5,
                 initial_completion_rate=0.0, ongoing_completion_rate=0.0,
                 survey_completed=False):

        super().__init__(model)

        self.node = node
        self.lsoa = lsoa
        model.grid.place_agent(self, node)

        self.response_chance = response_chance
        self.initial_completion_rate = initial_completion_rate
        self.ongoing_completion_rate = ongoing_completion_rate
        self.survey_completed = survey_completed
        self.completion_step = 0 if survey_completed else None
        self.completion_source = 'initial' if survey_completed else None

    def complete_survey(self, step_number, source):
        """
        Mark the household's electronic survey as completed once only.

        Parameters
        ----------
        step_number : int
            The model step number at which the survey was completed.
        source : str
            The source of the survey completion ('initial' or 'ongoing').

        Returns
        -------
        bool
            True if the survey was completed now, False if it was already 
            completed.
        """
        if self.survey_completed:
            return False

        self.survey_completed = True
        self.completion_step = step_number
        self.completion_source = source
        return True


class FieldWorker(mesa.Agent):
    """
    An agent representing a field worker. They move around the road network, 
    visiting households.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.prev_node = None
        self.display_position = node
        self.target_node = None
        self.route_nodes = []
        self.route_index = 0
        self.edge_progress = 0.0
        self.busy_time_remaining_seconds = 0.0
        self.interaction_mu = hh_interaction_mean
        self.interaction_std = hh_interaction_std
        model.grid.place_agent(self, node)

        # VRP routing state
        self.assigned_lsoa = None  # LSOA this agent is assigned to for current day
        self.vrp_waypoints = []  # Ordered list of target household nodes for this agent
        self.vrp_waypoint_index = 0  # Current position in waypoints list
        self.daily_assigned_households = []  # Households allocated for today's workload
        self.assigned_day = None  # Day when this agent was last assigned (for diagnostics)

    def has_pending_assigned_household_at_node(self, node):
        """
        Return True if the node contains at least one incomplete household
        from this agent's daily assignment.
        """
        if node is None:
            return False

        return any(
            (household.node == node) and (not household.survey_completed)
            for household in self.daily_assigned_households
        )

    def has_pending_assigned_households(self):
        """
        Return True if this agent still has incomplete assigned households.
        """
        return any(
            not household.survey_completed
            for household in self.daily_assigned_households
        )

    def clear_route(self):
        """
        Clears an in-progress route and snaps the display position to the
        agent's current graph node.
        """
        self.target_node = None
        self.route_nodes = []
        self.route_index = 0
        self.edge_progress = 0.0
        self.display_position = self.node

    def has_incomplete_household_at_node(self, node):
        """
        Returns True when the agent's node still has a household that has not 
        completed the Census questionnaire.

        Parameters
        ----------
        node : tuple
            The (easting, northing) coordinates of the node to check.

        Returns
        -------
        bool
            True if there is at least one incomplete household at the node, 
            False otherwise.
        """
        return any(
            not household.survey_completed
            for household in self.model.node_to_households.get(node, [])
        )

    def has_incomplete_households(self):
        """
        Returns True if any household in the model has yet to complete their 
        Census questionnaire.

        Returns
        -------
        bool
            True if there is at least one such household in the model,
            False otherwise.
        """
        return any(not household.survey_completed for household in \
                                                        self.model.households)

    def get_next_vrp_target(self):
        """
        Advance past any completed waypoints and return the next pending
        VRP target node for this agent, or None if all waypoints are done.

        Returns
        -------
        tuple or None
            The (easting, northing) coordinates of the next VRP waypoint,
            or None if no more waypoints.
        """
        # Skip over waypoints that no longer have assigned pending households.
        while self.vrp_waypoint_index < len(self.vrp_waypoints):
            waypoint_node = self.vrp_waypoints[self.vrp_waypoint_index]
            if self.has_pending_assigned_household_at_node(waypoint_node):
                return waypoint_node
            self.vrp_waypoint_index += 1

        return None

    def choose_target_node(self):
        """
        Choose the next household node to visit. Prioritizes today's assigned
        waypoints, then falls back to nearest incomplete household from the
        agent's own daily assignment. If the assignment is complete, the agent
        stops and does not retarget other households.

        Returns
        -------
        tuple or None
            The (easting, northing) coordinates of the chosen target node, or
            None if all households have completed the Census questionnaire.
        """
        if self.has_pending_assigned_household_at_node(self.node):
            return self.node

        if self.assigned_lsoa:
            if not self.has_pending_assigned_households():
                return None

            # Priority 1: next TSP waypoint for today's assigned households.
            vrp_target = self.get_next_vrp_target()
            if vrp_target is not None:
                return vrp_target

            # Priority 2: nearest assigned incomplete household.
            assigned_incomplete = [
                household.node for household in self.daily_assigned_households
                if not household.survey_completed
            ]
            if assigned_incomplete:
                return min(
                    assigned_incomplete,
                    key=lambda node: (node[0] - self.node[0]) ** 2 +
                                     (node[1] - self.node[1]) ** 2,
                )

            return None

        # Global household finder fallback used for unassigned agents.
        return min(
            (
                household.node for household in self.model.households
                if not household.survey_completed
            ),
            key=lambda node: (node[0] - self.node[0]) ** 2 + 
                                                (node[1] - self.node[1]) ** 2,
            default=None,
        )

    def build_route(self):
        """
        Builds the shortest path from the current node to the selected target.

        Returns
        -------
        bool
            True if a route was successfully built, False if no route could be 
            found or if there is no target node.
        """
        target_node = self.choose_target_node()
        if target_node is None:
            self.clear_route()
            return False

        self.target_node = target_node
        self.route_index = 0
        self.edge_progress = 0.0

        if target_node == self.node:
            self.route_nodes = [self.node]
            self.display_position = self.node
            return True

        try:
            self.route_nodes = nx.shortest_path(
                self.model.graph,
                self.node,
                target_node,
                weight='length',
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            self.clear_route()
            return False

        self.display_position = self.node
        return True

    def interpolate_position(self, start_node, end_node, edge_length):
        """
        Returns the current display position along an edge using linear
        interpolation between the two endpoint nodes.

        Parameters
        ----------
        start_node : tuple
            The (easting, northing) coordinates of the edge's start node.
        end_node : tuple
            The (easting, northing) coordinates of the edge's end node.
        edge_length : float
            The length of the edge in metres.

        Returns
        -------
        tuple
            The (easting, northing) coordinates of the interpolated position.
        """
        if edge_length <= 0:
            return end_node

        progress_ratio = self.edge_progress / edge_length
        return (
            start_node[0] + (end_node[0] - start_node[0]) * progress_ratio,
            start_node[1] + (end_node[1] - start_node[1]) * progress_ratio,
        )

    def move(self):
        """
        Movement logic - agent traverses the road network toward the next 
        target household using a real 'distance budget' per step.

        Returns
        -------
        None
        """
        if self.edge_progress == 0 and \
                self.has_pending_assigned_household_at_node(self.node):
            self.clear_route()
            return

        if not self.has_incomplete_households():
            self.clear_route()
            return

        if self.edge_progress == 0 and not \
            self.has_pending_assigned_household_at_node(self.target_node):
            self.clear_route()

        if not self.route_nodes and not self.build_route():
            return

        if self.target_node == self.node:
            self.display_position = self.node
            return

        distance_budget = self.model.travel_distance_per_step
        while distance_budget > 0 and self.route_index < len(self.route_nodes) - 1:
            start_node = self.route_nodes[self.route_index]
            end_node = self.route_nodes[self.route_index + 1]
            edge_length = self.model.graph[start_node][end_node]['length']
            remaining_edge_distance = edge_length - self.edge_progress

            if distance_budget < remaining_edge_distance:
                self.edge_progress += distance_budget
                self.display_position = self.interpolate_position(
                    start_node,
                    end_node,
                    edge_length,
                )
                return

            distance_budget -= remaining_edge_distance
            self.edge_progress = 0.0
            self.prev_node = self.node
            self.model.grid.move_agent(self, end_node)
            self.node = end_node
            self.display_position = end_node
            self.route_index += 1

            if self.target_node == self.node:
                self.clear_route()
                return

            if not self.has_pending_assigned_household_at_node(self.target_node):
                self.clear_route()
                return

        self.display_position = self.node

    def knock(self, household):
        """
        The field worker knocks on a household's door. Records the knock against
        the household's LSOA and returns True if someone answers.

        Parameters
        ----------
        household : Household agent
            The household being knocked on.

        Returns
        -------
        bool
            True if someone answers the door, False otherwise.
        """
        self.model.lsoa_stats[household.lsoa]['knocks'] += 1
        # If not in, put in a postcard. Does this prompt a response? Does it 
        # annoy them?
        return self.random.random() < household.response_chance

    def interaction(self, household, mu, std):
        """
        The field worker interacts with a household member. Records the
        interaction against the household's LSOA.

        Parameters
        ----------
        household : Household agent
            The household being interacted with.
        mu : float
            The mean time for the interaction in seconds.
        std : float
            The standard deviation of the interaction time in seconds.

        Returns
        -------
        interaction_length : float
            The length of the interaction in seconds.
        """
        self.model.lsoa_stats[household.lsoa]['interactions'] += 1
        # Longer could mean higher P of success
        # Change this length of time to be more realistic if data exists.
        interaction_length = self.random.normalvariate(mu=mu, sigma=std)

        return interaction_length

    def visit_household(self):
        """
        Whole process of a field worker visiting a household: knocking, waiting
        for a response, then interacting if someone opens the door.
        """
        candidates = [
            household for household in self.daily_assigned_households
            if household.node == self.node and not household.survey_completed
        ]
        if not candidates:
            return
        household = self.random.choice(candidates)
        answered = self.knock(household)
        if answered:
            interaction_length = self.interaction(
                household,
                self.interaction_mu,
                self.interaction_std,
            )
            interaction_seconds = max(0.0, interaction_length)
            self.busy_time_remaining_seconds += interaction_seconds
            self.model.current_day_interaction_seconds += interaction_seconds

    def step(self):
        """
        One step for each field staff agent in the simulation. Acknowledges if 
        an interaction with a household is in progress.
        """
        if self.busy_time_remaining_seconds > 0:
            self.busy_time_remaining_seconds = max(
                0.0,
                self.busy_time_remaining_seconds - \
                    self.model.simulation_step_seconds,
            )
            return

        self.move()
        self.visit_household()
