"""
This agent-based model attempts to represent the spread of sentiment towards a 
census in a student hall of residence, with varying numbers of student 
ambassadors that have a positive influence on sentiment.
"""
import mesa
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


class Student(mesa.Agent):
    """
    A student, living in a university hall of residence, with an initial 
    sentiment towards the census between 0 and 1. The student can be influenced 
    by other students, and by student ambassadors, to change their sentiment.
    """
    def __init__(self, model):
        super().__init__(model)

        self.sentiment = self.random.uniform(0, 1)

    def interaction(self):
        """
        Student interacts with a random other student, and their sentiment 
        becomes the average sentiment of the two students. If the other student 
        is an ambassador, the sentiment is increased by a fixed amount.
        """
        other_student = self.random.choice(self.model.students)
        if isinstance(other_student, Ambassador):
            self.sentiment += 0.1
        else:
            self.sentiment = (self.sentiment + other_student.sentiment) / 2



class Ambassador(mesa.Agent):
    """
    A student ambassador in a university hall of residence, with a 
    positive sentiment towards the census. The ambassador can influence other 
    students to increase their sentiment.
    """
    def __init__(self, model):
        super().__init__(model)

        self.sentiment = 0.9


class HallOfResidence(mesa.Model):
    """
    A university hall of residence, with a certain number of students and 
    ambassadors.
    """
    def __init__(self, n_students=100, n_ambassadors=1):
        super().__init__()

        self.students = Student.create_agents(model=self, n=n_students)
        self.ambassadors = Ambassador.create_agents(model=self, 
                                                    n=n_ambassadors)

    def step(self):
        for student in self.students:
            self.students.shuffle_do("interaction")


model = HallOfResidence(n_students=100, n_ambassadors=1)
model.run_until(100)

print('Model has finished running.')
print(f'Average sentiment amongst students: {np.mean([student.sentiment for 
                                                student in model.students])}')