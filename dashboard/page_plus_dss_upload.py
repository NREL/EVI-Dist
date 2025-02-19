import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import panel as pn
import param
from tkinter import Tk, filedialog
from styles import custom_style
from actions import gen_xf_mappings
import pickle

class pgPlusDSSUpload(param.Parameterized):

    file_names = param.Dict()
    months = param.List()
    configs = param.Dict()
    #next_page = param.String(default='')
    #ready = param.Boolean(default=False)
    ready = param.Boolean(default=False)

    @param.output('input_file_names', 'configs', 'months')
    def output(self):
        input_file_names = {'dss_main' : self.filename_texts[0].value,
                           'premise_report' : self.filename_texts[1].value,
                           'adoption_data' : self.filename_texts[2].value}
        sim_name = os.path.basename(self.filename_texts[0].value)
        sim_name, _ = os.path.splitext(sim_name)
        adoption_name = os.path.basename(self.filename_texts[2].value)
        adoption_name, _ = os.path.splitext(adoption_name)
        configs = {'sim_name': sim_name,
                   'adoption': adoption_name}
        return input_file_names, configs, self.months

    def __init__(self):
        super().__init__()

        # self.custom_style = {
        #     "font-size": "12pt",
        # }

        # current_working_directory = os.getcwd()

        self.info_texts = [pn.pane.Markdown("""<b style='font-size:12pt'>Please select main OpenDSS (*.dss) file:</b>
                                               <br>This is the "main" or "master" .dss file that points to all OpenDSS model assets. This file is typically found within the OpenDSS folder along with the other .dss files.</br>""",
                                            width=400),
                           pn.pane.Markdown("""<b style='font-size:12pt'>Please select feeder premise report file:</b>
                                               <br>This file contains columns for Transformer IDs, Premise Numbers, Coordiantes, Regions, and Bank Sizes for the feeder(s) of interest.</br>""",
                                            width=400),
                           pn.pane.Markdown("""<b style='font-size:12pt'>Please select EV adoption scenario for the selected feeder(s):</b>
                                                        <br>This file contains columns such as Veh_ID_Num, start_soc, end_soc, energy_kwh, Premise Number, Transformer ID for the feeder(s) of interest.</br>""",
                                            width=400),
                           ]

        self.file_browse_buttons = [pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100),
                                    pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100),
                                    pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100),
                                    ]

        self.filename_texts = [pn.widgets.StaticText(value="Selected File: ", align=('center','center')),
                               pn.widgets.StaticText(value="Selected File: ", align=('center','center')),
                               pn.widgets.StaticText(value="Selected File: ", align=('center','center')),
                               ]

        self.file_browse_buttons[0].on_click(lambda event, button_index=0: self.select_files(button_index, event, "data/opendss_model"))
        self.file_browse_buttons[1].on_click(lambda event, button_index=1: self.select_files(button_index, event, "data/premise_data"))
        self.file_browse_buttons[2].on_click(lambda event, button_index=2: self.select_files(button_index, event, "data/adoptions"))

        self.progress_bar = pn.widgets.Progress(name='Progress', value=0, width=500, align=('center','center'))
        self.variables = dict()
        self.months = []

        def upload_on_click(event):
            file_name_check = True
            for fn in self.filename_texts:
                print(fn.value)
                if fn.value == 'Selected File: ':
                    print('No pass!')
                    pn.state.notifications.warning('Some input files are not selected!', duration=4000)
                    file_name_check = False
                    break

            if file_name_check:
                file_names = dict()
                file_names['dss_main'] = self.filename_texts[0].value
                file_names['premise_report'] = self.filename_texts[1].value
                file_names['ev_adoption'] = self.filename_texts[2].value

                try:
                    self.variables, self.months[:] = gen_xf_mappings(file_names, self.progress_bar)
                    #TODO: add some file check for the main dss file

                    mappings_directory = EVIDIST_ROOT_PATH + "/data/mappings"
                    if not os.path.exists(mappings_directory):
                        os.makedirs(mappings_directory)

                    mappings_directory = mappings_directory + "/mappings_plus.pkl"
                    print(mappings_directory)
                    with open(mappings_directory, "wb") as f:
                        pickle.dump(self.variables, f)

                    self.ready = True
                    pn.state.notifications.success('Files successfully uploaded!', duration=4000)

                except Exception:
                    pn.state.notifications.error('Files not found! Make sure file paths are correct.', duration=4000)


        self.progress_start_button = pn.widgets.Button(name='Upload selected files', button_type='primary', align=('center','center'))
        self.progress_start_button.on_click(upload_on_click)

        # External callback function
        self.external_callback = None

    def panel(self):

        return pn.Column(
            pn.Row(self.info_texts[0], pn.Spacer(width=20), self.file_browse_buttons[0], self.filename_texts[0]),
            pn.Row(self.info_texts[1], pn.Spacer(width=20), self.file_browse_buttons[1], self.filename_texts[1]),
            pn.Row(self.info_texts[2], pn.Spacer(width=20), self.file_browse_buttons[2], self.filename_texts[2]),
            pn.Row(self.progress_bar, self.progress_start_button)
        )

    def select_files(self, button_index, event, initial_dir: str):
        root = Tk()
        root.withdraw()
        root.call('wm', 'attributes', '.', '-topmost', True)
        initial_dir_path = EVIDIST_ROOT_PATH + "/" + initial_dir
        file_name = filedialog.askopenfilename(multiple=False, initialdir=initial_dir_path)
        if file_name == "":
            file_name = "Selected File: "
        self.filename_texts[button_index].value = file_name
        return file_name
