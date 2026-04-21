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

    def __init__(self, model, ethnicity):
        # Passing parameters to the parent class - ensures base agent set-up 
        # happens before we set any agent behaviour.
        super().__init__(model)

        self.wealth = 1
        self.ethnicity = ethnicity

        
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


class MoneyModel(mesa.Model):
    """
    A model with some number of agents. Creates a subclass of the model class
    from mesa. 
    """

    def __init__(self, n, seed=None):
        
        super().__init__(seed=seed)
        ethnicities = ["Green", "Blue", "Mixed"]
        self.num_agents = n

        MoneyAgent.create_agents(model=self, n=n,
                                 ethnicity = self.random.choices(ethnicities, 
                                                                 k=n))

    def step(self):
        """
        Advances the model by one step (a step is the smallest time period
        in the model, also called a tick)
        """
        self.agents.shuffle_do("exchange_money")

model = MoneyModel(n=100)
model.run_for(30)

# Obtaining qualities of first five agents.
for agent in model.agents.select(at_most=5):
    print(f"  Agent {agent.unique_id}: wealth={agent.wealth}, "
          f"ethnicity={agent.ethnicity}")


# Getting all wealth values
all_wealth = model.agents.get('wealth')
print(f"First five wealth values: {all_wealth[:5]}")
print(f"Total wealth in economy: {sum(all_wealth)}")

wealth_and_ethnicity = model.agents.get(["wealth", "ethnicity"])
print("First five agents (wealth, ethnicity):")
for values in wealth_and_ethnicity [:5]:
    print(f"  {values}")
