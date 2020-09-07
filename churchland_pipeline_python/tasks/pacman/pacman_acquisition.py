import datajoint as dj
from ... import lab, acquisition, equipment, reference
from ...utilities import speedgoat
import os, re

schema = dj.schema('churchland_analyses_pacman_acquisition')

# -------------------------------------------------------------------------------------------------------------------------------
# LEVEL 0
# -------------------------------------------------------------------------------------------------------------------------------

@schema 
class ArmPosture(dj.Lookup):
    definition = """
    # Arm posture
    -> lab.Monkey
    posture_id: tinyint unsigned # unique posture ID number
    ---
    elbow_angle: tinyint unsigned # elbow flexion angle in degrees (0 = fully flexed)
    shoulder_angle: tinyint unsigned # shoulder flexion angle in degrees (0 = arm by side)
    """
    
    contents = [
        ['Cousteau', 1, 90, 65],
        ['Cousteau', 2, 90, 40],
        ['Cousteau', 3, 90, 75]
    ]

@schema
class ConditionParams(dj.Lookup):
    """
    Task condition parameters. Each condition consists of a unique combination of force, 
    stimulation, and general target trajectory parameters. For conditions when stimulation
    was not delivered, stimulation parameters are left empty. Each condition also includes
    a set of parameters unique to the particular type of target trajectory.
    """

    definition = """
    condition_id: smallint unsigned
    """

    class Force(dj.Part):
        definition = """
        # Force parameters
        -> master
        force_id: smallint unsigned # ID number
        ---
        force_max: tinyint unsigned # maximum force (N)
        force_offset: decimal(5,4) # baseline force (N)
        force_inverted: bool # if false, then pushing on the load cell moves PacMan upwards onscreen
        """
        
    class Stim(dj.Part):
        definition = """
        # CereStim parameters
        -> master
        stim_id: smallint unsigned # ID number
        ---
        stim_current: smallint unsigned # stim current (uA)
        stim_electrode: smallint unsigned # stim electrode number
        stim_polarity: tinyint unsigned # stim polarity
        stim_pulses: tinyint unsigned # number of pulses in stim train
        stim_width1: smallint unsigned # first pulse duration (us)
        stim_width2: smallint unsigned # second pulse duration (us)
        stim_interphase: smallint unsigned # interphase duration (us)
        stim_frequency: smallint unsigned # stim frequency (Hz)
        """

    class Target(dj.Part):
        definition = """
        # Target force profile parameters
        -> master
        target_id: smallint unsigned # ID number
        ---
        target_duration: decimal(5,4) # target duration (s)
        target_offset: decimal(5,4) # offset from baseline [proportion playable window]
        target_pad: decimal(5,4) # duration of "padding" dots leading into and out of target (s)
        """
        
    class Static(dj.Part):
        definition = """
        # Static force profile parameters
        -> master.Target
        """
        
    class Ramp(dj.Part):
        definition = """
        # Linear ramp force profile parameters
        -> master.Target
        ---
        target_amplitude: decimal(5,4) # target amplitude [proportion playable window]
        """
        
    class Sine(dj.Part):
        definition = """
        # Sinusoidal (single-frequency) force profile parameters
        -> master.Target
        ---
        target_amplitude: decimal(5,4) # target amplitude [proportion playable window]
        target_frequency: decimal(5,4) # sinusoid frequency [Hz]
        """
        
    class Chirp(dj.Part):
        definition = """
        # Chirp force profile parameters
        -> master.Target
        ---
        target_amplitude: decimal(5,4) # target amplitude [proportion playable window]
        target_frequency_init: decimal(5,4) # initial frequency [Hz]
        target_frequency_final: decimal(5,4) # final frequency [Hz]
        """
        
    @classmethod
    def parseparams(self, params):
        """
        Parses a dictionary constructed from a set of Speedgoat parameters (written
        on each trial) in order to extract the set of attributes associated with each
        part table of ConditionParams
        """

        # force attributes
        force_attr = dict(
            force_max = params['frcMax'], 
            force_offset = params['frcOff'],
            force_inverted = params['frcPol']==-1
        )

        cond_rel = ConditionParams.Force

        # stimulation attributes
        if params.get('stim')==1:
                
            prog = re.compile('stim([A-Z]\w*)')
            stim_attr = {
                'stim_' + prog.search(k).group(1).lower(): v
                for k,v in zip(params.keys(), params.values()) 
                if prog.search(k) is not None and k != 'stimDelay'
                }

            cond_rel = cond_rel * ConditionParams.Stim
            
        else:
            stim_attr = dict()
            cond_rel = cond_rel - ConditionParams.Stim

        # target attributes
        targ_attr = dict(
            target_duration = params['duration'],
            target_offset = params['offset'][0],
            target_pad = params['padDur']
        )

        # target type attributes
        if params['type'] == 'STA':

            targ_type_rel = ConditionParams.Static
            targ_type_attr = dict()

        elif params['type'] == 'RMP':

            targ_type_rel = ConditionParams.Ramp
            targ_type_attr = dict(
                target_amplitude = params['amplitude'][0]
            )

        elif params['type'] == 'SIN':

            targ_type_rel = ConditionParams.Sine
            targ_type_attr = dict(
                target_amplitude = params['amplitude'][0],
                target_frequency = params['frequency'][0]
            )

        elif params['type'] == 'CHP':

            targ_type_rel = ConditionParams.Chirp
            targ_type_attr = dict(
                target_amplitude = params['amplitude'][0],
                target_frequency_init = params['frequency'][0],
                target_frequency_final = params['frequency'][1]
            )

        cond_rel = cond_rel * ConditionParams.Target * targ_type_rel

        # aggregate all parameter attributes into a dictionary
        cond_attr = dict(
            Force = force_attr,
            Stim = stim_attr,
            Target = targ_attr,
            TargetType = targ_type_attr
        )

        return cond_attr, cond_rel, targ_type_rel
    
@schema
class TaskState(dj.Lookup):
    definition = """
    # Simulink Stateflow task state IDs and names
    task_state_id: tinyint unsigned # task state ID number
    ---
    task_state_name: varchar(255) # unique task state name
    """
    
# -------------------------------------------------------------------------------------------------------------------------------
# LEVEL 1
# -------------------------------------------------------------------------------------------------------------------------------
    
@schema
class Behavior(dj.Imported):
    definition = """
    # Behavioral data imported from Speedgoat
    -> acquisition.BehaviorRecording
    ---
    """
    
    class Condition(dj.Part):
        definition = """
        # Condition data
        -> master
        -> ConditionParams
        """

    class Trial(dj.Part):
        definition = """
        # Trial data
        -> master
        trial_number: smallint unsigned # trial number (within session)
        ---
        -> Behavior.Condition
        save_tag: tinyint unsigned # save tag
        successful_trial: bool
        simulation_time: longblob # absolute simulation time
        task_state: longblob # task state IDs
        force_raw_online: longblob # amplified output of load cell
        force_filt_online: longblob # online (boxcar) filtered and normalized force used to control Pac-Man
        reward: longblob # TTL signal indicating the delivery of juice reward
        photobox: longblob # photobox signal
        stim = null: longblob # TTL signal indicating the delivery of a stim pulse
        """
        
    def make(self, key):

        # insert entry to Behavior table
        Behavior.insert1(key)

        # local path to behavioral summary file and sample rate
        behavior_summary_path, fs = (acquisition.BehaviorRecording & key).fetch1('behavior_summary_file_path', 'behavior_sample_rate')
        behavior_summary_path = (reference.EngramPath & {'engram_tier': 'locker'}).ensurelocal(behavior_summary_path)

        # path to all behavior files
        behavior_path = os.path.sep.join(behavior_summary_path.split(os.path.sep)[:-1] + [''])

        # identify task controller
        task_controller_hardware = (acquisition.Task & acquisition.Session & key).fetch1('task_controller_hardware')

        if task_controller_hardware == 'Speedgoat':

            # load summary file
            summary = speedgoat.readtaskstates(behavior_summary_path)

            # update task states
            TaskState.insert(summary, skip_duplicates=True)

            # parameter and data files
            behavior_files = os.listdir(behavior_path)
            param_files = [f for f in behavior_files if f.endswith('.params')]
            data_files = [f for f in behavior_files if f.endswith('.data')]

            # populate conditions from parameter files
            for f_param in param_files:

                # trial number
                trial = re.search(r'beh_(\d*)',f_param).group(1)

                # ensure matching data file exists
                if f_param.replace('params','data') not in data_files:

                    print('Missing data file for trial {}'.format(trial))

                else:
                    # read params file
                    params = speedgoat.readtrialparams(behavior_path + f_param)

                    # extract condition attributes from params file
                    cond_attr, cond_rel, targ_type_rel = ConditionParams.parseparams(params)

                    # aggregate condition part table parameters into a single dictionary
                    all_cond_attr = {k: v for d in list(cond_attr.values()) for k, v in d.items()}
                    
                    # insert new condition if none exists
                    if not(cond_rel & all_cond_attr):

                        # insert condition table
                        if not(ConditionParams()):
                            new_cond_id = 0
                        else:
                            all_cond_id = ConditionParams.fetch('condition_id')
                            new_cond_id = next(i for i in range(2+max(all_cond_id)) if i not in all_cond_id)

                        cond_key = {'condition_id': new_cond_id}
                        ConditionParams.insert1(cond_key)

                        # insert Force, Stim, and Target tables
                        for cond_part_name in ['Force', 'Stim', 'Target']:

                            # attributes for part table
                            cond_part_attr = cond_attr[cond_part_name]

                            if not(cond_part_attr):
                                continue

                            cond_part_rel = getattr(ConditionParams, cond_part_name)
                            cond_part_id = cond_part_name.lower() + '_id'

                            if not(cond_part_rel & cond_part_attr):

                                if not(cond_part_rel()):
                                    new_cond_part_id = 0
                                else:
                                    all_cond_part_id = cond_part_rel.fetch(cond_part_id)
                                    new_cond_part_id = next(i for i in range(2+max(all_cond_part_id)) if i not in all_cond_part_id)

                                cond_part_attr[cond_part_id] = new_cond_part_id
                            else:
                                cond_part_attr[cond_part_id] = (cond_part_rel & cond_part_attr).fetch(cond_part_id, limit=1)[0]

                            cond_part_rel.insert1(dict(**cond_key, **cond_part_attr))

                        # insert target type table
                        targ_type_rel.insert1(dict(**cond_key, **cond_attr['TargetType'], target_id=cond_attr['Target']['target_id']))
                    

            # populate trials from data files
            success_state = (TaskState() & 'task_state_name="Success"').fetch1('task_state_id')

            for f_data in data_files:

                # trial number
                trial = int(re.search(r'beh_(\d*)',f_data).group(1))

                # find matching parameters file
                try:
                    param_file = next(filter(lambda f: f_data.replace('data','params')==f, param_files))
                except StopIteration:
                    print('Missing parameters file for trial {}'.format(trial))
                else:
                    # convert params to condition keys
                    params = speedgoat.readtrialparams(behavior_path + param_file)
                    cond_attr, cond_rel, targ_type_rel = ConditionParams.parseparams(params)

                    # read data
                    data = speedgoat.readtrialdata(behavior_path + f_data, success_state, fs)

                    # aggregate condition part table parameters into a single dictionary
                    all_cond_attr = {k: v for d in list(cond_attr.values()) for k, v in d.items()}

                    # insert condition data
                    cond_id = (cond_rel & all_cond_attr).fetch1('condition_id')
                    cond_key = dict(**key, condition_id=cond_id)
                    Behavior.Condition.insert1(cond_key, skip_duplicates=True)

                    # insert trial data
                    trial_key = dict(**cond_key, **data, trial_number=trial, save_tag=params['saveTag'])
                    Behavior.Trial.insert1(trial_key)


@schema
class SessionBlock(dj.Manual):
    definition = """
    # Set of save tags and arm postures for conducting analyses
    -> acquisition.Session
    block_id: tinyint unsigned # block ID
    ---
    -> ArmPosture
    """
    
    class SaveTag(dj.Part):
        definition = """
        # Block save tags
        -> master
        -> acquisition.Session.SaveTag
        """