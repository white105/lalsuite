## Octave script for comparing the 1st stage Fstat calculation of 
## HierarchicalSearch.c with ComputeFStatistic_v2. We run
## HierarchicalSearch using 1 stack and compare the outputs on the same
## parameter space.  The
## reference time is allowed to be different from the start time of the
## first sft. 


## Set the parameters

fStart=310;
fBand=0.05;
DataFiles="/home/badkri/fakesfts2/H-1_H*.sft";
skyfile="./skypatchfile";

system("rm -rf ./outMulti");
system("mkdir -p ./outMulti");

cmdline = sprintf("./DriveHoughMulti --sftDir=%s --printStats=1 \
--printTemplates=1 --f0=%.12g --fSearchBand=%.12g  --skyfile=%s", \
		  DataFiles, fStart, fBand, skyfile);

[output,status] = system(cmdline);

load outMulti/skypatch_1/HMtemplates

FreqVector = HMtemplates(:,4);
fdotVector = HMtemplates(:,5);
AlphaVector = HMtemplates(:,2);
DeltaVector = HMtemplates(:,3);

N1 =  HMtemplates(:,1);


load skypatchfile;

## look at the first skypatch only -- for now
AlphaWeight = skypatchfile(1,1);
DeltaWeight = skypatchfile(1,2);


for index = 1:length(FreqVector)
##for index = 1:2

length(FreqVector) - index

cmdline = sprintf("./ValidateHoughMulti --sftDir=%s \
--fStart=%.12g --fSearchBand=%.12g  --Alpha=%.12g --Delta=%.12g \
--Freq=%.12g --fdot=%.12g --AlphaWeight=%.12g --DeltaWeight=%.12g",\
		  DataFiles, fStart, fBand, AlphaVector(index), \
		  DeltaVector(index), FreqVector(index), \
		  fdotVector(index), AlphaWeight, DeltaWeight); 


[output,status] = system(cmdline);

load tempout;

diff(index) = N1(index) - tempout(1);

endfor 


