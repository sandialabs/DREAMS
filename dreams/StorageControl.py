import dreams


class StorageControl():
    """
    Standard storage controller designed for peak shaving high and low.

    name must be openDSS complient (no spaces, no periods, etc)

    Includes options to set rate_charge and reserve as parameters in dss start
    with a %.

    Other control not tested/handled at this time.

    Requires control name and element to monitor.
    """

    def __init__(
            self,
            name: str,
            element: str,
            element_list=None,
            reserve: int = 20,
            rate_charge: int = 100,
            rate_kw: int = 100,
            max_ctrl_iter=None,
            kwband_low=10,
            kwband_high=10,
            **kwargs
            ) -> None:

        # save input to self
        self.name = name
        self.element = element

        self.element_list = element_list

        self.max_ctrl_iter = max_ctrl_iter

        self.redirect = None

        # default paramater dictionary
        self.parameter_dictionary = {
            'element': self.element,
            # 'terminal': 1,
            'monphase': 'ave',
            'modedischarge': 'peakshave',
            'modecharge': 'peakshavelow',
            'daily': '',
            'kwtarget': 50000,
            'kwtargetlow': 100,
            '%reserve': reserve,
            '%ratecharge': rate_charge,
            '%ratekw': rate_kw,
            '%kwband': kwband_high,  # allow for +/- 5% from band.
            '%kwbandlow': kwband_low,
            'inhibittime': 1,
            # 'resetlevel': 0.2,
            'dispfactor': 0.01,
            # 'dispmode': 'external',
            'eventlog': 'yes'  # may be faster if no
            }

        # update/ add any other key word args to param dictionary
        self.parameter_dictionary.update(**kwargs)

        # remove extraneous keys...
        if self.parameter_dictionary['modedischarge'] == 'time':
            del self.parameter_dictionary['kwtarget']
            del self.parameter_dictionary['daily']
            del self.parameter_dictionary['%kwband']
            del self.parameter_dictionary['%kwbandlow']
            # del self.parameter_dictionary['inhibittime']
            del self.parameter_dictionary['monphase']

        if self.parameter_dictionary['modedischarge'] == 'loadshape':
            del self.parameter_dictionary['kwtarget']
            # del self.parameter_dictionary['modecharge']
            del self.parameter_dictionary['%ratecharge']
            del self.parameter_dictionary['%ratekw']
            del self.parameter_dictionary['kwtargetlow']
            del self.parameter_dictionary['%kwband']
            del self.parameter_dictionary['%kwbandlow']
            del self.parameter_dictionary['inhibittime']
            del self.parameter_dictionary['monphase']

        if self.parameter_dictionary['modedischarge'] == 'peakshave':
            del self.parameter_dictionary['daily']

    def create_control_redirect(self):
        """
        Using paramters of object, create and return redirect
        """
        lines = []

        # create control definition based on parameter dictionary
        lines.append(f'new StorageController.{self.name}')
        for key, value in self.parameter_dictionary.items():
            lines.append(f"~ {key}={value}")

        # add maxxcontroliter line
        if self.max_ctrl_iter is not None:
            lines.append(f'set maxcontroliter = {self.max_ctrl_iter}')

        # create and save redirect
        self.redirect = dreams.Redirect(self.name, lines=lines)

        return self.redirect
