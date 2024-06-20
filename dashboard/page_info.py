import panel as pn
import param


def gen_info():
    info = f"""# Info
                EVI-DiST welcomes you with the following mode selection page. As of version 0.7.1a, only the **Lite** version is available.
            """

    jpg_pane = pn.pane.Image('/dashboard/fig/welcome.png')

    return jpg_pane

