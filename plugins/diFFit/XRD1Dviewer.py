#!/usr/bin/env pythonw
'''
GUI for displaying 1D XRD images

'''

import os
import numpy as np
from scipy import constants

#import h5py
import matplotlib.cm as colormap

import wx

#from wxmplot.imagepanel import ImagePanel
from wxmplot import PlotPanel
from wxutils import MenuItem

from larch_plugins.io import tifffile
from larch_plugins.diFFit.XRDCalculations import fabioOPEN,integrate_xrd,xy_file_reader
from larch_plugins.diFFit.ImageControlsFrame import ImageToolboxFrame
from larch_plugins.diFFit.XRDCalibrationFrame import CalibrationPopup

import matplotlib.pyplot as plt

HAS_pyFAI = False
try:
    import pyFAI
    import pyFAI.calibrant
    from pyFAI.calibration import Calibration
    HAS_pyFAI = True
except ImportError:
    pass


###################################

VERSION = '0 (18-October-2016)'
SLIDER_SCALE = 1000. ## sliders step in unit 1. this scales to 0.001

###################################

class Viewer1DXRD(wx.Frame):
    '''
    Frame for housing all 1D XRD viewer widgets
    '''
    def __init__(self, data):
        
        label = 'diFFit.py : 1D XRD Viewer'
        wx.Frame.__init__(self, None, -1,title=label, size=(1500, 600))
        
        self.SetMinSize((700,500))
        
        self.statusbar = self.CreateStatusBar(3,wx.CAPTION )

        ## Default information
        self.data_name    = []
        self.xy_data      = []
        self.xy_plot      = []
        self.plotted_data = []

        self.XRD1DMenuBar()
        self.Panel1DViewer()
        
        self.Centre()
        self.Show(True)

        try:
            self.add1Ddata(*data)
        except:
            pass
            
     
        ## Set defaults for plotting        
        self.plot1D.cursor_mode = 'zoom'
#         self.plot1D.xlabel = self.ch_xaxis.GetString(self.ch_xaxis.GetSelection())
#         print self.ch_xaxis.GetString(self.ch_xaxis.GetSelection())
#         self.plot1D.conf.yaxis = 'Intensity (a.u.)'


    def write_message(self, s, panel=0):
        '''write a message to the Status Bar'''
        self.SetStatusText(s, panel)


##############################################
#### PANEL DEFINITIONS
    def XRD1DMenuBar(self):

        menubar = wx.MenuBar()
        
        ###########################
        ## diFFit1D
        diFFitMenu = wx.Menu()
        
        MenuItem(self, diFFitMenu, '&Open diffration image', '', None)
        MenuItem(self, diFFitMenu, 'Sa&ve displayed image to file', '', None)
        MenuItem(self, diFFitMenu, '&Save settings', '', None)
        MenuItem(self, diFFitMenu, '&Load settings', '', None)
        MenuItem(self, diFFitMenu, '&Add analysis to map file', '', None)
       
        menubar.Append(diFFitMenu, '&diFFit1D')

        ###########################
        ## Process
        ProcessMenu = wx.Menu()
        
        MenuItem(self, ProcessMenu, '&Load mask file', '', None)
        MenuItem(self, ProcessMenu, '&Remove current mask', '', None)
        MenuItem(self, ProcessMenu, '&Create mask', '', None)
        MenuItem(self, ProcessMenu, 'Load &background image', '', None)
        MenuItem(self, ProcessMenu, '&Remove current background image', '', None)
        
        menubar.Append(ProcessMenu, '&Process')

        ###########################
        ## Analyze
        AnalyzeMenu = wx.Menu()
        
        MenuItem(self, AnalyzeMenu, '&Calibrate', '', None)
        MenuItem(self, AnalyzeMenu, '&Load calibration file', '', None)
        MenuItem(self, AnalyzeMenu, '&Show current calibration', '', None)
        AnalyzeMenu.AppendSeparator()
        MenuItem(self, AnalyzeMenu, '&Integrate (open 1D viewer)', '', None)

        menubar.Append(AnalyzeMenu, '&Analyze')

        ###########################
        ## Create Menu Bar
        self.SetMenuBar(menubar)

    def Panel1DViewer(self):
        '''
        Frame for housing all 1D XRD viewer widgets
        '''
        self.panel = wx.Panel(self)

        leftside  = self.LeftSidePanel(self.panel)
        rightside = self.RightSidePanel(self.panel)        

        panel1D = wx.BoxSizer(wx.HORIZONTAL)
        panel1D.Add(leftside,flag=wx.ALL,border=10)
        panel1D.Add(rightside,proportion=1,flag=wx.EXPAND|wx.ALL,border=10)

        self.panel.SetSizer(panel1D)
    
    def Toolbox(self,panel):
        '''
        Frame for visual toolbox
        '''
        
        tlbx = wx.StaticBox(self.panel,label='PLOT TOOLBOX')#, size=(200, 200))
        vbox = wx.StaticBoxSizer(tlbx,wx.VERTICAL)

        ###########################
        ## X-Scale
        hbox_xaxis = wx.BoxSizer(wx.HORIZONTAL)
        self.ttl_xaxis = wx.StaticText(self.panel, label='X-SCALE')
        xunits = ['q (A^-1)',u'2\u03B8','d (A)'] ## \u212B
        self.ch_xaxis = wx.Choice(self.panel,choices=xunits)

        self.ch_xaxis.Bind(wx.EVT_CHOICE, self.onCHANGEx)
    
        hbox_xaxis.Add(self.ttl_xaxis, flag=wx.RIGHT, border=8)
        hbox_xaxis.Add(self.ch_xaxis, flag=wx.EXPAND, border=8)
        vbox.Add(hbox_xaxis, flag=wx.ALL, border=10)

        ###########################
        ## Y-Scale
        hbox_yaxis = wx.BoxSizer(wx.HORIZONTAL)
        self.ttl_yaxis = wx.StaticText(self.panel, label='Y-SCALE')
        yscales = ['linear','log']
        self.ch_yaxis = wx.Choice(self.panel,choices=yscales)

        self.ch_yaxis.Bind(wx.EVT_CHOICE,   None)
    
        hbox_yaxis.Add(self.ttl_yaxis, flag=wx.RIGHT, border=8)
        hbox_yaxis.Add(self.ch_yaxis, flag=wx.EXPAND, border=8)
        vbox.Add(hbox_yaxis, flag=wx.ALL, border=10)
        
        return vbox

    def DataBox(self,panel):
        '''
        Frame for visual toolbox
        '''
        
        tlbx = wx.StaticBox(self.panel,label='DATA TOOLBOX')#, size=(200, 200))
        vbox = wx.StaticBoxSizer(tlbx,wx.VERTICAL)


        ###########################
        ## DATA CHOICE

        self.ch_data = wx.Choice(self.panel,choices=self.data_name)
        self.ch_data.Bind(wx.EVT_CHOICE,   self.onSELECT)
        vbox.Add(self.ch_data, flag=wx.EXPAND|wx.ALL, border=8)
    
        self.ttl_data = wx.StaticText(self.panel, label='')
        vbox.Add(self.ttl_data, flag=wx.EXPAND|wx.ALL, border=8)

        ###########################

        self.ck_bkgd = wx.CheckBox(self.panel,label='BACKGROUND')
        self.ck_smth = wx.CheckBox(self.panel,label='SMOOTHING')
        
        self.ck_bkgd.Bind(wx.EVT_CHECKBOX,   None)
        self.ck_smth.Bind(wx.EVT_CHECKBOX,   None)

        vbox.Add(self.ck_bkgd, flag=wx.ALL, border=8)
        vbox.Add(self.ck_smth, flag=wx.ALL, border=8)
    
        ###########################
        ## Scale
        hbox_scl1 = wx.BoxSizer(wx.HORIZONTAL)
        self.ttl_scl = wx.StaticText(self.panel, label='Y-SCALING')
        self.sldr_scl = wx.Slider(self.panel)
        self.sldr_scl.Bind(wx.EVT_SLIDER,   None)                

        hbox_scl1.Add(self.ttl_scl, flag=wx.RIGHT, border=8)
        hbox_scl1.Add(self.sldr_scl, flag=wx.RIGHT, border=8)

        vbox.Add(hbox_scl1, flag=wx.BOTTOM|wx.TOP, border=8)

        hbox_scl2 = wx.BoxSizer(wx.HORIZONTAL)
        self.entr_scale = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        self.btn_scale = wx.Button(self.panel,label='set scale')

        self.btn_scale.Bind(wx.EVT_BUTTON,   None)

        hbox_scl2.Add(self.btn_scale, flag=wx.RIGHT, border=8)
        hbox_scl2.Add(self.entr_scale, flag=wx.RIGHT, border=8)

        vbox.Add(hbox_scl2, flag=wx.BOTTOM, border=10)

        ###########################
        ## Hide/show and reset
        hbox_btns = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_hide  = wx.Button(self.panel,label='hide')
        self.btn_reset = wx.Button(self.panel,label='reset')
        self.btn_rmv   = wx.Button(self.panel,label='remove')
        
        self.btn_hide.Bind(wx.EVT_BUTTON,  self.hide1Ddata)
        self.btn_reset.Bind(wx.EVT_BUTTON, None)
        self.btn_rmv.Bind(wx.EVT_BUTTON,   self.remove1Ddata)
        
        hbox_btns.Add(self.btn_hide,  flag=wx.ALL, border=10)
        hbox_btns.Add(self.btn_reset, flag=wx.ALL, border=10)
        hbox_btns.Add(self.btn_rmv,   flag=wx.ALL, border=10)
        vbox.Add(hbox_btns, flag=wx.ALL, border=10)
               
        return vbox    

    def RightSidePanel(self,panel):
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.plot1DXRD(panel)
        vbox.Add(self.plot1D,proportion=1,flag=wx.ALL|wx.EXPAND,border = 10)

        return vbox

    def LeftSidePanel(self,panel):
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        plttools = self.Toolbox(self.panel)
        
        self.btn_data = wx.Button(panel,label='ADD NEW DATA SET')
        self.btn_data.Bind(wx.EVT_BUTTON, self.loadXYFILE)
        
        dattools = self.DataBox(self.panel)
        
        vbox.Add(plttools,flag=wx.ALL,border=10)
        vbox.Add(self.btn_data, flag=wx.ALL, border=12)
        vbox.Add(dattools,flag=wx.ALL,border=10)
        

        return vbox



##############################################
#### XRD PLOTTING FUNCTIONS
    def plot1DXRD(self,panel):
    
        self.plot1D = PlotPanel(panel,size=(1000, 500))
        self.plot1D.messenger = self.write_message
  
         ## trying to get this functionality into our gui
        ## mkak 2016.11.10      
#         interactive_legend().show()

        
    def add1Ddata(self,x,y,name=None):
        
        plt_no = (len(self.xy_data)/2)
        if name is None:
            name = 'dataset %i' % plt_no

        self.data_name.append(name)
        self.xy_data.extend([x,y])
        self.xy_plot.extend([x,y])
        self.plotted_data.append(self.plot1D.oplot(x,y,label=name,show_legend=True))

        self.ch_data.Set(self.data_name)
        self.ch_data.SetStringSelection(name)
        self.onSELECT(None)

    def remove1Ddata(self,event):
        
        ## Needs pop up warning: "Do you really want to delete this data set from plotter?
        ## Current settings will not be saved."
        ## mkak 2016.11.10
        
        plt_no = self.ch_data.GetSelection()        
        print 'trying to DELETE plot number: %i' % plt_no
        print '\t',self.data_name[plt_no]

        ## removing name from list works... do not activate till rest is working
        ## mkak 2016.11.10
#         self.data_name.remove(self.data_name[plt_no])
#         self.ch_data.Set(self.data_name)

    def hide1Ddata(self,event):

        plt_no = self.ch_data.GetSelection()        
        print 'trying to hide plot number: %i' % plt_no
        print '\t',self.data_name[plt_no]

    def onSELECT(self,event):
    
        data_str = self.ch_data.GetString(self.ch_data.GetSelection())
        self.ttl_data.SetLabel('SELECTED: %s' % data_str)

    def onCHANGEx(self, event):
        
        print 'changed x-axis...'

#         q,I = self.xrd.data1D
# 
#         if event is not None:
#             if 0 == event.GetInt():
#                 ## q in units 1/A
#                 self.xunit = 'q'
#                 self.xlabel = 'q (1/A)'
#                 x = q
#             elif 1 == event.GetInt():
#                 ## d in units A
#                 self.xunit = '2th'
#                 self.xlabel = r'$2\Theta$'+r' $(^\circ)$'
#                 x = calc_q_to_2th(q,self.xrd.wavelength*1e10)
#             elif 2 == event.GetInt():
#                 ## d in units A
#                 self.xunit = 'd'
#                 self.xlabel = 'd (A)'
#                 x = calc_q_to_d(q)
#         
#         self.plot1d([x,I])
# 
#         if self.xrd2 is not None:
#             self.oplot1D([x,I])

##############################################
#### XRD FILE OPENING/SAVING 
    def loadXYFILE(self,event):
    
        wildcards = 'XRD data file (*.xy)|*.xy|All files (*.*)|*.*'
        dlg = wx.FileDialog(self, message='Choose 1D XRD data file',
                           defaultDir=os.getcwd(),
                           wildcard=wildcards, style=wx.FD_OPEN)

        path, read = None, False
        if dlg.ShowModal() == wx.ID_OK:
            read = True
            path = dlg.GetPath().replace('\\', '/')
        dlg.Destroy()
        
        if read:
            x,y = xy_file_reader(path)

            self.add1Ddata(x,y,name=os.path.split(path)[-1])

            str_msg = 'Adding data: %s' % os.path.split(path)[-1]
            self.write_message(str_msg,panel=0)

    def saveXYFILE(self,event):
        wildcards = 'XRD data file (*.xy)|*.xy|All files (*.*)|*.*'
        dlg = wx.FileDialog(self, 'Save data as...',
                           defaultDir=os.getcwd(),
                           wildcard=wildcards,
                           style=wx.SAVE|wx.OVERWRITE_PROMPT)

        path, save = None, False
        if dlg.ShowModal() == wx.ID_OK:
            save = True
            path = dlg.GetPath().replace('\\', '/')
        dlg.Destroy()
        
        if save:
            
            print 'need to write something to save data - like pyFAI does?'


def interactive_legend(ax=None):
    if ax is None:
        ax = plt.gca()
    if ax.legend_ is None:
        ax.legend()

    return InteractiveLegend(ax.legend_)

class InteractiveLegend(object):
    def __init__(self, legend):
        self.legend = legend
        self.fig = legend.axes.figure

        self.lookup_artist, self.lookup_handle = self._build_lookups(legend)
        self._setup_connections()

        self.update()

    def _setup_connections(self):
        for artist in self.legend.texts + self.legend.legendHandles:
            artist.set_picker(10) # 10 points tolerance

        self.fig.canvas.mpl_connect('pick_event', self.on_pick)
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)

    def _build_lookups(self, legend):
        labels = [t.get_text() for t in legend.texts]
        handles = legend.legendHandles
        label2handle = dict(zip(labels, handles))
        handle2text = dict(zip(handles, legend.texts))

        lookup_artist = {}
        lookup_handle = {}
        for artist in legend.axes.get_children():
            if artist.get_label() in labels:
                handle = label2handle[artist.get_label()]
                lookup_handle[artist] = handle
                lookup_artist[handle] = artist
                lookup_artist[handle2text[handle]] = artist

        lookup_handle.update(zip(handles, handles))
        lookup_handle.update(zip(legend.texts, handles))

        return lookup_artist, lookup_handle

    def on_pick(self, event):
        handle = event.artist
        if handle in self.lookup_artist:
            artist = self.lookup_artist[handle]
            artist.set_visible(not artist.get_visible())
            self.update()

    def on_click(self, event):
        if event.button == 3:
            visible = False
        elif event.button == 2:
            visible = True
        else:
            return

        for artist in self.lookup_artist.values():
            artist.set_visible(visible)
        self.update()

    def update(self):
        for artist in self.lookup_artist.values():
            handle = self.lookup_handle[artist]
            if artist.get_visible():
                handle.set_visible(True)
            else:
                handle.set_visible(False)
        self.fig.canvas.draw()

    def show(self):
        plt.show()


##### Pop-up from 2D XRD Viewer to calculate 1D pattern
class Calc1DPopup(wx.Dialog):
    def __init__(self,xrd2Ddata,ai,mask=None):
    
        """Constructor"""
        dialog = wx.Dialog.__init__(self, None, title='Calculate 1DXRD options',
                                    style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER,
                                    size = (210,410))
        
       
        self.mask = mask
        self.data2D = xrd2Ddata
        self.ai = ai
        

        self.Init()
        self.setDefaults()
        
        ## Set defaults
        self.wedges.SetValue('1')
        

    def Init(self):
    
        self.panel = wx.Panel(self)

        mainsizer = wx.BoxSizer(wx.VERTICAL)
        
        ## Mask 
        self.ch_mask = wx.CheckBox(self.panel, label='APPLY CURRENT MASK?')
        self.ch_mask.Bind(wx.EVT_CHECKBOX,None)
        
        mainsizer.Add(self.ch_mask,flag=wx.ALL,border=8)
        if self.mask == None:
            self.ch_mask.Disable()
        
        ## Azimutal wedges 
        wedgesizer = wx.BoxSizer(wx.VERTICAL)

        ttl_wedges = wx.StaticText(self.panel, label='AZIMUTHAL WEDGES')
        
        wsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.wedges = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        self.wedge_arrow = wx.SpinButton(self.panel, style=wx.SP_VERTICAL|wx.SP_ARROW_KEYS|wx.SP_WRAP)
       
        self.wedge_arrow.Bind(wx.EVT_SPIN, self.OnSpin)
        
        wsizer.Add(self.wedges,flag=wx.RIGHT,border=8)
        wsizer.Add(self.wedge_arrow,flag=wx.RIGHT,border=8)
        
        wedgesizer.Add(ttl_wedges,flag=wx.BOTTOM,border=8)
        wedgesizer.Add(wsizer,flag=wx.BOTTOM,border=8)

        mainsizer.Add(wedgesizer,flag=wx.ALL,border=8)

        ## Y-Range
        ysizer = wx.BoxSizer(wx.VERTICAL)
        
        ttl_yrange = wx.StaticText(self.panel, label='Y-RANGE (a.u.)')
                
        yminsizer = wx.BoxSizer(wx.HORIZONTAL)
        ttl_ymin = wx.StaticText(self.panel, label='minimum')
        self.ymin = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        yminsizer.Add(ttl_ymin,  flag=wx.RIGHT, border=5)        
        yminsizer.Add(self.ymin,  flag=wx.RIGHT, border=5)        
        
        ymaxsizer = wx.BoxSizer(wx.HORIZONTAL)
        ttl_ymax = wx.StaticText(self.panel, label='maximum')
        self.ymax = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        ymaxsizer.Add(ttl_ymax,  flag=wx.RIGHT, border=5)        
        ymaxsizer.Add(self.ymax,  flag=wx.RIGHT, border=5)

        ysizer.Add(ttl_yrange,  flag=wx.BOTTOM, border=5)        
        ysizer.Add(yminsizer,  flag=wx.BOTTOM, border=5)
        ysizer.Add(ymaxsizer,  flag=wx.BOTTOM, border=5)
        mainsizer.Add(ysizer,  flag=wx.ALL, border=5)


        ## X-Range
        xsizer = wx.BoxSizer(wx.VERTICAL)
        
        ttl_xrange = wx.StaticText(self.panel, label='X-RANGE')
        
        xunitsizer = wx.BoxSizer(wx.HORIZONTAL)
        xunits = ['q (A^-1)',u'2\u03B8','d (A)'] ## \u212B
        ttl_xunit = wx.StaticText(self.panel, label='units')
        self.ch_xunit = wx.Choice(self.panel,choices=xunits)
        self.ch_xunit.Bind(wx.EVT_CHOICE,self.onUnits)
        
        xunitsizer.Add(ttl_xunit, flag=wx.RIGHT, border=5)
        xunitsizer.Add(self.ch_xunit, flag=wx.RIGHT, border=5)

        xstepsizer = wx.BoxSizer(wx.HORIZONTAL)
        ttl_xstep = wx.StaticText(self.panel, label='steps')
        self.xstep = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        xstepsizer.Add(ttl_xstep,  flag=wx.RIGHT, border=5)
        xstepsizer.Add(self.xstep,  flag=wx.RIGHT, border=5)
                        
        xminsizer = wx.BoxSizer(wx.HORIZONTAL)
        ttl_xmin = wx.StaticText(self.panel, label='minimum')
        self.xmin = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        xminsizer.Add(ttl_xmin,  flag=wx.RIGHT, border=5)
        xminsizer.Add(self.xmin,  flag=wx.RIGHT, border=5)
        
        xmaxsizer = wx.BoxSizer(wx.HORIZONTAL)
        ttl_xmax = wx.StaticText(self.panel, label='maximum')
        self.xmax = wx.TextCtrl(self.panel,wx.TE_PROCESS_ENTER)
        xmaxsizer.Add(ttl_xmax,  flag=wx.RIGHT, border=5)        
        xmaxsizer.Add(self.xmax,  flag=wx.RIGHT, border=5)

        xsizer.Add(ttl_xrange,  flag=wx.BOTTOM, border=5)
        xsizer.Add(xunitsizer, flag=wx.ALL, border=5)
        xsizer.Add(xstepsizer, flag=wx.ALL, border=5)
        xsizer.Add(xminsizer,  flag=wx.BOTTOM, border=5)
        xsizer.Add(xmaxsizer,  flag=wx.BOTTOM, border=5)
        mainsizer.Add(xsizer,  flag=wx.ALL, border=5)

        ## Okay Buttons
#         btn_cncl = wx.Button(self.panel, wx.CANCEL)
        btn_save = wx.Button(self.panel, label = 'Save 1D')
        btn_plot  = wx.Button(self.panel, label = 'Plot 1D')

        btn_save.Bind(wx.EVT_BUTTON,self.onSAVE)
        btn_plot.Bind(wx.EVT_BUTTON,self.onPLOT)
#         btn_cncl.SetLabel('Close')

        minisizer = wx.BoxSizer(wx.HORIZONTAL)
#         minisizer.Add(btn_cncl,  flag=wx.RIGHT, border=5)
        minisizer.Add(btn_save,  flag=wx.RIGHT, border=5)
        minisizer.Add(btn_plot,  flag=wx.RIGHT, border=5)
        
        mainsizer.Add(minisizer, flag=wx.ALL, border=8)
#         mainsizer.Add(btn_cncl, flag=wx.ALL, border=8)

        self.panel.SetSizer(mainsizer)
        
        
    def setDefaults(self):

        self.ymin.SetValue(str(0))
        self.ymax.SetValue(str(10000))
        self.xstep.SetValue(str(5001))
        self.xmin.SetValue(str(0.1))
        self.xmax.SetValue(str(5.5))
        self.wedges.SetValue(str(1))
        
        self.wedge_arrow.SetRange(1, 10)
        self.wedge_arrow.SetValue(1)
        
    def onUnits(self,event):

        hc = constants.value(u'Planck constant in eV s') * \
                       constants.value(u'speed of light in vacuum') * 1e-3 ## units: keV-m
#         if self.slctEorL.GetSelection() == 1:
#             energy = float(self.EorL.GetValue()) ## units keV
#             wavelength = hc/(energy)*1e10 ## units: A
#             self.EorL.SetValue(str(wavelength))
#         else:
#             wavelength = float(self.EorL.GetValue())*1e-10 ## units: m
#             energy = hc/(wavelength) ## units: keV
#             self.EorL.SetValue(str(energy))

    def OnSpin(self, event):
        self.wedges.SetValue(str(event.GetPosition())) 



    def onSAVE(self,event):
        wildcards = '1D XRD file (*.xy)|*.xy|All files (*.*)|*.*'
        dlg = wx.FileDialog(self, 'Save file as...',
                           defaultDir=os.getcwd(),
                           wildcard=wildcards,
                           style=wx.SAVE|wx.OVERWRITE_PROMPT)

        path, save = None, False
        if dlg.ShowModal() == wx.ID_OK:
            save = True
            path = dlg.GetPath().replace('\\', '/')
        dlg.Destroy()
        
        if save:
            self.data1D = integrate_xrd(self.data2D,steps=self.steps,ai = self.ai,file=path,verbose=True)

    def onPLOT(self,event):
        
        self.data1D = integrate_xrd(self.data2D,steps=self.steps,ai = self.ai,save=False,verbose=True)
        Viewer1DXRD(self.data1D)


      
class diFFit1D(wx.App):
    def __init__(self):
        wx.App.__init__(self)

    def run(self):
        self.MainLoop()

    def createApp(self):
        frame = Viewer1DXRD(None)
        frame.Show()
        self.SetTopWindow(frame)

    def OnInit(self):
        self.createApp()
        return True

def registerLarchPlugin():
    return ('_diFFit', {})

class DebugViewer(diFFit1D):
    def __init__(self, **kws):
        diFFit1D.__init__(self, **kws)

    def OnInit(self):
        #self.Init()
        self.createApp()
        #self.ShowInspectionTool()
        return True

if __name__ == '__main__':
    diFFit1D().run()
