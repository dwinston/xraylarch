#!/usr/bin/python
"""
subclass of wxmplot.ImageFrame specific for Map Viewer -- adds custom menus
"""

import os
import time
from threading import Thread
import socket
import json
from collections import OrderedDict
from functools import partial
import wx
try:
    from wx._core import PyDeadObjectError
except:
    PyDeadObjectError = Exception
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg

import larch
from larch_plugins.epics import pv_fullname

from wxmplot import ImageFrame, PlotFrame
from wxmplot.imagepanel import ImagePanel
from wxmplot.imageconf import ColorMap_List, Interp_List
from wxmplot.colors import rgb2hex

from wxutils import (SimpleText, TextCtrl, Button, Popup)


CURSOR_MENULABELS = {'zoom':  ('Zoom to Rectangle\tCtrl+B',
                               'Left-Drag to zoom to rectangular box'),
                     'lasso': ('Select Points for XRF Spectra\tCtrl+N',
                               'Left-Drag to select points freehand'),
                     'prof':  ('Select Line Profile\tCtrl+K',
                               'Left-Drag to select like for profile')}


class MapImageFrame(ImageFrame):
    """
    MatPlotlib Image Display on a wx.Frame, using ImagePanel
    """

    def __init__(self, parent=None, size=None, mode='intensity',
                 lasso_callback=None, move_callback=None,                 
                 show_xsections=False, cursor_labels=None,
                 at_beamline=False, instdb=None,  inst_name=None,
                 output_title='Image',   **kws):


        self.det = None
        self.xrmfile = None
        self.map = None
        self.at_beamline = at_beamline
        self.instdb = instdb
        self.inst_name = inst_name

        ImageFrame.__init__(self, parent=parent, size=size,
                            lasso_callback=lasso_callback,
                            cursor_labels=cursor_labels, mode=mode,
                            output_title=output_title, **kws)

        self.panel.add_cursor_mode('prof', motion = self.prof_motion,
                                   leftdown = self.prof_leftdown,
                                   leftup   = self.prof_leftup)
        self.panel.report_leftdown = self.report_leftdown
        self.panel.report_motion   = self.report_motion

        self.move_callback = move_callback
        self.prof_plotter = None
        self.zoom_ini =  None
        self.lastpoint = [None, None]
        self.this_point = None
        self.rbbox = None

    def display(self, map, det=None, xrmfile=None, xoff=0, yoff=0, **kws):
        self.xoff = xoff
        self.yoff = yoff
        self.det = det
        self.xrmfile = xrmfile
        self.map = map
        self.title = ''
        if 'title' in kws:
            self.title = kws['title']
        ImageFrame.display(self, map, **kws)
        if 'x' in kws:
            self.panel.xdata = kws['x']
        if 'y' in kws:
            self.panel.ydata = kws['y']
        if self.panel.conf.auto_contrast:
            self.set_contrast_levels()


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
        self.report_leftdown(event=event)
        if event.inaxes and len(self.map.shape) == 2:
            self.lastpoint = [None, None]
            self.zoom_ini = [event.x, event.y, event.xdata, event.ydata]

    def prof_leftup(self, event=None):
        if len(self.map.shape) != 2:
            return
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
            self.zoom_ini = None
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

            except (AttributeError, PyDeadObjectError):
                self.prof_plotter = None

        if self.prof_plotter is None:
            self.prof_plotter = PlotFrame(self, title='Profile')
            self.prof_plotter.panel.report_leftdown = self.prof_report_coords

        xlabel, y2label = 'Pixel (x)',  'Pixel (y)'

        if dy > dx:
            x, y = y, x
            xlabel, y2label = y2label, xlabel
        self.prof_plotter.panel.clear() # reset_config()

        if len(self.title) < 1:
            self.title = os.path.split(self.xrmfile.filename)[1]

        opts = dict(linewidth=2, marker='+', markersize=3,
                    show_legend=True, xlabel=xlabel)
        self.prof_plotter.plot(x, z, title=self.title, color='blue',
                               zorder=20, xmin=min(x)-3, xmax=max(x)+3,
                               ylabel='counts', label='counts', **opts)

        self.prof_plotter.oplot(x, y, y2label=y2label, label=y2label,
                              zorder=3, side='right', color='#771111', **opts)

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

    def onCursorMode(self, event=None):
        self.panel.cursor_mode = 'zoom'
        if 1 == event.GetInt():
            self.panel.cursor_mode = 'lasso'
        elif 2 == event.GetInt():
            self.panel.cursor_mode = 'prof'


    def report_leftdown(self, event=None):
        if event is None:
            return
        if event.xdata is None or event.ydata is None:
            return

        ix, iy = round(event.xdata), round(event.ydata)
        conf = self.panel.conf
        if conf.flip_ud:  iy = conf.data.shape[0] - iy
        if conf.flip_lr:  ix = conf.data.shape[1] - ix

        self.this_point = None
        msg = ''
        if (ix >= 0 and ix < conf.data.shape[1] and
            iy >= 0 and iy < conf.data.shape[0]):
            pos = ''
            pan = self.panel
            # print 'has xdata? ', pan.xdata is not None, pan.ydata is not None
            labs, vals = [], []
            if pan.xdata is not None:
                labs.append(pan.xlab)
                vals.append(pan.xdata[ix])
            if pan.ydata is not None:
                labs.append(pan.ylab)
                vals.append(pan.ydata[iy])
            pos = ', '.join(labs)
            vals =', '.join(['%.4g' % v for v in vals])
            pos = '%s = [%s]' % (pos, vals)
            dval = conf.data[iy, ix]
            if len(pan.data_shape) == 3:
                dval = "%.4g, %.4g, %.4g" % tuple(dval)
            else:
                dval = "%.4g" % dval
            if pan.xdata is not None and pan.ydata is not None:
                self.this_point = (pan.xdata[ix], pan.ydata[iy])

            msg = "Pixel [%i, %i], %s, Intensity=%s " % (ix, iy, pos, dval)
        self.panel.write_message(msg, panel=0)

    def report_motion(self, event=None):
        return

    def onLasso(self, data=None, selected=None, mask=None, **kws):
        if hasattr(self.lasso_callback , '__call__'):
            self.lasso_callback(data=data, selected=selected, mask=mask,
                                xoff=self.xoff, yoff=self.yoff,
                                det=self.det, xrmfile=self.xrmfile, **kws)

    def CustomConfig(self, panel, sizer, irow):
        """config panel for left-hand-side of frame"""
        conf = self.panel.conf
        lpanel = panel
        lsizer = sizer
        labstyle = wx.ALIGN_LEFT|wx.LEFT|wx.TOP|wx.EXPAND

        zoom_mode = wx.RadioBox(panel, -1, "Cursor Mode:",
                                wx.DefaultPosition, wx.DefaultSize,
                                ('Zoom to Rectangle',
                                 'Pick Area for XRF Spectrum',
                                 'Show Line Profile'),
                                1, wx.RA_SPECIFY_COLS)
        zoom_mode.Bind(wx.EVT_RADIOBOX, self.onCursorMode)
        sizer.Add(zoom_mode,  (irow, 0), (1, 4), labstyle, 3)
        if self.at_beamline:
            
            if self.instdb is not None:
                
                self.pos_name = wx.TextCtrl(panel, -1, '',  size=(175, -1))
                label   = SimpleText(panel, label='Position name:',
                                     size=(-1, -1))
                sbutton = Button(panel, 'Save Position', size=(100, -1),
                                 action=self.onSavePixelPosition)
                sizer.Add(label,         (irow+1, 0), (1, 1), labstyle, 3)
                sizer.Add(self.pos_name, (irow+1, 1), (1, 3), labstyle, 3)
                sizer.Add(sbutton,       (irow+2, 0), (1, 2), labstyle, 3)
                irow  = irow + 2
                
            mbutton = Button(panel, 'Move to Position', size=(100, -1),
                                 action=self.onMoveToPixel)
            sizer.Add(mbutton,       (irow+1, 0), (1, 2), labstyle, 3)

    def onMoveToPixel(self, event=None):
        if self.this_point is not None and self.move_callback is not None:
            self.move_callback(*self.this_point)

    def onSavePixelPosition(self, event=None):
        if self.this_point is not None:
            pvn  = pv_fullname
            mapconf    = self.xrmfile.xrfmap['config']
            pos_addrs = [pvn(x) for x in mapconf['positioners']]
            env_addrs = [pvn(x) for x in mapconf['environ/address']]
            env_vals  = [str(x) for x in mapconf['environ/value']]

            position = {}
            for p in pos_addrs:
                position[p] = None

            position[pvn(mapconf['scan/pos1'].value)] = float(self.this_point[0])
            position[pvn(mapconf['scan/pos2'].value)] = float(self.this_point[1])

            for addr, val in zip(env_addrs, env_vals):
                if addr in pos_addrs and position[addr] is None:
                    position[addr] = float(val)

            pos_name = str(self.pos_name.GetValue().strip())
            notes = {'source': self.title}
            if len(pos_name) > 0 and self.instdb is not None: 
                self.instdb.save_position(self.inst_name, pos_name, position,
                                          notes=json.dumps(notes))
           
