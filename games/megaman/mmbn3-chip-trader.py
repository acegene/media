#!/usr/bin/env python3
#
# type: ignore # TODO

import csv

from typing import List

rows_reconstructed: List[List[str]] = list()

with open("mmbn3-chip-trader.csv", newline="") as csvfile:
    spamreader = csv.reader(csvfile, delimiter=" ", quotechar="|")
    for i, row in enumerate(spamreader):
        if i != 0:
            row_split = row[0].split(",")
            is_in_reconstructed = False
            for r in rows_reconstructed:
                if r[:4] == row_split[:4]:
                    is_in_reconstructed = True
                    if row_split[4] == "bugfrag_10":
                        r[7] = "o"
                    elif row_split[4] == "dnn_10":
                        r[6] = "o"
                    elif row_split[4] == "hospital_10":
                        r[5] = "o"
                    elif row_split[4] == "higsby_3":
                        r[4] = "o"
                    else:
                        assert False
            if not is_in_reconstructed:
                rows_reconstructed.append([row_split[0], row_split[1], row_split[2], row_split[3], "", "", "", ""])
                if row_split[4] == "bugfrag_10":
                    rows_reconstructed[-1][7] = "o"
                elif row_split[4] == "dnn_10":
                    rows_reconstructed[-1][6] = "o"
                elif row_split[4] == "hospital_10":
                    rows_reconstructed[-1][5] = "o"
                elif row_split[4] == "higsby_3":
                    rows_reconstructed[-1][4] = "o"
                else:
                    assert False

rows_alpha_split = []
for row in rows_reconstructed:
    row_alpha_split = [""] * 35
    row_alpha_split[:8] = row[:8]
    for i, r in enumerate(row):
        if i == 2:
            for c in r.split("/"):
                if c.isalpha():
                    index_letter = ord(c.lower()) - 97
                    index_letter_row = index_letter + 9
                    row_alpha_split[index_letter_row] = "o"
                else:
                    assert c == "*"
                    row_alpha_split[8] = "o"
    rows_alpha_split.append(row_alpha_split)

print("num,name,code,star,higsby_3,hospital_10,dnn_10,bugfrag_10,*,a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z")
for row in rows_alpha_split:
    print(",".join([r if r != "" else "x" for r in row]))
