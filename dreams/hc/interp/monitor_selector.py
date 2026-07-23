import dreams
import networkx as nx


class MonitorSelector():
    """
    Class to identify buses and themal elements for interpolation hc monitors
    """
    def __init__(
            self,
            feeder,
            bus_name=None,
            hc_type='gen',
            ):
        self.feeder = feeder
        self.model_fp = feeder.stats['path']

        # store voltages and capacities to self... voltages maybe less vital...
        self.voltages = feeder.bus_voltages.copy()
        self.capacities = None
        self.collect_capacities()

        # identify non source buses for voltage monitors.
        src_bus = feeder.voltage_sources['short_bus1'].iloc[0]
        non_src_bus_mask = feeder.buses.index != src_bus
        self.available_bus = feeder.buses[non_src_bus_mask].index.values

        self.bus_name = bus_name

        # ensure only two types
        if hc_type != 'gen':
            hc_type = 'load'
        self.hc_type = hc_type

        self.has_coords = sum(feeder.buses['distance'] > 0) > 0

        # init graph
        self.graph = dreams.Graph(self.model_fp)

        self.upstream_bus = None
        self.downstream_bus = None

        self.buses_to_monitor = None
        self.thermal_elements_to_monitor = None

        if self.bus_name is not None:
            self.update(self.bus_name)

    def collect_capacities(self):
        """
        Collect feeder capacities and store to self
        """
        self.feeder.update_capacity()
        self.capacities = self.feeder.capacity.copy()

        # for later index
        self.capacities['lower_lname'] = self.capacities['longname'].str.lower()
        self.capacities.set_index('lower_lname', inplace=True)


    def update(self, bus_name):
        """
        based on bus_name

        identify ancestors
        identify successors

        select immediate up/down thermal elements
        select 'in line' up/down critical buses

        select upstream critical thermal elements
    
        if coords:
            identify bus_distance
            identify most critical up and down voltages

            identify most critical 'closer' thermal elements
        
        ensure unique list return
        """
        self.bus_name = bus_name
        
        buses_to_monitor = []
        thermal_elements_to_monitor = []

        # ensure non-source bus only.
        upstream_bus = nx.ancestors(self.graph.G, bus_name)
        upstream_bus = list(upstream_bus.intersection(self.available_bus))
        self.upstream_bus = upstream_bus

        downstream_bus = nx.descendants(self.graph.G, bus_name)
        downstream_bus = list(downstream_bus.intersection(self.available_bus))
        self.downstream_bus = downstream_bus

        # monitor upstream critical bus, and critical thermal element
        if len(upstream_bus) > 0:
            us_bus = self._find_critical_bus(upstream_bus)
            buses_to_monitor.append(us_bus)

            # identify critical upstream  thermal elements
            upstream_te = self._find_critical_thermal_element(upstream_bus)
            thermal_elements_to_monitor.append(upstream_te)

        # identify feeding edge(s)
        us_edge = list(self.graph.G.in_edges(bus_name))
        if len(us_edge) > 0:
            # account for all upstream (in to bus) edges
            for sel_edge in us_edge:
                us_edge_attr = self.graph.G.edges[(sel_edge[0], sel_edge[1] ,0)]
                us_te = us_edge_attr['attr']['pde_name']
                thermal_elements_to_monitor.append(us_te)

        if len(downstream_bus) > 0:
            ds_bus = self._find_critical_bus(downstream_bus)
            buses_to_monitor.append(ds_bus)

        # identify leaving edge(s)
        ds_edge = list(self.graph.G.out_edges(bus_name))
        if len(ds_edge) > 0:
            # monitor all from bus thermal edges
            for sel_edge in ds_edge:
                ds_edge_attr = self.graph.G.edges[(sel_edge[0], sel_edge[1] ,0)]
                ds_te = ds_edge_attr['attr']['pde_name']
                thermal_elements_to_monitor.append(ds_te)

        if self.has_coords:
            # select most critical near and far elements
            # collect bus of interst distance
            bus_dist = self.feeder.buses.loc[bus_name]['distance']

            # select only non-source buses
            available_buses = self.feeder.buses.loc[self.available_bus]

            # identify closer buses
            closer_bus_mask = available_buses['distance'] < bus_dist
            closer_buses = available_buses[closer_bus_mask].index.values
            if len(closer_buses) > 0:
                closer_crit_v_bus = self._find_critical_bus(closer_buses)
                buses_to_monitor.append(closer_crit_v_bus)

                # identify most critical 'closer' thermal element
                closer_te = self._find_critical_thermal_element(closer_buses)
                thermal_elements_to_monitor.append(closer_te)

            # identify further buses
            further_bus_mask = available_buses['distance'] > bus_dist
            further_buses = available_buses[further_bus_mask].index.values
            if len(further_buses) > 0:
                further_critical_v_bus = self._find_critical_bus(further_buses)
                buses_to_monitor.append(further_critical_v_bus)

        # ensure unique lists
        self.buses_to_monitor = list(set(buses_to_monitor))
        self.thermal_elements_to_monitor = list(set(thermal_elements_to_monitor))

    def _find_critical_thermal_element(self, bus_list):
        """
        return critical thermal element - 
        most loaded if demand,
        least loaded if generation

        look only at upstream, or feeding elements.
        consider actual amps instead of percent usage
        """
        # only in edges of upstream bus
        edges = self.graph.G.in_edges(bus_list)

        # get all 'upstream in edges' i.e. feeding elements
        pde_names = []
        for edge in edges:
            edge_ndx = (edge[0], edge[1], 0)
            edge_dict = self.graph.G.edges[edge_ndx]
            edge_pde = edge_dict['attr']['pde_name']
            pde_names.append(edge_pde)

        # ensure names conform to index format
        pde_names =[x.lower() for x in set(pde_names)]

        valid_pde = [x for x in pde_names if x in self.capacities.index.values]
        if len(valid_pde) == 0:
            print(bus_list)
            print(f'error - no valid pde...')
            return ''
        else:
            capacities = self.capacities.loc[pde_names]

        if self.hc_type == 'gen':
            # generation will reduce current, and go negative, so least existing loaded element...
            #crit_te = capacities.sort_values('imax').index[0]  # this doesn't seem to be the correct indicator.
            # generation reverses flow of existing current, then any extra will flow to source....
            crit_te = capacities.sort_values('remaining_amps').index[0]  # surprisingly okay results?

        else:
            # load will increase current, and go beyond rating, so least remaing amps
            crit_te = capacities.sort_values('remaining_amps').index[0]  # for demand

        return crit_te

    def _find_critical_bus(self, bus_list):
        """
        return highest voltage bus if gen, else lowest
        """
        if self.hc_type == 'gen':
            closer_crit_v_bus = self.get_highest_voltage_bus(bus_list)
            return closer_crit_v_bus
        else:
            closer_crit_v_bus = self.get_lowest_voltage_bus(bus_list)
            return closer_crit_v_bus

    def get_highest_voltage_bus(self, bus_list):
        """
        based on feeder and bus list, identify highest non source, voltage
        """
        v_df = self.feeder.bus_voltages.loc[bus_list]
        v_df_sort = self.sort_max_voltage(v_df)
        # ensure non-zero
        valid_mask = v_df_sort > 0
        v_df_sort = v_df_sort[valid_mask]
        max_v_bus = v_df_sort.index[0]  # first bus
        return max_v_bus

    def get_lowest_voltage_bus(self, bus_list):
        """
        based on feeder and bus list, identify lowest, non-zero, voltage
        """
        v_df = self.feeder.bus_voltages.loc[bus_list]
        v_df_sort = self.sort_min_voltage(v_df)
        # ensure non-zero
        valid_mask = v_df_sort > 0
        v_df_sort = v_df_sort[valid_mask]
        min_v_bus = v_df_sort.index[-1]  # last bus
        return min_v_bus

    def sort_max_voltage(self, voltage_df):
        """
        collect maximum voltage from buses
        sort in descending
        """
        df = voltage_df[['v1','v2','v3']].copy()
        return df.max(axis=1).sort_values(ascending=False)

    def sort_min_voltage(self, voltage_df):
        """
        collect maximum voltage from buses
        sort in descending
        """
        df = voltage_df[['v1','v2','v3']].copy()
        return df.min(axis=1).sort_values(ascending=False)
