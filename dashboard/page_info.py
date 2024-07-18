import panel as pn
import param
from version_info import version_name

def gen_info():
    info = f"""# Info
                EVI-DiST welcomes you with the following mode selection page. As of version {version_name}, only the **Lite** version is available.
            """

    jpg_pane = pn.pane.Image('/dashboard/fig/welcome.png')

    return jpg_pane

