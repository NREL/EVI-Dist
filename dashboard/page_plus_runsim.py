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
from actions import DataOperatorPlus

from modules.simulation_plus import SimPlus
from dashboard.version_info import version_name

pn.extension('terminal')

class pgPlusRunSim(param.Parameterized):

    input_file_names = param.Dict()
    configs = param.Dict()

    ready = param.Boolean(default=False)

    @param.output('input_file_names', 'output_file_names', 'configs')
    def output(self):
        input_file_names = {'dss_main' : self.input_file_names['dss_main']}
        input_file_names['premise_report'] = self.input_file_names['premise_report']
        input_file_names['adoption_data'] = self.input_file_names['adoption_data']
        output_file_names = dict()
        output_file_names['evloads'] = f'sim_plus_evloads.csv'
        output_file_names['linecurrents'] = f'sim_plus_linecurrents.csv'
        output_file_names['linedata'] = f'sim_plus_linedata.csv'
        output_file_names['trnscurrents'] = f'sim_plus_trnscurrents.csv'
        output_file_names['trnskva'] = f'sim_plus_trnskva.csv'
        output_file_names['trnskva_ratings'] = f'sim_plus_trnskva_ratings.csv'
        output_file_names['voltages'] = f'sim_plus_voltages.csv'
        output_file_names['bus_info'] = f'sim_plus_businfo.csv'
        output_file_names['charge_events'] = f'sim_plus_charge_event_data.csv'
        output_file_names['trns_premise_ev_mapping'] = f'sim_plus_trns_premise_ev_mapping.pkl'
        output_file_names['ev_charge_stats'] = f'sim_plus_ev_charge_stats.csv'
        configs = {"sim_name": self.configs["sim_name"]}
        configs['feeder'] = self.configs['feeder']
        configs['controller'] = self.configs['controller']
        configs['adoption'] = self.configs['adoption']
        configs['month'] = self.configs['month']
        configs['day_of_week'] = self.configs['day_of_week']
        return input_file_names, output_file_names, configs

    def __init__(self, **params):
        super().__init__(**params)
        # print(self.file_names)
        # print(self.configs)
        self.progress_bar = pn.widgets.Progress(name='Progress', value=0, width=300, align=('center','center'))
        self.simulation_description = pn.pane.Markdown(f"""
            ## Simulation Configuration Summary
            - Name: <b>{self.configs["sim_name"]}</b>
            - Feeder: <b>{self.configs["feeder"]}</b>
            - EV charging controller: <b>{self.configs["controller"]}</b>
            - Simulated month: <b>{self.configs["month"]}</b>
            - Simulated day of week: <b>{self.configs["day_of_week"]}</b>
            """,
            height=200)
        self.info_text = [pn.pane.Markdown("Execution progress", styles=custom_style, align=('center','center')),
                          pn.pane.Markdown("0%", width=50, styles=custom_style, align=('center','center'))]
        self.pb = tqdm(total=100)
        #self.tqdm_progress = Tqdm(align=('center','center'), width=300)

        ########################### THIS VERSION SHOULD BE READ OFF OF A FILE #############################
        self.terminal = pn.widgets.Terminal(f"EVI-DiST (v{version_name})\nSimulation terminal\n==================================\n",

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

        async def update_progress_bar1(progress_queue):
            while True:
                s = await progress_queue.get()  # Get the latest progress value from the queue
                self.progress_bar.value = int(s)
                self.info_text[1].object = f"{int(s)}%"
                self.pb.n = s
                self.pb.refresh()
                #self.tqdm_progress.value = int(s)
                if s >= 60:
                    # self.ready = True
                    break

        async def update_progress_bar2(progress_queue):
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


            # self.configs["month"] = 1 #TODO: make this an option to select in the GUI
            # self.configs["day_of_week"] = 1 #TODO: make this an option to select in the GUI

            progress = [0]
            sim = SimPlus(sim_name=self.configs["sim_name"],
                          feeder_name=self.configs["feeder"],
                          main_dss_file=self.input_file_names["dss_main"],
                          ev_adoption_file=self.input_file_names["adoption_data"],
                          premise_data_file=self.input_file_names["premise_report"],
                          controller_name=self.configs["controller"],
                          month=self.configs["month"],
                          day_of_week=self.configs["day_of_week"],
                          sim_start_time=6*3600,
                          sim_end_time=30*3600,
                          )

            await asyncio.gather(
                sim.run(progress, progress_queue),
                update_progress_bar1(progress_queue)
            )

            output_file_names = dict()
            output_file_names['evloads'] = f'sim_plus_evloads.csv'
            output_file_names['linecurrents'] = f'sim_plus_linecurrents.csv'
            output_file_names['linedata'] = f'sim_plus_linedata.csv'
            output_file_names['trnscurrents'] = f'sim_plus_trnscurrents.csv'
            output_file_names['trnskva'] = f'sim_plus_trnskva.csv'
            output_file_names['trnskva_ratings'] = f'sim_plus_trnskva_ratings.csv'
            output_file_names['voltages'] = f'sim_plus_voltages.csv'
            output_file_names['bus_info'] = f'sim_plus_businfo.csv'
            output_file_names['charge_events'] = f'sim_plus_charge_event_data.csv'
            output_file_names['trns_premise_ev_mapping'] = f'sim_plus_trns_premise_ev_mapping.pkl'
            output_file_names['ev_charge_stats'] = f'sim_plus_ev_charge_stats.csv'

            dop = DataOperatorPlus(output_file_names, self.configs["controller"])
            await asyncio.gather(
                dop.load_data(progress, progress_queue),
                update_progress_bar2(progress_queue)
            )
            pn.state.dop = dop


        progress_start = pn.widgets.Button(name='Start simulation', button_type='success', align=('center','center'))
        progress_start.on_click(run_async)

        return pn.Row(pn.Column(self.simulation_description,
                                pn.Row(pn.Spacer(width=20), margin=(0, 0, 0, 0)),
                                pn.Row(pn.Spacer(width=20), progress_start, self.progress_bar, self.info_text[1], align='center', margin=(0, 0, 0, 0))),
                      self.terminal)
