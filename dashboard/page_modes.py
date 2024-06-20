import panel as pn
import param
from styles import button_style


class pgModes(param.Parameterized):

    # operator = param.Selector(default='Uploading input files', objects=['Uploading input files', 'Execution'])
    next_page = param.String(default='')
    ready = param.Boolean(default=False)

    def panel(self):

        btn_lite = pn.widgets.Button(name='EVI-DiST Lite', width=200, height=50, button_type='success', align=('center','center'))
        btn_plus = pn.widgets.Button(name='EVI-DiST Plus', width=200, height=50, button_type='primary', align=('center','center'))
        #btn_pro = pn.widgets.Button(name='EVI-DIST Pro', width=200, height=50, button_type='danger', align=('center','center'))

        def on_lite_click(event):
            self.next_page = 'Uploading input files'
            self.ready = True

        def on_plus_click(event):
            pn.state.notifications.warning('Plus version is still under development!', duration=4000)

        btn_lite.on_click(on_lite_click)
        btn_plus.on_click(on_plus_click)


        # btn_lite.on_click(lambda event: setattr(self, 'ready', True) and setattr(self, 'next_page', 'Uploading input files'))
        # btn_plus.on_click(lambda event: setattr(self, 'ready', True) and setattr(self, 'next_page', 'Execution'))
        # btn_pro.on_click(lambda event: setattr(self, 'ready', True) and setattr(self, 'next_page', 'Execution'))

        return pn.Row(
                pn.Column(
                    pn.Spacer(height=25),
                    #pn.Row(btn_lite, pn.widgets.StaticText(value='Service transformer loading evaluation', align=('center','center')), align=('center', 'center')),
                    pn.Row(btn_lite, align=('center', 'center')),
                    pn.Spacer(height=25),
                    #pn.Row(btn_plus, pn.widgets.StaticText(value='OpenDSS grid simulation', align=('center','center')), align=('center', 'center')),
                    pn.Row(btn_plus, align=('center', 'center')),
                    pn.Spacer(height=25), 
                    #pn.Row(btn_pro, pn.widgets.StaticText(value='Pro explanation', align=('center','center')), align=('center', 'center')),
                    #pn.Row(btn_pro, align=('center', 'center')),
                    sizing_mode='stretch_width'
                    ),
                height=300,
                sizing_mode='stretch_width'
            )


        
        