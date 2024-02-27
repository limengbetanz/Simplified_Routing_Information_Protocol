"""
Description:
This programme is used to genetate a LP file with given paramenters.

"""

class Generator:
    """
    This class is to implement a generator which uses the given numbers of source nodes,
    transit nodes and destination nodes
    """
    def __init__(self, sources, transits, destinations, file_name):
        """
        Initialise a rip generator
        """
        self.sources = sources
        self.transits = transits
        self.destinations = destinations
        self.file_name = file_name
        self.file_string = ""


    def generate_objective_func(self):
        """
        Generate the objective function
        """
        self.file_string += "Minimize\n"
        self.file_string += "r\n\n"


    def generate_subject_to_constraints(self):
        """
        Generate subject-to constraints which include demand constraints, capacity constraints.
        """ 
        self.file_string += "Subject to\n"

        # Fill in demand constraints
        for i in range(1, self.sources + 1):
            for j in range(1, self.destinations + 1):
                equation = ""
                for k in range(1, self.transits + 1):
                    equation += "x{0}{1}{2}".format(i, k, j)
                    if k != self.transits:
                        equation += " + "
                    else:
                        equation += " = {}\n".format(i + j)
                        self.file_string += equation

        # Fill in capacity constraints (source -> transit)
        self.file_string += "\n"
        
        for i in range(1, self.sources + 1):
            for k in range(1, self.transits + 1):
                equation = ""
                for j in range(1, self.destinations + 1):
                    equation += "x{0}{1}{2}".format(i, k, j)
                    if j != self.destinations:
                        equation += " + "
                    else:
                        equation += " - c{}{} <= 0\n".format(i, k)
                        self.file_string += equation

        # Fill in capacity constraints (transit -> destination)
        self.file_string += "\n"

        for j in range(1, self.destinations + 1):
            for k in range(1, self.transits + 1):
                equation = ""
                for i in range(1, self.sources + 1):
                    equation += "x{0}{1}{2}".format(i, k, j)
                    if i != self.sources:
                        equation += " + "
                    else:
                        equation += " - d{}{} <= 0\n".format(k, j)
                        self.file_string += equation

        # Fill in split paths constraints
        self.file_string += "\n"
        
        for i in range(1, self.sources + 1):
            for j in range(1, self.destinations + 1):
                equation = ""
                for k in range(1, self.transits + 1):
                    equation += "u{0}{1}{2}".format(i, k, j)
                    if k != self.transits:
                        equation += " + "
                    else:
                        equation += " = 2\n"
                        self.file_string += equation

        # Equal split flow constraints
        self.file_string += "\n"

        for i in range(1, self.sources + 1):
            for j in range(1, self.destinations + 1):
                for k in range(1, self.transits + 1):
                    equation = ""
                    equation += "x{0}{1}{2} - {3} u{4}{5}{6} = 0\n".format(i, k, j, 0.5 * (i + j), i, k, j)
                    self.file_string += equation


        # Transits balance load constraints
        self.file_string += "\n"

        for k in range(1, self.transits + 1):
            equation = ""
            for i in range(1, self.sources + 1):
                for j in range(1, self.destinations + 1):
                    equation += "x{0}{1}{2}".format(i, k, j)
                    if not (i == self.sources and j == self.destinations):
                        equation += " + "
            
            equation += " - r <= 0\n"
            self.file_string += equation


    def generate_bounds(self):
        """
        Generate all bounds
        """
        self.file_string += "\n"
        self.file_string += "Bounds"
        self.file_string += "\n"

        # xikj > = 0
        for i in range(1, self.sources + 1):
            for k in range(1, self.transits + 1):
                for j in range(1, self.destinations + 1):
                    equation = ""
                    equation += "x{0}{1}{2} >= 0\n".format(i, k, j)
                    self.file_string += equation

        # r >= 0
        self.file_string += "r >= 0\n"

    
    def generate_binary_bounds(self):
        """
        Generete all integer bounds
        """
        self.file_string += "\n"
        self.file_string += "Binary"
        self.file_string += "\n"

        for i in range(1, self.sources + 1):
            for k in range(1, self.transits + 1):
                for j in range(1, self.destinations + 1):
                    equation = ""
                    equation += "u{0}{1}{2}\n".format(i, k, j)
                    self.file_string += equation

        self.file_string += "\n"
        self.file_string += "End"


    def generate(self):
        """
        Generate a lp file accroding to the numbers of of source nodes,
        transit nodes and destination nodes
        """
        self.generate_objective_func()
        self.generate_subject_to_constraints()
        self.generate_bounds()
        self.generate_binary_bounds()

        file_object = open(self.file_name, "w")
        file_object.write(self.file_string)
        file_object.close()

        print("{} has been created!".format(self.file_name))


def main():
    """
    Create a lp file generator and run it
    """

    source_count = input("How many source nodes do you need?: ")
    transit_count = input("How many transit nodes do you need?: ")
    destiantion_count = input("How many destination nodes do you need?: ")

    lp_generator = Generator(int(source_count), int(transit_count), int(destiantion_count), "lp.lp")
    lp_generator.generate()


if __name__ == "__main__":
    main()