#!/usr/bin/python
"""
subclass of wxmplot.ImageFrame specific for Map Viewer -- adds custom menus
"""
import sys
import os
import wx
from wx._core import PyDeadObjectError
import numpy
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg

import larch

sys.path.insert(0, larch.plugin_path('wx'))
from wxutils import Closure, LabelEntry, SimpleText

from wxmplot import ImageFrame, PlotFrame
from wxmplot.imagepanel import ImagePanel
from wxmplot.imageconf import ColorMap_List, Interp_List
from wxmplot.colors import rgb2hex


CURSOR_MENULABELS = {'zoom':  ('Zoom to Rectangle\tCtrl+B',
                               'Left-Drag to zoom to rectangular box'),
                     'lasso': ('Select Points for XRF Spectra\tCtrl+X',
                               'Left-Drag to select points freehand'),
                     'prof':  ('Select Line Profile\tCtrl+K',
                               'Left-Drag to select like for profile')}

class MapImageFrame(ImageFrame):
    """
    MatPlotlib Image Display on a wx.Frame, using ImagePanel
    """

    def __init__(self, parent=None, size=None,
                 config_on_frame=True, lasso_callback=None,
                 show_xsections=False, cursor_labels=None,
                 output_title='Image',   **kws):

        ImageFrame.__init__(self, parent=parent, size=size,
                            config_on_frame=config_on_frame,
                            lasso_callback=lasso_callback,
                            cursor_labels=cursor_labels,
                            output_title=output_title, **kws)
        self.panel.add_cursor_mode('prof', motion = self.prof_motion,
                                   leftdown = self.prof_leftdown,
                                   leftup   = self.prof_leftup)
        self.prof_plotter = None
        self.zoom_ini =  None
        self.lastpoint = [None, None]
        self.rbbox = None

    def prof_motion(self, event=None):
        if not event.inaxes or self.zoom_ini is None:
            return
        try:
            xmax, ymax  = event.x, event.y
        except:
            return

        xmin, ymin, xd, yd = self.zoom_ini
        if event.xdata is not None:
            self.lastpoint[0] = event.xdata
        if event.ydata is not None:
            self.lastpoint[1] = event.ydata

        yoff = self.panel.canvas.figure.bbox.height
        ymin, ymax = yoff - ymin, yoff - ymax

        zdc = wx.ClientDC(self.panel.canvas)
        zdc.SetLogicalFunction(wx.XOR)
        zdc.SetBrush(wx.TRANSPARENT_BRUSH)
        zdc.SetPen(wx.Pen('White', 2, wx.SOLID))
        zdc.ResetBoundingBox()
        zdc.BeginDrawing()

        # erase previous box
        if self.rbbox is not None:
            zdc.DrawLine(*self.rbbox)
        self.rbbox = (xmin, ymin, xmax, ymax)
        zdc.DrawLine(*self.rbbox)
        zdc.EndDrawing()

    def prof_leftdown(self, event=None):
        self.panel.report_leftdown(event=event)
        if event.inaxes:
            self.lastpoint = [None, None]
            self.zoom_ini = [event.x, event.y, event.xdata, event.ydata]

    def prof_leftup(self, event=None):
        if self.rbbox is not None:
            zdc = wx.ClientDC(self.panel.canvas)
            zdc.SetLogicalFunction(wx.XOR)
            zdc.SetBrush(wx.TRANSPARENT_BRUSH)
            zdc.SetPen(wx.Pen('White', 2, wx.SOLID))
            zdc.ResetBoundingBox()
            zdc.BeginDrawing()
            zdc.DrawLine(*self.rbbox)
            zdc.EndDrawing()
            self.rbbox = None

        if self.zoom_ini is None or self.lastpoint[0] is None:
            return

        x0 = int(self.zoom_ini[2])
        x1 = int(self.lastpoint[0])
        y0 = int(self.zoom_ini[3])
        y1 = int(self.lastpoint[1])
        dx, dy = abs(x1-x0), abs(y1-y0)

        self.lastpoint, self.zoom_ini = [None, None], None
        if dx < 2 and dy < 2:
            return

        outdat = []

        if dy > dx:
            _y0 = min(int(y0), int(y1+0.5))
            _y1 = max(int(y0), int(y1+0.5))

            for iy in range(_y0, _y1):
                ix = int(x0 + (iy-int(y0))*(x1-x0)/(y1-y0))
                outdat.append((ix, iy))
        else:
            _x0 = min(int(x0), int(x1+0.5))
            _x1 = max(int(x0), int(x1+0.5))
            for ix in range(_x0, _x1):
                iy = int(y0 + (ix-int(x0))*(y1-y0)/(x1-x0))
                outdat.append((ix, iy))
        x, y, z = [], [], []
        for ix, iy in outdat:
            x.append(ix)
            y.append(iy)
            z.append(self.panel.conf.data[iy,ix])
        self.prof_dat = dy>dx, outdat

        if self.prof_plotter is not None:
            try:
                self.prof_plotter.Raise()
                self.prof_plotter.clear()

            except AttributeError, PyDeadObjectError:
                self.prof_plotter = None

        if self.prof_plotter is None:
            self.prof_plotter = PlotFrame(self, title='Profile')
            self.prof_plotter.panel.report_leftdown = self.prof_report_coords

        xlabel, y2label = 'Pixel (x)',  'Pixel (y)'

        if dy > dx:
            x, y = y, x
            xlabel, y2label = y2label, xlabel
        self.prof_plotter.panel.clear() # reset_config()
        self.prof_plotter.plot(x, z, xlabel=xlabel, show_legend=True,
                               xmin=min(x)-3, xmax=max(x)+3, zorder=10,
                               ylabel='counts', label='counts',
                               linewidth=2, marker='+', color='blue')
        self.prof_plotter.oplot(x, y, y2label=y2label, label=y2label,
                                side='right', show_legend=True, zorder=5,
                                color='#771111', linewidth=1, marker='+',
                                markersize=3)
        self.prof_plotter.panel.unzoom_all()
        self.prof_plotter.Show()
        self.zoom_ini = None

    def prof_report_coords(self, event=None):
        """override report leftdown for profile plotter"""
        if event is None:
            return
        ex, ey = event.x, event.y
        msg = ''
        plotpanel = self.prof_plotter.panel
        axes  = plotpanel.fig.get_axes()[0]
        write = plotpanel.write_message
        try:
            x, y = axes.transData.inverted().transform((ex, ey))
        except:
            x, y = event.xdata, event.ydata

        if x is None or y is None:
            return

        this_point = 0, 0, 0, 0, 0
        for ix, iy in self.prof_dat[1]:
            if (int(x) == ix and not self.prof_dat[0] or
                int(x) == iy and self.prof_dat[0]):
                this_point = (ix, iy,
                              self.panel.xdata[ix],
                              self.panel.ydata[iy],
                              self.panel.conf.data[iy, ix])

        msg = "Pixel [%i, %i], X, Y = [%.4f, %.4f], Intensity= %g" % this_point
        write(msg,  panel=0)


    def display(self, img, title=None, colormap=None, style='image', **kw):
        """plot after clearing current plot """
        if title is not None:
            self.SetTitle(title)
        if self.config_on_frame:
            if len(img.shape) == 3:
                for comp in self.config_panel.Children:
                    comp.Disable()
            else:
                for comp in self.config_panel.Children:
                    comp.Enable()
        self.panel.display(img, style=style, **kw)
        self.panel.conf.title = title
        if colormap is not None:
            self.set_colormap(name=colormap)
        contour_value = 0
        if style == 'contour':
            contour_value = 1
        if self.config_on_frame and hasattr(self, 'contour_toggle'):
            self.contour_toggle.SetValue(contour_value)

        self.bgcol = rgb2hex(self.GetBackgroundColour()[:3])

        self.panel.redraw()
        self.panel.fig.set_facecolor(self.bgcol)

    def BuildMenu(self):
        mids = self.menuIDs
        m0 = wx.Menu()
        mids.EXPORT = wx.NewId()
        m0.Append(mids.SAVE,   "&Save Image\tCtrl+S",  "Save PNG Image of Plot")
        m0.Append(mids.CLIPB,  "&Copy Image\tCtrl+C",  "Copy Image to Clipboard")
        m0.Append(mids.EXPORT, "Export Data",   "Export to ASCII file")
        m0.AppendSeparator()
        m0.Append(mids.PSETUP, 'Page Setup...', 'Printer Setup')
        m0.Append(mids.PREVIEW, 'Print Preview...', 'Print Preview')
        m0.Append(mids.PRINT, "&Print\tCtrl+P", "Print Plot")
        m0.AppendSeparator()
        m0.Append(mids.EXIT, "E&xit\tCtrl+Q", "Exit the 2D Plot Window")

        self.top_menus['File'] = m0

        mhelp = wx.Menu()
        mhelp.Append(mids.HELP, "Quick Reference",  "Quick Reference for WXMPlot")
        mhelp.Append(mids.ABOUT, "About", "About WXMPlot")
        self.top_menus['Help'] = mhelp

        mbar = wx.MenuBar()

        mbar.Append(self.top_menus['File'], "File")
        for m in self.user_menus:
            title,menu = m
            mbar.Append(menu, title)
        mbar.Append(self.top_menus['Help'], "&Help")


        self.SetMenuBar(mbar)
        self.Bind(wx.EVT_MENU, self.onHelp,            id=mids.HELP)
        self.Bind(wx.EVT_MENU, self.onAbout,           id=mids.ABOUT)
        self.Bind(wx.EVT_MENU, self.onExit ,           id=mids.EXIT)
        self.Bind(wx.EVT_CLOSE,self.onExit)

    def BuildCustomMenus(self):
        "build menus"
        mids = self.menuIDs
        mids.SAVE_CMAP = wx.NewId()
        mids.LOG_SCALE = wx.NewId()
        mids.FLIP_H    = wx.NewId()
        mids.FLIP_V    = wx.NewId()
        mids.FLIP_O    = wx.NewId()
        mids.ROT_CW    = wx.NewId()
        mids.CUR_ZOOM  = wx.NewId()
        mids.CUR_LASSO = wx.NewId()
        mids.CUR_PROF  = wx.NewId()
        m = wx.Menu()
        m.Append(mids.UNZOOM, "Zoom Out\tCtrl+Z",
                 "Zoom out to full data range")
        m.Append(mids.LOG_SCALE, "Log Scale Intensity\tCtrl+L", "", wx.ITEM_CHECK)
        m.AppendSeparator()
        m.Append(mids.ROT_CW, 'Rotate clockwise\tCtrl+R', '')
        m.Append(mids.FLIP_V, 'Flip Top/Bottom\tCtrl+T', '')
        m.Append(mids.FLIP_H, 'Flip Left/Right\tCtrl+F', '')
        m.AppendSeparator()
        m.Append(mids.SAVE_CMAP, "Save Image of Colormap")

        self.Bind(wx.EVT_MENU, self.onFlip,       id=mids.FLIP_H)
        self.Bind(wx.EVT_MENU, self.onFlip,       id=mids.FLIP_V)
        self.Bind(wx.EVT_MENU, self.onFlip,       id=mids.ROT_CW)

        sm = wx.Menu()
        for itype in Interp_List:
            wid = wx.NewId()
            sm.AppendRadioItem(wid, itype, itype)
            self.Bind(wx.EVT_MENU, Closure(self.onInterp, name=itype), id=wid)
        self.user_menus  = [('&Options', m), ('Smoothing', sm)]

    def onCursorMode(self, event=None):
        self.panel.cursor_mode = 'zoom'
        if 1 == event.GetInt():
            self.panel.cursor_mode = 'lasso'
        elif 2 == event.GetInt():
            self.panel.cursor_mode = 'prof'

    def onLasso(self, data=None, selected=None, mask=None, **kws):
        if hasattr(self.lasso_callback , '__call__'):
            self.lasso_callback(data=data, selected=selected, mask=mask, **kws)

    def redraw_cmap(self):
        conf = self.panel.conf
        if not hasattr(conf, 'image'): return
        self.cmap_image.set_cmap(conf.cmap)

        lo = conf.cmap_lo
        hi = conf.cmap_hi
        cmax = 1.0 * conf.cmap_range
        wid = numpy.ones(cmax/4)
        self.cmap_data[:lo, :] = 0
        self.cmap_data[lo:hi] = numpy.outer(numpy.linspace(0., 1., hi-lo), wid)
        self.cmap_data[hi:, :] = 1
        self.cmap_image.set_data(self.cmap_data)
        self.cmap_canvas.draw()

    def BuildConfigPanel(self):
        """config panel for left-hand-side of frame"""
        conf = self.panel.conf
        lpanel = wx.Panel(self)
        lsizer = wx.GridBagSizer(7, 4)

        self.config_panel = lpanel
        labstyle = wx.ALIGN_LEFT|wx.LEFT|wx.TOP|wx.EXPAND

        # interp_choice =  wx.Choice(lpanel, choices=Interp_List)
        # interp_choice.Bind(wx.EVT_CHOICE,  self.onInterp)

        s = wx.StaticText(lpanel, label=' Color Table:', size=(100, -1))
        s.SetForegroundColour('Blue')
        lsizer.Add(s, (0, 0), (1, 3), labstyle, 5)

        cmap_choice =  wx.Choice(lpanel, size=(120, -1), choices=ColorMap_List)
        cmap_choice.Bind(wx.EVT_CHOICE,  self.onCMap)
        cmap_name = conf.cmap.name
        if cmap_name.endswith('_r'):
            cmap_name = cmap_name[:-2]
        cmap_choice.SetStringSelection(cmap_name)
        self.cmap_choice = cmap_choice

        cmap_reverse = wx.CheckBox(lpanel, label='Reverse Table',
                                  size=(140, -1))
        cmap_reverse.Bind(wx.EVT_CHECKBOX, self.onCMapReverse)
        cmap_reverse.SetValue(conf.cmap_reverse)
        self.cmap_reverse = cmap_reverse

        cmax = conf.cmap_range
        self.cmap_data   = numpy.outer(numpy.linspace(0, 1, cmax),
                                       numpy.ones(cmax/4))

        self.cmap_fig   = Figure((0.20, 1.0), dpi=100)
        self.cmap_axes  = self.cmap_fig.add_axes([0, 0, 1, 1])
        self.cmap_axes.set_axis_off()

        self.cmap_canvas = FigureCanvasWxAgg(lpanel, -1,
                                             figure=self.cmap_fig)

        self.bgcol = rgb2hex(lpanel.GetBackgroundColour()[:3])
        self.cmap_fig.set_facecolor(self.bgcol)

        self.cmap_image = self.cmap_axes.imshow(self.cmap_data,
                                                cmap=conf.cmap,
                                                interpolation='bilinear')

        self.cmap_axes.set_ylim((0, cmax), emit=True)

        self.cmap_lo_val = wx.Slider(lpanel, -1, conf.cmap_lo, 0,
                                     conf.cmap_range, size=(-1, 180),
                                     style=wx.SL_INVERSE|wx.SL_VERTICAL)

        self.cmap_hi_val = wx.Slider(lpanel, -1, conf.cmap_hi, 0,
                                     conf.cmap_range, size=(-1, 180),
                                     style=wx.SL_INVERSE|wx.SL_VERTICAL)

        self.cmap_lo_val.Bind(wx.EVT_SCROLL,  self.onStretchLow)
        self.cmap_hi_val.Bind(wx.EVT_SCROLL,  self.onStretchHigh)

        iauto_toggle = wx.CheckBox(lpanel, label='Autoscale Intensity?',
                                  size=(160, -1))
        iauto_toggle.Bind(wx.EVT_CHECKBOX, self.onInt_Autoscale)
        iauto_toggle.SetValue(conf.auto_intensity)

        lsizer.Add(self.cmap_choice,  (1, 0), (1, 4), labstyle, 2)
        lsizer.Add(self.cmap_reverse, (2, 0), (1, 4), labstyle, 5)
        lsizer.Add(self.cmap_lo_val,  (3, 0), (1, 1), labstyle, 5)
        lsizer.Add(self.cmap_canvas,  (3, 1), (1, 2), wx.ALIGN_CENTER|labstyle)
        lsizer.Add(self.cmap_hi_val,  (3, 3), (1, 1), labstyle, 5)
        lsizer.Add(iauto_toggle,      (4, 0), (1, 4), labstyle)

        self.imin_val = LabelEntry(lpanel, conf.int_lo,  size=65, labeltext='I min:',
                                   action = Closure(self.onThreshold, argu='lo'))
        self.imax_val = LabelEntry(lpanel, conf.int_hi,  size=65, labeltext='I max:',
                                   action = Closure(self.onThreshold, argu='hi'))
        self.imax_val.Disable()
        self.imin_val.Disable()

        lsizer.Add(self.imin_val.label, (5, 0), (1, 1), labstyle, 5)
        lsizer.Add(self.imax_val.label, (6, 0), (1, 1), labstyle, 5)
        lsizer.Add(self.imin_val,       (5, 1), (1, 3), labstyle, 5)
        lsizer.Add(self.imax_val,       (6, 1), (1, 3), labstyle, 5)

        zoom_mode = wx.RadioBox(lpanel, -1, "Cursor Mode:",
                                wx.DefaultPosition, wx.DefaultSize,
                                ('Zoom to Rectangle',
                                 'Pick Area for XRF Spectrum',
                                 'Show Line Profile'),
                                1, wx.RA_SPECIFY_COLS)
        zoom_mode.Bind(wx.EVT_RADIOBOX, self.onCursorMode)

        lsizer.Add(zoom_mode,  (7, 0), (1, 4), labstyle, 3)


        lpanel.SetSizer(lsizer)
        lpanel.Fit()
        return lpanel