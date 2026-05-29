"""
An ABM aiming to replicate the movement of field workers within Census
operations. I have chosen a neighbourhood in Coventry to represent the 
fieldwork area, for no particular reason.

Aaron Stace, 29/05/2026
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




class FieldWorker():
    """
    A field worker, who moves around a geographic area to conduct census
    operations.
    """

    def __init__(self, id, location):
        self.id = id
        self.location = location

    def step(self):
        # Placeholder for a method that updates the worker's location at each time step
        pass


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
        pass