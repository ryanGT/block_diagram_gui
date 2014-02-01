import xml.etree.ElementTree as ET
## tree = ET.parse('test.xml')
## root = tree.getroot()

import xml_utils
import block_diagrams
import block_diagram_xml

class_map1  = {#'swept_sine':block_diagrams.swept_sine, \
               #'summing_block':block_diagrams.summing_block, \
               #'DTTMM_block':block_diagram_xml.DTTMM_block, \
               }


#could all of this be replaced by a bunch of blocktype:getattr(block_diagrams, blocktype)?
class_map2 = {'swept_sine':block_diagrams.swept_sine, \
              'summing_block':block_diagrams.summing_block, \
              'DTTMM_block':block_diagrams.DTTMM_block, \
              'finite_width_pulse':block_diagrams.finite_width_pulse, \
              'arbitrary_input':block_diagrams.arbitrary_input, \
              'zoh_block':block_diagrams.zoh_block, \
              'serial_plant_arduino':block_diagrams.serial_plant_block_arduino, \
              'serial_plant_psoc':block_diagrams.serial_plant_block_psoc, \
              'TF_block':block_diagrams.TF_block, \
              'gain_block':block_diagrams.gain_block, \
              'saturation_block':block_diagrams.saturation_block, \
              'digital_TF_block':block_diagrams.digital_TF_block, \
              'PID_block':block_diagrams.PID_block, \
              #'beam':['mu','L','EI','N'], \
              }


import parse_DTTMM_xml

from xml_utils import find_child, children_to_dict, \
     get_params

from IPython.core.debugger import Pdb


def sub_num_into_clean_params(clean_params, num_params):
    for key, val in clean_params.iteritems():
        if type(val) == str and num_params.has_key(val):
            clean_params[key] = num_params[val]

    return clean_params


class system_xml_parser(object):
    def get_blocks(self):
        self.block_list_xml = find_child(self.root, 'blocks')


    def parse_blocks(self):
        parsed_block_list = []
        for block in self.block_list_xml.getchildren():
            tagname = block.tag
            # apparently I started using two different xml
            # protocols as some point
            if tagname.lower() != 'block' and block.attrib:
                name = block.attrib['name']
                blocktype = block.tag
                params = get_params(block)
            elif tagname.lower() == 'block':
                # I guess this is the newer style based on
                # xml_utils and block_diagram_gui.py
                name = xml_utils.get_child_value(block,'name')
                blocktype = xml_utils.get_child_value(block,\
                                                      'blocktype')
                params = xml_utils.get_params(block)
            #kwargs = children_to_dict(block)
            if class_map1.has_key(blocktype):
                myclass = class_map1[blocktype]
            else:
                myclass = block_diagram_xml.bd_XML_element
            cur_block = myclass(name=name, \
                                blocktype=blocktype, \
                                params=params)
            cur_block.cleanup_params()
            parsed_block_list.append(cur_block)
        self.parsed_block_list = parsed_block_list



    def set_parsed_block_list(self, blocklist):
        """This is for use with converting a blocklist from some other
        parser, such as from
        block_diagram_xml.block_diagram_system_parser"""
        self.parsed_block_list = blocklist
        for block in self.parsed_block_list:
            block.cleanup_params()


    def _convert_blocks(self, numeric_parameters={}):
        blocklist = []
        block_name_dict = {}
        for xml_block in self.parsed_block_list:
            name = xml_block.name
            blocktype = xml_block.blocktype
            myclass = class_map2[blocktype]
            if numeric_parameters:
                clean_params2 = sub_num_into_clean_params(xml_block.clean_params, \
                                                          numeric_parameters)
            else:
                clean_params2 = xml_block.clean_params
            curblock = myclass(name=name, **clean_params2)   
            if hasattr(xml_block, 'input'):
                curblock.input_name = xml_block.input
            if hasattr(xml_block, 'input2'):
                curblock.input2_name = xml_block.input2
            elif xml_block.clean_params.has_key('input2'):
                curblock.input2_name = xml_block.clean_params['input2']
            if hasattr(curblock, 'convert'):
                if callable(curblock.convert):
                    curblock.convert(numeric_parameters=numeric_parameters)
            blocklist.append(curblock)
            block_name_dict[name] = curblock


        for block in blocklist:
            if block.input_name is not None:
                in_block = block_name_dict[block.input_name]
                block.input = in_block
            if hasattr(block, 'input2_name'):
                in2_block = block_name_dict[block.input2_name]
                block.input2 = in2_block


        self.blocklist = blocklist
        self.block_name_dict = block_name_dict
        

    def _create_bd_sys(self):
        sys = block_diagrams.block_diagram_system(blocks=self.blocklist)
        return sys


    def convert(self, numeric_parameters={}):
        """Convert the parsed XML representation into a block diagram
        system model."""
        self._convert_blocks(numeric_parameters=numeric_parameters)
        return self._create_bd_sys()


    def parse(self):
        self.get_blocks()
        self.parse_blocks()

        
    def __init__(self, xmlpath=None):
        self.xmlpath = xmlpath
        if xmlpath is not None:
            self.tree = ET.parse(xmlpath)
            self.root = self.tree.getroot()
            self.parse()


class exp_xml_system_parser(system_xml_parser):
    def _create_bd_sys(self):
        sys = block_diagrams.exp_block_diagram_system(blocks=self.blocklist)
        return sys


    def convert(self, numeric_parameters={}):
        """Convert the parsed XML representation into a block diagram
        system model."""
        self._convert_blocks(numeric_parameters=numeric_parameters)
        return self._create_bd_sys()


class psoc_exp_xml_system_parser(exp_xml_system_parser):
    def _create_bd_sys(self):
        sys = block_diagrams.psoc_exp_block_diagram_system(blocks=self.blocklist)
        return sys
    

def run_xml_sim(xmlpath, t, u, input_block_name, \
                numeric_parameters={}):
    sys = system_xml_parser(xmlpath)
    sim_sys = sys.convert(numeric_parameters=numeric_parameters)
    input_block = sim_sys.get_block(input_block_name)
    input_block.set_u(u)
    N = len(t)
    dt = t[1]-t[0]
    sim_sys.prep_for_sim(N, t, dt)

    sim_sys.sort_blocks()
    sim_sys.Run_Simulation()

    return sim_sys

                

if __name__ == '__main__':
    from matplotlib.pyplot import *
    from scipy import *
    import txt_mixin
    
    #sys = system_xml_parser('test_OL_system.xml')
    #sys = system_xml_parser('test_OL_pulse_system.xml')
    #sys = system_xml_parser('test_OL_arb_input.xml')
    sys = system_xml_parser('P_control_arb_input.xml')
    from JVC_params import JVC_model_dict
    JVC_model_dict['k_motor'] = 1.0
    JVC_model_dict['b_motor'] = 0.1

    sim_sys = sys.convert(numeric_parameters=JVC_model_dict)
    #df_path = 'PSoC_data/OL_pulse_test_sys_check_SLFR_RTP_OL_Test_uend=0.txt'
    df_path = 'PSoC_data/step_response_kp_1_amp_200.txt'
    import txt_data_processing
    df = txt_data_processing.Data_File(df_path)
    
    input_case = 2

    filename = 'sim_data.txt'
    if input_case == 1:
        t = df.t
        u = df.u
        filename = 'sim_step_response.txt'
    elif input_case == 2:
        import control_utils
        u, t = control_utils.create_swept_sine_signal(fmax=20.0, fmin=0.0, \
                                                      tspan=10.0, dt=1.0/500, \
                                                      deadtime=0.5)
        filename = 'sim_swept_sine.txt'
        
    input_block = sim_sys.get_block('input')
    input_block.set_u(u)
    #t = arange(0,7,0.002)
    ## swept_sine = sim_sys.get_block('swept_sine')
    ## u, t = swept_sine.build_u_and_t()
    N = len(t)
    dt = t[1]-t[0]
    sim_sys.prep_for_sim(N, t, dt)

    sim_sys.sort_blocks()
    sim_sys.Run_Simulation()
    dttmm_sys = sim_sys.get_block('SFLR')
    accel = dttmm_sys.sys.sensors[-1]
    encoder = dttmm_sys.sys.sensors[0]

    enc_counts = encoder.signal_vect#*JVC_model_dict['H']
    u = sim_sys.blocks[0].output

    sum1 = sim_sys.get_block('sum1')
    v = sum1.output
    
    figure(1)
    clf()
    plot(t, u)

    figure(2)
    clf()
    plot(t, enc_counts)
    plot(t, dttmm_sys.output[:,0])#*JVC_model_dict['H'])
    plot(df.t, df.theta)

    figure(3)
    clf()
    plot(t, accel.signal_vect)
    plot(t, dttmm_sys.output[:,1])    
    plot(df.t, df.a)


    data = column_stack([t, u, v, enc_counts, accel.signal_vect])
    txt_mixin.dump_delimited(filename, data, labels=['t','u','v','theta','a'])

    show()
