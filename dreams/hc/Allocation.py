"""
Allocation class
"""
from dataclasses import dataclass
import numpy as np
import sys


class Allocation():
    """
    Class to define an allocation used in a hosting capacity scenario.
    Through variaous rules, buses are chosen for adding a specified
    elements that are also specified.

    Used by Scenario class to claculate and create line string for redirect.


    For defining:

    Location rules ~ bus masks based on feeder qualities / theshholds

    size rues
        * total amount to add over all course of steps
        * amount for each step (will be a list same number of steps as sim)
        * number of elements - total or per step step

    element kind
    elemnent descriptions used to generate simulation element string

    general options:
        * avoid/allow multi per location
            eg many per location (avoid if possible), ignore -
            will affect how random list is created
            if not enough, stop? max limit per bus? capacity limitation?
        * shared phase, single phase

    """

    def __init__(
            self,
            feeder,
            name,
            duplication=True,
            shared_phase=False,
            linear=True,  # for future possibilites of non linear?
            parent_association=None,
            ):

        self.name = name
        self.feeder = feeder

        self.duplication = duplication
        self.shared_phase = shared_phase

        self.parent_association = parent_association  # for pv with storage..?

        viable_rules = [
            'element',  # has to do with line writing
            'location',  # identify bus for line
            'capacity',  # size of element based on upstream capacity
            'size',  # size of element related to another element
            'control',  # line writing - QSTS
            'shape',  # line writing = QSTS
        ]
        self.rules = {rule: {} for rule in viable_rules}

        self.viable_buses = []
        self.viable_bus_size_limits = {}  # dictionary - with size limits?

    def __repr__(self) -> str:
        repr_str = [
            f"Allocation '{self.name}'\n"
            f"Useful attribtutes: .rules .viable_buses\n"
        ]
        return "".join(repr_str)

    @property
    def n_elements(self):
        """  Simple return of number of elements in allocation class """
        return len(self.rules['elements'].keys())

    def add_allocation_element(
            self,
            allocation_element
            ):
        """
        define type of element to add for allocation.
        If previously existing element exists for this allocation of the same
        name, it will be overwritten.

        """
        logic_checks = []
        # is pv
        logic_checks.append(
            isinstance(allocation_element, PhotovoltaicAllocationElement)
        )
        # is load
        logic_checks.append(
            isinstance(allocation_element, LoadAllocationElement)
        )
        # is storage
        logic_checks.append(
            isinstance(allocation_element, StorageAllocationElement)
        )
        logic_checks.append(
            isinstance(allocation_element, WindAllocationElement)
        )

        if any(logic_checks):
            name = allocation_element.name
            self.rules['element'][name] = allocation_element
        else:
            print(f"Element type of {type(allocation_element)} invalid")

    def add_location_rule(
            self,
            name,
            feeder_element_class,
            element_attribute,
            comparison_operation,
            comparison_value,
            bus1_attribute='bus1'
            ):
        """
        Information to select locations for elements to be allocated to.
        NOTE: uses feeder attached to self - SO, may not be always in sync
        with dss

        name used to identify location rule.
        Inputs used to create mask of buses to later use for alloction.
        eg

        feeder_element_class.element_attribute
        load.kv
        comparison_operation
        >=
        comparison_value
        .2

        results in mask of buses where load.kv >= .2

        feeder_element_class - used in mask creation, identifies feeder
        element class to compare.
        element_attribute - used in conjuction with feeder_element_class to
        collect feeder attribute to compare to.

        identify viable buses that meet given rules.

        eg
        # for home ev charging
        loads.kv > .2
        loads.primary = False

        # for pv
        # ideally this would apply to upstream transformers,
        but as is would return lowside of xfmr

        transformer.kva <= 25
        buses.primary = False

        transformer.kva > 25  # commercial

        # for storage...
        transformer.kva <= 25
        buses.primary == False
        pvsystem == True
        """
        # check if feeder element class in feeder attribues
        if feeder_element_class not in dir(self.feeder):
            print('Attribute Does not exist')
            return AttributeError

        attr_df = getattr(self.feeder, feeder_element_class)

        # check if element attribute in feeder dataframe
        if element_attribute not in attr_df.columns:
            # see if attribute is actually the index..
            if element_attribute != attr_df.index.name:
                print('Attribute is not index')
                return KeyError
            else:
                attr_df = attr_df.copy()  # to prevent changing of original
                attr_df = attr_df.reset_index()

        # check if bus1 is defined
        if bus1_attribute not in attr_df.columns:
            if bus1_attribute != attr_df.index.name:
                print('Bus1 Does not exist')
                return KeyError
            else:
                bus1_attribute = 'bus1'
                attr_df = attr_df.copy()  # to prevent changing of original
                attr_df[bus1_attribute] = attr_df.index

        # collect attribute of interest
        feeder_attr = attr_df[element_attribute]

        # run generic comparison for location masking
        mask_result = generic_comparison(
            feeder_attr,
            comparison_operation,
            comparison_value
        )

        # collect and store location result
        if sum(mask_result) > 0:
            bus1_data = getattr(attr_df[mask_result], bus1_attribute)
            resulting_locations = set(bus1_data)
            # create dataclass
            resulting_rule = LocationRule(
                name,
                feeder_element_class,
                element_attribute,
                comparison_operation,
                comparison_value,
                resulting_locations
            )
            # store in object
            self.rules['location'][name] = resulting_rule
        else:
            print('No Elements match Location Rule.')

    def add_capcity_rule(self):
        """
        deal with not overloading elements base on capacity
        using upstream distance?  collect maximum amount
        """

    def add_size_rule(self):
        """
        related to proportional size of element in relation to another
        """

    def add_control_rule(self, name):
        """"
        define controls to be added to each allocated element
        eg volt/var, storage control rules
        """
        if isinstance(self.rules['control'], dict):
            self.rules['control'] = []
        self.rules['control'].append(name)

    def add_shape_rule(self, kind, name):
        """
        define profile to be attached to allocated elements
        eg demand, irradiance...

        name is the name of a loaded profile
        # TODO maybe handle passing in a profile object...

        kind is one of: yearly, daily, or duty

        Only one shape per allocation seems to make sense
        """
        valid_kinds = ['yearly', 'daily', 'duty']
        if kind not in valid_kinds:
            print('Not valid kind of shape')

        self.rules['shape'] = {'kind': kind, 'name': name}

    def update_viable_buses(self):
        """
        update viable buses for allocation

        if size or capacity rules are defined,
        create dictionary of buses and capacity

        if no buses are found, notify/error?
        """
        # find intersection of all location rules
        locations = []
        for value in self.rules['location'].values():
            locations.append(value.resulting_locations)

        # NOTE: this intersection should only be done on fully defined buses
        # THEN, the short bus should be matched...
        # a better way to include distance rules should be figured out.
        self.viable_buses = list(set.intersection(*locations))

        if len(self.viable_buses) == 0:
            print('Allocation Warning: No Viable buses found '
                  '- ignoring phase definitions...')
            # NOTE generally, this will happen if bus_df is used.
            # this is because there are no long buses in the bus df
            valid_short_buses = []
            long_buses_on_short_bus = {}
            locations = []

            for value in self.rules['location'].values():
                for bus in value.resulting_locations:
                    if '.' in bus:
                        short_bus = bus.split('.')[0]
                        if short_bus not in long_buses_on_short_bus:
                            long_buses_on_short_bus[short_bus] = []
                        long_buses_on_short_bus[short_bus].append(bus)
                    else:
                        valid_short_buses.append(bus)

            for short_bus in valid_short_buses:
                if short_bus in long_buses_on_short_bus:
                    for long_bus in long_buses_on_short_bus[short_bus]:
                        locations.append(long_bus)

            self.viable_buses = list(set(locations))
            if len(self.viable_buses) == 0:
                print('Allocation Error: No viable buses.')
                sys.exit()
            print(f'Found {len(self.viable_buses)} resulting locations.')

        # TODO: if size rules exist, update information
        # for now just use blank
        # may really have more to do with capacity...?
        self.viable_bus_size_limits = {x: 0 for x in self.viable_buses}


class LoadAllocationElement():
    """
    Class to handle definition and tracking of Load elements.

    Calculate kw and kvar according to kind of allocation:
        every_step = apply same amount every step
        each_step = total values to be a list of values to be added each step
        total = total amount spread accross each step equally

    Current Valid Definitions:
    Element size and n_elements, kind = every_step
    * A defined number of sized elements will be added each step
    """

    def __init__(
            self,
            name,
            element_prepend='ADDED_LOAD_',
            element_kw=0,
            element_kvar=0,
            total_kw=0,
            total_kvar=0,
            n_elements=0,
            kind='every_step'
            ):
        """
        Based on given definitions, calculate required values for scenario
        """
        self.name = name
        self.element_prepend = element_prepend
        self.element_kw = element_kw
        self.element_kvar = element_kvar
        self.total_kw = total_kw
        self.total_kvar = total_kvar
        self.n_elements = n_elements

        valid_kinds = [
            'every_step',
            'each_step',
            'total'
        ]
        if kind not in valid_kinds:
            print('Ill defined element - kind not vaild')
        else:
            self.kind = kind

        # for scenario placeholders
        # populated via calculate_lines_per_step method
        self._kw_per_line = 0
        self._kvar_per_line = 0
        self._lines_per_step = 0

        # for tracking
        self.total_allocated_elements = 0
        self.total_allocated_kw = 0
        self.total_allocated_kvar = 0

        # based on inputs, set case type.
        self.element_defined = (element_kw != 0) or (element_kvar != 0)
        self.steps_defined = isinstance(total_kw, list) or \
            isinstance(total_kvar, list)

        # in case of totals being a list, simple logic throws error
        try:
            self.total_defined = (total_kw != 0) or (total_kvar != 0)
        except TypeError:
            self.total_defined = 0

        self.number_defined = n_elements > 0

        self.allocation_case = None

        if self.element_defined and self.number_defined:
            # kw known, number per step known
            self.allocation_case = 1

        elif self.element_defined and self.steps_defined:
            # kw known, total for each step known
            self.allocation_case = 2

        elif self.element_defined and self.total_defined:
            # kw known, total defined as single value
            self.allocation_case = 3

        if self.allocation_case is None:
            print('Ill defined element - definition matches no valid cases')

    def __repr__(self) -> str:
        info_str = (f"Load Element Name: {self.name} // " +
                    f"{self.total_allocated_elements} elements allocated //" +
                    f" Total: {self.total_allocated_kw} kw " +
                    f"{self.total_allocated_kvar} kvar"
                    )
        return info_str

    def reset_allocation_tracking(self):
        """
        Reset tracking of allocation
        """
        self.total_allocated_elements = 0
        self.total_allocated_kw = 0
        self.total_allocated_kvar = 0

    def update_allocation_tracking(self, current_step):
        """
        Method to track element allocation
        """
        lines_written = sum(self._lines_per_step[0:(current_step+1)])
        self.total_allocated_elements = lines_written
        self.total_allocated_kw = self._kw_per_line * lines_written
        self.total_allocated_kvar = self._kvar_per_line * lines_written

    def get_lines_per_step(self, total_steps):
        """
        TODO Handle 'total' situaion
        Based on kind of allocation, object definition parameters,
        and number of total scenario number of steps,
        calculate and update object private variables.
        i.e. _kw_per_line, _kvar_per_line, _lines_per_step
        _lines_per_step is a list of additional lines to write each step.
        e.g. if 7 elements are to be allocated per step for 4 steps:
        _lines_per_step == [7, 7, 7, 7]

        This approach is to allow for non-linear allocations per step that may
        reflect situations better - e.g. [3, 4, 10, 11]
        """

        if self.kind == 'every_step':
            # handle lines when every line is the same
            if self.allocation_case == 1:
                self._kw_per_line = self.element_kw
                self._kvar_per_line = self.element_kvar

                self._lines_per_step = [self.n_elements] * total_steps
                return self._lines_per_step

        elif self.kind == 'each_step':
            # handle definition of sizes for each step
            # expects input of total kw on system during for each step
            if self.allocation_case == 2:
                # element size and list of sizes to add each step is known
                self._kw_per_line = self.element_kw
                self._kvar_per_line = self.element_kvar
                # TODO check lenght of list is same as n_Steps
                # ASSERT kw dictates element n
                # could write logic to find which is larger, or which value
                # ends up allocating more - BUT for now - happy path only
                # calculate elements per total
                # ceil to elimante possible under allocation
                n_total_allocations = np.ceil(
                    np.array(self.total_kw) / self.element_kw
                    )
                next_step = n_total_allocations[1:]
                previous_step = n_total_allocations[0:-1]
                lines_per_step = list(next_step - previous_step)
                lines_per_step.insert(0, n_total_allocations[0])

                self._lines_per_step = lines_per_step

                return self._lines_per_step

        elif self.kind == 'total':
            # handle case were total amount is given.
            if self.allocation_case == 3:
                # element size and list of sizes to add each step is known
                self._kw_per_line = self.element_kw
                self._kvar_per_line = self.element_kvar

                # ASSERT kw dictates total amount
                # calculate total number of allocations required
                n_total_allocations = np.ceil(self.total_kw / self.element_kw)
                # translate to allocaitons per step
                allocations_per_step = np.ceil(n_total_allocations/total_steps)
                # create list of lines per step
                lines_per_step = [allocations_per_step] * total_steps

                # insert zero for first step
                lines_per_step.insert(0, 0)
                self._lines_per_step = lines_per_step

                return self._lines_per_step

        else:
            # case not handled
            print(f"Error - allocation kind '{self.kind}' not valid.")
            return 0

    def get_kw_per_line(self):
        """
        Return current kw per line
        """
        return self._kw_per_line

    def get_kvar_per_line(self):
        """
        Return current kvar per line
        """
        return self._kvar_per_line


class PhotovoltaicAllocationElement():
    """
    Class to handle definition and tracking of allocated PV elements
    """

    def __init__(
            self,
            name,
            element_prepend='ADDED_PV_',
            element_kva=0,
            element_kvar=0,
            total_kva=0,
            total_kvar=0,
            n_elements=0,
            irradiance=1.0,
            element_kv=None,  # to be used later for voltage things
            element_pf=None,  # power factor...
            kind='every_step',
            match_bus_phase=False  # for multiphase systems...
            ):
        """
        Based on given definitions, calculate required values for scenario
        """
        self.name = name
        self.element_prepend = element_prepend
        self.element_kva = element_kva
        self.element_kvar = element_kvar
        self.total_kva = total_kva
        self.total_kvar = total_kvar
        self.n_elements = n_elements

        self.element_kv = element_kv
        self.irradiance = irradiance
        self.element_pf = element_pf

        self.match_bus_phase = match_bus_phase

        valid_kinds = [
            'every_step',
            'each_step',
            'total'
        ]
        if kind not in valid_kinds:
            print('Ill defined element - kind not vaild')
        else:
            self.kind = kind

        # for scenario placeholders
        # populated via calculate_lines_per_step method
        self._kva_per_line = 0
        self._kvar_per_line = 0
        self._lines_per_step = 0

        # for tracking
        self.total_allocated_elements = 0
        self.total_allocated_kva = 0
        self.total_allocated_kvar = 0

        # based on inputs, set case type.
        self.element_defined = (element_kva != 0) or (element_kvar != 0)
        self.steps_defined = isinstance(total_kva, list) or \
            isinstance(total_kvar, list)
        # in case of totals being a list, simple logic throws error
        try:
            self.total_defined = (total_kva != 0) or (total_kvar != 0)
        except TypeError:
            self.total_defined = 0

        self.number_defined = n_elements > 0

        self.allocation_case = None

        if self.element_defined and self.number_defined:
            # kva known, number per step known
            self.allocation_case = 1

        elif self.element_defined and self.steps_defined:
            # kva known, total for each step known
            self.allocation_case = 2

        elif self.element_defined and self.total_defined:
            # kva known, total defined as single value
            self.allocation_case = 3

        if self.allocation_case is None:
            print('Ill defined element - definition matches no valid cases')

    def __repr__(self) -> str:
        info_str = (f"PV Element Name: {self.name} // " +
                    f"{self.total_allocated_elements} elements allocated //" +
                    f" Total: {self.total_allocated_kva} kva " +
                    f"{self.total_allocated_kvar} kvar"
                    )
        return info_str

    def reset_allocation_tracking(self):
        """
        Reset tracking of allocation
        """
        self.total_allocated_elements = 0
        self.total_allocated_kw = 0
        self.total_allocated_kvar = 0

    def update_allocation_tracking(self, current_step):
        """
        Method to track element allocation
        """
        lines_written = sum(self._lines_per_step[0:(current_step+1)])
        self.total_allocated_elements = lines_written
        self.total_allocated_kva = self._kva_per_line * lines_written
        self.total_allocated_kvar = self._kvar_per_line * lines_written

    def get_lines_per_step(self, total_steps):
        """
        TODO handle each step
        TODO Handle 'total' situaion
        Based on kind of allocation, object definition parameters,
        and number of total scenario number of steps,
        calculate and update object private variables.
        i.e. _kw_per_line, _kvar_per_line, _lines_per_step
        _lines_per_step is a list of additional lines to write each step.
        e.g. if 7 elements are to be allocated per step for 4 steps:
        _lines_per_step == [7, 7, 7, 7]

        This approach is to allow for non-linear allocations per step that may
        reflect situations better - e.g. [3, 4, 10, 11]
        """

        if self.kind == 'every_step':
            # handle lines when every line is the same
            if self.allocation_case == 1:
                self._kva_per_line = self.element_kva
                self._kvar_per_line = self.element_kvar

                self._lines_per_step = [self.n_elements] * total_steps
                return self._lines_per_step

        elif self.kind == 'each_step':
            # handle definition of sizes for each step
            if self.allocation_case == 2:
                # element size and list of sizes to add each step is known
                self._kva_per_line = self.element_kva
                self._kvar_per_line = self.element_kvar
                # TODO check lenght of list is same as n_Steps
                # ASSERT kw dictates element n
                # could write logic to find which is larger, or which value
                # ends up allocating more - BUT for now - happy path only
                # calculate elements per total 
                # ceil to elimante possible under allocation
                n_total_allocations = np.ceil(
                    np.array(self.total_kva) / self.element_kva
                    )
                next_step = n_total_allocations[1:]
                previous_step = n_total_allocations[0:-1]
                lines_per_step = list(next_step - previous_step)
                lines_per_step.insert(0, n_total_allocations[0])

                self._lines_per_step = lines_per_step

                return self._lines_per_step

        elif self.kind == 'total':
            # handle case were total amount is given.
            if self.allocation_case == 3:
                # element size and list of sizes to add each step is known
                self._kva_per_line = self.element_kva
                self._kvar_per_line = self.element_kvar

                # ASSERT kva dictates total amount
                # calculate total number of allocations required
                n_total_allocations = np.ceil(self.total_kva /
                                              self.element_kva)
                # translate to allocaitons per step
                allocations_per_step = np.ceil(n_total_allocations/total_steps)
                # create list of lines per step
                lines_per_step = [allocations_per_step] * total_steps

                # insert zero for first step
                lines_per_step.insert(0, 0)
                self._lines_per_step = lines_per_step

                return self._lines_per_step

        else:
            # case not handled
            print(f"Error - allocation kind '{self.kind}' not valid.")
            return 0

    def get_kva_per_line(self):
        """
        Return current kw per line
        """
        return self._kva_per_line

    def get_kvar_per_line(self):
        """
        Return current kvar per line
        """
        return self._kvar_per_line


class StorageAllocationElement():
    """
    Class to handle definition and tracking of storage elements

    Similar to PV allocation at the moment...
    ASSERT kva dictacts amount of storage...

    Thinking: will likely need to handle kwh better.
    """
    def __init__(
            self,
            name,
            element_prepend='ADDED_STORAGE_',
            element_kv=None,
            element_kva=0,
            element_kwh=0,
            element_reserve=20,
            element_stored=50,
            total_kva=0,
            total_kwh=0,
            n_elements=0,
            dispmode='',
            kind='every_step'
            ):
        """
        Based on given definitions, calculate required values for scenario
        """
        self.name = name
        self.element_prepend = element_prepend
        self.element_kva = element_kva
        self.element_kwh = element_kwh
        self.element_reserve = element_reserve
        self.element_stored = element_stored
        self.element_kv = element_kv
        self.total_kva = total_kva
        self.total_kwh = total_kwh
        self.n_elements = n_elements
        self.dispmode = dispmode

        valid_kinds = [
            'every_step',
            'each_step',
            'total'
        ]
        if kind not in valid_kinds:
            print('Ill defined element - kind not vaild')
        else:
            self.kind = kind

        # for scenario placeholders
        # populated via calculate_lines_per_step method
        self._kva_per_line = 0
        self._kwh_per_line = 0
        self._lines_per_step = 0

        # for tracking
        self.total_allocated_elements = 0
        self.total_allocated_kva = 0
        self.total_allocated_kwh = 0

        # based on inputs, set case type.
        self.element_defined = element_kva != 0
        self.steps_defined = isinstance(total_kva, list)

        # in case of totals being a list, simple logic throws error
        try:
            self.total_defined = total_kva != 0
        except TypeError:
            self.total_defined = 0

        self.number_defined = n_elements > 0

        self.allocation_case = None

        if self.element_defined and self.number_defined:
            # kva known, number per step known
            self.allocation_case = 1

        elif self.element_defined and self.steps_defined:
            # kva known, total for each step known
            self.allocation_case = 2

        elif self.element_defined and self.total_defined:
            # kva known, total defined as single value
            self.allocation_case = 3

        if self.allocation_case is None:
            print('Ill defined element - definition matches no valid cases')

    def __repr__(self) -> str:
        info_str = (f"Storage Element Name: {self.name} // " +
                    f"{self.total_allocated_elements} elements allocated //" +
                    f" Total: {self.total_allocated_kva} kva " +
                    f"{self.total_allocated_kwh} kwh"
                    )
        return info_str

    def reset_allocation_tracking(self):
        """
        Reset tracking of allocation
        """
        self.total_allocated_elements = 0
        self.total_allocated_kva = 0
        self.total_allocated_kwh = 0

    def update_allocation_tracking(self, current_step):
        """
        Method to track element allocation
        """
        lines_written = sum(self._lines_per_step[0:(current_step+1)])
        self.total_allocated_elements = lines_written
        self.total_allocated_kva = self._kva_per_line * lines_written
        self.total_allocated_kwh = self._kwh_per_line * lines_written

    def get_lines_per_step(self, total_steps):
        """
        coppied and modifed from PV allocation
        """

        if self.kind == 'every_step':
            # handle lines when every line is the same
            if self.allocation_case == 1:
                self._kva_per_line = self.element_kva
                self._kwh_per_line = self.element_kwh

                self._lines_per_step = [self.n_elements] * total_steps
                return self._lines_per_step

        elif self.kind == 'each_step':
            # handle definition of sizes for each step
            if self.allocation_case == 2:
                # element size and list of sizes to add each step is known
                self._kva_per_line = self.element_kva
                self._kwh_per_line = self.element_kwh
                # TODO check lenght of list is same as n_Steps
                # ASSERT kw dictates element n
                # could write logic to find which is larger, or which value
                # ends up allocating more - BUT for now - happy path only
                # calculate elements per total
                # ceil to elimante possible under allocation
                n_total_allocations = np.ceil(
                    np.array(self.total_kva) / self.element_kva
                    )
                next_step = n_total_allocations[1:]
                previous_step = n_total_allocations[0:-1]
                lines_per_step = list(next_step - previous_step)
                lines_per_step.insert(0, n_total_allocations[0])

                self._lines_per_step = lines_per_step

                return self._lines_per_step

        elif self.kind == 'total':
            # handle case were total amount is given.
            if self.allocation_case == 3:
                # element size and list of sizes to add each step is known
                self._kva_per_line = self.element_kva
                self._kwh_per_line = self.element_kwh

                # ASSERT kva dictates total amount
                # calculate total number of allocations required
                n_total_allocations = np.ceil(self.total_kva /
                                              self.element_kva)
                # translate to allocaitons per step
                allocations_per_step = np.ceil(n_total_allocations/total_steps)
                # create list of lines per step
                lines_per_step = [allocations_per_step] * total_steps

                # insert zero for first step
                lines_per_step.insert(0, 0)
                self._lines_per_step = lines_per_step

                return self._lines_per_step

        else:
            # case not handled
            print(f"Error - allocation kind '{self.kind}' not valid.")
            return 0

    def get_kva_per_line(self):
        """
        Return current kw per line
        """
        return self._kva_per_line

    def get_kwh_per_line(self):
        """
        Return current kvar per line
        """
        return self._kwh_per_line


class WindAllocationElement():
    """
    Class to handle definition and tracking of wind generator elements

    Similar to PV allocation at the moment.

    Generally, store allocation parameters,
    handle identification of valid allocation method,
    perform required calculations for element power per line (element)
    store total allocation statistics.

    pf is defined as negative to indicate absorbing vars.
    (i.e. generating inductive vars)
    """
    def __init__(
            self,
            name,
            element_prepend='ADDED_WIND_',
            element_kw=0,
            element_pf=-0.9,
            total_kw=0,
            n_elements=0,
            element_kv=None,  # to be used later for voltage things
            kind='every_step',
            match_bus_phase=False  # for multiphase systems...
            ):
        """
        Based on given definitions, calculate required values for scenario
        """
        self.name = name
        self.element_prepend = element_prepend
        self.element_kw = element_kw
        self.element_pf = element_pf

        self.total_kw = total_kw
        self.n_elements = n_elements

        self.element_kv = element_kv

        self.match_bus_phase = match_bus_phase

        # for scenario placeholders
        # populated via calculate_lines_per_step method
        self._kw_per_line = 0
        self._lines_per_step = 0

        # for tracking
        self.total_allocated_elements = 0
        self.total_allocated_kw = 0

        # for allocation case
        self.number_defined = n_elements > 0
        self.allocation_case = None

        # TODO: functionalize input check for kind of allocation
        # inputs: element and total power rating...
        valid_kinds = [
            'every_step',
            'each_step',
            'total'
        ]
        if kind not in valid_kinds:
            print('Ill defined element - kind not vaild')
        else:
            self.kind = kind

        # based on inputs, set case type.
        self.element_defined = element_kw != 0
        self.steps_defined = isinstance(total_kw, list)

        # in case of totals being a list, simple logic throws error
        try:
            self.total_defined = total_kw != 0
        except TypeError:
            self.total_defined = 0

        if self.element_defined and self.number_defined:
            # kva known, number per step known
            self.allocation_case = 1

        elif self.element_defined and self.steps_defined:
            # kva known, total for each step known
            self.allocation_case = 2

        elif self.element_defined and self.total_defined:
            # kva known, total defined as single value
            self.allocation_case = 3

        if self.allocation_case is None:
            print('Ill defined element - definition matches no valid cases')

    def __repr__(self) -> str:
        info_str = (f"Wind Generator Name: {self.name} // " +
                    f"{self.total_allocated_elements} elements allocated //" +
                    f" Total: {self.total_allocated_kw} kw "
                    )
        return info_str

    def reset_allocation_tracking(self):
        """
        Reset tracking of allocation
        """
        self.total_allocated_elements = 0
        self.total_allocated_kw = 0    

    def update_allocation_tracking(self, current_step):
        """
        Method to track element allocation
        """
        lines_written = sum(self._lines_per_step[0:(current_step+1)])
        self.total_allocated_elements = lines_written
        self.total_allocated_kw = self._kw_per_line * lines_written

    def get_lines_per_step(self, total_steps):
        """
        This method could likely be functionalized and resued.
        TODO handle each step
        TODO Handle 'total' situaion
        Based on kind of allocation, object definition parameters,
        and number of total scenario number of steps,
        calculate and update object private variables.
        i.e. _kw_per_line, _kvar_per_line, _lines_per_step
        _lines_per_step is a list of additional lines to write each step.
        e.g. if 7 elements are to be allocated per step for 4 steps:
        _lines_per_step == [7, 7, 7, 7]

        This approach is to allow for non-linear allocations per step that may
        reflect situations better - e.g. [3, 4, 10, 11]
        """

        if self.kind == 'every_step':
            # handle lines when every line is the same
            if self.allocation_case == 1:
                self._kw_per_line = self.element_kw

                self._lines_per_step = [self.n_elements] * total_steps
                return self._lines_per_step

        elif self.kind == 'each_step':
            # handle definition of sizes for each step
            if self.allocation_case == 2:
                # element size and list of sizes to add each step is known
                self._kw_per_line = self.element_kw
                # TODO check length of list is same as n_Steps
                # ASSERT kw dictates element n
                # could write logic to find which is larger, or which value
                # ends up allocating more - BUT for now - happy path only
                # calculate elements per total 
                # ceil to elimante possible under allocation
                n_total_allocations = np.ceil(
                    np.array(self.total_kw) / self.element_kw
                    )
                next_step = n_total_allocations[1:]
                previous_step = n_total_allocations[0:-1]
                lines_per_step = list(next_step - previous_step)
                lines_per_step.insert(0, n_total_allocations[0])

                self._lines_per_step = lines_per_step

                return self._lines_per_step

        elif self.kind == 'total':
            # handle case were total amount is given.
            if self.allocation_case == 3:
                # element size and list of sizes to add each step is known
                self._kw_per_line = self.element_kw

                # ASSERT kw dictates total amount
                # calculate total number of allocations required
                n_total_allocations = np.ceil(self.total_kw /
                                              self.element_kw)
                # translate to allocaitons per step
                allocations_per_step = np.ceil(n_total_allocations/total_steps)
                # create list of lines per step
                lines_per_step = [allocations_per_step] * total_steps

                # insert zero for first step
                lines_per_step.insert(0, 0)
                self._lines_per_step = lines_per_step

                return self._lines_per_step

        else:
            # case not handled
            print(f"Error - allocation kind '{self.kind}' not valid.")
            return 0

    def get_kw_per_line(self):
        """
        Return current kw per line
        """
        return self._kw_per_line


@dataclass
class LocationRule:
    """ Class to hold data for location rules """
    name: str
    feeder_element_class: str
    element_attribute: str
    comparison_operation: str
    comparison_value: str
    resulting_locations: set


def generic_comparison(left_value, comparison_operation, right_value):
    """
    function to handle comparisons of numeric values from strings 
    Also handles a 'contains' situation that looks for matches.

    Assert left value is data frame.
    """
    # maybe use operator.gt? etc. because this will be masking pandas dfs...
    try:
        if comparison_operation == '<':
            return left_value < right_value
        if comparison_operation == '>':
            return left_value > right_value
        if comparison_operation == '==':
            return left_value == right_value
        if comparison_operation == '!=':
            return left_value != right_value
        if comparison_operation == '<=':
            return left_value <= right_value
        if comparison_operation == '>=':
            return left_value >= right_value
        if comparison_operation == 'contains':
            return left_value.str.lower().str.contains(right_value.lower())
        if comparison_operation == 'isin':
            return left_value.isin(right_value)
        return NotImplemented
    except TypeError:
        print('Types do not support comparison')
        return
