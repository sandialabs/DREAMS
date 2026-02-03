"""
Class to allow for easier network / graph creation
"""

import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


class Graph():
    """
    Create graph of feeder.
    """
    def __init__(
            self,
            feeder):

        self.feeder = feeder
        self.G = self.create_simple_graph(feeder)
        self.is_connected = nx.is_connected(self.G)

        self.n_cycles = None
        self.cycles = None
        self.node_position = None

        self.upstream_xfmr_df = None

    def create_simple_graph(self, feeder):
        """
        Create simple graph using 'short_bus' names.
        """
        mulit_graph = nx.MultiGraph()

        # add nodes to graph (buses)
        # makes graph using only short bus... not individual phases.
        for index, row in feeder.buses.iterrows():
            node = index
            node_dict = {
                'name': index,
                'kv_base': row['kv_base'],
                'longitude': row['longitude'],
                'latitude': row['latitude'],
                }
            mulit_graph.add_node(node, attr=node_dict)

        # add edges of transformers, lines, switches, reactors. fuses?
        elements_to_add = {
            'lines': ['short_bus1', 'short_bus2'],
            'switches': ['short_bus1', 'short_bus2'],
            'reactors': ['short_bus1', 'short_bus2'],
            'transformers': ['short_bus1', 'short_bus2'],
            }

        for element, connections in elements_to_add.items():
            feeder_df = getattr(feeder, element)

            for _, row in feeder_df.iterrows():
                connection_1 = row[connections[0]]
                connection_2 = row[connections[1]]
                mulit_graph.add_edge(connection_1, connection_2, attr=row)

        return mulit_graph

    def find_all_cycles(self, update_object=True):
        """
        Identify all cycles (loops) in graph
        """
        graph_copy = self.G.copy()
        cycles = []
        while True:
            try:
                cycle = nx.find_cycle(graph_copy)
                cycles.append(cycle)
                # Remove the edges forming the cycle to find the next one
                graph_copy.remove_edge(*cycle[-1])
            except nx.NetworkXNoCycle:
                break

        if update_object:
            self.cycles = cycles
            self.n_cycles = len(cycles)

        return cycles

    def get_node_position(self, update_object=True):
        """
        Function to generate node position dictionary
        Optionally updates object node_position
        """
        pos = {}
        for node in self.G.nodes():
            x = self.G.nodes[node]['attr']['longitude']
            y = self.G.nodes[node]['attr']['latitude']
            pos[node] = (x, y)

        if update_object:
            self.node_position = pos

        return pos

    def get_upstream_xfmr_kva(
            self,
            secondary_kv_limit=1.0,
            breadth_lim=10,
            ):
        """
        Return (and save to self), upstream transformer kva for all buses
        except for bus connected to voltage source.
        Uses breadth first search to find nearest high voltage xfrm bus
        of secondary buses.
        assumes max transformer is limit for primary connected buses.
        """
        xfmr_lim_res = {}
        max_kva = self.feeder.transformers['kva'].max()
        vs_bus = self.feeder.voltage_sources['short_bus1'].values[0]

        for index, bus_row in self.feeder.buses.iterrows():
            if index == vs_bus:
                # skip voltage source bus
                continue

            n = 1
            # handle primary
            xfmr_lim_res[index] = {}
            xfmr_lim_res[index]['n_phases'] = bus_row['n_phases']
            xfmr_lim_res[index]['phases'] = bus_row['phases']
            xfmr_lim_res[index]['kv_base'] = bus_row['kv_base']

            if bus_row['primary']:
                xfmr_lim_res[index]['upstream_xfmr'] = np.nan
                xfmr_lim_res[index]['upstream_xfmr_kva'] = max_kva
                xfmr_lim_res[index]['breadth_n'] = np.nan
                continue

            for edge in nx.bfs_edges(self.G, bus_row.name, breadth_lim):
                found_edge = np.nan
                next_node = edge[1]
                next_node_kv = self.G.nodes[next_node]['attr']['kv_base']

                if next_node_kv > secondary_kv_limit:
                    found_edge = edge
                    break
                n += 1

            xfmr_mask = self.feeder.transformers['short_bus2'] == found_edge[0]

            if sum(xfmr_mask) == 0:
                print(f'WARNING: upstream sum(xfmr_mask) = 0 {found_edge}')
            upstream_xfmr = self.feeder.transformers[xfmr_mask]
            upstream_xfmr_name = upstream_xfmr.index[0]
            upstream_xfmr_kva = upstream_xfmr.normhkva.min()

            xfmr_lim_res[index]['upstream_xfmr'] = upstream_xfmr_name
            xfmr_lim_res[index]['upstream_xfmr_kva'] = upstream_xfmr_kva
            xfmr_lim_res[index]['breadth_n'] = n

        upstream_xfmr_df = pd.DataFrame.from_dict(xfmr_lim_res, orient='index')
        self.upstream_xfmr_df = upstream_xfmr_df

        return upstream_xfmr_df

    def plot(
            self,
            substation_name=None,
            show_cycles=False,
            ):
        """
        Plot graph using feeder coordinates.
        Optionally plot the substation if the node name is provded.
        Optionally plot cycles longer than 2 edges
        """

        if self.node_position is None:
            pos = self.get_node_position(self)
        else:
            pos = self.node_position

        if show_cycles:
            if self.cycles is None:
                cycles = self.find_all_cycles()
            else:
                cycles = self.cycles

        # standard draw.
        fig = plt.figure()
        ax = fig.add_subplot(111)

        if show_cycles:
            longer_cycles = [x for x in cycles if len(x) > 2]
            for n in longer_cycles:
                nx.draw_networkx_edges(
                    self.G,
                    pos,
                    ax=ax,
                    edgelist=n,
                    width=4,
                    alpha=1,
                    edge_color="tab:red",
                )

        nx.draw(self.G, pos, node_size=0, ax=ax)

        if substation_name is not None:
            if substation_name in self.G.nodes:
                # substation plot
                nx.draw_networkx_nodes(
                    self.G,
                    pos,
                    ax=ax,
                    nodelist=[substation_name],
                    node_size=30,
                    alpha=1,
                    node_color='green',
                    edgecolors="black",
                )
            else:
                print(f"'{substation_name}' not found in graph nodes")

        return (fig, ax)
