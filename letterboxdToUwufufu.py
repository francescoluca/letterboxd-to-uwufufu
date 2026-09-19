#import requests
import csv
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("file", help="CSV path file")
args = parser.parse_args()

with open(args.file) as f:
    reader = csv.reader(f)
    next(reader)    #to skip header
    for row in reader:
        print(row)