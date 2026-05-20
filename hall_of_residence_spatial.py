"""
This agent-based model attempts to represent the spread of sentiment towards a 
census in a student hall of residence, with varying numbers of student 
ambassadors that have a positive influence on sentiment.
"""
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

import mesa 
from mesa.discrete_space import CellAgent, OrthogonalMooreGrid
from mesa.visualization import SolaraViz, SpaceRenderer, make_plot_component
from mesa.visualization.components import AgentPortrayalStyle



class Student(CellAgent):
    """
    A student, living in a university hall of residence, with an initial 
    sentiment towards the census between 0 and 1. The student can be influenced 
    by other students, and by student ambassadors, to change their sentiment.
    """
    def __init__(self, model, cell):
        super().__init__(model)

        self.cell = cell
        self.sentiment = self.random.uniform(0, 1)

    def move(self):
        """
        Student moves to a random neighbouring cell.
        """
        self.cell = self.cell.neighborhood.select_random_cell()


    def interaction(self):
        """
        Student interacts with a random other student, and their sentiment 
        becomes the average sentiment of the two students. If the other student 
        is an ambassador, the sentiment is increased by a fixed amount.

        Sentiment only transferred to another student/ambassador in the same
        cell.
        """
        other_person = [a for a in self.cell.agents if a is not self]

        if other_person:
            person = self.random.choice(other_person)
            if isinstance(person, Ambassador):
                self.sentiment = min(1, self.sentiment + 0.25)
            else:
                self.sentiment = (self.sentiment + person.sentiment) / 2

    
    def step(self):
        self.move()
        self.interaction()


class Ambassador(CellAgent):
    """
    A student ambassador in a university hall of residence, with a 
    positive sentiment towards the census. The ambassador can influence other 
    students to increase their sentiment.
    """
    def __init__(self, model, cell):
        super().__init__(model)

        self.cell = cell
        self.sentiment = 0.9

    def move(self):
        """
        Ambassador moves to a random neighbouring cell.
        """
        self.cell = self.cell.neighborhood.select_random_cell()

    def step(self):
        self.move()



class HallOfResidence(mesa.Model):
    """
    A university hall of residence, with a certain number of students and 
    ambassadors.
    """
    def __init__(self, n_stu, n_amb, width, height, seed=None):
        """
        Initialises the spatial hall of residence model.

        Args:
            n_stu: Number of students in the hall of residence.
            n_amb: Number of ambassadors in the hall of residence.
            width: Width of the grid representing the hall of residence.
            height: Height of the grid representing the hall of residence.
            seed: Random seed for reproducibility.
        """
        
        super().__init__(seed=seed)

        self.grid = OrthogonalMooreGrid((width, height), random=self.random)
        self.num_students = n_stu
        self.num_ambassadors = n_amb

        self.students = Student.create_agents(model=self, n=self.num_students, 
                    cell=self.random.choices(self.grid.all_cells.cells, 
                    k=self.num_students))
        self.ambassadors = Ambassador.create_agents(model=self, 
                    n=self.num_ambassadors, 
                    cell=self.random.choices(self.grid.all_cells.cells, 
                    k=self.num_ambassadors))

        self.data_collector = mesa.DataCollector(
                                    agent_reporters={'sentiment': 'sentiment'})
        self.data_collector.collect(self)

    def step(self):
        self.students.shuffle_do('step')
        self.ambassadors.shuffle_do('step')


for _ in range(2):

    model1 = HallOfResidence(n_stu=200, n_amb=1, width=10, height=10, seed=None)
    model1.run_until(60)
    model2 = HallOfResidence(n_stu=200, n_amb=2, width=10, height=10, seed=None)
    model2.run_until(60)
    model3 = HallOfResidence(n_stu=200, n_amb=3, width=10, height=10, seed=None)
    model3.run_until(60)

data1 = model1.data_collector.get_agent_vars_dataframe()
data2 = model2.data_collector.get_agent_vars_dataframe()
data3 = model3.data_collector.get_agent_vars_dataframe()

g1 = sns.histplot(data1['sentiment'], binwidth=0.1, binrange=(0, 1))
g1.set(title='Sentiment distribution', xlabel='Sentiment', 
       ylabel='No. of students')
plt.show()
g2 = sns.histplot(data2['sentiment'], binwidth=0.1, binrange=(0, 1))
g2.set(title='Sentiment distribution', xlabel='Sentiment',  
       ylabel='No. of students')
plt.show()
g3 = sns.histplot(data3['sentiment'], binwidth=0.1, binrange=(0, 1))
g3.set(title='Sentiment distribution', xlabel='Sentiment',
         ylabel='No. of students')
plt.show()

print('Model variants have finished running.')
