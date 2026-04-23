"""
Exploring Mesa package as part of ABM discovery. This is an ABM using the 
Boltzmann Wealth Model, from a tutorial on mesa.readthedocs.io. 
"""
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import mesa

class MoneyAgent(mesa.Agent):
    """
    An agent with fixed initial wealth.
    """

    def __init__(self, model):
        # Passing parameters to the parent class - ensures base agent set-up 
        # happens before we set any agent behaviour.
        super().__init__(model)

        self.wealth = 1

        
    def exchange_money(self):
        """
        Agents exchange money between each other. In this function, one agent 
        gives 1 'wealth' token to another.
        """
        if self.wealth > 0: 
            other_agent = self.random.choice(self.model.agents)
            if other_agent is not None:
                other_agent.wealth += 1
                self.wealth -= 1

    def donate_money(self, recipients):
        """
        Gives one wealth unit to a random recipient.
        """
        if self.wealth > 0 and len(recipients) > 0:
            recipient = self.random.choice(recipients)
            recipient.wealth += 1
            self.wealth -= 1



class PolicyModel(mesa.Model):
    """
    A model where rich agents donate to poorer agents, after an intial money
    has occured.
    """

    def __init__(self, n):
        
        super().__init__()

        MoneyAgent.create_agents(model=self, n=n)

    def step(self):
        """
        Advances the model by one step (a step is the smallest time period
        in the model, also called a tick).
        """
        self.agents.shuffle_do("exchange_money")

        rich_agents = self.agents.select(lambda x: x.wealth >= 5)
        poor_agents = self.agents.select(lambda x: x.wealth == 0)

        if len(rich_agents) > 0 and len(poor_agents) > 0:
            rich_agents.shuffle_do("donate_money", recipients=poor_agents)

model = PolicyModel(n=100)
model.run_for(100)

broke_agents = len(model.agents.select(lambda x: x.wealth == 0))
rich_agents = len(model.agents.select(lambda x: x.wealth >= 5))

print(f"After redistribution policy, there are {broke_agents} broke agents and "
      f"{rich_agents} rich agents.")
