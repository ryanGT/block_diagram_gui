import xml.etree.ElementTree as ET
## tree = ET.parse('test.xml')
## root = tree.getroot()

import DTTMM_xml
import DTTMM
import numpy

import pdb

class_map = {'dc_motor':DTTMM.DT_TMM_DC_motor_4_states, \
             'torsional_spring_damper':DTTMM.DT_TMM_TSD_4_states, \
             'rigid_mass':DTTMM.DT_TMM_rigid_mass_4_states, \
             'transverse_force':DTTMM.transverse_forcing_element_4_states, \
             #'beam':['mu','L','EI','N'], \
             }

from IPython.core.debugger import Pdb

             
def find_child(element, name):
    found = 0
    for child in element.getchildren():
        if child.tag == name:
            found = 1
            break

    if found:
        return child
    else:
        raise ValueError, "did not find child with tag name %s in %s" % \
              (name, element.getchildren())


def children_to_dict(element):
    mydict = {}
    for child in element.getchildren():
        key = child.tag.strip()
        val = child.text.strip()
        mydict[key] = val
    return mydict
    

def get_params(element):
    params_xml = find_child(element, 'params')
    params = children_to_dict(params_xml)
    return params


def get_num_params(params, sys_num_params):
    params_out = {}

    for key, val in params.iteritems():
        valout = None
        try:
            valout = float(val)
        except ValueError:
            valout = sys_num_params[val]

        assert valout is not None, 'problem with %s:%s' % (key,val)
        params_out[key] = valout

    return params_out
    

def discretize_beam(beam, beam_params):
    N = beam_params['N']
    mu = beam_params['mu']
    L = beam_params['L']
    EI = beam_params['EI']
    L2 = L/N#length of each discretized beam section
    L2b = L/(N-1)#number of springs
    k2 = EI/L2b#<-- using L2b seems to improve the agreement with the
               #continuous beam model
    m2 = mu*L2
    h = beam_params['t']#beam thickness1.0/32#inches
    I2 = (1.0/12)*m2*(L2**2+h**2)#h is the height or thickness of the beam

    if beam_params.has_key('damping_factor'):
        b2 = k2*beam_params['damping_factor']
    else:
        b2 = 0.0
    m2_params = {'m':m2, 'L':L2, 'r':L2*0.5, 'I': I2}
    tsd2_params = {'k':k2, 'b':b2}

    #pdb.set_trace()
    rigid_mass0 = DTTMM.DT_TMM_rigid_mass_4_states(**m2_params)

    beam_list = [rigid_mass0]

    N1 = int(N-1)
    
    for i in range(N1):
        TSD_i = DTTMM.DT_TMM_TSD_4_states(**tsd2_params)
        beam_list.append(TSD_i)
        mass_i = DTTMM.DT_TMM_rigid_mass_4_states(**m2_params)
        beam_list.append(mass_i)

    return beam_list


    
class DTTMM_xml_parser(object):
    def get_elements(self):
        self.element_list_xml = find_child(self.root, 'elements')


    def get_sensors(self):
        self.sensor_list_xml = find_child(self.root, 'sensors')


    def get_actuators(self):
        self.actuator_list_xml = find_child(self.root, 'actuators')


    def parse_elements(self):
        parsed_element_list = []
        for element in self.element_list_xml.getchildren():
            name = element.attrib['name']
            elemtype = element.tag
            params = get_params(element)
            parsed_elem = DTTMM_xml.DTTMM_XML_element(name=name, \
                                                      elemtype=elemtype, \
                                                      params=params)
            parsed_element_list.append(parsed_elem)
            
        self.parsed_element_list = parsed_element_list


    def parse_sensors(self):
        parsed_sensor_list = []
        for sensor in self.sensor_list_xml.getchildren():
            name = sensor.attrib['name']
            kwargs = children_to_dict(sensor)
            cur_sensor = DTTMM_xml.sensor_XML_element(name=name, **kwargs)
            parsed_sensor_list.append(cur_sensor)
        self.parsed_sensor_list = parsed_sensor_list


    def parse_actuators(self):
        parsed_actuator_list = []
        for actuator in self.actuator_list_xml.getchildren():
            name = actuator.attrib['name']
            kwargs = children_to_dict(actuator)
            cur_actuator = DTTMM_xml.actuator_XML_element(name=name, **kwargs)
            parsed_actuator_list.append(cur_actuator)
        self.parsed_actuator_list = parsed_actuator_list

        
    def parse(self):
        self.get_elements()
        self.get_sensors()
        self.get_actuators()
        self.parse_elements()
        self.parse_sensors()
        self.parse_actuators()


    def convert(self, numeric_parameters={}):
        """Convert the parsed XML representation into a DTTMM system
        model."""
        elemlist = []
        elem_name_dict = {}
        #pdb.set_trace()
        for xml_element in self.parsed_element_list:
            name = xml_element.name
            num_params = get_num_params(xml_element.params, \
                                        numeric_parameters)
            if xml_element.elemtype == 'beam':
                beam_list = discretize_beam(xml_element, num_params)
                elemlist.extend(beam_list)
                elem_name_dict[name] = beam_list[-1]
            else:
                myclass = class_map[xml_element.elemtype]
                cur_elem = myclass(**num_params)
                elemlist.append(cur_elem)
                elem_name_dict[name] = cur_elem

        #set the prev_element property for each element
        prevelem = elemlist[0]
        for elem in elemlist[1:]:
            elem.prev_element = prevelem
            prevelem = elem
                
        self.elemlist = elemlist
        self.elem_name_dict = elem_name_dict

        #sensors
        sensor_list = []
        for sensor in self.parsed_sensor_list:
            name1 = sensor.elem1
            elem1 = self.elem_name_dict[name1]
            name2 = sensor.elem2
            if name2 == 'None':
                elem2 = None
            else:
                elem2 = self.elem_name_dict[name2]
            if hasattr(sensor, 'gain'):
                try:
                    gain = float(sensor.gain)#actually, I think this is already handled
                except:
                    if type(sensor.gain) == str and numeric_parameters.has_key(sensor.gain):
                        gain = numeric_parameters[sensor.gain]
                    else:
                        gain = sensor.gain
            else:
                gain = 1.0
            sensor_name = sensor.name
            signal = sensor.signal
            sensor_type = sensor.sensor_type
            sensor_obj = DTTMM.DT_TMM_Sensor(sensor_name, \
                                             signal=signal, \
                                             sensor_type=sensor_type, \
                                             elem1=elem1, \
                                             elem2=elem2, \
                                             gain=gain)
            sensor_list.append(sensor_obj)

        self.sensor_list = sensor_list

        #actuators
        act_list = []
        for act in self.parsed_actuator_list:
            name = act.name
            elem = self.elem_name_dict[name]
            signal = act.signal
            act_obj = DTTMM.DT_TMM_Actuator(element=elem, \
                                            name=name, \
                                            attr=signal)
            act_list.append(act_obj)

        self.act_list = act_list
            
        return elemlist
    
    
    def __init__(self, filename):
        self.filename = filename
        self.tree = ET.parse(filename)
        self.root = self.tree.getroot()
        self.parse()


if __name__ == '__main__':


    ## p = JVC_model_dict['p_act1']
    ## g = JVC_model_dict['num_act']/p
    ## dt = 1.0/500
    ## JVC_model_dict['g'] = g
    ## JVC_model_dict['p'] = p
    ## JVC_model_dict['dt'] = dt
    ## JVC_model_dict['t_beam'] = t_m
    from JVC_params import JVC_model_dict
    
    myparser = DTTMM_xml_parser('test.xml')
    myparser.convert(JVC_model_dict)

    #dt = 1.0/1000
    dt = 1.0/500.0
    

    import control_utils
    u, t = control_utils.create_swept_sine_signal(20,tspan=10.0, dt=1.0/500,deadtime=1.0)

    mysys = DTTMM.DT_TMM_System_from_XML_four_states(myparser.elemlist, \
                                                     sensors=myparser.sensor_list, \
                                                     actuators=myparser.act_list, \
                                                     dt=dt)

    
    N = len(u)
    ol_v = numpy.zeros(N)
    ol_v[10:20] = 125.0
    mysys.init_sim(N)

    input_signal = u
    for i, u_i in enumerate(input_signal):
        if i > 0:
            mysys.run_sim_one_step(i, [u_i], int_case=1)


    from matplotlib.pyplot import *

    figure(1)
    clf()
    subplot(311)
    plot(mysys.t, input_signal)

    subplot(312)
    plot(mysys.t, mysys.sensors[0].signal_vect)

    subplot(313)
    plot(mysys.t, mysys.sensors[1].signal_vect)


    show()
    ## def __init__(self, element_list, N_states, \
    ##              N=None, dt=None, int_case=1, \
    ##              initial_conditions=None, \
    ##              unknown_params=[], \
    ##              param_limits={}):


    #I need to convert sensor and input descriptions into something I
    #can use with the DTTMM system.  I think this needs to include a
    #sensors class with a read method.  The sensor class would need to
    #know elem1 and elem2 and the parameter to read.  The read method
    #would take the for loop index i.  It would then call
    #getattr(elem1,parameter)[i] and optionally
    #getattr(elem2,parameter)[i].
    #
    #The system class should also have a set_input method that sets
    #the correct parameter[i] at each time step for the input
    #parameter of the input element.
    #
    #The parser/converter needs to convert the element name in the xml
    #to the correct element in elemlist (or the names need to be
    #passed on to the final DTTMM model) in order for the sensor and
    #actuator names to work.
