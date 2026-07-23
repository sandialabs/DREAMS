""" 
helper functions related to running the simulations required for 
QSTS hosting capacity
"""

import dreams
import numpy as np
import opendssdirect as dssdirect

from . import monitor as interp_monitors
# from . import monitor_selector as ms

# general functions
def init_feeder(
        qsts_hc,
        create_monitors=False,
        kva=None,
        bus_name=None,
        step_size_s=60*60,
        ):
    """
    Solve feeder, initialize monitors,
    create, modify, or move pv_hca system
    initialze model to run simulation

    NOTE: currently, all thermal elements are monitored.
    This is not required and increases execution time.
    likely, Only a select few (2-4ish) are required for thermal data recording.

    Voltage monitoring is handled at the pv system

    substation backfeeding is accounted for at the vsource.
    """
    feeder = qsts_hc.feeder
    asset_shape = qsts_hc.asset_shape
    asset_mode = qsts_hc.mode
    debug = qsts_hc.debug

    if (asset_shape is not None) and create_monitors:
        # use shape file to create loadshape with name
        shape_line = asset_shape.create_shape_redirect().lines[0]
        shape_creation_res = dreams.dss.cmd(shape_line)
        # print(f"shape creation res: {shape_creation_res}")

    feeder.solve(set_mode=True)  # TODO: pass in mode? unsure if it matters for this solution

    if qsts_hc.kind == 'gen':
        if kva is None:
            if bus_name is None:
                # first run only
                add_first_hca_gen(feeder, kw=0.01, asset_shape=asset_shape, asset_mode=asset_mode)
            else:
                add_first_hca_gen(feeder, bus_name, asset_shape=asset_shape, asset_mode=asset_mode)
        else:
            # kva defined
            if bus_name is None:
                modify_existing_gen_hca(kva)
            else:
                # kva and bus name - change location
                # TODO: add in case where bus_name is not none to move pv system??? unsure of this note 20260612
                move_gen_hca(feeder, bus_name, kva)

    else:
        # TODO: handle demand type of hosting capacity
        # NOTE: kva, assumed to be kw for now - should maybe allow different pf
        if kva is None:
            if bus_name is None:
                # first run only
                add_first_hca_load(feeder, kw=0.01, asset_shape=asset_shape, asset_mode=asset_mode)
            else:
                add_first_hca_load(feeder, bus_name, asset_shape=asset_shape, asset_mode=asset_mode)
        else:
            # kva defined
            if bus_name is None:
                modify_existing_load_hca(kva)
            else:
                # kva and bus name - change location
                move_load_hca(feeder, bus_name, kva)

    if create_monitors:
        qsts_hc.monitor_redirect = interp_monitors.add_monitors_to_feeder(feeder)

    # model init variables that may be parameterized later
    control_mode = 'static'
    max_iterations = 100
    max_ctrl_iterations = 50

    initialize_commands = [
        'reset',
        'reset monitors',
        'reset meters',
        'reset eventlog',
        'init',
        'set miniterations = 1',  # QSTS Speed up
        f'set maxiterations = {max_iterations}',
        f'set maxcontroliter = {max_ctrl_iterations}',  # added 12/14/23
        #'set sampleenergymeters=no',  # QSTS Speed up if no? - maybe.
        f'set controlmode={control_mode}',
        f'set mode={qsts_hc.mode}',
        f'set stepsize={step_size_s}s',
        'set number=1',
        'set totaltime=0',
        'set hour=0',
        'set min=0',
        'set sec=0',
        # above line to fix offset
        ]

    for cmd in initialize_commands:
        res = dreams.dss.cmd(cmd)
        if debug:
            print(f"{cmd} >> {res}")

def run_qsts(n_total_steps=8760, debug=False):
    """
    Execute the dss solve command an appropriate number of times.
    Returns a False for non-convergence
    """
    run_cmds = [
        "set number=1",
        'set controlmode=static',
    ]
    for run_cmd in run_cmds:
        run_res = dreams.dss.cmd(run_cmd)
        if debug:
            print(f"{run_cmd} >> {run_res}")

    # run each sln...
    converged = False
    for n in range(1, n_total_steps+1):
        run_res = dreams.dss.cmd('solve')

        if debug:
            if run_res == '':
                print(f"solve >> '{run_res}' >> {n}/{n_total_steps} >> {round(n/n_total_steps*100, 2)} %    ", end='\r')
            else:
                print()
                print(f"solve >> '{run_res}' >> {n}/{n_total_steps} >> {round(n/n_total_steps*100, 2)} %")
                print()

        converged = dssdirect.Solution.Converged()
        if not converged:
            print()
            print(f"Non-Convergence! at step {n}")
            return converged

    if debug:
        print()

    return converged
    
def collect_3_buses(feeder):
    """
    identify primary 3 buses for simple hosting capacity test

    Obvious issues with this approach, but useful enough for now
    """
    primary_mask = feeder.buses['primary']
    three_phase_mask = feeder.buses['n_phases'] == 3

    select_buses = feeder.buses[primary_mask & three_phase_mask]

    max_dist = select_buses['distance'].max()

    # identify furthest bus
    furthest_bus = select_buses.sort_values('distance').index[-1]

    # identify nearest bus
    near_mask = select_buses['distance'] < (max_dist * .25)
    select_buses[near_mask].sort_values('distance')
    nearest_bus = select_buses[near_mask].sort_values('distance').index[-1]

    # identify middle bus
    mid_mask = select_buses['distance'] > (max_dist * .666)
    middle_bus = select_buses[mid_mask].sort_values('distance').index[0]

    buses = [nearest_bus, middle_bus, furthest_bus]

    return buses

def collect_asset_range(start_value, end_value, iterations, kind='exp'):
    """"
    generate exponential range of values for asset size
    """
    if kind == 'exp':
        return np.logspace(
            np.log10(start_value),
            np.log10(end_value),
            num=iterations,
            dtype=int)
    else:
        return np.linspace(
            start_value,
            end_value,
            num=iterations,
            dtype=int)

def run_asset_range(qsts_hc, bus_name):
    """
    Run QSTS for each asset size, return dictionary of monitors
    """
    qsts_mons = {}
    qsts_mons[bus_name] = {}
    feeder = qsts_hc.feeder
    debug = qsts_hc.debug

    # update monitor selection using selector
    qsts_hc.monitor_selector.update(bus_name)
    if qsts_hc.debug:
        print("* identified elements to monitor:")
        print(qsts_hc.monitor_selector.buses_to_monitor)
        print(qsts_hc.monitor_selector.thermal_elements_to_monitor)

    # add monitors from monitor selector
    added_ms_monitors = []
    added_ms_monitors.extend(
        interp_monitors.add_voltage_monitors_from_ms(
            feeder,
            qsts_hc.monitor_selector.buses_to_monitor,
            qsts_hc.debug)
            )
    added_ms_monitors.extend(
        interp_monitors.add_thermal_montiors_from_ms(
            qsts_hc.monitor_selector.thermal_elements_to_monitor,
            qsts_hc.debug)
            )

    # ensure added asset on expected bus
    init_feeder(qsts_hc, kva=1, bus_name=bus_name, step_size_s=qsts_hc.step_size_sec)

    if qsts_hc.debug:
        print(f'testing {bus_name} with {1} kva')

    converged = run_qsts(n_total_steps=qsts_hc.total_time_steps, debug=debug)
    # if not converged:  # not handled... yet

    step_monitors = interp_monitors.collect_monitors()
    qsts_mons[bus_name][1] = step_monitors

    for asset_size in qsts_hc.asset_range:
        # update asset size
        int_size = int(asset_size)
        init_feeder(qsts_hc, kva=int_size, step_size_s=qsts_hc.step_size_sec)
        if qsts_hc.debug:
            print(f'testing {bus_name} with asset size: {int_size}')
        converged = run_qsts(n_total_steps=qsts_hc.total_time_steps, debug=debug)
        if converged:
            step_monitors = interp_monitors.collect_monitors()
            if qsts_hc.debug:
                print(step_monitors)
            qsts_mons[bus_name][int_size] = step_monitors
        else:
            print(f"* Skipping asset size {int_size}")

    # disable monitors from monitor selector
    interp_monitors.disable_monitors(added_ms_monitors)

    if qsts_hc.debug:
        print(f'Asset range of {bus_name} complete')
    return qsts_mons[bus_name]


# generation specific realted helpers
def add_first_hca_gen(
        feeder,
        bus_name=None,
        kw=None,
        asset_shape=None,
        asset_mode=None,
        ):
    """
    add first generation asset (pv) to feeder named 'gen_hca'
    """
    if bus_name is None:
        test_buses = collect_3_buses(feeder)
        bus_name = test_buses[0]
    bus = feeder.buses.loc[bus_name]

    n_phases = bus['n_phases']
    kv_base = bus['kv_base']

    if n_phases == 2:
        conn_type = 'delta'
    else:
        conn_type = 'wye'

    if kw is None:
        initial_size = 1  # initial size
    else:
        initial_size = kw

    # set pmpp and kva equal asset size.
    pv_line = f"new pvsystem.gen_hca bus1={bus_name} model=1 phases={n_phases} conn={conn_type} kv={kv_base} " \
        f"kva={initial_size} pmpp={initial_size} " \
        r"irradiance=1 vmaxpu=2 vminpu=0.1 %cutin=0.1 %cutout=0.1 %r=0.0 pfpriority=yes balanced=yes "
    
    if asset_shape is not None:
        # modify pv line to indicate profile NOTE: assumes duty as mode
        shape_addition = f" duty={asset_shape.name} "
        pv_line += shape_addition

    # this lines are required to reset internal openDSS linkings
    pv_s_mon_line = 'New Monitor.gen_hca_s element=PVsystem.gen_hca mode=1 PPolar=false terminal=1 enabled=true'
    pv_v_mon_line = 'New Monitor.volt__gen_hca element=PVsystem.gen_hca mode=0 terminal=1 enabled=true'

    # add pv system and monitor
    dreams.dss.cmd(pv_line)
    dreams.dss.cmd(pv_s_mon_line)
    dreams.dss.cmd(pv_v_mon_line)

def modify_existing_gen_hca(new_kva, debug=False):
    """
    Modify existing generation hca asset sizing
    """
    update_kva_cmd = f"edit pvsystem.gen_hca kva={new_kva}"
    kva_res = dreams.dss.cmd(update_kva_cmd)
    update_kva_cmd = f"edit pvsystem.gen_hca pmpp={new_kva}"
    pmpp_res = dreams.dss.cmd(update_kva_cmd)

    if debug:
        # note: all valid results should be ''
        print(f'kva result: {kva_res}')
        print(f'pmpp result: {pmpp_res}')

def move_gen_hca(feeder, bus_name, kva, debug=False):
    """
    move gen_hca element to new bus and update kva
    """
    bus = feeder.buses.loc[bus_name]

    n_phases = bus['n_phases']
    kv_base = bus['kv_base']

    if n_phases == 2:
        conn_type = 'delta'
    else:
        conn_type = 'wye'

    update_bus_cmd = f"edit pvsystem.gen_hca bus1={bus_name}"
    bus_res = dreams.dss.cmd(update_bus_cmd)

    update_phases_cmd = f"edit pvsystem.gen_hca phases={n_phases}"
    phase_res = dreams.dss.cmd(update_phases_cmd)

    update_conn_cmd = f"edit pvsystem.gen_hca conn={conn_type}"
    con_res = dreams.dss.cmd(update_conn_cmd)

    update_kv_cmd = f"edit pvsystem.gen_hca kv={kv_base}"
    kv_res = dreams.dss.cmd(update_kv_cmd)

    # use function to update kva and pmpp
    modify_existing_gen_hca(kva, debug)

    # required update of hca monitor (else incorrect reporting)
    update_s_monitor = "edit Monitor.gen_hca_s element=PVsystem.gen_hca"
    s_res = dreams.dss.cmd(update_s_monitor)
    update_v_monitor = "edit Monitor.volt__gen_hca element=PVsystem.gen_hca"
    v_res = dreams.dss.cmd(update_v_monitor)

    if debug:
        # note: all valid results should be ''
        print(f'bus_res: {bus_res}')
        print(f'phase_res: {phase_res}')
        print(f'con_res: {con_res}')
        print(f'kv_res: {kv_res}')
        print(f's_res: {s_res}')
        print(f'v_res: {v_res}')


# load related helpers
def add_first_hca_load(
        feeder,
        bus_name=None,
        kw=None,
        asset_shape=None,
        asset_mode=None):
    """
    add first demand asset (load) to feeder named 'load_hca'
    TODO: instead of full constant power, allow otehr types of load
    """
    if bus_name is None:
        test_buses = collect_3_buses(feeder)
        bus_name = test_buses[0]
    bus = feeder.buses.loc[bus_name]

    n_phases = bus['n_phases']
    kv_base = bus['kv_base']

    if n_phases == 2:
        conn_type = 'delta'  # NOTE: carry over from generation hosting capacity... may not make sense here
    else:
        conn_type = 'wye'

    if kw is None:
        initial_size = 1  # initial size
    else:
        initial_size = kw

    # initialize load
    load_line = f"new load.load_hca bus1={bus_name} phases={n_phases} model=1 " \
        f"conn={conn_type} kv={kv_base} " \
        f"kW={initial_size} kvar=0 " \
        r"Vmaxpu=2 Vminpu=0.7 "
    
    if asset_shape is not None:
        # modify pv line to indicate profile NOTE: assumes duty as mode
        shape_addition = f" duty={asset_shape.name} "
        load_line += shape_addition

    # this lines are required to reset internal openDSS linkings
    load_s_mon_line = 'New Monitor.load_hca_s element=load.load_hca mode=1 terminal=1 enabled=true PPolar=false'
    load_v_mon_line = 'New Monitor.volt__load_hca element=load.load_hca  mode=0 terminal=1 enabled=true'

    # add pv system and monitor
    dreams.dss.cmd(load_line)
    dreams.dss.cmd(load_s_mon_line)
    dreams.dss.cmd(load_v_mon_line)

def modify_existing_load_hca(new_kw, debug=False):
    """
    Modify existing generation hca asset sizing
    """
    update_kw_cmd = f"edit load.load_hca kw={new_kw}"
    kw_res = dreams.dss.cmd(update_kw_cmd)

    if debug:
        # note: all valid results should be ''
        print(f'kw result: {kw_res}')

def move_load_hca(feeder, bus_name, kva, debug=False):
    """
    move load_hca element to new bus and update kw
    # NOTE still assumeing constant power 1.0 load for now
    """
    bus = feeder.buses.loc[bus_name]

    n_phases = bus['n_phases']
    kv_base = bus['kv_base']

    if n_phases == 2:
        conn_type = 'delta'
    else:
        conn_type = 'wye'

    update_bus_cmd = f"edit load.load_hca bus1={bus_name}"
    bus_res = dreams.dss.cmd(update_bus_cmd)

    update_phases_cmd = f"edit load.load_hca phases={n_phases}"
    phase_res = dreams.dss.cmd(update_phases_cmd)

    update_conn_cmd = f"edit load.load_hca conn={conn_type}"
    con_res = dreams.dss.cmd(update_conn_cmd)

    update_kv_cmd = f"edit load.load_hca kv={kv_base}"
    kv_res = dreams.dss.cmd(update_kv_cmd)

    # use function to update kw
    modify_existing_load_hca(kva, debug)

    # required update of hca monitor (else incorrect reporting)
    update_s_monitor = "edit Monitor.load_hca_s element=load.load_hca"
    s_res = dreams.dss.cmd(update_s_monitor)
    update_v_monitor = "edit Monitor.volt__load_hca element=load.load_hca"
    v_res = dreams.dss.cmd(update_v_monitor)

    if debug:
        # note: all valid results should be ''
        print(f'bus_res: {bus_res}')
        print(f'phase_res: {phase_res}')
        print(f'con_res: {con_res}')
        print(f'kv_res: {kv_res}')
        print(f's_res: {s_res}')
        print(f'v_res: {v_res}')