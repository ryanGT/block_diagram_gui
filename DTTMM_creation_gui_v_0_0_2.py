from __future__ import print_function

# Used to guarantee to use at least Wx2.8
import wxversion
wxversion.ensureMinimal('2.8')

import sys, time, os, gc
import matplotlib
matplotlib.use('WXAgg')
import matplotlib.cm as cm
import matplotlib.cbook as cbook
from matplotlib.backends.backend_wxagg import Toolbar, FigureCanvasWxAgg
from matplotlib.figure import Figure
import numpy as np

import wx
import wx.xrc as xrc

import wx.grid
#import wx.grid as  gridlib

import parse_DTTMM_xml

import xml.etree.ElementTree as ET
from xml.dom import minidom

#import ryans_first_xrc

import pdb

from DTTMM_xml import prettify, element_params, sorted_elements, \
     DTTMM_XML_element, sensor_XML_element, actuator_XML_element
    
class PlotPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.fig = Figure((9,6), 100)
        self.canvas = FigureCanvasWxAgg(self, -1, self.fig)
        self.toolbar = Toolbar(self.canvas) #matplotlib toolbar
        self.toolbar.Realize()
        #self.toolbar.set_active([0,1])

        # Now put all into a sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        # This way of adding to sizer allows resizing
        sizer.Add(self.canvas, 1, wx.LEFT|wx.TOP|wx.GROW)
        # Best to allow the toolbar to resize!
        sizer.Add(self.toolbar, 0, wx.GROW)
        self.SetSizer(sizer)
        self.Fit()


    def init_plot_data(self):
        a = self.fig.add_subplot(111)
        t = np.arange(0,1,0.01)
        y = np.sin(2*np.pi*t)
        self.lines = a.plot(t,y)
        self.ax = a
        self.toolbar.update() # Not sure why this is needed - ADS


    def change_plot(self):
        self.ax.clear()
        t = np.arange(0,1,0.01)
        y2 = np.cos(2*np.pi*t)
        self.ax.plot(t,y2)
        self.canvas.draw()

        
    def GetToolBar(self):
        # You will need to override GetToolBar if you are using an
        # unmanaged toolbar in your frame
        return self.toolbar

    ## def OnWhiz(self,evt):
    ##     self.x += np.pi/15
    ##     self.y += np.pi/20
    ##     z = np.sin(self.x) + np.cos(self.y)
    ##     self.im.set_array(z)

    ##     zmax = np.amax(z) - ERR_TOL
    ##     ymax_i, xmax_i = np.nonzero(z >= zmax)
    ##     if self.im.origin == 'upper':
    ##         ymax_i = z.shape[0]-ymax_i
    ##     self.lines[0].set_data(xmax_i,ymax_i)

    ##     self.canvas.draw()

    def onEraseBackground(self, evt):
        # this is supposed to prevent redraw flicker on some X servers...
        pass


class MyApp(wx.App):
    def clear_params_grid(self):
        self.params_grid.SetCellValue(0,0, "parameter")
        self.params_grid.SetCellValue(0,1, "value")
        for i in range(1,10):
            self.params_grid.SetCellValue(i,0, "")
            self.params_grid.SetCellValue(i,1, "")


    def build_params_dict(self):
        params_dict = {}
        exit_code = 0
        for i in range(1,10):
            key = self.params_grid.GetCellValue(i,0)
            val = self.params_grid.GetCellValue(i,1)
            print('key = ' + key)
            print('val = ' + val)
            key = key.strip()
            val = val.strip()
            if not key:
                break
            elif not val:
                msg = 'Empty parameters are not allow: %s' % key
                wx.MessageBox(msg, 'Parameter Error', 
                              wx.OK | wx.ICON_ERROR)
                exit_code = 1
                break
            params_dict[key] = val
        print('params_dict = %s' % params_dict)
        return params_dict
        

    def get_new_element_type(self):
        key = self.new_element_choice.GetStringSelection()
        return key


    def set_param_labels(self):
        self.clear_params_grid()
        key = self.get_new_element_type()
        cur_params = element_params[key]
        for i, item in enumerate(cur_params):
            self.params_grid.SetCellValue(i+1,0, item)
        

    def append_one_element(self, name, elemtype, params_dict):
        new_element = DTTMM_XML_element(name=name, \
                                        elemtype=elemtype, \
                                        params=params_dict)
        self.elemlist.append(new_element)
        self.element_list_box.Append(name)
        
        
    def on_add_element(self,event):
        print('in on_add_element')
        print('selection: %s' % self.new_element_choice.GetStringSelection())
        self.plotpanel.change_plot()
        params_dict = self.build_params_dict()
        elemtype = self.get_new_element_type()
        name = self.new_element_name_box.GetValue()
        self.append_one_element(name, elemtype, params_dict)


    def on_save_button(self, event):
        sys = ET.Element('system')
        #add elements
        params_elem = ET.SubElement(sys, 'elements')
        for elem in self.elemlist:
            attrib = {'name':elem.name}
            elem_xml = ET.SubElement(params_elem, elem.elemtype, attrib=attrib)
            params_xml = ET.SubElement(elem_xml, 'params')
            for key, val in elem.params.iteritems():
                val_xml = ET.SubElement(params_xml, key)
                val_xml.text = val


        #add sensors
        sensors = ET.SubElement(sys, 'sensors')
        sensor_1 = sensor_XML_element(name='encoder', sensor_type='abs', \
                                      signal='theta', elem1='dc_motor1')
        sensor_2 = sensor_XML_element(name='accel', sensor_type='abs', \
                                      signal='xddot', elem1='beam1')
        sensor_list = [sensor_1, sensor_2]

        attrs = ['sensor_type','signal','elem1','elem2']
        
        for sensor in sensor_list:
            sense = ET.SubElement(sensors, 'sensor', {'name':sensor.name})
            for attr in attrs:
                cur_xml = ET.SubElement(sense, attr)
                cur_xml.text = str(getattr(sensor, attr))


        #add actuator(s)
        actuators = ET.SubElement(sys, 'actuators')
        act1 = actuator_XML_element(name='dc_motor1', signal='v')
        actuator_list = [act1]

        for act in actuator_list:
            act_xml = ET.SubElement(actuators, 'actuator', {'name':act.name})
            sig_xml = ET.SubElement(act_xml, 'signal')
            sig_xml.text = act.signal
            
        pretty_str = prettify(sys)
        filename = 'test.xml'#should have dialog here
        f = open(filename, 'wb')
        f.write(pretty_str)
        f.close()
        ##>>> ET.dump(a)
        ##<a><b /><c><d /></c></a>


    def get_filename(self):
        dirname = ''
        dlg = wx.FileDialog(self.panel, "Choose a file", dirname, \
                            "", "*.xml", wx.OPEN)
        filepath = None
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetFilename()
            dirname = dlg.GetDirectory()
            filepath = os.path.join(dirname, filename)
        dlg.Destroy()
        return filepath
    

    def on_load_button(self, event):
        filepath = self.get_filename()
        self.parser = parse_DTTMM_xml.DTTMM_xml_parser(filepath)
        self.elemlist = []
        for element in self.parser.parsed_element_list:
            self.append_one_element(element.name, \
                                    element.elemtype, \
                                    element.params)
            

    def display_params(self, elem):
        params_dict = elem.params
        #pdb.set_trace()
        self.clear_params_grid()
        keys = params_dict.keys()
        keys.sort()
        for i, key in enumerate(keys):
            self.params_grid.SetCellValue(i+1,0, key)
            self.params_grid.SetCellValue(i+1,1, params_dict[key])

        
    def on_element_select(self, event):
        print('in on_element_select')
        curname = self.element_list_box.GetStringSelection()
        index = self.element_list_box.GetSelection()
        print('curname = %s, index = %i' % (curname, index))
        elem = self.elemlist[index]
        self.display_params(elem)

        
    def on_new_element_choice(self, event):
        print('in OnNewElementChoice')
        print('selection: %s' % self.new_element_choice.GetStringSelection())
        self.set_param_labels()
        new_name = self.suggest_element_name()
        self.new_element_name_box.SetValue(new_name)
        


    def count_elements_of_type(self, elemtype):
        count = 0
        for elem in self.elemlist:
            if elem.elemtype == elemtype:
                count += 1
        return count


    def suggest_element_name(self, elemtype=None):
        if elemtype is None:
            elemtype = self.get_new_element_type()
        count = self.count_elements_of_type(elemtype)
        return elemtype + str(count+1)
    
        
    def OnInit(self):
        #xrcfile = cbook.get_sample_data('ryans_first_xrc.xrc', asfileobj=False)
        xrcfile = 'ryans_first_xrc.xrc'
        print('loading', xrcfile)

        self.res = xrc.XmlResource(xrcfile)

        # main frame and panel ---------

        self.frame = self.res.LoadFrame(None,"MainFrame")
        self.panel = xrc.XRCCTRL(self.frame,"MainPanel")
        self.new_element_choice = xrc.XRCCTRL(self.frame, "new_element_choice")
        self.new_element_choice.SetItems(sorted_elements)
        self.add_element_button = xrc.XRCCTRL(self.frame,"add_element_button")
        wx.EVT_BUTTON(self.add_element_button, self.add_element_button.GetId(),
                      self.on_add_element)
        wx.EVT_CHOICE(self.new_element_choice, self.new_element_choice.GetId(),
                      self.on_new_element_choice)

        self.load_button = xrc.XRCCTRL(self.frame, "load_button")
        wx.EVT_BUTTON(self.load_button, self.load_button.GetId(),
                      self.on_load_button)
        self.save_button = xrc.XRCCTRL(self.frame, "save_button")
        wx.EVT_BUTTON(self.save_button, self.save_button.GetId(),
                      self.on_save_button)
        
        #self.params_panel = xrc.XRCCTRL(self.frame, "params_panel")
        #self.params_grid = gridlib.Grid(self.params_panel)
        self.params_grid = xrc.XRCCTRL(self.frame, "params_grid")
        self.params_grid.CreateGrid(10,2)
        self.set_param_labels()
        ## sizer_g = wx.BoxSizer(wx.VERTICAL)
        ## sizer_g.Add(self.params_grid, 1, wx.EXPAND)
        ## self.params_panel.SetSizer(sizer_g)
        
        plot_container = xrc.XRCCTRL(self.frame,"plot_container_panel")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # matplotlib panel itself
        self.plotpanel = PlotPanel(plot_container)
        self.plotpanel.init_plot_data()

        # wx boilerplate
        sizer.Add(self.plotpanel, 1, wx.EXPAND)
        plot_container.SetSizer(sizer)
        #self.plotpanel.SetMinSize((900,600))

        self.new_element_name_box = xrc.XRCCTRL(self.frame, "element_name_ctrl")
        self.new_element_name_box.SetMinSize((200,-1))
        self.elemlist = []
        new_name = self.suggest_element_name()
        self.new_element_name_box.SetValue(new_name)

        self.element_list_box = xrc.XRCCTRL(self.frame, "element_list_box")
        self.element_list_box.SetMinSize((200,-1))

        wx.EVT_LISTBOX(self.element_list_box, self.element_list_box.GetId(),
                       self.on_element_select)


        
        self.frame.SetClientSize((800,700))
        self.frame.Show(1)
        self.SetTopWindow(self.frame)
        return True


if __name__ == '__main__':
    app = MyApp(0)
    app.MainLoop()

