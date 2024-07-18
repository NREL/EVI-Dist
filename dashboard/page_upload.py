import panel as pn
import param
from tkinter import Tk, filedialog
from styles import custom_style
from actions import gen_xf_mappings
import os
import pickle

class pgUpload(param.Parameterized):

    file_names = param.Dict()
    months = param.List()
    #next_page = param.String(default='')
    #ready = param.Boolean(default=False)
    ready = param.Boolean(default=False)
    
    @param.output('file_names', 'months')
    def output(self):
        # self.file_names = [v.value for v in self.filename_texts]
        self.file_names = {'premise_report' : self.filename_texts[0].value,
                           'ev_adoption' : self.filename_texts[1].value}
        #self.months = [v.value for v in self.filename_texts]  # This line depends on your actual use case
        return self.file_names, self.months

    def __init__(self):
        super().__init__()

        # self.custom_style = {
        #     "font-size": "12pt",
        # }

        current_working_directory = os.getcwd()

        self.info_texts = [pn.pane.Markdown("""<b style='font-size:12pt'>Please select feeder premise report file:</b>
                                               <br>This file contains columns for Transformer IDs, Premise Numbers, Coordiantes, Regions, and Bank Sizes for the feeder(s) of interest.</br>""",
                                            width=400),
                           pn.pane.Markdown("""<b style='font-size:12pt'>Please select EV adoption scenario for the selected feeder(s):</b>
                                                        <br>This file contains columns such as Veh_ID_Num, start_soc, end_soc, energy_kwh, Premise Number, Transformer ID for the feeder(s) of interest.</br>""",
                                            width=400)]
                        #    pn.pane.Markdown("""<b style='font-size:12pt'>Please select the AMI dataset file (if any) for the selected feeder:</b>
                        #                             <br>This file contains columns representing  </br>""",
                        #                     width=400)]
        
        self.file_browse_buttons = [pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100),
                                    pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100)]
        
        self.filename_texts = [pn.widgets.StaticText(value="Selected File: ", align=('center','center')),
                               pn.widgets.StaticText(value="Selected File: ", align=('center','center'))]
        
        self.file_browse_buttons[0].on_click(lambda event, button_index=0: self.select_files(button_index, event))
        self.file_browse_buttons[1].on_click(lambda event, button_index=1: self.select_files(button_index, event))

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
                file_names['premise_report'] = self.filename_texts[0].value
                file_names['ev_adoption'] = self.filename_texts[1].value

                try:
                    self.variables, self.months[:] = gen_xf_mappings(file_names, self.progress_bar)
                     
                    #print(type(self.months))
                    # We can have another error if the uploaded file are not compatible 
                    # This can be either embedded in the function or using some sort of return value

                    current_directory = os.getcwd()
                    parent_directory = os.path.dirname(current_directory)

                    mappings_directory = current_directory + "/data/mappings"
                    if not os.path.exists(mappings_directory):
                        os.makedirs(mappings_directory)

                    mappings_directory = mappings_directory + "/mappings.pkl"
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
            pn.Row(self.progress_bar, self.progress_start_button)
        )
    
    def select_files(self, button_index, event):
        root = Tk()
        root.withdraw()                                        
        root.call('wm', 'attributes', '.', '-topmost', True)   
        file_name = filedialog.askopenfilename(multiple=False)    
        if file_name == "":
            file_name = "Selected File: "
        self.filename_texts[button_index].value = file_name
        return file_name 
        