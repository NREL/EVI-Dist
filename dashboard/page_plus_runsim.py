import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import panel as pn
import param
import asyncio
from styles import custom_style
from tqdm import tqdm
from panel.widgets import Tqdm

from modules.simulation_plus import SimPlus

pn.extension('terminal')

class pgPlusRunSim(param.Parameterized):

    file_names = param.Dict()
    configs = param.Dict()

    ready = param.Boolean(default=False)

    @param.output('file_names', 'configs')
    def output(self):
        self.file_names = {'dss_main' : self.file_names['dss_main']}
        self.file_names['evloads'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_evloads.csv'
        self.file_names['linecurrents'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_linecurrents.csv'
        self.file_names['linedata'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_linedata.csv'
        self.file_names['trnscurrents'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_trnscurrents.csv'
        self.file_names['trnskva'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_trnskva.csv'
        self.file_names['trnskva_ratings'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_trnskva_ratings.csv'
        self.file_names['voltages'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_voltages.csv'
        self.file_names['bus_info'] = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.configs["sim_name"]}_businfo.csv'
        self.configs = {"sim_name": self.configs["sim_name"]}
        return self.file_names, self.configs
    
    def __init__(self, **params):
        super().__init__(**params)
        # print(self.file_names)
        # print(self.configs)
        self.progress_bar = pn.widgets.Progress(name='Progress', value=0, width=300, align=('center','center'))
        self.simulation_description = pn.pane.Markdown(f"""
                    ## Simulation config summary
                    - <b>{self.configs["sim_name"]}</b>""", height=150)
        self.info_text = [pn.pane.Markdown("Execution progress", styles=custom_style, align=('center','center')), 
                          pn.pane.Markdown("0%", width=50, styles=custom_style, align=('center','center'))]
        self.pb = tqdm(total=100)
        #self.tqdm_progress = Tqdm(align=('center','center'), width=300)

        ########################### THIS VERSION SHOULD BE READ OFF OF A FILE #############################
        self.terminal = pn.widgets.Terminal("EVI-DiST (v.0.7.1a)\nSimulation terminal\n==================================\n",

        options={
            "foreground": "#53676d",
            "background": "#fbf3db",
            "cursorColor": "#3a4d53",       
            "selectionBackground": "#cfcebe",
            "black": "#e9e4d0",
            "red": "#d2212d",
            "green": "#489100",
            "yellow": "#ad8900",
            "blue": "#0072d4",
            "purple": "#ca4898",
            "cyan": "#009c8f",
            "white": "#909995",
            "brightBlack": "#cfcebe",
            "brightRed": "#cc1729",
            "brightGreen": "#428b00",
            "brightYellow": "#a78300",
            "brightBlue": "#006dce",
            "brightPurple": "#c44392",
            "brightCyan": "#00978a",
            "brightWhite": "#3a4d53",
            "cursor": "#3a4d53"
        },
        height=300, sizing_mode='stretch_width')
        sys.stdout = self.terminal 
    
    def panel(self):

        async def update_progress_bar(progress_queue):
            while True:
                s = await progress_queue.get()  # Get the latest progress value from the queue
                self.progress_bar.value = int(s)
                self.info_text[1].object = f"{int(s)}%"
                self.pb.n = s
                self.pb.refresh()
                #self.tqdm_progress.value = int(s) 
                if s >= 100:
                    self.ready = True
                    break

        async def run_async(event):
           
            progress_queue = asyncio.Queue()

            progress = [0]
            sim = SimPlus(self.configs["sim_name"], self.file_names["dss_main"])

            await asyncio.gather(
                sim.run(progress, progress_queue),
                update_progress_bar(progress_queue)
            )


        progress_start = pn.widgets.Button(name='Start simulation', button_type='success', align=('center','center'))
        progress_start.on_click(run_async)

        return pn.Row(pn.Column(self.simulation_description, 
                                pn.Row(pn.Spacer(width=20), margin=(0, 0, 0, 0)),
                                pn.Row(pn.Spacer(width=20), progress_start, self.progress_bar, self.info_text[1], align='center', margin=(0, 0, 0, 0))),
                      self.terminal)
                        