#!/usr/bin/env python
'''Generate indices from 0 to N-1.'''

# Command line processing and usage help

import argparse
parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
parser.add_argument('N', type=int, help='Number of indices to generate')
parser.add_argument('-o', "--offset", type=int, help="specify non-zero offset")
parser.add_argument('-r', "--reverse", action="store_true")
args=parser.parse_args()

offset=0
if args.offset:  offset+=args.offset

if args.reverse:
    for i in range(0,args.N):  print(args.N+offset-i-1)
else:
    for i in range(0,args.N):  print(i+offset)
    

