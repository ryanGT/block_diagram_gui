"""This was basically the first wxPython GUI I created during my
sabbatical.  It is my first attempt to re-learn wxPython since moving
to my Mac and it is my first attempt to use xrc and xrced to create
xml for describing a wxPython GUI.  So, it is a little rusty and not
pretty at times.  I eventually set out to modularize some of the
things I used in this GUI to make it easier to create
block_diagram_exp_gui.py, which has some overlap with this module.
The main idea is that this module would be used for fully creating an
xml description of a block diagram system and then
block_diagram_exp_gui.py or a corresponding simulation running GUI
would be used to tweak the parameters in the models and run the
corresponding experiments or simulations.

For now, the GUI has only two classes:

- :py:class:`block_replacement_dialog`
- :py:class:`MyApp`

For now, block diagrams are only drawn using tikz (the original idea
was to compare tikz to something I would cook up using matplotlib, but
I haven't played with that yet).  For now, I am also forcing tikz pdfs
to be converted to jpegs using imagemagick and ghostscript (actually
using pdf_to_jpeg_one_page.py on mac or linux).  There was some issue
with the pdf viewer that shipped with the current version of wxPython
when I started working on this.  So, the dependency list for drawing
block diagrams is a bit long (pdflatex, tikz, imagemagick,
ghostscript, ....

Basic Usage
=================

In order to use the software to create a block diagram system, you
first select a block type that you want to add from the wxChoice
control that is just below the block diagram canvas and is on the far
left.  The wxChoice control is
:py:attr:`MyApp.new_block_choice`. Selecting a block type from this
control causes a suggested name to be placed in the text control
:py:attr:`MyApp.new_block_name` and loads the parameters into the grid
control :py:attr:`MyApp.params_grid`.  Right-clicking on on certain
cells will cause menu options to pop up.  It is probably not clear to
the user which items have pop-up options.  One bad feature right now
is that the GUI makes no attempt to warn the user if they don't press
the add button.  Selecting a block, changing its name, and make
changes to its parameters do not actually do anything if the user
doesn't add the block by pushing the button, i.e. if the user closes
the GUI or chooses another block from the choice control, the changes
will be lost.

Menu choices and keyboard short cuts exist for saving the block
diagram to XML, loading a block diagram from XML, saving the block
diagram to latex (tikz), updating the diagram, and autosizing the
params_gird (i.e. making the columns fit correctly).  There are also
menu options for forcing the scaling of the block diagram to use
height or width.  I don't think these options actually do anything
right now.

Autodoc Class and Method Documentation
==================================================

"""

from __future__ import print_function

# Used to guarantee to use at least Wx2.8
import wxversion
wxversion.ensureMinimal('2.8')

use_pdfviewer = False

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

import block_diagram_xml

#import ryans_first_xrc

import pdb

import wx_utils
import xml_utils
import copy

if use_pdfviewer:
    import PyPDF2
    from wx.lib.pdfviewer import pdfViewer, pdfButtonPanel

xml_wildcard = "XML files (*.xml)|*.xml"
tex_wildcard = "TEX files (*.tex)|*.tex"

from block_diagram_xml import bd_XML_element

#from wx_mpl_plot_panels import PlotPanel

block_params = {'arbitrary_input':[], \
                'finite_width_pulse':['t_on','t_off','amp'], \
                'step_input':['t_on','amp'], \
                'TF_block':['num','den','input','c2dmethod'], \
                'DTTMM_block':['xmlpath','input'], \
                'zoh_block':['input'], \
                'summing_block':['input','input2'], \
                'swept_sine':['fmin','fmax','tspan','deadtime','amp'], \
                'serial_plant':['microcontroller','input','sensors','actuators'], \
                'gain_block':['gain','input'], \
                'saturation_block':['max','min','input'], \
                'digital_TF_block':['numz','denz','input'], \
                'PID_block':['kp','ki','kd'], \
                }

tikz_type_map = {'arbitrary_input':'input', \
                'finite_width_pulse':'input', \
                'step_input':'input', \
                'summing_block':'sum', \
                'swept_sine':'input', \
                }
                 

simple_wire_fmt = '\\draw [->] (%s) -- (%s);'
complex_wire_fmt = '\\draw [->] (%s) %s (%s);'


common_props = ['label','caption','position_type','show_outputs',\
                'tikz_block_options','input_ind']
output_opts = ['show_output_arrows','output_distances','output_angles','output_labels']

required_opts = common_props

for key, val in block_params.iteritems():
    val.extend(common_props)
    block_params[key] = val#don't sure if this is necessary since val
                           #is a reference to a list

relative_props = ['relative_block','relative_direction','relative_distance', 'xshift', 'yshift']
abs_props = ['abs_coordinates']

#options to copy when a block is replaced
copy_opts = ['input'] + common_props + output_opts + relative_props + abs_props


sorted_blocks = sorted(block_params.iterkeys())

max_rows = 20#maximum number of rows that should be searched 

tikz_header = r"""\input{drawing_header}
\def \springlength {2.0cm}
\pgfmathparse{\springlength*3}
\let\damperlength\pgfmathresult
\def \groundX {0.0cm}
\def \groundwidth {4cm}
\def \masswidth {2.5cm}
\pgfmathparse{\masswidth/2}
\let\halfmasswidth\pgfmathresult
\def \wallwidth {0.35cm}
\pgfmathparse{\wallwidth/2}
\let\halfwallwidth\pgfmathresult
\pgfmathparse{\masswidth+0.7cm}
\let\wallheight\pgfmathresult
\def \mylabelshift {0.2cm}

\usetikzlibrary{shapes,arrows}
\tikzstyle{block} = [draw, fill=blue!10, rectangle, 
    minimum height=1.0cm, minimum width=1.0cm]
\tikzstyle{multilineblock} = [draw, fill=blue!10, rectangle, 
    minimum height=1.25cm, minimum width=1.0cm, 
    text width=2cm,text centered,midway]
\tikzstyle{sum} = [draw, fill=blue!20, circle, node distance=1.5cm]
\tikzstyle{input} = [emptynode]%[coordinate]
\tikzstyle{output} = [emptynode]
\tikzstyle{myarrow} = [coordinate, node distance=1.5cm]
\tikzstyle{pinstyle} = [pin edge={to-,thin,black}]
\tikzstyle{serialnode} = [inner sep=0.5mm,rectangle,draw=black, fill=black]
\tikzstyle{serialline} = [draw, ->, ultra thick, densely dashed]
\tikzstyle{mylabel} = [emptynode, yshift=\mylabelshift]

"""

def change_ext(pathin, new_ext):
    """Function to change the extension of a path, such as switching
    an *.xml file to a *.tex file."""
    pne, ext = os.path.splitext(pathin)
    if new_ext[0] != '.':
        new_ext = '.' + new_ext
    newpath = pne + new_ext
    return newpath



class block_replacement_dialog(wx.Dialog):
    """Dialog to replace one block with another.  The dialog displays
    the old block name and block type along with a wxChoice control
    for choosing the new block and a text ctrl for specifying the name
    of the new block.  The dialog should return the name and blocktype
    for the new block and then the main app can handle the processing
    by copying parameters as appropriate, replacing all references to
    the old block with the name of the new, and making the change in
    self.blocklist.

    Note that this class uses wxPython xrc to create a dialog within
    an app that is created from a different wxPython xrc file.  I am
    using the wxPython two stage creation approach (sort of, I guess).
    That is what the webpage I found this on said and that is what the
    pre and post stuff does."""
    def __init__(self, parent, old_name='', old_type=''):
        pre = wx.PreDialog() 
        self.PostCreate(pre)
        res = xrc.XmlResource('block_replacement_dialog_xrc.xrc')
        res.LoadOnDialog(self, None, "main_dialog")
        self.parent = parent

        self.Bind(wx.EVT_BUTTON, self.on_ok, xrc.XRCCTRL(self, "ok_button")) 
        self.Bind(wx.EVT_BUTTON, self.on_cancel, xrc.XRCCTRL(self, "cancel_button"))

        self.old_block_name_ctrl = xrc.XRCCTRL(self, "old_block_name_ctrl")
        self.old_block_type_ctrl = xrc.XRCCTRL(self, "old_block_type_ctrl")
        self.old_block_name_ctrl.SetValue(old_name)
        self.old_block_type_ctrl.SetValue(old_type)
        
        self.new_block_choice = xrc.XRCCTRL(self, "new_block_choice")
        self.new_block_choice.SetItems(sorted_blocks)
        wx.EVT_CHOICE(self.new_block_choice, self.new_block_choice.GetId(),
                      self.on_new_block_choice)

        #set default name
        self.new_block_name = xrc.XRCCTRL(self, "new_block_name")
        temp_type = sorted_blocks[0]
        temp_name = self.parent.suggest_block_name(blocktype=temp_type)
        self.new_block_name.SetValue(temp_name)
        ## self.figure_number_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_enter)


    def on_new_block_choice(self, event):
        """Set a recommended name in the text control
        :py:attr:`self.new_block_name` whenever the user makes a
        selection in :py:attr:`self.new_block_choice`.  The suggestion
        is based on the existing blocks in the parent blocklist."""
        blocktype = self.new_block_choice.GetStringSelection()
        name = self.parent.suggest_block_name(blocktype=blocktype)
        self.new_block_name.SetValue(name)


    def on_ok(self, event):
        """Close and return wx.ID_OK if the user clicks OK"""
        self.EndModal(wx.ID_OK)


    def on_cancel(self, event):
        """Close the dialog and return wx.ID_CANCEL"""
        self.EndModal(wx.ID_CANCEL)
        


class MyApp(wx.App):
    def clear_params_grid(self):
        """Assign empty strings to the cell 0 and 1 of the first
        :py:const:`max_rows` rows."""
        self.params_grid.SetCellValue(0,0, "parameter")
        self.params_grid.SetCellValue(0,1, "value")
        for i in range(1,max_rows):
            self.params_grid.SetCellValue(i,0, "")
            self.params_grid.SetCellValue(i,1, "")


    def build_params_dict(self):
        """Build a dictionary from :py:attr:`MyApp.params_grid`.  The
        first column contains the keys and the second column contains
        the values.  The zeroth row is skipped."""
        params_dict = {}
        exit_code = 0
        for i in range(1,max_rows):
            key = self.params_grid.GetCellValue(i,0)
            val = self.params_grid.GetCellValue(i,1)
            key = key.strip()
            val = val.strip()
            val = xml_utils.full_clean(val)
            if not key:
                break
            elif not val:
                ## msg = 'Empty parameters are not allow: %s' % key
                ## wx.MessageBox(msg, 'Parameter Error', 
                ##               wx.OK | wx.ICON_ERROR)
                ## exit_code = 1
                ## break
                val = None#do I really want to make this explicit, or
                          #just leave it blank?
            params_dict[key] = val
        print('params_dict = %s' % params_dict)
        return params_dict
        

    def get_new_block_type(self):
        """Get the string for the current selection of
        :py:attr:`MyApp.new_block_choice` and return it."""
        key = self.new_block_choice.GetStringSelection()
        return key


    def set_param_labels(self):
        """Clear the params grid, get the current block type, find the
        corresponding list of parameters for the block, set the
        parameter keys as the cell values for column 0."""
        self.clear_params_grid()
        key = self.get_new_block_type()
        cur_params = block_params[key]
        for i, item in enumerate(cur_params):
            if item is None:
                item = ''
            self.params_grid.SetCellValue(i+1,0, item)
        

    def append_one_block(self, name, blocktype, params_dict):
        """Append one block to :py:attr:`MyApp.blocklist` and append
        its name to the list box :py:attr:`MyApp.block_list_box`."""
        new_block = bd_XML_element(name=name, \
                                   blocktype=blocktype, \
                                   params=params_dict)
        self.blocklist.append(new_block)
        self.block_list_box.Append(name)


    def on_load_xml(self, event=0):
        """Load a list of blocks from a block diagram xml file"""
        xml_path = wx_utils.my_file_dialog(parent=self.frame, \
                                           msg="Load block list/system from XML", \
                                           kind="open", \
                                           wildcard=xml_wildcard, \
                                           )
        if xml_path:
            print('xml_path = ' + xml_path)
            myparser = block_diagram_xml.block_diagram_system_parser(xml_path)
            myparser.parse()
            myparser.convert()
            for block in myparser.block_list:
                print('block.params = %s' % block.params)
                self.append_one_block(block.name, block.blocktype, block.params)

            self.xml_path = xml_path

        
    def on_add_block(self,event):
        """Respond to the pressing of the Add Block button:
        - get the parameters dict from :py:attr:`MyApp.params_grid`
        - get the blocktype from :py:attr:`MyApp.new_block_choice`
        - get the block name from :py:attr:`MyApp.new_block_name`
        - pass those values to :py:meth:`MyApp.append_one_block`
        """
        #self.plotpanel.change_plot()
        params_dict = self.build_params_dict()
        blocktype = self.get_new_block_type()
        name = self.new_block_name_box.GetValue()
        self.append_one_block(name, blocktype, params_dict)


    def search_and_replace_block_name(self, old_name, new_name):
        """As part of replacing an old block with a new one, we need
        to look for everywhere that the old block name was referenced.
        This most likely occurs as the input to other blocks or as
        their relative blocks."""
        search_params = ['input','input2','relative_block']
        for block in self.blocklist:
            for param in search_params:
                if block.params.has_key(param):
                    if block.params[param] == old_name:
                        block.params[param] = new_name
                        

    def _replace_block(self, ind, new_block):
        """Do the most basic part of replacing a block, i.e. put it in
        :py:attr:`MyApp.blocklist` and put its name in the list box."""
        self.blocklist[ind] = new_block
        self.block_list_box.SetString(ind, new_block.name)


    def on_delete_block(self, event):
        """Remove a block from :py:attr:`MyApp.blocklist`, remove its
        name from the list box, and remove all references to the block
        from other blocks, such as input or relative placement stuff"""
        index = self.block_list_box.GetSelection()
        print('index = ' + str(index))
        if index < 0 or not index:
            wx.MessageBox('you must select a block to replace')
            return

        old_block = self.blocklist[index]
        old_name = old_block.name
        self.block_list_box.Delete(index)
        self.blocklist.pop(index)
        self.search_and_replace_block_name(old_name, None)#<-- or possibly ''
        

    def on_replace_block(self, event):
        """Respond to the replace block button being pushed. Get the
        old block name and type, show the
        :py:class:`block_replacement_dialog`, create the new block,
        copy appropriate parameters from the old block to the new, ..."""
        index = self.block_list_box.GetSelection()
        print('index = ' + str(index))
        if index < 0 or not index:
            wx.MessageBox('you must select a block to replace')
            return
        old_block = self.blocklist[index]
        old_name = old_block.name
        old_type = old_block.blocktype
        my_dialog = block_replacement_dialog(self, old_name=old_name, \
                                             old_type=old_type)

        res = my_dialog.ShowModal()
        if res == wx.ID_OK:
            new_name = my_dialog.new_block_name.GetValue()
            new_type = my_dialog.new_block_choice.GetStringSelection()
            new_params = block_params[new_type]
            None_list = [None]*len(new_params)
            new_dict = dict(zip(new_params, None_list))
            filt_new_keys = [item for item in new_params if item not in copy_opts]
            all_opts_to_copy = copy_opts + filt_new_keys
            for key in all_opts_to_copy:
                if old_block.params.has_key(key):
                    new_dict[key] = old_block.params[key]

            new_block = bd_XML_element(name=new_name, \
                                       blocktype=new_type, \
                                       params=new_dict)
            
            self._replace_block(index, new_block)
            self.search_and_replace_block_name(old_name, new_name)
            
        my_dialog.Destroy()
        

    def on_popup_item_selected(self, event):
        """Respond to a pop-up menu item being selected by setting the
        parameter :py:attr:`self.popup_choice`."""
        item = self.popupmenu.FindItemById(event.GetId())
        text = item.GetText()
        self.popup_choice = text
        

    def create_popup_menu(self, item_list):
        """Create a pop-up menu and bind the selection method of each
        entry to :py:meth:`MyApp.on_popup_item_selected`."""
        self.popupmenu = wx.Menu()
        self.popup_choice = None
        
        for item in item_list:
            menu_item = self.popupmenu.Append(-1, item)
            self.Bind(wx.EVT_MENU, self.on_popup_item_selected, menu_item)
            

    def get_grid_val(self, prop):
        """Find the row corresponding to prop (search down column 0 of
        :py:attr:`MyApp.params_grid` until you find a match) and
        return the corresponding value from column 1)."""
        i = 0
        while i < max_rows:
            attr = self.params_grid.GetCellValue(i, 0)
            if attr == prop:
                val = self.params_grid.GetCellValue(i, 1)
                return val.strip()
            else:
                i += 1


    def set_grid_val(self, prop, value):
        """Search down column 0 of :py:attr:`MyApp.params_grid` until
        you find the row containing prop.  Set the value of column 1
        of that row to value."""
        i = 0
        while i < max_rows:
            attr = self.params_grid.GetCellValue(i, 0)
            if attr == prop:
                self.params_grid.SetCellValue(i, 1, str(value))
                return
            else:
                i += 1
                

    def delete_grid_rows(self, prop_list):
        """Search down column 0 of :py:attr:`MyApp.params_grid`;
        delete any row where the key in column 0 is in
        :py:const:`prop_list`."""
        i = 0
        while i < max_rows:
            prop = self.params_grid.GetCellValue(i, 0)
            if prop in prop_list:
                self.params_grid.DeleteRows(i, 1)
            else:
                i += 1


    def find_first_empty_row(self):
        """Find the first empty row of :py:attr:`MyApp.params_grid`."""
        i = 0
        while i < max_rows:
            prop = self.params_grid.GetCellValue(i, 0)
            if not prop:
                return i
            else:
                i += 1


    def set_cell_append_if_necessary(self, row, col=0, val=''):
        """Set the value of cell (row,col) to val; if row is greater
        than the number of rows in the grid, append one empty row and
        use it instead of the specified row number (row)."""
        n_rows = self.params_grid.GetNumberRows()
        if row >= n_rows:
            self.params_grid.AppendRows(1)
            row = self.find_first_empty_row()
        self.params_grid.SetCellValue(row, col, val)
        
        
    def append_rows(self, prop_list):
        """Append rows, one for each element in :py:const:`prop_list`"""
        start_ind = self.find_first_empty_row()
        for i, prop in enumerate(prop_list):
            self.set_cell_append_if_necessary(i+start_ind, 0, prop)
            

    def get_existing_props(self):
        """Build a list of the properties/keys in column 0; stop when
        you get to an empty row"""
        prop_list = []
        for i in range(1, max_rows):
            prop = self.params_grid.GetCellValue(i, 0)
            if prop:
                prop_list.append(prop)
            else:
                return prop_list

            
    def append_rows_if_missing(self, prop_list):
        """filter :py:const:`prop_list` to find any elements that are
        not already in column 0 of :py:attr:`MyApp.params_grid`;
        append rows for those new elements/keys"""
        existing_rows = self.get_existing_props()
        new_items = [item for item in prop_list if item not in existing_rows]
        self.append_rows(new_items)
        

    def autosize_columns(self, event=0):
        """Autosize the columns of :py:attr:`MyApp.params_grid`"""
        self.params_grid.AutoSizeColumns()


    def on_show_outputs_change(self):
        """Respond to the user changing the option to show the output
        arrows on :py:attr:`MyApp.params_grid`.  Add to the grid
        options for output angles, output labels, whether or not to
        show the arrowheads and so on."""
        show_outs_str = self.get_grid_val('show_outputs')
        show_outs_bool = xml_utils.str_to_bool(show_outs_str)
        if show_outs_bool:
            self.append_rows_if_missing(output_opts)
            #try to determine sensible defaults
            #
            # ? how do I determine info about the active block?
            #
            # output_opts = ['show_output_arrows','output_distances','output_angles']
            output_str = self.get_grid_val('sensors')
            show_arrows = [True]
            out_distances = [1.0]
            out_angles = [0]
            out_labels = ['']
            
            if output_str:
                my_outputs = xml_utils.full_clean(output_str)
                if type(my_outputs) == list:
                    num_out = len(my_outputs)
                    show_arrows = [True]*num_out
                    out_distances = [1.0]*num_out
                    out_labels = ['']*num_out
                    if num_out == 1:
                        out_angles = [0]
                    elif num_out == 2:
                        out_angles = [-30,30]
                    elif num_out == 3:
                        out_angles = [-45,0,45]
                    elif num_out == 4:
                        out_angles =[-45, -15, 15, 45]

            self.set_grid_val('output_angles', out_angles)
            self.set_grid_val('output_distances', out_distances)
            self.set_grid_val('show_output_arrows', show_arrows)
            self.set_grid_val('output_labels', out_labels)
        else:
            self.delete_grid_rows(output_opts)
            

        
    def on_position_type_change(self, old_val):
        """Respond to a change in the position type by adding or
        removing rows in :py:attr:`MyApp.params_grid` related to
        either absolute positioning or relative positioning,
        e.g. adding a rows for the relative block and relative
        direction if the new choice is relative positioning."""
        i = 0
        pos_type = self.get_grid_val('position_type')
        if pos_type == 'absolute':
            del_props = relative_props
            new_props = abs_props
        elif pos_type == 'relative':
            del_props = abs_props
            new_props = relative_props
        print('before delete_grid_rows')
        if pos_type != old_val:
            self.delete_grid_rows(del_props)
        print('after delete_grid_rows')
        self.append_rows_if_missing(new_props)
        print('after append_rows')
        self.autosize_columns()


    def _get_other_blocks(self):
        """Get a list of blocks from the list box that does not
        include the currently selected block.  This is slightly tricky
        because the block whose parameters are being editted may not
        be in the list box yet if it hasn't been added yet"""
        index = self.block_list_box.GetSelection()
        all_blocks = self.block_list_box.GetItems()#this will start out with all the blocks
        #don't pop if the current block isn't actually in the list yet
        other_blocks = copy.copy(all_blocks)
        curname = self.new_block_name_box.GetValue()
        selected_name = self.block_list_box.GetStringSelection()
        if curname==selected_name:
            selected_block = other_blocks.pop(index)
        print('other_blocks = ' + str(other_blocks))
        return other_blocks


    def create_true_false_popup_menu(self):
        """Create a pop-up menu with two options, True and False"""
        self.create_popup_menu(['True','False'])


    def set_xmlpath_from_dialog(self):
        """Set the xmlpath for a DT-TMM element from a file dialog,
        i.e. show the dialog when the user right-clicks on the xmlpath
        row of :py:attr:`MyApp.params_grid`."""
        xml_path = wx_utils.my_file_dialog(parent=self.frame, \
                                           msg="Load DT-TMM system from XML", \
                                           kind="open", \
                                           wildcard=xml_wildcard, \
                                           )
        if xml_path:
            self.set_grid_val('xmlpath', xml_path)

        
    def show_popup_menu(self, event):
        """Show a pop-up menu when the user right-clicks on certain
        rows of :py:attr:`MyApp.params_grid`.  Find the key in column
        0 of the row corresponding to the click and then show the
        corresponding pop-up menu if there is one that corresponds to
        that key.  Essentially do nothing if no corresponding pop-up
        menu is setup for that key (just print a message to the
        command window) - this could be changed to a message box
        dialog if that would be helpful."""
        col = event.GetCol()
        row = event.GetRow()
        attr = self.params_grid.GetCellValue(row,0)
        attr = attr.strip()
        old_val = self.params_grid.GetCellValue(row,1)
        old_val = old_val.strip()
        if attr in ['input', 'relative_block', 'input2']:
            other_blocks = self._get_other_blocks()
            self.create_popup_menu(other_blocks)
        elif attr == 'position_type':
            self.create_popup_menu(['absolute','relative'])
        elif attr == 'microcontroller':
            self.create_popup_menu(['arduino','psoc'])
        elif attr == 'relative_direction':
            self.create_popup_menu(['right of','left of','below of','above of'])
        elif attr == 'show_outputs':
            self.create_true_false_popup_menu()
        elif attr == 'c2dmethod':
            self.create_popup_menu(['tustin','zoh'])
        elif attr == 'xmlpath':
            #we aren't going to actually do a popup menu, so this is
            #slightly tricky
            self.set_xmlpath_from_dialog()
            return
        else:
            print('no popup menu for attribute %s' % attr)
            return

        #actually show the popup menu
        #pos = event.GetPosition()
        #pos = self.frame.ScreenToClient(pos)
        result = self.frame.PopupMenu(self.popupmenu)#, pos)
        print('result = %s' % result)
        if result and hasattr(self, 'popup_choice'):
            if self.popup_choice:
                self.params_grid.SetCellValue(row, col, self.popup_choice)
                
            self.on_cell_change()
            #post-processing
            if attr == 'position_type':
                self.on_position_type_change(old_val)

            elif attr == 'show_outputs':
                self.on_show_outputs_change()
            

    def on_block_name_get_focus(self, event):
        """Store the name in :py:attr:`MyApp.new_block_name_box`
        before the user edits it.  This is done to find the
        corresponding index after the name is changed.

        I don't know if this is as important as it was in data_vis_gui
        because I am only allowing the selecting of one item in the
        list box.

        I guess I still need it to see if the old name was already in
        the list box.  If the user changes the name of a block that
        isn't in the list yet, I don't need any special processing."""
        self.old_name = self.new_block_name_box.GetValue()


    def on_change_block_name(self, event):
        """This method exists to make it possible for the name of an
        existing block to be changed.  This is made slightly
        complicated by the fact that a new block is kind of in limbo
        until the user presses the add block button.  So, this method
        first tries to determine if the change to the name in
        :py:attr:`MyApp.new_block_name_box` corresponds to a block
        that is already in the list box.  If the name that is selected
        in the list box is the same as :py:attr:`MyApp.old_name`, then
        the name of an existing block has been changed."""
        curname = self.new_block_name_box.GetValue()
        selected_name = self.block_list_box.GetStringSelection()
        if (not selected_name) or (curname==selected_name):
            return
        if selected_name == self.old_name:
            #there was a change and we should respond to it
            index = self.block_list_box.GetSelection()
            self.blocklist[index].name = curname
            self.block_list_box.SetString(index, curname)
            


    def on_save(self, event):
        """Save the block diagram system as an XML file"""
        xml_path = wx_utils.my_file_dialog(parent=self.frame, \
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



    def get_filename(self):
        """I don't think this method is actually used.  It has
        probably been replaced by wx_utils.my_file_dialog."""
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
    


    def display_params(self, elem):
        """clear the :py:attr:`MyApp.params_grid` and then load it
        with the keys, values in :py:attr:`elem.params`"""
        params_dict = elem.params
        self.clear_params_grid()
        keys = params_dict.keys()
        keys.sort()
        for i, key in enumerate(keys):
            self.params_grid.SetCellValue(i+1,0, key)
            val = params_dict[key]
            if val is None:
                val = ''
            if type(val) not in [str, unicode]:
                val = str(val)
            self.params_grid.SetCellValue(i+1,1, val)

        self.append_rows_if_missing(required_opts)


    def on_cell_change(self, event=None):
        """If the cell that has been changed corresponds to a
        parameter for and existing block (i.e. the block name in
        :py:attr:`MyApp.new_block_name_box` is in the list box
        already), the update the parameters for the block."""
        block_name = self.new_block_name_box.GetValue()
        existing_blocks = self.block_list_box.GetItems()
        if block_name in existing_blocks:
            #this is an edit on an existing block, so we should update
            #the parameters
            index = existing_blocks.index(block_name)
            params_dict = self.build_params_dict()
            self.blocklist[index].params = params_dict
            
        #self.params_grid.AutoSizeColumns()
        
        
    def on_block_select(self, event):
        """When the user selects a block name in the list box, load
        the name of the block into :py:attr:`MyApp.new_block_name_box`
        and load the block's parameters into :py:attr:`MyApp.params_grid`."""
        curname = self.block_list_box.GetStringSelection()
        index = self.block_list_box.GetSelection()
        print('curname = %s, index = %i' % (curname, index))
        elem = self.blocklist[index]
        self.new_block_name_box.SetValue(elem.name)
        self.display_params(elem)
        self.autosize_columns()

        
    def on_new_block_choice(self, event):
        """When the user selects a new type of block to add, suggest a
        name for the new block and put it in
        :py:attr:`MyApp.new_block_name_box` and then load the
        parameters/keys for that block type into the first column of
        :py:attr:`MyApp.params_grid`"""
        self.set_param_labels()
        new_name = self.suggest_block_name()
        self.new_block_name_box.SetValue(new_name)
        self.autosize_columns()


    def count_blocks_of_type(self, blocktype):
        """Count all of the existing blocks of a certain type as part
        of suggesting a name for a new block."""
        count = 0
        for elem in self.blocklist:
            if elem.blocktype == blocktype:
                count += 1
        return count


    def suggest_block_name(self, blocktype=None):
        """Suggest a name for a new block, such as summing_block7."""
        if blocktype is None:
            blocktype = self.get_new_block_type()
        count = self.count_blocks_of_type(blocktype)
        return blocktype + str(count+1)


    def on_exit(self,event):
        """Close the GUI"""
        self.frame.Close(True)  # Close the frame.



    def find_abs_blocks(self):
        """Find all blocks whose position type is absolute"""
        abs_inds = []

        for i, block in enumerate(self.blocklist):
            if block.params['position_type'] == 'absolute':
                abs_inds.append(i)

        return abs_inds
    

    def find_block(self, block_name):
        """Find the first block whose name matches
        :py:const:`block_name`; there is no check to make sure that
        only one block is a match"""
        for block in self.blocklist:
            if block.name == block_name:
                return block


    def sort_list_box(self):
        """Make sure that the order of the block names in the list box
        corresponds to the order of the underlying list,
        :py:attr:`MyApp.blocklist`.  This is necessary after the
        blocks are sorted for tikz drawing order."""
        for i, block in enumerate(self.blocklist):
            self.block_list_box.SetString(i, block.name)
        
        
    def estimate_coordinates(self):
        """Estimate the coordinates of each block.  Assuming that one
        block is set as absolute and all the rest are relative to one
        another, estimate the coordinates of the relative blocks.
        This will be done to try and determine how complicated wires
        should run, i.e. the difference between |- and -| in tikz
        (first up or down, then over or vice versa).

        Note that you must call block.set_params_as_attrs() for each
        block in :py:attr:`MyApp.blocklist` before calling this
        method.

        Note that this method sorts the blocks so that any
        blocks/nodes used for relative placement should already be
        added before the current block is added."""
        #first, find the abs block and make sure there is only one
        abs_inds = self.find_abs_blocks()
        assert len(abs_inds) > 0, "did not find any absolute blocks in self.blocklist"
        assert len(abs_inds) == 1, "found more than one absolute blocks in self.blocklist"

        #I want to be able to undo this if I need to
        backup_list = copy.copy(self.blocklist)

        
        abs_block = self.blocklist.pop(abs_inds[0])
        sorted_blocks = [abs_block]

        relative_list = [block.params['relative_block'] for block in self.blocklist]

        #now,how to do the sorting?
        #
        # - each block can only have one relative block, so it shouldn't be too bad

        # for each item in sorted_blocks, search for any block that is
        # relative to it and add that block to the list

        i = 0

        while i < len(sorted_blocks):
            curname = sorted_blocks[i].name
            try:
                next_index = relative_list.index(curname)
                relative_list.pop(next_index)
                curblock = self.blocklist.pop(next_index)
                sorted_blocks.append(curblock)
            except ValueError:
                i += 1


        if len(self.blocklist) > 0:
            #sorting failed
            self.blocklist = backup_list
            print('sorting failed')
            return
        else:
            #blocks are correctly sorted
            self.blocklist = sorted_blocks
            #!#!#: sort the blocks in the list box here
            self.sort_list_box()


        for block in self.blocklist:
            #block.set_params_as_attrs()#<--- this should be done before calling this method
            if block.params['position_type'] == 'absolute':
                coords_str = block.params['abs_coordinates']
                coords_str_list = coords_str.split(',')
                coords_str_list = [item.strip() for item in coords_str_list]
                coords = [float(item) for item in coords_str_list]
                assert len(coords) == 2, "Problem with abs coords: %s" % coords_str
                block.coordinates = np.array(coords)
            else:
                rel_name = block.params['relative_block']
                rel_block = self.find_block(rel_name)
                rel_distance = float(block.params['relative_distance'])
                direction = block.params['relative_direction']
                dir_dict = {'right of':np.array([1.0,0]), \
                            'left of':np.array([-1.0,0]), \
                            'above of':np.array([0.0,1.0]), \
                            'below of':np.array([0.0,-1.0]), \
                            }
                shift = rel_distance*dir_dict[direction]
                if hasattr(block, 'xshift') and block.xshift:
                    shift += np.array([block.xshift,0])
                if hasattr(block, 'yshift') and block.yshift:
                    shift += np.array([0,block.yshift])
                
                block.coordinates = rel_block.coordinates + shift

            print('block name: %s' % block.name)
            print('   coordinates: ' + str(block.coordinates))
            

    def create_tikz_block_lines(self):
        """Create the latex code lines that correspond to the block
        nodes. Return the list of latex code lines."""
        mylist = []
        abs_node_pat = '\\node [%s] (%s) at (%s) {%s};'#type, name, coordinates, label
        rel_opt_pat = '%s, %s=%s, node distance=%scm'
        rel_node_pat = '\\node [%s] (%s) {%s};'#type, relative direction, relative block, \
            #node distance, name, label

        for block in self.blocklist:
            blocktype = block.blocktype
            label = block.params['label']
            print('label = ' +str(label))
            if label is None:
                label = ''
            print('label = ' +str(label))                    
            if tikz_type_map.has_key(blocktype):
                tikz_type = tikz_type_map[blocktype]
            else:
                tikz_type = 'block'#generic block
            if block.params['position_type'] == 'absolute':
                mytup = (tikz_type, block.name, block.params['abs_coordinates'], label)
                blockline = abs_node_pat % mytup
            elif block.params['position_type'] == 'relative':
                opt_tup = (tikz_type, block.params['relative_direction'], \
                           block.params['relative_block'], \
                           block.params['relative_distance'])
                opt_str = rel_opt_pat % opt_tup
                if block.params.has_key('tikz_block_options') and block.params['tikz_block_options']:
                    opt_str += ', ' + block.params['tikz_block_options']
                if hasattr(block, 'xshift') and block.xshift:
                    xshift_str = ', xshift=%0.4gcm' % block.xshift
                    opt_str += xshift_str
                if hasattr(block, 'yshift') and block.yshift:
                    yshift_str = ', yshift=%0.4gcm' % block.yshift
                    opt_str += yshift_str
                    
                mytup = (opt_str, block.name, label)
                blockline = rel_node_pat % mytup
            mylist.append(blockline)
            if block.blocktype == 'summing_block':
                sign_label0 = block.name + '_label0'
                sign_label1 = block.name + '_label1'
                line0 = r'\path (%s) ++(-55:0.4) node (%s) {\small{$-$}};' % \
                        (block.name, sign_label0)
                line1 = r'\path (%s) ++(155:0.4) node (%s) {\small{$+$}};' % \
                        (block.name, sign_label1)
                mylist.append(line0)
                mylist.append(line1)


        return mylist



    def create_output_lines(self):
        """For any block whose :py:const:`show_outputs` value is set
        to True, create the corresponding output nodes, lines, and
        (optionally) arrowheads."""
        mylines = ['%output lines/arrows']
        out = mylines.append

        for block in self.blocklist:
            if block.params.has_key('show_outputs'):
                show_outputs = block.params['show_outputs']
                if type(show_outputs) == str:
                    show_outputs = xml_utils.str_to_bool(show_outputs)

                if show_outputs:
                    output_nodes = []
                    # define the output node near the block
                    # define the output node iteself (eventually need to care about direction, I think)
                    #  ? can I get direction out of output angle ?
                    # define the arrow tip node if necessary
                    # draw the output line
                    # draw the output arrow
                    # add the label if given
                    
                    #\node [output] at (serial_plant.-30) (output0) {};
                    basename = block.name
                    num_outputs = block.get_num_outputs()

                    startline = '\\node [output] at (%s.%0.4g) (%s) {};'
                    outline = '\\node [emptynode, %s=%s, node distance=%0.4gcm] (%s) {};'
                    arrowline = '\\draw [->] (%s) -- (%s);'
                    nonarrowline = '\\draw [-] (%s) -- (%s);'
                    labelline = '\\node [mylabel, above of=%s, node distance=0cm] (%s) {%s};'
                    
                    
                    #\node [myarrow, right of=output0, emptynode, node distance=1cm] (serial_plant_out0) {};
                    for i in range(num_outputs):
                        startname = basename + '_out%i_start' % i
                        curangle = float(block.params['output_angles'][i])
                        outputname = basename + '_out%i' % i
                        out(startline % (basename, curangle, startname))
                        if abs(curangle) < 95.0 or curangle > 265.0:
                            direction = 'right of'
                        else:
                            direction = 'left of'

                        curdistance = float(block.params['output_distances'][i])
                        out(outline % (direction, startname, curdistance, outputname))

                        show_arrow = xml_utils.str_to_bool(block.params['show_output_arrows'][i])
                        if show_arrow:
                            arrowname = basename + '_out%i_arrow' % i
                            arrowdist = 0.7# bad, bad hard coding
                            out(outline % (direction, outputname, arrowdist, arrowname))
                            out(arrowline % (startname, arrowname))
                        else:
                            out(nonarrowline % (startname, outputname))

                        curlabel = block.params['output_labels'][i]
                        if curlabel:
                            labelname = basename + '_out%i_label' % i
                            out(labelline % (outputname, labelname, curlabel))

                        output_nodes.append(outputname)

                    block.output_nodes = output_nodes

        return mylines

                        

    def find_input_node(self, block, attr='input'):
        """Find the tikz input node associated with a certain block"""
        input_ind = 0
        if block.params.has_key('input_ind') and block.params['input_ind']:
            input_ind = int(block.params['input_ind'])

        input_block = self.find_block(block.params[attr])
        if hasattr(input_block, 'output_nodes'):
            in_node = input_block.output_nodes[input_ind]
        else:
            in_node = input_block.name
        return in_node


    def additional_input_wire(self, block, attr='input2'):
        """Handle the tikz code for the second input wire to a block
        such as a summing block that has more than one input."""
        #input ind may need to be added here
        input_block = self.find_block(block.params[attr])
        if input_block:
            in_node = self.find_input_node(block, attr=attr)

            input_x, input_y = input_block.coordinates
            my_x, my_y = block.coordinates

            wire_line = None

            if (my_x == input_x) or (my_y == input_y):
                wire_fmt = '--'
            elif my_x < input_x:
                #I am to the left of my input
                if my_y < input_y:
                    wire_fmt = '|-'#vertical first, then horizontal
                else:
                    wire_fmt = '-|'#horizontal first, then, vertical
            else:
                #I am to the right of my input
                wire_fmt = '|-'

            wire_line = complex_wire_fmt % (in_node, wire_fmt, block.name)
            return wire_line
    

    def update_latex(self, tex_path):
        """This is the top level method for updating the latex tikz
        code associated with the block diagram.  It performs all the
        steps necessary to update the latex file, i.e.

        - call :py:meth:`MyApp.estimate_coordinates` for estimating
          the coordinates and sorting the blocks
        - call :py:meth:`MyApp.create_tikz_block_lines` to output the tikz
          lines for each block
        - call :py:meth:`MyApp.create_output_lines` to create lines and
          possibly arrowheads and labels for any block whose
          :py:const:`show_outputs` option is True
        - add the tikz lines for drawing wires
        - dump the tikz code to the latex file
        - return the list of latex lines
        """
        
        mylist = [r'\begin{document}', \
                  r"\begin{tikzpicture}[every node/.style={font=\large}, node distance=2.5cm,>=latex']", \
                  ]

        for block in self.blocklist:
            block.set_params_as_attrs()

        #estimate block coordinates for tricky wires and to get the
        #blocks to ouput in a valid order so all the relative
        #references work
        self.estimate_coordinates()
            
        #draw blocks
        block_list_tikz = self.create_tikz_block_lines()
        mylist.extend(block_list_tikz)
        
        #draw outputs
        output_lines = self.create_output_lines()
        mylist.extend(output_lines)

        
        # Draw wires
        #
        # This will be fairly complicated.
        #
        # Here is example code from a simple file (DC_motor_kp.tex)
        #
        ## \draw [->] (input) -- (sum) node[pos=0.9, yshift=0.25cm] {\small{$+$}};
        ## \draw [->] (sum) -- (controller);
        ## \draw [->] (controller) -- (plant);
        ## \draw [->] (plant) -- (output) node [emptynode] (outarrow) [pos=0.5] {};

        ## \coordinate [below of=plant, node distance=1.5cm] (tmp);
        ## \draw [->] (outarrow) |- (tmp) -| (sum) node[pos=0.9, xshift=0.2cm] {{\small $-$}};

        # draw wires
        mylist.append('')
        mylist.append('% wires')

        
        first = 1
        for block in self.blocklist:
            if block.params.has_key('input') and block.params['input']:
                #the block has an input and should get some kind of wire
                in_node = self.find_input_node(block)
                wire_line = None
                if (block.params['position_type'] == 'relative') and \
                       block.params['input'] == block.params['relative_block']:
                    if hasattr(block,'xshift') and block.xshift:
                        #this is not a simple wire
                        wire_line = None
                    else:
                        #this is a simple wire
                        wire_line = simple_wire_fmt % (in_node, block.name)
                if wire_line is None:
                    #this is a more complicate wire
                    input_block = self.find_block(block.params['input'])
                    input_x, input_y = input_block.coordinates
                    my_x, my_y = block.coordinates
                    if my_x < input_x:
                        #I am to the left of my input
                        if my_y < input_y:
                            wire_fmt = '|-'#vertical first, then horizontal
                        else:
                            wire_fmt = '-|'#horizontal first, then, vertical
                    else:
                        #I am to the right of my input
                        wire_fmt = '|-'

                    wire_line = complex_wire_fmt % (in_node, wire_fmt, block.name)

                if wire_line:
                    mylist.append(wire_line)

            
                if hasattr(block, 'input2'):
                    wire_line2 = self.additional_input_wire(block, attr='input2')
                    if wire_line2:
                        mylist.append(wire_line2)
                    

        # additional wires for summing blocks
        
        mylist.append('\\end{tikzpicture}')
        mylist.append('\\end{document}')
        list_str = '\n'.join(mylist)
        full_str = tikz_header + '\n' + list_str
        f = open(tex_path, 'wb')
        f.writelines(full_str)
        f.close()
        ## \node (input) {$\theta_d$};
        ## \node [sum, right of=input] (sum) {};
        return mylist
        

    def on_save_tikz(self, event=0):
        """Show a dialog for the latex output path and then call
        :py:meth:`MyApp.update_latex` passing in that path."""
        ## mylist = tikz_header.split('\n')#<-- is this good or bad?
        ##                                 #should I create my list first
        ##                                 #and then convert it to a
        ##                                 #string?
        tex_path = wx_utils.my_file_dialog(parent=self.frame, \
                                           msg="Save TiKZ Block Diagram drawing as", \
                                           kind="save", \
                                           wildcard=tex_wildcard, \
                                           )
        if tex_path:
            self.update_latex(tex_path)
        return tex_path


    def on_update_diagram(self, event=0):
        """First update the latex file, then run pdflatex,
        ghostscript, and imagemagick convert to create a nice-looking,
        screen-size block diagram.  Note that on Mac and Linux, my
        script called pdf_to_jpeg_one_page.py is called, so this
        script must be on the system path."""
        wp, hp = self.diagram_panel.Size

        if hasattr(self, 'tex_path'):
            tex_path = self.tex_path
        elif hasattr(self, 'xml_path'):
            tex_path = change_ext(self.xml_path, 'tex')
            self.tex_path = tex_path
        else:
            tex_path = self.on_save_tikz(event)
            
        if tex_path:
            self.update_latex(tex_path)
            
            cmd = 'pdflatex %s' % tex_path
            os.system(cmd)

            if use_pdfviewer:
                pdfpath = change_ext(tex_path, '.pdf')
                self.pdfviewer.LoadFile(pdfpath)

            else:
                curdir = os.getcwd()
                dir, fn = os.path.split(tex_path)
                fno, ext = os.path.splitext(fn)
                pdfname = fno + '.pdf'
            
                os.chdir(dir)
                cmd2 = 'pdf_to_jpeg_one_page.py -r 600 %s' % pdfname
                os.system(cmd2)

                jpgname = fno + '.jpg'
                
                smaller_jpegname = fno + '_smaller.jpg'
                jpgpath = os.path.join(dir, smaller_jpegname)

                #imagemajick resize
                cmd = 'convert ' + jpgname + \
                      ' -filter Cubic -resize 50% -unsharp 0x0.75+0.75+0.008 ' + \
                      smaller_jpegname
                os.system(cmd)
                
                Img = wx.Image(jpgpath, wx.BITMAP_TYPE_JPEG)
                wi, hi = Img.GetSize()

                if (wi > wp) or (hi > hp):
                    ratio_w = wp/float(wi)
                    ratio_h = hp/float(hi)
                    if ratio_w < ratio_h:
                        #width needs more shrinking
                        scale = ratio_w
                    else:
                        scale = ratio_h
                    #override scale for now; then use the menu based override option
                    ## scale = ratio_w
                    ## if hasattr(self, 'diagram_scaling'):
                    ##     if self.diagram_scaling.lower() == 'height':
                    ##         print('in scale, ratio_h = %0.4g' % ratio_h)
                    ##         scale = ratio_h
                    ##     else:
                    ##         scale = ratio_w
                    new_w = int(wi*scale)
                    new_h = int(hi*scale)
                    #Img = Img.Scale(new_w, new_h)#<-- this works but is ugly
                    scaled_jpegname = fno + '_scaled.jpg'
                    scaled_path = os.path.join(dir, scaled_jpegname)
                    size_str = '%ix%i' % (new_w, new_h)
                    cmd = 'convert ' + jpgname + ' -filter Cubic -resize ' + size_str + \
                          ' -unsharp 0x0.75+0.75+0.008 ' + scaled_jpegname
                    os.system(cmd)

                    #Img = wx.Image(smaller_jpegname, wx.BITMAP_TYPE_JPEG)
                    Img = wx.Image(scaled_path, wx.BITMAP_TYPE_JPEG)
                    
                    
                self.static_bitmap.SetBitmap(wx.BitmapFromImage(Img))
                os.chdir(curdir)

            self.frame.Refresh()


    def on_set_width_scaling(self, event):
        """This was an attempt to force the jpeg for the block diagram
        to be scaled to fit the width of the jpeg.  I don't think it
        currently has any affect."""
        self.diagram_scaling = 'width'
        print('self.diagram_scaling = ' + self.diagram_scaling)
        
        
    def on_set_height_scaling(self, event):
        """This was an attempt to force the jpeg for the block diagram
        to be scaled to fit the height of the jpeg.  I don't think it
        currently has any affect."""
        self.diagram_scaling = 'height'
        print('self.diagram_scaling = ' + self.diagram_scaling)
            
        
    def OnInit(self):
        """Intialize the GUI, loading the xml xrc file and binding
        various methods to GUI event."""
        #xrcfile = cbook.get_sample_data('ryans_first_xrc.xrc', asfileobj=False)
        if use_pdfviewer:
            xrcfile = 'block_diagram_gui_xrc.xrc'
        else:
            xrcfile = 'block_diagram_gui_xrc_bitmap_backup.xrc'

        assert os.path.exists(xrcfile), "Could not find xrc file: " + xrcfile
        print('loading', xrcfile)

        self.res = xrc.XmlResource(xrcfile)

        # main frame and panel ---------

        self.frame = self.res.LoadFrame(None,"MainFrame")
        self.panel = xrc.XRCCTRL(self.frame,"MainPanel")
        self.new_block_choice = xrc.XRCCTRL(self.frame, "new_block_choice")
        self.new_block_choice.SetItems(sorted_blocks)
        self.add_block_button = xrc.XRCCTRL(self.frame,"add_block_button")
        wx.EVT_BUTTON(self.add_block_button, self.add_block_button.GetId(),
                      self.on_add_block)
        wx.EVT_CHOICE(self.new_block_choice, self.new_block_choice.GetId(),
                      self.on_new_block_choice)

        self.load_button = xrc.XRCCTRL(self.frame, "load_button")
        wx.EVT_BUTTON(self.load_button, self.load_button.GetId(),
                      self.on_load_xml)
        self.save_button = xrc.XRCCTRL(self.frame, "save_button")
        wx.EVT_BUTTON(self.save_button, self.save_button.GetId(),
                      self.on_save)

        
        self.replace_block_button = xrc.XRCCTRL(self.frame, "replace_block_button")
        wx.EVT_BUTTON(self.replace_block_button, self.replace_block_button.GetId(),
                      self.on_replace_block)

        self.delete_block_button = xrc.XRCCTRL(self.frame, "delete_block_button")
        wx.EVT_BUTTON(self.delete_block_button, self.delete_block_button.GetId(),
                      self.on_delete_block)
        
        self.frame.Bind(wx.EVT_MENU, self.on_exit, \
                       id=xrc.XRCID('exit_menu'))       
        self.frame.Bind(wx.EVT_MENU, self.on_save, \
                       id=xrc.XRCID('save_menu'))       
        self.frame.Bind(wx.EVT_MENU, self.on_load_xml, \
                       id=xrc.XRCID('load_menu'))
        self.frame.Bind(wx.EVT_MENU, self.on_save_tikz, \
                        id=xrc.XRCID('save_tikz_menu'))
        self.frame.Bind(wx.EVT_MENU, self.on_update_diagram, \
                        id=xrc.XRCID('update_diagram_menu'))
        self.frame.Bind(wx.EVT_MENU, self.on_set_width_scaling, \
                        id=xrc.XRCID('force_width_scaling_menu'))
        self.frame.Bind(wx.EVT_MENU, self.on_set_height_scaling, \
                        id=xrc.XRCID('force_height_scaling_menu'))
        #self.params_panel = xrc.XRCCTRL(self.frame, "params_panel")
        #self.params_grid = gridlib.Grid(self.params_panel)
        self.accel_tbl = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('O'), xrc.XRCID('load_menu')),
                                             ])
        self.frame.SetAcceleratorTable(self.accel_tbl)

        
        self.params_grid = xrc.XRCCTRL(self.frame, "params_grid")
        self.params_grid.CreateGrid(max_rows,2)
        ## self.params_grid.GetGridWindow().Bind(wx.EVT_RIGHT_DOWN, self.show_popup_menu)
        self.params_grid.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK,
                              self.show_popup_menu)
        self.params_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGE, \
                              self.on_cell_change)
        self.set_param_labels()
        ## sizer_g = wx.BoxSizer(wx.VERTICAL)
        ## sizer_g.Add(self.params_grid, 1, wx.EXPAND)
        ## self.params_panel.SetSizer(sizer_g)

        self.static_bitmap = xrc.XRCCTRL(self.frame, "static_bitmap")
        plot_container = xrc.XRCCTRL(self.frame,"plot_container_panel")
        if use_pdfviewer:
            viewer_flags = wx.HSCROLL|wx.VSCROLL|wx.SUNKEN_BORDER|wx.EXPAND
            self.pdfviewer = pdfViewer(plot_container, \
                                       wx.NewId(), wx.DefaultPosition, \
                                       wx.DefaultSize, \
                                       viewer_flags)
            self.pdfviewer.UsePrintDirect = False

        self.diagram_panel = plot_container
        mycontrol = self.static_bitmap
        self.w_init, self.h_init = mycontrol.GetSize()
        #self.pdfviewer.SetSizerProps(expand=True, proportion=1)
        
        ## sizer = wx.BoxSizer(wx.VERTICAL)

        ## # matplotlib panel itself
        ## self.plotpanel = PlotPanel(plot_container)
        ## self.plotpanel.init_plot_data()

        ## # wx boilerplate
        ## sizer.Add(self.plotpanel, 1, wx.EXPAND)
        ## plot_container.SetSizer(sizer)
        ## #self.plotpanel.SetMinSize((900,600))

        self.new_block_name_box = xrc.XRCCTRL(self.frame, "block_name_ctrl")
        self.new_block_name_box.SetMinSize((200,-1))
        self.new_block_name_box.Bind(wx.EVT_KILL_FOCUS, self.on_change_block_name)
        self.new_block_name_box.Bind(wx.EVT_SET_FOCUS, self.on_block_name_get_focus)
        self.new_block_name_box.Bind(wx.EVT_TEXT_ENTER, self.on_change_block_name)
        
        self.blocklist = []
        new_name = self.suggest_block_name()
        self.new_block_name_box.SetValue(new_name)

        self.block_list_box = xrc.XRCCTRL(self.frame, "block_list_box")
        self.block_list_box.SetMinSize((200,-1))

        wx.EVT_LISTBOX(self.block_list_box, self.block_list_box.GetId(),
                       self.on_block_select)


        
        self.frame.SetClientSize((800,700))
        self.frame.Show(1)
        self.SetTopWindow(self.frame)
        return True


if __name__ == '__main__':
    app = MyApp(0)
    app.MainLoop()

