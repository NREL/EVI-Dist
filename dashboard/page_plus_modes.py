import panel as pn
import param
from styles import button_style


class pgPlusModes(param.Parameterized):

    # operator = param.Selector(default='Uploading input files', objects=['Uploading input files', 'Execution'])
    next_page = param.String(default='')
    ready = param.Boolean(default=False)

    def panel(self):

        btn_lite = pn.widgets.Button(name='Run sim from scratch', width=200, height=50, button_type='success', align=('center','center'))
        btn_loadsession = pn.widgets.Button(name='Load saved simulation files', width=200, height=50, button_type='primary', align=('center','center'))

        def on_lite_click(event):
            self.next_page = 'Plus: upload DSS file'
            self.ready = True
            
        def on_load_session_click(event):
            self.next_page = 'Plus: load session'
            self.ready = True

        btn_lite.on_click(on_lite_click)
        btn_loadsession.on_click(on_load_session_click)

        return pn.Row(
                pn.Column(
                    pn.Spacer(height=25),
                    pn.Row(btn_lite, align=('center', 'center')),
                    pn.Spacer(height=25),
                    pn.Row(btn_loadsession, align=('center', 'center')),
                    sizing_mode='stretch_width'
                    ),
                height=300,
                sizing_mode='stretch_width'
            )


        
        