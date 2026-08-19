"""
An ABM modelling the movement of field workers around a local authority, 
visiting households.

Aaron Stace, 08/06/2026
"""
import mesa
from config import (
    INTERACTION_COMPLETION_CHANCE,
    KNOCK_COMPLETION_CHANCE,
    KNOCK_RESPONSE_CHANCE,
    hh_interaction_mean,
    hh_interaction_std,
)


class Household(mesa.Agent):
    """
    Household agents, located in the model at the nearest road/path node to 
    their actual geographical location.
    """
    # Start with one type of household. Maybe have another household class that 
    # inherits later on?
    def __init__(self, model, node, lsoa, 
                 knock_response_chance=KNOCK_RESPONSE_CHANCE,
                 initial_completion_rate=0.0, ongoing_completion_rate=0.0,
                 survey_completed=False):

        super().__init__(model)

        self.node = node
        self.lsoa = lsoa
        model.grid.place_agent(self, node)

        self.knock_response_chance = knock_response_chance
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
        self.households_knocked = set()  # Assigned households already knocked today
        self.pending_assigned_households = set()  # Assigned households not yet knocked (O(1) lookup)
        self.node_to_pending_assigned = {}  # node -> set[Household] for pending households
        self.assigned_day = None  # Day when this agent was last assigned (for diagnostics)
        self.absent_today = False  # True if this agent is absent from work today
        self.use_nn_routing = False  # True if this agent ignores the planned route and uses nearest-neighbour routing

    def has_pending_assigned_household_at_node(self, node):
        """
        Return True if the node contains at least one assigned household that
        has not yet been knocked by this agent.
        """
        if node is None:
            return False

        return bool(self.node_to_pending_assigned.get(node))

    def has_pending_assigned_households(self):
        """
        Return True if this agent still has assigned households to knock on.
        """
        return bool(self.pending_assigned_households)

    def has_knocked_all_assigned_households(self):
        """
        Return True if this agent has knocked all households on today's list.
        """
        if not self.daily_assigned_households:
            return False

        return not self.has_pending_assigned_households()

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

    def reset_daily_state(self):
        """
        Clear all per-day routing and assignment state. Called when an agent
        has no target LSOA or could not be placed in one.
        """
        self.assigned_lsoa = None
        self.clear_route()
        self.vrp_waypoint_index = 0
        self.daily_assigned_households = []
        self.households_knocked = set()
        self.pending_assigned_households = set()
        self.node_to_pending_assigned = {}
        self.vrp_waypoints = []

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
            if self.pending_assigned_households:
                return min(
                    (hh.node for hh in self.pending_assigned_households),
                    key=lambda node: (node[0] - self.node[0]) ** 2 +
                                     (node[1] - self.node[1]) ** 2,
                )

            return None

        raise RuntimeError(
            f"FieldWorker {self.unique_id} has no assigned LSOA in \
                choose_target_node(). "
            "Ensure assign_agents_to_target_lsoas() is called before agents \
                step."
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

        self.route_nodes = self.model.get_road_path(self.node, target_node)
        if not self.route_nodes:
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

        if not self.has_pending_assigned_households():
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
        self.households_knocked.add(household)
        self.pending_assigned_households.discard(household)
        self.node_to_pending_assigned.get(household.node, set()).discard(household)
        # If not in, put in a postcard. Does this prompt a response? Does it 
        # annoy them?
        return self.random.random() < household.knock_response_chance

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
        candidates = list(self.node_to_pending_assigned.get(self.node, set()))
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
            if self.random.random() < INTERACTION_COMPLETION_CHANCE:
                self.model.register_completion(
                    household,
                    characteristic='fieldwork',
                    step_number=self.model.steps,
                )
        elif self.random.random() < KNOCK_COMPLETION_CHANCE:
            self.model.register_completion(
                household,
                characteristic='fieldwork',
                step_number=self.model.steps,
            )

    def step(self):
        """
        One step for each field staff agent in the simulation. Acknowledges if 
        an interaction with a household is in progress.
        """
        if self.absent_today:
            return

        if self.busy_time_remaining_seconds > 0:
            self.busy_time_remaining_seconds = max(
                0.0,
                self.busy_time_remaining_seconds - \
                    self.model.simulation_step_seconds,
            )
            return

        self.move()
        self.visit_household()
