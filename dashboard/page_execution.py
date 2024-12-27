import sys
import os
sys.path.append(os.getcwd())
import panel as pn
import param
import asyncio
from styles import custom_style
import threading
from tqdm import tqdm
from panel.widgets import Tqdm
from version_info import version_name
from actions import convert_xfmappings_to_csv
from modules.simulation import SimLite

pn.extension('terminal')

class pgExecution(param.Parameterized):

    file_names = param.Dict()
    configs = param.Dict()
    ready = param.Boolean(default=False)

    @param.output('file_names', 'configs')
    def output(self):
        return self.file_names, self.configs
    
    def __init__(self, **params):
        super().__init__(**params)
        self.progress_bar = pn.widgets.Progress(name='Progress', value=0, width=300, align=('center','center'))
        self.simulation_description = pn.pane.Markdown(f"""
                    ## Simulation config summary
                    - <b>Selected feeder: </b>{self.configs['feeder']}
                    - <b>Selected controller(s): </b>{self.configs['controller']}
                    - <b>Selected month: </b>{self.configs['month']}
                    - <b>Timezone: </b>{self.configs['timezone'] if self.configs['timezone'] != 'UTC' else 'UTC or default timezone'}
                    - <b>EV Adoption: </b>{self.configs['adoption']}
                    - <b>AMI data: </b>{self.configs['ami_data_file']}""", height=150)
        self.info_text = [pn.pane.Markdown("Execution progress", styles=custom_style, align=('center','center')), 
                          pn.pane.Markdown("0%", width=50, styles=custom_style, align=('center','center'))]
        self.pb = tqdm(total=100)
        

        self.terminal = pn.widgets.Terminal(f"EVI-DiST (v{version_name})\nSimulation terminal\n==================================\n",
        options = {
            "theme": {
                "background": '#222426',
                "foreground": '#FFD700'
            },
            "fontSize": 10,
            "fontFamily": 'Fira Code, Menlo, Monaco, "Courier New", monospace',
            "cursorBlink": True
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
            progress_start.disabled = True
            progress_queue = asyncio.Queue()

            progress = [0]
            sim = SimLite(self.file_names, self.configs)

            await asyncio.gather(
                sim.run(progress, progress_queue),
                update_progress_bar(progress_queue)
            )


        progress_start = pn.widgets.Button(name='Start simulation', button_type='success', align=('center','center'))
        progress_start.on_click(run_async)

        return pn.Row(pn.Column(self.simulation_description, 
                                # pn.Row(pn.Spacer(width=20), margin=(0, 0, 0, 0)),
                                # pn.Row(pn.Spacer(width=20), margin=(0, 0, 0, 0)),
                                pn.Row(pn.Spacer(width=20), progress_start, self.progress_bar, self.info_text[1], align='center', margin=(10, 5, 5, 5))),
                      self.terminal)
                        