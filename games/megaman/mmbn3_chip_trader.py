#!/usr/bin/env python3

import csv

from typing import List

from utils import path_utils

HEADER_NAME_TO_INDEX = {
    "bugfrag_10": 7,
    "dnn_10": 6,
    "hospital_10": 5,
    "higsby_3": 4,
}


def main() -> None:
    rows_reconstructed: List[List[str]] = []

    with path_utils.open_unix_safely("mmbn3-chip-trader.csv") as csvfile:
        spamreader = csv.reader(csvfile, delimiter=" ", quotechar="|")
        for i, row_raw in enumerate(spamreader):
            if i != 0:
                row_split = row_raw[0].split(",")
                is_in_reconstructed = False
                for row in rows_reconstructed:
                    if row[:4] == row_split[:4]:
                        is_in_reconstructed = True
                        row[HEADER_NAME_TO_INDEX[row_split[4]]] = "o"
                if not is_in_reconstructed:
                    rows_reconstructed.append([row_split[0], row_split[1], row_split[2], row_split[3], "", "", "", ""])
                    rows_reconstructed[-1][HEADER_NAME_TO_INDEX[row_split[4]]] = "o"

    rows_alpha_split = []
    for row in rows_reconstructed:
        row_alpha_split = [""] * 35
        row_alpha_split[:8] = row[:8]
        for i, elem in enumerate(row):
            if i == 2:
                for c in elem.split("/"):
                    if c.isalpha():
                        index_letter = ord(c.lower()) - 97
                        index_letter_row = index_letter + 9
                        row_alpha_split[index_letter_row] = "o"
                    else:
                        assert c == "*"
                        row_alpha_split[8] = "o"
        rows_alpha_split.append(row_alpha_split)

    print(
        "num,name,code,star,higsby_3,hospital_10,dnn_10,bugfrag_10,*,a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z"
    )
    for row in rows_alpha_split:
        print(",".join([r if r != "" else "x" for r in row]))


if __name__ == "__main__":
    main()
