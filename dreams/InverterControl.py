import dreams


class InverterControl():
    """
    Standard creation of inverter control for PV systems.

    Name is used to assign control to via control rules.
    Must be openDSS complient (no spaces, no periods, etc)

    Volt Var (vv) and Volt Watt (vw) curves are standard 1547 2018 b.

    The curves can be replaced by passing in new lists of values for
    vv_x, vv_y, vw_x, vw_y.  The x axis corresponds to PU voltage while the y
    axis corresponds to the PU limit of the controlled output.

    Includes param for max control iterations - may be changed...

    Note:
    Depending on voltage requirements, may cause issues with storage
    controller.

    activepchangetolerance
    Voltagechagnetolerance
    varchangetolerance
    rateofchangemode - may have to do with oscillation

    """

    def __init__(
            self,
            name: str,
            kind: str = 'vv_vw',
            vv_x: list = None,
            vv_y: list = None,
            vw_x: list = None,
            vw_y: list = None,
            max_ctrl_iter=None,
            **kwargs
            ) -> None:

        # handle vv and vw xy curve creation
        if vv_x is None:
            self.vv_x = [0.92, 0.98, 1.0, 1.02, 1.08]
        else:
            self.vv_x = vv_x

        if vv_y is None:
            self.vv_y = [0.44, 0.0, 0.0, 0.0, -0.44]
        else:
            self.vv_y = vv_y

        if vw_x is None:
            self.vw_x = [1.0, 1.06, 1.1]
        else:
            self.vw_x = vw_x

        if vw_y is None:
            self.vw_y = [1.0, 1.0, 0.2]
        else:
            self.vw_y = vw_y

        # save varibles to self
        self.name = name
        self.kind = kind

        # populated by scenario (if used)
        self.der_list = []

        self.max_ctrl_iter = max_ctrl_iter

        self.redirect = None  # placeholder

        # create required property dictionary
        default_param_dicts = {
            'vv_vw': {
                'combimode': 'vv_vw',
                'voltage_curvex_ref': 'rated',
                'vvc_curve1': f"{self.name}_vv_curve",
                'voltwatt_curve': f"{self.name}_vw_curve",
                'voltwattyaxis': 'PMPPPU',
                'refreactivepower': 'VARMAX',
            },
            'vv': {
                'mode': 'VOLTVAR',
                'voltage_curvex_ref': 'rated',
                'vvc_curve1': f"{self.name}_vv_curve",
                'refreactivepower': 'VARMAX',
            },
            'vw': {
                'mode': 'VOLTWATT',
                'voltage_curvex_ref': 'rated',
                'voltwatt_curve': f"{self.name}_vw_curve",
                'voltwattyaxis': 'PMPPPU',
            }
        }

        # check for kind validity
        if self.kind not in default_param_dicts:
            print(f"'{kind}' not a valid Inverter Control kind")
            return
        self.parameter_dictionary = default_param_dicts[kind]

        # update/ add any other key word args to param dictionary
        self.parameter_dictionary.update(**kwargs)

    def create_control_redirect(self):
        """
        Using parameters of object, create redirect to fully define control.
        """
        lines = []

        # create xy curve(s)
        if self.kind in ['vv', 'vv_vw']:
            # make volt var curve
            lines.append(f"new xycurve.{self.name}_vv_curve "
                         f"npts={len(self.vv_y)} "
                         f"yarray={self.vv_y} xarray={self.vv_x}")

        if self.kind in ['vw', 'vv_vw']:
            # make volt watt curve
            lines.append(f"new xycurve.{self.name}_vw_curve "
                         f"npts={len(self.vw_y)} "
                         f"yarray={self.vw_y} xarray={self.vw_x}")

        # create control definition based on parameter dictionary
        lines.append(f'new invcontrol.{self.name}')
        for key, value in self.parameter_dictionary.items():
            lines.append(f"~ {key}={value}")

        if self.der_list is None:
            lines.append("~ derlist=[]")

        lines.append("~ eventlog=yes")  # for debug - may be faster if no

        # add maxxcontroliter line
        if self.max_ctrl_iter is not None:
            lines.append(f'set maxcontroliter = {self.max_ctrl_iter}')

        # create and save redirect
        self.redirect = dreams.Redirect(self.name, lines=lines)

        return self.redirect
