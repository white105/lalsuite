"""
inspiral_online_pipe_inject.py - online inspiral pipeline driver script

This script produced the necessary condor submit and dag files to run
a prototype online analysis in E11
"""

__author__ = 'Duncan Brown <duncan@gravity.phys.uwm.edu>'
__date__ = '$Date$'
__version__ = '$Revision$'

# import standard modules
import sys, os
import popen2, time
import getopt, re, string
import socket
import tempfile
import ConfigParser
import urlparse

# import the modules we need to build the pipeline
from glue import pipeline
from lalapps import inspiral
import mkcal

def usage():
  msg = """\
Usage: lalapps_inspiral_pipe [options]

  -h, --help               display this message
  -v, --version            print version information and exit

  -f, --config-file FILE   use configuration file FILE
  -l, --log-path PATH      directory to write condor log file
"""
  print >> sys.stderr, msg

# pasrse the command line options to figure out what we should do
shortop = "hvf:l:"
longop = [
  "help",
  "version",
  "config-file=",
  "log-path="
  ]

try:
  opts, args = getopt.getopt(sys.argv[1:], shortop, longop)
except getopt.GetoptError:
  usage()
  sys.exit(1)

config_file = None
config_file = None
log_path = None

for o, a in opts:
  if o in ("-v", "--version"):
    print "$Id$"
    sys.exit(0)
  elif o in ("-h", "--help"):
    usage()
    sys.exit(0)
  elif o in ("-f", "--config-file"):
    config_file = a
  elif o in ("-l", "--log-path"):
    log_path = a
  else:
    print >> sys.stderr, "Unknown option:", o
    usage()
    sys.exit(1)

if not config_file:
  print >> sys.stderr, "No configuration file specified."
  print >> sys.stderr, "Use --config-file FILE to specify location."
  sys.exit(1)

if not log_path:
  print >> sys.stderr, "No log file path specified."
  print >> sys.stderr, "Use --log-path PATH to specify a location."
  sys.exit(1)

try: os.mkdir('cache')
except: pass
try: os.mkdir('logs')
except: pass

# create the config parser object and read in the ini file
cp = ConfigParser.ConfigParser()
cp.read(config_file)

# create a log file that the Condor jobs will write to
basename = re.sub(r'\.ini',r'',config_file)
tempfile.tempdir = log_path
tempfile.template = basename + '.dag.log.'
logfile = tempfile.mktemp()
fh = open( logfile, "w" )
fh.close()

# create the DAG writing the log to the specified directory
dag = pipeline.CondorDAG(logfile)
dag.set_dag_file(basename)

# create the Condor jobs that will be used in the DAG
df_job = pipeline.LSCDataFindJob('cache','logs',cp)
tmplt_job = inspiral.TmpltBankJob(cp)
split_job = inspiral.SplitBankJob(cp)
insp_job = inspiral.InspiralJob(cp)
sinca_job = inspiral.IncaJob(cp)
inca_job = inspiral.IncaJob(cp)
bbhinj_job = inspiral.BbhInjJob(cp)

# set better submit file names than the default
subsuffix = '.sub'
df_job.set_sub_file( basename + '.datafind'+ subsuffix )
tmplt_job.set_sub_file( basename + '.tmpltbank' + subsuffix )
split_job.set_sub_file( basename + '.splitbank' + subsuffix )
insp_job.set_sub_file( basename + '.inspiral' + subsuffix )
sinca_job.set_sub_file( basename + '.sinca' + subsuffix )
inca_job.set_sub_file( basename + '.inca' + subsuffix )
bbhinj_job.set_sub_file( basename + '.bbhinj' + subsuffix )

# set up incas for single ifo mode
sinca_job.add_opt('single-summ-value',' ')
sinca_job.add_opt('single-ifo',' ')
sinca_job.add_opt('all-data',' ')
inca_job.add_opt('single-ifo',' ')
inca_job.add_opt('all-data',' ')

# get the pad and chunk lengths from the values in the ini file
pad = int(cp.get('data', 'pad-data'))
n = int(cp.get('data', 'segment-length'))
s = int(cp.get('data', 'number-of-segments'))
r = int(cp.get('data', 'sample-rate'))
o = int(cp.get('inspiral', 'segment-overlap'))
length = ( n * s - ( s - 1 ) * o ) / r
overlap = o / r

# read science segs that are greater or equal to a chunk from the input file
data = pipeline.ScienceData()
data.read(cp.get('input','segments'),length)

# create the chunks from the science segments
data.make_chunks(length,overlap,0,0,overlap/2)
data.make_chunks_from_unused(
  length,overlap/2,0,overlap/2,0,overlap/2)

# get the order of the ifos to filter
ifo = cp.get('pipeline','ifo')
run = cp.get('pipeline','run')

# create a shell script to publish the output data
# XXX this is a hack: it should be done properly
publish_location = os.path.join(cp.get('publish','outputdir'), '${1}')
pfn_location = "gsiftp://" + socket.getfqdn() + publish_location
publish_script = open('publish.sh','w')
publish_script.write("#!/bin/bash\n")
publish_script.write("cp -f ${1} %s\n" % publish_location)
publish_script.write("ldbdc --server %s --insert %s --pfn %s\n"
  % ( cp.get('publish','ldbdserver'), publish_location, pfn_location ) )
publish_script.close()
os.chmod('publish.sh',0755)

# create all the LSCdataFind jobs to run in sequence
prev_df = None

# store things needed for a big inca at the end
dag_start_time = None
dag_end_time = None
sinca_nodes = []

for seg in data:
  # find all the data
  df = pipeline.LSCDataFindNode(df_job)
  df.set_start(seg.start() - pad)
  df.set_end(seg.end() + pad)
  df.set_observatory(ifo[0])
  if prev_df: 
    df.add_parent(prev_df)
  dag.add_node(df)
  prev_df = df

  for chunk in seg:
    # remember the start time and update the end time
    if not dag_start_time:
      dag_start_time = chunk.start()
    dag_end_time = chunk.end()

    # create the template bank job
    bank = inspiral.TmpltBankNode(tmplt_job)
    bank.set_start(chunk.start())
    bank.set_end(chunk.end())
    bank.set_ifo(ifo)
    bank.set_cache(df.get_output())
    bank.add_parent(df)
    dag.add_node(bank)
    
    # split the template bank
    split = inspiral.SplitBankNode(split_job)
    split.set_bank(bank.get_output())
    split.set_num_banks(cp.get('pipeline','numbanks'))
    split.add_parent(bank)
    dag.add_node(split)

    # create the injection parameters
    bbhinject = inspiral.BbhInjNode(bbhinj_job)
    bbhinject.set_start(chunk.start())
    bbhinject.set_end(chunk.end())
    bbhinject.set_seed(chunk.start())
    bbhinject.add_parent(split)
    dag.add_node(bbhinject)

    # create the inspiral job
    i = 0
    sub_insp = []
    for subbank in split.get_output():
      insp = inspiral.InspiralNode(insp_job)
      insp.set_start(chunk.start())
      insp.set_end(chunk.end())
      insp.add_var_opt('trig-start-time',chunk.trig_start())
      insp.set_ifo(ifo)
      insp.set_cache(df.get_output())
      insp.set_bank(subbank)
      insp.set_injections(bbhinject.get_output())
      insp.set_user_tag("%2.2d" % i)
      i = i + 1
      insp.add_parent(bbhinject)
      dag.add_node(insp)
      sub_insp.append(insp)

    # create the inca that stitches the inspiral jobs back together
    sinca = inspiral.IncaNode(sinca_job)
    sinca.set_ifo_a(ifo)
    sinca.set_start(chunk.start())
    sinca.set_end(chunk.end())
    for insp in sub_insp:
      sinca.add_parent(insp)
      sinca.add_var_arg(insp.get_output())
    sinca.set_post_script( "/bin/ln -sf %s %s" % 
      (os.path.join(os.getcwd(), sinca.get_output_a()), 
       os.path.join(cp.get('publish','dmtdir'), sinca.get_output_a())) )
    dag.add_node(sinca)
    sinca_nodes.append(sinca)

# use inca to concatenate all the inspiral files
inca = inspiral.IncaNode(inca_job)
inca.set_ifo_a(ifo)
inca.set_start(dag_start_time)
inca.set_end(dag_end_time)
inca.set_post_script("publish.sh %s" % inca.get_output_a())
for sinca in sinca_nodes:
  inca.add_parent(sinca)
  inca.add_var_arg(sinca.get_output_a())
dag.add_node(inca)

# write the dag
dag.write_sub_files()
dag.write_dag()

# write out a log file for this script
log_fh = open(basename + '.pipeline.log', 'w')
  
# FIXME: the following code uses obsolete CVS ID tags.
# It should be modified to use git version information.
log_fh.write( "$Id$" + "\n\n" )
log_fh.write( "Invoked with arguments:\n" )
for o, a in opts:
  log_fh.write( o + ' ' + a + '\n' )
log_fh.write( "\n" )
log_fh.write( "Parsed " + str(len(data)) + " science segments\n" )
total_data = 0
for seg in data:
  for chunk in seg:
    total_data += len(chunk)
print >> log_fh, "total data =", total_data

print >> log_fh, "\n===========================================\n"
print >> log_fh, data
for seg in data:
  print >> log_fh, seg
  for chunk in seg:
    print >> log_fh, chunk

sys.exit(0)
