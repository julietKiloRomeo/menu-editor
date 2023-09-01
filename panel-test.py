import numpy as np
import pandas as pd
from matplotlib.figure import Figure

# https://medium.com/@marcskovmadsen/i-prefer-to-use-panel-for-my-data-apps-here-is-why-1ff5d2b98e8f

data_url = "https://cdn.jsdelivr.net/gh/holoviz/panel@master/examples/assets/occupancy.csv"
data = pd.read_csv(data_url, parse_dates=["date"]).set_index("date")

primary_color = "#0072B5"
secondary_color = "#94EA84"


def mpl_plot(avg, highlight):
    fig = Figure(figsize=(10,5))
    ax = fig.add_subplot()
    avg.plot(ax=ax, c=primary_color)
    if len(highlight):
        highlight.plot(style="o", ax=ax, c=secondary_color)
    return fig


def find_outliers(variable="Temperature", window=20, sigma=10, view_fn=mpl_plot):
    avg = data[variable].rolling(window=window).mean()
    residual = data[variable] - avg
    std = residual.rolling(window=window).std()
    outliers = np.abs(residual) > std * sigma
    return view_fn(avg, avg[outliers])


# Panel
import panel as pn

pn.extension(sizing_mode="stretch_width", template="fast")

# Define labels and widgets
pn.pane.Markdown("Variable").servable(area="sidebar")
variable = pn.widgets.RadioBoxGroup(
    name="Variable", value="Temperature", options=list(data.columns), margin=(-10, 5, 10, 10)
).servable(area="sidebar")
window = pn.widgets.IntSlider(name="Window", value=20, start=1, end=60).servable(area="sidebar")

# Make your functions interactive, i.e. react to changes in widget values
ifind_outliers = pn.bind(find_outliers, variable, window, 10)

# Layout the interactive functions
pn.panel(ifind_outliers, sizing_mode="scale_both").servable()

# Configure the template
pn.state.template.param.update(
    site="Panel", title="Getting Started Example",
    accent_base_color=primary_color, header_background=primary_color,
)