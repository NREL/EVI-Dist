import panel as pn
import param
from tkinter import Tk, filedialog
from styles import custom_style
from actions import gen_xf_mappings
import os
import pickle
import sys
import json
import io
import zipfile

parent_directory = os.getcwd()

sys.path.append(parent_directory + "/modules")
sys.path.append(parent_directory)

class pgLoadSession(param.Parameterized):
    
    @param.output('file_names','configs')
    def output(self):
        # self.file_names = {'dss_main' : self.filename_texts[0].value}
        return self.file_names, self.configs

    def __init__(self):
        super().__init__()

        self.info_texts = [pn.pane.Markdown("""<b style='font-size:12pt'>Please select the Lite session (*.zip) file:</b>
                                               <br>This file contains ...</br>""",
                                            width=400)
                           ]
        
        self.file_browse_buttons = [pn.widgets.Button(name='Browse', align=('center','center'), button_type='success', width=100)]
        
        self.filename_texts = [pn.widgets.StaticText(value="Selected File: ", align=('center','center'))]
        
        self.file_browse_buttons[0].on_click(lambda event, button_index=0: self.select_files(button_index, event))

        self.progress_bar = pn.widgets.Progress(name='Progress', value=0, width=500, align=('center','center'))
        self.saved_session_file_name = ""
        self.file_names = param.Dict()
        self.configs = param.Dict()

        self.progress_start_button = pn.widgets.Button(name='Upload selected files', button_type='primary', align=('center','center'))
        self.progress_start_button.on_click(self.upload_on_click)

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
    
    def upload_on_click(self,event):
        file_name_check = True
        for fn in self.filename_texts:
            print(fn.value)
            if fn.value == 'Selected File: ':
                print('No pass!')
                pn.state.notifications.warning('Some input files are not selected!', duration=4000)
                file_name_check = False
                break
        
        if file_name_check:
            try:
                self.unzip_and_save(self.filename_texts[0].value)
                # self.load_saved_session()
                self.ready = True    
                pn.state.notifications.success('Files successfully uploaded!', duration=4000)
                
            except Exception:
                pn.state.notifications.error('Files not found! Make sure file paths are correct.', duration=4000)
    
    def load_saved_session(self):
        
        with open(self.filename_texts[0].value, "r") as json_file:
            data_dict = json.load(json_file)
        
            data_dict["configs"]["month"] = int(data_dict["configs"]["month"])
            
            self.file_names = data_dict["file_names"]
            self.configs = data_dict["configs"]
            

    def unzip_and_save(self, zip_filepath):
        """Unzips the contents of a zip file, handling JSON and CSV files differently.
        """
        
        temp_directory = parent_directory + "/data/temp/"
        mappings_directory = parent_directory + "/data/mappings/"

        # Open the zip file in binary read mode ("rb")
        with open(zip_filepath, "rb") as f:
            zip_data = f.read() # Read the contents of the file into memory
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for file_info in zf.infolist():
                if not file_info.is_dir():
                    filename = file_info.filename
                    file_data = zf.read(filename)

                    if filename.endswith(".json"):
                        json_data = json.loads(file_data)
                        json_data["configs"]["month"] = int(json_data["configs"]["month"])
            
                        self.file_names = json_data["file_names"]
                        self.configs = json_data["configs"]
                    elif filename.endswith(".csv"):
                        # Save CSV files to the target directory
                        file_path = os.path.join(temp_directory, filename)
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        with open(file_path, "wb") as f:
                            f.write(file_data)
                    elif filename.endswith(".pkl"):
                        # Save pkl files to the target directory
                        file_path = os.path.join(mappings_directory, filename)
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        with open(file_path, "wb") as f:
                            f.write(file_data)
                    else:
                        print(f"Unsupported file type: {filename}")  # Optional
