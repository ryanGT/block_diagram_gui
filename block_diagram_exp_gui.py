from __future__ import print_function

# Used to guarantee to use at least Wx2.8
import wxversion
wxversion.ensureMinimal('2.8')

use_pdfviewer = False

from numpy import *

import xml_utils
xml_wildcard = "XML files (*.xml)|*.xml"
txt_wildcard = "TXT files (*.txt)|*.txt"

import xml.etree.ElementTree as ET

import wx_utils
import wx_mpl_plot_panels

import sys, time, os, gc, pdb
starting_dir = os.getcwd()
#print('starting_dir = ' + starting_dir)
sys.path.append(starting_dir)
exp_dir = os.path.join(starting_dir, 'exp_xml_systems')
if os.path.exists(exp_dir):
    sys.path.append(exp_dir)

## import matplotlib
## matplotlib.use('WXAgg')
## import matplotlib.cm as cm
## import matplotlib.cbook as cbook
## from matplotlib.backends.backend_wxagg import Toolbar, FigureCanvasWxAgg
## from matplotlib.figure import Figure
import numpy as np
import txt_mixin, rwkmisc, rwkos

import wx
import wx.xrc as xrc

import wx.grid
#import wx.grid as  gridlib

import tikz_bitmap_viewer_panel
bd_panel_class = tikz_bitmap_viewer_panel.tikz_panel

import params_grid_and_listbox_panel
params_grid_class = params_grid_and_listbox_panel.params_grid_panel_hide_tikz

import input_params_panel
input_params_class = input_params_panel.input_params_panel

import parse_xml_bd_system

other_input_types = ['swept_sine', 'finite_width_pulse', 'step_input']
              
              
def gen_input_vect(T=2.0, case='sys_check', dt=1.0/500, input_params={'amp':100}):
    t = arange(0,T,dt)
    u = zeros_like(t)
    amp = input_params['amp']
    
    if case == 'sys_check':
        u[10:50] = amp
        u[-90:-50] = -amp

    elif case in ['step','step_input']:
        ind_on = int(input_params['t_on']/dt)
        u[ind_on:] = amp


    elif case == 'finite_width_pulse':
        ind_on = int(input_params['t_on']/dt)
        ind_off = int(input_params['t_off']/dt)
        u[ind_on:ind_off] = amp


    elif case == 'swept_sine':
        import control_utils
        t_span = T
        fmax = input_params['fmax']
        fmin = input_params['fmin']
        deadtime = input_params['deadtime']
        
        u, t = control_utils.create_swept_sine_signal(fmax=fmax, fmin=fmin, \
                                                      tspan=t_span, dt=dt, \
                                                      deadtime=deadtime)
        u *= amp

    elif case == 'return_to_zero':
        #really do nothing, but this is a valid case
        u = zeros_like(t)
    else:
        raise ValueError, "I don't know what to do with case %s" % case
        
    return u

label_dict = {'$\\ddot{x}_{tip}$':'accel', \
              '$\\ddot{x}$':'accel'}


def clean_labels(listin):
    listout = []

    for item in listin:
        if label_dict.has_key(item):
            clean_label = label_dict[item]
        else:
            clean_label = rwkmisc.clean_latex(item)
            
        listout.append(clean_label)

    return listout

              

class my_frame(wx.Frame):
    def Close_Serial(self):
        if hasattr(self, 'ser') and self.ser is not None:
            self.ser.close()
        self.ser = None


    def on_exit(self,event):
        """Close the GUI"""
        self.Close_Serial()
        self.Close(True)  # Close the frame.


    def find_input_block(self, sys):
        arb_inputs = sys.get_blocks_by_type('arbitrary_input')
        assert len(arb_inputs) == 1, 'problem with the len of arb_inputs: ' + str(arb_inputs)
        input_block = arb_inputs[0]
        for intype in other_input_types:
            matching_blocks = sys.get_blocks_by_type(intype)
            assert len(matching_blocks) == 0, 'found input other than arbitrary_input: ' + intype
            
        return input_block
        

    def _prep_and_run_exp(self, u, dt=1.0/500, sys=None):
        if sys is None:
            sys = self.exp_sys

        input_block = self.find_input_block(sys)
        N = len(u)
        nvect = arange(N)
        t = dt*nvect
        sys.sort_blocks()
        sys.prep_for_exp(N, t, dt)
        input_block.set_u(u)
        sys.Run_Exp()
        self.t = t
        

    def replace_serial_plant(self, sys):
        if self.microcontroller == 'psoc':
            for block in sys.parsed_block_list:
                if block.blocktype == 'serial_plant':
                    block.blocktype += '_psoc'
        else:
            raise ValueError, "only psoc microcontrollers are supported at this time, " + \
                  'self.microcontroller = ' + str(self.microcontroller)

        return sys
    
    def _get_micro_parser_class(self):
        if self.microcontroller == 'psoc':
            myclass = parse_xml_bd_system.psoc_exp_xml_system_parser
        else:
            raise ValueError, "only psoc microcontrollers are supported at this time, " + \
                  'self.microcontroller = ' + str(self.microcontroller)
        
        return myclass
        
        
    def parse_blocklist(self):
        myclass = self._get_micro_parser_class()
        sys = myclass()
        sys.set_parsed_block_list(self.blocklist)
        sys_out = self.replace_serial_plant(sys)
        return sys_out
        
    
    def parse_xml_w_micro(self, xmlpath):
        myclass = self._get_micro_parser_class()
        sys = myclass(xmlpath)
        sys_out = self.replace_serial_plant(sys)
        return sys_out


    def open_or_attach_serial_connection(self, sys):
        if (not hasattr(self, 'ser')) or (self.ser is None):
            sys._open_ser()
            self.ser = sys.ser
        else:
            #attach self.ser to sys.ser
            sys.attach_ser(self.ser)
            #sys.ser = self.ser

        
    def on_run_sys_check(self, event):
        # - load, parse, and convert sys_check_sys.xml
        # - connect serial (attaching it to self), using self.ser if it exists
        # - Run_Exp
        #   - prep for exp and such
        # - plot results
        sys_check_name = 'sys_check_sys.xml'
        sys_check_name = 'sys_check_sys.xml'
        if os.path.exists(sys_check_name):
            sys_check_path = sys_check_name
        else:
            sys_check_path = rwkos.FindinPath(sys_check_name)
        xml_sys = self.parse_xml_w_micro(sys_check_path)
        self.sys_check_sys = xml_sys.convert()
        self.open_or_attach_serial_connection(self.sys_check_sys)

        u = gen_input_vect(T=2.0, dt=1.0/500, case='sys_check')
        self._prep_and_run_exp(u, sys=self.sys_check_sys)

        #plot results
        input_block = self.find_input_block(self.sys_check_sys)
        plant_block = self.sys_check_sys.get_blocks_by_type('serial_plant')[0]
        self.plot_sys = self.sys_check_sys
        self.plot_results([(input_block, 0, '$v$'), \
                           (plant_block, 0, '$\\theta$'), \
                           (plant_block, 1, '$\\ddot{x}_{tip}$')])


    def check_blocks(self, plot_list):
        valid = True

        for row in plot_list:
            blockname = row[0]
            try:
                self.plot_sys.get_block(blockname)
            except:
                valid = False
                break

        return valid


    def get_labels(self, plot_list):
        labels = []

        for row in plot_list:
            if len(row) > 2:
                label = row[2]
            else:
                label = None
            labels.append(label)

        return labels
    

    def get_data(self, plot_list):
        data_list = []
        for row in plot_list:
            blockname = row[0]
            if row[1]:
                col = int(row[1])
            else:
                col = 0
            try:
                block = self.plot_sys.get_block(blockname)
                if len(block.output.shape) == 1:
                    vect = block.output
                else:
                    vect = block.output[:,col]
                data_list.append(vect)
                
            except:
                print('data not valid')
                return None

        return data_list
                

    def validate_plot_list_and_get_data(self, plot_list):
        """A valid plot list is one whose block names are all valid
        (i.e. there are blocks that correspond to that name) and one
        whose column indices all make sense (i.e. we don't ask for
        data columns that don't exist)."""
        valid = True
        #check blocks
        if not plot_list:
            valid = False
        elif not self.check_blocks(plot_list):
            valid = False

        if valid:
           data_list = self.get_data(plot_list)
           return data_list
        else:
            return None


    def on_run_test(self, event, reset_theta=True):
        #print('in on_run_test')
        if not hasattr(self.bd_panel, 'xml_path'):
            wx.MessageBox('You must load an xml file before running a test.', \
                          'Load an XML file', \
                          wx.OK)
            return

        if hasattr(self, 'blocklist') and self.blocklist:
            #use self.blocklist
            xml_sys = self.parse_blocklist()
        else:
            xml_sys = self.parse_xml_w_micro(self.bd_panel.xml_path)
        self.exp_sys = xml_sys.convert()
        self.open_or_attach_serial_connection(self.exp_sys)

        if reset_theta:
            self.on_reset_theta(event)
            
        u_case, u_dict = self.input_params_panel.get_input_params()
        if u_dict is None:
            return
        u = gen_input_vect(T=u_dict['max_T'], dt=1.0/500, case=u_case, \
                           input_params=u_dict)
        self._prep_and_run_exp(u, sys=self.exp_sys)

        #plot results
        self.plot_sys = self.exp_sys
        input_block = self.find_input_block(self.exp_sys)
        #pdb.set_trace()
        #first check to see if there are valid signals already defined in the self.plot_panel.signals_grid
        #use defaults if not
        plot_list = self.plot_panel.get_plot_list()
        data_list = self.validate_plot_list_and_get_data(plot_list)
        if data_list:
            label_list = self.get_labels(plot_list)
            self.plot_data_list_with_labels(data_list, label_list)
        else:
            plant_block = self.exp_sys.get_blocks_by_type('serial_plant')[0]
            self.plot_results([(input_block, 0, '$u$'), \
                               (plant_block, 0, '$\\theta$'), \
                               (plant_block, 1, '$\\ddot{x}_{tip}$')])

            mylist = [(input_block.name, '$u$', 0), \
                      (plant_block.name, '$\\theta$', 0), \
                      (plant_block.name, '$\\ddot{x}_{tip}$', 1)]
            self.plot_panel.set_signals_info(mylist)


    def on_save_data(self, event):
        #need filepath dialog here
        filepath = wx_utils.my_file_dialog(parent=self, \
                                           msg="Save data as txt file", default_file="", \
                                           wildcard=txt_wildcard, \
                                           kind="save", \
                                           check_overwrite=False)
        if filepath:
            plot_list = self.plot_panel.get_plot_list()
            data_list = self.validate_plot_list_and_get_data(plot_list)
            if data_list:
                label_list = self.get_labels(plot_list)

            all_data = [self.t] + data_list
            all_labels = ['Time (sec.)'] + label_list
            c_labels = clean_labels(all_labels)
            data_mat = np.column_stack(all_data)
            # I could kind of use a way to clean the labels from latex to plain ascii
            # i.e. $\ddot{x}_{tip}$ --> accel
            txt_mixin.dump_delimited(filepath, data_mat, labels=c_labels)
        

    def on_return_to_zero(self, event):
        """Send the experimental system (kind of assuming the SFLR
        here, but I guess it works with any plant) back to zero by
        basically running a step input with 0 amplitude.

        Is it better to use self.exp_sys if it exists (thereby
        assuming it is stable, and using its vibration suppression if
        there is some), or do I force the loading of a P control
        system?  Using a different system will ensure that the data
        from the last test is still available for saving, but I could
        accomplish that by making a copy of self.exp_sys Using a
        separate system requires that its xml file always be present.

        In the end, I think P control is safer, so I will do that.
        The P control xml path should probably be configurable in the
        future."""
        print('in on_return_to_zero')
        if not hasattr(self, 'return_to_zero_sys'):
            P_control_name = 'P_control_SFLR.xml'
            if os.path.exists(P_control_name):
                P_control_path = P_control_name
            else:
                P_control_path = rwkos.FindinPath(P_control_name)
            xml_sys = self.parse_xml_w_micro(P_control_path)
            self.return_to_zero_sys = xml_sys.convert()
            
        self.open_or_attach_serial_connection(self.return_to_zero_sys)

        u = gen_input_vect(T=2.0, dt=1.0/500, case='return_to_zero')
        self._prep_and_run_exp(u, sys=self.return_to_zero_sys)
        
        

    def on_reset_theta(self, event):
        #print('in on_reset_theta')
        #how do I get access to a serial system to send the command?
        if hasattr(self, 'exp_sys'):
            self.exp_sys.Reset_Theta()
        elif hasattr(self, 'sys_check_sys'):
            self.sys_check_sys.Reset_Theta()
        elif hasattr(self, 'return_to_zero_sys'):
            self.return_to_zero_sys.Reset_Theta()
            

    def plot_results(self, mylist, clear=True, legloc=1):
        """Plot the results for the list of tuples in mylist, where
        the first element of each tuple is a block and the second is
        the index the output column.  If multiple columns are desired
        for one block, the list should have one entry per column, i.e.
        [(blockA, 0), (blockA, 1)].  The tuple may have an optional
        third element that is the label for the line."""
        fig = self.plot_panel.get_fig()
        if clear:
            fig.clf()
            
        ax = fig.add_subplot(111)
        self.plot_panel.ax = ax

        any_labels = False
        
        for mytup in mylist:
            tup0 = mytup[0]
            if type(tup0) in [str, unicode]:
                block = self.plot_sys.get_block(tup0)
            else:
                block = tup0
                
            if len(block.output.shape) == 1:
                vect = block.output
            else:
                col = mytup[1]
                vect = block.output[:,col]

            if len(mytup) > 2:
                label = mytup[2]
                any_labels = True
            else:
                label = None

            ax.plot(self.t, vect, label=label)

            if any_labels:
                ax.legend(loc=legloc)
                
        self.plot_panel.draw()


    def plot_data_list_with_labels(self, data_list, label_list, \
                                   clear=True, legloc=1):
        fig = self.plot_panel.get_fig()
        if clear:
            fig.clf()

        ax = fig.add_subplot(111)#<-- this is probably bad if we aren't clearing
        self.plot_panel.ax = ax

        for vect, label in zip(data_list, label_list):
            ax.plot(self.t, vect, label=label)


        ax.legend(loc=legloc)
        self.plot_panel.draw()
        
        
    def on_force_update_diagram(self, event):
        self.bd_panel.on_update_diagram(event, force_refresh=True)
        
        
    def __init__(self, parent, id, title, microcontroller='psoc'):        
        ## wx.Frame.__init__(self, parent, id, title)
        ## self.main_panel = wx.Panel(self)
        ## self.nb = wx.Notebook(self.main_panel)

        ## mainsizer = wx.FlexGridSizer(rows=1, cols=1, hgap=5, vgap=5)
        ## mainsizer.Add(self.main_panel,1.0,wx.ALL|wx.EXPAND,5)

        pre = wx.PreFrame()
        res = xrc.XmlResource('bd_exp_gui_xrc.xrc')
        res.LoadOnFrame(pre, parent, "main_frame") 
        self.PostCreate(pre)

        self.nb = xrc.XRCCTRL(self, "nb")

        self.blocklist = []
        self.parent = parent
        self.microcontroller = microcontroller

        gridSizer = wx.FlexGridSizer(rows=2, cols=1, hgap=5, vgap=5)
        self.page1 = wx.Panel(self.nb)
        self.bd_panel = bd_panel_class(self.page1, bd_parent=self)
        gridSizer.Add(self.bd_panel,1.0,wx.ALL|wx.EXPAND,5)
        #self.SetClientSize((800,700))

        self.input_params_panel = input_params_class(self.nb)


        self.params_grid_panel = params_grid_class(self.page1, bd_parent=self)
        gridSizer.Add(self.params_grid_panel,1.0,wx.ALL,5)

        self.page1.SetSizer(gridSizer)
        self.page1.Layout()

        self.plot_panel = wx_mpl_plot_panels.plot_panel_with_bd_side_panel(self.nb, \
                                                                           bd_parent=self, \
                                                                           plot_method=self.plot_results)
        
        self.nb.AddPage(self.page1, "Block Diagram")
        self.nb.AddPage(self.input_params_panel, "Input Parameters")
        self.nb.AddPage(self.plot_panel, "Plot")
        
        self.res = xrc.XmlResource('bd_exp_menu_xrc2.xrc')
        self.menubar = self.res.LoadMenuBar("bd_exp_menu")
        self.SetMenuBar(self.menubar) 

        self.Bind(wx.EVT_MENU, self.on_load_xml, \
                        id=xrc.XRCID('load_xml_menu'))
        self.Bind(wx.EVT_MENU, self.on_exit, \
                        id=xrc.XRCID('quit_menu'))

        self.Bind(wx.EVT_MENU, self.bd_panel.on_update_diagram, \
                        id=xrc.XRCID('update_diagram_menu'))

        self.Bind(wx.EVT_MENU, self.on_force_update_diagram, \
                        id=xrc.XRCID('force_update_diagram_menu'))
        
        self.Bind(wx.EVT_MENU, self.on_save, \
                        id=xrc.XRCID('save_xml_menu'))
        
        self.Bind(wx.EVT_MENU, self.on_save_data, \
                  id=xrc.XRCID('save_data_menu'))

        self.Bind(wx.EVT_MENU, self.on_run_sys_check, \
                        id=xrc.XRCID('run_sys_check_menu'))

        self.Bind(wx.EVT_MENU, self.on_run_test, \
                  id=xrc.XRCID('run_test_menu'))

        self.Bind(wx.EVT_MENU, self.on_return_to_zero, \
                  id=xrc.XRCID('return_to_zero_menu'))

        self.Bind(wx.EVT_MENU, self.on_reset_theta, \
                  id=xrc.XRCID('reset_theta_menu'))

        #set a redundant shotcut for loading/opening an xml file
        self.accel_tbl = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('O'), xrc.XRCID('load_xml_menu')),
                                             ])
        self.SetAcceleratorTable(self.accel_tbl)
        
        self.SetClientSize((900,700))

        
        

    def on_load_xml(self, event):
        print('in on_load_xml')
        self.bd_panel.on_load_xml(event)
        self.params_grid_panel.reset_list_box()


    def on_save(self, event):
        xml_path = wx_utils.my_file_dialog(parent=self, \
                                           msg="Save Block Diagram System as", \
                                           kind="save", \
                                           wildcard=xml_wildcard, \
                                           )
        if xml_path:
            root = ET.Element('block_diagram_system')
            bd_list_xml = ET.SubElement(root, 'blocks')

            for block in self.blocklist:
                block.create_xml(bd_list_xml)

            xml_utils.write_pretty_xml(root, xml_path)
            

## class MyApp(wx.App):
##     def on_exit(self,event):
##         """Close the GUI"""
##         self.frame.Close(True)  # Close the frame.

        
##     def OnInit(self):
##         self.frame = myframe(None, wx.NewId(), "Block Diagram Experiments GUI")
##         gridSizer = wx.FlexGridSizer(rows=2, cols=1, hgap=5, vgap=5)
##         self.bd_panel = bd_panel_class(self.frame)
##         gridSizer.Add(self.bd_panel,1.0,wx.ALL|wx.EXPAND,5)
##         #self.frame.SetClientSize((800,700))


##         self.params_grid_panel = params_grid_class(self.frame)
##         gridSizer.Add(self.params_grid_panel,1.0,wx.ALL,5)

##         self.res = xrc.XmlResource('bd_exp_menu_xrc2.xrc')
##         self.menubar = self.res.LoadMenuBar("bd_exp_menu")
##         self.frame.SetMenuBar(self.menubar) 

##         self.frame.Bind(wx.EVT_MENU, self.on_load_xml, \
##                         id=xrc.XRCID('load_xml_menu'))
##         self.frame.Bind(wx.EVT_MENU, self.on_exit, \
##                         id=xrc.XRCID('quit_menu'))

##         self.frame.Bind(wx.EVT_MENU, self.bd_panel.on_update_diagram, \
##                         id=xrc.XRCID('update_diagram_menu'))

##         self.frame.SetSizerAndFit(gridSizer)
##         self.frame.Show(1)
##         self.SetTopWindow(self.frame)
##         return True


class MyApp(wx.App):
    def OnInit(self):
        frame = my_frame(None, wx.NewId(), "Block Diagram Experiments GUI")
        self.SetTopWindow(frame)
        frame.Show()
        return True
    

if __name__ == '__main__':
    app = MyApp(0)
    app.MainLoop()

