"""
Class to allow for easier network / graph creation
"""

import opendssdirect as dss
import os
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

class Graph():
    """
    Class to create directed graph of feeder based on incidence matrix
    """
    def __init__(
            self,
            model_fp,
            init=True):

        self.model_fp = model_fp

        if init:
            self.incidence_matrix = self.get_incidence_matrix()
            self.G = self.get_directed_graph()

    def get_incidence_matrix(self):
        """
        Clears any openDSS direct feeder,
        Solves system at located model_fp,
        and returns incidence matrix where the `value` column indicates flow
        entering bus via pde.
        """
        dss.run_command('clear')
        dss.run_command(f"""compile "{self.model_fp}" """)  # quotes intentional
        dss.run_command('solve')

        dss.run_command("calcincmatrix_o")

        paths_to_remove = []

        inc_matrix_fp = dss.run_command("export incmatrix incidence_matrix.csv")
        inc_matrix = pd.read_csv(inc_matrix_fp)
        paths_to_remove.append(inc_matrix_fp)

        row_fp = dss.run_command("export incmatrixrow incidence_matrix_row.csv")
        row_names = pd.read_csv(row_fp)
        paths_to_remove.append(row_fp)

        col_fp = dss.run_command("export incmatrixcols incidence_matrix_cols.csv")
        col_names = pd.read_csv(col_fp)
        paths_to_remove.append(col_fp)

        # remove temporary opendss exports
        for temp_path in paths_to_remove:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        inc_bus_names = col_names.iloc[inc_matrix['Col']]
        inc_matrix['bus_name'] = inc_bus_names.reset_index(drop=True)
        inc_matrix['bus_name'] = inc_matrix['bus_name'].astype(str)
        inc_pde_name = row_names.iloc[inc_matrix['Row']]
        inc_matrix['pde_name'] = inc_pde_name.reset_index(drop=True)

        # addition to help with per phase graph
        inc_matrix['bus_nodes'] = ''
        inc_matrix['n_bus_nodes'] = 0
        inc_matrix['kv_base'] = 0.0

        for idx, row in inc_matrix.iterrows():
            bus_name = row['bus_name']
            dss.Circuit.SetActiveBus(bus_name)
            inc_matrix.at[idx, 'n_bus_nodes'] = int(dss.Bus.NumNodes())
            inc_matrix.at[idx, 'bus_nodes'] = dss.Bus.Nodes()
            inc_matrix.at[idx, 'kv_base'] = float(dss.Bus.kVBase())
            inc_matrix.at[idx, 'x_coord'] = float(dss.Bus.X())
            inc_matrix.at[idx, 'y_coord'] = float(dss.Bus.Y())

        return inc_matrix

    def get_directed_graph(self):
        """
        Create networkx directed graph from incidence matrix

        ASSERT: feeder used to create incidence matrix is active in dss direct
        This will be the case if exqecuted immediately after `get_incidence_matrix`
        """
        # init graph
        graph = nx.MultiDiGraph()

        # create nodes
        bus_names = dss.Circuit.AllBusNames()
        bus_dict = {}
        for bus_name in bus_names:
            dss.Circuit.SetActiveBus(bus_name)
            bus_dict[bus_name] = {}
            bus_dict[bus_name]['kv_base'] = float(dss.Bus.kVBase())
            bus_dict[bus_name]['x_coord'] = float(dss.Bus.X())
            bus_dict[bus_name]['y_coord'] = float(dss.Bus.Y())

        # add nodes to graph
        for bus_name, bus_attributes in bus_dict.items():
            graph.add_node(bus_name, attr=bus_attributes)

        # add edges (if possible) to graph
        for pde_name, pde_df in self.incidence_matrix.groupby('pde_name'):
            n_connects = len(pde_df)

            if n_connects == 1:
                # print(f"Skipping edge {pde_name} - only one connection")
                continue

            if n_connects > 2:
                # print(f"Skipping edge {pde_name} - too many connections")
                # should probably not happen...
                continue

            sorted_pde = pde_df.sort_values('Value', ascending=False)

            bus_1 = sorted_pde.iloc[0]['bus_name']  # value of 1
            bus_2 = sorted_pde.iloc[1]['bus_name']  # value of -1

            edge_dict = {
                'kind': pde_name.split('.')[0],
                'pde_name': pde_name,
            }

            graph.add_edge(bus_1, bus_2, attr=edge_dict)

        # check for loops
        graph_copy = graph.copy()
        cycles = []

        while True:
            try:
                cycle = nx.find_cycle(graph_copy)
                cycles.append(cycle)
                # Remove the edges forming the cycle to find the next one
                graph_copy.remove_edge(*cycle[-1])
            except nx.NetworkXNoCycle:
                break
        if len(cycles) > 0:
            print(f"WARNING: directed graph has {len(cycles)} loops!")

        return graph

    def plot(self, kind='basic'):
        """
        plot function to allow for more plot type returns
        """
        if kind == 'basic':
            return self.plot_basic_graph()

    def plot_basic_graph(
            self,
            ):
        """
        return basic plot of graph using bus coordinates
        May not be super helpful, but good confirmation that graph works
        """
        fig, ax = plt.subplots()

        graph = self.G
        pos = {}
        for node in graph.nodes():
            x = graph.nodes[str(node)]['attr']['x_coord']
            y = graph.nodes[str(node)]['attr']['y_coord']
            pos[node] = (x, y)

        nx.draw(
            graph,
            pos,
            with_labels=False,
            node_color='skyblue',
            node_size=1,
            edge_color='k',
            arrows=True,
            ax=ax)

        plt.axis('off')
        plt.show()

        return fig, ax
