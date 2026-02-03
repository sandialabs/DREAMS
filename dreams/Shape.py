import pandas as pd
import dreams


class Shape():
    """
    Create open DSS compatible shape - or profile.
    Useful for demand and irradiance.
    Can accept either a data_path or data series.
    If using data_path, interval of 0 seems to work.
    If useing a pandas data series, interval should be related to the
    hours between each data point.

    Uses all valid values as points, unless n_points is defined.
    Specify interval and mode.  Default of yearly hours.
    Specify element kind (loads, pv_system, ... to match feeder attribute) and
    optional element list.
    if elements are listed, the apply_to_elements method will only apply to
    the named elements, else it will be applied to all elements.

    plot allows visualization of shape.


    realization this may also be very similar to a control redirect...

    """

    def __init__(
            self,
            data_path,
            name,
            header=None,
            column=1,
            n_points=None,
            hour_interval=1.0,
            # minute_interval=0.0,
            # second_interval=0.0,
            mode='yearly',
            element_kind='loads',
            element_list=None,
            ):

        # save variables to self
        self.data_path = data_path
        self.name = name

        self.hour_interval = hour_interval
        # self.minute_interval = minute_interval
        # self.second_interval = second_interval
        self.mode = mode
        self.element_list = element_list

        self.element_kind = element_kind

        # attempt to load data
        if isinstance(data_path, pd.Series):
            self.data = data_path
        else:
            self.data = pd.read_csv(data_path, header=header)
            self.data = self.data.iloc[:, column]

        if n_points is None:
            self.n_points = len(self.data)
        else:
            self.data = self.data.iloc[0:n_points]

    def plot(self, **kwargs):
        """
        plot profile - ensure time correct loading
        """
        return self.data.plot(title=self.name, **kwargs)

    def create_shape_redirect(self, use_file=False):
        """
        create redirect that loads profile into openDSS.
        uses parameters of self.
        """
        if not use_file:
            lines = [
                f"new loadshape.{self.name} npts={self.n_points} "
                f"interval={self.hour_interval} "
                f"mult={list(self.data.values)}"
            ]
        else:
            lines = [
                f"new loadshape.{self.name} npts={self.n_points} "
                f"interval={self.hour_interval} "
                f"csvfile='{self.data_path}'"
            ]

        return dreams.Redirect(self.name, lines=lines)

    def create_edit_elements_redirect(self, feeder):
        """
        create redirect to edit system elements to follow shape.
        apply to all elements of deinfed kind unless list is provided
        in which case, apply only to listed elements.
        """
        element_df = getattr(feeder, self.element_kind)

        # handle difference between df and dss
        if self.element_kind == 'loads':
            element_kind = 'load'
        elif self.element_kind == 'pv_systems':
            element_kind = 'pvsystem'

        if self.element_list is not None:
            # maske values to valid entries
            cleaned_list = [x for x in self.element_list
                            if x in element_df.index]
            element_df = element_df.loc[cleaned_list]

        lines = []
        # using list
        for element in element_df.index:
            line = f"edit {element_kind}.{element} {self.mode}={self.name}"
            lines.append(line)

        name = f"{self.element_kind}_to_{self.name}"

        return dreams.Redirect(name, lines=lines)
