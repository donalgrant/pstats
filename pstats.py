#!/usr/bin/env python

import sys

import pandas as pd
from functools import reduce
import numpy as np
from numpy import sqrt

def linInterp(x,a):
    '''Interpolate array a to index x'''
    if x>=len(a)-1: return a[len(a)-1]
    if x<=0:        return a[0]
    i=int(x)
    return a[i]+(a[i+1]-a[i])*(x-i)

def divs(n,i,a):  return linInterp( (len(a)+1) * i/n - 1, a)
'''Return the value a the (interpolated, unit-offset) bin i of n'''


def mom(n,a):  return a.map(lambda x,p=n:  x**p).sum()/a.count()
'''Calculate the nth moment of array a.'''
    
def dev(n,a):  return a.map(lambda x,m=a.mean(),p=n: (x-m)**p).sum()/a.count()
'''Calculate the nth deviation of array a.'''

def ndev(n,a):
    return a.map(lambda x,m=a.mean(),s=a.std(),p=n: ((x-m)/s)**p).sum()/a.count()
'''Calculate the average number of N'th standard deviations.'''

def absm(n,a): a.map(lambda x,m=a.mean(),p=n: abs(x-m)**p).sum()/a.count()
'''Calculate the nth absolute deviation.'''

# the x in the lambda function below is a pandas Series, possibly sorted

stats = { 'min':    lambda x:   x.min(),        
          'absmin': lambda x:   x.abs().min(),
          'n':      lambda x:   x.count(),         
          'max':    lambda x:   x.max(),
          'mean':   lambda x:   x.mean(),
          'sum':    lambda x:   x.sum(),
          'median': lambda x:   x.median(),     
          'range':  lambda x:   x.max()-x.min(),
          'stdev':  lambda x:   x.std(),
          'stderr': lambda x:   x.std()/sqrt(x.count()),       
          'skew':   lambda x:   x.skew(),
          'kurt':   lambda x:   x.kurt(),      
          'rms':    lambda x:   sqrt(mom(2,x)), 
          'svar':   lambda x:   x.std()**2,
          'plq':    lambda x:   x.quantile(0.25),
          'puq':    lambda x:   x.quantile(0.75),
          'absdev': lambda x:   absm(1,x), 
          'qN':     lambda n,x: x.quantile(n/100.0),
          'momN':   lambda n,x: mom(n,x),       
          'devN':   lambda n,x: dev(n,x),          
          'ndevN':  lambda n,x: ndev(n,x),  
          'absmN':  lambda n,x: absm(n,x)      
          }

# Command line processing and usage help

import argparse
parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", action="store_true")
group.add_argument("-q", "--quiet", action="store_true")
parser.add_argument("-nh","--no-header", help="turn off output headers",
                    action="store_true", dest="no_header")
parser.add_argument("--no-sort", help="don't sort input data",
                    action="store_true", dest="no_sort")
parser.add_argument("--stat_list", action="store_true",
                    help="list names of all statistics")
parser.add_argument('stats', metavar='stat_names', nargs='*',
                    help='names of statistics to calculate')
args=parser.parse_args()

if args.stat_list:
    i=1
    for k in stats.keys():
        print(k,end=' ')
        if i % 10 == 0:  print()
        i+=1
    print()
    sys.exit()

# process list of statistics to load up those which have an argument

import re
stat_capture='(\w+?)(\d+([.]\d*)?)$'

for m in filter(lambda x: re.search(stat_capture,x),args.stats):
    (s,n)=re.search(stat_capture,m).group(1,2)
    s+='N'
    if args.verbose: print(f'loading stats key {m} with lambda fn calling stats {s} with arg {n}')
    if s not in(stats):
        print(f'statistic {s} not available')
        sys.exit()
    stats[m]=lambda x,y=float(n),s=s: stats[s](y,x)

if args.verbose:
    print('all N stats loaded')
    print(args.stats)
    
# confirm all statistics are now available

for s in args.stats:
    if s not in(stats):
        print(f'statistic {s} not available')
        sys.exit()
    if re.search('\w+N$',s):
        print(f'statistic {s} requires substituting N for a numeric value')
        sys.exit()

# read all the data into a pandas dataframe

df = pd.read_csv(sys.stdin,delimiter='\s+',header=None)

if args.verbose: print(df.describe().T)

if not (args.no_header):
    for s in args.stats:
        print('{0:>10s}'.format(s),end=' ')
    print()
   
for c in range(len(df.columns)):
    for s in args.stats:
        pl=df[c].copy()
        if not args.no_sort: pl.sort_values(ascending=True, inplace=True)
        print('{:10.4g}'.format(stats[s](pl)),end=' ')
    print()
    

