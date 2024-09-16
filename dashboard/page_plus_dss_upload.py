import panel as pn
import param
from tkinter import Tk, filedialog
from styles import custom_style
from actions import gen_xf_mappings
import os
import pickle

class pgPlusDSSUpload(param.Parameterized):

    file_names = param.Dict()
    months = param.List()
    configs = param.Dict()
    #next_page = param.String(default='')
    #ready = param.Boolean(default=False)
    ready = param.Boolean(default=False)
    
    @param.output('file_names', 'configs')
    def output(self):
        self.file_names = {'dss_main' : self.filename_texts[0].value}
        sim_name = os.path.basename(self.filename_texts[0].value)
        sim_name, _ = os.path.splitext(sim_name)
        self.configs = {'sim_name': sim_name}
        return self.file_names, self.configs

    def __init__(self):
        super().__init__()

        # self.custom_style = {
        #     "font-size": "12pt",
        # }

        current_working_directory = os.getcwd()

        self.info_texts = [pn.pane.Markdown("""<b style='font-size:12pt'>Please select main OpenDSS (*.dss) file:</b>
                                               <br>This file contains ...</br>""",
                                            width=400)
                           ]
        
        self.file_browse_buttons = [pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100)]
        
        self.filename_texts = [pn.widgets.StaticText(value="Selected File: ", align=('center','center'))]
        
        self.file_browse_buttons[0].on_click(lambda event, button_index=0: self.select_files(button_index, event))

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

                try:
                    #TODO: add some file check for the main dss file

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
        