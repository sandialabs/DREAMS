"""
Class to handle various redirects
"""
import os
import dreams


class Redirect():
    """
    read, write, execute, and print openDSS redirects.
    lines assumed to be a list of dss executable commandss.
    file_location is the path to the file containing dss commands.
    """

    def __init__(
            self,
            name=None,
            file_location=None,
            lines=None,
            read_file=False):

        if name is None:
            self.name = 'redirect'
        else:
            self.name = name

        self.file_location = file_location

        self.lines = lines
        if read_file:
            self.read()

        self.cmd_result = []

    def __repr__(self) -> str:
        repr_str = [
            f"Redirect Name: '{self.name}'\n"
            f"Attribtutes: .file_location .lines .cmd_result\n"
            f"Methods: .read .write .execute .print .print_cmd_result\n"
        ]
        return "".join(repr_str)

    def read(self):
        """
        Read file at file location into lines attribute
        """
        self.lines = []
        # inusre about defining an encoding here...
        with open(self.file_location, 'r') as file:
            for line in file:
                self.lines.append(line.rstrip())

    def write(self, output_location=None):
        """
        If location is path, use name for file name.
        otherwise, overwrite file given in output_location.
        returns location of written file
        """
        if output_location is None:
            output_location = self.file_location

        if not os.path.isfile(output_location):
            output_location = os.path.join(output_location, f'{self.name}.dss')

        with open(output_location, 'w', encoding="utf-8") as file:
            file.writelines(line + '\n' for line in self.lines)

        return output_location

    def print(self, limit=None):
        """
        Print contents of redirect lines to screen.
        Limit defines how many from head or tail (if < 0) of lines to print
        """
        lines_to_print = self.lines

        if isinstance(limit, int):
            if limit > 0:
                lines_to_print = self.lines[0:limit]
            else:
                lines_to_print = self.lines[limit:]

        for line in lines_to_print:
            print(line)

    def print_cmd_result(self, limit=None):
        """
        Prints the contents of the command results to the terminal
        Limit defines how many from head or tail (if < 0) of lines to print
        """
        lines_to_print = self.cmd_result

        if isinstance(limit, int):
            if limit > 0:
                lines_to_print = self.cmd_result[0:limit]
            else:
                lines_to_print = self.cmd_result[limit:]

        for line in lines_to_print:
            print(line)

    def execute(self, record_line_numbers=True):
        """
        execute the contents of redirect in DSS.
        Record command result and, optionally, the associated line number.
        """
        # clear any previous results
        self.cmd_result = []

        line_number = 1

        for line in self.lines:
            cmd_result = dreams.dss.cmd(line)
            if record_line_numbers:
                str_line_number = f"{str(line_number).zfill(4)}"
                self.cmd_result.append(
                    f"{str_line_number} | {line} -> {cmd_result}")
                line_number += 1
            else:
                self.cmd_result.append(f"{line} -> {cmd_result}")
